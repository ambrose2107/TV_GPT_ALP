"""
core/timezone_utils.py — v8 (updated)
Dual-timezone display for all signal/trade timestamps.
Used in webhook log and recent signals display.
"""

import pytz
from datetime import datetime

US_TZ = pytz.timezone("US/Eastern")
JST_TZ = pytz.timezone("Asia/Tokyo")
UTC_TZ = pytz.utc


def now_all_zones():
    """Return current time in UTC, US Eastern, and JST."""
    utc_now = datetime.now(UTC_TZ)
    return {
        "utc": utc_now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "us": utc_now.astimezone(US_TZ).strftime("%Y-%m-%d %H:%M:%S %Z"),
        "jst": utc_now.astimezone(JST_TZ).strftime("%Y-%m-%d %H:%M:%S JST"),
        "utc_iso": utc_now.isoformat(),
    }


def format_dual_timezone(dt_utc: datetime) -> str:
    """
    Given a UTC datetime, return a formatted string showing both
    US Eastern time and JST — for display in signal/trade logs.
    Example: "2026-05-23 09:35 EDT  |  22:35 JST"
    """
    if dt_utc.tzinfo is None:
        dt_utc = UTC_TZ.localize(dt_utc)
    us = dt_utc.astimezone(US_TZ)
    jst = dt_utc.astimezone(JST_TZ)
    return f"{us.strftime('%Y-%m-%d %H:%M %Z')}  |  {jst.strftime('%H:%M JST')}"


def format_timestamp_for_db() -> str:
    """Return UTC ISO string for database storage."""
    return datetime.now(UTC_TZ).isoformat()


def parse_and_dual_format(timestamp_str: str) -> str:
    """
    Parse a timestamp string from DB (ISO or space-separated UTC)
    and return dual-zone formatted string.
    Returns original string on parse failure.
    """
    if not timestamp_str:
        return ""
    try:
        ts = timestamp_str.replace("T", " ").split(".")[0]
        dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        dt = UTC_TZ.localize(dt)
        return format_dual_timezone(dt)
    except Exception:
        return str(timestamp_str)
