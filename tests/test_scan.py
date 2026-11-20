import csv
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import scan


class Intensive200Tests(unittest.TestCase):
    def test_exactly_200_unique_with_original_watchlist_preserved(self):
        rows = scan.load_watchlist(scan.BASE / "watchlist.csv")
        self.assertEqual(len(rows), 200)
        self.assertEqual(len({r["ticker"] for r in rows}), 200)
        self.assertEqual(rows[0]["ticker"], "BABA")
        self.assertEqual(rows[4]["ticker"], "NVDA")
        self.assertEqual(rows[0]["buy_validation"], "PROVISIONAL")
        self.assertEqual(rows[0]["buy_price"], "75")
        self.assertTrue(all("sector" in r for r in rows))

    def test_all_200_receive_same_quantitative_metrics(self):
        now = datetime(2026, 11, 20, 8, tzinfo=timezone.utc)
        seen_chunks = []
        def batch_fetcher(tickers):
            seen_chunks.append(tickers)
            return {s: self.mock_quote() for s in tickers}
        with tempfile.TemporaryDirectory() as folder:
            result = scan.run_scan(output=Path(folder), now=now,
                                   batch_fetcher=batch_fetcher, btc_fetcher=self.mock_btc)
            self.assertEqual(len(seen_chunks), 8)
            self.assertTrue(all(len(chunk) == 25 for chunk in seen_chunks))
            self.assertEqual(result["stock_quotes_available"], 200)
            self.assertEqual(result["validated_buy_count"], 0)
            self.assertEqual(len(result["stocks"]), 200)
            self.assertTrue(all(r["rsi_14"] is not None for r in result["stocks"]))
            self.assertTrue(all(r["technical_watch_zone"] is not None for r in result["stocks"]))
            self.assertTrue(all(r["technical_deep_zone"] < r["technical_watch_zone"] for r in result["stocks"]))
            self.assertTrue(all(r["validated_buy_price"] is None for r in result["stocks"]))
            self.assertFalse(result["trade_execution_enabled"])
            self.assertEqual(result["confirmed_holdings"], [])
            with (Path(folder) / "latest.csv").open(newline="") as f:
                self.assertEqual(len(list(csv.DictReader(f))), 200)
            self.assertEqual(len(json.loads((Path(folder) / "latest.json").read_text())["stocks"]), 200)
            html = (Path(folder) / "index.html").read_text(encoding="utf8")
            self.assertIn("all 200 stocks", html)
            self.assertIn("Price-level bar", html)
            self.assertIn("Bitcoin", html)

    @staticmethod
    def mock_quote():
        return {"closes": [100 + (i * .16) + (i % 4) for i in range(252)],
                "volumes": [1500 + (i % 5) * 80 for i in range(252)],
                "quote_date": "2026-11-20T00:00:00+11:00"}

    @staticmethod
    def mock_btc(pair):
        return {"last": 100000.0 if pair == "XBTAUD" else 65000.0,
                "bid": 99999.0, "ask": 100001.0}

    def test_buy_prices_not_fabricated_from_technical_zones(self):
        data = scan.compute_metrics(self.mock_quote(), {
            "ticker": "NVDA", "buy_price": "", "fair_value": "",
            "buy_validation": "UNRESEARCHED"}, datetime(2026, 11, 20, 8, tzinfo=timezone.utc))
        self.assertIsNone(data["validated_buy_price"])
        self.assertIsNone(data["fair_value_estimate"])
        self.assertIsNone(data["distance_to_validated_buy_pct"])
        self.assertGreater(data["technical_watch_zone"], 0)
        self.assertGreater(data["technical_deep_zone"], 0)

    def test_original_baba_buy_level_is_provisional(self):
        row = scan.load_watchlist(scan.BASE / "watchlist.csv")[0]
        metrics = scan.compute_metrics(self.mock_quote(), row, datetime(2026, 11, 20, 8, tzinfo=timezone.utc))
        self.assertIsNone(metrics["validated_buy_price"])
        self.assertEqual(metrics["manual_provisional_buy_price"], 75)
        self.assertIsNotNone(metrics["distance_to_manual_provisional_pct"])

    def test_validation_requires_research_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "watchlist.csv"
            rows = scan.load_watchlist(scan.BASE / "watchlist.csv")
            rows[0]["buy_validation"] = "VALIDATED"
            with path.open("w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=scan.REQUIRED_FIELDS)
                writer.writeheader();writer.writerows(rows)
            with self.assertRaisesRegex(ValueError, "requires buy price"):
                scan.load_watchlist(path)

    def test_missing_feeds_are_visible_not_fake(self):
        with tempfile.TemporaryDirectory() as folder:
            result = scan.run_scan(output=Path(folder),
                   batch_fetcher=lambda tickers: {},
                   btc_fetcher=lambda _: (_ for _ in ()).throw(RuntimeError("offline")))
            self.assertEqual(result["stock_quotes_available"], 0)
            self.assertTrue(all(r["price"] is None for r in result["stocks"]))
            self.assertTrue(all(r["data_status"] == "UNAVAILABLE" for r in result["stocks"]))
            self.assertEqual(set(result["bitcoin"]), {"XBTAUD", "XBTUSD"})
            self.assertIn("error", result["bitcoin"]["XBTUSD"])

    def test_partial_bad_batch_does_not_abort_200(self):
        calls = 0
        def fetching(tickers):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("Yahoo rate limit")
            return {t: self.mock_quote() for t in tickers}
        with tempfile.TemporaryDirectory() as folder:
            data = scan.run_scan(output=Path(folder), batch_fetcher=fetching,
                                 btc_fetcher=self.mock_btc)
            self.assertEqual(calls, 8)
            self.assertEqual(data["stock_quotes_available"], 175)
            self.assertEqual(sum("rate limit" in r["data_status"] for r in data["stocks"]), 25)
            self.assertEqual(len(data["stocks"]), 200)

    def test_math_and_currency_consistency(self):
        self.assertEqual(scan.currency_for("BHP.AX"), "AUD")
        self.assertEqual(scan.currency_for("RY"), "USD")  # US-listed Canadian bank share
        self.assertEqual(scan.currency_for("SHOP.TO"), "CAD")
        self.assertAlmostEqual(scan.pct_distance(90, 75), 20.0)
        self.assertEqual(scan.rsi14([100] * 15), 50.0)
        self.assertIsNone(scan.rsi14([100] * 14))


if __name__ == "__main__":
    unittest.main()
