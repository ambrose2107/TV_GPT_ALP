"""
test_bot.py — Test suite
Run with: python test_bot.py
Tests webhook handler, config, DB, and Alpaca adapter (mock).
No real API calls made.
"""
import os, sys, json, unittest
from unittest.mock import patch, MagicMock

# ── Set dummy env vars before importing anything ──────────────────────────────
os.environ.setdefault("ALPACA_API_KEY",    "TEST_KEY")
os.environ.setdefault("ALPACA_SECRET_KEY", "TEST_SECRET")
os.environ.setdefault("ALPACA_MODE",       "paper")
os.environ.setdefault("WEBHOOK_SECRET",    "test_secret_123")
os.environ.setdefault("APP_SECRET_KEY",    "test_app_secret")
os.environ.setdefault("DASHBOARD_PASSWORD","testpass")
os.environ.setdefault("DB_PATH",           ":memory:")  # in-memory DB for tests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── 1. Config Tests ───────────────────────────────────────────────────────────
class TestConfig(unittest.TestCase):
    def test_alpaca_mode_paper(self):
        from core.config import Config
        self.assertEqual(Config.ALPACA_MODE, "paper")

    def test_base_url_is_paper(self):
        from core.config import Config
        self.assertIn("paper-api", Config.ALPACA_BASE_URL)

    def test_webhook_secret_loaded(self):
        from core.config import Config
        self.assertEqual(Config.WEBHOOK_SECRET, "test_secret_123")

    def test_kill_switch_off(self):
        from core.config import Config
        self.assertFalse(Config.KILL_SWITCH)


# ── 2. Database Tests ─────────────────────────────────────────────────────────
class TestDatabase(unittest.TestCase):
    def setUp(self):
        os.environ["DB_PATH"] = ":memory:"
        # Re-init DB for each test
        import importlib
        import core.database as db_mod
        importlib.reload(db_mod)
        db_mod.init_db()
        self.db = db_mod

    def test_log_and_retrieve_trade(self):
        self.db.log_trade("AAPL", "buy", 5, "market", "placed", "order-123")
        trades = self.db.get_recent_trades(10)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["symbol"], "AAPL")
        self.assertEqual(trades[0]["action"], "buy")
        self.assertEqual(trades[0]["status"], "placed")

    def test_log_and_retrieve_webhook(self):
        self.db.log_webhook({"secret": "x", "action": "buy"}, "success")
        wh = self.db.get_recent_webhooks(10)
        self.assertEqual(len(wh), 1)
        self.assertEqual(wh[0]["status"], "success")

    def test_multiple_trades(self):
        self.db.log_trade("AAPL", "buy",  3, "market", "placed")
        self.db.log_trade("TSLA", "sell", 1, "market", "placed")
        trades = self.db.get_recent_trades(10)
        self.assertEqual(len(trades), 2)

    def test_failed_trade(self):
        self.db.log_trade("AAPL", "buy", 1, "market", "failed", message="Insufficient funds")
        trades = self.db.get_recent_trades(10)
        self.assertEqual(trades[0]["status"], "failed")
        self.assertIn("Insufficient", trades[0]["message"])


