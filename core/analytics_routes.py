"""
core/analytics_routes.py — v8 NEW
Analytics API: /api/analytics/summary  /api/analytics/symbol/<sym>
Powers the Analytics tab with per-symbol win rates, P&L charts, equity curve.
"""
from flask import Blueprint, jsonify, session
from core.database import get_conn, _close
from core.logger import get_logger
from collections import defaultdict

logger = get_logger(__name__)
analytics_bp = Blueprint("analytics", __name__)

def _auth():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    return None

def _get_all_closed():
    """Pull all closed positions from DB."""
    conn = get_conn()
    conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
    try:
        rows = conn.execute(
            "SELECT symbol, side, qty, entry_price, exit_price, pnl, pnl_pct, closed_at "
            "FROM closed_positions ORDER BY closed_at DESC"
        ).fetchall()
    except Exception:
        rows = []
    _close(conn)
    return rows

@analytics_bp.route("/api/analytics/summary", methods=["GET"])
def analytics_summary():
    e = _auth()
    if e: return e

    rows = _get_all_closed()
    if not rows:
        return jsonify({"symbols": [], "totals": {}, "equity_curve": [], "raw_count": 0})

    by_symbol = defaultdict(lambda: {
        "trades": 0, "wins": 0, "losses": 0,
        "total_pnl": 0.0, "win_pnl": 0.0, "loss_pnl": 0.0,
        "max_win": 0.0, "max_loss": 0.0,
    })
    timeline = []

    for r in rows:
        sym = r.get("symbol", "UNKNOWN")
        pnl = float(r.get("pnl") or 0)
        s   = by_symbol[sym]
        s["trades"] += 1
        s["total_pnl"] += pnl
        if pnl > 0:
            s["wins"]    += 1
            s["win_pnl"] += pnl
            s["max_win"]  = max(s["max_win"], pnl)
        else:
            s["losses"]   += 1
            s["loss_pnl"] += pnl
            s["max_loss"]  = min(s["max_loss"], pnl)
        date_str = str(r.get("closed_at", ""))[:10]
        timeline.append({"date": date_str, "pnl": pnl, "symbol": sym})

    symbols_out = []
    for sym, s in sorted(by_symbol.items(), key=lambda x: -x[1]["trades"]):
        win_rate = round(s["wins"] / s["trades"] * 100, 1) if s["trades"] > 0 else 0
        avg_win  = round(s["win_pnl"]  / s["wins"],   2) if s["wins"]   > 0 else 0
        avg_loss = round(s["loss_pnl"] / s["losses"], 2) if s["losses"] > 0 else 0
        pf       = round(abs(s["win_pnl"] / s["loss_pnl"]), 2) if s["loss_pnl"] != 0 else 99.0
        symbols_out.append({
            "symbol":        sym,
            "trades":        s["trades"],
            "wins":          s["wins"],
            "losses":        s["losses"],
            "win_rate":      win_rate,
            "total_pnl":     round(s["total_pnl"], 2),
            "avg_win":       avg_win,
            "avg_loss":      avg_loss,
            "profit_factor": pf,
            "max_win":       round(s["max_win"],  2),
            "max_loss":      round(s["max_loss"], 2),
        })

    all_trades   = len(rows)
    all_wins     = sum(1 for r in rows if float(r.get("pnl") or 0) > 0)
    all_pnl      = sum(float(r.get("pnl") or 0) for r in rows)
    win_pnl_sum  = sum(float(r.get("pnl") or 0) for r in rows if float(r.get("pnl") or 0) > 0)
    loss_pnl_sum = sum(float(r.get("pnl") or 0) for r in rows if float(r.get("pnl") or 0) <= 0)

    totals = {
        "total_trades":  all_trades,
        "total_wins":    all_wins,
        "total_losses":  all_trades - all_wins,
        "win_rate":      round(all_wins / all_trades * 100, 1) if all_trades else 0,
        "total_pnl":     round(all_pnl, 2),
        "profit_factor": round(abs(win_pnl_sum / loss_pnl_sum), 2) if loss_pnl_sum != 0 else 99.0,
        "avg_trade_pnl": round(all_pnl / all_trades, 2) if all_trades else 0,
        "best_trade":    round(max((float(r.get("pnl") or 0) for r in rows), default=0), 2),
        "worst_trade":   round(min((float(r.get("pnl") or 0) for r in rows), default=0), 2),
    }

    # Equity curve
    timeline_sorted = sorted(timeline, key=lambda x: x["date"])
    cumulative = 0
    equity_curve = []
    for t in timeline_sorted:
        cumulative += t["pnl"]
        equity_curve.append({
            "date":           t["date"],
            "cumulative_pnl": round(cumulative, 2),
            "trade_pnl":      round(t["pnl"], 2),
            "symbol":         t["symbol"],
        })

    return jsonify({
        "symbols":      symbols_out,
        "totals":       totals,
        "equity_curve": equity_curve,
        "raw_count":    len(rows),
    })

@analytics_bp.route("/api/analytics/symbol/<symbol>", methods=["GET"])
def analytics_symbol_detail(symbol):
    e = _auth()
    if e: return e
    rows     = _get_all_closed()
    sym_rows = [r for r in rows if r.get("symbol", "").upper() == symbol.upper()]
    return jsonify({"symbol": symbol.upper(), "trades": sym_rows})
