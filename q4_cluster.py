"""Effective sample size once entries are clustered by calendar day."""
import math
def wilson_lo(k,n,z=1.96):
    p=k/n; d=1+z*z/n; c=(p+z*z/(2*n))/d
    return max(0.0,c - z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d)
def min_n(p,bar,z=1.96):
    for n in range(20,60000):
        if wilson_lo(round(p*n),n,z)>bar: return n
    return None

print("DESIGN EFFECT: trades entered on the same day share one market shock.")
print("With m trades per cluster and intra-cluster correlation rho,")
print("effective n = n / (1 + (m-1)*rho).\n")
for m,rho in [(2,0.3),(2,0.5),(3,0.3),(3,0.5),(3,0.7)]:
    de=1+(m-1)*rho
    print(f"  {m} trades/day, rho={rho}: design effect {de:.2f}  ->  "
          f"need {de:.2f}x more trades")

print("\n" + "="*72)
print("REQUIRED **RAW** TRADES at design effect 2.0 (3/day, rho=0.5)")
print("="*72)
bars={"3.0/1.5":0.452,"4.0/1.5":0.375}
print(f"{'obs WR':<9}" + "".join(f"{k:>26}" for k in bars))
for p in (0.45,0.48,0.50,0.55,0.60):
    row=f"{p*100:>5.0f}%   "
    for k,b in bars.items():
        n=min_n(p,b)
        row += f"{(str(n)+' -> '+str(n*2) if n else 'never'):>26}"
    print(row)
print("\nCapacity ceiling: 3y x 3 slots / 2.5d hold = ~907 raw trades total.")
print("35% holdout = ~318 raw.  20% holdout = ~181 raw.")
