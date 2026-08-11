"""
STAGE 1 / data layer.

ASSUMPTIONS FLAGGED (change at top of file, do not bury):
  A1. "ADV > 2M" read as 2,000,000 SHARES/day median over the lookback.
      Dollar ADV also computed because that is what actually drives spread.
  A2. adjustment='split'. NOT 'all'. Dividend-adjusted prices distort the
      $10-100 price filter and shift stop distances by the dividend yield.
      For a price-level strategy you want split-only.
  A3. Earnings exclusion FAILS CLOSED. If we cannot confirm a symbol's
      earnings dates, the symbol is dropped, not traded. There is no free
      earnings calendar in Alpaca; you must supply one.
  A4. Halt detection is heuristic: a session with volume==0, or a missing
      session while >70% of the universe traded. Alpaca does not expose
      halt flags on daily bars.
  A5. Survivorship: Alpaca returns delisted symbols only if you name them.
      A universe built from *today's* active assets is survivorship-biased
      and will overstate returns. See build_universe() note.
"""
from __future__ import annotations
import os, csv
from datetime import date, timedelta
from collections import defaultdict

MIN_PRICE, MAX_PRICE = 10.0, 100.0
MIN_ADV_SHARES = 2_000_000
EARNINGS_BLACKOUT_DAYS = 7          # >= max_hold(5) + 2 buffer


# ----------------------------------------------------------------- fetch
def fetch_daily_bars(symbols, start: date, end: date):
    """Returns {symbol: [ {date, open, high, low, close, volume}, ... ]}"""
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from alpaca.data.enums import Adjustment

    key, sec = os.environ.get("APCA_API_KEY_ID"), os.environ.get("APCA_API_SECRET_KEY")
    if not key or not sec:
        raise SystemExit("Set APCA_API_KEY_ID and APCA_API_SECRET_KEY.")
    client = StockHistoricalDataClient(key, sec)

    out = defaultdict(list)
    CHUNK = 100
    for i in range(0, len(symbols), CHUNK):
        batch = symbols[i:i + CHUNK]
        req = StockBarsRequest(symbol_or_symbols=batch, timeframe=TimeFrame.Day,
                               start=start, end=end,
                               adjustment=Adjustment.SPLIT)   # A2
        bars = client.get_stock_bars(req)
        for sym, rows in bars.data.items():
            for b in rows:
                out[sym].append(dict(date=b.timestamp.date(), open=float(b.open),
                                     high=float(b.high), low=float(b.low),
                                     close=float(b.close), volume=float(b.volume)))
        print(f"  fetched {min(i+CHUNK, len(symbols))}/{len(symbols)} symbols")
    for s in out:
        out[s].sort(key=lambda r: r["date"])
    return dict(out)


def list_tradable_universe(max_symbols=None):
    """
    A5 WARNING: this returns symbols ACTIVE TODAY. Anything that delisted,
    was acquired, or went to zero during your backtest window is absent.
    That is survivorship bias and it inflates results. To do this properly
    you need a point-in-time constituent list (Sharadar/Norgate/CRSP, paid).
    Treat any Stage 1 result from this universe as an OPTIMISTIC bound.
    """
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import GetAssetsRequest
    from alpaca.trading.enums import AssetClass, AssetStatus

    tc = TradingClient(os.environ["APCA_API_KEY_ID"],
                       os.environ["APCA_API_SECRET_KEY"], paper=True)
    assets = tc.get_all_assets(GetAssetsRequest(status=AssetStatus.ACTIVE,
                                                asset_class=AssetClass.US_EQUITY))
    syms = sorted(a.symbol for a in assets
                  if a.tradable and a.fractionable and a.exchange.value in
                  ("NASDAQ", "NYSE", "ARCA", "AMEX") and "." not in a.symbol)
    return syms[:max_symbols] if max_symbols else syms


