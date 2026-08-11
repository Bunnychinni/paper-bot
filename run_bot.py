#!/usr/bin/env python3
"""
Orchestrator: scan -> enter (morning) | protect/exit/reconcile (evening).

  python run_bot.py morning --target 2.5 --stop 2.0
  python run_bot.py evening --target 2.5 --stop 2.0 --max-hold 5

Morning: runs the scanner (which itself requires preregistration.md),
takes its ranked candidates, places paper entries.
Evening: attaches OCO protection to any unprotected fill, applies the
time exit, reconciles fills into the logbook with realised slippage.
"""
import argparse, subprocess, sys, re

def scan_candidates(target, stop):
    """Run scanner.py, parse its printed candidate lines."""
    r = subprocess.run([sys.executable, "scanner.py",
                       "--target", str(target), "--stop", str(stop)],
                      capture_output=True, text=True)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr); sys.exit("scanner failed")
    syms = re.findall(r"^\s+\d+\.\s+([A-Z]{1,5})\s", r.stdout, re.M)
    return syms

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["morning", "evening"])
    ap.add_argument("--target", type=float, required=True)
    ap.add_argument("--stop", type=float, required=True)
    ap.add_argument("--max-hold", type=int, default=5)
    a = ap.parse_args()

    import executor
    if a.mode == "morning":
        cands = scan_candidates(a.target, a.stop)
        print(f"candidates: {cands}")
        executor.morning_run(cands, a.target, a.stop)
    else:
        executor.evening_run(a.target, a.stop, a.max_hold)

if __name__ == "__main__":
    main()
