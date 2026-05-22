"""
core/database.py — SQLite: trades, webhook_log, closed_positions
"""
import sqlite3, os, threading
from datetime import datetime
import pytz

DB_PATH = os.environ.get("DB_PATH", "trades.db")

UTC = pytz.utc
JST = pytz.timezone("Asia/Tokyo")
EST = pytz.timezone("US/Eastern")

def get_conn():
    global DB_PATH
    DB_PATH = os.environ.get("DB_PATH", "trades.db")
    if DB_PATH == ":memory:":
        if not hasattr(_local, "conn") or _local.conn is None:
            _local.conn = sqlite3.connect(":memory:", check_same_thread=False)
            _local.conn.row_factory = sqlite3.Row
        return _local.conn
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _close(conn):
    if DB_PATH != ":memory:":
        conn.close()

def reset_memory_db():
    if hasattr(_local, "conn") and _local.conn:
        _local.conn.close()
    _local.conn = None

def init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT    DEFAULT (datetime('now')),
            symbol      TEXT    NOT NULL,
            action      TEXT    NOT NULL,
            quantity    REAL    NOT NULL,
            order_type  TEXT    NOT NULL,
            status      TEXT    NOT NULL,
            alpaca_id   TEXT,
            message     TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS webhook_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT    DEFAULT (datetime('now')),
            raw_payload TEXT,
            status      TEXT,
            error       TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS closed_positions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            closed_at    TEXT    DEFAULT (datetime('now')),
            symbol       TEXT    NOT NULL,
            qty          REAL    NOT NULL,
            entry_price  REAL,
            exit_price   REAL,
            pnl          REAL,
            pnl_pct      REAL,
            side         TEXT,
            hold_time    TEXT,
            alpaca_id    TEXT
        )
    """)
    conn.commit()
    _close(conn)

# ── Trades ────────────────────────────────────────────────────────────────────
def log_trade(symbol, action, quantity, order_type, status, alpaca_id=None, message=None):
    conn = get_conn()
    conn.execute(
        "INSERT INTO trades (symbol,action,quantity,order_type,status,alpaca_id,message) VALUES (?,?,?,?,?,?,?)",
        (symbol, action, quantity, order_type, status, alpaca_id, message)
    )
    conn.commit()
    _close(conn)

def get_recent_trades(limit=50):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    _close(conn)
    return [dict(r) for r in rows]

def get_all_trades():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM trades ORDER BY id DESC").fetchall()
    _close(conn)
    return [dict(r) for r in rows]

# ── Webhooks ──────────────────────────────────────────────────────────────────
def log_webhook(raw_payload, status, error=None):
    conn = get_conn()
    conn.execute(
        "INSERT INTO webhook_log (raw_payload,status,error) VALUES (?,?,?)",
        (str(raw_payload), status, error)
    )
    conn.commit()
    _close(conn)

// def get_recent_webhooks(limit=20):
//    conn = get_conn()
//    rows = conn.execute("SELECT * FROM webhook_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
//    _close(conn)
//    return [dict(r) for r in rows]
    
def get_recent_webhooks(limit=20):
    conn = get_conn()

    rows = conn.execute(
        "SELECT * FROM webhook_log ORDER BY id DESC LIMIT ?",
        (limit,)
    ).fetchall()

    _close(conn)

    webhooks = []

    for r in rows:
        row = dict(r)

        try:
            ts = row.get("timestamp")

            if ts:
                # SQLite datetime -> UTC
                dt = datetime.strptime(
                    ts,
                    "%Y-%m-%d %H:%M:%S"
                )

                dt = UTC.localize(dt)

                row["utc_time"] = dt.strftime(
                    "%Y-%m-%d %H:%M:%S"
                )

                row["jst_time"] = (
                    dt.astimezone(JST)
                    .strftime("%Y-%m-%d %H:%M:%S")
                )

                row["est_time"] = (
                    dt.astimezone(EST)
                    .strftime("%Y-%m-%d %H:%M:%S")
                )

        except Exception:
            row["utc_time"] = "-"
            row["jst_time"] = "-"
            row["est_time"] = "-"

        webhooks.append(row)

    return webhooks



# ── Closed Positions ──────────────────────────────────────────────────────────
def log_closed_position(symbol, qty, entry_price, exit_price, side="long",
                        hold_time=None, alpaca_id=None):
    if entry_price and exit_price:
        if side == "long":
            pnl     = (exit_price - entry_price) * qty
            pnl_pct = ((exit_price - entry_price) / entry_price) * 100
        else:
            pnl     = (entry_price - exit_price) * qty
            pnl_pct = ((entry_price - exit_price) / entry_price) * 100
    else:
        pnl = pnl_pct = None

    conn = get_conn()
    conn.execute(
        """INSERT INTO closed_positions
           (symbol,qty,entry_price,exit_price,pnl,pnl_pct,side,hold_time,alpaca_id)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (symbol, qty, entry_price, exit_price, pnl, pnl_pct, side, hold_time, alpaca_id)
    )
    conn.commit()
    _close(conn)

def get_closed_positions(limit=100):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM closed_positions ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    _close(conn)
    return [dict(r) for r in rows]

def get_all_closed_positions():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM closed_positions ORDER BY id DESC").fetchall()
    _close(conn)
    return [dict(r) for r in rows]

def get_closed_summary():
    conn = get_conn()
    row = conn.execute("""
        SELECT
            COUNT(*)          as total_trades,
            SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winners,
            SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losers,
            SUM(pnl)          as total_pnl,
            AVG(pnl)          as avg_pnl,
            MAX(pnl)          as best_trade,
            MIN(pnl)          as worst_trade
        FROM closed_positions
        WHERE pnl IS NOT NULL
    """).fetchone()
    _close(conn)
    return dict(row) if row else {}
