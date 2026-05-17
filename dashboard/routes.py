"""
dashboard/routes.py — All dashboard routes (v4 complete)
"""
from flask import Blueprint, render_template, jsonify, request, session, redirect, url_for, send_file
import io, json
from core.database import (get_recent_trades, get_recent_webhooks, get_closed_positions,
                            get_closed_summary, log_closed_position)
from core.config import Config
from core.telegram import send_telegram, alert_kill_switch
from core.excel_export import export_trades_excel
from brokers.alpaca_adapter import AlpacaAdapter
from core.logger import get_logger

logger = get_logger(__name__)
dashboard_bp = Blueprint("dashboard", __name__)
alpaca = AlpacaAdapter()

def _auth():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    return None

@dashboard_bp.route("/")
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

@dashboard_bp.route("/api/account")
def api_account():
    e = _auth(); 
    if e: return e
    try:
        return jsonify({"account": alpaca.get_account(), "positions": alpaca.get_positions()})
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500

@dashboard_bp.route("/api/trades")
def api_trades():
    e = _auth(); 
    if e: return e
    return jsonify(get_recent_trades(50))

@dashboard_bp.route("/api/webhooks")
def api_webhooks():
    e = _auth(); 
    if e: return e
    return jsonify(get_recent_webhooks(20))

@dashboard_bp.route("/api/closed_positions")
def api_closed_positions():
    e = _auth(); 
    if e: return e
    return jsonify({"positions": get_closed_positions(100), "summary": get_closed_summary()})

@dashboard_bp.route("/api/close_position", methods=["POST"])
def api_close_position():
    e = _auth(); 
    if e: return e
    data   = request.json or {}
    symbol = data.get("symbol","").upper().strip()
    qty    = data.get("qty", None)
    if not symbol:
        return jsonify({"success": False, "error": "Symbol required"}), 400
    try:
        pos          = alpaca.get_position(symbol)
        entry_price  = float(pos.get("avg_entry_price", 0)) if pos else None
        current_price= float(pos.get("current_price",  0)) if pos else None
        pos_qty      = float(pos.get("qty", 0))             if pos else 0
        side         = "long" if pos_qty > 0 else "short"

        if qty and float(qty) < abs(pos_qty):
            close_qty  = float(qty)
            order_side = "sell" if pos_qty > 0 else "buy"
            result     = alpaca.place_market_order(symbol, order_side, close_qty)
        else:
            result    = alpaca.close_position(symbol)
            close_qty = abs(pos_qty)

        if entry_price and current_price:
            log_closed_position(symbol, close_qty, entry_price, current_price, side,
                                alpaca_id=result.get("id") if result else None)
        pnl = ((current_price - entry_price) * close_qty if side == "long"
               else (entry_price - current_price) * close_qty) if entry_price and current_price else 0
        send_telegram(f"📤 <b>CLOSED {symbol}</b> Qty:{close_qty} P&L:<b>${pnl:+.2f}</b>")
        return jsonify({"success": True, "pnl": round(pnl,2)})
    except Exception as ex:
        return jsonify({"success": False, "error": str(ex)}), 500

@dashboard_bp.route("/api/close_all", methods=["POST"])
def api_close_all():
    e = _auth(); 
    if e: return e
    try:
        positions = alpaca.get_positions()
        for p in positions:
            sym  = p["symbol"]
            qty  = float(p["qty"])
            en   = float(p.get("avg_entry_price",0))
            cu   = float(p.get("current_price",0))
            side = "long" if qty > 0 else "short"
            log_closed_position(sym, abs(qty), en, cu, side)
        result = alpaca.close_all_positions()
        send_telegram("🚨 <b>ALL POSITIONS CLOSED</b> via dashboard")
        return jsonify({"success": True})
    except Exception as ex:
        return jsonify({"success": False, "error": str(ex)}), 500

@dashboard_bp.route("/api/kill_switch", methods=["POST"])
def api_kill_switch():
    e = _auth(); 
    if e: return e
    state = request.json.get("enabled", True)
    with open(".kill_switch","w") as f:
        f.write("1" if state else "0")
    Config.KILL_SWITCH = state
    alert_kill_switch(state)
    return jsonify({"success": True, "kill_switch": state})

