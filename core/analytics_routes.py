"""
core/analytics_routes.py — v9
Institutional-grade analytics from Alpaca closed orders.
Features:
- Pulls LIVE from Alpaca /v2/orders (all filled orders, any date range)
- Fallback to local DB closed_positions
- Date range filter, per-symbol breakdown, equity curve
- Portfolio allocation pie data, drawdown, Sharpe ratio, holding time
"""
from flask import Blueprint, jsonify, session, request
from core.database import get_conn, _close, get_closed_positions
from core.logger import get_logger
from core.config import Config
from collections import defaultdict
import requests
from datetime import datetime, timezone, timedelta
import math

logger = get_logger(__name__)
analytics_bp = Blueprint("analytics", __name__)

def _auth():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    return None

def _alpaca_headers():
    return {
        "APCA-API-KEY-ID":     Config.ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": Config.ALPACA_SECRET_KEY,
    }

def _fetch_alpaca_orders(date_from: str = None, date_to: str = None) -> list:
    """
    Pull ALL filled orders from Alpaca, optionally filtered by date range.
    date_from / date_to: ISO date strings 'YYYY-MM-DD'
    Returns list of normalised trade dicts.

    FIX: Alpaca defaults to ~7 days when no 'after' param is sent.
    We always send 'after' (default: account epoch 2015-01-01) so we get
    the full history. We also paginate via 'after_id' to bypass the 500 limit.
    """
    try:
        base = Config.ALPACA_BASE_URL
        url  = f"{base}/v2/orders"

        # Default to full history if no date range given
        after_ts = f"{date_from}T00:00:00Z" if date_from else "2015-01-01T00:00:00Z"
        until_ts = f"{date_to}T23:59:59Z"   if date_to   else None

        all_orders = []
        page_token = None

        while True:
            params = {
                "status":    "all",
                "limit":     500,
                "direction": "asc",
                "after":     after_ts,
            }
            if until_ts:
                params["until"] = until_ts
            if page_token:
                params["after"] = page_token  # paginate from last order time

            r = requests.get(url, headers=_alpaca_headers(), params=params, timeout=15)
            r.raise_for_status()
            batch = r.json()
            if not batch:
                break
            all_orders.extend(batch)

            # If we got a full page, paginate using the last order's filled_at
            if len(batch) == 500:
                last_ts = batch[-1].get("filled_at") or batch[-1].get("submitted_at") or ""
                if last_ts and last_ts != page_token:
                    page_token = last_ts
                    continue
            break

        trades = []
        for o in all_orders:
            if o.get("status") not in ("filled", "partially_filled"):
                continue
            sym   = o.get("symbol", "")
            side  = o.get("side", "")
            qty   = float(o.get("filled_qty") or o.get("qty") or 0)
            price = float(o.get("filled_avg_price") or 0)
            ts    = o.get("filled_at") or o.get("submitted_at") or ""
            if not sym or qty == 0:
                continue
            trades.append({
                "symbol":    sym,
                "side":      side,
                "qty":       qty,
                "price":     price,
                "timestamp": ts[:19].replace("T", " "),
                "date":      ts[:10],
                "alpaca_id": o.get("id", ""),
                "source":    "alpaca",
            })

        logger.info(f"Fetched {len(trades)} filled orders from Alpaca (scanned {len(all_orders)} total)")
        return trades
    except Exception as e:
        logger.warning(f"Alpaca orders fetch failed: {e}")
        return []

def _build_round_trips(trades: list) -> list:
    """
    Match buy→sell pairs per symbol into closed round-trip P&L records.
    Uses FIFO matching.
    """
    # Group by symbol, separate buys and sells
    buys  = defaultdict(list)
    sells = defaultdict(list)
    for t in trades:
        if t["side"] == "buy":
            buys[t["symbol"]].append(t)
        else:
            sells[t["symbol"]].append(t)

    round_trips = []
    for sym in set(list(buys.keys()) + list(sells.keys())):
        bq = list(buys[sym])   # FIFO queue
        sq = list(sells[sym])
        for sell in sq:
            remaining_sell_qty = sell["qty"]
            while remaining_sell_qty > 0 and bq:
                buy = bq[0]
                matched_qty = min(buy["qty"], remaining_sell_qty)
                pnl     = (sell["price"] - buy["price"]) * matched_qty
                pnl_pct = ((sell["price"] - buy["price"]) / buy["price"] * 100) if buy["price"] > 0 else 0
                round_trips.append({
                    "symbol":      sym,
                    "side":        "long",
                    "qty":         matched_qty,
                    "entry_price": buy["price"],
                    "exit_price":  sell["price"],
                    "pnl":         round(pnl, 2),
                    "pnl_pct":     round(pnl_pct, 2),
                    "entry_date":  buy["date"],
                    "exit_date":   sell["date"],
                    "closed_at":   sell["timestamp"],
                    "source":      sell.get("source", "alpaca"),
                })
                buy["qty"] -= matched_qty
                remaining_sell_qty -= matched_qty
                if buy["qty"] <= 0:
                    bq.pop(0)
    return sorted(round_trips, key=lambda x: x["closed_at"])

