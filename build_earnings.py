#!/usr/bin/env python3
"""
Build earnings.csv from SEC EDGAR 8-K Item 2.02 filings.

Free, official, complete history, no API key, no rate-limit tier games.
An 8-K with Item 2.02 ("Results of Operations and Financial Condition")
IS the earnings announcement. The filing acceptance timestamp gives you
the BMO/AMC timing that a calendar scrape usually loses.

  python build_earnings.py --symbols AAPL,MSFT --years 4 --out earnings.csv
  python build_earnings.py --from-universe universe.txt --years 4

!! I COULD NOT TEST THIS. My sandbox cannot reach sec.gov (proxy 403).
!! The endpoints and JSON shapes are as documented, but verify on 2-3
!! symbols before trusting a 400-symbol run.

SCHEMA WRITTEN:
    symbol,date,timing,accession
    AAPL,2025-10-30,amc,0000320193-25-000103
    MSFT,2025-10-29,amc,0000789019-25-000041

  date      YYYY-MM-DD, the filing/announcement date
  timing    bmo | amc | unknown
            bmo = accepted before 09:30 ET -> affects THAT day's open
            amc = accepted after 16:00 ET  -> affects the NEXT day's open
  accession for audit; drop the column if you prefer, the loader ignores it

WHY TIMING MATTERS: an AMC report on day T moves day T+1. A symmetric
+/-7 day blackout absorbs this, so timing is optional for Stage 1. It
becomes load-bearing in Stage 2 when you are deciding whether tomorrow's
open is safe to enter.
"""
import argparse, csv, json, os, sys, time
from datetime import datetime, timedelta, timezone
try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:
    ET = timezone(timedelta(hours=-5))

# See timing_from(). Verify with the 3-symbol run before the 400-symbol loop.
SEC_TS_IS_UTC = True
from urllib.request import Request, urlopen

# SEC requires a descriptive User-Agent with contact info. They will
# block you without it. Put YOUR email here.
UA = os.environ.get("SEC_UA", "swing-research yourname@example.com")
HDRS = {"User-Agent": UA, "Accept-Encoding": "gzip, deflate"}
RATE = 0.11          # SEC asks <= 10 req/sec; this is ~9


def get(url):
    time.sleep(RATE)
    req = Request(url, headers=HDRS)
    with urlopen(req, timeout=30) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            import gzip
            raw = gzip.decompress(raw)
        return json.loads(raw)


def ticker_to_cik():
    """SEC's official ticker->CIK map."""
    data = get("https://www.sec.gov/files/company_tickers.json")
    return {v["ticker"].upper(): str(v["cik_str"]).zfill(10)
            for v in data.values()}


def earnings_8ks(cik, since):
    """
    All 8-K filings with Item 2.02 for one CIK.
    data.sec.gov/submissions/CIK##########.json holds ~1000 recent filings
    inline plus older ones in referenced files. For 3-4 years of 8-Ks the
    inline block is normally sufficient; we follow the overflow files too.
    """
    base = get(f"https://data.sec.gov/submissions/CIK{cik}.json")
    blocks = [base["filings"]["recent"]]
    for extra in base["filings"].get("files", []):
        if extra.get("filingTo", "9999") >= since:
            blocks.append(get(f"https://data.sec.gov/submissions/{extra['name']}"))

    out = []
    for b in blocks:
        forms = b.get("form", [])
        for i, form in enumerate(forms):
            if form != "8-K":
                continue
            items = (b.get("items") or [""] * len(forms))[i]
            if "2.02" not in (items or ""):
                continue
            fdate = b["filingDate"][i]
            if fdate < since:
                continue
            acc = b["accessionNumber"][i]
            adt = (b.get("acceptanceDateTime") or [None] * len(forms))[i]
            out.append((fdate, timing_from(adt), acc))
    return out


def timing_from(accept_iso):
    """
    Classify an 8-K acceptance timestamp as bmo / intraday / amc.

    !! UNRESOLVED: I am not certain whether SEC's acceptanceDateTime is
    !! UTC or already Eastern. It is often rendered with a trailing Z that
    !! may be cosmetic. Both interpretations are computed below and the
    !! 3-symbol verification run is designed to tell you which is right:
    !!   AAPL and MSFT report AFTER the close -> must come back 'amc'
    !!   JPM reports BEFORE the open          -> must come back 'bmo'
    !! If AAPL shows 'intraday' in summer months but 'amc' in winter, the
    !! timestamps are UTC and SEC_TS_IS_UTC below is correct. If AAPL is
    !! 'amc' year-round only when SEC_TS_IS_UTC=False, flip it.

    The previous version used a fixed -5 offset and silently misclassified
    every after-close filing during EDT (March-November) as 'intraday'.
    """
    if not accept_iso:
        return "unknown"
    try:
        s = accept_iso.replace("Z", "")
        t = datetime.fromisoformat(s)
        if SEC_TS_IS_UTC:
            t = t.replace(tzinfo=timezone.utc).astimezone(ET)
        mins = t.hour * 60 + t.minute
        if mins < 9 * 60 + 30:
            return "bmo"
        if mins >= 16 * 60:
            return "amc"
        return "intraday"
    except Exception:
        return "unknown"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols")
    ap.add_argument("--from-universe", help="file with one symbol per line")
    ap.add_argument("--years", type=int, default=4)
    ap.add_argument("--out", default="earnings.csv")
    a = ap.parse_args()

    if "@example.com" in UA:
        sys.exit("Set SEC_UA to 'yourproject your@email.com'. SEC blocks generic agents.")

    if a.from_universe:
        syms = [l.strip().upper() for l in open(a.from_universe) if l.strip()]
    elif a.symbols:
        syms = [s.strip().upper() for s in a.symbols.split(",")]
    else:
        sys.exit("Need --symbols or --from-universe")

    since = (datetime.now() - timedelta(days=365 * a.years + 60)).strftime("%Y-%m-%d")
    print(f"mapping tickers -> CIK")
    cmap = ticker_to_cik()

    missing, rows = [], []
    for i, s in enumerate(syms, 1):
        cik = cmap.get(s)
        if not cik:
            missing.append(s); continue
        try:
            for d, tim, acc in earnings_8ks(cik, since):
                rows.append((s, d, tim, acc))
        except Exception as e:
            print(f"  !! {s}: {e}")
            missing.append(s)
        if i % 25 == 0:
            print(f"  {i}/{len(syms)}  rows={len(rows)}")

    with open(a.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "date", "timing", "accession"])
        w.writerows(sorted(set(rows)))

    print(f"\nwrote {a.out}: {len(set(rows))} announcements, "
          f"{len({r[0] for r in rows})} symbols")
    if missing:
        print(f"NO DATA for {len(missing)} symbols: {missing[:20]}")
        print("These FAIL CLOSED in the backtest (never traded). That is correct")
        print("behaviour, but if the list is long your effective universe shrank.")
        print("Common causes: foreign issuers file 6-K not 8-K; ETFs have no")
        print("earnings at all and should be excluded from the universe upstream.")


if __name__ == "__main__":
    main()
