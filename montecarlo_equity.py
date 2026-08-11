"""
Monte Carlo on $1,000 starting equity, compounding, in DOLLARS.

This is NOT a backtest. It is a distribution over outcomes given an assumed
edge. It answers: "if my win rate really is X, what does the dollar equity
curve and the worst-case drawdown look like?"

A single backtest path badly understates drawdown. 10,000 paths does not.
"""
import numpy as np

rng = np.random.default_rng(20260805)


def simulate(win_rate, target_pct, stop_pct, cost_pct,
             n_trades, start_equity=1000.0, pos_frac=0.30,
             gap_prob=0.08, gap_mult=2.0, n_paths=10000):
    """
    pos_frac  : fraction of equity per position (3 slots x 0.30 = 90% deployed)
    gap_prob  : P(a losing trade gaps through the stop overnight)
    gap_mult  : how much worse than the stop that loss is
    """
    equity = np.full(n_paths, start_equity)
    peak = equity.copy()
    max_dd = np.zeros(n_paths)
    curves = np.zeros((n_paths, n_trades + 1))
    curves[:, 0] = start_equity

    for t in range(n_trades):
        size = equity * pos_frac
        win = rng.random(n_paths) < win_rate

        ret = np.where(win, target_pct / 100.0, -stop_pct / 100.0)

        # losers can gap through the stop (overnight risk)
        gapped = (~win) & (rng.random(n_paths) < gap_prob)
        ret = np.where(gapped, -(stop_pct * gap_mult) / 100.0, ret)

        pnl = size * ret - size * (cost_pct / 100.0)
        equity = equity + pnl
        equity = np.maximum(equity, 0.0)

        peak = np.maximum(peak, equity)
        dd = np.where(peak > 0, (peak - equity) / peak, 0.0)
        max_dd = np.maximum(max_dd, dd)
        curves[:, t + 1] = equity

    return equity, max_dd, curves


def report(label, **kw):
    eq, dd, curves = simulate(**kw)
    med = np.median(eq)
    print(f"\n{label}")
    print(f"  final equity   p5 ${np.percentile(eq,5):>8.2f}   "
          f"p25 ${np.percentile(eq,25):>8.2f}   "
          f"MED ${med:>8.2f}   "
          f"p75 ${np.percentile(eq,75):>8.2f}   "
          f"p95 ${np.percentile(eq,95):>8.2f}")
    print(f"  net $ (median) {med - 1000:>+9.2f}     "
          f"P(end below $1000) = {100*np.mean(eq < 1000):>4.1f}%     "
          f"P(end below $800) = {100*np.mean(eq < 800):>4.1f}%")
    print(f"  max drawdown   MED {100*np.median(dd):>5.1f}%   "
          f"p90 {100*np.percentile(dd,90):>5.1f}%   "
          f"p99 {100*np.percentile(dd,99):>5.1f}%   "
          f"WORST {100*np.max(dd):>5.1f}%")
    return curves


if __name__ == "__main__":
    N_TRADES = 150   # ~1 year: 3 slots, ~3-day holds, signals not every day

    print("=" * 84)
    print("SWING  target 3.0% / stop 1.5% / cost 0.10% / 150 trades / $1,000 start")
    print("break-even win rate = 35.6%   (before gap risk)")
    print("=" * 84)
    for wr in [0.35, 0.40, 0.45, 0.50, 0.55]:
        report(f"win rate {wr:.0%}", win_rate=wr, target_pct=3.0, stop_pct=1.5,
               cost_pct=0.10, n_trades=N_TRADES)

    print()
    print("=" * 84)
    print("INTRADAY  target 0.5% / stop 0.3% / cost 0.10% / 500 trades / $1,000 start")
    print("break-even win rate = 50.0%   (no gap risk -- flat overnight)")
    print("=" * 84)
    for wr in [0.50, 0.55, 0.60]:
        report(f"win rate {wr:.0%}", win_rate=wr, target_pct=0.5, stop_pct=0.3,
               cost_pct=0.10, n_trades=500, gap_prob=0.0)

    print()
    print("=" * 84)
    print("EQUIVALENCE CHECK")
    print("An intraday system needs a 60% win rate at 0.5/0.3 to roughly match")
    print("a swing system at 45% win rate on 3.0/1.5. Ask yourself which of those")
    print("two claims you can actually defend out of sample.")
    print("=" * 84)

    # risk-per-trade reality check
    print()
    print("RISK PER TRADE at $300 position:")
    for stop in [1.0, 1.5, 2.0, 3.0]:
        loss = 300 * stop / 100
        print(f"  {stop:.1f}% stop -> ${loss:.2f} loss = {loss/1000*100:.2f}% of a $1,000 account")
    print("  3 slots all stopped out at 1.5% simultaneously = "
          f"${3*300*0.015:.2f} = {3*300*0.015/10:.2f}% of account")
