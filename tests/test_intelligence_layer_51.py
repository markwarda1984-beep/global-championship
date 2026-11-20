"""Offline research-only regression tests; never contact brokers or providers."""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

import intelligence_layer_51 as m

NOW = datetime(2026, 11, 21, 1, 0, tzinfo=timezone.utc)


def scan(day='2026-11-20', price=100, ccy='AUD'):
    return {'scan_utc': '2026-11-20T21:00:00Z', 'orders_enabled': False,
            'stocks': [{'ticker': f'T{i:03}', 'company': f'Test {i}', 'currency': ccy,
                        'last_daily_close': price, 'quote_date': day,
                        'provisional_entry': 70, 'entry_basis': 'UNVERIFIED FUNDAMENTAL MODEL',
                        'data_status': 'ok', 'model_status': 'INDICATIVE'} for i in range(200)]}


def valuation(ccy='AUD', fiscal='2026-09-30'):
    return {'summary': {'timestamp_utc': '2026-11-20T20:00:00Z', 'source': 'unofficial Yahoo'},
            'stocks': [{'ticker': f'T{i:03}', 'model_status': 'INDICATIVE MODEL — NOT VERIFIED',
                        'model_type': 'DCF', 'bear_value': 90, 'base_value': 130 + (i % 3),
                        'bull_value': 160, 'model_watch_entry': 94,
                        'fiscal_as_of': fiscal, 'price_currency': ccy, 'fundamental_currency': ccy,
                        'model_quality': 'LOW: UNVERIFIED', 'source': 'unofficial Yahoo',
                        'model_assumptions': 'scenario only'} for i in range(200)]}


def assumptions():
    return json.loads((Path(__file__).resolve().parents[1] / 'settings/intelligence_51.json').read_text())


