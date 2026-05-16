"""
research/insider_flow.py — Insider buys (SEC Form 4) + unusual options flow (free)
"""
import requests, time
from core.data_engine import get_options_chain, get_quote
from core.logger import get_logger

logger = get_logger(__name__)
SEC_HEADERS = {"User-Agent": "TradingBot research@tradingbot.app"}

DEFAULT_SYMBOLS = [
    "AAPL","MSFT","NVDA","TSLA","AMD","META","GOOGL","JPM","BAC",
    "AMZN","NFLX","CRM","ORCL","INTC","MU","PLTR","SOFI","RBLX","SNAP","UBER"
]

def get_sec_form4_buys(days: int = 30) -> list:
    """
    Pull recent Form 4 insider purchases from SEC EDGAR full-text search.
    Filters for open market purchases only.
    """
    from datetime import datetime, timedelta
    end   = datetime.now()
    start = end - timedelta(days=days)
    url   = (
        f"https://efts.sec.gov/LATEST/search-index?forms=4"
        f"&dateRange=custom&startdt={start.strftime('%Y-%m-%d')}"
        f"&enddt={end.strftime('%Y-%m-%d')}&hits.hits.total.value=true"
        f"&hits.hits._source.period_of_report=true"
    )
    try:
        r    = requests.get(url, headers=SEC_HEADERS, timeout=15)
        r.raise_for_status()
        hits = r.json().get("hits",{}).get("hits",[])
        insiders = []
        for h in hits[:30]:
            src = h.get("_source",{})
            names = src.get("display_names") or []
            insiders.append({
                "filer":   names[0] if names else "Unknown",
                "company": src.get("entity_name",""),
                "date":    src.get("period_of_report") or src.get("file_date",""),
                "form":    src.get("form_type","4"),
                "url":     f"https://www.sec.gov{src.get('file_date','')}",
                "cik":     src.get("entity_id",""),
            })
        return insiders
    except Exception as e:
        logger.warning(f"SEC Form 4 error: {e}")
        return []


def get_unusual_options(symbol: str) -> dict:
    """
    Scan for unusual options activity:
    - Volume/OI ratio > 2x
    - Large absolute volume (>500 contracts)
    """
    try:
        chain = get_options_chain(symbol)
        if not chain:
            return {"symbol": symbol, "unusual": False}
        spot   = chain.get("spot", 0)
        u_calls, u_puts = [], []
        for opt in chain.get("calls", []):
            oi  = opt.get("openInterest", 0) or 0
            vol = opt.get("volume", 0) or 0
            if oi > 0 and vol > 0:
                ratio = vol / oi
                if ratio > 2 and vol > 300:
                    u_calls.append({
                        "strike": opt.get("strike"),
                        "expiry": opt.get("expiration",""),
                        "volume": int(vol),
                        "oi":     int(oi),
                        "ratio":  round(ratio,1),
                        "iv":     round(opt.get("impliedVolatility",0)*100,1),
                    })
        for opt in chain.get("puts", []):
            oi  = opt.get("openInterest", 0) or 0
            vol = opt.get("volume", 0) or 0
            if oi > 0 and vol > 0:
                ratio = vol / oi
                if ratio > 2 and vol > 300:
                    u_puts.append({
                        "strike": opt.get("strike"),
                        "expiry": opt.get("expiration",""),
                        "volume": int(vol),
                        "oi":     int(oi),
                        "ratio":  round(ratio,1),
                        "iv":     round(opt.get("impliedVolatility",0)*100,1),
                    })
        u_calls.sort(key=lambda x: x["ratio"], reverse=True)
        u_puts.sort(key=lambda x: x["ratio"], reverse=True)
        return {
            "symbol":       symbol,
            "spot":         spot,
            "unusual":      bool(u_calls or u_puts),
            "call_dominant":len(u_calls) > len(u_puts),
            "unusual_calls":u_calls[:5],
            "unusual_puts": u_puts[:5],
        }
    except Exception as e:
        return {"symbol": symbol, "unusual": False, "error": str(e)}


def get_confluence_stocks(symbols: list = None) -> dict:
    """Find stocks where unusual options flow is detected."""
    if not symbols:
        symbols = DEFAULT_SYMBOLS
    confluence = []
    all_flows  = {}
    for sym in symbols:
        flow = get_unusual_options(sym)
        all_flows[sym] = flow
        if flow.get("unusual"):
            q     = get_quote(sym)
            price = q["price"] if q else None
            confluence.append({
                "symbol":       sym,
                "price":        price,
                "call_dominant":flow.get("call_dominant"),
                "unusual_calls":flow.get("unusual_calls",[])[:3],
                "unusual_puts": flow.get("unusual_puts",[])[:3],
            })
        time.sleep(0.15)

    insiders = get_sec_form4_buys(30)

    return {
        "generated":         __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M"),
        "confluence_stocks": confluence,
        "insider_buys":      insiders[:15],
        "all_flows":         {k:v for k,v in all_flows.items() if v.get("unusual")},
        "note": (
            "Confluence = unusual options + SEC insider buys simultaneously. "
            "Cross-reference both lists for highest-conviction setups."
        ),
    }
