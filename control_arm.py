#!/usr/bin/env python3
"""
CONTROL ARM -- random-entry baseline for the profiler.

Signal-day MFE is uninterpretable on its own. Every stock has positive
max-favourable-excursion over five days purely from volatility. A median
MFE of 3% means nothing until you know what random days in the same
universe, under the same filters, produce.

Run AFTER mfe_profile.py (it reads profile_obs.json).

  python control_arm.py --years 6 --universe universe.txt --earnings earnings.csv

If the median 5-day edge over random is near zero, the signal selects
nothing and no target choice will rescue it. Stop before Stage 1 rather
than after.
"""
import argparse, json, os, random, sys
from datetime import date, timedelta

import stage1_data as D
import mfe_profile as MP


def signal_random(hist, today, p=0.004, rng=random):
    """
    Matched control. Same shape as the real signal, fires at random on
    days where the real signal COULD have fired (>=205 bars of history,
    so the 200-day trend filter would have been live). Same 3-per-day cap,
    same next-open entry, same universe, same exclusion filters.

    p is tuned to produce a control sample of roughly the same size as
    the signal sample; it does not affect the per-trade statistics.
    """
    out = [s for s in hist if len(hist[s]) >= 205 and rng.random() < p]
    return out[:3]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=6)
    ap.add_argument("--universe", default="universe.txt")
    ap.add_argument("--earnings", default="earnings.csv")
    ap.add_argument("--seed", type=int, default=20260805)
    ap.add_argument("--p", type=float, default=0.004,
                    help="per-symbol-day firing probability for the control")
    a = ap.parse_args()

    if not os.path.exists("profile_obs.json"):
        sys.exit("Run mfe_profile.py first -- this reads profile_obs.json.")
    if not os.path.exists(a.universe):
        sys.exit(f"No {a.universe}. Run build_universe_file.py first.")

    earnings = D.load_earnings(a.earnings)
    if earnings is None:
        sys.exit(f"No {a.earnings}. Run build_earnings.py first. Fails closed.")

    rng = random.Random(a.seed)
    syms = [l.strip() for l in open(a.universe) if l.strip()]
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=365 * a.years + 300)

    print(f"control arm: {len(syms)} symbols, {start} .. {end}")
    bars = D.fetch_daily_bars(syms, start, end)
    halted = D.flag_halts(bars)
    bad = {s: D.detect_unadjusted_splits(b) for s, b in bars.items()}
    elig, _ = D.build_universe(bars)

    print("\n" + "=" * 84)
    print("CONTROL: RANDOM ENTRIES (same universe, same filters, same cap)")
    print("=" * 84)
    ctl = MP.profile(bars, lambda h, t: signal_random(h, t, a.p, rng),
                     elig, halted, earnings, bad)
    print(f"control n = {len(ctl)}")

    raw = json.load(open("profile_obs.json"))
    sig = [dict(o, date=(date.fromisoformat(o["date"])
                         if isinstance(o["date"], str) else o["date"]))
           for o in raw]
    print(f"signal  n = {len(sig)}")

    if not sig or not ctl:
        sys.exit("Empty signal or control sample -- that is a bug, not a result.")

    print(f"\n{'metric':<17}{'SIGNAL':>12}{'CONTROL':>12}{'DIFF':>12}")
    print("-" * 53)
    rows = [("median ret t+5", "ret5", 50), ("mean ret t+5", "ret5", None),
            ("median ret t+1", "ret1", 50), ("median ret t+3", "ret3", 50),
            ("median MFE5", "mfe5", 50), ("p75 MFE5", "mfe5", 75),
            ("p90 MFE5", "mfe5", 90), ("median MAE5", "mae5", 50),
            ("p25 MAE5", "mae5", 25)]
    for lbl, k, q in rows:
        A = [o[k] for o in sig]
        B = [o[k] for o in ctl]
        fa = (sum(A) / len(A)) if q is None else MP.pct(A, q)
        fb = (sum(B) / len(B)) if q is None else MP.pct(B, q)
        print(f"{lbl:<17}{fa:>11.2f}%{fb:>11.2f}%{fa - fb:>+11.2f}%")

    print(f"\nP(TOUCH TARGET within 5 days) -- lift over random is what matters")
    print(f"{'target':<10}{'SIGNAL':>10}{'CONTROL':>10}{'LIFT':>10}")
    print("-" * 40)
    for t in (1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0):
        pa = 100 * sum(1 for o in sig if o["mfe5"] >= t) / len(sig)
        pb = 100 * sum(1 for o in ctl if o["mfe5"] >= t) / len(ctl)
        print(f"  {t:.1f}%{pa:>9.1f}%{pb:>9.1f}%{pa - pb:>+9.1f}")

    edge = MP.pct([o["ret5"] for o in sig], 50) - MP.pct([o["ret5"] for o in ctl], 50)
    mean_edge = (sum(o["ret5"] for o in sig) / len(sig)
                 - sum(o["ret5"] for o in ctl) / len(ctl))

    print("\n" + "=" * 84)
    print(f">>> median 5-day edge over random : {edge:+.3f}%")
    print(f">>> mean   5-day edge over random : {mean_edge:+.3f}%")
    print("=" * 84)
    print("Near zero means the signal selects nothing. No target choice fixes")
    print("that. Stop before Stage 1 rather than after.")
    print()
    print("Also a bug detector: if SIGNAL and CONTROL are near-identical across")
    print("EVERY row above, suspect a filter that is silently excluding")
    print("everything, not a signal that happens to be weak.")


if __name__ == "__main__":
    main()
