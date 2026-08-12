#!/usr/bin/env python3
"""
PHASE 2 / crypto observation scanner. LOGS ONLY -- places no orders.

Fetches daily bars for the most liquid Alpaca crypto pairs, computes the
same reversal features used in the equity rule, and records EVERY symbol
every day (not just signals). Logging non-signal days too means the
dataset carries its own control group: later you can compare forward
returns on signal days vs all other days without any new collection.

No pre-registration covers crypto TRADING, so none happens. This file
cannot submit an order; there is no trading client import.
"""
from __future__ import annotations
import sqlite3
from datetime import date, datetime, timedelta, timezone

SYMBOLS = ["BTC/USD", "ETH/USD", "SOL/USD", "LTC/USD",
           "DOGE/USD", "LINK/USD", "AVAX/USD", "BCH/USD"]
DB = "logbook.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS crypto_obs (
  obs_date TEXT NOT NULL,
  symbol TEXT NOT NULL,
  close REAL, ret1d REAL, z20 REAL, pct_vs_sma200 REAL,
  vol20_ann REAL, signal INTEGER, recorded_ts TEXT,
  PRIMARY KEY (obs_date, symbol)
);
"""


def fetch_bars(days=260):
    from alpaca.data.historical import CryptoHistoricalDataClient
    from alpaca.data.requests import CryptoBarsRequest
    from alpaca.data.timeframe import TimeFrame
    c = CryptoHistoricalDataClient()          # crypto data needs no keys
    req = CryptoBarsRequest(symbol_or_symbols=SYMBOLS, timeframe=TimeFrame.Day,
                            start=datetime.now(timezone.utc) - timedelta(days=days + 10))
    bars = c.get_crypto_bars(req)
    out = {}
    for s in SYMBOLS:
        rows = bars.data.get(s, [])
        out[s] = [float(b.close) for b in rows][-days:]
    return out


def features(closes):
    """Same shape as the equity rule: z vs 20d, position vs 200d, red day."""
    if len(closes) < 201:
        return None
    px = closes[-1]
    ret1d = px / closes[-2] - 1
    win = closes[-21:-1]
    m = sum(win) / len(win)
    sd = (sum((x - m) ** 2 for x in win) / (len(win) - 1)) ** 0.5
    z20 = (px - m) / sd if sd else 0.0
    sma200 = sum(closes[-200:]) / 200
    rets = [closes[i] / closes[i - 1] - 1 for i in range(len(closes) - 20, len(closes))]
    mm = sum(rets) / len(rets)
    vol = (sum((r - mm) ** 2 for r in rets) / (len(rets) - 1)) ** 0.5 * (365 ** 0.5) * 100
    sig = 1 if (px > sma200 and z20 <= -1.5 and ret1d < 0) else 0
    return dict(close=px, ret1d=100 * ret1d, z20=z20,
                pct_vs_sma200=100 * (px / sma200 - 1), vol20_ann=vol, signal=sig)


def main():
    today = str(date.today())
    con = sqlite3.connect(DB)
    con.executescript(SCHEMA)
    try:
        bars = fetch_bars()
    except Exception as e:
        print(f"crypto fetch failed (non-fatal): {e}")
        return
    n_sig = 0
    print(f"\nCRYPTO OBSERVATION {today}  (logged, never traded)")
    print(f"  {'symbol':<10}{'close':>12}{'1d%':>8}{'z20':>7}{'vs200d':>9}{'signal':>8}")
    for s in SYMBOLS:
        f = features(bars.get(s, []))
        if f is None:
            print(f"  {s:<10}{'insufficient history':>30}")
            continue
        n_sig += f["signal"]
        print(f"  {s:<10}{f['close']:>12,.2f}{f['ret1d']:>8.2f}{f['z20']:>7.2f}"
              f"{f['pct_vs_sma200']:>8.1f}%{('  YES' if f['signal'] else '   --'):>8}")
        con.execute("INSERT OR REPLACE INTO crypto_obs VALUES (?,?,?,?,?,?,?,?,?)",
                    (today, s, f["close"], f["ret1d"], f["z20"], f["pct_vs_sma200"],
                     f["vol20_ann"], f["signal"],
                     datetime.now(timezone.utc).isoformat(timespec="seconds")))
    con.commit()
    n = con.execute("SELECT COUNT(*) FROM crypto_obs").fetchone()[0]
    d = con.execute("SELECT COUNT(DISTINCT obs_date) FROM crypto_obs").fetchone()[0]
    print(f"\n  signals today: {n_sig} | dataset: {n} observations over {d} days")
    print("  NO ORDERS. Crypto is observation-only until a rule is pre-registered.")
    con.close()


if __name__ == "__main__":
    main()
