"""Offline unit tests: prove safe evidence gating, unchanged 200, no trades."""
import csv
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import discovery_engine as d

NOW = datetime(2026, 11, 21, 0, 0, tzinfo=timezone.utc)


def candidate(t="NEWW", url="https://www.sec.gov/Archives/edgar/data/1/abc.htm"):
    return {"ticker": t, "company": "New Wave Technology", "theme": "AI compute",
            "evidence_date": "2026-11-20T12:00:00Z", "evidence_url": url,
            "evidence_kind": "SEC_8K_FILING_REFERENCE", "discovery_source": "SEC and GDELT"}


def quote(price=3.2, med=400_000, cap=2e9, stale=0):
    return {"price": price, "median_dollar_volume_20d": med,
            "market_cap": cap, "stale_days": stale, "quote_date": "2026-11-20"}


class DiscoveryTests(unittest.TestCase):
    def test_trusted_seed_domains(self):
        self.assertTrue(d.safe_primary("https://announcements.asx.com.au/asxpdf/example.pdf"))
        self.assertTrue(d.safe_primary("https://ir.penguinsolutions.com/news"))
        self.assertFalse(d.safe_primary("http://www.sec.gov/Archives/file"))
        self.assertFalse(d.safe_primary("https://sec.gov.evil.test/file"))
        self.assertFalse(d.safe_primary("https://fake.asx.com.au/file"))

    def test_dates_reject_future_and_old(self):
        self.assertTrue(d.is_recent("2026-11-20", NOW))
        self.assertFalse(d.is_recent("2025-11-20", NOW))
        self.assertFalse(d.is_recent("2026-12-30", NOW))

    def test_sec_company_mapping(self):
        dct = {"fields": ["cik", "name", "ticker", "exchange"],
               "data": [[1616533, "Penguin Solutions Inc", "PENG", "Nasdaq"],
                        [100, "Example ETF", "EX", "OTC"]]}
        mapping = d.sec_cik_map(dct)
        self.assertEqual(mapping["1616533"]["ticker"], "PENG")
        self.assertNotIn("100", mapping)

    def test_sec_feed_parsing(self):
        xml = '''<feed xmlns="http://www.w3.org/2005/Atom">
          <entry><title>8-K - Penguin Solutions (0001616533) (Filer)</title>
          <updated>2026-11-20T12:20:00-05:00</updated>
          <link href="https://www.sec.gov/Archives/edgar/data/1616533/abc-index.htm" />
          <summary>8-K Items: 2.02</summary></entry></feed>'''
        lookup = {"1616533": {"ticker": "PENG", "company": "Penguin Solutions Inc", "exchange": "NASDAQ"}}
        results = d.parse_sec_atom(xml, lookup, NOW)
        self.assertEqual(results["PENG"]["evidence_kind"], "SEC_8K_FILING_REFERENCE")
        self.assertEqual(len(results), 1)

    def test_lead_needs_topic_and_filing_and_name(self):
        filing = {"PENG": {**candidate("PENG"), "company": "Penguin Solutions Inc"}}
        articles = [
            {"title": "Penguin Solutions announces AI infrastructure contract", "url": "https://example.org/a"},
            {"title": "PENG stock rockets on rumours", "url": "https://example.org/b"},
            {"title": "Other company announces AI infrastructure contract", "url": "https://example.org/c"},
        ]
        matched = d.extract_news_matches(articles, filing)
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["ticker"], "PENG")

    def test_older_candidates_rotate_into_price_checks(self):
        old = [f"OLD{i}" for i in range(45)]
        first = d.rotate_price_queue(["NEW1", "NEW2"], old, NOW, limit=15)
        next_ = d.rotate_price_queue(["NEW1", "NEW2"], old, NOW + timedelta(hours=1), limit=15)
        self.assertEqual(first[:2], ["NEW1", "NEW2"])
        self.assertEqual(len(first), 15)
        self.assertNotEqual(first[2:], next_[2:])
        self.assertTrue(set(first + next_) & set(old))

    def test_market_gate_blocks_thin_unverified_and_megacaps(self):
        self.assertTrue(d.market_checks(quote())[0])
        self.assertFalse(d.market_checks(quote(med=1_000))[0])
        self.assertFalse(d.market_checks(quote(cap=None))[0])
        self.assertFalse(d.market_checks(quote(cap=50_000_000_000))[0])
        self.assertFalse(d.market_checks(quote(stale=9))[0])
        self.assertFalse(d.market_checks(None)[0])

    def test_new_monitor_and_no_trade(self):
        registry = d.evaluate([candidate()], {"NEWW": quote()}, {}, {"OLD"}, NOW)
        self.assertEqual(registry["candidates"]["NEWW"]["status"], "MONITOR")
        self.assertEqual(registry["events"]["newly_monitored"], ["NEWW"])
        self.assertIsNone(registry["candidates"]["NEWW"]["buy_readiness"])
        self.assertFalse(registry["orders_enabled"])
        self.assertNotIn("OLD", registry["candidates"])

    def test_existing_200_always_excluded(self):
        registry = d.evaluate([candidate("OLD")], {"OLD": quote()}, {}, {"OLD"}, NOW)
        self.assertFalse(registry["candidates"])

    def test_failed_liquidity_three_checks_archive_with_history(self):
        first = d.evaluate([candidate()], {"NEWW": quote()}, {}, set(), NOW)
        previous = {"candidates": first["candidates"]}
        for i in range(1, 4):
            result = d.evaluate([], {"NEWW": quote(med=900)}, previous, set(), NOW + timedelta(days=i))
            previous = {"candidates": result["candidates"]}
        self.assertEqual(previous["candidates"]["NEWW"]["status"], "ARCHIVED_MONITORING")
        self.assertIn("archive_reason", previous["candidates"]["NEWW"])
        again = d.evaluate([], {"NEWW": quote()}, previous, set(), NOW + timedelta(days=4))
        self.assertEqual(again["candidates"]["NEWW"]["status"], "MONITOR")
        self.assertEqual(again["events"]["revived"], ["NEWW"])

    def test_feed_outage_does_not_archive(self):
        first = d.evaluate([candidate()], {"NEWW": quote()}, {}, set(), NOW)
        next_ = d.evaluate([], {}, {"candidates": first["candidates"]}, set(), NOW + timedelta(days=1))
        self.assertEqual(next_["candidates"]["NEWW"]["status"], "MONITOR")
        self.assertFalse(next_["events"]["newly_archived"])

    def test_manual_exclusion_not_readded(self):
        prev = {"candidates": {"NEWW": {"ticker": "NEWW", "status": "MANUAL_EXCLUDE"}}}
        actual = d.evaluate([candidate()], {"NEWW": quote()}, prev, set(), NOW)
        self.assertEqual(actual["candidates"]["NEWW"]["status"], "MANUAL_EXCLUDE")

    def test_seed_list_has_official_references(self):
        p = Path(__file__).resolve().parent.parent / "discovery_seeds.csv"
        seeds = d.read_seeds(p, NOW)
        self.assertEqual(set(x["ticker"] for x in seeds), {"DUG.AX", "EOS.AX", "PENG", "BTDR"})

    def test_offline_snapshot_never_claims_live_trades(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            rows = [{"ticker": f"T{i:03d}"} for i in range(200)]
            with (root / "watchlist.csv").open("w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["ticker"])
                writer.writeheader()
                writer.writerows(rows)
            (root / "discovery_seeds.csv").write_text((Path(__file__).resolve().parent.parent / "discovery_seeds.csv").read_text())
            with patch.object(d, "TODAY", return_value=NOW):
                result = d.run(root=root, offline=True)
            self.assertFalse(result["orders_enabled"])
            self.assertEqual(result["pending_count"], 4)
            self.assertEqual(result["monitor_count"], 0)
            report = json.loads((root / "reports" / "discovery_latest.json").read_text())
            self.assertTrue(report["research_only"])
            self.assertEqual(len(report["new_pending"]), 4)
            self.assertEqual(len(rows), 200)

    def test_only_verified_market_data_promotes(self):
        pending = d.evaluate([candidate()], {"NEWW": quote(cap=None)}, {}, set(), NOW)
        self.assertEqual(pending["candidates"]["NEWW"]["status"], "PENDING_EVIDENCE")
        next_ = d.evaluate([candidate()], {"NEWW": quote()}, {"candidates": pending["candidates"]}, set(), NOW)
        self.assertEqual(next_["candidates"]["NEWW"]["status"], "MONITOR")

    def test_report_is_safe_and_clearly_limited(self):
        reg = d.evaluate([candidate()], {"NEWW": quote()}, {}, set(), NOW)
        result = d.make_snapshot(reg, {"sec": {"status": "unavailable"}}, NOW)
        self.assertEqual(result["monitor_count"], 1)
        self.assertFalse(result["orders_enabled"])
        self.assertTrue(result["limitations"])
        self.assertEqual(result["source_health"]["sec"]["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()

# Championship 5.1 reliability regressions.
class DiscoveryReliability51Tests(unittest.TestCase):
    def test_sec_contact_requires_real_email_shaped_identifier(self):
        self.assertFalse(d.valid_sec_contact(''))
        self.assertFalse(d.valid_sec_contact('Championship-Research/5.0 (+github URL only)'))
        self.assertFalse(d.valid_sec_contact('Research contact@example.com\nInjected: header'))
        self.assertTrue(d.valid_sec_contact('Research Team contact@user-owned-domain.com'))

    def test_403_is_not_retried(self):
        class Response:
            status_code = 403
        session = unittest.mock.Mock()
        session.get.return_value = Response()
        with self.assertRaises(d.SourceFetchError) as ctx, patch.object(d.time, 'sleep') as sleep:
            d.fetch_with_retry(session, d.SEC_TICKERS, source='sec_directory')
        self.assertEqual(ctx.exception.code, 403)
        self.assertEqual(session.get.call_count, 1)
        sleep.assert_not_called()

    def test_429_is_not_retried_or_hammered(self):
        class Response:
            status_code = 429
        session = unittest.mock.Mock()
        session.get.return_value = Response()
        with self.assertRaises(d.SourceFetchError) as ctx, patch.object(d.time, 'sleep') as sleep:
            d.fetch_with_retry(session, d.GDELT, source='gdelt_doc')
        self.assertEqual(ctx.exception.code, 429)
        self.assertEqual(session.get.call_count, 1)
        sleep.assert_not_called()

    def test_503_retry_once_then_success(self):
        import requests
        first = unittest.mock.Mock()
        first.status_code = 503
        first.raise_for_status.side_effect = requests.HTTPError('503', response=first)
        second = unittest.mock.Mock()
        second.status_code = 200
        second.raise_for_status.return_value = None
        sess = unittest.mock.Mock()
        sess.get.side_effect = [first, second]
        with patch.object(d.time, 'sleep') as sleep:
            self.assertIs(d.fetch_with_retry(sess, 'https://example.org/test'), second)
        self.assertEqual(sess.get.call_count, 2)
        sleep.assert_called_once()

    def test_unconfigured_sec_skipped_gdelt_failure_reported(self):
        class Resp:
            status_code = 429
        sess = unittest.mock.Mock()
        sess.get.return_value = Resp()
        with patch.object(d.time, 'sleep') as sleep:
            leads, health = d.discover_external(sess, NOW, sec_configured=False)
        self.assertEqual(leads, [])
        self.assertEqual(health['sec_8k']['status'], 'configuration_required')
        self.assertEqual(health['gdelt']['status'], 'rate_limited')
        self.assertEqual(sess.get.call_count, 3)  # GDELT then Google and Bing RSS fallbacks
        self.assertEqual(health['google_news']['status'], 'rate_limited')
        self.assertEqual(health['bing_news']['status'], 'rate_limited')
        sleep.assert_not_called()

    def test_one_rotating_gdelt_topic_per_run(self):
        class Resp:
            status_code = 200
            def raise_for_status(self): pass
            def json(self): return {'articles': []}
        for hour, expected_theme in [(2, 1), (8, 2), (10, 3), (13, 4), (16, 5), (21, 6)]:
            sess = unittest.mock.Mock()
            sess.get.return_value = Resp()
            result, health = d.discover_external(sess, NOW.replace(hour=hour), sec_configured=False)
            self.assertEqual(result, [])
            self.assertEqual(sess.get.call_count, 1)
            self.assertEqual(health['gdelt']['checked_theme'], expected_theme)
            self.assertEqual(health['gdelt']['status'], 'ok')

    def test_secondary_news_ticker_is_pending_even_if_liquid(self):
        news = {'title': 'AI data center startup signs major contract (NASDAQ: TEST)',
                'url': 'https://example-news.com/news/item', 'seendate': '20261120T120000Z'}
        leads = d.extract_unverified_news_leads([news], NOW)
        self.assertEqual([x['ticker'] for x in leads], ['TEST'])
        self.assertEqual(leads[0]['evidence_kind'], 'SECONDARY_NEWS_TICKER_LEAD_UNVERIFIED')
        reg = d.evaluate(leads, {'TEST': quote()}, {}, set(), NOW)
        self.assertEqual(reg['candidates']['TEST']['status'], 'PENDING_EVIDENCE')
        self.assertIn('PRIMARY_DISCLOSURE_NOT_VERIFIED', reg['candidates']['TEST']['concerns'])
        self.assertIsNone(reg['candidates']['TEST']['buy_readiness'])
        self.assertFalse(reg['orders_enabled'])

    def test_secondary_news_does_not_override_primary_evidence(self):
        good = d.evaluate([candidate('TEST')], {'TEST': quote()}, {}, set(), NOW)
        lead = {'ticker':'TEST','company':'AI business in headline',
                'evidence_date':'2026-11-20','evidence_url':'https://example.com/story',
                'evidence_kind':'SECONDARY_NEWS_TICKER_LEAD_UNVERIFIED'}
        next_ = d.evaluate([lead], {'TEST': quote()}, {'candidates':good['candidates']}, set(), NOW)
        self.assertEqual(next_['candidates']['TEST']['status'], 'MONITOR')
        self.assertEqual(next_['candidates']['TEST']['evidence_kind'], 'SEC_8K_FILING_REFERENCE')

    def test_gdelt_absent_date_or_naked_ticker_is_rejected(self):
        bad = [
            {'title':'AI company signs contract (NASDAQ: TEST)', 'url':'https://news.example.org/s'},
            {'title':'AI company signs contract TEST', 'url':'https://news.example.org/s', 'seendate':'20261120T120000Z'},
            {'title':'AI company signs contract (NASDAQ: TEST)', 'url':'http://news.example.org/s', 'seendate':'20261120T120000Z'},
        ]
        self.assertEqual(d.extract_unverified_news_leads(bad, NOW), [])

    def test_first_party_corroboration_promotes_secondary_lead(self):
        first = d.evaluate([{'ticker':'TEST', 'company':'story', 'theme':'AI',
             'evidence_date':'2026-11-20','evidence_url':'https://news.example.org/a',
             'evidence_kind':'SECONDARY_NEWS_TICKER_LEAD_UNVERIFIED'}],
             {'TEST':quote()}, {}, set(), NOW)
        second = d.evaluate([candidate('TEST')], {'TEST':quote()},
            {'candidates':first['candidates']}, set(), NOW)
        self.assertEqual(second['candidates']['TEST']['status'], 'MONITOR')
        self.assertEqual(second['candidates']['TEST']['evidence_kind'], 'SEC_8K_FILING_REFERENCE')

    def test_source_coverage_badge_warns_on_partial(self):
        reg = d.evaluate([], {}, {}, set(), NOW)
        snap = d.make_snapshot(reg, {'sec_8k': {'status':'configuration_required'},
            'gdelt': {'status':'ok'}}, NOW)
        self.assertEqual(snap['source_coverage'], 'PARTIAL_OR_UNAVAILABLE')
        self.assertEqual(snap['monitor_count'], 0)
        self.assertTrue(snap['schema_version'].startswith('5.2'))
