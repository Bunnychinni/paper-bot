"""
STAGE 2 / logbook. Every signal, its context, and what happened next.

This file is the entire point of Stage 2. The scanner is a data-collection
instrument, not an income source. In 12-18 months this database is the
out-of-sample sample you cannot get any other way.

Three tables:
  runs      one row per scanner execution, including days with no signals
            (absence of signal is data -- you need the denominator)
  signals   one row per candidate, with the full context snapshot
  outcomes  filled in later by resolve.py once the forward bars exist
"""
from __future__ import annotations
import json, sqlite3
from datetime import date

DB = "logbook.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run_id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_date TEXT NOT NULL,
  run_ts TEXT NOT NULL,
  prereg_hash TEXT NOT NULL,
  prereg_name TEXT NOT NULL,
  universe_n INTEGER,
  scanned_n INTEGER,
  signals_n INTEGER,
  context_json TEXT,
  error TEXT
);
CREATE TABLE IF NOT EXISTS signals (
  signal_id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL,
  signal_date TEXT NOT NULL,
  symbol TEXT NOT NULL,
  rank INTEGER,
  ref_close REAL,
  intended_entry REAL,
  target REAL,
  stop REAL,
  shares REAL,
  notional REAL,
  size_multiplier REAL,
  reason TEXT,
  features_json TEXT,
  UNIQUE(signal_date, symbol)
);
CREATE TABLE IF NOT EXISTS outcomes (
  signal_id INTEGER PRIMARY KEY,
  resolved_ts TEXT,
  actual_entry REAL,
  exit_price REAL,
  exit_date TEXT,
  exit_reason TEXT,
  ret_pct REAL,
  mfe5 REAL,
  mae5 REAL,
  held_days INTEGER,
  entry_slip_bps REAL
);
CREATE INDEX IF NOT EXISTS idx_sig_date ON signals(signal_date);
"""


def connect(path=DB):
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    return con


def start_run(con, prereg_hash, prereg_name, context, universe_n, scanned_n):
    from datetime import datetime, timezone
    cur = con.execute(
        "INSERT INTO runs(run_date,run_ts,prereg_hash,prereg_name,universe_n,"
        "scanned_n,signals_n,context_json) VALUES(?,?,?,?,?,?,0,?)",
        (context["date"], datetime.now(timezone.utc).isoformat(),
         prereg_hash, prereg_name, universe_n, scanned_n, json.dumps(context)))
    con.commit()
    return cur.lastrowid


def log_signal(con, run_id, sig):
    con.execute(
        "INSERT OR IGNORE INTO signals(run_id,signal_date,symbol,rank,ref_close,"
        "intended_entry,target,stop,shares,notional,size_multiplier,reason,"
        "features_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (run_id, sig["signal_date"], sig["symbol"], sig["rank"], sig["ref_close"],
         sig["intended_entry"], sig["target"], sig["stop"], sig["shares"],
         sig["notional"], sig["size_multiplier"], sig["reason"],
         json.dumps(sig.get("features", {}))))
    con.commit()


def finish_run(con, run_id, n_signals, error=None):
    con.execute("UPDATE runs SET signals_n=?, error=? WHERE run_id=?",
                (n_signals, error, run_id))
    con.commit()


def unresolved(con, min_age_days=7):
    """Signals old enough that their 5-day forward window has closed."""
    cutoff = str(date.today().fromordinal(date.today().toordinal() - min_age_days))
    return con.execute(
        "SELECT s.signal_id, s.signal_date, s.symbol, s.intended_entry, s.target, "
        "s.stop FROM signals s LEFT JOIN outcomes o USING(signal_id) "
        "WHERE o.signal_id IS NULL AND s.signal_date <= ? ORDER BY s.signal_date",
        (cutoff,)).fetchall()


def record_outcome(con, signal_id, **kw):
    from datetime import datetime, timezone
    con.execute(
        "INSERT OR REPLACE INTO outcomes(signal_id,resolved_ts,actual_entry,"
        "exit_price,exit_date,exit_reason,ret_pct,mfe5,mae5,held_days,"
        "entry_slip_bps) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (signal_id, datetime.now(timezone.utc).isoformat(),
         kw.get("actual_entry"), kw.get("exit_price"), kw.get("exit_date"),
         kw.get("exit_reason"), kw.get("ret_pct"), kw.get("mfe5"),
         kw.get("mae5"), kw.get("held_days"), kw.get("entry_slip_bps")))
    con.commit()


def progress(con):
    """How close are you to a testable sample?"""
    n_sig = con.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    n_res = con.execute("SELECT COUNT(*) FROM outcomes").fetchone()[0]
    n_days = con.execute("SELECT COUNT(DISTINCT signal_date) FROM signals").fetchone()[0]
    n_runs = con.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    hashes = con.execute("SELECT COUNT(DISTINCT prereg_hash) FROM runs").fetchone()[0]
    row = con.execute("SELECT AVG(ret_pct), COUNT(*) FROM outcomes").fetchone()
    return dict(runs=n_runs, signals=n_sig, resolved=n_res, entry_dates=n_days,
                prereg_versions=hashes,
                mean_ret=(row[0] if row[0] is not None else 0.0), n_ret=row[1])


def print_progress(con, target_trades=318):
    p = progress(con)
    print(f"\n  runs {p['runs']} | signals {p['signals']} | resolved {p['resolved']}"
          f" | distinct entry dates {p['entry_dates']}")
    pctdone = 100 * p["resolved"] / target_trades
    print(f"  progress to a testable sample: {p['resolved']}/{target_trades} "
          f"({pctdone:.1f}%)")
    if p["prereg_versions"] > 1:
        print(f"  !! {p['prereg_versions']} DIFFERENT pre-registrations in this DB.")
        print(f"  !! Changing the rule mid-collection restarts your sample.")
        print(f"  !! Analyse each prereg_hash separately or you are pooling")
        print(f"  !! different hypotheses, which is exactly the trap.")
    print(f"\n  DO NOT compute expectancy until you hit the target. Peeking at")
    print(f"  a running mean and stopping when it looks good is optional-stopping")
    print(f"  bias and it will manufacture an edge that is not there.")
