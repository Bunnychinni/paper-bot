"""
Block bootstrap by entry date, and MEASURED design effect.

Replaces the Wilson interval. Wilson assumes independent trials; trades
entered on the same day share one market shock and are not independent.
The block bootstrap resamples ENTRY DATES with replacement, carrying all
trades from a date together, so the correlation structure is preserved
without needing to estimate rho at all.

rho and the design effect are still computed, but as DIAGNOSTICS -- so
you can see how bad the clustering is and sanity-check the bootstrap
width. They are not used to correct anything.
"""
from __future__ import annotations
import random
from collections import defaultdict


# ------------------------------------------------------- measured rho
def intraclass_correlation(trades, key="ret_pct", by="entry_date"):
    """
    One-way random-effects ICC via the ANOVA estimator.
    rho = (MSB - MSW) / (MSB + (m0 - 1) * MSW)

    Returns (rho, mean_cluster_size, design_effect, n_clusters).
    rho is clamped at 0 below; a negative estimate means no detectable
    clustering, which for this signal would be surprising and worth
    investigating rather than accepting.
    """
    g = defaultdict(list)
    for t in trades:
        g[t[by]].append(t[key])
    g = {k: v for k, v in g.items() if v}
    k = len(g)
    n = sum(len(v) for v in g.values())
    if k < 2 or n <= k:
        return 0.0, (n / k if k else 0), 1.0, k

    grand = sum(sum(v) for v in g.values()) / n
    ssb = sum(len(v) * (sum(v)/len(v) - grand) ** 2 for v in g.values())
    ssw = sum(sum((x - sum(v)/len(v)) ** 2 for x in v) for v in g.values())
    msb = ssb / (k - 1)
    msw = ssw / (n - k) if n > k else 0.0

    sizes = [len(v) for v in g.values()]
    m0 = (n - sum(s*s for s in sizes)/n) / (k - 1)
    denom = msb + (m0 - 1) * msw
    rho = 0.0 if denom == 0 else max(0.0, (msb - msw) / denom)

    mbar = n / k
    return rho, mbar, 1 + (mbar - 1) * rho, k


# ------------------------------------------------------- the bootstrap
def block_bootstrap(trades, stat_fn, n_boot=20000, by="entry_date",
                    alpha=0.05, one_sided=True, seed=20260805):
    """
    Resample whole entry-date blocks with replacement.
    one_sided=True returns (lower_bound, None) at level alpha -- correct
    here because the hypothesis is directional (edge > 0) and we never
    care about the upper tail.
    """
    rng = random.Random(seed)
    blocks = defaultdict(list)
    for t in trades:
        blocks[t[by]].append(t)
    keys = list(blocks)
    if len(keys) < 5:
        return None, None, []

    point = stat_fn(trades)
    draws = []
    for _ in range(n_boot):
        samp = []
        for _ in range(len(keys)):
            samp.extend(blocks[keys[rng.randrange(len(keys))]])
        if samp:
            draws.append(stat_fn(samp))
    draws.sort()

    def q(p):
        i = min(len(draws) - 1, max(0, int(p * len(draws))))
        return draws[i]

    if one_sided:
        return point, q(alpha), draws
    return point, (q(alpha/2), q(1 - alpha/2)), draws


def weekly_blocks(trades):
    """Conservative variant: block by ISO week, not day.

    Use this if the daily ICC comes back high AND signals persist across
    consecutive sessions. Blocking by day still assumes adjacent days are
    independent, which for a market-wide reversal signal during a
    multi-day selloff is optimistic.
    """
    out = []
    for t in trades:
        d = t["entry_date"]
        y, w, _ = d.isocalendar()
        out.append({**t, "entry_week": f"{y}-W{w:02d}"})
    return out


# ------------------------------------------------------------ the gate
def expectancy_net(trades, stressed_cost_pct):
    """Mean per-trade return in %, net of the stressed round-trip cost."""
    if not trades:
        return 0.0
    return sum(t["ret_pct"] for t in trades) / len(trades) - stressed_cost_pct


def exit_breakdown(trades):
    """% and mean P&L per exit bucket, reported separately. Never blended."""
    g = defaultdict(list)
    for t in trades:
        g[t["reason"]].append(t)
    n = len(trades) or 1
    out = {}
    for r in ("target", "target_gap", "stop_clean", "stop_gap", "time"):
        v = g.get(r, [])
        out[r] = dict(
            n=len(v), pct=100*len(v)/n,
            mean_ret=(sum(x["ret_pct"] for x in v)/len(v)) if v else 0.0,
            mean_usd=(sum(x["pnl"] for x in v)/len(v)) if v else 0.0,
            contribution=sum(x["ret_pct"] for x in v)/n)
    return out


