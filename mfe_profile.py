#!/usr/bin/env python3
"""
STAGE 0.5 -- SIGNAL PROFILER.

Runs the entry rule and records what happens next. NO TARGET. NO STOP.
NO POSITION LIMIT. NO CAPITAL. Nothing here can be tuned toward a gate
because nothing here knows a gate exists.

Outputs, per horizon t+1..t+5:
  forward return distribution
  MFE  max favourable excursion (best intrabar high vs entry)
  MAE  max adverse excursion    (worst intrabar low vs entry)
  P(touch) for a ladder of candidate targets
  the implied natural target/stop, read off the data

READ ORDER: run this, look at the MFE/MAE percentiles, pick the target
from where the move ACTUALLY goes, then and only then compute whether
the gate is reachable. If it is not reachable, that is a result about
your capacity, not a reason to move the target.

  python mfe_profile.py --years 3 --earnings earnings.csv --max-symbols 400
"""
import argparse, os, sys
from datetime import date, timedelta
from collections import defaultdict

import stage1_data as D
from signals import signal_reversal

HORIZONS = (1, 2, 3, 4, 5)
TARGET_LADDER = (1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0)
STOP_LADDER = (1.0, 1.25, 1.5, 2.0, 2.5, 3.0)


def pct(xs, q):
    if not xs: return 0.0
    s = sorted(xs); k = (len(s) - 1) * q / 100
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def profile(bars_by_sym, signal_fn, eligible, halted, earnings, bad):
    idx = {s: {b["date"]: i for i, b in enumerate(bars)}
           for s, bars in bars_by_sym.items()}
    all_dates = sorted({b["date"] for bs in bars_by_sym.values() for b in bs})
    hist = {s: [] for s in bars_by_sym}
    obs = []

    for today in all_dates:
        for sym in signal_fn(hist, today):
            bars = bars_by_sym.get(sym)
            i = idx.get(sym, {}).get(today)
            if bars is None or i is None or i + max(HORIZONS) >= len(bars):
                continue
            if not eligible.get(sym, {}).get(today, False): continue
            if today in halted.get(sym, set()): continue
            if today in bad.get(sym, set()): continue
            if D.in_earnings_blackout(sym, today, earnings): continue

            entry = bars[i]["open"]           # next-bar-open discipline preserved
            if entry <= 0: continue
            rec = {"sym": sym, "date": today, "entry": entry}
            run_hi, run_lo = -1e9, 1e9
            for h in HORIZONS:
                b = bars[i + h]
                run_hi = max(run_hi, b["high"])
                run_lo = min(run_lo, b["low"])
                rec[f"ret{h}"] = (b["close"] / entry - 1) * 100
                rec[f"mfe{h}"] = (run_hi / entry - 1) * 100
                rec[f"mae{h}"] = (run_lo / entry - 1) * 100
            obs.append(rec)

        for s in hist:
            bs = bars_by_sym.get(s)
            j = idx.get(s, {}).get(today)
            if j is not None: hist[s].append(bs[j])
    return obs


