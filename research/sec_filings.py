"""
research/sec_filings.py — Institutional footprint tracker
Pulls 13F filings from SEC EDGAR for major funds
"""
import requests
import json
from core.logger import get_logger

logger = get_logger(__name__)

HEADERS = {"User-Agent": "TradingBot research@tradingbot.com"}

FUNDS = {
    "Berkshire Hathaway": "0001067983",
    "Bridgewater Associates": "0001350694",
    "Renaissance Technologies": "0001037389",
    "Citadel": "0001423689",
    "Two Sigma": "0001448942",
}

def get_latest_13f(cik: str, fund_name: str) -> dict:
    """Fetch latest 13F filing for a given CIK."""
    try:
        url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        filings = data.get("filings", {}).get("recent", {})
        forms   = filings.get("form", [])
        accNums = filings.get("accessionNumber", [])
        dates   = filings.get("filingDate", [])

        # Find latest 13F-HR
        for i, form in enumerate(forms):
            if form == "13F-HR":
                acc = accNums[i].replace("-", "")
                return {
                    "fund":      fund_name,
                    "cik":       cik,
                    "accession": accNums[i],
                    "date":      dates[i],
                    "url":       f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/",
                }
        return {"fund": fund_name, "error": "No 13F-HR found"}
    except Exception as e:
        logger.warning(f"SEC fetch error for {fund_name}: {e}")
        return {"fund": fund_name, "error": str(e)}


def get_13f_holdings(cik: str, accession: str) -> list:
    """Parse holdings from 13F filing index."""
    try:
        acc_clean = accession.replace("-", "")
        idx_url   = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/{accession}-index.json"
        resp      = requests.get(idx_url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        idx_data  = resp.json()

        # Find the primary document (infotable xml or primary doc)
        files = idx_data.get("directory", {}).get("item", [])
        xml_file = None
        for f in files:
            name = f.get("name", "").lower()
            if "infotable" in name and name.endswith(".xml"):
                xml_file = f["name"]
                break
            if name.endswith(".xml") and "primary" not in name and "form13f" not in name:
                xml_file = f["name"]

        if not xml_file:
            return []

        xml_url  = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/{xml_file}"
        xml_resp = requests.get(xml_url, headers=HEADERS, timeout=20)
        xml_resp.raise_for_status()

        # Simple XML parse for holdings
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml_resp.text)
        ns   = {"ns": "http://www.sec.gov/edgar/document/thirteenf/informationtable"}

        holdings = []
        for info in root.findall(".//ns:infoTable", ns) or root.findall(".//infoTable"):
            try:
                ns_tag = lambda tag: info.find(f"ns:{tag}", ns) or info.find(tag)
                name_el  = ns_tag("nameOfIssuer")
                val_el   = ns_tag("value")
                shrte_el = ns_tag("sshPrnamt")
                ticker_el= ns_tag("cusip")

                holdings.append({
                    "name":   name_el.text.strip()  if name_el  else "",
                    "value":  int(val_el.text)       if val_el   else 0,
                    "shares": int(shrte_el.text)     if shrte_el else 0,
                    "cusip":  ticker_el.text.strip() if ticker_el else "",
                })
            except:
                continue
        return sorted(holdings, key=lambda x: x["value"], reverse=True)[:30]
    except Exception as e:
        logger.warning(f"Holdings parse error: {e}")
        return []


def get_institutional_tracker() -> dict:
    """
    Main function — returns data for all 5 funds.
    Returns latest filing info + top holdings per fund.
    """
    results = {}
    for fund_name, cik in FUNDS.items():
        logger.info(f"Fetching 13F for {fund_name}...")
        filing = get_latest_13f(cik, fund_name)
        if "error" not in filing:
            holdings = get_13f_holdings(cik, filing["accession"])
            filing["top_holdings"] = holdings[:10]
            filing["total_holdings"] = len(holdings)
        else:
            filing["top_holdings"] = []
        results[fund_name] = filing

    return results
