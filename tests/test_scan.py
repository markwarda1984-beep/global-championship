import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import scan


class ScannerTests(unittest.TestCase):
    def test_30_unique_watchlist_stocks(self):
        stocks = scan.load_watchlist(scan.BASE / "watchlist.csv")
        self.assertEqual(len(stocks), 30)
        self.assertEqual(len({s["ticker"] for s in stocks}), 30)
        self.assertEqual([s["ticker"] for s in stocks if s["buy_price"]], ["BABA"])
        self.assertEqual(next(s["status"] for s in stocks if s["ticker"] == "NVDA"), "NO BUY")

    def test_target_math_is_explicit_and_provisional(self):
        self.assertEqual(scan.distance_above_target(90.0, "75"), 20.0)
        self.assertEqual(scan.distance_above_target(60.0, "75"), -20.0)
        self.assertIsNone(scan.distance_above_target(90.0, ""))
        self.assertEqual(scan.currency_for("BHP.AX"), "AUD")
        self.assertEqual(scan.currency_for("NVDA"), "USD")

    def test_sparkline_does_not_need_internet(self):
        self.assertIn("<svg", scan.sparkline([10, 11, 9, 12]))
        self.assertEqual(scan.sparkline([]), "—")

    def test_full_scan_with_injected_offline_market_feeds(self):
        def fake_stock(ticker):
            if ticker == "SLS":
                raise RuntimeError("ticker not available")
            return {"price": 90.0, "quote_date": "2026-11-19T00:00:00-05:00", "history": [85, 89, 90]}

        def fake_btc(pair):
            return {"last": 100000.0 if pair == "XBTAUD" else 65000.0, "bid": 99999.0, "ask": 100001.0}

        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            result = scan.run_scan(output=output, stock_fetcher=fake_stock, btc_fetcher=fake_btc,
                                   now=datetime(2026, 11, 20, 5, 0, tzinfo=timezone.utc))
            self.assertEqual(result["stock_quotes_available"], 29)
            self.assertEqual(result["funding_status"], "NOT_YET_FUNDED")
            self.assertFalse(result["trade_execution_enabled"])
            self.assertEqual(result["confirmed_holdings"], [])
            self.assertEqual(result["scan_sydney"], "2026-11-20T16:00:00+11:00")
            self.assertEqual(result["bitcoin"]["XBTAUD"]["last"], 100000.0)
            self.assertTrue(all((output / filename).is_file() for filename in ("latest.csv", "latest.json", "index.html")))
            doc = json.loads((output / "latest.json").read_text())
            self.assertEqual(len(doc["stocks"]), 30)
            self.assertIn("Bitcoin", (output / "index.html").read_text())
            self.assertIn("<svg", (output / "index.html").read_text())
            self.assertIn("UNAVAILABLE", (output / "latest.csv").read_text())

    def test_feed_errors_do_not_turn_into_fake_prices(self):
        with tempfile.TemporaryDirectory() as folder:
            result = scan.run_scan(output=Path(folder),
                                   stock_fetcher=lambda _: (_ for _ in ()).throw(RuntimeError("offline")),
                                   btc_fetcher=lambda _: (_ for _ in ()).throw(RuntimeError("offline")))
            self.assertEqual(result["stock_quotes_available"], 0)
            self.assertTrue(all(r["price"] is None for r in result["stocks"]))
            self.assertEqual(set(result["bitcoin"]), {"XBTAUD", "XBTUSD"})
            self.assertIn("error", result["bitcoin"]["XBTUSD"])


if __name__ == "__main__":
    unittest.main()
