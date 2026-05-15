"""
core/analyzer.py — Analyzer Pro logic in Python
Replicates RSI, MACD, ADX, Bollinger, EMA50, VWAP across timeframes using yfinance
"""
import yfinance as yf
import pandas as pd
import numpy as np
from core.logger import get_logger

logger = get_logger(__name__)

TIMEFRAMES = {
    "5m":  {"period": "5d",  "interval": "5m"},
    "15m": {"period": "5d",  "interval": "15m"},
    "1h":  {"period": "30d", "interval": "1h"},
    "4h":  {"period": "60d", "interval": "1h"},   # aggregate 4 x 1h
    "1D":  {"period": "1y",  "interval": "1d"},
    "1W":  {"period": "5y",  "interval": "1wk"},
}

# ── RSI ───────────────────────────────────────────────────────────────────────
def calc_rsi(close: pd.Series, period=14) -> float:
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, np.nan)
    rsi   = 100 - (100 / (1 + rs))
    return round(float(rsi.iloc[-1]), 2) if not rsi.empty else None

def rsi_judgment(val):
    if val is None: return "N/A"
    if val >= 80:   return "Extreme Overbought"
    if val >= 70:   return "Overbought"
    if val >= 65:   return "Strong Up"
    if val >= 60:   return "Mod Up"
    if val >= 55:   return "Slightly Up"
    if val >= 45:   return "Neutral"
    if val >= 40:   return "Slightly Down"
    if val >= 35:   return "Mod Down"
    if val >= 30:   return "Oversold"
    return "Extreme Oversold"

# ── MACD ──────────────────────────────────────────────────────────────────────
def calc_macd(close: pd.Series):
    ema12  = close.ewm(span=12, adjust=False).mean()
    ema26  = close.ewm(span=26, adjust=False).mean()
    macd   = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist   = macd - signal
    return float(macd.iloc[-1]), float(signal.iloc[-1]), float(hist.iloc[-1])

def macd_judgment(macd, signal, hist):
    if macd is None: return "N/A"
    if macd > 0 and hist > 0 and macd > signal:  return "Strong Bull"
    if macd > 0 and hist > 0:                     return "Bull"
    if macd > 0 and hist < 0:                     return "Weakening Bull"
    if macd < 0 and hist < 0 and macd < signal:   return "Strong Bear"
    if macd < 0 and hist < 0:                     return "Bear"
    if macd < 0 and hist > 0:                     return "Weakening Bear"
    return "Neutral"

# ── ADX ───────────────────────────────────────────────────────────────────────
def calc_adx(high, low, close, period=14):
    tr   = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    atr  = tr.rolling(period).mean()
    dmp  = (high.diff().clip(lower=0))
    dmn  = (-low.diff().clip(upper=0))
    dmp[dmp < dmn] = 0
    dmn[dmn < dmp] = 0
    dip  = 100 * dmp.rolling(period).mean() / atr.replace(0, np.nan)
    din  = 100 * dmn.rolling(period).mean() / atr.replace(0, np.nan)
    dx   = 100 * (dip - din).abs() / (dip + din).replace(0, np.nan)
    adx  = dx.rolling(period).mean()
    return float(adx.iloc[-1]), float(dip.iloc[-1]), float(din.iloc[-1])

def adx_judgment(adx, dip, din):
    if adx is None: return "N/A"
    if adx >= 50 and dip > din:   return "Extreme Up"
    if adx >= 40 and dip > din:   return "Very Strong Up"
    if adx >= 30 and dip > din:   return "Strong Up"
    if adx >= 20 and dip > din:   return "Trending Up"
    if adx < 20:                   return "No Trend"
    if adx >= 20 and din > dip:    return "Trending Down"
    if adx >= 30 and din > dip:    return "Strong Down"
    if adx >= 40 and din > dip:    return "Very Strong Down"
    return "Extreme Down"

# ── Bollinger ─────────────────────────────────────────────────────────────────
def calc_bb(close: pd.Series, period=20, std=2):
    mid   = close.rolling(period).mean()
    sigma = close.rolling(period).std()
    upper = mid + std * sigma
    lower = mid - std * sigma
    pct_b = (close - lower) / (upper - lower).replace(0, np.nan)
    return float(upper.iloc[-1]), float(mid.iloc[-1]), float(lower.iloc[-1]), float(pct_b.iloc[-1])

