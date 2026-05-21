"""
core/market_data.py — Market data engine
Priority: Alpaca Data API → yfinance → Demo mode
All three work on Railway. Sandbox shows demo data.
"""
import os, math, time, random, requests
from datetime import datetime, timedelta, timezone
from core.config import Config
from core.logger import get_logger

logger = get_logger(__name__)

ALPACA_DATA_URL = "https://data.alpaca.markets"

def _alpaca_headers():
    return {
        "APCA-API-KEY-ID":     Config.ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": Config.ALPACA_SECRET_KEY,
    }

def _yahoo_headers():
    return {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
        "Accept": "application/json,text/html,*/*",
        "Accept-Language": "en-US,en;q=0.9",
    }

# ── Check if data sources are reachable ─────────────────────────────────────
def _alpaca_reachable():
    try:
        r = requests.get(
            f"{ALPACA_DATA_URL}/v2/stocks/AAPL/bars",
            params={"timeframe":"1Day","limit":1,"feed":"iex"},
            headers=_alpaca_headers(), timeout=8)
        return r.status_code == 200
    except:
        return False

def _yahoo_reachable():
    try:
        r = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/AAPL",
            params={"interval":"1d","range":"5d"},
            headers=_yahoo_headers(), timeout=8)
        return r.status_code == 200
    except:
        return False

# ── ALPACA DATA API ──────────────────────────────────────────────────────────
def alpaca_get_bars(symbol: str, timeframe: str = "1Day",
                    limit: int = 200, feed: str = "iex") -> list | None:
    """
    Get OHLCV bars from Alpaca.
    timeframe: 1Min, 5Min, 15Min, 1Hour, 1Day, 1Week
    Returns list of dicts: {t, o, h, l, c, v}
    """
    try:
        url = f"{ALPACA_DATA_URL}/v2/stocks/{symbol.upper()}/bars"
        params = {"timeframe": timeframe, "limit": limit, "feed": feed,
                  "sort": "asc", "adjustment": "raw"}
        r = requests.get(url, params=params, headers=_alpaca_headers(), timeout=12)
        r.raise_for_status()
        bars = r.json().get("bars", [])
        return bars
    except Exception as e:
        logger.warning(f"Alpaca bars {symbol} {timeframe}: {e}")
        return None


def alpaca_get_multi_bars(symbols: list, timeframe: str = "1Day",
                          limit: int = 100) -> dict | None:
    """Get bars for multiple symbols in one call."""
    try:
        url = f"{ALPACA_DATA_URL}/v2/stocks/bars"
        params = {"symbols": ",".join(s.upper() for s in symbols),
                  "timeframe": timeframe, "limit": limit,
                  "feed": "iex", "sort": "asc", "adjustment": "raw"}
        r = requests.get(url, params=params, headers=_alpaca_headers(), timeout=15)
        r.raise_for_status()
        return r.json().get("bars", {})
    except Exception as e:
        logger.warning(f"Alpaca multi-bars: {e}")
        return None