# ── 3. Webhook Handler Tests ─────────────────────────────────────────────────
class TestWebhookHandler(unittest.TestCase):
    def setUp(self):
        os.environ["DB_PATH"] = ":memory:"
        from core.database import reset_memory_db, init_db
        reset_memory_db()
        init_db()

    @patch("webhook.handler.alpaca")
    def test_valid_buy_signal(self, mock_alpaca):
        mock_alpaca.place_market_order.return_value = {"id": "ord-001", "status": "accepted"}
        mock_alpaca.get_position.return_value = None

        from webhook.handler import process_webhook
        result = process_webhook({
            "secret":   "test_secret_123",
            "symbol":   "AAPL",
            "action":   "buy",
            "quantity": 2
        })
        self.assertTrue(result["success"])
        self.assertIn("BUY", result["message"])
        mock_alpaca.place_market_order.assert_called_once_with("AAPL", "buy", 2.0)

    @patch("webhook.handler.alpaca")
    def test_valid_sell_signal(self, mock_alpaca):
        mock_alpaca.place_market_order.return_value = {"id": "ord-002", "status": "accepted"}
        mock_alpaca.get_position.return_value = None

        from webhook.handler import process_webhook
        result = process_webhook({
            "secret":   "test_secret_123",
            "symbol":   "TSLA",
            "action":   "sell",
            "quantity": 1
        })
        self.assertTrue(result["success"])
        self.assertIn("SELL", result["message"])

    @patch("webhook.handler.alpaca")
    def test_flip_closes_long_before_sell(self, mock_alpaca):
        """Buy-Sell flip: selling when long position exists should close long first."""
        mock_alpaca.get_position.return_value = {"qty": "5"}   # long position open
        mock_alpaca.close_position.return_value = {}
        mock_alpaca.place_market_order.return_value = {"id": "ord-003", "status": "accepted"}

        from webhook.handler import process_webhook
        result = process_webhook({
            "secret":   "test_secret_123",
            "symbol":   "AAPL",
            "action":   "sell",
            "quantity": 5
        })
        self.assertTrue(result["success"])
        mock_alpaca.close_position.assert_called_once_with("AAPL")

    def test_wrong_secret_rejected(self):
        from webhook.handler import process_webhook
        result = process_webhook({
            "secret":   "wrong_secret",
            "symbol":   "AAPL",
            "action":   "buy",
            "quantity": 1
        })
        self.assertFalse(result["success"])
        self.assertIn("Invalid", result["message"])

    def test_invalid_action_rejected(self):
        from webhook.handler import process_webhook
        result = process_webhook({
            "secret":   "test_secret_123",
            "symbol":   "AAPL",
            "action":   "hold",    # not valid
            "quantity": 1
        })
        self.assertFalse(result["success"])

    def test_zero_quantity_rejected(self):
        from webhook.handler import process_webhook
        result = process_webhook({
            "secret":   "test_secret_123",
            "symbol":   "AAPL",
            "action":   "buy",
            "quantity": 0
        })
        self.assertFalse(result["success"])

    def test_exceeds_max_position_size(self):
        from core.config import Config
        from webhook.handler import process_webhook
        result = process_webhook({
            "secret":   "test_secret_123",
            "symbol":   "AAPL",
            "action":   "buy",
            "quantity": Config.MAX_POSITION_SIZE + 100
        })
        self.assertFalse(result["success"])
        self.assertIn("MAX_POSITION_SIZE", result["message"])

    def test_missing_symbol_rejected(self):
        from webhook.handler import process_webhook
        result = process_webhook({
            "secret":   "test_secret_123",
            "symbol":   "",
            "action":   "buy",
            "quantity": 1
        })
        self.assertFalse(result["success"])

    def test_kill_switch_blocks_trade(self):
        import core.config as cfg
        original = cfg.Config.KILL_SWITCH
        cfg.Config.KILL_SWITCH = True
        try:
            from webhook.handler import process_webhook
            result = process_webhook({
                "secret":   "test_secret_123",
                "symbol":   "AAPL",
                "action":   "buy",
                "quantity": 1
            })
            self.assertFalse(result["success"])
            self.assertIn("Kill switch", result["message"])
        finally:
            cfg.Config.KILL_SWITCH = original


