"""Regression: old US$33.3938 NVDA target must NEVER reach a current research entry.

Synthetic primary documents below are test fixtures, not claims about any stock.
"""
import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch
import report_bridge as bridge
import intelligence_layer_51 as intel
import opportunity_engine as opp
import valuation_engine as old

NOW=datetime(2026,11,21,1,tzinfo=timezone.utc)


def scan():
    tickers=['NVDA','BABA']+[f'Z{i:03d}' for i in range(198)]
    return {'stocks':[{'ticker':x,'name':x,'company':x,'price':125.53 if x=='NVDA' else 100,
            'last_daily_close':125.53 if x=='NVDA' else 100,
            'currency':'USD','quote_date':'2026-11-20T00:00:00',
            'technical_watch_zone':120 if x=='NVDA' else 70,
            'manual_provisional_buy_price':75 if x=='BABA' else None,
            'buy_validation':'VALIDATED' if x=='BABA' else 'UNRESEARCHED',
            'validated_buy_price':75 if x=='BABA' else None,
            'data_status':'DAILY HISTORY — NOT LIVE'} for x in tickers],
            'orders_enabled':False,'scan_utc':'2026-11-20T22:00:00Z'}


def unofficial():
    return {'summary':{'timestamp_utc':'2026-11-20T22:00:00Z'},'stocks':[
        {'ticker':'NVDA','model_watch_entry':33.3938,
         'model_deep_entry':25,'model_status':'INDICATIVE MODEL — NOT VERIFIED OR APPROVED',
         'price_currency':'USD','base_value':47.7054}]}


def full60(primary=False):
    v={'schema_version':'6.0-full-cycle-primary-evidence-1','original_watchlist_count':200,
       'reported_count':200,'orders_enabled':False,'orders_generated':0,
       'published_at_utc':'2026-11-20T22:00:00Z','companies':[]}
    for row in scan()['stocks']:
        ticker=row['ticker']
        x={'ticker':ticker,'orders_enabled':False,'research_only':True,
           'validation_status':'NOT VALIDATED','selected_entry':None,
           'missing_evidence_flags':['PRIMARY_XBRL_NOT_COLLECTED'],
           'price_currency':'USD','price_as_of':'2026-11-20T00:00:00',
           'latest_dated_price':125.53 if ticker=='NVDA' else 100,
           'source_confidence':'INSUFFICIENT_PRIMARY_ECONOMIC_EVIDENCE'}
        if ticker=='NVDA' and primary:
            x.update({'validation_status':'PRIMARY_INPUTS_VALIDATED_FORECASTS_HYPOTHETICAL',
                'selected_entry':90,'verified_intrinsic_value':120,
                'bear':70,'base':120,'bull':160,'missing_evidence_flags':[],
                'margin_of_safety_entries':{'10pct':108,'15pct':102,'20pct':96},
                'selected_margin_of_safety_pct':20,
                'primary_source_evidence':{'source_hash_sha256':'a'*64,
                    'url':'https://data.sec.gov/api/xbrl/companyfacts/CIK0000000001.json'},
                'assumptions':{'forecast':'illustrative'},'sector_method':'NORMALIZED_EARNINGS_AND_DCF',
                'risks':['Forecast unverified'],'report_as_of_utc':'2026-11-20T22:00:00Z',
                'buy_readiness':{'status':'WAIT_FOR_MARGIN_OF_SAFETY'}})
        v['companies'].append(x)
    return v

