"""
STAGE 1 / backtest engine. Cash account, T+1 settlement, $ compounding.

GAP ACCOUNTING (correction 2):
  A stop is an ORDER, not a guarantee. Three distinct exit categories,
  reported separately and NEVER blended:

    stop_clean : bar traded down through the stop intraday. Filled at the
                 stop price minus a small slip. Loss ~= intended stop.
    stop_gap   : bar OPENED at or below the stop. The stop became a market
                 order at the open. Filled at the open. Loss > intended.
    target_gap : bar OPENED at or above the target. Limit filled at the
                 open, better than intended. Reported separately as an
                 offsetting item -- it is NOT netted against stop_gap,
                 because you cannot rely on it and it is not symmetric.

  Reported for stop_gap: frequency (of all trades and of losers),
  average realized loss, worst single loss, and total $ gap tax vs a
  world where every stop held exactly.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from datetime import date, timedelta

SEC_RATE, TAF_RATE, TAF_CAP, CAT_RATE = 20.60/1_000_000, 0.000195, 9.79, 0.000050
def ceil_penny(x): return math.ceil(x*100 - 1e-9)/100
def sell_fees(pr, sh): return (ceil_penny(SEC_RATE*pr)
                               + ceil_penny(min(TAF_RATE*sh, TAF_CAP))
                               + ceil_penny(CAT_RATE*sh))
def buy_fees(sh): return ceil_penny(CAT_RATE*sh)

def next_bday(d):
    d += timedelta(days=1)
    while d.weekday() >= 5: d += timedelta(days=1)
    return d


@dataclass
class Pos:
    sym: str; shares: float; entry: float; entry_date: date
    target: float; stop: float


@dataclass
class Account:
    settled: float = 1000.0
    pending: list = field(default_factory=list)
    pos: dict = field(default_factory=dict)
    slots: int = 3
    frac: float = 0.30
    trades: list = field(default_factory=list)

    def settle(self, today):
        keep, freed = [], 0.0
        for d, a in self.pending:
            (keep.append((d, a)) if d > today else None)
            freed += a if d <= today else 0.0
        self.pending, self.settled = keep, self.settled + freed

    def equity(self, marks):
        held = sum(p.shares*marks.get(p.sym, p.entry) for p in self.pos.values())
        return self.settled + sum(a for _, a in self.pending) + held

    def open(self, sym, px, today, tgt, stp, marks):
        if sym in self.pos or len(self.pos) >= self.slots: return False
        notional = min(self.equity(marks)*self.frac, self.settled)
        if notional < 1.0: return False
        sh = notional/px
        fee = buy_fees(sh)
        if notional + fee > self.settled: return False
        self.settled -= notional + fee
        self.pos[sym] = Pos(sym, sh, px, today, tgt, stp)
        return True

    def close(self, sym, px, today, reason):
        p = self.pos.pop(sym)
        proceeds = p.shares*px
        fee = sell_fees(proceeds, p.shares)
        net = proceeds - fee
        self.pending.append((next_bday(today), net))
        cost_basis = p.shares*p.entry
        self.trades.append(dict(
            sym=sym, entry=p.entry, exit=px, shares=p.shares,
            entry_date=p.entry_date, exit_date=today, reason=reason,
            pnl=net - cost_basis,
            ret_pct=(px/p.entry - 1)*100,
            intended_stop_pct=(p.stop/p.entry - 1)*100,
            held=(today - p.entry_date).days,
            fees=fee + buy_fees(p.shares)))


def run(bars_by_sym, signal_fn, eligible, halted, earnings, bad_dates,
        start_equity=1000.0, target_pct=3.0, stop_pct=1.5, max_hold=5,
        entry_slip_bps=2.0, stop_slip_bps=3.0, in_earnings_fn=None):
    """
    Intrabar convention: STOP IS CHECKED FIRST. If a bar touches both the
    stop and the target, we assume the stop filled. Doing it the other way
    is the single most common source of inflated backtests.
    """
    from stage1_data import in_earnings_blackout
    in_earnings_fn = in_earnings_fn or in_earnings_blackout

    idx = {s: {b["date"]: b for b in bars} for s, bars in bars_by_sym.items()}
    all_dates = sorted({b["date"] for bs in bars_by_sym.values() for b in bs})
    acct = Account(settled=start_equity)
    hist = {s: [] for s in bars_by_sym}
    curve, skipped = [], {"earnings": 0, "halt": 0, "ineligible": 0, "corp_action": 0}

    for today in all_dates:
        acct.settle(today)
        marks = {s: idx[s][today]["close"] for s in idx if today in idx[s]}

        # ---- exits ----
        for sym in list(acct.pos):
            bar = idx[sym].get(today)
            p = acct.pos[sym]
            if not bar or p.entry_date == today:
                continue
            if bar["open"] <= p.stop:                       # GAPPED THROUGH
                acct.close(sym, bar["open"], today, "stop_gap")
            elif bar["low"] <= p.stop:                      # clean stop
                acct.close(sym, p.stop*(1 - stop_slip_bps/10_000), today, "stop_clean")
            elif bar["open"] >= p.target:                   # favourable gap
                acct.close(sym, bar["open"], today, "target_gap")
            elif bar["high"] >= p.target:
                acct.close(sym, p.target, today, "target")
            elif (today - p.entry_date).days >= max_hold:
                acct.close(sym, bar["close"], today, "time")

        # ---- entries, using only bars strictly before today ----
        for sym in signal_fn(hist, today):
            if len(acct.pos) >= acct.slots: break
            bar = idx.get(sym, {}).get(today)
            if not bar or sym in acct.pos: continue
            if not eligible.get(sym, {}).get(today, False):
                skipped["ineligible"] += 1; continue
            if today in halted.get(sym, set()):
                skipped["halt"] += 1; continue
            if today in bad_dates.get(sym, set()):
                skipped["corp_action"] += 1; continue
            if in_earnings_fn(sym, today, earnings):
                skipped["earnings"] += 1; continue
            px = bar["open"]*(1 + entry_slip_bps/10_000)
            acct.open(sym, px, today, px*(1+target_pct/100), px*(1-stop_pct/100), marks)

        for s in hist:
            if today in idx[s]: hist[s].append(idx[s][today])
        curve.append((today, acct.equity(marks)))

    return acct, curve, skipped


# --------------------------------------------------------------- metrics
def analyse(acct, curve, start_equity=1000.0):
    t = acct.trades
    eq = [e for _, e in curve] or [start_equity]
    peak, mdd = eq[0], 0.0
    for v in eq:
        peak = max(peak, v); mdd = max(mdd, (peak - v)/peak if peak else 0)

    wins = [x for x in t if x["pnl"] > 0]
    losses = [x for x in t if x["pnl"] <= 0]
    gross_w = sum(x["pnl"] for x in wins)
    gross_l = -sum(x["pnl"] for x in losses)

    gaps = [x for x in t if x["reason"] == "stop_gap"]
    cleans = [x for x in t if x["reason"] == "stop_clean"]
    tgaps = [x for x in t if x["reason"] == "target_gap"]

    # gap tax: what the gapped exits cost vs. the stop holding exactly
    gap_tax = sum((x["intended_stop_pct"] - x["ret_pct"])/100 * x["shares"] * x["entry"]
                  for x in gaps)

    return dict(
        n=len(t), start=eq[0], end=eq[-1],
        ret_pct=(eq[-1]/eq[0]-1)*100 if eq[0] else 0,
        win_rate=100*len(wins)/len(t) if t else 0,
        profit_factor=(gross_w/gross_l) if gross_l > 0 else float("inf"),
        max_dd=100*mdd,
        avg_hold=sum(x["held"] for x in t)/len(t) if t else 0,
        avg_win=sum(x["ret_pct"] for x in wins)/len(wins) if wins else 0,
        avg_loss=sum(x["ret_pct"] for x in losses)/len(losses) if losses else 0,
        total_fees=sum(x["fees"] for x in t),
        exits={r: sum(1 for x in t if x["reason"] == r)
               for r in ("target", "target_gap", "stop_clean", "stop_gap", "time")},
        gap=dict(
            n=len(gaps),
            pct_all=100*len(gaps)/len(t) if t else 0,
            pct_losers=100*len(gaps)/len(losses) if losses else 0,
            avg_loss_pct=sum(x["ret_pct"] for x in gaps)/len(gaps) if gaps else 0,
            worst_loss_pct=min((x["ret_pct"] for x in gaps), default=0.0),
            worst_loss_usd=min((x["pnl"] for x in gaps), default=0.0),
            gap_tax_usd=gap_tax,
            clean_avg_loss_pct=sum(x["ret_pct"] for x in cleans)/len(cleans) if cleans else 0),
        favourable_gap=dict(
            n=len(tgaps),
            avg_gain_pct=sum(x["ret_pct"] for x in tgaps)/len(tgaps) if tgaps else 0),
    )
