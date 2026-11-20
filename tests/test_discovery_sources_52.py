"""Championship 5.2: provider fallback, persistent cross-run cooldown and safety."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import discovery_engine as d

NOW = datetime(2026, 11, 21, 0, 0, tzinfo=timezone.utc)
RSS = '''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>News</title>
<item><title>Penguin Solutions announces AI infrastructure contract (NASDAQ: PENG)</title>
<link>https://news.google.com/rss/articles/one</link>
<pubDate>Fri, 20 Nov 2026 12:00:00 GMT</pubDate></item>
<item><title>Old AI data center contract (NASDAQ: OLD)</title>
<link>https://news.google.com/rss/articles/old</link>
<pubDate>Fri, 20 Nov 2020 12:00:00 GMT</pubDate></item>
<item><title>Hostile AI data center contract (NASDAQ: BAD)</title>
<link>http://news.google.com/rss/articles/bad</link>
<pubDate>Fri, 20 Nov 2026 12:00:00 GMT</pubDate></item>
</channel></rss>'''

class GoodRSS:
    status_code = 200
    text = RSS
    def raise_for_status(self):
        return None

class RateLimited:
    status_code = 429
    headers = {"Retry-After":"120"}

class GoodGdelt:
    status_code = 200
    def raise_for_status(self): return None
    def json(self): return {'articles': []}

class Test52(unittest.TestCase):
    def test_google_rss_parses_only_recent_https(self):
        articles = d.parse_google_news_rss(RSS,NOW)
        self.assertEqual(len(articles),1)
        self.assertEqual(articles[0]['source'],'google_news_rss')
        self.assertIn('PENG', articles[0]['title'])
        self.assertTrue(d.gdelt_seen_date(articles[0], NOW))

    def test_google_rss_rejects_invalid_root(self):
        with self.assertRaises(ValueError): d.parse_google_news_rss('<html/>',NOW)

    def test_429_opens_persistent_cooldown_and_uses_rss(self):
        sess=Mock()
        sess.get.side_effect=[RateLimited(), GoodRSS()]
        with patch.object(d.time,'sleep') as sleep:
            leads, health=d.discover_external(sess,NOW,sec_configured=False)
        self.assertEqual(sess.get.call_count,2)
        sleep.assert_not_called()
        self.assertEqual(health['gdelt']['status'],'rate_limited')
        self.assertEqual(health['google_news']['status'],'ok')
        self.assertEqual(health['google_news']['article_count'],1)
        self.assertGreater(d.iso_date(health['gdelt_control']['gdelt_retry_at_utc']),NOW)
        self.assertEqual(health['gdelt_control']['gdelt_consecutive_429'],1)
        self.assertEqual([v['ticker'] for v in leads],['PENG'])
        self.assertEqual(leads[0]['evidence_kind'],'SECONDARY_NEWS_TICKER_LEAD_UNVERIFIED')

    def test_cooldown_skips_gdelt_and_still_uses_rss(self):
        retry=(NOW+timedelta(hours=12)).isoformat()
        sess=Mock();sess.get.return_value=GoodRSS()
        leads, health=d.discover_external(sess,NOW+timedelta(hours=1),
            sec_configured=False,source_state={'gdelt_retry_at_utc':retry,'gdelt_consecutive_429':1})
        self.assertEqual(sess.get.call_count,1)
        self.assertEqual(sess.get.call_args.args[0],d.GOOGLE_NEWS_RSS)
        self.assertEqual(health['gdelt']['status'],'cooldown')
        self.assertEqual([v['ticker'] for v in leads],['PENG'])

    def test_expired_cooldown_retries_once(self):
        retry=(NOW-timedelta(minutes=1)).isoformat()
        sess=Mock();sess.get.return_value=GoodGdelt()
        leads, health=d.discover_external(sess,NOW,sec_configured=False,
            source_state={'gdelt_retry_at_utc':retry,'gdelt_consecutive_429':3})
        self.assertEqual(sess.get.call_count,1)
        self.assertEqual(sess.get.call_args.args[0],d.GDELT)
        self.assertEqual(health['gdelt']['status'],'ok')
        self.assertIsNone(health['gdelt_control']['gdelt_retry_at_utc'])
        self.assertEqual(health['gdelt_control']['gdelt_consecutive_429'],0)

    def test_repeat_429_increases_delay(self):
        sess=Mock();sess.get.side_effect=[RateLimited(),GoodRSS()]
        _,health=d.discover_external(sess,NOW,sec_configured=False,
            source_state={'gdelt_consecutive_429':1})
        self.assertGreaterEqual(d.iso_date(health['gdelt_control']['gdelt_retry_at_utc']),NOW+timedelta(hours=24))

    def test_google_news_success_restores_core_news_coverage(self):
        reg=d.evaluate([],{}, {},set(), NOW)
        snap=d.make_snapshot(reg,{'sec_8k':{'status':'ok'}, 'gdelt':{'status':'rate_limited'},
                                  'google_news':{'status':'ok'}},NOW)
        self.assertEqual(snap['source_coverage'],'CORE_SOURCES_AVAILABLE_WITH_FALLBACK')
        self.assertFalse(snap['orders_enabled'])

    def test_no_primary_means_no_monitor_even_with_good_quote(self):
        leads=d.extract_unverified_news_leads(d.parse_google_news_rss(RSS,NOW),NOW)
        quote={'price':6.2,'median_dollar_volume_20d':1e6,'market_cap':3e9,'stale_days':0}
        reg=d.evaluate(leads,{'PENG':quote},{},set(),NOW)
        self.assertEqual(reg['candidates']['PENG']['status'],'PENDING_EVIDENCE')
        self.assertFalse(reg['orders_enabled'])
        self.assertIsNone(reg['candidates']['PENG']['buy_readiness'])

    def test_429_does_not_end_research_when_rss_also_limited(self):
        sess=Mock();sess.get.return_value=RateLimited()
        _,health=d.discover_external(sess,NOW,sec_configured=False)
        self.assertEqual(health['gdelt']['status'],'rate_limited')
        self.assertEqual(health['google_news']['status'],'rate_limited')
        self.assertEqual(sess.get.call_count,3)

    def test_original_200_exclusion_with_google_news(self):
        leads=d.extract_unverified_news_leads(d.parse_google_news_rss(RSS,NOW),NOW)
        reg=d.evaluate(leads,{}, {}, {'PENG'},NOW)
        self.assertEqual(reg['candidates'],{})

    def test_retry_after_response_is_read_but_no_wait_loop(self):
        sess=Mock();sess.get.return_value=RateLimited()
        with self.assertRaises(d.SourceFetchError) as cm, patch.object(d.time,'sleep') as sleep:
            d.fetch_with_retry(sess,d.GDELT,source='gdelt_doc')
        self.assertEqual(cm.exception.retry_after_seconds,120)
        sleep.assert_not_called()

if __name__=='__main__':unittest.main()

class TestTertiaryFallback52(unittest.TestCase):
    def test_bing_rss_used_when_gdelt_and_google_blocked(self):
        sess = Mock()
        sess.get.side_effect = [RateLimited(), RateLimited(), GoodRSS()]
        leads, health = d.discover_external(sess, NOW, sec_configured=False)
        self.assertEqual(sess.get.call_count, 3)
        self.assertEqual(health['gdelt']['status'], 'rate_limited')
        self.assertEqual(health['google_news']['status'], 'rate_limited')
        self.assertEqual(health['bing_news']['status'], 'ok')
        self.assertEqual(leads[0]['discovery_source'], 'Bing News RSS (secondary, unverified)')
        snap = d.make_snapshot(d.evaluate(leads, {}, {}, set(), NOW), {
            'sec_8k': {'status': 'ok'}, 'gdelt': health['gdelt'],
            'google_news': health['google_news'], 'bing_news': health['bing_news']}, NOW)
        self.assertEqual(snap['source_coverage'], 'CORE_SOURCES_AVAILABLE_WITH_FALLBACK')

    def test_bing_not_called_if_google_news_has_items(self):
        sess = Mock()
        sess.get.side_effect = [RateLimited(), GoodRSS()]
        _,health=d.discover_external(sess,NOW,sec_configured=False)
        self.assertEqual(sess.get.call_count,2)
        self.assertEqual(health['bing_news']['status'],'not_needed')

    def test_google_news_response_missing_items_tries_bing(self):
        empty = GoodRSS()
        empty.text = '<rss><channel><title>None</title></channel></rss>'
        sess=Mock()
        sess.get.side_effect=[RateLimited(),empty,GoodRSS()]
        leads,health=d.discover_external(sess,NOW,sec_configured=False)
        self.assertEqual(sess.get.call_count,3)
        self.assertEqual(health['google_news']['status'],'ok')
        self.assertEqual(health['bing_news']['status'],'ok')
        self.assertEqual([x['ticker'] for x in leads],['PENG'])

    def test_live_run_persists_cooldown_without_trades(self):
        import csv
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'reports').mkdir()
            (root/'discovery_seeds.csv').write_text('ticker,company,theme,evidence_date,official_url\n')
            with (root/'watchlist.csv').open('w',newline='') as f:
                w=csv.DictWriter(f, fieldnames=['ticker'])
                w.writeheader()
                w.writerows({'ticker': f'T{i:03d}'} for i in range(200))
            control={'gdelt_retry_at_utc':(NOW+timedelta(hours=12)).isoformat(),
                     'gdelt_consecutive_429':1}
            with patch.object(d,'TODAY',return_value=NOW), \
                 patch.object(d,'discover_external',return_value=([],{
                     'sec_8k':{'status':'ok'},'gdelt':{'status':'rate_limited'},
                     'google_news':{'status':'ok'},'bing_news':{'status':'not_needed'},
                     'gdelt_control':control})), \
                 patch.object(d,'fetch_quotes',return_value=({}, {'status':'ok'})):
                snapshot=d.run(root=root,offline=False)
            registry=json.loads((root/'reports'/'discovery_watchlist.json').read_text())
            self.assertEqual(registry['source_state'],control)
            self.assertFalse(snapshot['orders_enabled'])
            self.assertTrue(registry['original_200_unchanged'])
            self.assertEqual(snapshot['source_coverage'],'CORE_SOURCES_AVAILABLE_WITH_FALLBACK')