def run_gate(trades, base_cost_pct, stress_mult=3.0, exec_share=0.90,
             alpha=0.05, block_by="entry_date"):
    cs = base_cost_pct*(1-exec_share) + base_cost_pct*exec_share*stress_mult
    rho, mbar, de, k = intraclass_correlation(trades)
    pt, lo, draws = block_bootstrap(
        trades, lambda ts: expectancy_net(ts, cs), by=block_by, alpha=alpha)
    return dict(n=len(trades), n_blocks=k, rho=rho, mean_cluster=mbar,
                design_effect=de, stressed_cost=cs,
                expectancy=pt, lower_bound=lo,
                passes=(lo is not None and lo > 0),
                exits=exit_breakdown(trades))


def print_gate(g, label=""):
    print("\n" + "="*78)
    print(f"EXPECTANCY GATE {label}")
    print("="*78)
    print(f"  trades {g['n']}  across {g['n_blocks']} entry dates "
          f"(mean {g['mean_cluster']:.2f}/date)")
    print(f"  MEASURED intra-date ICC rho = {g['rho']:.3f}  "
          f"-> design effect {g['design_effect']:.2f}")
    print(f"  stressed round-trip cost {g['stressed_cost']:.3f}%")
    print()
    print("  EXIT BREAKDOWN (separate buckets, never blended):")
    print(f"    {'bucket':<12}{'n':>6}{'% of all':>10}{'mean ret':>11}"
          f"{'mean $':>10}{'contrib':>10}")
    for r, v in g["exits"].items():
        print(f"    {r:<12}{v['n']:>6}{v['pct']:>9.1f}%{v['mean_ret']:>10.2f}%"
              f"{v['mean_usd']:>9.2f}{v['contribution']:>9.3f}%")
    print()
    print(f"  expectancy net of stressed cost : {g['expectancy']:+.4f}% / trade")
    print(f"  one-sided 95% block-bootstrap LB: {g['lower_bound']:+.4f}% / trade"
          if g["lower_bound"] is not None else "  bootstrap: too few blocks")
    print()
    print(f"  >>> {'PASS' if g['passes'] else 'FAIL'} "
          f"(lower bound must exceed 0)")
    print("="*78)


# ------------------------------------------------- regime decomposition
def by_year(trades, stressed_cost_pct):
    """
    Expectancy per calendar year. Essential at a 6-year window: if the
    whole edge lives in 2020-21, you have not found an edge, you have
    found a regime that ended.
    """
    g = defaultdict(list)
    for t in trades:
        g[t["entry_date"].year].append(t)
    out = {}
    for y in sorted(g):
        v = g[y]
        rets = [x["ret_pct"] for x in v]
        mu = sum(rets)/len(rets) - stressed_cost_pct
        sd = (sum((r - sum(rets)/len(rets))**2 for r in rets)/max(1, len(rets)-1))**0.5
        out[y] = dict(n=len(v), expectancy=mu, sd=sd,
                      total_usd=sum(x["pnl"] for x in v))
    return out


def print_by_year(trades, stressed_cost_pct):
    d = by_year(trades, stressed_cost_pct)
    if not d:
        print("  no trades"); return
    print(f"\n  {'year':<7}{'n':>6}{'expectancy':>13}{'SD':>9}{'total $':>11}")
    print("  " + "-"*46)
    tot = sum(v["n"] for v in d.values())
    for y, v in d.items():
        print(f"  {y:<7}{v['n']:>6}{v['expectancy']:>12.3f}%{v['sd']:>8.2f}%"
              f"{v['total_usd']:>10.2f}")
    pos = [y for y, v in d.items() if v["expectancy"] > 0]
    print(f"\n  positive in {len(pos)}/{len(d)} years: {pos}")
    best = max(d, key=lambda y: d[y]["total_usd"])
    share = d[best]["total_usd"] / sum(abs(v["total_usd"]) for v in d.values()) \
            if sum(abs(v["total_usd"]) for v in d.values()) else 0
    print(f"  best year {best} contributes {100*share:.0f}% of gross P&L")
    print(f"  >>> if that share is above ~50%, the edge is one regime, not an edge.")
