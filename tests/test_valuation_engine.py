import csv
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import valuation_engine as ve

NOW = datetime(2026, 11, 20, 9, 0, tzinfo=timezone.utc)
QTR = datetime(2026, 8, 1, tzinfo=timezone.utc).timestamp()


def stock(ticker="MSFT", price=100.0, currency="USD"):
    return {"ticker": ticker, "price": price, "currency": currency,
            "stale_days": 1, "quote_date": "2026-11-19", "data_status": "DAILY HISTORY — NOT LIVE",
            "volatility_20d_annual_pct": 40.0}


def info(currency="USD", **kwargs):
    result = {"currency": currency, "financialCurrency": currency, "quoteType": "EQUITY",
              "mostRecentQuarter": QTR, "sharesOutstanding": 100_000_000,
              "marketCap": 10_000_000_000, "freeCashflow": 1_000_000_000,
              "revenueGrowth": .15, "sector": "Technology", "industry": "Software"}
    result.update(kwargs)
    return result


def meta(ticker="MSFT"):
    return {"ticker": ticker, "name": "Example", "sector": "US Technology & AI", "risk_note": ""}


class ValuationResearchTests(unittest.TestCase):
    def test_nonfinancial_fcf_model_has_scenario_range(self):
        row = ve.evaluate(meta(), stock(), {"info": info()}, NOW)
        self.assertTrue(row["model_status"].startswith("INDICATIVE"))
        self.assertLess(row["bear_value"], row["base_value"])
        self.assertLess(row["base_value"], row["bull_value"])
        self.assertIsNone(row["model_deep_entry"])
        self.assertIsNone(row["model_watch_entry"])
        self.assertEqual(row["manual_validation"], "NEVER AUTO VALIDATED")

    def test_riskier_stocks_have_wider_model_discount(self):
        high = stock()
        high["volatility_20d_annual_pct"] = 100.0
        low = ve.evaluate(meta(), stock(), {"info": info()}, NOW)
        risky = ve.evaluate(meta(), high, {"info": info()}, NOW)
        self.assertIsNone(risky["model_watch_entry"])
        self.assertIsNone(low["model_watch_entry"])
        self.assertIn("RETIRED",risky["caveats"])

    def test_negative_fcf_does_not_invent_value(self):
        row = ve.evaluate(meta(), stock(), {"info": info(freeCashflow=-1000)}, NOW)
        self.assertEqual(row["model_status"].startswith("UNVALUED"), True)
        self.assertIsNone(row["base_value"])
        self.assertIsNone(row["model_watch_entry"])

    def test_financial_uses_book_value_roe_not_fcf(self):
        k = meta("JPM")
        feed = info(sector="Financial Services", industry="Banks", bookValue=80,
                    returnOnEquity=.13, freeCashflow=-100000)
        row = ve.evaluate(k, stock("JPM"), {"info": feed}, NOW)
        self.assertTrue(row["model_status"].startswith("INDICATIVE"))
        self.assertEqual(row["model_type"], "FINANCIAL_BOOK_ROE")
        self.assertEqual(row["fcf_basis"], "NOT USED: FINANCIAL COMPANY")

    def test_visa_uses_cashflow_not_bank_book_model(self):
        row = ve.evaluate(meta("V"), stock("V"),
                          {"info": info(sector="Financial Services", industry="Credit Services")}, NOW)
        self.assertEqual(row["model_type"], "FCF_TO_EQUITY")
        self.assertTrue(row["model_status"].startswith("INDICATIVE"))

    def test_coinbase_and_berkshire_need_specialist_valuation(self):
        for ticker in ("COIN", "BRK-B"):
            row = ve.evaluate(meta(ticker), stock(ticker),
                              {"info": info(sector="Financial Services", industry="Capital Markets")}, NOW)
            self.assertEqual(row["model_type"], "SPECIALIST_RESEARCH_REQUIRED")
            self.assertIsNone(row["base_value"])

    def test_wrong_financial_currency_blocks_adr_mismatch(self):
        row = ve.evaluate(meta(), stock(), {"info": info(financialCurrency="CNY")}, NOW)
        self.assertTrue(row["model_status"].startswith("BLOCKED"))
        self.assertIn("Financial statement currency mismatch", row["caveats"])

    def test_mismatched_share_count_and_marketcap_blocks(self):
        row = ve.evaluate(meta(), stock(), {"info": info(marketCap=1_000_000_000)}, NOW)
        self.assertIn("mismatch", row["caveats"])
        self.assertIsNone(row["base_value"])

    def test_stale_fundamentals_block(self):
        row = ve.evaluate(meta(), stock(), {"info": info(mostRecentQuarter=1577836800)}, NOW)
        self.assertTrue(row["model_status"].startswith("BLOCKED"))

    def test_fiscal_date_required(self):
        row = ve.evaluate(meta(), stock(), {"info": info(mostRecentQuarter=None, lastFiscalYearEnd=None)}, NOW)
        self.assertIn("fiscal statement date", row["caveats"])

    def test_stale_or_absent_daily_quote_blocks(self):
        q = stock()
        q["stale_days"] = 10
        row = ve.evaluate(meta(), q, {"info": info()}, NOW)
        self.assertTrue(row["model_status"].startswith("BLOCKED"))
        self.assertIsNone(row["base_value"])

    def test_resource_requires_three_positive_annual_cashflows(self):
        k = meta("BHP.AX")
        k["sector"] = "Original 30"
        v = info("AUD", sector="Basic Materials")
        feed = {"info": v, "annual_fcf": [100_000_000, -200_000_000]}
        row = ve.evaluate(k, stock("BHP.AX", currency="AUD"), feed, NOW)
        self.assertTrue(row["model_status"].startswith("UNVALUED"))
        self.assertIsNone(row["model_watch_entry"])
        good = ve.evaluate(k, stock("BHP.AX", currency="AUD"),
                           {"info": v, "annual_fcf": [8e8, 1e9, 9e8]}, NOW)
        self.assertTrue(good["model_status"].startswith("INDICATIVE"))
        self.assertIn("MEDIAN", good["fcf_basis"])

    def test_specialist_biotech_requires_own_model(self):
        row = ve.evaluate(meta("SLS"), stock("SLS"),
                          {"info": info(sector="Healthcare", industry="Biotechnology")}, NOW)
        self.assertTrue(row["model_status"].startswith("BLOCKED"))
        self.assertIsNone(row["base_value"])

    def test_missing_fundamentals_returns_row_not_fake_quote(self):
        row = ve.evaluate(meta(), stock(), None, NOW)
        self.assertEqual(row["model_type"], "NONE")
        self.assertIsNone(row["model_watch_entry"])
        self.assertEqual(row["manual_validation"], "NEVER AUTO VALIDATED")

    def test_200_rows_offline_with_no_trade_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            tickers = [f"S{i:03d}" for i in range(200)]
            with (p / "watchlist.csv").open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["ticker", "name", "sector", "risk_note"])
                w.writeheader()
                for t in tickers:
                    w.writerow(meta(t) | {"ticker": t})
            prices = {"stocks": [stock(t) for t in tickers]}
            (p / "daily.json").write_text(json.dumps(prices))
            result = ve.run_engine(p / "watchlist.csv", p / "daily.json", p / "result",
                                   fetcher=lambda _: {"info": info()}, workers=3, max_minutes=1,
                                   now=NOW)
            self.assertEqual(result["total_rows"], 200)
            self.assertEqual(result["indicative_model_count"], 200)
            self.assertEqual(result["validated_buy_count"], 0)
            self.assertFalse(result["order_execution_enabled"])
            self.assertEqual(result["orders_generated"], 0)
            with (p / "result/valuation_200.csv").open(newline="", encoding="utf-8") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(len(rows), 200)
            self.assertTrue((p / "result/valuation_200.html").exists())

    def test_200_rows_feed_outage_still_outputs_all_with_no_fake_valuations(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            tickers = [f"S{i:03d}" for i in range(200)]
            with (p / "list.csv").open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["ticker", "name", "sector", "risk_note"])
                w.writeheader()
                for t in tickers:
                    w.writerow(meta(t) | {"ticker": t})
            (p / "price.json").write_text(json.dumps({"stocks": [stock(t) for t in tickers]}))
            def outage(_):
                raise RuntimeError("429: rate limited")
            result = ve.run_engine(p / "list.csv", p / "price.json", p / "report",
                                   fetcher=outage, now=NOW, max_minutes=1)
            self.assertEqual(result["total_rows"], 200)
            self.assertEqual(result["indicative_model_count"], 0)
            self.assertEqual(result["blocked_or_unvalued_count"], 200)
            with (p / "report/valuation_200.csv").open(newline="", encoding="utf-8") as file:
                self.assertTrue(all(not r["base_value"] for r in csv.DictReader(file)))

    def test_model_rejects_unsafe_discount_rate(self):
        with self.assertRaises(ValueError):
            ve.equity_fcf_dcf(1, .05, .035, .02)


if __name__ == "__main__":
    unittest.main()
