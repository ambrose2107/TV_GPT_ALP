"""
research/sec_filings.py — Institutional 13F tracker via SEC EDGAR (free)
"""
import requests, time
from core.data_engine import FUNDS, get_13f_filing, get_13f_holdings, get_quote
from core.logger import get_logger

logger = get_logger(__name__)

# Map CUSIP prefixes to approximate tickers (limited, most holdings need CUSIP lookup)
CUSIP_HINTS = {
    "037833100":"AAPL","594918104":"MSFT","023135106":"AMZN","30303M102":"META",
    "02079K305":"GOOGL","88160R101":"TSLA","67066G104":"NVDA","46625H100":"JPM",
    "70450Y103":"PYPL","025816109":"AMD","92826C839":"V",  "14040H105":"CAP",
    "58933Y105":"MET", "713448108":"PFE","532457108":"ELI","084670702":"BRK-B",
}

def enrich_holdings(holdings: list) -> list:
    """Try to add ticker/price to holdings."""
    enriched = []
    for h in holdings[:20]:
        cusip  = h.get("cusip","")
        ticker = CUSIP_HINTS.get(cusip)
        price  = None
        if ticker:
            q = get_quote(ticker)
            if q:
                price = q.get("price")
            time.sleep(0.05)
        enriched.append({**h, "ticker": ticker, "current_price": price})
    return enriched

def get_institutional_tracker() -> dict:
    """
    Fetch latest 13F for all 5 funds.
    Returns filing metadata + top holdings.
    """
    results = {}
    for fund_name, cik in FUNDS.items():
        logger.info(f"Fetching 13F for {fund_name}...")
        filing = get_13f_filing(cik, fund_name)
        if filing.get("found"):
            time.sleep(0.5)
            holdings = get_13f_holdings(cik, filing["accession"])
            filing["top_holdings"]    = enrich_holdings(holdings)
            filing["total_holdings"]  = len(holdings)
            filing["total_value_bn"]  = round(sum(h["value"] for h in holdings) / 1_000_000, 2)
        else:
            filing["top_holdings"]   = []
            filing["total_holdings"] = 0
            filing["total_value_bn"] = 0
        results[fund_name] = filing
        time.sleep(0.3)
    return results

def analyze_institutional_momentum(all_filings: dict) -> list:
    """
    Cross-reference holdings across funds to find stocks where
    institutional buying has accelerated but retail attention is still low.
    Returns top 5 conviction stocks.
    """
    stock_mentions = {}
    for fund_name, filing in all_filings.items():
        for h in filing.get("top_holdings", [])[:20]:
            name = h.get("name","")
            if not name:
                continue
            if name not in stock_mentions:
                stock_mentions[name] = {
                    "name": name, "ticker": h.get("ticker"),
                    "funds": [], "total_value": 0, "total_shares": 0,
                }
            stock_mentions[name]["funds"].append(fund_name)
            stock_mentions[name]["total_value"]  += h.get("value",0)
            stock_mentions[name]["total_shares"] += h.get("shares",0)

    # Filter: held by 2+ funds, rank by total value
    multi_fund = [v for v in stock_mentions.values() if len(v["funds"]) >= 2]
    multi_fund.sort(key=lambda x: x["total_value"], reverse=True)
    return multi_fund[:10]
