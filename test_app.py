import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import app as payagent


class PayAgentDemoTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db = payagent.DB_PATH
        payagent.DB_PATH = Path(self.temp_dir.name) / "test.db"
        payagent.init_db()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), payagent.PayAgentHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        payagent.DB_PATH = self.original_db
        self.temp_dir.cleanup()

    def post_json(self, path, payload):
        request = urllib.request.Request(self.base + path, data=json.dumps(payload).encode(),
                                         headers={"Content-Type":"application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.status, json.loads(response.read().decode())

    def get_json(self, path):
        with urllib.request.urlopen(self.base + path, timeout=3) as response:
            return response.status, json.loads(response.read().decode())

    def test_home_serves_frontend_and_assets(self):
        with urllib.request.urlopen(self.base + "/", timeout=3) as response:
            html = response.read().decode()
            self.assertEqual(response.status, 200)
        self.assertIn('href="style.css"', html)
        self.assertIn('src="app.js"', html)
        for path in ("/style.css", "/app.js"):
            with urllib.request.urlopen(self.base + path, timeout=3) as response:
                self.assertEqual(response.status, 200)
                self.assertGreater(len(response.read()), 0)

    def test_offer_inside_floor_is_accepted(self):
        result = payagent.negotiate("watch-pro", 1, "Can you do $115?")
        self.assertTrue(result["accepted"])
        self.assertEqual(result["suggested_price"], 115.0)
        self.assertEqual(result["decision"], "OFFER_ACCEPTED")

    def test_low_offer_gets_counter_offer(self):
        result = payagent.negotiate("watch-pro", 1, "Can you do $70?")
        self.assertFalse(result["accepted"])
        self.assertEqual(result["decision"], "COUNTER_OFFER")
        self.assertGreaterEqual(result["suggested_price"], result["floor_price"])

    def test_best_member_price_uses_quantity_discount(self):
        one = payagent.negotiate("watch-pro", 1, "")
        two = payagent.negotiate("watch-pro", 2, "")
        self.assertLess(two["suggested_price"], one["suggested_price"])

    def test_invalid_quantity_is_rejected(self):
        with self.assertRaises(ValueError):
            payagent.negotiate("watch-pro", 6, "")

    def test_high_risk_checkout_enters_review_queue(self):
        status, data = self.post_json("/api/checkout", {
            "product_id":"watch-pro", "quantity":5, "unit_price":110.0,
            "device_new":True, "country_mismatch":True, "buyer_message":"Judge demo transaction"
        })
        self.assertEqual(status, 200)
        self.assertTrue(data["simulated"])
        self.assertEqual(data["risk"]["level"], "HIGH")
        self.assertEqual(data["risk"]["status"], "REVIEW_REQUIRED")

    def test_state_returns_seed_transactions(self):
        status, data = self.get_json("/api/state")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(data["stats"]["total_transactions"], 4)
        self.assertEqual(len(data["products"]), 4)

    def test_resolve_action_changes_status(self):
        status, _ = self.post_json("/api/transactions/PA-10426/action", {"action":"resolve"})
        self.assertEqual(status, 200)
        _, detail = self.get_json("/api/transactions/PA-10426")
        self.assertEqual(detail["transaction"]["status"], "RESOLVED")

    def test_checkout_rejects_price_below_merchant_floor(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post_json("/api/checkout", {"product_id":"watch-pro", "quantity":1, "unit_price":10})
        self.assertEqual(ctx.exception.code, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
