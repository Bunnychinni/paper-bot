"""
STAGE 2 / overnight context. Regime filter + macro blackout.

WHAT I COULD NOT GET, AND WHAT I USED INSTEAD -- read before trusting this:

  ES / NQ futures : Alpaca does not serve futures on the free plan.
                    PROXY: SPY and QQQ prior-day close-to-close move.
                    This is NOT overnight futures. It tells you what
                    happened yesterday, not what is happening at 8:45.
                    If you later get a futures feed, replace index_move().

  VIX             : Alpaca does not serve index values (VIX is an index,
                    not a security). PROXY: VIXY, the short-term VIX
                    futures ETF. It tracks direction well and LEVEL badly
                    -- contango decay means VIXY's absolute value drifts
                    down over years and is not comparable across time.
                    So we use its PERCENTILE over a trailing window, never
                    a fixed threshold like "VIX > 20".
                    Second proxy, and honestly the better one: realized
                    volatility of SPY over the last 20 sessions. No feed
                    needed, no decay, directly measurable.

  Macro calendar  : no free reliable API. You supply macro_calendar.csv.
                    FAILS OPEN with a loud warning, unlike the earnings
                    blackout which fails closed. Different risk: missing
                    an earnings date can hand you a -18% gap, missing a
                    CPI print costs you some extra variance. Not the same
                    severity, so not the same default.
"""
from __future__ import annotations
import csv, os
from datetime import date, timedelta

MACRO_HALVE = {"CPI", "FOMC", "NFP", "PCE"}   # halve size
MACRO_SKIP  = {"FOMC_DECISION"}                # skip entirely


def load_macro(path="macro_calendar.csv"):
    """CSV: date,event   e.g.  2026-09-17,FOMC_DECISION"""
    if not os.path.exists(path):
        print(f"  !! WARNING: no {path}. Macro filter DISABLED (fails open).")
        print(f"  !! FOMC dates are published a year ahead at federalreserve.gov;")
        print(f"  !! BLS publishes CPI and NFP release schedules. Fill this in.")
        return None
    out = {}
    with open(path) as f:
        for row in csv.DictReader(f):
            y, m, d = row["date"].split("-")
            out.setdefault(date(int(y), int(m), int(d)), set()).add(
                row["event"].strip().upper())
    return out


def macro_state(today, macro):
    """Returns ('ok'|'halve'|'skip', reason)."""
    if macro is None:
        return "ok", "macro filter disabled (no calendar file)"
    ev = macro.get(today, set())
    if ev & MACRO_SKIP:
        return "skip", f"macro: {sorted(ev & MACRO_SKIP)}"
    if ev & MACRO_HALVE:
        return "halve", f"macro: {sorted(ev & MACRO_HALVE)}"
    return "ok", "no macro event"


def realized_vol(bars, n=20):
    """Annualised close-to-close vol over n sessions. The honest vol measure."""
    c = [b["close"] for b in bars[-(n + 1):]]
    if len(c) < n + 1:
        return None
    rets = [c[i] / c[i - 1] - 1 for i in range(1, len(c))]
    m = sum(rets) / len(rets)
    sd = (sum((r - m) ** 2 for r in rets) / (len(rets) - 1)) ** 0.5
    return sd * (252 ** 0.5) * 100


def vol_percentile(bars, lookback=252, n=20):
    """Where today's realized vol sits vs its own history. Beats a fixed
    threshold because volatility regimes shift and 20 does not mean in 2026
    what it meant in 2019."""
    series = []
    for i in range(n + 1, len(bars)):
        v = realized_vol(bars[:i], n)
        if v is not None:
            series.append(v)
    if len(series) < 30:
        return None, None
    hist = series[-lookback:]
    cur = series[-1]
    pct = 100 * sum(1 for x in hist if x <= cur) / len(hist)
    return cur, pct


def index_move(bars):
    """PROXY for overnight futures. Prior-session close-to-close %."""
    if len(bars) < 2:
        return None
    return (bars[-1]["close"] / bars[-2]["close"] - 1) * 100


def build_context(bars_by_sym, today, macro_path="macro_calendar.csv"):
    """
    bars_by_sym needs SPY, QQQ, VIXY (VIXY optional).
    Returns a dict the scanner uses and the logbook stores verbatim, so you
    can later ask 'did this filter actually help?' instead of guessing.
    """
    macro = load_macro(macro_path)
    state, reason = macro_state(today, macro)

    spy = bars_by_sym.get("SPY", [])
    qqq = bars_by_sym.get("QQQ", [])
    vixy = bars_by_sym.get("VIXY", [])

    rv, rv_pct = vol_percentile(spy) if spy else (None, None)
    _, vixy_pct = vol_percentile(vixy) if vixy else (None, None)

    ctx = dict(
        date=str(today),
        spy_prior_move=index_move(spy),
        qqq_prior_move=index_move(qqq),
        spy_realized_vol=rv,
        spy_vol_percentile=rv_pct,
        vixy_vol_percentile=vixy_pct,
        macro_state=state,
        macro_reason=reason,
        size_multiplier=1.0,
        notes=[],
    )

    if state == "skip":
        ctx["size_multiplier"] = 0.0
        ctx["notes"].append(f"SKIP DAY -- {reason}")
    elif state == "halve":
        ctx["size_multiplier"] = 0.5
        ctx["notes"].append(f"HALF SIZE -- {reason}")

    # Regime note only. NOT a filter -- you have not demonstrated that
    # conditioning on vol helps, and turning an untested belief into a rule
    # is how the last strategy died. Log it, decide later with data.
    if rv_pct is not None:
        band = ("LOW" if rv_pct < 30 else "HIGH" if rv_pct > 70 else "MID")
        ctx["notes"].append(f"vol regime {band} ({rv_pct:.0f}th pct, rv={rv:.1f}%)")

    return ctx