def report(obs):
    n = len(obs)
    if not n:
        print("NO SIGNALS. Check filters before concluding anything."); return
    print(f"\n{'='*84}\nSIGNAL PROFILE -- n = {n} raw signal events "
          f"(pre-capacity, no 3-slot limit applied)\n{'='*84}")

    dates = defaultdict(int)
    for o in obs: dates[o["date"]] += 1
    print(f"  distinct entry dates : {len(dates)}")
    print(f"  mean signals per active date : {n/len(dates):.2f}")
    print(f"  max signals on one date : {max(dates.values())}")
    top = sorted(dates.values(), reverse=True)
    print(f"  share of signals on the busiest 10% of dates : "
          f"{100*sum(top[:max(1,len(top)//10)])/n:.1f}%")
    print("  ^^ this is the clustering problem, measured. See bootstrap.py")

    print(f"\n{'horizon':<9}{'median':>9}{'mean':>9}{'p25':>9}{'p75':>9}{'p90':>9}")
    print("-"*54)
    for h in HORIZONS:
        r = [o[f"ret{h}"] for o in obs]
        print(f"  t+{h:<6}{pct(r,50):>8.2f}%{sum(r)/len(r):>8.2f}%"
              f"{pct(r,25):>8.2f}%{pct(r,75):>8.2f}%{pct(r,90):>8.2f}%")

    print(f"\nMAX FAVOURABLE EXCURSION (how far the move actually goes)")
    print(f"{'by t+':<9}{'median':>9}{'p75':>9}{'p90':>9}{'p95':>9}")
    print("-"*45)
    for h in HORIZONS:
        m = [o[f"mfe{h}"] for o in obs]
        print(f"  t+{h:<6}{pct(m,50):>8.2f}%{pct(m,75):>8.2f}%"
              f"{pct(m,90):>8.2f}%{pct(m,95):>8.2f}%")

    print(f"\nMAX ADVERSE EXCURSION (how much heat before it works)")
    print(f"{'by t+':<9}{'median':>9}{'p75':>9}{'p90':>9}{'p95':>9}")
    print("-"*45)
    for h in HORIZONS:
        m = [o[f"mae{h}"] for o in obs]
        print(f"  t+{h:<6}{pct(m,50):>8.2f}%{pct(m,25):>8.2f}%"
              f"{pct(m,10):>8.2f}%{pct(m,5):>8.2f}%")

    print(f"\nP(TOUCH TARGET within 5 days)   -- picks the target, honestly")
    print(f"{'target':<10}{'P(touch)':>11}{'P(touch first, MAE>-1.5%)':>28}")
    print("-"*49)
    for t in TARGET_LADDER:
        hit = [o for o in obs if o["mfe5"] >= t]
        clean = [o for o in hit if o["mae5"] > -1.5]
        print(f"  {t:.1f}%{100*len(hit)/n:>13.1f}%{100*len(clean)/n:>25.1f}%")

    print(f"\nP(STOP HIT within 5 days)")
    for s in STOP_LADDER:
        hit = sum(1 for o in obs if o["mae5"] <= -s)
        print(f"  -{s:.2f}% : {100*hit/n:>5.1f}%")

    print(f"\n{'='*84}\nIMPLIED NATURAL PARAMETERS (read off the data, not chosen)\n{'='*84}")
    med_mfe = pct([o["mfe5"] for o in obs], 50)
    p75_mfe = pct([o["mfe5"] for o in obs], 75)
    med_mae = pct([o["mae5"] for o in obs], 50)
    p25_mae = pct([o["mae5"] for o in obs], 25)
    print(f"  median MFE  {med_mfe:.2f}%   p75 MFE {p75_mfe:.2f}%")
    print(f"  median MAE  {med_mae:.2f}%   p25 MAE {p25_mae:.2f}%")
    print(f"\n  A target near the MEDIAN MFE is hit ~50% of the time.")
    print(f"  A target near the p75 MFE is hit ~25% of the time.")
    print(f"  A stop tighter than the median MAE stops out over half your")
    print(f"  winners before they work. That is the constraint that actually")
    print(f"  binds, and it is why a 1.5% stop may simply be wrong.")
    print(f"\n  IF median MFE < 3%, the 4.0% target is not supported by this")
    print(f"  signal and should not be used regardless of what the gate needs.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=6)
    ap.add_argument("--universe", default="universe.txt")
    ap.add_argument("--earnings", default="earnings.csv")
    a = ap.parse_args()

    earnings = D.load_earnings(a.earnings)
    if earnings is None:
        sys.exit(f"No {a.earnings}. Run build_earnings.py first. Fails closed.")

    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=365*a.years + 300)   # +300 for 200d warmup
    if not os.path.exists(a.universe):
        sys.exit(f"No {a.universe}. Run build_universe_file.py first.\n"
                 "Refusing to fall back to list_tradable_universe(), which\n"
                 "sorts alphabetically and would silently give you an A-C slice.")
    syms = [l.strip() for l in open(a.universe) if l.strip()]
    print(f"universe: {len(syms)} symbols from {a.universe}")
    print(f"fetching {len(syms)} symbols, {start} .. {end}")
    bars = D.fetch_daily_bars(syms, start, end)
    halted = D.flag_halts(bars)
    bad = {s: D.detect_unadjusted_splits(b) for s, b in bars.items()}
    eligible, _ = D.build_universe(bars)
    print(f"{len(eligible)} symbols pass filters\n")

    obs = profile(bars, signal_reversal, eligible, halted, earnings, bad)
    report(obs)

    import json
    with open("profile_obs.json", "w") as f:
        json.dump([{k: (str(v) if k == "date" else v) for k, v in o.items()}
                   for o in obs], f)
    print("\nwrote profile_obs.json")


if __name__ == "__main__":
    main()