class TestIntelligence51(unittest.TestCase):
    def test_existing_200_preserved(self):
        r = scan()
        m.assert_safety(r)
        r['stocks'].pop()
        with self.assertRaises(ValueError): m.assert_safety(r)

    def test_200_unique_required(self):
        r = scan(); r['stocks'][0] = copy.deepcopy(r['stocks'][1])
        with self.assertRaises(ValueError): m.assert_safety(r)

    def test_orders_must_be_disabled(self):
        r = scan(); r['orders_enabled'] = True
        with self.assertRaises(ValueError): m.assert_safety(r)

    def test_first_run_baseline_without_fabricated_changes(self):
        result = m.scan_changes(None, scan(), NOW)
        self.assertEqual(result['comparison_status'], 'BASELINE_ONLY_NO_PREVIOUS_SCAN')
        self.assertEqual(result['new_daily_bar_count'], 0)
        self.assertFalse(result['orders_enabled'])

    def test_new_bar_move_requires_distinct_session(self):
        a, b = scan('2026-11-19'), scan('2026-11-20')
        b['stocks'][0]['last_daily_close'] = 108
        result = m.scan_changes(a, b, NOW)
        self.assertEqual(result['new_daily_bar_count'], 200)
        x = next(z for z in result['material_changes'] if z['ticker'] == 'T000')
        self.assertEqual(x['daily_bar_change_pct'], 8)

    def test_same_day_revisions_not_marked_market_gains(self):
        a, b = scan(), scan()
        b['stocks'][0]['last_daily_close'] = 115
        result = m.scan_changes(a, b, NOW)
        self.assertEqual(result['new_daily_bar_count'], 0)
        self.assertEqual(result['same_bar_revision_count'], 1)
        self.assertFalse(any(x['ticker'] == 'T000' for x in result['material_changes']))

    def test_regression_is_reported(self):
        result = m.scan_changes(scan('2026-11-20'), scan('2026-11-19'), NOW)
        self.assertEqual(result['quote_date_regression_count'], 200)

    def test_field_changes_reported_without_quote_move(self):
        a, b = scan(), scan(); b['stocks'][0]['model_status'] = 'BLOCKED'
        result = m.scan_changes(a, b, NOW)
        self.assertEqual(result['research_field_change_count'], 1)
        self.assertEqual(result['material_changes'][0]['ticker'], 'T000')

    def test_incomplete_previous_scan_fails_closed(self):
        a = scan(); a['stocks'].pop()
        with self.assertRaises(ValueError): m.scan_changes(a, scan(), NOW)

    def test_valid_indicative_models_ranked_without_buy_signal(self):
        result = m.valuation_top10(scan(), valuation(), NOW)
        self.assertEqual(len(result['ranked_top_10']), 10)
        self.assertEqual(result['eligible_for_research_count'], 200)
        self.assertEqual(result['verified_buy_count'], 0)
        self.assertTrue(all(x['buy_readiness_pct'] is None and not x['verified_buy_signal'] for x in result['ranked_top_10']))

    def test_missing_fundamental_currency_blocks_model(self):
        v = valuation(); v['stocks'][0]['fundamental_currency'] = 'USD'
        result = m.valuation_top10(scan(), v, NOW)
        self.assertEqual(result['eligible_for_research_count'], 199)

    def test_old_fundamentals_blocks_model(self):
        result = m.valuation_top10(scan(), valuation(fiscal='2020-01-01'), NOW)
        self.assertEqual(result['ranked_top_10'], [])

    def test_stale_valuation_snapshot_blocks_all(self):
        v = valuation(); v['summary']['timestamp_utc'] = '2025-11-20T20:00:00Z'
        self.assertEqual(m.valuation_top10(scan(), v, NOW)['ranked_top_10'], [])

    def test_source_primary_filing_metadata(self):
        record = {'evidence_kind': 'SEC_8K_FILING_REFERENCE',
                  'evidence_url': 'https://www.sec.gov/Archives/edgar/data/42/some.htm'}
        result = m.verify_url_metadata(record, sec_ok=True)
        self.assertTrue(result['primary_source_verified'])
        self.assertFalse(result['primary_claim_verified'])

    def test_official_host_without_fetch_is_not_verified(self):
        record = {'evidence_kind': 'CURATED_OFFICIAL_DISCLOSURE_REFERENCE',
                  'evidence_url': 'https://ir.bitdeer.com/investor-news'}
        self.assertFalse(m.verify_url_metadata(record)['primary_source_verified'])

    def test_untrusted_website_is_not_verified(self):
        record = {'evidence_kind': 'CURATED_OFFICIAL_DISCLOSURE_REFERENCE',
                  'evidence_url': 'https://bad-domain.example/press-release'}
        ses = Mock()
        x = m.verify_url_metadata(record, ses, allow_network=True)
        self.assertFalse(x['primary_source_verified'])
        ses.get.assert_not_called()

    def test_verified_reachability_never_verified_claim(self):
        record = {'evidence_kind': 'CURATED_OFFICIAL_DISCLOSURE_REFERENCE',
                  'evidence_url': 'https://ir.bitdeer.com/investor-news'}
        resp = Mock(status_code=200, headers={'Content-Type': 'text/html'})
        ses = Mock();ses.get.return_value=resp
        x = m.verify_url_metadata(record, ses, allow_network=True)
        self.assertTrue(x['primary_source_verified'])
        self.assertFalse(x['primary_claim_verified'])
        self.assertFalse(ses.get.call_args.kwargs['allow_redirects'])
        self.assertTrue(ses.get.call_args.kwargs['stream'])
        resp.close.assert_called_once()

    def test_queue_fails_closed_when_unavailable(self):
        reg = {'orders_enabled':False,'original_200_unchanged':True,
               'candidates':{'BTDR':{'status':'PENDING_EVIDENCE','evidence_kind':'CURATED_OFFICIAL_DISCLOSURE_REFERENCE',
                                    'evidence_url':'https://ir.bitdeer.com/investor-news','evidence_date':'2026-11-20'}}}
        result = m.research_queue(reg, {'source_health':{}}, NOW)
        self.assertEqual(result['not_yet_verified_count'],1)
        self.assertEqual(result['claim_verified_count'],0)
        self.assertFalse(result['orders_enabled'])

    def test_archive_not_in_verified_queue(self):
        reg = {'orders_enabled':False,'original_200_unchanged':True,
               'candidates':{'TST':{'status':'ARCHIVED_MONITORING','evidence_kind':'SEC_8K_FILING_REFERENCE',
                                    'evidence_url':'https://www.sec.gov/Archives/edgar/data/42/some.htm',
                                    'evidence_date':'2026-11-20'}}}
        result = m.research_queue(reg, {'source_health':{'sec_8k':{'status':'ok'}}}, NOW)
        self.assertEqual(result['source_verified_reference_count'],0)

    def test_offset_baseline_aud_13_months(self):
        result = m.after_tax_comparison({'ranked_top_10':[]}, assumptions(), {'status':'unavailable'}, NOW)
        self.assertEqual(result['offset_savings_aud_for_horizon'],62.83)
        self.assertFalse(result['orders_enabled'])
        self.assertIn('NO_DISCOUNT',result['tax_method'])

    def test_aud_profit_tax_and_expenses(self):
        top = {'ranked_top_10':[{'rank':1,'ticker':'T000','currency':'AUD','last_daily_close':100,
                                 'bear_value':80,'base_value':120,'bull_value':130}]}
        result=m.after_tax_comparison(top, assumptions(), {'status':'unavailable'}, NOW)
        row=result['ranked_research_scenarios'][0]
        self.assertEqual(row['status'],'SCENARIO_ONLY_NOT_A_PREDICTION')
        outcome=row['hypothetical_outcomes']['base']['income_158k']
        self.assertAlmostEqual(outcome['conservative_tax_stress_aud'], max(0,outcome['gross_profit_after_fees_aud'])*.39,delta=.01)
        self.assertTrue(outcome['beats_offset_in_this_hypothetical_scenario'])

    def test_losses_not_refunded_by_salary_tax(self):
        top={'ranked_top_10':[{'rank':1,'ticker':'T000','currency':'AUD','last_daily_close':100,
                               'bear_value':50,'base_value':60,'bull_value':70}]}
        result=m.after_tax_comparison(top, assumptions(), {},NOW)
        outcome=result['ranked_research_scenarios'][0]['hypothetical_outcomes']['base']['income_158k']
        self.assertEqual(outcome['conservative_tax_stress_aud'],0)
        self.assertLess(outcome['illustrative_after_tax_profit_aud'],0)

    def test_usd_blocks_without_fx(self):
        top={'ranked_top_10':[{'rank':1,'ticker':'T000','currency':'USD','last_daily_close':100,
                               'bear_value':90,'base_value':130,'bull_value':160}]}
        row=m.after_tax_comparison(top,assumptions(),{'status':'unavailable'},NOW)['ranked_research_scenarios'][0]
        self.assertEqual(row['status'],'BLOCKED_MISSING_FRESH_AUD_FX')
        self.assertFalse(row['hypothetical_outcomes'])

    def test_usd_comparison_works_with_fresh_fx(self):
        top={'ranked_top_10':[{'rank':1,'ticker':'T000','currency':'USD','last_daily_close':100,
                               'bear_value':90,'base_value':130,'bull_value':160}]}
        row=m.after_tax_comparison(top,assumptions(),{'status':'ok','aud_per_usd':1.55},NOW)['ranked_research_scenarios'][0]
        self.assertEqual(row['aud_per_currency'],1.55)
        self.assertTrue(row['hypothetical_outcomes'])

    def test_stale_fx_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'fx.json';m.write(p, {'status':'ok','aud_per_usd':1.5,'quote_date':'2026-10-01'})
            r=m.fx_aud_rate(p,NOW)
            self.assertEqual(r['status'],'unavailable')

    def test_journal_deduplicates_same_evidence(self):
        evt={'ticker':'TEST','event_type':'RESEARCH','evidence_date':'2026-11-20','rationale':'notes'}
        a=m.append_journal(None,[evt],NOW)
        b=m.append_journal(a,[evt],NOW)
        self.assertEqual(a['entry_count'],1)
        self.assertEqual(b['entry_count'],1)
        self.assertFalse(b['orders_enabled'])
        self.assertIsNone(b['entries'][0]['order_id'])

    def test_journal_large_price_move_is_alert_not_trade(self):
        a,b=scan('2026-11-19'),scan('2026-11-20');b['stocks'][0]['last_daily_close']=111
        changes=m.scan_changes(a,b,NOW)
        events=m.journal_events(changes,{}, {'ranked_top_10':[]}, NOW)
        self.assertTrue(any(x['ticker']=='T000' and x['event_type']=='LARGE_DAILY_BAR_MOVE_RESEARCH_ALERT' for x in events))
        self.assertFalse(any(x['event_type'] in ('BUY','SELL','ORDER') for x in events))

    def test_end_to_end_offline_scan_writes_readable_json(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'reports').mkdir();(root/'data').mkdir();(root/'settings').mkdir()
            m.write(root/'reports/latest.json',scan())
            m.write(root/'reports/valuation_latest.json',valuation())
            (root/'settings/intelligence_51.json').write_text(json.dumps(assumptions()))
            result=m.run(root,mode='scan',offline=True,now=NOW)
            self.assertEqual(result['base_scanner_count'],200)
            for f in result['reports']:
                if f=='reports/research_queue_latest.json':continue
                json.loads((root/f).read_text())
            self.assertEqual(m.read(root/'reports/valuation_top10_latest.json')['verified_buy_count'],0)

    def test_end_to_end_offline_discovery_preserves_200(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'reports').mkdir()
            m.write(root/'reports/discovery_latest.json',{'source_health':{'sec_8k':{'status':'ok'}}})
            m.write(root/'reports/discovery_watchlist.json',{'orders_enabled':False,'original_200_unchanged':True,
                                                              'candidates':{}})
            out=m.run(root,mode='discovery',offline=True,now=NOW)
            self.assertFalse(out['orders_enabled'])
            self.assertEqual(m.read(root/'reports/research_queue_latest.json')['records'],[])

    def test_user_research_notes_are_logged_but_order_instructions_rejected(self):
        notes = {"entries": [
            {"ticker":"NVDA", "decision":"WATCH", "decision_date":"2026-11-20",
             "thesis":"Wait for independent catalysts", "risk":"Volatility"},
            {"ticker":"NVDA", "decision":"BUY", "decision_date":"2026-11-20"},
        ]}
        events=m.journal_events({"material_changes":[]}, {}, {"ranked_top_10":[]}, NOW, notes)
        self.assertEqual(len(events),1)
        self.assertEqual(events[0]['stated_research_decision'],'WATCH')
        record=m.append_journal(None,events,NOW)
        self.assertFalse(record['orders_enabled'])
        self.assertIsNone(record['entries'][0]['order_id'])

    def test_snapshots_are_captured_before_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'reports').mkdir();(root/'data').mkdir()
            m.write(root/'reports/latest.json',scan())
            self.assertEqual(m.run(root,'snapshot')['snapshot'],True)
            self.assertEqual(m.read(root/'data/intel51_prior_report.json')['stocks'][0]['ticker'],'T000')


if __name__ == '__main__':
    unittest.main()