def bb_judgment(pct_b):
    if pct_b is None: return "N/A"
    if pct_b >= 1.2:  return "Super Upper"
    if pct_b >= 1.0:  return "Extreme Upper"
    if pct_b >= 0.9:  return "Strong Upper"
    if pct_b >= 0.8:  return "Upper Break"
    if pct_b >= 0.5:  return "Above Mid"
    if pct_b >= 0.4:  return "In Bands"
    if pct_b >= 0.2:  return "Below Mid"
    if pct_b >= 0.1:  return "Lower Break"
    if pct_b >= 0.0:  return "Strong Lower"
    return "Extreme Lower"

# ── EMA50 ─────────────────────────────────────────────────────────────────────
def calc_ema50(close: pd.Series):
    ema = close.ewm(span=50, adjust=False).mean()
    pct = (float(close.iloc[-1]) - float(ema.iloc[-1])) / float(ema.iloc[-1]) * 100
    return float(ema.iloc[-1]), round(pct, 2)

def ema50_judgment(pct):
    if pct is None: return "N/A"
    if pct >= 15:   return "Super Up"
    if pct >= 8:    return "Very Strong Up"
    if pct >= 4:    return "Strong Up"
    if pct >= 2:    return "Mod Up"
    if pct >= 0.5:  return "Uptrend"
    if pct >= -0.5: return "Consolidating"
    if pct >= -2:   return "Downtrend"
    if pct >= -4:   return "Mod Down"
    if pct >= -8:   return "Strong Down"
    if pct >= -15:  return "Very Strong Down"
    return "Super Down"

# ── VWAP ──────────────────────────────────────────────────────────────────────
def calc_vwap(high, low, close, volume):
    typical = (high + low + close) / 3
    vwap    = (typical * volume).cumsum() / volume.cumsum()
    pct     = (float(close.iloc[-1]) - float(vwap.iloc[-1])) / float(vwap.iloc[-1]) * 100
    return float(vwap.iloc[-1]), round(pct, 2)

def vwap_judgment(pct):
    if pct is None: return "N/A"
    if pct >= 5:    return "Extreme Over"
    if pct >= 3:    return "Far Over"
    if pct >= 2:    return "Strong Over"
    if pct >= 1:    return "Over"
    if pct >= 0.2:  return "Slightly Over"
    if pct >= -0.2: return "Near"
    if pct >= -1:   return "Slightly Under"
    if pct >= -2:   return "Under"
    if pct >= -3:   return "Strong Under"
    if pct >= -5:   return "Far Under"
    return "Extreme Under"

# ── Score ─────────────────────────────────────────────────────────────────────
SCORE_MAP = {
    # RSI
    "Extreme Overbought": 1, "Overbought": 2, "Strong Up": 3, "Mod Up": 4,
    "Slightly Up": 5, "Neutral": 6, "Slightly Down": 7, "Mod Down": 8,
    "Oversold": 9, "Extreme Oversold": 11,
    # MACD
    "Strong Bull": 1, "Bull": 3, "Weakening Bull": 4,
    "Weakening Bear": 7, "Bear": 9, "Strong Bear": 11,
    # ADX
    "Extreme Up": 1, "Very Strong Up": 2, "Trending Up": 5, "No Trend": 6,
    "Trending Down": 7, "Strong Down": 9, "Very Strong Down": 10, "Extreme Down": 11,
    # BB
    "Super Upper": 1, "Extreme Upper": 2, "Upper Break": 4, "Above Mid": 5,
    "In Bands": 6, "Below Mid": 7, "Lower Break": 8, "Strong Lower": 9, "Extreme Lower": 11,
    # EMA50
    "Super Up": 1, "Very Strong Up": 2, "Uptrend": 5, "Consolidating": 6,
    "Downtrend": 7, "Super Down": 11,
    # VWAP
    "Extreme Over": 1, "Far Over": 2, "Strong Over": 3, "Over": 4,
    "Slightly Over": 5, "Near": 6, "Slightly Under": 7, "Under": 8,
    "Strong Under": 9, "Far Under": 10, "Extreme Under": 11,
}

