import csv
import json
import tempfile
import unittest
from pathlib import Path
import scan
import opportunity_engine as eng

class OpportunityEngineTests(unittest.TestCase):
    @staticmethod
    def make_row(ticker="A"):
        return {"ticker": ticker, "name": ticker, "sector": "test", "price": 100.0,
                "stale_days": 0, "sma_50": 90.0, "sma_200": 85.0,
                "change_20d_pct": 10.0, "change_63d_pct": 20.0,
                "rsi_14": 60.0, "volatility_20d_annual_pct": 50.0,
                "volume_ratio_20d": 1.4, "technical_watch_zone": 80,
                "technical_deep_zone": 68, "validated_buy_price": None,
                "manual_provisional_buy_price": None, "buy_validation": "UNRESEARCHED",
                "quote_date": "2026-11-20T00:00:00+11:00", "data_status": "DAILY HISTORY — NOT LIVE"}

    def test_unresearched_company_cannot_be_marked_buy(self):
        r = eng.assess(self.make_row())
        self.assertIn("RESEARCH ONLY", r["research_decision"])
        self.assertIsNone(r["validated_buy_price"])
        self.assertIsInstance(r["technical_priority_score"], float)

    def test_missing_quotes_never_score(self):
        r = self.make_row()
        r["price"] = None
        x = eng.assess(r)
        self.assertIsNone(x["technical_priority_score"])
        self.assertIn("INSUFFICIENT", x["research_decision"])

    def test_stale_data_never_score(self):
        r = self.make_row()
        r["stale_days"] = 15
        self.assertIsNone(eng.assess(r)["technical_priority_score"])

    def test_provisional_buy_cannot_be_treated_as_validated(self):
        r = self.make_row()
        r.update({"manual_provisional_buy_price": 75.0, "buy_validation":"PROVISIONAL"})
        self.assertEqual(eng.assess(r)["research_decision"],"RESEARCH ONLY — NO VALIDATED BUY")

    def test_200_row_research_output_and_no_orders(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            r=[self.make_row(f"S{i}") for i in range(200)]
            (folder/"latest.json").write_text(json.dumps({"scan_sydney":"2026-11-20T19:00:00+11:00","stocks":r}))
            summary=eng.run_engine(folder/"latest.json",folder)
            self.assertEqual(summary["universe"],200)
            self.assertEqual(summary["orders_generated"],0)
            self.assertFalse(summary["trade_execution_enabled"])
            self.assertEqual(summary["fundamentally_validated_buy_count"],0)
            with (folder/"opportunity_triage_200.csv").open(newline="") as f:
                self.assertEqual(len(list(csv.DictReader(f))),200)
            self.assertIn("research triage",(folder/"opportunity_triage_200.html").read_text())

    def test_reject_partial_universe(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            (folder/"latest.json").write_text(json.dumps({"stocks":[self.make_row()]}))
            with self.assertRaisesRegex(ValueError,"200 unique"):
                eng.run_engine(folder/"latest.json",folder)

if __name__=="__main__": unittest.main()
