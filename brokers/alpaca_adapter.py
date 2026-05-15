"""
brokers/alpaca_adapter.py — Alpaca API wrapper
Handles BUY, SELL, close position, get positions, symbol validation
"""
import requests
from core.logger import get_logger
from core.config import Config

logger = get_logger(__name__)

# Common mistakes → correct Alpaca symbol
SYMBOL_SUGGESTIONS = {
    "NASDAQ":   "QQQ",
    "NASDAQ100":"QQQ",
    "NDX":      "QQQ",
    "SP500":    "SPY",
    "S&P500":   "SPY",
    "S&P":      "SPY",
    "DOW":      "DIA",
    "DOWJONES": "DIA",
    "RUSSELL":  "IWM",
    "NIFTY":    None,     # Indian index — not on Alpaca
    "SENSEX":   None,
    "SILVER":   "SLV",
    "GOLD":     "GLD",
    "OIL":      "USO",
    "BITCOIN":  "BITO",
    "BTC":      "BITO",
}

class AlpacaAdapter:
    def __init__(self):
        self.api_key    = Config.ALPACA_API_KEY
        self.secret_key = Config.ALPACA_SECRET_KEY
        self.base_url   = Config.ALPACA_BASE_URL
        self.headers = {
            "APCA-API-KEY-ID":     self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
            "Content-Type":        "application/json"
        }

    def _request(self, method, endpoint, payload=None):
        url = f"{self.base_url}{endpoint}"
        try:
            resp = requests.request(method, url, headers=self.headers, json=payload, timeout=10)
            resp.raise_for_status()
            return resp.json() if resp.text else {}
        except requests.exceptions.HTTPError as e:
            logger.error(f"Alpaca HTTP error: {e} | Response: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Alpaca request error: {e}")
            raise

    def validate_symbol(self, symbol: str) -> dict:
        """
        Check if a symbol is valid and tradeable on Alpaca.
        Returns: { "valid": bool, "message": str, "suggestion": str|None }
        """
        symbol = symbol.upper().strip()

        # Check common wrong names first
        if symbol in SYMBOL_SUGGESTIONS:
            suggestion = SYMBOL_SUGGESTIONS[symbol]
            if suggestion is None:
                return {
                    "valid": False,
                    "message": f"'{symbol}' is an Indian market instrument and is NOT available on Alpaca. Alpaca only supports US stocks/ETFs.",
                    "suggestion": None
                }
            return {
                "valid": False,
                "message": f"'{symbol}' is not a stock ticker — it's an index/exchange name. Did you mean '{suggestion}'?",
                "suggestion": suggestion
            }

        # Check with Alpaca assets endpoint
        try:
            asset = self._request("GET", f"/v2/assets/{symbol}")
            if not asset.get("tradable", False):
                return {
                    "valid": False,
                    "message": f"'{symbol}' exists on Alpaca but is NOT currently tradeable.",
                    "suggestion": None
                }
            if asset.get("status") != "active":
                return {
                    "valid": False,
                    "message": f"'{symbol}' is not active on Alpaca (status: {asset.get('status')}).",
                    "suggestion": None
                }
            return {"valid": True, "message": "OK", "suggestion": None}
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return {
                    "valid": False,
                    "message": f"'{symbol}' was not found on Alpaca. Check the ticker is a valid US stock/ETF symbol.",
                    "suggestion": None
                }
            # If Alpaca API itself is down, allow through with a warning
            logger.warning(f"Could not validate symbol {symbol} — Alpaca assets API error: {e}")
            return {"valid": True, "message": "Validation skipped (API unavailable)", "suggestion": None}
        except Exception as e:
            logger.warning(f"Symbol validation skipped for {symbol}: {e}")
            return {"valid": True, "message": "Validation skipped", "suggestion": None}

    def get_account(self):
        return self._request("GET", "/v2/account")

    def get_positions(self):
        return self._request("GET", "/v2/positions")

    def get_position(self, symbol):
        try:
            return self._request("GET", f"/v2/positions/{symbol}")
        except:
            return None

    def place_market_order(self, symbol: str, side: str, qty: float):
        payload = {
            "symbol":        symbol.upper(),
            "qty":           str(qty),
            "side":          side.lower(),
            "type":          "market",
            "time_in_force": "day"
        }
        logger.info(f"Placing {side.upper()} {qty} {symbol} @ MARKET")
        return self._request("POST", "/v2/orders", payload)

    def place_limit_order(self, symbol: str, side: str, qty: float, limit_price: float):
        payload = {
            "symbol":        symbol.upper(),
            "qty":           str(qty),
            "side":          side.lower(),
            "type":          "limit",
            "limit_price":   str(round(limit_price, 2)),
            "time_in_force": "day"
        }
        logger.info(f"Placing {side.upper()} {qty} {symbol} @ LIMIT {limit_price}")
        return self._request("POST", "/v2/orders", payload)

    def close_position(self, symbol: str):
        logger.info(f"Closing position for {symbol}")
        try:
            return self._request("DELETE", f"/v2/positions/{symbol}")
        except Exception as e:
            logger.warning(f"Could not close position for {symbol}: {e}")
            return None

    def close_all_positions(self):
        logger.warning("CLOSING ALL POSITIONS")
        return self._request("DELETE", "/v2/positions")

    def cancel_all_orders(self):
        logger.info("Cancelling all open orders")
        return self._request("DELETE", "/v2/orders")

    def get_open_orders(self):
        return self._request("GET", "/v2/orders?status=open")
