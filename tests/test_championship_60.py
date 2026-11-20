"""6.0 tests: deterministic mock first-party evidence, never real trades or network."""
import csv
import json
import math
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock,patch
import championship_60 as m
NOW=datetime(2026,11,21,3,0,tzinfo=timezone.utc)
CFG=m.DEFAULT_ASSUMPTIONS

def fixture_company(n=8,sh=100_000_000,earn=500_000_000,cash=600_000_000,sector='STABLE',stale=False):
    """Synthetic issuer evidence for tests, never public company observations."""
    facts={k:[] for k in m.TAG_MAP}
    facts['shares'].append({'end':'2025-09-30','value':sh,'form':'10-Q','filed':'2025-11-10'})
    y=2025
    for i in range(n):
        yr=y-n+1+i
        start=f'{yr}-01-01';end=f'{yr}-12-31'
        if i==n-1:
            end=f'{yr}-12-31'
        facts['net_income'].append({'start':start,'end':end,'value':earn*(1+i*.06),
             'accession':f'0000-{yr}-A','filed':f'{yr+1}-02-10','form':'10-K'})
        facts['revenue'].append({'start':start,'end':end,'value':2e9*(1+i*.05),'filed':f'{yr+1}-02-10'})
        facts['operating_cash_flow'].append({'start':start,'end':end,'value':cash*(1+i*.03),
           'accession':f'0000-{yr}-A','filed':f'{yr+1}-02-10'})
        facts['capex'].append({'start':start,'end':end,'value':cash*.2*(1+i*.03),
           'accession':f'0000-{yr}-A','filed':f'{yr+1}-02-10'})
        facts['equity'].append({'end':end,'value':2e9*(1+i*.05),'filed':f'{yr+1}-02-10'})
        facts['assets'].append({'end':end,'value':5e9*(1+i*.05)})
        facts['liabilities'].append({'end':end,'value':3e9*(1+i*.05)})
    # Actual source SEC facts use start/end inclusive: 364 days for calendar FY.
    shares={'end':'2026-09-30','value':sh,'form':'10-Q','filed':'2026-11-10'}
    return {'ticker':'TEST','issuer_name':'Synthetic Test Corporation','cik':123,
       'source_url':'https://data.sec.gov/api/xbrl/companyfacts/CIK0000000123.json',
       'observed_utc':NOW.isoformat() if not stale else '2025-01-01T00:00:00+00:00',
       'status':'OFFICIAL_SEC_COMPANYFACTS_RETRIEVED','latest_share_count':shares,
       'annual_facts':facts,'evidence_hash_sha256':'a'*64,'orders_enabled':False}

def raw_fixture(cik=123,years=6):
    facts={'us-gaap':{},'dei':{}}
    def add(ns,key,unit,items):facts[ns][key]={'units':{unit:items}}
    fs={k:[] for k in ['cash','capex','ni','revenue','equity']}
    for yr in range(2020,2020+years):
        meta={'start':f'{yr}-01-01','end':f'{yr}-12-31','form':'10-K',
           'filed':f'{yr+1}-02-10','accn':f'000123-{yr}', 'fp':'FY', 'fy':yr}
        fs['cash'].append({**meta,'val':500_000_000})
        fs['capex'].append({**meta,'val':100_000_000})
        fs['ni'].append({**meta,'val':350_000_000})
        fs['revenue'].append({**meta,'val':2_000_000_000})
        fs['equity'].append({'end':meta['end'],'form':'10-K','filed':meta['filed'],'val':1_500_000_000})
    add('us-gaap','NetCashProvidedByUsedInOperatingActivities','USD',fs['cash'])
    add('us-gaap','PaymentsToAcquirePropertyPlantAndEquipment','USD',fs['capex'])
    add('us-gaap','NetIncomeLoss','USD',fs['ni'])
    add('us-gaap','Revenues','USD',fs['revenue'])
    add('us-gaap','StockholdersEquity','USD',fs['equity'])
    add('dei','EntityCommonStockSharesOutstanding','shares',[
       {'end':'2025-09-30','filed':'2025-11-10','form':'10-Q','val':100_000_000,'accn':'shprev'},
       {'end':'2026-09-30','filed':'2026-11-10','form':'10-Q','val':100_000_000,'accn':'sh'}])
    return {'cik':cik,'entityName':'Synthetic Test Corporation','facts':facts}

