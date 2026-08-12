#!/usr/bin/env python3
"""
Export bot status -> docs/status.json for the GitHub Pages dashboard.
Runs inside the workflow after the bot. Read-only. Never fails the build.
"""
import json, os, sqlite3
from datetime import datetime, timezone

OUT = "docs/status.json"
TARGET_TRADES = 300


def from_logbook():
    d = dict(runs=[], fills=[], signals_total=0, resolved=0, entry_dates=0)
    if not os.path.exists("logbook.db"):
        return d
    con = sqlite3.connect("logbook.db")
    try:
        d["runs"] = [dict(zip(("date", "ts", "prereg", "signals"), r)) for r in
                     con.execute("SELECT run_date, run_ts, prereg_hash, signals_n "
                                 "FROM runs ORDER BY run_id DESC LIMIT 10")]
    except sqlite3.OperationalError:
        pass
    try:
        d["signals_total"] = con.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        d["entry_dates"] = con.execute(
            "SELECT COUNT(DISTINCT signal_date) FROM signals").fetchone()[0]
        d["resolved"] = con.execute("SELECT COUNT(*) FROM outcomes").fetchone()[0]
    except sqlite3.OperationalError:
        pass
    try:
        d["fills"] = [dict(zip(("symbol", "side", "qty", "price", "filled_at"), r))
                      for r in con.execute(
                          "SELECT symbol, side, qty, avg_price, filled_at FROM fills "
                          "WHERE status LIKE '%FILLED%' OR status LIKE '%filled%' "
                          "ORDER BY filled_at DESC LIMIT 20")]
    except sqlite3.OperationalError:
        pass
    con.close()
    return d


def from_alpaca():
    try:
        from alpaca.trading.client import TradingClient
        c = TradingClient(os.environ["APCA_API_KEY_ID"],
                          os.environ["APCA_API_SECRET_KEY"], paper=True)
        a = c.get_account()
        pos = [dict(symbol=p.symbol, qty=float(p.qty),
                    avg_entry=float(p.avg_entry_price),
                    value=float(p.market_value),
                    upl=float(p.unrealized_pl)) for p in c.get_all_positions()]
        return dict(equity=float(a.equity), cash=float(a.cash),
                    status=str(a.status), positions=pos)
    except Exception as e:
        return dict(error=str(e)[:120], positions=[])


def main():
    os.makedirs("docs", exist_ok=True)
    payload = dict(
        generated=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        target_trades=TARGET_TRADES,
        mode="PAPER ONLY",
        logbook=from_logbook(),
        account=from_alpaca(),
    )
    with open(OUT, "w") as f:
        json.dump(payload, f, indent=1)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