def score_to_label(avg):
    if avg <= 2:   return ("Strong Bull 🟢", "bull-strong")
    if avg <= 4:   return ("Bull 🟢", "bull")
    if avg <= 5.5: return ("Slightly Bull 🟡", "bull-weak")
    if avg <= 6.5: return ("Neutral ⚪", "neutral")
    if avg <= 8:   return ("Slightly Bear 🟠", "bear-weak")
    if avg <= 9:   return ("Bear 🔴", "bear")
    return ("Strong Bear 🔴", "bear-strong")

# ── Main function ─────────────────────────────────────────────────────────────
def analyze_symbol(symbol: str, timeframes=None) -> dict:
    """
    Run full Analyzer Pro analysis on a symbol.
    Returns a dict with results per timeframe + overall score.
    """
    if timeframes is None:
        timeframes = ["15m", "1h", "1D"]

    results = {}
    overall_scores = []

    for tf in timeframes:
        if tf not in TIMEFRAMES:
            continue
        cfg = TIMEFRAMES[tf]
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=cfg["period"], interval=cfg["interval"])
            if df.empty or len(df) < 30:
                results[tf] = {"error": "Not enough data"}
                continue

            close  = df["Close"]
            high   = df["High"]
            low    = df["Low"]
            volume = df["Volume"]

            row = {}
            scores = []

            # RSI
            rsi_val = calc_rsi(close)
            rsi_j   = rsi_judgment(rsi_val)
            row["RSI"] = {"value": rsi_val, "label": rsi_j, "score": SCORE_MAP.get(rsi_j, 6)}
            scores.append(SCORE_MAP.get(rsi_j, 6))

            # MACD
            m, s, h = calc_macd(close)
            macd_j  = macd_judgment(m, s, h)
            row["MACD"] = {"value": round(m, 4), "label": macd_j, "score": SCORE_MAP.get(macd_j, 6)}
            scores.append(SCORE_MAP.get(macd_j, 6))

            # ADX
            adx_v, dip, din = calc_adx(high, low, close)
            adx_j = adx_judgment(adx_v, dip, din)
            row["ADX"] = {"value": round(adx_v, 1), "label": adx_j, "score": SCORE_MAP.get(adx_j, 6)}
            scores.append(SCORE_MAP.get(adx_j, 6))

            # Bollinger
            bu, bm, bl, pb = calc_bb(close)
            bb_j = bb_judgment(pb)
            row["Bollinger"] = {"value": round(pb, 3), "label": bb_j, "score": SCORE_MAP.get(bb_j, 6)}
            scores.append(SCORE_MAP.get(bb_j, 6))

            # EMA50
            ema_v, ema_pct = calc_ema50(close)
            ema_j = ema50_judgment(ema_pct)
            row["EMA50"] = {"value": f"{ema_pct:+.2f}%", "label": ema_j, "score": SCORE_MAP.get(ema_j, 6)}
            scores.append(SCORE_MAP.get(ema_j, 6))

            # VWAP
            vw_v, vw_pct = calc_vwap(high, low, close, volume)
            vwap_j = vwap_judgment(vw_pct)
            row["VWAP"] = {"value": f"{vw_pct:+.2f}%", "label": vwap_j, "score": SCORE_MAP.get(vwap_j, 6)}
            scores.append(SCORE_MAP.get(vwap_j, 6))

            avg = sum(scores) / len(scores)
            label, css = score_to_label(avg)
            row["_result"] = {"score": round(avg, 2), "label": label, "css": css}

            results[tf] = row
            overall_scores.extend(scores)

        except Exception as e:
            logger.warning(f"analyze_symbol {symbol} {tf}: {e}")
            results[tf] = {"error": str(e)}

    overall_avg   = sum(overall_scores) / len(overall_scores) if overall_scores else 6.0
    overall_label, overall_css = score_to_label(overall_avg)

    current_price = None
    try:
        t = yf.Ticker(symbol)
        info = t.fast_info
        current_price = round(float(info.last_price), 2)
    except:
        pass

    return {
        "symbol":        symbol,
        "price":         current_price,
        "timeframes":    results,
        "overall_score": round(overall_avg, 2),
        "overall_label": overall_label,
        "overall_css":   overall_css,
    }