@dashboard_bp.route("/api/export_excel")
def api_export_excel():
    e = _auth(); 
    if e: return e
    try:
        data = export_trades_excel()
        from datetime import datetime
        return send_file(io.BytesIO(data),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"trades_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx")
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500

@dashboard_bp.route("/api/test_telegram", methods=["POST"])
def api_test_telegram():
    e = _auth(); 
    if e: return e
    ok = send_telegram("✅ <b>Telegram connected!</b>\nYour OptiTrade bot is online.")
    return jsonify({"success": ok, "message": "Sent!" if ok else "Failed — check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID"})

# ── Analyzer Pro ──────────────────────────────────────────────────────────────
@dashboard_bp.route("/api/analyze", methods=["POST"])
def api_analyze():
    e = _auth(); 
    if e: return e
    data       = request.json or {}
    symbols    = [s.strip().upper() for s in data.get("symbols",[]) if s.strip()][:10]
    timeframes = data.get("timeframes", ["15m","1h","1D"])
    if not symbols:
        return jsonify({"error":"No symbols"}), 400
    try:
        from core.analyzer import analyze_multiple
        results = analyze_multiple(symbols, timeframes)
        from core.market_data import data_source_status
        return jsonify({"results": results, "timeframes": timeframes,
                        "data_source": data_source_status()})
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500

# ── Stock chart data ──────────────────────────────────────────────────────────
@dashboard_bp.route("/api/chart_data", methods=["POST"])
def api_chart_data():
    e = _auth(); 
    if e: return e
    data   = request.json or {}
    symbol = data.get("symbol","").upper()
    period = data.get("period","3mo")
    try:
        from core.market_data import get_bars
        bars = get_bars(symbol, "1D")
        if not bars:
            return jsonify({"error": "No data"}), 404
        from datetime import datetime
        dates  = []
        for b in bars:
            try:
                dt = datetime.fromisoformat(b["t"].replace("Z","+00:00"))
                dates.append(dt.strftime("%m/%d"))
            except:
                dates.append("")
        return jsonify({
            "symbol":  symbol,
            "dates":   dates,
            "open":    [b.get("o") for b in bars],
            "high":    [b.get("h") for b in bars],
            "low":     [b.get("l") for b in bars],
            "close":   [b.get("c") for b in bars],
            "volume":  [b.get("v") for b in bars],
            "source":  bars[0].get("source","unknown") if bars else "unknown",
        })
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500

# ── Compare stocks ────────────────────────────────────────────────────────────
@dashboard_bp.route("/api/compare", methods=["POST"])
def api_compare():
    e = _auth(); 
    if e: return e
    data    = request.json or {}
    symbols = [s.strip().upper() for s in data.get("symbols",[]) if s.strip()][:8]
    period  = data.get("period","3mo")
    if not symbols:
        return jsonify({"error":"No symbols"}), 400
    try:
        from core.market_data import get_bars
        from datetime import datetime
        result = {}
        for sym in symbols:
            bars = get_bars(sym, "1D")
            if not bars: continue
            dates, closes = [], []
            for b in bars:
                try:
                    dt = datetime.fromisoformat(b["t"].replace("Z","+00:00"))
                    dates.append(dt.strftime("%m/%d"))
                except:
                    dates.append("")
                closes.append(b.get("c"))
            base = next((c for c in closes if c), None)
            if not base: continue
            norm = [round((c/base-1)*100,2) if c else None for c in closes]
            result[sym] = {"dates":dates, "norm":norm, "closes":closes,
                           "source": bars[0].get("source","demo") if bars else "demo"}
        return jsonify(result)
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500

# ── Research routes (free data) ───────────────────────────────────────────────
@dashboard_bp.route("/api/research/institutional")
def api_research_institutional():
    e = _auth(); 
    if e: return e
    try:
        from research.sec_filings import get_institutional_tracker, analyze_institutional_momentum
        data      = get_institutional_tracker()
        momentum  = analyze_institutional_momentum(data)
        return jsonify({"funds": data, "momentum_stocks": momentum})
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500