def alpaca_get_snapshot(symbol: str) -> dict | None:
    """Get latest quote + trade + daily bar for a symbol."""
    try:
        url = f"{ALPACA_DATA_URL}/v2/stocks/{symbol.upper()}/snapshot"
        r   = requests.get(url, params={"feed":"iex"}, headers=_alpaca_headers(), timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning(f"Alpaca snapshot {symbol}: {e}")
        return None


def alpaca_get_multi_snapshots(symbols: list) -> dict | None:
    """Snapshots for multiple symbols."""
    try:
        url = f"{ALPACA_DATA_URL}/v2/stocks/snapshots"
        r   = requests.get(url, params={"symbols":",".join(s.upper() for s in symbols),
                                         "feed":"iex"},
                           headers=_alpaca_headers(), timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning(f"Alpaca multi-snapshots: {e}")
        return None


# ── YAHOO FINANCE FALLBACK ────────────────────────────────────────────────────
def yahoo_get_chart(symbol: str, interval: str = "1d",
                    period: str = "6mo") -> dict | None:
    """Yahoo Finance v8 chart data."""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol.upper()}"
        r   = requests.get(url, params={"interval":interval,"range":period},
                           headers=_yahoo_headers(), timeout=12)
        r.raise_for_status()
        res = r.json()["chart"]["result"][0]
        ts  = res["timestamp"]
        q   = res["indicators"]["quote"][0]
        return {"timestamps":ts, "open":q.get("open",[]),
                "high":q.get("high",[]), "low":q.get("low",[]),
                "close":q.get("close",[]), "volume":q.get("volume",[])}
    except Exception as e:
        logger.warning(f"Yahoo chart {symbol}: {e}")
        return None


def yahoo_get_options(symbol: str) -> dict | None:
    """Yahoo Finance options chain."""
    try:
        url = f"https://query1.finance.yahoo.com/v7/finance/options/{symbol.upper()}"
        r   = requests.get(url, headers=_yahoo_headers(), timeout=12)
        r.raise_for_status()
        res = r.json()["optionChain"]["result"][0]
        return {
            "symbol":  symbol.upper(),
            "spot":    res.get("quote",{}).get("regularMarketPrice",0),
            "expiries":res.get("expirationDates",[]),
            "calls":   res.get("options",[{}])[0].get("calls",[]),
            "puts":    res.get("options",[{}])[0].get("puts",[]),
        }
    except Exception as e:
        logger.warning(f"Yahoo options {symbol}: {e}")
        return None


def yahoo_earnings_date(symbol: str) -> str | None:
    """Get next earnings date from Yahoo."""
    try:
        url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{symbol.upper()}"
        r   = requests.get(url, params={"modules":"calendarEvents"},
                           headers=_yahoo_headers(), timeout=10)
        r.raise_for_status()
        dates = (r.json()["quoteSummary"]["result"][0]
                  ["calendarEvents"]["earnings"].get("earningsDate",[]))
        if dates:
            return datetime.fromtimestamp(dates[0]["raw"]).strftime("%Y-%m-%d")
    except:
        pass
    return None


# ── DEMO DATA (sandbox / offline fallback) ────────────────────────────────────
def _gen_price_series(seed_price: float, n: int, vol: float = 0.015) -> list:
    """Generate realistic random-walk price series."""
    random.seed(hash(seed_price) % 1000)
    prices, p = [], seed_price
    for _ in range(n):
        p = p * (1 + random.gauss(0.0002, vol))
        prices.append(round(p, 2))
    return prices


def demo_bars(symbol: str, n: int = 200, weekly: bool = False) -> list:
    """Generate realistic demo OHLCV bars with correct dates going back from today."""
    seed = {"AAPL":182,"MSFT":415,"NVDA":875,"TSLA":175,"AMD":160,
            "META":490,"GOOGL":175,"JPM":205,"SPY":520,"QQQ":440,
            "XLK":215,"XLV":140,"XLF":42,"XLY":185,"XLI":125,
            "XLC":95,"XLP":78,"XLE":90,"XLB":88,"XLU":68,"XLRE":38,
            "MU":110,"AMZN":185,"NFLX":625,"CRM":290,"NVDA":875,
            "SOXX":220,"GLD":195,"SLV":28,"USO":75,"QQQ":440,
            "IWM":195,"DIA":385}.get(symbol.upper(), 100)
    closes = _gen_price_series(seed, n)
    bars   = []
    now    = datetime.now(timezone.utc)
    step   = timedelta(weeks=1) if weekly else timedelta(days=1)
    # Start from n bars ago, skip weekends for daily
    count  = 0
    day    = now - step * n
    for i in range(n * 2):  # extra iterations to skip weekends
        if len(bars) >= n:
            break
        day += step
        if not weekly and day.weekday() >= 5:  # skip Sat/Sun
            continue
        c = closes[count] if count < len(closes) else closes[-1]
        count += 1
        o = closes[count-2] if count > 1 else c
        h = max(o, c) * (1 + random.uniform(0, 0.008))
        l = min(o, c) * (1 - random.uniform(0, 0.008))
        bars.append({
            "t":      day.strftime("%Y-%m-%dT00:00:00+00:00"),
            "o":      round(o,2), "h": round(h,2),
            "l":      round(l,2), "c": c,
            "v":      int(random.uniform(5e6, 80e6)),
            "source": "demo"
        })
    return bars


# ── UNIFIED get_bars (tries Alpaca → Yahoo → Demo) ───────────────────────────
# TF → (alpaca_timeframe, bar_count, yahoo_interval, yahoo_period)
# UI periods map directly to this config
PERIOD_CONFIG = {
    # Intraday
    "5m":   ("5Min",  100,  "5m",  "5d"),
    "15m":  ("15Min", 200,  "15m", "5d"),
    "1h":   ("1Hour", 300,  "1h",  "30d"),
    "4h":   ("1Hour", 500,  "1h",  "60d"),
    # Daily
    "1mo":  ("1Day",  22,   "1d",  "1mo"),
    "3mo":  ("1Day",  66,   "1d",  "3mo"),
    "6mo":  ("1Day",  132,  "1d",  "6mo"),
    "1y":   ("1Day",  252,  "1d",  "1y"),
    "1D":   ("1Day",  252,  "1d",  "1y"),   # analyzer default
    # Weekly
    "1W":   ("1Week", 52,   "1wk", "1y"),
    "3y":   ("1Day",  756,  "1d",  "3y"),
    "5y":   ("1Day",  1260, "1d",  "5y"),
    "10y":  ("1Week", 520,  "1wk", "10y"),
    # Aliases
    "3Y":   ("1Day",  756,  "1d",  "3y"),
    "5Y":   ("1Day",  1260, "1d",  "5y"),
    "10Y":  ("1Week", 520,  "1wk", "10y"),
}

# Keep backward compat
ALPACA_TF_MAP = {k: (v[0], v[1]) for k,v in PERIOD_CONFIG.items()}
YAHOO_MAP     = {k: (v[2], v[3]) for k,v in PERIOD_CONFIG.items()}

def get_bars(symbol: str, period: str = "1y") -> list | None:
    """
    Unified bar fetcher. period = any key in PERIOD_CONFIG.
    e.g: "1mo","3mo","6mo","1y","3y","5y","10y","5m","15m","1h","1D","1W"
    Returns list of dicts: {t, o, h, l, c, v, source}
    """
    symbol = symbol.upper()
    cfg    = PERIOD_CONFIG.get(period, PERIOD_CONFIG["1y"])
    alp_tf, alp_limit, yh_interval, yh_period = cfg
    weekly = period in ("1W","10Y","10y")

    # 1. Alpaca Data API (primary)
    bars = alpaca_get_bars(symbol, alp_tf, alp_limit)
    if bars:
        for b in bars:
            b["source"] = "alpaca"
        logger.info(f"✅ Alpaca: {symbol} {period} ({len(bars)} bars)")
        return bars

    # 2. Yahoo Finance (fallback)
    chart = yahoo_get_chart(symbol, yh_interval, yh_period)
    if chart:
        closes    = chart.get("close",[])
        opens     = chart.get("open", [])
        highs     = chart.get("high", [])
        lows      = chart.get("low",  [])
        volumes   = chart.get("volume",[])
        timestamps= chart.get("timestamps",[])
        bars = []
        for i in range(len(closes)):
            if closes[i] is None: continue
            ts = datetime.fromtimestamp(timestamps[i], tz=timezone.utc).isoformat() \
                 if i < len(timestamps) else ""
            bars.append({
                "t": ts,
                "o": opens[i]   if i<len(opens)  and opens[i]   is not None else closes[i],
                "h": highs[i]   if i<len(highs)  and highs[i]   is not None else closes[i],
                "l": lows[i]    if i<len(lows)   and lows[i]    is not None else closes[i],
                "c": closes[i],
                "v": volumes[i] if i<len(volumes) and volumes[i] is not None else 0,
                "source": "yahoo"
            })
        logger.info(f"✅ Yahoo: {symbol} {period} ({len(bars)} bars)")
        return bars

    # 3. Demo fallback (sandbox — all sources blocked)
    logger.warning(f"⚠️ Demo: {symbol} {period} ({alp_limit} bars)")
    return demo_bars(symbol, alp_limit, weekly=weekly)


def get_quote_live(symbol: str) -> dict:
    """Get current price. Alpaca → Yahoo → Demo."""
    symbol = symbol.upper()
    snap   = alpaca_get_snapshot(symbol)
    if snap:
        db = snap.get("dailyBar", {})
        lt = snap.get("latestTrade", {})
        return {
            "symbol": symbol,
            "price":  lt.get("p", db.get("c", 0)),
            "open":   db.get("o", 0),
            "high":   db.get("h", 0),
            "low":    db.get("l", 0),
            "close":  db.get("c", 0),
            "volume": db.get("v", 0),
            "source": "alpaca"
        }

    # Yahoo fallback
    try:
        r = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
            params={"interval":"1d","range":"1d"},
            headers=_yahoo_headers(), timeout=8)
        if r.ok:
            meta = r.json()["chart"]["result"][0]["meta"]
            return {
                "symbol": symbol,
                "price":  meta.get("regularMarketPrice", 0),
                "open":   meta.get("regularMarketOpen",  0),
                "high":   meta.get("regularMarketDayHigh",0),
                "low":    meta.get("regularMarketDayLow", 0),
                "close":  meta.get("chartPreviousClose",  0),
                "volume": meta.get("regularMarketVolume", 0),
                "source": "yahoo"
            }
    except:
        pass

    # Demo
    seed = {"AAPL":182,"MSFT":415,"NVDA":875,"TSLA":175}.get(symbol, 100)
    return {"symbol":symbol, "price":seed, "open":seed,"high":seed*1.01,
            "low":seed*0.99,"close":seed,"volume":10000000,"source":"demo"}


