"""
MirrorFish AI Engine — Multi-LLM market prediction layer
Supports: Groq (free), OpenRouter (free tier), Hugging Face (free)
Runs fully online on Railway — no local GPU needed.
"""

import os
import json
import requests
import time
from datetime import datetime
import pytz
from core.logger import get_logger

logger = get_logger(__name__)

# ── Provider registry ──────────────────────────────────────────────────────────
PROVIDERS = {
    "groq": {
        "name": "Groq (free)",
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "env_key": "GROQ_API_KEY",
        "models": [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "mixtral-8x7b-32768",
            "gemma2-9b-it",
        ],
        "default_model": "llama-3.3-70b-versatile",
        "headers_extra": {},
        "free": True,
    },
    "openrouter": {
        "name": "OpenRouter (free tier)",
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "env_key": "OPENROUTER_API_KEY",
        "models": [
            "meta-llama/llama-3.3-70b-instruct:free",
            "mistralai/mistral-7b-instruct:free",
            "google/gemma-2-9b-it:free",
            "microsoft/phi-3-mini-128k-instruct:free",
        ],
        "default_model": "meta-llama/llama-3.3-70b-instruct:free",
        "headers_extra": {
            "HTTP-Referer": "https://optitrade-ai.railway.app",
            "X-Title": "OptiTrade MirrorFish",
        },
        "free": True,
    },
    "huggingface": {
        "name": "HuggingFace (free)",
        "url": "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.3",
        "env_key": "HUGGINGFACE_API_KEY",
        "models": ["mistralai/Mistral-7B-Instruct-v0.3"],
        "default_model": "mistralai/Mistral-7B-Instruct-v0.3",
        "headers_extra": {},
        "free": True,
        "hf_mode": True,
    },
}


def _get_available_provider():
    """Return first provider that has an API key configured."""
    preferred_order = ["groq", "openrouter", "huggingface"]
    for name in preferred_order:
        p = PROVIDERS[name]
        if os.environ.get(p["env_key"]):
            return name, p
    return None, None


def _call_openai_compat(provider_cfg, model, messages, max_tokens=1024, temperature=0.3):
    """Call any OpenAI-compatible endpoint."""
    api_key = os.environ.get(provider_cfg["env_key"], "")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        **provider_cfg.get("headers_extra", {}),
    }
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    resp = requests.post(provider_cfg["url"], headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def _call_hf(provider_cfg, prompt, max_tokens=512):
    """Call HuggingFace Inference API."""
    api_key = os.environ.get(provider_cfg["env_key"], "")
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {
        "inputs": prompt,
        "parameters": {"max_new_tokens": max_tokens, "temperature": 0.3},
    }
    resp = requests.post(provider_cfg["url"], headers=headers, json=payload, timeout=45)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, list):
        return data[0].get("generated_text", "")
    return str(data)


def get_provider_status():
    """Return dict of all providers and their config status."""
    result = {}
    for name, cfg in PROVIDERS.items():
        key = os.environ.get(cfg["env_key"])
        result[name] = {
            "name": cfg["name"],
            "configured": bool(key),
            "key_hint": f"...{key[-4:]}" if key else "not set",
            "models": cfg["models"],
            "env_var": cfg["env_key"],
        }
    return result


# ── MirrorFish prediction functions ───────────────────────────────────────────

SYSTEM_PROMPT = """You are MirrorFish, an AI market analyst assistant integrated into OptiTrade, 
an algorithmic trading system. You analyze technical and fundamental data and give structured, 
concise trading insights. You always respond in valid JSON when asked.
Never give financial advice; always note that analysis is for educational purposes only."""


