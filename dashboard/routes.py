"""
dashboard/routes.py — All dashboard routes
"""
from flask import Blueprint, render_template, jsonify, request, session, redirect, url_for, send_file
import io
from core.database import (get_recent_trades, get_recent_webhooks, get_closed_positions,
                            get_closed_summary, log_closed_position, get_all_trades)
from core.config import Config
from core.telegram import send_telegram, alert_kill_switch
from core.excel_export import export_trades_excel
from brokers.alpaca_adapter import AlpacaAdapter
from core.logger import get_logger

logger = get_logger(__name__)
dashboard_bp = Blueprint("dashboard", __name__)
alpaca = AlpacaAdapter()

# ── Auth ──────────────────────────────────────────────────────────────────────
@dashboard_bp.route("/", methods=["GET"])
def index():
    if not session.get("logged_in"):
        return redirect(url_for("dashboard.login"))
    return render_template("dashboard.html")

@dashboard_bp.route("/login", methods=["GET","POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == Config.DASHBOARD_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("dashboard.index"))
        error = "Wrong password"
    return render_template("login.html", error=error)

@dashboard_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("dashboard.login"))

def _auth():
    if not session.get("logged_in"):
        return jsonify({"error":"Unauthorized"}), 401
    return None

# ── Account ───────────────────────────────────────────────────────────────────
@dashboard_bp.route("/api/account")
def api_account():
    e = _auth()
    if e: return e
    try:
        account   = alpaca.get_account()
        positions = alpaca.get_positions()
        return jsonify({"account": account, "positions": positions})
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500

# ── Trades ────────────────────────────────────────────────────────────────────
@dashboard_bp.route("/api/trades")
def api_trades():
    e = _auth()
    if e: return e
    return jsonify(get_recent_trades(50))

@dashboard_bp.route("/api/webhooks")
def api_webhooks():
    e = _auth()
    if e: return e
    return jsonify(get_recent_webhooks(20))

# ── Closed positions ──────────────────────────────────────────────────────────
@dashboard_bp.route("/api/closed_positions")
def api_closed_positions():
    e = _auth()
    if e: return e
    return jsonify({
        "positions": get_closed_positions(100),
        "summary":   get_closed_summary()
    })

# ── Close selected position ───────────────────────────────────────────────────
@dashboard_bp.route("/api/close_position", methods=["POST"])
def api_close_position():
    e = _auth()
    if e: return e
    data   = request.json or {}
    symbol = data.get("symbol","").upper().strip()
    qty    = data.get("qty", None)  # optional: partial close qty

    if not symbol:
        return jsonify({"success": False, "error": "Symbol required"}), 400

    try:
        # Get current position for P&L tracking
        pos = alpaca.get_position(symbol)
        entry_price  = float(pos.get("avg_entry_price", 0)) if pos else None
        current_price= float(pos.get("current_price", 0))  if pos else None
        pos_qty      = float(pos.get("qty", 0))             if pos else 0
        side         = "long" if pos_qty > 0 else "short"   if pos else "long"

        # Partial or full close
        if qty and float(qty) < abs(pos_qty):
            close_qty = float(qty)
            order_side = "sell" if pos_qty > 0 else "buy"
            result = alpaca.place_market_order(symbol, order_side, close_qty)
        else:
            result = alpaca.close_position(symbol)
            close_qty = abs(pos_qty)

        # Log to closed_positions
        if entry_price and current_price:
            log_closed_position(
                symbol=symbol, qty=close_qty,
                entry_price=entry_price, exit_price=current_price,
                side=side, alpaca_id=result.get("id") if result else None
            )

        pnl = ((current_price - entry_price) * close_qty
               if entry_price and current_price and side=="long"
               else (entry_price - current_price) * close_qty
               if entry_price and current_price else 0)

        send_telegram(
            f"📤 <b>POSITION CLOSED</b>\n"
            f"📌 {symbol} | Qty: {close_qty}\n"
            f"💰 P&L: <b>${pnl:+.2f}</b>"
        )

        return jsonify({"success": True, "result": result, "pnl": round(pnl, 2)})
    except Exception as ex:
        return jsonify({"success": False, "error": str(ex)}), 500

# ── Close ALL ─────────────────────────────────────────────────────────────────
@dashboard_bp.route("/api/close_all", methods=["POST"])
def api_close_all():
    e = _auth()
    if e: return e
    try:
        positions = alpaca.get_positions()
        for p in positions:
            sym    = p["symbol"]
            qty    = float(p["qty"])
            entry  = float(p.get("avg_entry_price", 0))
            curr   = float(p.get("current_price", 0))
            side   = "long" if qty > 0 else "short"
            log_closed_position(sym, abs(qty), entry, curr, side)
        result = alpaca.close_all_positions()
        send_telegram("🚨 <b>ALL POSITIONS CLOSED</b> via dashboard")
        return jsonify({"success": True, "result": result})
    except Exception as ex:
        return jsonify({"success": False, "error": str(ex)}), 500

# ── Kill switch ───────────────────────────────────────────────────────────────
@dashboard_bp.route("/api/kill_switch", methods=["POST"])
def api_kill_switch():
    e = _auth()
    if e: return e
    state = request.json.get("enabled", True)
    with open(".kill_switch", "w") as f:
        f.write("1" if state else "0")
    Config.KILL_SWITCH = state
    alert_kill_switch(state)
    return jsonify({"success": True, "kill_switch": state})

# ── Excel export ──────────────────────────────────────────────────────────────
@dashboard_bp.route("/api/export_excel")
def api_export_excel():
    e = _auth()
    if e: return e
    try:
        data = export_trades_excel()
        return send_file(
            io.BytesIO(data),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"trades_{__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        )
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500

# ── Telegram test ─────────────────────────────────────────────────────────────
@dashboard_bp.route("/api/test_telegram", methods=["POST"])
def api_test_telegram():
    e = _auth()
    if e: return e
    ok = send_telegram("✅ <b>Telegram test message</b>\nYour trading bot is connected!")
    return jsonify({"success": ok, "message": "Sent!" if ok else "Failed — check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID"})

# ── Analyzer ──────────────────────────────────────────────────────────────────
@dashboard_bp.route("/api/analyze", methods=["POST"])
def api_analyze():
    e = _auth()
    if e: return e
    data      = request.json or {}
    symbols   = [s.strip().upper() for s in data.get("symbols", []) if s.strip()]
    timeframes= data.get("timeframes", ["15m","1h","1D"])

    if not symbols:
        return jsonify({"error": "No symbols provided"}), 400
    if len(symbols) > 10:
        return jsonify({"error": "Max 10 symbols at once"}), 400

    from core.analyzer import analyze_symbol
    results = []
    for sym in symbols:
        try:
            result = analyze_symbol(sym, timeframes)
            results.append(result)
        except Exception as ex:
            results.append({"symbol": sym, "error": str(ex)})

    return jsonify({"results": results, "timeframes": timeframes})

# ── Research: Institutional ───────────────────────────────────────────────────
@dashboard_bp.route("/api/research/institutional", methods=["GET"])
def api_research_institutional():
    e = _auth()
    if e: return e
    try:
        from research.sec_filings import get_institutional_tracker
        return jsonify(get_institutional_tracker())
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500

# ── Research: Earnings Whiplash ───────────────────────────────────────────────
@dashboard_bp.route("/api/research/earnings", methods=["GET"])
def api_research_earnings():
    e = _auth()
    if e: return e
    try:
        from research.earnings import get_earnings_whiplash
        return jsonify(get_earnings_whiplash(max_stocks=50))
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500

# ── Research: Sector Rotation ─────────────────────────────────────────────────
@dashboard_bp.route("/api/research/sectors", methods=["GET"])
def api_research_sectors():
    e = _auth()
    if e: return e
    try:
        from research.sector_rotation import get_sector_rotation
        return jsonify(get_sector_rotation())
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500

# ── Research: Insider + Options ───────────────────────────────────────────────
@dashboard_bp.route("/api/research/insider", methods=["POST"])
def api_research_insider():
    e = _auth()
    if e: return e
    try:
        data    = request.json or {}
        symbols = data.get("symbols", None)
        from research.insider_flow import get_confluence_stocks
        return jsonify(get_confluence_stocks(symbols))
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500

# ── Health ────────────────────────────────────────────────────────────────────
@dashboard_bp.route("/health")
def health():
    return jsonify({"status":"ok"})
