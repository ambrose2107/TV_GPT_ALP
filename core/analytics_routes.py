"""
Trade Analytics routes — /api/analytics/*
Powers the new Analytics tab: per-symbol win rates, P&L breakdowns, charts.
"""

from flask import Blueprint, jsonify, session
from core.database import get_db_connection
from core.logger import get_logger
from collections import defaultdict

logger = get_logger(__name__)
analytics_bp = Blueprint("analytics", __name__)


def _require_login():
    return session.get("logged_in") is True


def _get_analytics_data():
    """Compute all analytics from closed_positions table."""
    conn = get_db_connection()
    conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
    cur = conn.cursor()
    # Try closed_positions first (v7 table), fall back to trades
    try:
        cur.execute("""
            SELECT symbol, side, qty, entry_price, exit_price,
                   pnl_dollar, pnl_percent, closed_at
            FROM closed_positions
            ORDER BY closed_at DESC
        """)
        rows = cur.fetchall()
    except Exception:
        rows = []

    if not rows:
        # Fallback: derive from trades table
        try:
            cur.execute("""
                SELECT symbol, action as side, quantity as qty,
                       price as exit_price, 0 as entry_price,
                       0 as pnl_dollar, 0 as pnl_percent,
                       timestamp as closed_at
                FROM trades ORDER BY timestamp DESC LIMIT 200
            """)
            rows = cur.fetchall()
        except Exception:
            rows = []
    conn.close()
    return rows


@analytics_bp.route("/api/analytics/summary", methods=["GET"])
def analytics_summary():
    if not _require_login():
        return jsonify({"error": "Unauthorized"}), 401

    rows = _get_analytics_data()
    if not rows:
        return jsonify({"symbols": [], "totals": {}, "timeline": []})

    # Per-symbol stats
    by_symbol = defaultdict(lambda: {
        "trades": 0, "wins": 0, "losses": 0,
        "total_pnl": 0.0, "win_pnl": 0.0, "loss_pnl": 0.0,
        "max_win": 0.0, "max_loss": 0.0,
    })

    timeline = []  # date → cumulative pnl

    for r in rows:
        sym = r.get("symbol", "UNKNOWN")
        pnl = float(r.get("pnl_dollar") or 0)
        pnl_pct = float(r.get("pnl_percent") or 0)
        s = by_symbol[sym]
        s["trades"] += 1
        s["total_pnl"] += pnl
        if pnl > 0:
            s["wins"] += 1
            s["win_pnl"] += pnl
            s["max_win"] = max(s["max_win"], pnl)
        else:
            s["losses"] += 1
            s["loss_pnl"] += pnl
            s["max_loss"] = min(s["max_loss"], pnl)

        # Timeline entry
        date_str = str(r.get("closed_at", ""))[:10]
        timeline.append({"date": date_str, "pnl": pnl, "symbol": sym})

    # Build symbol list sorted by total trades
    symbols_out = []
    for sym, s in sorted(by_symbol.items(), key=lambda x: -x[1]["trades"]):
        win_rate = round(s["wins"] / s["trades"] * 100, 1) if s["trades"] > 0 else 0
        avg_win = round(s["win_pnl"] / s["wins"], 2) if s["wins"] > 0 else 0
        avg_loss = round(s["loss_pnl"] / s["losses"], 2) if s["losses"] > 0 else 0
        pf = round(abs(s["win_pnl"] / s["loss_pnl"]), 2) if s["loss_pnl"] != 0 else 99.0
        symbols_out.append({
            "symbol": sym,
            "trades": s["trades"],
            "wins": s["wins"],
            "losses": s["losses"],
            "win_rate": win_rate,
            "total_pnl": round(s["total_pnl"], 2),
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": pf,
            "max_win": round(s["max_win"], 2),
            "max_loss": round(s["max_loss"], 2),
        })

    # Overall totals
    all_trades = len(rows)
    all_wins = sum(1 for r in rows if float(r.get("pnl_dollar") or 0) > 0)
    all_pnl = sum(float(r.get("pnl_dollar") or 0) for r in rows)
    total_win_pnl = sum(float(r.get("pnl_dollar") or 0) for r in rows if float(r.get("pnl_dollar") or 0) > 0)
    total_loss_pnl = sum(float(r.get("pnl_dollar") or 0) for r in rows if float(r.get("pnl_dollar") or 0) <= 0)

    totals = {
        "total_trades": all_trades,
        "total_wins": all_wins,
        "total_losses": all_trades - all_wins,
        "win_rate": round(all_wins / all_trades * 100, 1) if all_trades else 0,
        "total_pnl": round(all_pnl, 2),
        "profit_factor": round(abs(total_win_pnl / total_loss_pnl), 2) if total_loss_pnl != 0 else 99.0,
        "avg_trade_pnl": round(all_pnl / all_trades, 2) if all_trades else 0,
        "best_trade": round(max((float(r.get("pnl_dollar") or 0) for r in rows), default=0), 2),
        "worst_trade": round(min((float(r.get("pnl_dollar") or 0) for r in rows), default=0), 2),
    }

    # Cumulative PnL timeline (sorted by date)
    timeline_sorted = sorted(timeline, key=lambda x: x["date"])
    cumulative = 0
    equity_curve = []
    for t in timeline_sorted:
        cumulative += t["pnl"]
        equity_curve.append({"date": t["date"], "cumulative_pnl": round(cumulative, 2), "trade_pnl": round(t["pnl"], 2), "symbol": t["symbol"]})

    return jsonify({
        "symbols": symbols_out,
        "totals": totals,
        "equity_curve": equity_curve,
        "raw_count": len(rows),
    })


@analytics_bp.route("/api/analytics/symbol/<symbol>", methods=["GET"])
def analytics_symbol_detail(symbol):
    """Get all trades for a specific symbol."""
    if not _require_login():
        return jsonify({"error": "Unauthorized"}), 401
    symbol = symbol.upper()
    rows = _get_analytics_data()
    sym_trades = [r for r in rows if r.get("symbol", "").upper() == symbol]
    return jsonify({"symbol": symbol, "trades": sym_trades})
