"""
Correction 1: break-even win rate using PER-PRICE actual cost,
split by fill style (aggressive = take liquidity, passive = post + wait).
"""
import math

SEC_RATE, TAF_RATE, TAF_CAP, CAT_RATE = 20.60/1_000_000, 0.000195, 9.79, 0.000050
def ceil_penny(x): return math.ceil(x*100 - 1e-9)/100

# price -> (quoted spread bps, aggressive slip bps/side, passive adverse bps/side)
PRICE_TIERS = {
    10.0:  (10.0, 3.0, 2.0),
    25.0:  ( 6.0, 2.5, 2.0),
    50.0:  ( 4.0, 2.0, 2.0),
    100.0: ( 3.0, 2.0, 2.0),
}

def rt_cost_pct(notional, price, aggressive=True, slip_mult=1.0):
    spread_bps, agg_slip, pas_slip = PRICE_TIERS[price]
    shares = notional/price
    reg = (ceil_penny(SEC_RATE*notional)
           + ceil_penny(min(TAF_RATE*shares, TAF_CAP))
           + ceil_penny(CAT_RATE*shares)*2)
    if aggressive:
        exec_bps = spread_bps + 2*agg_slip*slip_mult      # cross both ways
    else:
        exec_bps = 2*pas_slip*slip_mult                   # no crossing
    exec_cost = notional * exec_bps/10_000
    return (reg + exec_cost)/notional*100

def breakeven(t, s, c): return (s + c)/(t + s)

N = 300.0
SETUPS = [("Intraday 0.5/0.3", 0.5, 0.3),
          ("Swing 3.0/1.5",    3.0, 1.5),
          ("Swing 3.0/2.0",    3.0, 2.0),
          ("Swing 4.0/1.5",    4.0, 1.5),
          ("Swing 4.0/2.0",    4.0, 2.0)]

print("="*94)
print("PER-PRICE ROUND-TRIP COST, $300 notional  (% of position)")
print("="*94)
print(f"{'Price':>7}{'AGGRESSIVE':>14}{'PASSIVE':>12}{'ratio':>9}")
for p in PRICE_TIERS:
    a, q = rt_cost_pct(N,p,True), rt_cost_pct(N,p,False)
    print(f"${p:>6.0f}{a:>13.3f}%{q:>11.3f}%{a/q:>8.2f}x")

for aggressive in (True, False):
    tag = "AGGRESSIVE FILLS (market / marketable limit)" if aggressive \
          else "PASSIVE FILLS (resting limit, no spread paid)"
    print()
    print("="*94)
    print(f"BREAK-EVEN WIN RATE -- {tag}")
    print("="*94)
    hdr = f"{'Setup':<18}{'frictionless':>13}" + "".join(f"{'$'+format(p,'.0f'):>11}" for p in PRICE_TIERS)
    print(hdr); print("-"*len(hdr))
    for name, t, s in SETUPS:
        base = breakeven(t,s,0.0)*100
        row = f"{name:<18}{base:>12.1f}%"
        for p in PRICE_TIERS:
            c = rt_cost_pct(N,p,aggressive)
            row += f"{breakeven(t,s,c)*100:>10.1f}%"
        print(row)

print()
print("="*94)
print("HOW MUCH THE EDGE DEPENDS ON PASSIVE ENTRY  (pts of win rate saved by going passive)")
print("="*94)
for name, t, s in SETUPS:
    row = f"{name:<18}"
    for p in PRICE_TIERS:
        d = (breakeven(t,s,rt_cost_pct(N,p,True)) - breakeven(t,s,rt_cost_pct(N,p,False)))*100
        row += f"{'$'+format(p,'.0f')+': '+format(d,'+.1f'):>13}"
    print(row)

print()
print("="*94)
print("SLIPPAGE STRESS -- break-even if realized slip is 3x your assumption")
print("(aggressive fills, worst tier $10 and best tier $100)")
print("="*94)
print(f"{'Setup':<18}{'$10 1x':>9}{'$10 3x':>9}{'delta':>8}   {'$100 1x':>9}{'$100 3x':>9}{'delta':>8}")
for name, t, s in SETUPS:
    r = f"{name:<18}"
    for p in (10.0, 100.0):
        b1 = breakeven(t,s,rt_cost_pct(N,p,True,1.0))*100
        b3 = breakeven(t,s,rt_cost_pct(N,p,True,3.0))*100
        r += f"{b1:>8.1f}%{b3:>8.1f}%{b3-b1:>+7.1f}   "
    print(r)
