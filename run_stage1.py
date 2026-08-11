#!/usr/bin/env python3
"""
STAGE 1 runner -- Candidate #1 (short-term reversal), expectancy gate.

ORDER OF OPERATIONS IS ENFORCED:
  1. build_earnings.py     -> earnings.csv
  2. mfe_profile.py        -> profile_obs.json, and YOUR chosen target/stop
  3. run_stage1.py --target X --stop Y

There is no default target or stop. The script refuses to run without
them, because a default is a recommendation and I am not making one
until the profiler reports where the move actually goes.

  python run_stage1.py --target 2.5 --stop 1.75 --earnings earnings.csv
"""
import argparse, os, sys
from datetime import date, timedelta

import stage1_data as D
import stage1_backtest as B
import stage1_validate as V
import bootstrap as BS
from signals import signal_reversal

HOLDOUT_FRAC = 0.35     # per your call; ~318 raw trades at capacity


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=float, required=True,
                    help="REQUIRED. No default. Read it off mfe_profile.py.")
    ap.add_argument("--stop", type=float, required=True,
                    help="REQUIRED. No default. Read it off the MAE table.")
    ap.add_argument("--max-hold", type=int, default=5)
    ap.add_argument("--years", type=int, default=6)
    ap.add_argument("--universe", default="universe.txt")
    ap.add_argument("--earnings", default="earnings.csv")
    ap.add_argument("--cost-pct", type=float, default=0.123)
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--block", default="entry_date",
                    choices=["entry_date", "entry_week"],
                    help="entry_week is the conservative variant; use it if "
                         "the measured ICC is high and signals persist across "
                         "consecutive sessions.")
    a = ap.parse_args()

    if not os.path.exists("profile_obs.json"):
        sys.exit("Run mfe_profile.py first. Choosing a target before seeing "
                 "the MFE distribution is how the design gets fitted to the gate.")

    earnings = D.load_earnings(a.earnings)
    if earnings is None:
        sys.exit(f"No {a.earnings}. Run build_earnings.py. Fails closed by design.")

    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=365*a.years + 300)
    print(f"STAGE 1  target {a.target}%  stop {a.stop}%  hold<={a.max_hold}d  "
          f"cost {a.cost_pct}%  holdout {HOLDOUT_FRAC:.0%}\n")

    if not os.path.exists(a.universe):
        sys.exit(f"No {a.universe}. Run build_universe_file.py first.\n"
                 "Refusing to fall back to list_tradable_universe(), which\n"
                 "sorts alphabetically and would silently give you an A-C slice.")
    syms = [l.strip() for l in open(a.universe) if l.strip()]
    print(f"universe: {len(syms)} symbols from {a.universe}")
    bars = D.fetch_daily_bars(syms, start, end)
    halted = D.flag_halts(bars)
    bad = {s: D.detect_unadjusted_splits(b) for s, b in bars.items()}
    eligible, _ = D.build_universe(bars)
    print(f"{len(eligible)} symbols pass filters\n")

    all_dates = sorted({b["date"] for bs in bars.values() for b in bs})
    folds, hold = V.split_windows(all_dates, a.folds, HOLDOUT_FRAC)

    def sl(lo, hi):
        return {s: [b for b in bs if lo <= b["date"] <= hi]
                for s, bs in bars.items()}

    def go(lo, hi):
        acct, curve, skip = B.run(sl(lo, hi), signal_reversal, eligible, halted,
                                  earnings, bad, target_pct=a.target,
                                  stop_pct=a.stop, max_hold=a.max_hold)
        return acct, curve, B.analyse(acct, curve), skip

    wf_trades = []
    for i, (lo, hi) in enumerate(folds, 1):
        acct, curve, r, _ = go(lo, hi)
        V.print_report(r, f"WF fold {i}  {lo} .. {hi}")
        wf_trades += acct.trades

    acct, curve, hr, skip = go(*hold)
    V.print_report(hr, f"HOLDOUT  {hold[0]} .. {hold[1]}")
    print(f"\n  entries skipped: {skip}")

    print("\n  dollar equity curve (holdout, month ends):")
    seen = set()
    for d, e in curve:
        if (d.year, d.month) not in seen:
            seen.add((d.year, d.month)); print(f"    {d}  ${e:>8.2f}")

    trades = acct.trades
    if a.block == "entry_week":
        trades = BS.weekly_blocks(trades)

    g = BS.run_gate(trades, a.cost_pct, block_by=a.block)
    BS.print_gate(g, f"-- HOLDOUT, blocked by {a.block}")

    print("\n  REGIME DECOMPOSITION (walk-forward + holdout, all trades):")
    BS.print_by_year(wf_trades + acct.trades, g["stressed_cost"])

    # diagnostic: same gate on walk-forward, for consistency only
    wf = BS.weekly_blocks(wf_trades) if a.block == "entry_week" else wf_trades
    gw = BS.run_gate(wf, a.cost_pct, block_by=a.block)
    print(f"\n  walk-forward expectancy {gw['expectancy']:+.4f}%/trade "
          f"(LB {gw['lower_bound']:+.4f}%)  vs holdout {g['expectancy']:+.4f}%")
    print(f"  measured ICC: WF {gw['rho']:.3f} / holdout {g['rho']:.3f}")

    print("\n  SURVIVORSHIP HAIRCUT -- apply before believing the result:")
    print("  reported expectancy is an OPTIMISTIC bound. For a dip-buying")
    print("  signal, subtract roughly 0.10-0.20%/trade. If the lower bound")
    print("  does not clear that margin above zero, treat it as a FAIL.")
    lb = g["lower_bound"]
    if lb is not None:
        print(f"  lower bound {lb:+.4f}%  ->  haircut 0.15%  ->  {lb-0.15:+.4f}%  "
              f"{'still clears' if lb-0.15 > 0 else 'DOES NOT CLEAR'}")

    sys.exit(0 if g["passes"] else 1)


if __name__ == "__main__":
    main()
