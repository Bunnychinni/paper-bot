"""Mechanics test on synthetic bars with FORCED overnight gaps.
Purpose: prove gap exits are separated from clean stops and that the
verdict logic fails closed. The RETURNS ARE MEANINGLESS - random data."""
import random
from datetime import date, timedelta
import stage1_backtest as B, stage1_validate as V

random.seed(11)
syms=[f"S{i}" for i in range(8)]; bars={}
d0=date(2023,1,2)
for s in syms:
    p=40.0; d=d0; rows=[]
    for _ in range(600):
        while d.weekday()>=5: d+=timedelta(days=1)
        gap = -random.uniform(0.02,0.09) if random.random()<0.03 else random.gauss(0,0.004)
        o=p*(1+gap); c=o*(1+random.gauss(0.0003,0.015))
        rows.append(dict(date=d,open=o,high=max(o,c)*1.007,low=min(o,c)*0.993,
                         close=c,volume=3_000_000))
        p=c; d+=timedelta(days=1)
    bars[s]=rows

def sig(h,t):
    out=[]
    for s,b in h.items():
        if len(b)<25: continue
        c=[x["close"] for x in b]; sma=sum(c[-20:])/20
        if c[-2]<sma<=c[-1]: out.append(s)
    return out[:3]

dates=sorted({b["date"] for bs in bars.values() for b in bs})
elig={s:{d:True for d in dates} for s in syms}
acct,curve,skip=B.run(bars,sig,elig,{},{s:set() for s in syms},{s:set() for s in syms},
                      target_pct=3.0,stop_pct=1.5,max_hold=5,
                      in_earnings_fn=lambda *a,**k: False)
r=B.analyse(acct,curve)
V.print_report(r,"MECHANICS TEST (synthetic, forced gaps) - returns meaningless")
v=V.verdict(dict(n=r["n"],win_rate=r["win_rate"]),r,3.0,1.5,0.123)
V.print_verdict(v,3.0,1.5,0.123)
