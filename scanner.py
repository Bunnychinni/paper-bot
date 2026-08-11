#!/usr/bin/env python3
"""
STAGE 2 / scanner. Runs pre-open, ranks candidates, LOGS THEM. No orders.

  python scanner.py --prereg preregistration.md --universe universe.txt

REFUSES TO RUN without a pre-registration file. That is deliberate. The
whole reason Stage 2 exists is to accumulate uncontaminated forward data,
and data collected against a rule you are still editing is not that.
The file's SHA-256 is stored on every run; if you change the rule, the
hash changes, and analysis will tell you your sample restarted.

There is no order path in this file. grep it.
"""
import argparse, hashlib, os, sys
from datetime import date, timedelta

import stage1_data as D
import context as CTX
import logbook as LB
from signals import SIGNALS

BENCH = ["SPY", "QQQ", "VIXY"]


def prereg_hash(path):
    if not os.path.exists(path):
        sys.exit(
            f"\nNo {path}.\n\n"
            "Stage 2 will not collect data against an unregistered rule.\n"
            "Create it with, at minimum:\n"
            "  1. the mechanism (who is losing money to you, and why)\n"
            "  2. the exact entry rule\n"
            "  3. target, stop, max hold -- NOT read off profile_output.txt\n"
            "  4. universe and why\n"
            "  5. the pass/fail gate\n"
            "  6. what result would make you abandon it\n\n"
            "See README_RESULT.md section 5.\n")
    b = open(path, "rb").read()
    return hashlib.sha256(b).hexdigest()[:16]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prereg", default="preregistration.md")
    ap.add_argument("--universe", default="universe.txt")
    ap.add_argument("--earnings", default="earnings.csv")
    ap.add_argument("--signal", default="reversal", choices=list(SIGNALS))
    ap.add_argument("--target", type=float, required=True)
    ap.add_argument("--stop", type=float, required=True)
    ap.add_argument("--equity", type=float, default=1000.0)
    ap.add_argument("--slots", type=int, default=3)
    ap.add_argument("--pos-frac", type=float, default=0.30)
    ap.add_argument("--db", default="logbook.db")
    a = ap.parse_args()

    h = prereg_hash(a.prereg)
    print(f"pre-registration {a.prereg} sha256:{h}")

    earnings = D.load_earnings(a.earnings)
    if earnings is None:
        sys.exit(f"No {a.earnings}. Fails closed. Run build_earnings.py.")
    syms = [l.strip() for l in open(a.universe) if l.strip()]

    today = date.today()
    start = today - timedelta(days=420)          # ~200 sessions + slack
    print(f"fetching {len(syms)} symbols + benchmarks, {start} .. {today}")
    bars = D.fetch_daily_bars(syms + BENCH, start, today)
    bench = {s: bars.get(s, []) for s in BENCH}

    ctx = CTX.build_context(bench, today)
    print(f"\ncontext: {ctx['macro_reason']}")
    for n in ctx["notes"]:
        print(f"  {n}")
    print(f"  size multiplier: {ctx['size_multiplier']}")

    con = LB.connect(a.db)
    run_id = LB.start_run(con, h, a.prereg, ctx, len(syms), len(bars))

    if ctx["size_multiplier"] == 0.0:
        print("\nSKIP DAY. No candidates emitted. Logged.")
        LB.finish_run(con, run_id, 0)
        LB.print_progress(con)
        return

    halted = D.flag_halts(bars)
    bad = {s: D.detect_unadjusted_splits(b) for s, b in bars.items()}
    elig, _ = D.build_universe(bars)

    hist = {s: bars[s] for s in bars if s not in BENCH}
    picks = SIGNALS[a.signal](hist, today)

    kept, rank = [], 0
    for sym in picks:
        if sym not in elig or not any(elig[sym].values()):
            continue
        if today in halted.get(sym, set()) or today in bad.get(sym, set()):
            continue
        if D.in_earnings_blackout(sym, today, earnings):
            print(f"  {sym}: skipped, earnings blackout")
            continue
        b = bars.get(sym)
        if not b:
            continue
        rank += 1
        px = b[-1]["close"]                     # reference; real entry is tomorrow's open
        notional = a.equity * a.pos_frac * ctx["size_multiplier"]
        c = [x["close"] for x in b[-21:-1]]
        m = sum(c) / len(c)
        sd = (sum((x - m) ** 2 for x in c) / (len(c) - 1)) ** 0.5
        z = (px - m) / sd if sd else 0.0
        sma200 = sum(x["close"] for x in b[-200:]) / 200
        kept.append(dict(
            signal_date=str(today), symbol=sym, rank=rank, ref_close=px,
            intended_entry=px, target=px * (1 + a.target / 100),
            stop=px * (1 - a.stop / 100), shares=notional / px,
            notional=notional, size_multiplier=ctx["size_multiplier"],
            reason=f"{a.signal}: z={z:.2f} vs 20d, {100*(px/sma200-1):+.1f}% vs 200d SMA",
            features=dict(z20=z, pct_vs_sma200=100 * (px / sma200 - 1),
                          vol_pct=ctx.get("spy_vol_percentile"))))
        if rank >= a.slots:
            break

    print(f"\n{'='*72}\nCANDIDATES for next open ({len(kept)})\n{'='*72}")
    if not kept:
        print("  none today. Logged -- days with no signal are part of the sample.")
    for s in kept:
        print(f"  {s['rank']}. {s['symbol']:<6} ref ${s['ref_close']:.2f}  "
              f"target ${s['target']:.2f} (+{a.target}%)  stop ${s['stop']:.2f} "
              f"(-{a.stop}%)")
        print(f"     {s['shares']:.4f} sh = ${s['notional']:.2f}   {s['reason']}")
        LB.log_signal(con, run_id, s)

    LB.finish_run(con, run_id, len(kept))
    LB.print_progress(con)
    print("\nNO ORDERS PLACED. This is a logging instrument.")


if __name__ == "__main__":
    main()
