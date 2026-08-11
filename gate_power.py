"""Which gate, and what sample size does it need?"""
import math

print("="*84)
print("WHY THE WIN-RATE GATE IS WRONG A PRIORI (not conditionally on exit mix)")
print("="*84)
print("""
p = (S + C)/(T + S) is derived from a two-point outcome distribution:
every trade returns exactly +T or exactly -S. Three things already known
to be true break that derivation:

  stop_gap  -> losses exceed S, by a variable amount
  time      -> exits at an arbitrary intermediate P&L, obeying no formula
  target_gap-> gains exceed T

Win rate is a sufficient statistic ONLY for a binary outcome. Once the
outcome is continuous, two strategies with identical win rates can have
opposite expectancy. The exit distribution tells us HOW wrong the gate
is; it was already the wrong gate before we measured anything.

CORRECT GATE: expectancy per trade, net of stressed cost, one-sided 95%
block-bootstrap lower bound > 0.

One-sided is right, not a fudge: the hypothesis is directional (edge > 0),
we never care about the upper tail. z = 1.645, not 1.96.
""")

print("="*84)
print("SAMPLE SIZE FOR THE EXPECTANCY GATE")
print("   n = (z * sigma * sqrt(DesignEffect) / mu)^2")
print("="*84)
SIG = 2.5   # per-trade return SD, %. UNKNOWN until profiler runs. Sensitivity below.
def need(mu, de, z=1.645, sigma=SIG):
    return math.ceil((z*sigma*math.sqrt(de)/mu)**2)

print(f"\nassuming per-trade SD = {SIG}% (sensitivity table follows)\n")
print(f"{'net expectancy':<16}" + "".join(f"{'DE='+str(d):>12}" for d in (1.0,2.0,2.6,3.0,4.0)))
print("-"*76)
for mu in (0.15,0.20,0.30,0.40,0.50,0.75,1.00):
    row=f"  {mu:>5.2f}%/trade   "
    for de in (1.0,2.0,2.6,3.0,4.0):
        row+=f"{need(mu,de):>12,}"
    print(row)

print("\nCAPACITY: ~907 raw trades over 3y. 35% holdout = ~318 raw.")
print("Cells above ~318 are UNREACHABLE with 3 years of data.\n")

print("="*84)
print("SENSITIVITY TO SD (the number we do not yet know), at DE=3.0")
print("="*84)
print(f"{'sigma':<10}" + "".join(f"{'mu='+format(m,'.2f')+'%':>12}" for m in (0.2,0.3,0.5,0.75)))
for s in (1.5,2.0,2.5,3.0,3.5):
    row=f"  {s:.1f}%    "
    for m in (0.2,0.3,0.5,0.75):
        row+=f"{need(m,3.0,sigma=s):>12,}"
    print(row)

print()
print("="*84)
print("READ-OFF: minimum detectable expectancy at capacity (318 raw trades)")
print("="*84)
for de in (2.0,2.6,3.0,4.0):
    for s in (2.0,2.5,3.0):
        mu = 1.645*s*math.sqrt(de)/math.sqrt(318)
        print(f"  DE={de:<4} sigma={s:.1f}%  ->  need expectancy >= {mu:.3f}%/trade "
              f"(= ${3*mu:.2f} on a $300 position)")
    print()