class ActiveEntryRetirementTests(unittest.TestCase):
    def test_nvda_33_3938_provisional_deleted_even_if_vendor_file_unmodified(self):
        r=bridge.build(scan(),unofficial(),full60())
        nvda=next(x for x in r['stocks'] if x['ticker']=='NVDA')
        self.assertIsNone(nvda['provisional_entry'])
        self.assertIsNone(nvda['selected_entry_60'])
        self.assertIsNone(nvda['pct_above_entry'])
        self.assertEqual(nvda['validation_status_60'],'NOT VALIDATED')
        self.assertEqual(r['closest_to_buy_top_10'],[])
        self.assertNotIn('33.3938',json.dumps(r))
        self.assertEqual(len(r['stocks']),200)
        self.assertFalse(r['orders_enabled'])

    def test_manual_csv_level_does_not_override_missing_primary_6(self):
        r=bridge.build(scan(),unofficial(),full60())
        baba=next(x for x in r['stocks'] if x['ticker']=='BABA')
        self.assertIsNone(baba['selected_entry_60'])
        self.assertIsNone(baba['provisional_entry'])

    def test_validated_6_entry_can_flow_through_once_reconciled(self):
        r=full60(primary=True)
        # Fixture selects exactly the 20% margin: 120 * 0.80 = 96.
        r['companies'][0]['selected_entry']=96
        out=bridge.build(scan(),unofficial(),r)
        n=out['stocks'][0]
        self.assertIsNone(n['provisional_entry'])
        self.assertEqual(n['selected_entry_60'],96)
        self.assertEqual(n['verified_intrinsic_value_60'],120)
        self.assertEqual(n['margin_of_safety_entries_60']['15pct'],102)
        self.assertEqual(len(out['closest_to_buy_top_10']),1)
        self.assertFalse(out['orders_enabled'])

    def test_mismatched_price_date_blocks_false_entry(self):
        r=full60(primary=True)
        r['companies'][0]['selected_entry']=96
        r['companies'][0]['price_as_of']='2026-11-19T00:00:00'
        out=bridge.build(scan(),unofficial(),r)
        self.assertIsNone(out['stocks'][0]['selected_entry_60'])

    def test_mismatched_safety_level_blocks_false_entry(self):
        r=full60(primary=True)
        r['companies'][0]['selected_entry']=90
        self.assertIsNone(bridge.build(scan(),unofficial(),r)['stocks'][0]['selected_entry_60'])

    def test_unverified_hash_and_source_block_entry(self):
        r=full60(primary=True)
        r['companies'][0]['selected_entry']=96
        r['companies'][0]['primary_source_evidence']={}
        self.assertIsNone(bridge.build(scan(),unofficial(),r)['stocks'][0]['selected_entry_60'])

    def test_malicious_orders_flag_rejected(self):
        r=full60()
        r['orders_enabled']=True
        with self.assertRaisesRegex(ValueError,'Unsafe'):bridge.build(scan(),unofficial(),r)

    def test_incomplete_6_does_not_fall_back(self):
        x=full60()
        x['companies'].pop()
        with self.assertRaisesRegex(ValueError,'Incomplete|missing'):bridge.build(scan(),unofficial(),x)

    def test_6_cache_absent_does_not_return_legacy_buy_levels(self):
        x=bridge.build(scan(),unofficial(),None)
        self.assertIsNone(x['stocks'][0]['selected_entry_60'])
        self.assertIsNone(x['stocks'][0]['provisional_entry'])
        self.assertEqual(x['entry_eligible_count_60'],0)

    def test_top10_only_verified_primary_with_matching_20pct_entry(self):
        valid=full60(primary=True)
        valid['companies'][0]['selected_entry']=96
        out=intel.evidence_qualified_top10(scan(),valid,NOW)
        self.assertEqual(len(out['ranked_top_10']),1)
        self.assertEqual(out['ranked_top_10'][0]['ticker'],'NVDA')
        self.assertIsNone(out['ranked_top_10'][0]['model_watch_entry'])
        self.assertEqual(out['ranked_top_10'][0]['selected_6_0_entry'],96)
        self.assertFalse(out['orders_enabled'])
        empty=intel.evidence_qualified_top10(scan(),full60(),NOW)
        self.assertEqual(empty['ranked_top_10'],[])

    def test_offset_comparisons_do_not_ingest_unverified_model(self):
        top=intel.evidence_qualified_top10(scan(),full60(),NOW)
        with patch('intelligence_layer_51.fx_aud_rate',return_value={'status':'unavailable'}):
            cfg=json.loads((Path(__file__).resolve().parents[1]/'settings/intelligence_51.json').read_text())
            out=intel.after_tax_comparison(top,cfg,{'status':'unavailable'},NOW)
        self.assertEqual(out['ranked_research_scenarios'],[])
        self.assertEqual(len(out['offset_rate_scenarios']),2)
        self.assertFalse(out['orders_enabled'])

    def test_opportunity_triage_suppresses_legacy_manual_prices(self):
        row={'ticker':'NVDA','name':'NVIDIA','price':125.53,'stale_days':0,
             'validated_buy_price':33.3938,'manual_provisional_buy_price':33.3938,
             'fair_value_estimate':66,'fair_value_date':'2026-11-20','valuation_method':'DCF',
             'buy_validation':'VALIDATED'}
        o=opp.assess(row)
        self.assertIsNone(o['validated_buy_price'])
        self.assertIsNone(o['provisional_research_buy'])
        self.assertIsNone(o['fair_value_estimate'])

    def test_earnings_estimate_revisions_not_invented_from_yoy_growth(self):
        from championship_60 import missing_row
        mom={'earnings_signal':'IMPROVING','earnings_yoy_pct':24.0,
             'price_signal':'POSITIVE','price_change_20d_pct':10,'price_change_63d_pct':11}
        row=missing_row({'ticker':'NVDA','company':'NVIDIA','universe':'ORIGINAL_200'},
                        {'price':125.53,'currency':'USD','quote_date':'2026-11-20'},
                        'NORMALIZED_EARNINGS_AND_DCF',NOW,['MISSING_EVIDENCE'],mom)
        self.assertEqual(row['earnings_revisions']['status'],
                         'NOT VALIDATED — NO PRIMARY GUIDANCE OR CONSENSUS REVISION SERIES')
        self.assertIsNone(row['earnings_revisions']['estimated_eps_change_pct'])
        self.assertEqual(row['earnings_momentum']['change_pct'],24.0)

    def test_existing_workflow_schedules_and_order_are_preserved(self):
        root=Path(__file__).resolve().parents[1]
        d=(root/'.github/workflows/scan.yml').read_text()
        w=(root/'.github/workflows/valuation.yml').read_text()
        s=(root/'.github/workflows/discovery.yml').read_text()
        self.assertIn("35 2,8,10,13,16,21 * * *",s)
        self.assertIn("20 2,8,10,13,16,21 * * *",d)
        self.assertIn("10 3 * * 0",w)
        self.assertLess(d.index('run: python championship_60.py --mode scan'),d.index('run: python report_bridge.py'))
        self.assertLess(d.index('run: python report_bridge.py'),d.index('run: python intelligence_layer_51.py --mode scan'))
        self.assertLess(w.index('run: python championship_60.py --mode weekly'),w.index('run: python intelligence_layer_51.py --mode valuation'))
        self.assertIn('for attempt in 1 2 3 4 5 6',d)
        self.assertIn('for attempt in 1 2 3 4 5 6',w)
        self.assertIn('for attempt in 1 2 3 4 5 6',s)

if __name__=='__main__':unittest.main()
