"""
STAGE 1 / validation and verdict.

The verdict is deliberately hard to pass. It asks three questions:

  Q1 Does the observed win rate beat break-even at ASSUMED slippage?
  Q2 Does the LOWER 95% bound of the observed win rate still beat
     break-even at 3x assumed slippage?
  Q3 Is the holdout consistent with the walk-forward, or did the edge
     only exist in the data you looked at?

Q2 is the one that matters. A point estimate above break-even means
nothing at n=150 trades -- the 95% CI on a 45% win rate over 150 trades
is roughly +/- 8 points. If the lower bound does not clear a stressed
break-even, you do not have a demonstrated edge, you have noise that
happened to point the right way.
"""
from __future__ import annotations
import math
from datetime import timedelta


def wilson_ci(k, n, z=1.96):
    """Wilson score interval. Correct at small n, unlike normal approx."""
    if n == 0: return (0.0, 0.0)
    p = k/n
    d = 1 + z*z/n
    c = (p + z*z/(2*n))/d
    h = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n))/d
    return (max(0.0, c-h), min(1.0, c+h))


def breakeven(target_pct, stop_pct, cost_pct):
    return (stop_pct + cost_pct)/(target_pct + stop_pct)


def effective_stop_pct(res, nominal_stop_pct):
    """
    Gap-adjusted stop. The break-even formula assumes losers lose exactly
    `stop`. They don't. Use the ACTUAL average loss across all losing exits,
    which already contains the gap damage.
    """
    al = res["avg_loss"]
    return abs(al) if al else nominal_stop_pct


def split_windows(all_dates, n_folds=5, holdout_frac=0.35):
    """Sequential walk-forward folds + a final untouched holdout."""
    n = len(all_dates)
    cut = int(n*(1-holdout_frac))
    train_dates, hold_dates = all_dates[:cut], all_dates[cut:]
    size = len(train_dates)//n_folds
    folds = [(train_dates[i*size], train_dates[min((i+1)*size, size*n_folds)-1])
             for i in range(n_folds)]
    return folds, (hold_dates[0], hold_dates[-1])


def verdict(res_wf, res_hold, target_pct, stop_pct, cost_pct, stress_mult=3.0,
            exec_cost_share=0.90):
    """
    exec_cost_share: fraction of round-trip cost that is spread+slippage
    (the part that scales when you are wrong about slippage). Regulatory
    fees do not scale. From the cost model this is ~90%.
    """
    out = {}
    n, wr = res_hold["n"], res_hold["win_rate"]/100
    k = round(wr*n)

    eff_stop = effective_stop_pct(res_hold, stop_pct)
    cost_stressed = cost_pct*(1 - exec_cost_share) + cost_pct*exec_cost_share*stress_mult

    be_nominal = breakeven(target_pct, stop_pct, cost_pct)*100
    be_gapadj = breakeven(target_pct, eff_stop, cost_pct)*100
    be_stress = breakeven(target_pct, eff_stop, cost_stressed)*100

    lo, hi = wilson_ci(k, n)
    out.update(n=n, win_rate=wr*100, ci_lo=lo*100, ci_hi=hi*100,
               eff_stop=eff_stop, be_nominal=be_nominal, be_gapadj=be_gapadj,
               be_stress=be_stress, cost_stressed=cost_stressed)

    out["q1"] = wr*100 > be_gapadj
    out["q2"] = lo*100 > be_stress
    out["q3"] = (res_wf["win_rate"] - res_hold["win_rate"]) < 7.0 and res_hold["n"] >= 30
    out["pass"] = out["q1"] and out["q2"] and out["q3"]
    out["min_n_for_power"] = min_trades_needed(be_stress/100, wr)
    return out


def min_trades_needed(p_be, p_obs, z=1.96):
    """How many trades before the CI could possibly clear the stressed bar."""
    if p_obs <= p_be: return None
    d = p_obs - p_be
    return int(math.ceil(z*z*p_obs*(1-p_obs)/(d*d)))


def print_report(res, label):
    g, fg = res["gap"], res["favourable_gap"]
    print(f"\n--- {label} ---")
    print(f"  trades {res['n']:>4}   equity ${res['start']:.2f} -> ${res['end']:.2f} "
          f"({res['ret_pct']:+.2f}%)   maxDD {res['max_dd']:.1f}%")
    print(f"  win rate {res['win_rate']:.1f}%   profit factor {res['profit_factor']:.2f}   "
          f"avg hold {res['avg_hold']:.1f}d   fees ${res['total_fees']:.2f}")
    print(f"  avg win {res['avg_win']:+.2f}%   avg loss {res['avg_loss']:+.2f}%")
    print(f"  exits: {res['exits']}")
    print(f"  GAP-THROUGH-STOP (reported separately, not blended):")
    print(f"     count {g['n']}  = {g['pct_all']:.1f}% of trades, {g['pct_losers']:.1f}% of losers")
    print(f"     avg realized loss {g['avg_loss_pct']:+.2f}%   "
          f"(clean stops avg {g['clean_avg_loss_pct']:+.2f}%)")
    print(f"     WORST single loss {g['worst_loss_pct']:+.2f}%  = ${g['worst_loss_usd']:+.2f}")
    print(f"     gap tax: ${abs(g['gap_tax_usd']):.2f} of EXTRA loss vs stops holding "
          f"exactly ({100*abs(g['gap_tax_usd'])/res['start']:.1f}% of starting equity)")
    print(f"  favourable target gaps (NOT netted): {fg['n']}, avg {fg['avg_gain_pct']:+.2f}%")


def print_verdict(v, target_pct, stop_pct, cost_pct):
    print("\n" + "="*76)
    print("STAGE 1 VERDICT")
    print("="*76)
    print(f"  setup {target_pct}% / {stop_pct}%   assumed round-trip cost {cost_pct:.3f}%")
    print(f"  holdout trades           {v['n']}")
    print(f"  observed win rate        {v['win_rate']:.1f}%  "
          f"[95% CI {v['ci_lo']:.1f}% - {v['ci_hi']:.1f}%]")
    print(f"  gap-adjusted eff. stop   {v['eff_stop']:.2f}%  (vs nominal {stop_pct}%)")
    print()
    print(f"  break-even, nominal      {v['be_nominal']:.1f}%")
    print(f"  break-even, gap-adjusted {v['be_gapadj']:.1f}%   <- the honest bar")
    print(f"  break-even, 3x slippage  {v['be_stress']:.1f}%   "
          f"(cost {v['cost_stressed']:.3f}%)")
    print()
    print(f"  Q1 point estimate beats gap-adjusted break-even   {'PASS' if v['q1'] else 'FAIL'}")
    print(f"  Q2 CI LOWER BOUND beats 3x-slippage break-even    {'PASS' if v['q2'] else 'FAIL'}")
    print(f"  Q3 holdout consistent with walk-forward           {'PASS' if v['q3'] else 'FAIL'}")
    print()
    if v["pass"]:
        print("  >>> CLEARS. Margin is wide enough to survive being wrong about slippage.")
    else:
        print("  >>> DOES NOT CLEAR. Per your instruction: STOP. Do not tune.")
        if v["min_n_for_power"]:
            print(f"      (would need ~{v['min_n_for_power']} holdout trades for the CI to "
                  f"clear, at the currently observed win rate)")
        else:
            print("      (the point estimate itself is below the stressed bar -- more data "
                  "will not fix this)")
    print("="*76)