# ----------------------------------------------------- filters / hygiene
def median(xs):
    xs = sorted(xs)
    n = len(xs)
    return 0.0 if not n else (xs[n//2] if n % 2 else (xs[n//2-1]+xs[n//2])/2)


def flag_halts(bars_by_sym):
    """A4. Returns {symbol: set(dates)} of sessions to treat as untradeable."""
    all_dates = defaultdict(int)
    for bars in bars_by_sym.values():
        for b in bars:
            all_dates[b["date"]] += 1
    n = len(bars_by_sym)
    market_days = {d for d, c in all_dates.items() if c > 0.70 * n}

    halted = {}
    for sym, bars in bars_by_sym.items():
        have = {b["date"] for b in bars}
        bad = {b["date"] for b in bars if b["volume"] == 0}
        span = [d for d in market_days if bars[0]["date"] <= d <= bars[-1]["date"]]
        bad |= (set(span) - have)
        if bad:
            halted[sym] = bad
    return halted


def detect_unadjusted_splits(bars, threshold=0.35):
    """
    A2 sanity check. Even with adjustment='split', a missed corporate action
    shows up as a one-day move > threshold with no volume confirmation.
    Returns dates to distrust. Do not silently trade through these.
    """
    out = set()
    for i in range(1, len(bars)):
        prev, cur = bars[i-1]["close"], bars[i]["open"]
        if prev > 0 and abs(cur/prev - 1) > threshold:
            out.add(bars[i]["date"])
    return out


def load_earnings(path):
    """
    A3. CSV: symbol,date  (one row per announcement, YYYY-MM-DD).
    Sources: Financial Modeling Prep free tier, Nasdaq calendar scrape,
    or your broker. Alpaca does NOT provide this.
    Returns {symbol: set(date)} or None if the file is absent.
    """
    if not path or not os.path.exists(path):
        return None
    out = defaultdict(set)
    with open(path) as f:
        for row in csv.DictReader(f):
            y, m, d = row["date"].split("-")
            out[row["symbol"].strip().upper()].add(date(int(y), int(m), int(d)))
    return dict(out)


def in_earnings_blackout(sym, day, earnings, days=EARNINGS_BLACKOUT_DAYS):
    """A3 fail-closed: unknown symbol -> treated as blacked out."""
    if earnings is None:
        return True
    if sym not in earnings:
        return True
    return any(abs((e - day).days) <= days for e in earnings[sym])


def build_universe(bars_by_sym, lookback=60):
    """Apply price band + liquidity floor. Returns {symbol: {date: eligible}}."""
    eligible = {}
    stats = {}
    for sym, bars in bars_by_sym.items():
        if len(bars) < lookback + 21:
            continue
        ok = {}
        for i in range(lookback, len(bars)):
            w = bars[i-lookback:i]
            px = median([b["close"] for b in w])
            adv = median([b["volume"] for b in w])
            ok[bars[i]["date"]] = (MIN_PRICE <= px <= MAX_PRICE
                                   and adv >= MIN_ADV_SHARES)
        if any(ok.values()):
            eligible[sym] = ok
            w = bars[-lookback:]
            stats[sym] = dict(px=median([b["close"] for b in w]),
                              adv=median([b["volume"] for b in w]),
                              dollar_adv=median([b["close"]*b["volume"] for b in w]))
    return eligible, stats


def select_by_liquidity(start: date, n_top=400, probe_days=90, batch=200):
    """
    Two-pass universe selection. Replaces alphabetical truncation.

    Pass 1: fetch a short probe window at the START of the backtest and
            rank every tradable symbol by median dollar ADV.
    Pass 2: caller fetches full history for the top n_top only.

    LOOKAHEAD NOTE: ranking on the START of the window rather than on
    today is deliberate. Ranking by today's liquidity would select names
    that BECAME liquid, which is a forward-looking filter. This still
    cannot fix survivorship (A5) -- delisted names are absent from the
    asset list entirely -- but it removes the second, avoidable bias.
    """
    syms = list_tradable_universe()
    print(f"  probing {len(syms)} symbols for liquidity, "
          f"{start} .. {start + timedelta(days=probe_days)}")
    scored = []
    for i in range(0, len(syms), batch):
        chunk = syms[i:i+batch]
        try:
            bars = fetch_daily_bars(chunk, start, start + timedelta(days=probe_days))
        except Exception as e:
            print(f"  !! probe batch {i} failed: {e}"); continue
        for s, bs in bars.items():
            if len(bs) < probe_days // 3:
                continue
            px = median([b["close"] for b in bs])
            if not (MIN_PRICE <= px <= MAX_PRICE):
                continue
            adv = median([b["volume"] for b in bs])
            if adv < MIN_ADV_SHARES:
                continue
            scored.append((median([b["close"]*b["volume"] for b in bs]), s))
    scored.sort(reverse=True)
    out = [s for _, s in scored[:n_top]]
    print(f"  {len(scored)} symbols pass price+ADV at window start; "
          f"taking top {len(out)} by dollar ADV")
    return out