def _compute_analytics(rows: list) -> dict:
    """Full institutional-grade analytics from a list of closed trade rows."""
    if not rows:
        return {
            "symbols": [], "totals": {}, "equity_curve": [],
            "allocation_pie": [], "monthly_pnl": [], "drawdown": [],
            "raw_count": 0
        }

    by_symbol = defaultdict(lambda: {
        "trades": 0, "wins": 0, "losses": 0,
        "total_pnl": 0.0, "win_pnl": 0.0, "loss_pnl": 0.0,
        "max_win": 0.0, "max_loss": 0.0,
        "total_investment": 0.0,
    })
    timeline = []

    for r in rows:
        sym  = r.get("symbol", "UNKNOWN")
        pnl  = float(r.get("pnl") or 0)
        qty  = float(r.get("qty") or 0)
        ep   = float(r.get("entry_price") or 0)
        s    = by_symbol[sym]
        s["trades"]           += 1
        s["total_pnl"]        += pnl
        s["total_investment"] += qty * ep
        if pnl > 0:
            s["wins"]    += 1;  s["win_pnl"] += pnl
            s["max_win"]  = max(s["max_win"], pnl)
        else:
            s["losses"]  += 1;  s["loss_pnl"] += pnl
            s["max_loss"] = min(s["max_loss"], pnl)
        date_str = str(r.get("closed_at", r.get("exit_date", "")))[:10]
        timeline.append({"date": date_str, "pnl": pnl, "symbol": sym,
                          "qty": qty, "entry_price": ep})

    # Per-symbol output
    symbols_out = []
    for sym, s in sorted(by_symbol.items(), key=lambda x: -x[1]["trades"]):
        wr    = round(s["wins"] / s["trades"] * 100, 1) if s["trades"] > 0 else 0
        aw    = round(s["win_pnl"]  / s["wins"],   2) if s["wins"]   > 0 else 0
        al    = round(s["loss_pnl"] / s["losses"], 2) if s["losses"] > 0 else 0
        pf    = round(abs(s["win_pnl"] / s["loss_pnl"]), 2) if s["loss_pnl"] != 0 else 99.0
        roi   = round(s["total_pnl"] / s["total_investment"] * 100, 2) if s["total_investment"] > 0 else 0
        symbols_out.append({
            "symbol":        sym,
            "trades":        s["trades"],
            "wins":          s["wins"],
            "losses":        s["losses"],
            "win_rate":      wr,
            "total_pnl":     round(s["total_pnl"], 2),
            "avg_win":       aw,
            "avg_loss":      al,
            "profit_factor": pf,
            "max_win":       round(s["max_win"],  2),
            "max_loss":      round(s["max_loss"], 2),
            "total_investment": round(s["total_investment"], 2),
            "roi_pct":       roi,
        })

    # Overall totals
    n         = len(rows)
    wins      = sum(1 for r in rows if float(r.get("pnl") or 0) > 0)
    all_pnl   = sum(float(r.get("pnl") or 0) for r in rows)
    win_pnl   = sum(float(r.get("pnl") or 0) for r in rows if float(r.get("pnl") or 0) > 0)
    loss_pnl  = sum(float(r.get("pnl") or 0) for r in rows if float(r.get("pnl") or 0) <= 0)
    total_inv = sum(float(r.get("qty") or 0) * float(r.get("entry_price") or 0) for r in rows)
    pnl_list  = [float(r.get("pnl") or 0) for r in rows]
    avg_pnl   = all_pnl / n if n > 0 else 0
    var       = sum((x - avg_pnl)**2 for x in pnl_list) / n if n > 0 else 0
    sharpe    = round(avg_pnl / math.sqrt(var) if var > 0 else 0, 2)

    totals = {
        "total_trades":    n,
        "total_wins":      wins,
        "total_losses":    n - wins,
        "win_rate":        round(wins / n * 100, 1) if n else 0,
        "total_pnl":       round(all_pnl, 2),
        "profit_factor":   round(abs(win_pnl / loss_pnl), 2) if loss_pnl != 0 else 99.0,
        "avg_trade_pnl":   round(avg_pnl, 2),
        "best_trade":      round(max(pnl_list, default=0), 2),
        "worst_trade":     round(min(pnl_list, default=0), 2),
        "total_investment":round(total_inv, 2),
        "overall_roi_pct": round(all_pnl / total_inv * 100, 2) if total_inv > 0 else 0,
        "sharpe_approx":   sharpe,
        "expectancy":      round(avg_pnl, 2),
    }

    # Equity curve + drawdown
    timeline_sorted = sorted(timeline, key=lambda x: x["date"])
    cumulative = 0
    peak       = 0
    equity_curve = []
    drawdown     = []
    for t in timeline_sorted:
        cumulative += t["pnl"]
        peak = max(peak, cumulative)
        dd   = round(cumulative - peak, 2)
        equity_curve.append({
            "date":           t["date"],
            "cumulative_pnl": round(cumulative, 2),
            "trade_pnl":      round(t["pnl"], 2),
            "symbol":         t["symbol"],
        })
        drawdown.append({"date": t["date"], "drawdown": dd})

    max_dd = round(min((x["drawdown"] for x in drawdown), default=0), 2)
    totals["max_drawdown"] = max_dd

    # Monthly P&L
    monthly = defaultdict(float)
    for t in timeline_sorted:
        mo = t["date"][:7]  # YYYY-MM
        monthly[mo] += t["pnl"]
    monthly_pnl = [{"month": mo, "pnl": round(pnl, 2)}
                   for mo, pnl in sorted(monthly.items())]

    # Portfolio allocation pie (total $ invested per symbol as % of total)
    total_all_inv = sum(s["total_investment"] for s in symbols_out) or 1
    allocation_pie = [
        {
            "symbol":   s["symbol"],
            "invested": round(s["total_investment"], 2),
            "pct":      round(s["total_investment"] / total_all_inv * 100, 1),
            "pnl":      s["total_pnl"],
            "roi_pct":  s["roi_pct"],
        }
        for s in symbols_out
    ]

    return {
        "symbols":       symbols_out,
        "totals":        totals,
        "equity_curve":  equity_curve,
        "drawdown":      drawdown,
        "allocation_pie":allocation_pie,
        "monthly_pnl":   monthly_pnl,
        "raw_count":     n,
    }