def get_multi_quotes(symbols: list) -> dict:
    """Batch quotes. Returns {symbol: quote_dict}"""
    results = {}
    # Try Alpaca batch first
    snaps = alpaca_get_multi_snapshots(symbols)
    if snaps:
        for sym, snap in snaps.items():
            db = snap.get("dailyBar", {})
            lt = snap.get("latestTrade", {})
            results[sym] = {
                "symbol": sym, "price": lt.get("p", db.get("c",0)),
                "change_pct": snap.get("dailyBar",{}).get("vw",0),
                "volume": db.get("v",0), "source":"alpaca"
            }
        missing = [s for s in symbols if s.upper() not in results]
    else:
        missing = symbols

    for sym in missing:
        q = get_quote_live(sym)
        results[sym.upper()] = q
        time.sleep(0.05)

    return results


def get_options_data(symbol: str) -> dict | None:
    """Get options chain. Yahoo Finance → None."""
    chain = yahoo_get_options(symbol)
    if chain:
        return chain
    logger.warning(f"Options data unavailable for {symbol}")
    return None


def get_earnings_date(symbol: str) -> str | None:
    """Get next earnings date from Yahoo."""
    return yahoo_earnings_date(symbol)


# ── Historical volatility ─────────────────────────────────────────────────────
def calc_hist_vol(closes: list, window: int = 20) -> float | None:
    if len(closes) < window + 1:
        return None
    rets = [math.log(closes[i]/closes[i-1])
            for i in range(1, len(closes))
            if closes[i] and closes[i-1] and closes[i-1] > 0]
    if len(rets) < window:
        return None
    recent = rets[-window:]
    mean   = sum(recent) / len(recent)
    var    = sum((r-mean)**2 for r in recent) / (len(recent)-1)
    return round(math.sqrt(var) * math.sqrt(252) * 100, 1)


def data_source_status() -> dict:
    """Check which data sources are live. Used by /health endpoint."""
    alp  = _alpaca_reachable()
    yh   = _yahoo_reachable()
    return {
        "alpaca_data": "live" if alp else "unavailable",
        "yahoo":       "live" if yh  else "unavailable",
        "fallback":    "demo" if (not alp and not yh) else "not-needed",
        "note":        "On Railway all sources are live. Sandbox uses demo data." if (not alp and not yh) else "Live data active"
    }
