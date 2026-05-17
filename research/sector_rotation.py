"""
research/sector_rotation.py — Real sector rotation using unified data engine
"""
import time
from datetime import datetime
from core.market_data import get_bars, get_multi_quotes
from core.logger import get_logger

logger = get_logger(__name__)

SECTOR_ETFS = {
    "Technology":       "XLK",  "Healthcare":       "XLV",
    "Financials":       "XLF",  "Consumer Discr.":  "XLY",
    "Industrials":      "XLI",  "Communication":    "XLC",
    "Consumer Staples": "XLP",  "Energy":           "XLE",
    "Materials":        "XLB",  "Utilities":        "XLU",
    "Real Estate":      "XLRE",
}

TOP_ETFS = {
    "Technology":       ["QQQ","SOXX","IGV","VGT","ARKK"],
    "Healthcare":       ["IBB","XBI","IHI","ARKG","IHF"],
    "Financials":       ["KBE","KRE","IAI","KBWB","IYF"],
    "Consumer Discr.":  ["XRT","RTH","FDIS","IBUY","VCR"],
    "Industrials":      ["ITA","XAR","JETS","PAVE","VIS"],
    "Communication":    ["FCOM","VOX","IYZ","SOCL","ESPO"],
    "Consumer Staples": ["VDC","KXI","FSTA","IYK","PBJ"],
    "Energy":           ["OIH","XOP","FCG","AMLP","IEZ"],
    "Materials":        ["GDX","GDXJ","MOO","MXI","URNM"],
    "Utilities":        ["VPU","FXU","IDU","FUTY","RYU"],
    "Real Estate":      ["VNQ","IYR","SCHH","RWR","REZ"],
}

def _pct_return(bars, window):
    closes = [b["c"] for b in bars if b.get("c")]
    if len(closes) < window: return None
    return round((closes[-1]/closes[-window]-1)*100, 2)

def get_sector_rotation() -> dict:
    logger.info("Running sector rotation...")
    sectors = {}
    source  = "demo"

    for name, etf in SECTOR_ETFS.items():
        bars = get_bars(etf, "1D")
        if not bars:
            sectors[name] = {"etf": etf, "return_30d": None, "return_1y_ago": None}
            continue
        if bars and bars[0].get("source") != "demo":
            source = "live"

        ret_30  = _pct_return(bars, 22)   # ~22 trading days
        # 1yr ago: use bars from ~252 days back
        ret_prior = None
        if len(bars) >= 282:
            prior_slice = bars[-282:-252]
            if len(prior_slice) >= 22:
                c = [b["c"] for b in prior_slice if b.get("c")]
                if len(c) >= 2:
                    ret_prior = round((c[-1]/c[0]-1)*100, 2)

        rotating = False
        flip     = False
        if ret_30 is not None and ret_prior is not None:
            rotating = (ret_prior < 0 < ret_30) or (ret_prior > 0 > ret_30) or (ret_30 > ret_prior + 3)
            flip     = (ret_prior < 0 < ret_30)

        sectors[name] = {
            "etf":          etf,
            "return_30d":   ret_30,
            "return_1y_ago":ret_prior,
            "rotating":     rotating,
            "flip":         flip,
        }
        time.sleep(0.05)

    # ETF money flows for rotating sectors
    rotating = {k:v for k,v in sectors.items() if v.get("rotating")}
    etf_flows = {}
    for sec_name in list(rotating.keys())[:4]:
        etfs  = TOP_ETFS.get(sec_name, [])
        flows = []
        for etf in etfs:
            bars = get_bars(etf, "1D")
            if not bars: continue
            closes = [b["c"] for b in bars if b.get("c")]
            vol    = [b.get("v",0) for b in bars]
            r10    = _pct_return(bars, 10)
            r30    = _pct_return(bars, 22)
            avg_vol= sum(vol[-10:])/10 if len(vol)>=10 else 0
            price  = closes[-1] if closes else 0
            flows.append({
                "ticker":    etf,
                "price":     round(price,2),
                "return_10": r10,
                "return_30": r30,
                "avg_volume":int(avg_vol),
                "money_flow":round(price*avg_vol/1e6,1),
            })
            time.sleep(0.05)
        flows.sort(key=lambda x: x.get("money_flow",0) or 0, reverse=True)
        etf_flows[sec_name] = flows

    ranked = sorted(
        [(k,v["return_30d"]) for k,v in sectors.items() if v["return_30d"] is not None],
        key=lambda x: x[1], reverse=True
    )

    return {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "data_source": source,
        "sectors":   sectors,
        "rotating":  rotating,
        "etf_flows": etf_flows,
        "ranked":    ranked,
    }