@dashboard_bp.route("/api/research/earnings")
def api_research_earnings():
    e = _auth(); 
    if e: return e
    try:
        from research.earnings import get_earnings_whiplash
        return jsonify(get_earnings_whiplash(max_stocks=50))
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500

@dashboard_bp.route("/api/research/sectors")
def api_research_sectors():
    e = _auth(); 
    if e: return e
    try:
        from research.sector_rotation import get_sector_rotation
        return jsonify(get_sector_rotation())
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500

@dashboard_bp.route("/api/research/insider", methods=["POST"])
def api_research_insider():
    e = _auth(); 
    if e: return e
    data    = request.json or {}
    symbols = data.get("symbols", None)
    try:
        from research.insider_flow import get_confluence_stocks
        return jsonify(get_confluence_stocks(symbols))
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500

# ── Telegram bot commands ─────────────────────────────────────────────────────
@dashboard_bp.route("/telegram/webhook", methods=["POST"])
def telegram_webhook():
    try:
        data    = request.get_json(force=True, silent=True) or {}
        msg     = data.get("message",{})
        text    = msg.get("text","").strip()
        chat_id = str(msg.get("chat",{}).get("id",""))
        if chat_id != Config.TELEGRAM_CHAT_ID:
            return jsonify({"ok":True})
        cmd = text.lower().split()[0] if text else ""
        if cmd in ["/positions","/pos"]:
            positions = alpaca.get_positions()
            if not positions:
                send_telegram("📊 <b>No open positions</b>")
            else:
                lines = ["📊 <b>Open Positions</b>\n━━━━━━━━━━━━━━"]
                for p in positions:
                    pnl = float(p.get("unrealized_pl",0))
                    pct = float(p.get("unrealized_plpc",0))*100
                    lines.append(f"📌 <b>{p['symbol']}</b> Qty:{p['qty']}\n"
                                 f"   P&L: <b>${pnl:+.2f} ({pct:+.2f}%)</b>")
                send_telegram("\n".join(lines))
        elif cmd in ["/pnl","/summary"]:
            from core.database import get_closed_summary
            s  = get_closed_summary()
            wr = (s["winners"]/s["total_trades"]*100) if s.get("total_trades") else 0
            send_telegram(f"📋 <b>P&L Summary</b>\n━━━━━━━━━━━━━━\n"
                          f"Trades:{s.get('total_trades',0)} WinRate:<b>{wr:.1f}%</b>\n"
                          f"Total P&L:<b>${s.get('total_pnl',0):+.2f}</b>")
        elif cmd in ["/account","/balance"]:
            acc = alpaca.get_account()
            pnl = float(acc.get("equity",0)) - float(acc.get("last_equity",0))
            send_telegram(f"💼 <b>Account</b>\n"
                          f"Portfolio: <b>${float(acc.get('portfolio_value',0)):,.2f}</b>\n"
                          f"Today P&L: <b>${pnl:+.2f}</b>")
        elif cmd == "/closeall":
            alpaca.close_all_positions()
            send_telegram("🚨 <b>ALL POSITIONS CLOSED</b>")
        elif cmd == "/close" and len(text.split()) > 1:
            sym = text.split()[1].upper()
            try:
                alpaca.close_position(sym)
                send_telegram(f"✅ <b>{sym}</b> closed.")
            except Exception as ex:
                send_telegram(f"❌ Failed: {str(ex)[:100]}")
        else:
            send_telegram("🤖 Commands: /positions /pnl /account /close AAPL /closeall")
        return jsonify({"ok":True})
    except Exception as ex:
        logger.error(f"Telegram webhook: {ex}")
        return jsonify({"ok":True})

@dashboard_bp.route("/health")
def health():
    return jsonify({"status":"ok","message":"Trading bot running"})

@dashboard_bp.route("/api/data_status")
def api_data_status():
    from core.market_data import data_source_status
    return jsonify(data_source_status())
