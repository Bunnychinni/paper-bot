"""End-to-end dry run with the NETWORK STUBBED and synthetic bars.
Catches runtime errors only. Every number printed is meaningless."""
import random, json
from datetime import date, timedelta
import stage1_data as D

random.seed(42)
NS, ND = 40, 700
SY = [f"S{i:03d}" for i in range(NS)]
EARN = {}

def _bars():
    out={}
    for s in SY:
        p=random.uniform(12,95); rows=[]; d=date(2022,1,3)
        for _ in range(ND):
            while d.weekday()>=5: d+=timedelta(days=1)
            o=p*(1+random.gauss(0,0.004))
            c=o*(1+random.gauss(0.0003,0.016))
            rows.append(dict(date=d,open=o,close=c,high=max(o,c)*1.008,
                             low=min(o,c)*0.992,volume=random.uniform(2.2e6,9e6)))
            p=c; d+=timedelta(days=1)
        out[s]=rows
        # ~quarterly earnings so the blackout has something to bite on
        EARN[s]={rows[i]["date"] for i in range(30,ND,63)}
    return out

D.list_tradable_universe = lambda max_symbols=None: SY[:max_symbols or NS]
_B = _bars()
D.fetch_daily_bars = lambda syms,s,e: {k:[b for b in v if s<=b["date"]<=e]
                                       for k,v in _B.items() if k in syms}

print("=== stage1_data ===")
halted = D.flag_halts(_B); print(f"  flag_halts -> {len(halted)} symbols")
bad = {s: D.detect_unadjusted_splits(b) for s,b in _B.items()}
print(f"  detect_unadjusted_splits -> {sum(1 for v in bad.values() if v)} flagged")
elig, stats = D.build_universe(_B); print(f"  build_universe -> {len(elig)} eligible")
sel = D.select_by_liquidity(date(2022,1,3), n_top=20, probe_days=90)
print(f"  select_by_liquidity -> {len(sel)} symbols")

print("\n=== mfe_profile ===")
import mfe_profile as MP
from signals import signal_reversal
obs = MP.profile(_B, signal_reversal, elig, halted, EARN, bad)
print(f"  profile() -> {len(obs)} signal events")
MP.report(obs)

print("\n=== stage1_backtest + bootstrap ===")
import stage1_backtest as B, stage1_validate as V, bootstrap as BS
acct, curve, skip = B.run(_B, signal_reversal, elig, halted, EARN, bad,
                          target_pct=2.5, stop_pct=1.75, max_hold=5)
r = B.analyse(acct, curve)
V.print_report(r, "DRY RUN (synthetic)")
print(f"  skipped: {skip}")
if acct.trades:
    g = BS.run_gate(acct.trades, 0.123)
    BS.print_gate(g, "-- DRY RUN")
    BS.print_by_year(acct.trades, g["stressed_cost"])
    wk = BS.weekly_blocks(acct.trades)
    gw = BS.run_gate(wk, 0.123, block_by="entry_week")
    print(f"\n  weekly-block LB {gw['lower_bound']:+.4f}% vs "
          f"daily-block LB {g['lower_bound']:+.4f}%")
else:
    print("  NO TRADES - would be a bug in a real run")
