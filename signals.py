"""
Three candidate entry rules. Pick ONE. Do not test all three and keep the
best -- that is three-way multiple testing and it will hand you a false
positive roughly 1 time in 7 at a 5% threshold.

Each has a stated economic mechanism. If you can't say why someone is on
the other side of your trade losing money on purpose, you don't have an
edge, you have a pattern.
"""

# =====================================================================
# CANDIDATE 1 -- SHORT-TERM REVERSAL IN AN UPTREND
#   "Get paid for supplying liquidity to forced sellers."
#
# MECHANISM (why anyone is on the other side):
#   Some sellers are not selling because they think the stock is
#   overvalued. They are selling because they must: margin calls, fund
#   redemptions, risk-limit breaches, index deletions, stop cascades.
#   These sellers demand immediacy and will pay for it. The price
#   overshoots below fair value and reverts over 1-5 days. You are the
#   counterparty being compensated for warehousing that risk.
#   Documented: Lehmann (1990), Jegadeesh (1990), Nagel (2012) -- Nagel
#   is the important one, it shows short-term reversal returns are
#   essentially the return to liquidity provision and scale directly
#   with VIX.
#
# HORIZON FIT: excellent. The effect lives in the 1-5 day window, which
#   is exactly your holding period. This is the only one of the three
#   where the documented horizon matches your design.
#
# WHAT MAKES IT STOP WORKING:
#   - Low-volatility regimes. Nagel's result cuts both ways: when VIX is
#     low, dealer capital is abundant and the compensation shrinks toward
#     zero. Expect flat-to-negative in calm markets.
#   - Genuine downtrends. This is knife-catching by construction. The
#     200-day filter is not optional, it is the entire risk control, and
#     it still fails in fast crashes (Feb-Mar 2020, Aug 2024).
#   - Crowding. RSI(2) mean reversion is the most heavily publicized
#     retail systematic strategy in existence (Connors/Alvarez, 2008).
#     Public performance degraded materially through the 2010s. The
#     MECHANISM is durable; this specific PARAMETERIZATION is crowded.
#     Prefer the volatility-normalized version below over raw RSI(2).
#
# CORRELATED-ENTRY WARNING: signals fire market-wide on the same down
#   days. Your 3 slots will fill simultaneously with 3 correlated bets.
#   You are making ~1 bet, not 3. This inflates apparent trade count
#   without adding independent information. See notes on effective n.
# =====================================================================
def signal_reversal(hist, today, z_entry=-1.5, trend_days=200):
    picks = []
    for sym, bars in hist.items():
        if len(bars) < trend_days + 5:
            continue
        c = [b["close"] for b in bars]
        sma_trend = sum(c[-trend_days:]) / trend_days
        if c[-1] <= sma_trend:                      # regime filter, non-negotiable
            continue
        win = c[-21:-1]
        mean = sum(win) / len(win)
        var = sum((x - mean) ** 2 for x in win) / (len(win) - 1)
        sd = var ** 0.5
        if sd <= 0:
            continue
        z = (c[-1] - mean) / sd                     # vol-normalised, not raw RSI
        if z > z_entry:
            continue
        if c[-1] >= c[-2]:                          # require today closed down
            continue
        picks.append((z, sym))                      # most stretched first
    picks.sort()
    return [s for _, s in picks[:3]]