class InputTests(unittest.TestCase):
    def test_default_configuration(self):self.assertEqual(m.validate_cfg(CFG)['safety']['levels_pct'],[10,15,20])
    def test_unsafe_discount_rejected(self):
        c=json.loads(json.dumps(CFG));c['dcf']['base_cost_of_equity_pct']=2
        with self.assertRaises(ValueError):m.validate_cfg(c)
    def test_dcf_terminal_gap(self):
        with self.assertRaises(ValueError):m.dcf(1,.05,.03,.02,5)
    def test_method_sector_selection(self):
        self.assertEqual(m.method('JPM','US Finance'), 'BANK_INSURER_JUSTIFIED_BOOK')
        self.assertEqual(m.method('BHP.AX','Australia'),'FULL_CYCLE_NORMALIZED_EARNINGS')
        self.assertEqual(m.method('SLS','Biotechnology'),'PROJECT_RISK_ADJUSTED_NAV')
        self.assertEqual(m.method('GMG.AX','Australia'),'PROPERTY_ASSET_NAV_OR_AFFO')
        self.assertEqual(m.method('MSFT','Technology'),'NORMALIZED_EARNINGS_AND_DCF')
    def test_sec_mapping_issuer_identity_required(self):
        with self.assertRaises(ValueError):m.primary_series('TEST',raw_fixture(cik=456),NOW,123)
    def test_no_annual_quarterly_mix(self):
        payload=raw_fixture();items=payload['facts']['us-gaap']['NetIncomeLoss']['units']['USD']
        items.append({'start':'2025-10-01','end':'2025-12-31','filed':'2026-02-10','form':'10-K','val':999999999})
        o=m.primary_series('TEST',payload,NOW,123)
        self.assertEqual(len(o['annual_facts']['net_income']),6)
    def test_source_series_hash_and_provenance(self):
        o=m.primary_series('TEST',raw_fixture(),NOW,123)
        self.assertEqual(len(o['evidence_hash_sha256']),64)
        self.assertEqual(o['latest_share_count']['value'],100_000_000)
        self.assertIn('accession',o['annual_facts']['net_income'][-1])
    def test_primary_series_individual_period_reconciliation(self):
        o=m.primary_series('TEST',raw_fixture(),NOW,123)
        ps=m.combine_periods(o)
        self.assertEqual(ps[-1]['fcf'],400_000_000)
        self.assertEqual(len(ps),6)
    def test_mismatched_cash_period_fails(self):
        o=fixture_company(n=6)
        o['annual_facts']['capex'][-1]['start']='2025-04-01'
        ps=m.combine_periods(o)
        self.assertIsNone(ps[-1]['fcf'])

