"""
PAPER EXECUTION ENGINE. Places real orders in the Alpaca PAPER account.

HARD SAFETY RAILS (enforced in code):
  1. paper=True is hard-wired; a live endpoint is unreachable from here.
  2. Refuses to run without preregistration.md (hash logged per run).
  3. Max 3 open positions, max 30% of equity per position, never adds
     to an existing position.
  4. KILL SWITCH: create a file named STOP in the repo root -> cancels
     all orders, flattens all positions, refuses new entries.
  5. Cash-account aware: spends only settled cash reported by the API.

"Working as software" means orders in, fills back, exits managed,
everything booked. It does NOT mean the rule is profitable.
"""
from __future__ import annotations
import os, sys, sqlite3, hashlib
from datetime import date, datetime, timezone

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (MarketOrderRequest, LimitOrderRequest,
                                     GetOrdersRequest, StopLossRequest,
                                     TakeProfitRequest)
from alpaca.trading.enums import (OrderSide, TimeInForce, QueryOrderStatus,
                                  OrderClass)

DB = "logbook.db"
MAX_NOTIONAL = float(os.environ.get("MAX_NOTIONAL", "300"))  # cap per position; prereg cost model is $300


def client_or_die():
    key = os.environ.get("APCA_API_KEY_ID", "")
    sec = os.environ.get("APCA_API_SECRET_KEY", "")
    if not key or not sec:
        sys.exit("no API keys in environment")
    c = TradingClient(key, sec, paper=True)          # hard-wired paper
    acct = c.get_account()
    if getattr(acct, "account_blocked", False) or getattr(acct, "trading_blocked", False):
        sys.exit("account blocked -- refusing to run")
    return c, acct


def prereg_or_die(path="preregistration.md"):
    if not os.path.exists(path):
        sys.exit(f"no {path} -- the bot will not trade an unregistered rule.")
    txt = open(path, encoding="utf-8").read()
    if "TODO" in txt:
        sys.exit(f"{path} still contains TODO items -- fill them in first.")
    return hashlib.sha256(txt.encode()).hexdigest()[:16]


def kill_switch_engaged():
    return os.path.exists("STOP")


def flatten_all(c):
    print("KILL SWITCH: cancelling orders, closing all positions")
    c.cancel_orders()
    c.close_all_positions(cancel_orders=True)


def settled_cash(acct):
    return float(acct.cash)


def _fills_table(con):
    con.execute("""CREATE TABLE IF NOT EXISTS fills(
        order_id TEXT PRIMARY KEY, symbol TEXT, side TEXT, qty REAL,
        avg_price REAL, submitted_at TEXT, filled_at TEXT, status TEXT,
        recorded_ts TEXT)""")
    con.commit()


def reconcile(c):
    """Book every closed order into logbook.db (idempotent)."""
    con = sqlite3.connect(DB); _fills_table(con)
    req = GetOrdersRequest(status=QueryOrderStatus.CLOSED, limit=200)
    n = 0
    for o in c.get_orders(req):
        try:
            con.execute("INSERT OR IGNORE INTO fills VALUES(?,?,?,?,?,?,?,?,?)",
                        (str(o.id), o.symbol, str(o.side), float(o.filled_qty or 0),
                         float(o.filled_avg_price or 0),
                         str(o.submitted_at), str(o.filled_at), str(o.status),
                         datetime.now(timezone.utc).isoformat()))
            n += con.total_changes and 1
        except Exception as e:
            print("  reconcile skip:", o.symbol, e)
    con.commit(); con.close()
    print(f"  reconciled orders into {DB}")


def enter(c, sym, notional):
    if notional < 1.0:
        print(f"  {sym}: notional too small, skipped"); return
    o = c.submit_order(MarketOrderRequest(
        symbol=sym, notional=round(notional, 2),
        side=OrderSide.BUY, time_in_force=TimeInForce.DAY))
    print(f"  ENTRY submitted {sym} ${notional:.2f} id={o.id}")


def protect(c, sym, qty, avg_price, target_pct, stop_pct):
    """OCO: take-profit limit + stop-loss. Whole shares only (OCO cannot
    carry fractional qty); any fractional remainder is handled by the
    time exit, which closes the full position."""
    whole = int(float(qty))
    if whole < 1:
        print(f"  {sym}: fractional-only position, time exit will handle it")
        return
    tp = round(avg_price * (1 + target_pct/100), 2)
    st = round(avg_price * (1 - stop_pct/100), 2)
    c.submit_order(LimitOrderRequest(
        symbol=sym, qty=whole, side=OrderSide.SELL,
        time_in_force=TimeInForce.GTC, limit_price=tp,
        order_class=OrderClass.OCO,
        take_profit=TakeProfitRequest(limit_price=tp),
        stop_loss=StopLossRequest(stop_price=st)))
    print(f"  PROTECT {sym}: target {tp} / stop {st} ({whole} sh)")


def _cancel_open_orders_for(c, sym):
    for o in c.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[sym])):
        c.cancel_order_by_id(o.id)


def time_exit(c, max_hold_days):
    for p in c.get_all_positions():
        req = GetOrdersRequest(status=QueryOrderStatus.CLOSED, symbols=[p.symbol], limit=50)
        buys = [o for o in c.get_orders(req)
                if o.filled_at and o.side == OrderSide.BUY]
        if not buys:
            continue
        opened = max(o.filled_at for o in buys).date()
        held = (date.today() - opened).days
        if held >= max_hold_days:
            print(f"  TIME EXIT {p.symbol}: held {held}d")
            _cancel_open_orders_for(c, p.symbol)   # free the shares first
            c.close_position(p.symbol)


def morning_run(candidates, target_pct, stop_pct, max_positions=3, pos_frac=0.30):
    c, acct = client_or_die()
    h = prereg_or_die()
    print(f"prereg {h} | equity ${float(acct.equity):.2f} | "
          f"settled cash ${settled_cash(acct):.2f}")
    if kill_switch_engaged():
        flatten_all(c); return
    held = {p.symbol for p in c.get_all_positions()}
    pending = {o.symbol for o in c.get_orders(
        GetOrdersRequest(status=QueryOrderStatus.OPEN))
        if o.side == OrderSide.BUY}
    taken = held | pending
    slots = max_positions - len(taken)
    if slots <= 0:
        print(f"no free slots (held {sorted(held)}, pending {sorted(pending)})"); return
    fresh = [s for s in candidates if s not in taken]
    cash = settled_cash(acct)
    per = min(float(acct.equity) * pos_frac, cash / max(slots, 1), MAX_NOTIONAL)
    for sym in fresh[:slots]:
        enter(c, sym, per)
    reconcile(c)


def evening_run(target_pct, stop_pct, max_hold_days=5):
    c, acct = client_or_die()
    prereg_or_die()
    if kill_switch_engaged():
        flatten_all(c); reconcile(c); return
    open_orders = c.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN))
    protected = {o.symbol for o in open_orders if o.side == OrderSide.SELL}
    for p in c.get_all_positions():
        if p.symbol not in protected:
            protect(c, p.symbol, p.qty, float(p.avg_entry_price),
                    target_pct, stop_pct)
    time_exit(c, max_hold_days)
    reconcile(c)