# =====================================================================
# CANDIDATE 2 -- POST-EARNINGS DRIFT, ENTERED AFTER YOUR BLACKOUT
#   "Underreaction to information that is already public."
#
# MECHANISM: investors have limited attention and update beliefs slowly
#   after an earnings surprise. Price drifts in the direction of the
#   surprise for weeks. Ball & Brown (1968), Bernard & Thomas (1989),
#   DellaVigna & Pollet (2009) on Friday announcements getting the least
#   attention and the strongest drift. This is one of the most replicated
#   anomalies in finance.
#
# HORIZON FIT: POOR, and this is the main strike against it. The
#   documented drift runs 20-60 days. You are holding 2-5. You are
#   harvesting maybe a tenth of the effect while paying full round-trip
#   cost. It survives on this list because the mechanism is unusually
#   well-evidenced, not because the fit is good.
#
# TENSION WITH YOUR OWN FILTER: your earnings blackout excludes exactly
#   this window. Entry must be at blackout-exit (day +8), by which point
#   the sharpest drift has passed.
#
# WHAT MAKES IT STOP WORKING:
#   - Largely arbitraged in liquid large caps since the mid-2000s.
#     Surviving drift concentrates in small/illiquid names, which your
#     ADV > 2M filter deliberately excludes. Your filters and this
#     signal are pulling against each other.
#   - Needs an actual surprise measure (actual vs. consensus EPS).
#     A price gap is a noisy proxy and conflates the surprise with the
#     market's reaction to it.
#
# EXTRA DATA REQUIRED: consensus EPS estimates. EDGAR does not have
#   these. This is the one candidate that forces you onto a paid feed.
# =====================================================================
def signal_pead(hist, today, gap_min=0.04, entry_offset=8, earnings=None):
    """
    Proxy version using the earnings-day gap. Replace `gap` with a real
    standardised unexpected earnings measure if you go this route.
    """
    picks = []
    if earnings is None:
        return picks
    for sym, bars in hist.items():
        if len(bars) < 30 or sym not in earnings:
            continue
        target = [e for e in earnings[sym]
                  if 0 < (today - e).days <= entry_offset + 2]
        if not target:
            continue
        edate = max(target)
        if (today - edate).days != entry_offset:
            continue
        i = next((k for k, b in enumerate(bars) if b["date"] > edate), None)
        if i is None or i == 0:
            continue
        gap = bars[i]["open"] / bars[i - 1]["close"] - 1
        if gap < gap_min:
            continue
        if bars[-1]["close"] < bars[i]["open"]:     # drift intact, not given back
            continue
        picks.append((-gap, sym))
    picks.sort()
    return [s for _, s in picks[:3]]


# =====================================================================
# CANDIDATE 3 -- VOLATILITY CONTRACTION BREAKOUT
#   Included so you can see why I rank it last.
#
# STATED MECHANISM: volatility clusters. Low-range periods precede
#   high-range periods. This is real and well documented (Engle's ARCH,
#   1982; it won a Nobel).
#
# WHY THAT RATIONALE DOESN'T ACTUALLY SUPPORT THE TRADE -- read this
# before picking it:
#   Volatility clustering predicts the MAGNITUDE of the next move. It
#   says nothing about the DIRECTION. Every "coiled spring" writeup
#   quietly swaps one for the other. GARCH gives you |r|, not r.
#   The breakout direction is doing all the work and it has no
#   documented support. That is a category error, not a subtle flaw.
#
#   Worse, it is structurally hostile to your parameters. A wider
#   expected move means your 1.5% stop sits inside normal noise. You
#   will be stopped out by the volatility you correctly predicted.
#
# WHAT WOULD MAKE IT WORK: if the direction were supplied by something
#   with its own rationale (order flow imbalance, short interest,
#   institutional accumulation). Then you are testing THAT, and the
#   volatility contraction is just a timing filter. Which is fine, but
#   be honest that the contraction is not the edge.
# =====================================================================
def signal_squeeze(hist, today, lookback=7, breakout_bars=20):
    picks = []
    for sym, bars in hist.items():
        if len(bars) < breakout_bars + lookback + 1:
            continue
        rngs = [b["high"] - b["low"] for b in bars[-lookback:]]
        if rngs[-1] != min(rngs):                          # NR7
            continue
        hi = max(b["high"] for b in bars[-breakout_bars:-1])
        if bars[-1]["close"] <= hi:
            continue
        picks.append((-(bars[-1]["close"] / hi - 1), sym))
    picks.sort()
    return [s for _, s in picks[:3]]


SIGNALS = {"reversal": signal_reversal, "pead": signal_pead, "squeeze": signal_squeeze}