class ModelTests(unittest.TestCase):
    def test_four_year_filed_fcf_and_net_income_validates_hypothetical(self):
        o=fixture_company(n=6)
        vals,assumptions,flags=m.scenario_values('NORMALIZED_EARNINGS_AND_DCF',m.combine_periods(o),o,CFG,NOW)
        self.assertIsNotNone(vals);self.assertEqual(flags,[])
        self.assertLess(vals['bear'],vals['base']);self.assertLess(vals['base'],vals['bull'])
        self.assertEqual(assumptions['forecast_status'],'ANALYST_HYPOTHESIS_NOT_VERIFIED_FORWARD_GUIDANCE')
    def test_cyclicals_require_seven_years(self):
        o=fixture_company(n=6)
        val,a,flags=m.scenario_values('FULL_CYCLE_NORMALIZED_EARNINGS',m.combine_periods(o),o,CFG,NOW)
        self.assertIsNone(val);self.assertIn('CYCLICAL_FULL_CYCLE_SEVEN_YEARS_NOT_EVIDENCED',flags)
    def test_cyclicals_use_seven_years(self):
        o=fixture_company(n=8)
        vals,a,flags=m.scenario_values('FULL_CYCLE_NORMALIZED_EARNINGS',m.combine_periods(o),o,CFG,NOW)
        self.assertIsNotNone(vals);self.assertEqual(a['annual_years'],7)
    def test_bank_book_not_fcf_model(self):
        o=fixture_company(n=6)
        vals,a,flags=m.scenario_values('BANK_INSURER_JUSTIFIED_BOOK',m.combine_periods(o),o,CFG,NOW)
        self.assertIsNotNone(vals);self.assertIn('BOOK_VALUE_PER_SHARE',a['formula'])
    def test_specialist_asset_nav_missing_evidence_has_no_price(self):
        o=fixture_company()
        for key in ('PROPERTY_ASSET_NAV_OR_AFFO','HOLDING_COMPANY_ASSET_NAV','PROJECT_RISK_ADJUSTED_NAV'):
            v,a,f=m.scenario_values(key,m.combine_periods(o),o,CFG,NOW)
            self.assertIsNone(v);self.assertIn('SPECIALIST_ASSET_OR_PIPELINE_EVIDENCE_REQUIRED',f)
    def test_invalid_stale_share_count_blocks(self):
        o=fixture_company();o['latest_share_count']['end']='2022-01-01'
        v,a,f=m.scenario_values('NORMALIZED_EARNINGS_AND_DCF',m.combine_periods(o),o,CFG,NOW)
        self.assertIsNone(v);self.assertIn('CURRENT_PRIMARY_SHARE_COUNT_MISSING',f)
    def test_negative_cashflow_blocks(self):
        o=fixture_company()
        o['annual_facts']['operating_cash_flow'][-1]['value']=-100_000_000
        v,a,f=m.scenario_values('NORMALIZED_EARNINGS_AND_DCF',m.combine_periods(o),o,CFG,NOW)
        self.assertIsNone(v);self.assertIn('LOSS_OR_NEGATIVE_FREE_CASH_FLOW_NEEDS_SPECIALIST_MODEL',f)
    def test_dilution_math(self):
        v,a,f=m.scenario_values('NORMALIZED_EARNINGS_AND_DCF',m.combine_periods(fixture_company()),fixture_company(),CFG,NOW)
        self.assertAlmostEqual(m.stress_adjust(115,15),100)
    def test_momentum_cannot_validate(self):
        data={'change_20d_pct':20,'change_63d_pct':15,'price':120,'sma_50':100}
        mom=m.momentum(data,m.combine_periods(fixture_company()),CFG)
        self.assertIn(mom['momentum_selected_margin_of_safety_pct'],(10,15,20))
        row=m.missing_row({'ticker':'X','company':'X','universe':'DISCOVERY'},data,'NONE',NOW,['FILING_MISSING'],mom)
        self.assertIsNone(row['selected_entry']);self.assertEqual(row['validation_status'],'NOT VALIDATED')
    def test_positive_vs_negative_momentum_changes_safety(self):
        history=[{'net_income':100},{'net_income':120}]
        a=m.momentum({'price':120,'sma_50':110,'change_20d_pct':6,'change_63d_pct':5},history,CFG)
        b=m.momentum({'price':120,'change_20d_pct':-5,'change_63d_pct':-8},history,CFG)
        self.assertEqual(a['momentum_selected_margin_of_safety_pct'],10)
        self.assertEqual(b['momentum_selected_margin_of_safety_pct'],20)

