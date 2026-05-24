"""
MirrorFish routes — /api/mirrorfish/*
All endpoints require dashboard login session.
"""

from flask import Blueprint, request, jsonify, session
from mirrorfish.engine import analyze_symbol, analyze_portfolio, chat, get_provider_status
from core.database import get_closed_positions
from core.logger import get_logger

logger = get_logger(__name__)
mirrorfish_bp = Blueprint("mirrorfish", __name__)


def _require_login():
    return session.get("logged_in") is True


@mirrorfish_bp.route("/api/mirrorfish/status", methods=["GET"])
def mf_status():
    if not _require_login():
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(get_provider_status())


@mirrorfish_bp.route("/api/mirrorfish/analyze", methods=["POST"])
def mf_analyze():
    """Analyze a symbol with MirrorFish AI."""
    if not _require_login():
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json() or {}
    symbol = data.get("symbol", "").upper().strip()
    if not symbol:
        return jsonify({"error": "symbol required"}), 400
    market_data = data.get("market_data", {})
    signals = data.get("signals", {})
    result = analyze_symbol(symbol, market_data, signals)
    return jsonify(result)


@mirrorfish_bp.route("/api/mirrorfish/portfolio", methods=["POST"])
def mf_portfolio():
    """Analyze full portfolio with MirrorFish AI."""
    if not _require_login():
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json() or {}
    positions = data.get("positions", [])
    closed = get_closed_positions(limit=30)
    result = analyze_portfolio(positions, closed)
    return jsonify(result)


@mirrorfish_bp.route("/api/mirrorfish/chat", methods=["POST"])
def mf_chat():
    """Free-form market chat with MirrorFish."""
    if not _require_login():
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json() or {}
    message = data.get("message", "").strip()
    if not message:
        return jsonify({"error": "message required"}), 400
    context = data.get("context", {})
    response = chat(message, context)
    return jsonify({"response": response})
