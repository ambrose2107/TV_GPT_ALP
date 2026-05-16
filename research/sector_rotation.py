"""
research/sector_rotation.py — Real sector rotation using free Yahoo Finance data
"""
from core.data_engine import (get_sector_returns, get_etf_money_flow, TOP_ETFS_PER_SECTOR,
                               SECTOR_ETFS, get_chart)
from core.logger import get_logger
from datetime import datetime, timedelta
import time

logger = get_logger(__name__)

def get_sector_rotation() -> dict:
    """
    Full sector rotation analysis:
    - Current 30-day returns for all 11 sectors
    - Same period 1 year ago
    - Detects rotation (negative→positive or positive→negative flips)
    - Top 5 ETFs per rotating sector by money flow
    """
    logger.info("Running sector rotation analysis...")
    current = get_sector_returns(30)

    # Get 1-year-ago returns by fetching longer history
    prior = {}
    for name, etf in SECTOR_ETFS.items():
        try:
            chart = get_chart(etf, "1d", "2y")
            if not chart:
                prior[name] = None
                continue
            closes = [c for c in chart["close"] if c is not None]
            # ~252 trading days per year; 30-day window starting 1yr ago
            if len(closes) < 282:
                prior[name] = None
                continue
            ret = (closes[-252] / closes[-282] - 1) * 100
            prior[name] = round(ret, 2)
            time.sleep(0.1)
        except Exception as e:
            logger.warning(f"Prior return error {name}: {e}")
            prior[name] = None

    # Build sector summary + detect rotation
    sectors = {}
    for name in SECTOR_ETFS:
        curr_ret = current.get(name, {}).get("return")
        prev_ret = prior.get(name)
        etf      = SECTOR_ETFS[name]

        rotating    = False
        strength_flip = False
        if curr_ret is not None and prev_ret is not None:
            rotating      = (prev_ret < 0 < curr_ret) or (prev_ret > 0 > curr_ret) or (curr_ret > prev_ret + 3)
            strength_flip = (prev_ret < 0 < curr_ret)

        sectors[name] = {
            "etf":          etf,
            "return_30d":   curr_ret,
            "return_1y_ago":prev_ret,
            "rotating":     rotating,
            "flip":         strength_flip,
            "direction":    "UP" if (curr_ret or 0) > 0 else "DOWN",
        }

    # For rotating sectors, get top ETF money flows
    etf_flows = {}
    rotating_sectors = {k:v for k,v in sectors.items() if v["rotating"]}

    for sec_name in list(rotating_sectors.keys())[:4]:
        etfs   = TOP_ETFS_PER_SECTOR.get(sec_name, [])
        flows  = []
        for e in etfs:
            f = get_etf_money_flow(e)
            if "error" not in f:
                flows.append(f)
            time.sleep(0.1)
        flows.sort(key=lambda x: x.get("money_flow", 0) or 0, reverse=True)
        etf_flows[sec_name] = flows

    ranked = sorted(
        [(k, v["return_30d"]) for k, v in sectors.items() if v["return_30d"] is not None],
        key=lambda x: x[1], reverse=True
    )

    return {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "sectors":   sectors,
        "rotating":  rotating_sectors,
        "etf_flows": etf_flows,
        "ranked":    ranked,
    }