@analytics_bp.route("/api/analytics/summary", methods=["GET", "POST"])
def analytics_summary():
    e = _auth()
    if e: return e

    body      = request.get_json(silent=True) or {}
    date_from = body.get("date_from") or request.args.get("date_from")
    date_to   = body.get("date_to")   or request.args.get("date_to")
    source    = body.get("source", "auto")  # "alpaca", "db", "auto"

    rows = []

    # Try Alpaca first
    if source in ("alpaca", "auto"):
        alpaca_trades = _fetch_alpaca_orders(date_from, date_to)
        if alpaca_trades:
            rows = _build_round_trips(alpaca_trades)

    # Fall back to local DB
    if not rows:
        db_rows = get_closed_positions(limit=2000)
        if date_from or date_to:
            df = date_from or "2000-01-01"
            dt = date_to   or "2099-12-31"
            db_rows = [r for r in db_rows if df <= str(r.get("closed_at",""))[:10] <= dt]
        rows = db_rows

    if not rows:
        return jsonify({
            "symbols": [], "totals": {}, "equity_curve": [],
            "allocation_pie": [], "monthly_pnl": [], "drawdown": [],
            "raw_count": 0, "source": "empty"
        })

    result = _compute_analytics(rows)
    result["source"] = rows[0].get("source", "db") if rows else "empty"
    result["date_from"] = date_from
    result["date_to"]   = date_to
    return jsonify(result)


@analytics_bp.route("/api/analytics/symbol/<symbol>", methods=["GET"])
def analytics_symbol_detail(symbol):
    e = _auth()
    if e: return e
    date_from = request.args.get("date_from")
    date_to   = request.args.get("date_to")
    alpaca_trades = _fetch_alpaca_orders(date_from, date_to)
    if alpaca_trades:
        trips = _build_round_trips(alpaca_trades)
        sym_rows = [r for r in trips if r.get("symbol","").upper() == symbol.upper()]
    else:
        db_rows  = get_closed_positions(limit=2000)
        sym_rows = [r for r in db_rows if r.get("symbol","").upper() == symbol.upper()]
    return jsonify({"symbol": symbol.upper(), "trades": sym_rows})


@analytics_bp.route("/api/analytics/debug", methods=["GET"])
def analytics_debug():
    """Debug endpoint — shows raw Alpaca order count + sample. Remove in production."""
    e = _auth()
    if e: return e
    try:
        base = Config.ALPACA_BASE_URL
        headers = _alpaca_headers()
        # Quick account check
        acct = requests.get(f"{base}/v2/account", headers=headers, timeout=10)
        # Raw orders (last 30 days)
        orders = requests.get(f"{base}/v2/orders",
                              headers=headers,
                              params={"status": "all", "limit": 10, "direction": "desc"},
                              timeout=10)
        return jsonify({
            "alpaca_base_url": base,
            "has_api_key":     bool(Config.ALPACA_API_KEY),
            "account_status":  acct.status_code,
            "account_ok":      acct.ok,
            "orders_status":   orders.status_code,
            "orders_sample":   orders.json()[:3] if orders.ok else orders.text[:300],
        })
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500