# ── 4. Flask Route Tests ─────────────────────────────────────────────────────
class TestFlaskRoutes(unittest.TestCase):
    def setUp(self):
        os.environ["DB_PATH"] = ":memory:"
        from core.database import reset_memory_db, init_db
        reset_memory_db()
        init_db()
        from app import create_app
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def test_health_endpoint(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertEqual(data["status"], "ok")

    def test_webhook_bad_json(self):
        r = self.client.post("/webhook",
            data="not json",
            content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_webhook_wrong_secret(self):
        r = self.client.post("/webhook",
            json={"secret": "bad", "symbol": "AAPL", "action": "buy", "quantity": 1})
        self.assertEqual(r.status_code, 400)

    @patch("webhook.handler.alpaca")
    def test_webhook_valid_buy(self, mock_alpaca):
        mock_alpaca.place_market_order.return_value = {"id": "ord-999"}
        mock_alpaca.get_position.return_value = None

        r = self.client.post("/webhook", json={
            "secret":   "test_secret_123",
            "symbol":   "AAPL",
            "action":   "buy",
            "quantity": 1
        })
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertTrue(data["success"])

    def test_dashboard_redirects_to_login(self):
        r = self.client.get("/")
        self.assertIn(r.status_code, [302, 200])

    def test_login_page_loads(self):
        r = self.client.get("/login")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Trading Bot", r.data)


# ── 5. Symbol Validation Tests ───────────────────────────────────────────────
class TestSymbolValidation(unittest.TestCase):
    """Tests for the new symbol validation — no real API calls, all mocked."""

    def setUp(self):
        os.environ["DB_PATH"] = ":memory:"
        from core.database import reset_memory_db, init_db
        reset_memory_db()
        init_db()

    @patch("brokers.alpaca_adapter.requests.request")
    def test_nasdaq_rejected_with_suggestion(self, mock_req):
        """NASDAQ should be caught immediately by SYMBOL_SUGGESTIONS — no API call needed."""
        from brokers.alpaca_adapter import AlpacaAdapter
        adapter = AlpacaAdapter()
        result = adapter.validate_symbol("NASDAQ")
        self.assertFalse(result["valid"])
        self.assertEqual(result["suggestion"], "QQQ")
        self.assertIn("QQQ", result["message"])
        mock_req.assert_not_called()   # caught before any API call

    @patch("brokers.alpaca_adapter.requests.request")
    def test_indian_symbol_rejected(self, mock_req):
        """NIFTY/SENSEX should be rejected as Indian market."""
        from brokers.alpaca_adapter import AlpacaAdapter
        adapter = AlpacaAdapter()
        result = adapter.validate_symbol("NIFTY")
        self.assertFalse(result["valid"])
        self.assertIsNone(result["suggestion"])
        self.assertIn("Indian", result["message"])

    @patch("brokers.alpaca_adapter.requests.request")
    def test_valid_us_symbol_passes(self, mock_req):
        """AAPL should pass validation when Alpaca returns tradeable=True."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"tradable": true, "status": "active"}'
        mock_resp.json.return_value = {"tradable": True, "status": "active"}
        mock_resp.raise_for_status = MagicMock()
        mock_req.return_value = mock_resp

        from brokers.alpaca_adapter import AlpacaAdapter
        adapter = AlpacaAdapter()
        result = adapter.validate_symbol("AAPL")
        self.assertTrue(result["valid"])

    @patch("brokers.alpaca_adapter.requests.request")
    def test_unknown_symbol_404(self, mock_req):
        """Unknown symbol returns 404 → should be rejected with helpful message."""
        import requests as req_lib
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        http_error = req_lib.exceptions.HTTPError(response=mock_resp)
        mock_resp.raise_for_status.side_effect = http_error
        mock_req.return_value = mock_resp

        from brokers.alpaca_adapter import AlpacaAdapter
        adapter = AlpacaAdapter()
        result = adapter.validate_symbol("FAKESYMBOL")
        self.assertFalse(result["valid"])
        self.assertIn("not found", result["message"])

    @patch("webhook.handler.alpaca")
    def test_nasdaq_blocked_in_full_webhook_flow(self, mock_alpaca):
        """Full flow: NASDAQ as symbol should be caught and rejected before order placement."""
        mock_alpaca.validate_symbol.return_value = {
            "valid": False,
            "message": "'NASDAQ' is not a stock ticker. Did you mean 'QQQ'?",
            "suggestion": "QQQ"
        }
        from webhook.handler import process_webhook
        result = process_webhook({
            "secret":   "test_secret_123",
            "symbol":   "NASDAQ",
            "action":   "sell",
            "quantity": 10
        })
        self.assertFalse(result["success"])
        self.assertIn("QQQ", result["message"])
        mock_alpaca.place_market_order.assert_not_called()

    @patch("webhook.handler.alpaca")
    def test_spy_passes_validation_and_executes(self, mock_alpaca):
        """SPY should pass validation and place order normally."""
        mock_alpaca.validate_symbol.return_value = {"valid": True, "message": "OK", "suggestion": None}
        mock_alpaca.get_position.return_value = None
        mock_alpaca.place_market_order.return_value = {"id": "ord-spy-001"}

        from webhook.handler import process_webhook
        result = process_webhook({
            "secret":   "test_secret_123",
            "symbol":   "SPY",
            "action":   "buy",
            "quantity": 2
        })
        self.assertTrue(result["success"])
        mock_alpaca.place_market_order.assert_called_once_with("SPY", "buy", 2.0)


# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "="*60)
    print("  OptiTrade → Alpaca Bot — Test Suite")
    print("="*60 + "\n")
    loader = unittest.TestLoader()
    suite  = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestConfig))
    suite.addTests(loader.loadTestsFromTestCase(TestDatabase))
    suite.addTests(loader.loadTestsFromTestCase(TestWebhookHandler))
    suite.addTests(loader.loadTestsFromTestCase(TestFlaskRoutes))
    suite.addTests(loader.loadTestsFromTestCase(TestSymbolValidation))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    print("\n" + "="*60)
    if result.wasSuccessful():
        print("  ✅ ALL TESTS PASSED")
    else:
        print(f"  ❌ {len(result.failures)} FAILED, {len(result.errors)} ERRORS")
    print("="*60 + "\n")
    sys.exit(0 if result.wasSuccessful() else 1)
