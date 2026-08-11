#!/usr/bin/env python3
"""
Write universe.txt -- one symbol per line, for build_earnings.py.

  python build_universe_file.py --max-symbols 400 --out universe.txt

Uses the SAME filter as stage1_data.list_tradable_universe(), so the
symbols you fetch earnings for are exactly the symbols the backtest
will consider. If these two lists drift apart you get silent
fail-closed exclusions that look like "no signal".

A5 REMINDER: this is today's active list. Survivorship bias enters here
and nowhere else. See README_STAGE1.md.
"""
import argparse
import stage1_data as D

ap = argparse.ArgumentParser()
ap.add_argument("--max-symbols", type=int, default=400)
ap.add_argument("--out", default="universe.txt")
ap.add_argument("--years", type=int, default=6)
a = ap.parse_args()

from datetime import date, timedelta

end = date.today() - timedelta(days=1)
start = end - timedelta(days=365*a.years + 300)
syms = D.select_by_liquidity(start, n_top=a.max_symbols)

with open(a.out, "w") as f:
    f.write("\n".join(syms) + "\n")

print(f"\nwrote {a.out}: {len(syms)} symbols, ranked by dollar ADV at "
      f"window start ({start})")
print(f"top 10: {syms[:10]}")
print("\nThese are the MOST LIQUID names passing $10-100 + ADV>2M as of the")
print("START of the backtest window -- not an alphabetical slice, and not")
print("ranked on today's liquidity (which would be forward-looking).")
