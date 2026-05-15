"""
research/sector_rotation.py — Sector rotation detector
Compare 30-day sector performance vs same period 1 year ago
"""
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from core.logger import get_logger

logger = get_logger(__name__)

SECTORS = {
    "Technology":        "XLK",
    "Healthcare":        "XLV",
    "Financials":        "XLF",
    "Consumer Discr.":   "XLY",
    "Industrials":       "XLI",
    "Communication":     "XLC",
    "Consumer Staples":  "XLP",
    "Energy":            "XLE",
    "Materials":         "XLB",
    "Utilities":         "XLU",
    "Real Estate":       "XLRE",
}

SECTOR_TOP_ETFS = {
    "Technology":       ["QQQ","SOXX","IGV","ARKK","VGT"],
    "Healthcare":       ["IBB","XBI","IHI","IHF","ARKG"],
    "Financials":       ["KBE","KRE","IAI","IAK","KBWB"],
    "Consumer Discr.":  ["XRT","RTH","FDIS","IBUY","ONLN"],
    "Industrials":      ["ITA","XAR","JETS","PAVE","GII"],
    "Communication":    ["FCOM","IYZ","VOX","SOCL","ESPO"],
    "Consumer Staples": ["KXI","FSTA","VDC","IYK","IECS"],
    "Energy":           ["OIH","XOP","FCG","AMLP","IEZ"],
    "Materials":        ["GDX","GDXJ","MOO","MXI","URNM"],
    "Utilities":        ["FXU","FUTY","VPU","IDU","RYU"],
    "Real Estate":      ["VNQ","SCHH","IYR","RWR","REZ"],
}

def get_30d_return(ticker: str) -> float | None:
    try:
        t   = yf.Ticker(ticker)
        df  = t.history(period="35d", interval="1d")
        if len(df) < 20:
            return None
        ret = (df["Close"].iloc[-1] / df["Close"].iloc[-20] - 1) * 100
        return round(float(ret), 2)
    except:
        return None

def get_30d_return_1y_ago(ticker: str) -> float | None:
    try:
        end   = datetime.now() - timedelta(days=365)
        start = end - timedelta(days=35)
        t   = yf.Ticker(ticker)
        df  = t.history(start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"), interval="1d")
        if len(df) < 20:
            return None
        ret = (df["Close"].iloc[-1] / df["Close"].iloc[-20] - 1) * 100
        return round(float(ret), 2)
    except:
        return None

def get_etf_money_flow(ticker: str) -> dict:
    try:
        t   = yf.Ticker(ticker)
        df  = t.history(period="35d", interval="1d")
        if df.empty or len(df) < 10:
            return {"ticker": ticker, "error": "no data"}
        close  = df["Close"]
        volume = df["Volume"]
        ret_30 = round(float((close.iloc[-1]/close.iloc[-20] - 1)*100), 2) if len(close) >= 20 else None
        ret_10 = round(float((close.iloc[-1]/close.iloc[-10] - 1)*100), 2) if len(close) >= 10 else None
        avg_vol= round(float(volume.tail(10).mean()))
        return {
            "ticker":    ticker,
            "return_30": ret_30,
            "return_10": ret_10,
            "avg_volume":avg_vol,
            "price":     round(float(close.iloc[-1]), 2),
        }
    except Exception as e:
        return {"ticker": ticker, "error": str(e)}

def get_sector_rotation() -> dict:
    logger.info("Running sector rotation analysis...")
    sectors = {}

    for name, etf in SECTORS.items():
        curr = get_30d_return(etf)
        prev = get_30d_return_1y_ago(etf)

        rotating = False
        if curr is not None and prev is not None:
            rotating = (prev < 0 and curr > 0) or (curr > prev + 3)

        sectors[name] = {
            "etf":            etf,
            "return_30d":     curr,
            "return_30d_1yago": prev,
            "rotating":       rotating,
            "strength_flip":  prev < 0 and curr > 0 if (curr and prev) else False,
        }

    # Rotating sectors — pull top ETFs with money flow
    rotating_sectors = {k: v for k, v in sectors.items() if v["rotating"]}
    etf_flows = {}

    for sec_name in list(rotating_sectors.keys())[:4]:
        etfs = SECTOR_TOP_ETFS.get(sec_name, [])
        flows = [get_etf_money_flow(e) for e in etfs]
        flows = [f for f in flows if "error" not in f]
        flows.sort(key=lambda x: (x.get("return_10") or -999), reverse=True)
        etf_flows[sec_name] = flows

    # Rank all sectors by current return
    ranked = sorted(
        [(k, v) for k, v in sectors.items() if v["return_30d"] is not None],
        key=lambda x: x[1]["return_30d"], reverse=True
    )

    return {
        "sectors":          sectors,
        "rotating_sectors": rotating_sectors,
        "etf_flows":        etf_flows,
        "ranked":           [(k, v["return_30d"]) for k, v in ranked],
    }
