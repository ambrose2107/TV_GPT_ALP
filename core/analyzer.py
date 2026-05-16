"""
core/analyzer.py — Analyzer Pro: full technical analysis engine
Uses free Yahoo Finance data. Works on Railway.
Graceful fallback for sandbox (network blocked).
"""
import math
from core.logger import get_logger

logger = get_logger(__name__)

# ── Indicator calculations (pure Python, no pandas needed) ──────────────────

def _clean(lst):
    return [x for x in (lst or []) if x is not None]

def calc_rsi(closes, period=14):
    c = _clean(closes)
    if len(c) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(c)):
        d = c[i] - c[i-1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_g = (avg_g * (period-1) + gains[i]) / period
        avg_l = (avg_l * (period-1) + losses[i]) / period
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return round(100 - 100/(1+rs), 2)

def rsi_label(v):
    if v is None: return "N/A", 6
    if v >= 80:   return "Extreme Overbought", 2
    if v >= 70:   return "Overbought", 2
    if v >= 60:   return "Slightly Bull",  4
    if v >= 55:   return "Neutral-Bull",   5
    if v >= 45:   return "Neutral",        6
    if v >= 40:   return "Neutral-Bear",   7
    if v >= 30:   return "Oversold",       9
    return "Extreme Oversold", 10

def calc_ema(closes, span):
    c = _clean(closes)
    if len(c) < span:
        return None
    k, ema = 2/(span+1), c[0]
    for price in c[1:]:
        ema = price * k + ema * (1-k)
    return round(ema, 4)

def calc_macd(closes):
    c = _clean(closes)
    if len(c) < 26:
        return None, None, None
    def ema_series(data, span):
        k, s = 2/(span+1), data[0]
        result = [s]
        for p in data[1:]:
            s = p*k + s*(1-k)
            result.append(s)
        return result
    ema12 = ema_series(c, 12)
    ema26 = ema_series(c, 26)
    macd  = [a-b for a,b in zip(ema12, ema26)]
    sig   = ema_series(macd, 9)
    hist  = macd[-1] - sig[-1]
    return round(macd[-1], 4), round(sig[-1], 4), round(hist, 4)

def macd_label(macd, signal, hist):
    if macd is None: return "N/A", 6
    if macd > 0 and hist > 0 and macd > signal: return "Strong Bull", 1
    if macd > 0 and hist > 0:                   return "Bull",        3
    if macd > 0 and hist < 0:                   return "Weakening",   5
    if macd < 0 and hist > 0:                   return "Recovering",  7
    if macd < 0 and hist < 0 and macd < signal: return "Strong Bear", 10
    if macd < 0 and hist < 0:                   return "Bear",        8
    return "Neutral", 6

def calc_bb(closes, period=20, std_mult=2):
    c = _clean(closes)
    if len(c) < period:
        return None, None, None, None
    window = c[-period:]
    mid    = sum(window) / period
    var    = sum((x-mid)**2 for x in window) / period
    sigma  = math.sqrt(var)
    upper  = mid + std_mult * sigma
    lower  = mid - std_mult * sigma
    pct_b  = (c[-1] - lower) / (upper - lower) if upper != lower else 0.5
    return round(upper,4), round(mid,4), round(lower,4), round(pct_b,4)

def bb_label(pct_b):
    if pct_b is None: return "N/A", 6
    if pct_b >= 1.1:  return "Extreme Upper", 1
    if pct_b >= 0.8:  return "Upper Break",   3
    if pct_b >= 0.6:  return "Above Mid",     4
    if pct_b >= 0.4:  return "In Bands",      6
    if pct_b >= 0.2:  return "Below Mid",     7
    if pct_b >= 0.0:  return "Lower Break",   9
    return "Extreme Lower", 10

def calc_adx(highs, lows, closes, period=14):
    h = _clean(highs); l = _clean(lows); c = _clean(closes)
    n = min(len(h), len(l), len(c))
    if n < period + 1:
        return None, None, None
    h, l, c = h[-n:], l[-n:], c[-n:]
    trs, dmp, dmn = [], [], []
    for i in range(1, n):
        tr  = max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
        dm_plus  = max(h[i]-h[i-1], 0) if (h[i]-h[i-1]) > (l[i-1]-l[i]) else 0
        dm_minus = max(l[i-1]-l[i], 0) if (l[i-1]-l[i]) > (h[i]-h[i-1]) else 0
        trs.append(tr); dmp.append(dm_plus); dmn.append(dm_minus)
    def smooth(data, p):
        s = sum(data[:p])
        result = [s]
        for x in data[p:]:
            s = s - s/p + x
            result.append(s)
        return result
    atr = smooth(trs, period); dip = smooth(dmp, period); din = smooth(dmn, period)
    adx_vals = []
    for i in range(len(atr)):
        if atr[i] == 0: continue
        di_plus  = 100 * dip[i] / atr[i]
        di_minus = 100 * din[i] / atr[i]
        if di_plus + di_minus == 0: continue
        dx = 100 * abs(di_plus - di_minus) / (di_plus + di_minus)
        adx_vals.append(dx)
    if not adx_vals:
        return None, None, None
    adx_smooth = sum(adx_vals[-period:]) / min(period, len(adx_vals))
    atr_last   = atr[-1]
    dip_last   = 100 * dip[-1] / atr_last if atr_last else 0
    din_last   = 100 * din[-1] / atr_last if atr_last else 0
    return round(adx_smooth,1), round(dip_last,1), round(din_last,1)

def adx_label(adx, dip, din):
    if adx is None: return "N/A", 6
    if adx < 20:                    return "No Trend",       6
    up = dip > din
    if adx >= 50 and up:            return "Extreme Up",     1
    if adx >= 40 and up:            return "Very Strong Up", 2
    if adx >= 30 and up:            return "Strong Up",      3
    if adx >= 20 and up:            return "Trending Up",    4
    if adx >= 50 and not up:        return "Extreme Down",   10
    if adx >= 40 and not up:        return "Very Strong Dn", 9
    if adx >= 30 and not up:        return "Strong Down",    8
    return "Trending Down", 7

def calc_vwap(highs, lows, closes, volumes):
    h = _clean(highs); l = _clean(lows); c = _clean(closes); v = _clean(volumes)
    n = min(len(h), len(l), len(c), len(v))
    if n < 2: return None, None
    cum_tv = cum_v = 0
    for i in range(n):
        typ = (h[i]+l[i]+c[i])/3
        cum_tv += typ * v[i]
        cum_v  += v[i]
    vwap = cum_tv / cum_v if cum_v else c[-1]
    pct  = (c[-1] - vwap) / vwap * 100 if vwap else 0
    return round(vwap, 4), round(pct, 2)

def vwap_label(pct):
    if pct is None: return "N/A", 6
    if pct >= 3:   return "Far Over",     2
    if pct >= 1:   return "Over",         4
    if pct >= 0.2: return "Slightly Over",5
    if pct >= -0.2:return "Near VWAP",    6
    if pct >= -1:  return "Slightly Under",7
    if pct >= -3:  return "Under",        8
    return "Far Under", 9

def ema50_label(pct):
    if pct is None: return "N/A", 6
    if pct >= 8:   return "Super Uptrend",  1
    if pct >= 4:   return "Strong Uptrend", 2
    if pct >= 1:   return "Uptrend",        4
    if pct >= -1:  return "Consolidating",  6
    if pct >= -4:  return "Downtrend",      8
    if pct >= -8:  return "Strong Downtrend",9
    return "Super Downtrend", 10

def score_to_signal(avg):
    if avg <= 2:   return "Strong Bull 🟢", "bull2"
    if avg <= 4:   return "Bull 🟢",        "bull1"
    if avg <= 5.5: return "Slightly Bull 🟡","bln"
    if avg <= 6.5: return "Neutral ⚪",     "neut"
    if avg <= 8:   return "Slightly Bear 🟠","brn"
    if avg <= 9:   return "Bear 🔴",        "bear1"
    return "Strong Bear 🔴", "bear2"

INTERVAL_MAP = {
    "5m":  ("5m",  "5d"),
    "15m": ("15m", "5d"),
    "1h":  ("1h",  "30d"),
    "4h":  ("1h",  "60d"),   # aggregate later
    "1D":  ("1d",  "6mo"),
    "1W":  ("1wk", "5y"),
}

def analyze_one_tf(chart: dict) -> dict:
    """Run all 6 indicators on chart data."""
    if not chart:
        return {"error": "no data"}
    c = _clean(chart.get("close",  []))
    h = _clean(chart.get("high",   []))
    l = _clean(chart.get("low",    []))
    v = _clean(chart.get("volume", []))
    if len(c) < 20:
        return {"error": f"too few bars ({len(c)})"}

    scores = []
    row    = {}

    # RSI
    rsi_v = calc_rsi(c)
    rsi_l, rsi_s = rsi_label(rsi_v)
    row["rsi"] = {"v": rsi_v, "l": rsi_l}
    scores.append(rsi_s)

    # MACD
    m, sig, hst = calc_macd(c)
    mac_l, mac_s = macd_label(m, sig, hst)
    row["macd"] = {"v": round(m,4) if m else None, "l": mac_l}
    scores.append(mac_s)

    # ADX
    adx_v, dip, din = calc_adx(h, l, c)
    adx_l, adx_s = adx_label(adx_v, dip, din)
    row["adx"] = {"v": adx_v, "l": adx_l}
    scores.append(adx_s)

    # Bollinger
    bu, bm, bl, pb = calc_bb(c)
    bb_l, bb_s = bb_label(pb)
    row["bb"] = {"v": round(pb,3) if pb else None, "l": bb_l}
    scores.append(bb_s)

    # EMA50
    ema50 = calc_ema(c, 50)
    if ema50 and c[-1]:
        ema_pct = (c[-1] - ema50) / ema50 * 100
        ema_l, ema_s = ema50_label(ema_pct)
        row["ema50"] = {"v": f"{ema_pct:+.2f}%", "l": ema_l}
        scores.append(ema_s)
    else:
        row["ema50"] = {"v": None, "l": "N/A"}
        scores.append(6)

    # VWAP
    vwap_v, vwap_pct = calc_vwap(h, l, c, v)
    vwap_l, vwap_s = vwap_label(vwap_pct)
    row["vwap"] = {"v": f"{vwap_pct:+.2f}%" if vwap_pct else None, "l": vwap_l}
    scores.append(vwap_s)

    avg = sum(scores) / len(scores)
    sig_l, sig_css = score_to_signal(avg)
    row["result"] = {"l": sig_l, "css": sig_css, "score": round(avg,2)}
    return row


def analyze_symbol(symbol: str, timeframes: list = None) -> dict:
    """Full Analyzer Pro for one symbol across multiple timeframes."""
    if timeframes is None:
        timeframes = ["15m", "1h", "1D"]

    try:
        from core.data_engine import get_chart, get_quote
    except ImportError:
        return {"symbol": symbol, "error": "data engine unavailable", "timeframes": {}}

    # Get current price
    quote = get_quote(symbol)
    price = quote["price"] if quote else None

    tf_results = {}
    all_scores  = []

    for tf in timeframes:
        if tf not in INTERVAL_MAP:
            tf_results[tf] = {"error": "unknown timeframe"}
            continue
        interval, period = INTERVAL_MAP[tf]
        chart = get_chart(symbol, interval, period)
        if not chart:
            tf_results[tf] = {"error": "no data from Yahoo Finance"}
            continue
        result = analyze_one_tf(chart)
        tf_results[tf] = result
        if "result" in result:
            all_scores.append(result["result"]["score"])

    overall_avg = sum(all_scores)/len(all_scores) if all_scores else 6.0
    overall_l, overall_css = score_to_signal(overall_avg)

    return {
        "symbol":        symbol.upper(),
        "price":         price,
        "timeframes":    tf_results,
        "overall_score": round(overall_avg, 2),
        "overall_label": overall_l,
        "overall_css":   overall_css,
    }


def analyze_multiple(symbols: list, timeframes: list = None) -> list:
    """Analyze multiple symbols."""
    results = []
    for sym in symbols:
        try:
            r = analyze_symbol(sym.upper().strip(), timeframes)
            results.append(r)
        except Exception as e:
            results.append({"symbol": sym.upper(), "error": str(e), "timeframes": {}})
    return results