class WorkflowTests(unittest.TestCase):
    def prep(self,p):
        root=Path(p);(root/'settings').mkdir();(root/'reports').mkdir();(root/'data').mkdir()
        (root/'settings/championship_60.json').write_text(json.dumps(CFG))
        with (root/'watchlist.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=['ticker','name','sector']);w.writeheader()
            w.writerows({'ticker':f'T{i:03d}','name':f'Co {i}','sector':'Technology'} for i in range(200))
        (root/'data/latest.json').write_text(json.dumps({'stocks':[{'ticker':f'T{i:03d}','price':100,'currency':'USD','quote_date':'2026-11-20','change_20d_pct':6,'change_63d_pct':9,'sma_50':90} for i in range(200)]}))
        (root/'reports/discovery_watchlist.json').write_text(json.dumps({'orders_enabled':False,'original_200_unchanged':True,'candidates':{
             'EINS':{'company':'New ASX discovery','status':'PENDING_EVIDENCE','last_quote':None}}}))
        return root
    def test_all_200_plus_discovery_no_fabricated_targets(self):
        with tempfile.TemporaryDirectory() as p:
            root=self.prep(p)
            out=m.run(root,'scan',now=NOW)
            self.assertEqual(out['reported'],201);self.assertEqual(out['validated'],0)
            j=json.loads((root/'reports/valuation_60_latest.json').read_text())
            self.assertEqual(sum(x['universe']=='ORIGINAL_200' for x in j['companies']),200)
            self.assertTrue(all(x['validation_status']=='NOT VALIDATED' for x in j['companies']))
            self.assertTrue(all(x['verified_intrinsic_value'] is None for x in j['companies']))
            self.assertFalse(j['orders_enabled']);self.assertEqual(j['validated_buy_signal_count'],0)
    def test_with_verified_primary_single_company_has_entries(self):
        with tempfile.TemporaryDirectory() as p:
            root=self.prep(p)
            fixture=fixture_company(n=6)
            (root/'reports/primary_series_cache_60.json').write_text(json.dumps({'orders_enabled':False,'companies':{'T000':fixture}}))
            out=m.run(root,'scan',now=NOW)
            self.assertEqual(out['validated'],1)
            j=read_out(root)
            candidate=j['companies'][0]
            self.assertEqual(candidate['ticker'],'T000')
            self.assertEqual(candidate['validation_status'],'PRIMARY_INPUTS_VALIDATED_FORECASTS_HYPOTHETICAL')
            self.assertEqual(set(candidate['margin_of_safety_entries']),{'10pct','15pct','20pct'})
            self.assertLess(candidate['margin_of_safety_entries']['20pct'],candidate['margin_of_safety_entries']['10pct'])
            self.assertIsNone(candidate['buy_readiness']['score_pct'])
            self.assertFalse(candidate['orders_enabled'])
    def test_no_file_read_network_offline(self):
        with tempfile.TemporaryDirectory() as p:
            root=self.prep(p);session=Mock()
            result=m.run(root,'evidence-update',offline=True,session=session,now=NOW)
            self.assertEqual(result['status'],'OFFLINE_NO_NETWORK');session.get.assert_not_called()
    def test_sec_directory_403_does_not_hallucinate(self):
        with tempfile.TemporaryDirectory() as p:
            root=self.prep(p)
            sess=Mock();sess.get.return_value.status_code=403
            with patch.dict('os.environ',{'SEC_USER_AGENT':'Research contact@example.com'}):
                z=m.run(root,'evidence-update',session=sess,now=NOW)
            self.assertEqual(z['status'],'DIRECTORY_UNAVAILABLE')
            self.assertEqual(sess.get.call_count,1)
    def test_bounded_sec_requests_and_cache_retention(self):
        with tempfile.TemporaryDirectory() as p:
            root=self.prep(p)
            payload={'fields':['ticker','cik','exchange'],
                     'data':[[f'T{i:03d}',100+i,'NASDAQ'] for i in range(200)]}
            sess=Mock();
            class Reply:
                status_code=200
                def __init__(self,data):self.data=data
                def json(self):return self.data
            sess.get.side_effect=[Reply(payload)]+[Reply(raw_fixture(cik=100+i)) for i in range(12)]
            with patch.dict('os.environ',{'SEC_USER_AGENT':'Research contact@example.com'}),patch.object(m.time,'sleep'):
                result=m.run(root,'evidence-update',session=sess,now=NOW)
            self.assertEqual(result['cache_companies'],12)
            self.assertEqual(sess.get.call_count,13)
            out=json.loads((root/'reports/primary_series_cache_60.json').read_text())
            self.assertFalse(out['orders_enabled'])
            self.assertEqual(len(out['companies']),12)
            self.assertEqual(out['companies']['T000']['cik'],100)
    def test_original_200_invariant(self):
        with tempfile.TemporaryDirectory() as p:
            root=self.prep(p)
            (root/'watchlist.csv').write_text('ticker,name,sector\nAAA,x,y\n')
            with self.assertRaises(ValueError):m.run(root,'scan',now=NOW)

def read_out(root):return json.loads((root/'reports/valuation_60_latest.json').read_text())

if __name__=='__main__':unittest.main()

class ExtendedSectorAndReliabilityTests(unittest.TestCase):
    def test_asset_book_nav_is_not_intrinsic_value(self):
        src=fixture_company()
        info=m.asset_nav_book_proxy(src,NOW)
        self.assertIsNotNone(info)
        self.assertEqual(info['valuation_status'],'INFORMATION_ONLY_NOT_INTRINSIC_VALUE')
        self.assertNotIn('intrinsic_value',info)
    def test_asset_nav_formula_only_when_verified_appraisal_inputs_supplied(self):
        v=m.asset_nav_formula(200_000_000,50_000_000,10_000_000)
        self.assertEqual(v['base'],13.0)
        with self.assertRaises(ValueError):m.asset_nav_formula(200_000_000,None,10_000_000)
        with self.assertRaises(ValueError):m.asset_nav_formula(100_000_000,99_000_000,10_000_000)
    def test_primary_financial_evidence_does_not_resolve_adr_ratio(self):
        with tempfile.TemporaryDirectory() as d:
            root=WorkflowTests().prep(d)
            source=fixture_company()
            (root/'reports/primary_series_cache_60.json').write_text(json.dumps({'orders_enabled':False,'companies':{'T000':source}}))
            # Simulate an international ADR company without documented ADR/common-share ratio.
            with (root/'watchlist.csv').open(newline='') as f:rows=list(csv.DictReader(f))
            rows[0].update({'ticker':'SHEL','sector':'International'})
            with (root/'watchlist.csv').open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=['ticker','name','sector']);w.writeheader();w.writerows(rows)
            src=json.loads((root/'reports/primary_series_cache_60.json').read_text())
            src['companies']['SHEL']=src['companies'].pop('T000')
            (root/'reports/primary_series_cache_60.json').write_text(json.dumps(src))
            scan=json.loads((root/'data/latest.json').read_text());scan['stocks'][0]['ticker']='SHEL'
            (root/'data/latest.json').write_text(json.dumps(scan))
            result=m.run(root,'scan',now=NOW)
            self.assertEqual(result['validated'],0)
            row=json.loads((root/'reports/valuation_60_latest.json').read_text())['companies'][0]
            self.assertIn('ADR_OR_FOREIGN_PRIMARY_SHARE_BASIS_NOT_RECONCILED',row['missing_evidence_flags'])
    def test_provider_rate_limit_sets_persistent_cooldown(self):
        with tempfile.TemporaryDirectory() as p:
            root=WorkflowTests().prep(p)
            payload={'fields':['ticker','cik','exchange'],'data':[['T000',123,'NASDAQ']]}
            sess=Mock();r1=Mock(status_code=200);r1.json.return_value=payload
            r2=Mock(status_code=429);sess.get.side_effect=[r1,r2]
            with patch.dict('os.environ',{'SEC_USER_AGENT':'Research contact@example.com'}):
                data=m.run(root,'evidence-update',session=sess,now=NOW)
                self.assertEqual(data['status'],'PARTIAL_OR_UNAVAILABLE')
                sess2=Mock()
                result=m.run(root,'evidence-update',session=sess2,now=NOW+timedelta(minutes=5))
            self.assertEqual(result['status'],'GLOBAL_PROVIDER_COOLDOWN_ACTIVE')
            sess2.get.assert_not_called()
    def test_missing_data_never_turns_watchlist_manual_entry_into_60_target(self):
        with tempfile.TemporaryDirectory() as p:
            root=WorkflowTests().prep(p)
            with (root/'watchlist.csv').open() as f:rows=list(csv.DictReader(f))
            rows[0]['buy_price']='10';rows[0]['buy_validation']='PROVISIONAL'
            with (root/'watchlist.csv').open('w',newline='') as f:
                writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
            m.run(root,'scan',now=NOW)
            first=read_out(root)['companies'][0]
            self.assertEqual(first['validation_status'],'NOT VALIDATED')
            self.assertIsNone(first['selected_entry'])
            self.assertIsNone(first['margin_of_safety_entries']['20pct'])

class AdditionalFilingsChecks(unittest.TestCase):
    def test_same_period_fcf_requires_same_filing_accession(self):
        o=fixture_company()
        o['annual_facts']['capex'][-1]['accession']='not-the-ocf-filing'
        out=m.combine_periods(o)
        self.assertIsNone(out[-1]['fcf'])
    def test_secondary_share_count_required(self):
        o=fixture_company();o['annual_facts']['shares']=[]
        v,a,f=m.scenario_values('NORMALIZED_EARNINGS_AND_DCF',m.combine_periods(o),o,CFG,NOW)
        self.assertIsNone(v)
        self.assertIn('SECOND_INDEPENDENT_DATED_PRIMARY_SHARE_COUNT_REQUIRED',f)
    def test_big_dilution_or_split_blocks_without_reconciliation(self):
        o=fixture_company();o['annual_facts']['shares'][0]['value']=50_000_000
        v,a,f=m.scenario_values('NORMALIZED_EARNINGS_AND_DCF',m.combine_periods(o),o,CFG,NOW)
        self.assertIsNone(v)
        self.assertIn('PRIMARY_SHARE_BASIS_CHANGE_OVER_15PCT_SPLIT_OR_DILUTION_REVIEW',f)