def analyze_symbol(symbol: str, market_data: dict, signals: dict) -> dict:
    """
    Run MirrorFish analysis on a symbol.
    market_data: {"price": float, "change_pct": float, "volume": int, "rsi": float,
                  "macd_signal": str, "ema50": float, "vwap": float, "bb_position": str}
    signals: {"overall": str, "timeframes": {...}}
    Returns: {"prediction": str, "confidence": int, "reasoning": str,
              "key_levels": {"support": float, "resistance": float},
              "sentiment": str, "risk_note": str, "provider": str}
    """
    provider_name, provider_cfg = _get_available_provider()
    if not provider_cfg:
        return {
            "error": "No LLM provider configured. Add GROQ_API_KEY, OPENROUTER_API_KEY, or HUGGINGFACE_API_KEY to Railway env vars.",
            "prediction": "NEUTRAL",
            "confidence": 0,
            "reasoning": "No AI provider available.",
            "key_levels": {"support": 0, "resistance": 0},
            "sentiment": "unknown",
            "risk_note": "Configure an API key to enable MirrorFish.",
            "provider": "none",
        }

    prompt_data = f"""
Symbol: {symbol}
Current Price: ${market_data.get('price', 'N/A')}
Change: {market_data.get('change_pct', 'N/A')}%
Volume: {market_data.get('volume', 'N/A')}
RSI: {market_data.get('rsi', 'N/A')}
MACD Signal: {market_data.get('macd_signal', 'N/A')}
EMA50: {market_data.get('ema50', 'N/A')}
VWAP: {market_data.get('vwap', 'N/A')}
BB Position: {market_data.get('bb_position', 'N/A')}
Overall Signal: {signals.get('overall', 'N/A')}
Timeframe Signals: {json.dumps(signals.get('timeframes', {}))}
"""

    user_msg = f"""Analyze this stock and respond ONLY with valid JSON (no markdown, no explanation outside JSON):

{prompt_data}

Required JSON format:
{{
  "prediction": "BULLISH" or "BEARISH" or "NEUTRAL",
  "confidence": integer 0-100,
  "reasoning": "2-3 sentence explanation",
  "key_levels": {{"support": float, "resistance": float}},
  "sentiment": "strong_bull" or "bull" or "neutral" or "bear" or "strong_bear",
  "risk_note": "one sentence risk warning",
  "short_term_bias": "UP" or "DOWN" or "SIDEWAYS",
  "suggested_action": "BUY" or "SELL" or "HOLD" or "WATCH"
}}"""

    try:
        if provider_cfg.get("hf_mode"):
            raw = _call_hf(provider_cfg, SYSTEM_PROMPT + "\n\n" + user_msg)
            # Try to extract JSON from HF response
            start = raw.find("{")
            end = raw.rfind("}") + 1
            raw = raw[start:end] if start != -1 else "{}"
        else:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ]
            model = provider_cfg["default_model"]
            raw = _call_openai_compat(provider_cfg, model, messages, max_tokens=512)
            # Strip markdown fences if present
            if "```" in raw:
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]

        result = json.loads(raw)
        result["provider"] = provider_cfg["name"]
        result["model"] = provider_cfg["default_model"]
        result["timestamp_utc"] = datetime.utcnow().isoformat()
        return result

    except json.JSONDecodeError as e:
        logger.error(f"MirrorFish JSON parse error: {e} | raw: {raw[:200]}")
        return {
            "prediction": "NEUTRAL",
            "confidence": 0,
            "reasoning": f"LLM returned non-JSON response. Raw: {str(raw)[:100]}",
            "key_levels": {"support": 0, "resistance": 0},
            "sentiment": "unknown",
            "risk_note": "Parse error — check provider response.",
            "provider": provider_cfg["name"],
            "error": str(e),
        }
    except Exception as e:
        logger.error(f"MirrorFish error: {e}")
        return {
            "prediction": "NEUTRAL",
            "confidence": 0,
            "reasoning": str(e),
            "key_levels": {"support": 0, "resistance": 0},
            "sentiment": "unknown",
            "risk_note": "API error.",
            "provider": provider_cfg.get("name", "unknown"),
            "error": str(e),
        }


def analyze_portfolio(positions: list, closed_trades: list) -> dict:
    """
    Analyze overall portfolio health using MirrorFish.
    positions: list of {symbol, qty, market_value, unrealized_plpc}
    closed_trades: last 20 closed trades with P&L
    Returns portfolio-level AI commentary.
    """
    provider_name, provider_cfg = _get_available_provider()
    if not provider_cfg:
        return {"error": "No LLM provider configured.", "summary": "Configure an API key.", "provider": "none"}

    pos_summary = "\n".join(
        [f"  {p.get('symbol')}: {p.get('qty')} shares, ${p.get('market_value',0):.2f}, PnL {p.get('unrealized_plpc',0):.2f}%"
         for p in positions[:10]]
    ) or "  (no open positions)"

    wins = [t for t in closed_trades if float(t.get("pnl_dollar", 0)) > 0]
    losses = [t for t in closed_trades if float(t.get("pnl_dollar", 0)) <= 0]
    total_pnl = sum(float(t.get("pnl_dollar", 0)) for t in closed_trades)
    win_rate = round(len(wins) / len(closed_trades) * 100, 1) if closed_trades else 0

    user_msg = f"""Analyze this trading portfolio and respond ONLY with valid JSON:

Open Positions:
{pos_summary}

Recent Performance ({len(closed_trades)} closed trades):
  Win rate: {win_rate}%
  Total P&L: ${total_pnl:.2f}
  Wins: {len(wins)}, Losses: {len(losses)}
  Recent symbols traded: {list(set(t.get('symbol','') for t in closed_trades[:10]))}

Required JSON:
{{
  "portfolio_health": "STRONG" or "HEALTHY" or "MIXED" or "WEAK",
  "summary": "2-3 sentence portfolio commentary",
  "concentration_risk": "brief note on position concentration",
  "strategy_assessment": "is the algo strategy working? brief assessment",
  "top_suggestion": "one actionable suggestion",
  "win_rate_comment": "brief comment on {win_rate}% win rate"
}}"""

    try:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]
        model = provider_cfg["default_model"]
        raw = _call_openai_compat(provider_cfg, model, messages, max_tokens=400)
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw)
        result["provider"] = provider_cfg["name"]
        return result
    except Exception as e:
        logger.error(f"MirrorFish portfolio error: {e}")
        return {
            "portfolio_health": "UNKNOWN",
            "summary": str(e),
            "provider": provider_cfg.get("name", "unknown"),
            "error": str(e),
        }


def chat(message: str, context: dict = None) -> str:
    """
    Free-form chat with MirrorFish for market questions.
    context: optional dict with account/market info to inject.
    Returns plain text response.
    """
    provider_name, provider_cfg = _get_available_provider()
    if not provider_cfg:
        return "MirrorFish is not configured. Please add GROQ_API_KEY (free at console.groq.com) to your Railway environment variables."

    ctx_str = ""
    if context:
        ctx_str = f"\n\nCurrent context: {json.dumps(context, default=str)[:500]}"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT + ctx_str},
        {"role": "user", "content": message},
    ]

    try:
        if provider_cfg.get("hf_mode"):
            return _call_hf(provider_cfg, SYSTEM_PROMPT + "\n\nUser: " + message)
        model = provider_cfg["default_model"]
        return _call_openai_compat(provider_cfg, model, messages, max_tokens=600, temperature=0.5)
    except Exception as e:
        logger.error(f"MirrorFish chat error: {e}")
        return f"MirrorFish error: {str(e)}"
