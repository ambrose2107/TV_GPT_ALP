"""
research/earnings.py — Earnings Whiplash: HV vs IV asymmetric setups
"""
import time
from datetime import datetime, timedelta
from core.data_engine import get_chart, get_options_chain, get_earnings_calendar, calc_hist_vol
from core.logger import get_logger

logger = get_logger(__name__)

SP500_SAMPLE = [
    "AAPL","MSFT","NVDA","AMZN","META","GOOGL","TSLA","JPM","V","UNH",
    "XOM","LLY","JNJ","AVGO","PG","MA","HD","CVX","MRK","ABBV",
    "COST","PEP","KO","WMT","BAC","MCD","CRM","NFLX","TMO","CSCO",
    "ABT","ACN","TXN","NKE","PM","ORCL","IBM","QCOM","AMGN","HON",
    "CAT","GE","RTX","SPGI","INTU","AMAT","NOW","ISRG","GS","BLK",
    "MU","LRCX","AMD","REGN","CI","SLB","MMC","TJX","EOG","VRTX",
    "KLAC","F","GM","PANW","PYPL","UBER","SNAP","PINS","RBLX","ZM",
]

def get_earnings_whiplash(max_stocks: int = 60) -> dict:
    today    = datetime.now().date()
    deadline = today + timedelta(days=14)
    results  = []

    logger.info(f"Scanning {max_stocks} stocks for earnings whiplash...")

    for sym in SP500_SAMPLE[:max_stocks]:
        try:
            # Get earnings date
            ed = get_earnings_calendar(sym)
            if not ed:
                time.sleep(0.05)
                continue
            edate = datetime.strptime(ed[:10], "%Y-%m-%d").date()
            if not (today <= edate <= deadline):
                continue

            # Historical data
            chart = get_chart(sym, "1d", "1y")
            if not chart:
                continue
            closes = [c for c in chart["close"] if c is not None]
            if len(closes) < 30:
                continue

            hv    = calc_hist_vol(closes)
            if not hv or hv < 8:
                continue

            price = closes[-1]

            # Implied vol from options
            iv = None
            try:
                chain = get_options_chain(sym)
                if chain and chain.get("calls"):
                    spot  = chain["spot"] or price
                    calls = chain["calls"]
                    atm   = min(calls, key=lambda c: abs(c.get("strike",0)-spot))
                    iv    = round(atm.get("impliedVolatility",0)*100, 1)
            except:
                pass

            # Historical post-earnings moves (large single-day gaps as proxy)
            daily_moves = []
            for i in range(1, len(closes)):
                if closes[i] and closes[i-1]:
                    ret = abs(closes[i]/closes[i-1]-1)*100
                    if ret > 4:
                        daily_moves.append(round(ret,1))
            avg_move = round(sum(daily_moves[-4:])/len(daily_moves[-4:]),1) if daily_moves else None

            asymmetric = (iv is not None and hv > 0 and iv < hv * 0.78)

            results.append({
                "symbol":       sym,
                "earnings_date":ed[:10],
                "days_to_earn": (edate - today).days,
                "price":        round(price, 2),
                "hist_vol":     hv,
                "impl_vol":     iv,
                "iv_hv_ratio":  round(iv/hv, 2) if iv else None,
                "avg_move":     avg_move,
                "hist_moves":   daily_moves[-4:],
                "asymmetric":   asymmetric,
            })
            logger.info(f"  {sym}: HV={hv}% IV={iv}% Asym={asymmetric}")
            time.sleep(0.2)

        except Exception as e:
            logger.debug(f"Earnings scan {sym}: {e}")

    results.sort(key=lambda x: x["hist_vol"], reverse=True)
    top10  = results[:10]
    asym3  = [r for r in top10 if r["asymmetric"]][:3]

    return {
        "scan_date":         str(today),
        "stocks_scanned":    max_stocks,
        "with_earnings":     len(results),
        "top10":             top10,
        "asymmetric_setups": asym3,
    }
