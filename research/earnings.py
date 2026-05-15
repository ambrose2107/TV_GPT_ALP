"""
research/earnings.py — Earnings Whiplash Detector
Finds high historical volatility stocks with earnings in next 14 days
where implied volatility is LOWER than historical (asymmetric setup)
"""
import yfinance as yf
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from core.logger import get_logger

logger = get_logger(__name__)

SP500_SAMPLE = [
    "AAPL","MSFT","NVDA","AMZN","META","GOOGL","TSLA","BRK-B","JPM","V",
    "UNH","XOM","LLY","JNJ","AVGO","PG","MA","HD","CVX","MRK",
    "ABBV","COST","PEP","KO","WMT","BAC","MCD","CRM","NFLX","TMO",
    "CSCO","ABT","ACN","LIN","DHR","ADBE","TXN","NKE","NEE","PM",
    "ORCL","IBM","QCOM","AMGN","HON","CAT","GE","RTX","SPGI","INTU",
    "AMAT","NOW","ISRG","GS","BLK","SYK","AXP","DE","BKNG","ZTS",
    "PLD","GILD","MDLZ","ADI","MU","LRCX","AMD","REGN","CI","SLB",
    "MMC","TJX","EOG","VRTX","KLAC","SNPS","F","GM","PANW","PYPL",
]

def get_earnings_date(ticker_obj) -> str | None:
    try:
        cal = ticker_obj.calendar
        if cal is not None and not cal.empty:
            dates = cal.get("Earnings Date", [])
            if hasattr(dates, '__iter__') and len(list(dates)) > 0:
                d = list(dates)[0]
                if hasattr(d, 'date'):
                    return str(d.date())
                return str(d)[:10]
    except:
        pass
    return None

def calc_historical_vol(close: pd.Series, window=20) -> float:
    """Annualised realised volatility."""
    returns = np.log(close / close.shift(1)).dropna()
    if len(returns) < window:
        return None
    return float(returns.rolling(window).std().iloc[-1] * np.sqrt(252) * 100)

def get_implied_vol(ticker_obj) -> float | None:
    """Get IV from nearest ATM option."""
    try:
        exps = ticker_obj.options
        if not exps:
            return None
        exp  = exps[0]
        chain = ticker_obj.option_chain(exp)
        calls = chain.calls
        if calls.empty:
            return None
        spot = float(ticker_obj.fast_info.last_price)
        atm  = calls.iloc[(calls["strike"] - spot).abs().argsort()[:1]]
        iv   = atm["impliedVolatility"].values[0] * 100
        return round(iv, 1)
    except:
        return None

def get_earnings_whiplash(max_stocks=60) -> dict:
    """
    Scan S&P 500 sample for earnings in next 14 days with HV > IV setup.
    Returns top 10 by HV and flags 3 asymmetric setups.
    """
    today    = datetime.now().date()
    deadline = today + timedelta(days=14)
    results  = []

    logger.info(f"Scanning {max_stocks} stocks for earnings whiplash...")

    for sym in SP500_SAMPLE[:max_stocks]:
        try:
            t   = yf.Ticker(sym)
            ed  = get_earnings_date(t)
            if not ed:
                continue
            edate = datetime.strptime(ed[:10], "%Y-%m-%d").date()
            if not (today <= edate <= deadline):
                continue

            df  = t.history(period="1y", interval="1d")
            if df.empty or len(df) < 30:
                continue

            hv  = calc_historical_vol(df["Close"])
            if not hv or hv < 8:
                continue

            iv  = get_implied_vol(t)
            price = round(float(df["Close"].iloc[-1]), 2)

            # Historical post-earnings move (last 4 earnings)
            hist_moves = _calc_post_earnings_moves(df)

            asymmetric = (iv is not None and iv < hv * 0.75)

            results.append({
                "symbol":        sym,
                "earnings_date": ed[:10],
                "days_to_earn":  (edate - today).days,
                "price":         price,
                "hist_vol":      round(hv, 1),
                "impl_vol":      iv,
                "iv_hv_ratio":   round(iv / hv, 2) if iv else None,
                "hist_moves":    hist_moves,
                "avg_move":      round(np.mean([abs(m) for m in hist_moves]), 1) if hist_moves else None,
                "asymmetric":    asymmetric,
            })
        except Exception as e:
            logger.debug(f"Earnings scan {sym}: {e}")
            continue

    results.sort(key=lambda x: x["hist_vol"], reverse=True)
    top10 = results[:10]

    asymmetric = [r for r in top10 if r["asymmetric"]][:3]

    return {
        "scan_date":   str(today),
        "scan_window": "14 days",
        "stocks_scanned": max_stocks,
        "top10":       top10,
        "asymmetric_setups": asymmetric,
    }

def _calc_post_earnings_moves(df: pd.DataFrame) -> list:
    """Estimate historical post-earnings day moves from large gap days."""
    try:
        daily_ret = ((df["Close"] - df["Open"]) / df["Open"] * 100).abs()
        big_moves = daily_ret[daily_ret > 4].tail(4).tolist()
        return [round(m, 1) for m in big_moves]
    except:
        return []
