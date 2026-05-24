"""
core/database.py — v8
SQLite database layer.
Tables: trades, webhook_log, closed_positions

v8 changes:
- get_webhook_log now returns both utc + dual_tz fields
- get_closed_positions() helper exposed for analytics/mirrorfish
- init_db creates closed_positions if missing
"""

import sqlite3
import os
from core.logger import get_logger
from core.timezone_utils import parse_and_dual_format

logger = get_logger(__name__)
DB_PATH = os.environ.get("DB_PATH", "trades.db")


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        action TEXT NOT NULL,
        quantity REAL NOT NULL,
        price REAL,
        order_id TEXT,
        status TEXT DEFAULT 'filled',
        error_msg TEXT,
        timestamp TEXT NOT NULL
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS webhook_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT,
        action TEXT,
        raw_payload TEXT,
        result TEXT,
        timestamp TEXT NOT NULL
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS closed_positions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        side TEXT DEFAULT 'LONG',
        qty REAL DEFAULT 0,
        entry_price REAL DEFAULT 0,
        exit_price REAL DEFAULT 0,
        pnl_dollar REAL DEFAULT 0,
        pnl_percent REAL DEFAULT 0,
        closed_at TEXT NOT NULL
    )""")

    conn.commit()
    conn.close()
    logger.info("Database initialized.")


def log_trade(symbol, action, quantity, price=None, order_id=None,
              status="filled", error_msg=None):
    from core.timezone_utils import format_timestamp_for_db
    conn = get_db_connection()
    conn.execute(
        """INSERT INTO trades (symbol, action, quantity, price, order_id, status, error_msg, timestamp)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (symbol, action, quantity, price, order_id, status, error_msg,
         format_timestamp_for_db())
    )
    conn.commit()
    conn.close()


def log_webhook(symbol, action, raw_payload, result):
    from core.timezone_utils import format_timestamp_for_db
    conn = get_db_connection()
    conn.execute(
        """INSERT INTO webhook_log (symbol, action, raw_payload, result, timestamp)
           VALUES (?, ?, ?, ?, ?)""",
        (symbol, action, str(raw_payload)[:500], result, format_timestamp_for_db())
    )
    conn.commit()
    conn.close()


def get_trades(limit=50):
    conn = get_db_connection()
    conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
    cur = conn.cursor()
    cur.execute("SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    # Add dual-timezone display
    for row in rows:
        row["timestamp_display"] = parse_and_dual_format(row.get("timestamp", ""))
    return rows


def get_webhook_log(limit=20):
    conn = get_db_connection()
    conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
    cur = conn.cursor()
    cur.execute("SELECT * FROM webhook_log ORDER BY timestamp DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    # Add dual-timezone display field for each log entry
    for row in rows:
        ts_raw = row.get("timestamp", "")
        row["timestamp_display"] = parse_and_dual_format(ts_raw)
        # Keep original UTC for JS
        row["timestamp_utc"] = ts_raw
    return rows


def get_closed_positions(limit=100):
    conn = get_db_connection()
    conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT * FROM closed_positions ORDER BY closed_at DESC LIMIT ?",
            (limit,)
        )
        rows = cur.fetchall()
    except Exception:
        rows = []
    conn.close()
    for row in rows:
        row["closed_at_display"] = parse_and_dual_format(row.get("closed_at", ""))
    return rows


def save_closed_position(symbol, side, qty, entry_price, exit_price,
                          pnl_dollar, pnl_percent):
    from core.timezone_utils import format_timestamp_for_db
    conn = get_db_connection()
    conn.execute(
        """INSERT INTO closed_positions
           (symbol, side, qty, entry_price, exit_price, pnl_dollar, pnl_percent, closed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (symbol, side, qty, entry_price, exit_price, pnl_dollar, pnl_percent,
         format_timestamp_for_db())
    )
    conn.commit()
    conn.close()
