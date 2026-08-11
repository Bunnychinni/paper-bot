"""Verify ICC recovery + bootstrap width vs clustering. Synthetic, by design."""
import random, math
from datetime import date, timedelta
import bootstrap as BS

def make(n_dates, per_date, rho_true, mu=0.4, sd=2.5, seed=3):
    r=random.Random(seed); out=[]; d=date(2024,1,1)
    shared_sd = sd*math.sqrt(rho_true); idio_sd = sd*math.sqrt(1-rho_true)
    for _ in range(n_dates):
        shock=r.gauss(0,shared_sd)
        for _ in range(per_date):
            out.append(dict(entry_date=d, ret_pct=mu+shock+r.gauss(0,idio_sd),
                            pnl=0.0, reason="time"))
        d+=timedelta(days=1)
    return out

print(f"{'rho_true':>9}{'rho_meas':>10}{'DE_meas':>9}{'boot LB':>10}{'naive LB':>10}{'width x':>9}")
print("-"*57)
for rt in (0.0,0.3,0.5,0.7,0.9):
    t=make(106,3,rt)
    rho,mbar,de,k=BS.intraclass_correlation(t)
    pt,lo,_=BS.block_bootstrap(t, lambda ts: BS.expectancy_net(ts,0.0), n_boot=4000)
    rs=[x["ret_pct"] for x in t]; m=sum(rs)/len(rs)
    sd=(sum((x-m)**2 for x in rs)/(len(rs)-1))**0.5
    naive=m-1.645*sd/len(rs)**0.5
    print(f"{rt:>9.2f}{rho:>10.3f}{de:>9.2f}{lo:>9.3f}%{naive:>9.3f}%"
          f"{(m-lo)/(m-naive):>8.2f}x")
print("\nICC recovers rho; bootstrap widens with clustering while the naive")
print("interval does not. At rho=0.9 the naive CI is ~2x too narrow.")
