import copy
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from championship_90 import trading_lows, reconcile, specialist, priority, build
NOW=datetime(2026,11,24,tzinfo=timezone.utc)
def document(facts):
    return {'issuer':'Example issuer','source_url':'https://issuer.example/filing', 'accession_or_document_id':'annual-2026',
            'as_of':'2026-11-01','published_at':'2026-11-15','review_status':'PRIMARY_DOCUMENT_FIELDS_RECONCILED','facts':facts,
            'facts_sha256':hashlib.sha256(json.dumps(facts,sort_keys=True).encode()).hexdigest()}
def primary(currency='USD'):
    return {'ticker':'TEST','latest_share_count':{'value':100,'end':'2026-11-01'},
            'annual_facts':{'shares':[{'value':100,'end':'2026-11-01'}], 'net_income':[{'value':1000,'unit':currency}]}}
class Models(unittest.TestCase):
    def test_intraday_lows_and_previous_window(self):
        a=trading_lows(list(range(300,0,-1)),list(range(301,1,-1)))
        self.assertEqual(a['low_5d'],1);self.assertEqual(a['low_30d'],1)
        self.assertEqual(a['previous_5d_low'],2);self.assertEqual(a['low_52w'],1)
    def test_no_invented_intraday_or_short_history(self):
        self.assertIsNone(trading_lows([], [10]*300)['low_5d'])
        self.assertIsNone(trading_lows([1]*29,[2]*29)['low_30d'])
        self.assertIsNone(trading_lows([1]*251,[2]*251)['low_52w'])
    def test_adr_fx_direction_and_no_mutation(self):
        p=primary('EUR'); original=copy.deepcopy(p)
        basis=document({'ticker':'TEST','quote_currency':'USD','ordinary_shares_per_receipt':2,'ordinary_shares_outstanding':100})
        fx={'from':'EUR','to':'USD','rate':1.1,'as_of':'2026-11-23','source_url':'https://fx.example/dated'}
        n,a=reconcile(p,'USD',basis,fx,NOW,True)
        self.assertEqual(n['latest_share_count']['value'],50)
        self.assertEqual(n['annual_facts']['net_income'][0]['value'],1100)
        self.assertEqual(p,original); self.assertEqual(a['status'],'RECONCILED')
        self.assertIsNone(reconcile(p,'USD',basis,{**fx,'from':'USD'},NOW,True)[0])
        self.assertIsNone(reconcile(p,'USD',basis,{**fx,'as_of':'2025-01-01'},NOW,True)[0])
    def test_missing_ratio_currency_or_share_discrepancy_blocks(self):
        p=primary()
        self.assertIsNone(reconcile(p,'USD',None,None,NOW,True)[0])
        basis=document({'ticker':'TEST','quote_currency':'USD','ordinary_shares_per_receipt':2,'ordinary_shares_outstanding':120})
        self.assertIsNone(reconcile(p,'USD',basis,None,NOW,True)[0])
        p['annual_facts']['equity']=[{'value':100,'unit':'EUR'}]
        self.assertIsNone(reconcile(p,'USD',None,None,NOW)[0])
    def test_invalid_hash_and_future_date(self):
        basis=document({'ticker':'TEST','quote_currency':'USD','ordinary_shares_per_receipt':1,'ordinary_shares_outstanding':100})
        for change in [{'facts_sha256':'x'}, {'published_at':'2026-11-25'}]:
            self.assertIsNone(reconcile(primary(),'USD',{**basis,**change},None,NOW,True)[0])
    def test_verified_split_normalizes_prior_not_current(self):
        p=primary();p['annual_facts']['shares'].append({'value':50,'end':'2026-01-01'})
        basis=document({'ticker':'TEST','quote_currency':'USD','ordinary_shares_per_receipt':1,'ordinary_shares_outstanding':100,'splits':[{'new_per_old':2,'effective_date':'2026-06-01'}]})
        n,a=reconcile(p,'USD',basis,None,NOW)
        self.assertEqual([r['value'] for r in n['annual_facts']['shares']],[100,100])
    def test_specialist_methods_and_null_missing(self):
        cases=[('PROPERTY_ASSET_NAV_OR_AFFO',{'affo':80,'shares':10},100),
               ('HOLDING_COMPANY_ASSET_NAV',{'appraised_assets':1000,'total_liabilities':250,'shares':10},60),
               ('SPECIALIST_FINANCIAL_CAPITAL_STRUCTURE',{'tangible_common_equity':1000,'normalized_roe':.14,'shares':10},100),
               ('PROJECT_RISK_ADJUSTED_NAV',{'risk_adjusted_project_npv':1000,'cash':100,'debt':50,'remaining_funding':250,'shares':10},80)]
        for m,f,base in cases:
            vals,flags,_=specialist(m,document(f),NOW)
            self.assertAlmostEqual(vals['base'],base);self.assertFalse(flags)
            self.assertLessEqual(vals['bear'],vals['base']);self.assertLessEqual(vals['base'],vals['bull'])
            f.pop('shares');self.assertIsNone(specialist(m,document(f),NOW)[0])
    def test_thresholds_strict_and_inclusive_and_stale(self):
        q={'price':40,'currency':'USD','quote_date':'2026-11-23','previous_5d_low':41}
        self.assertFalse(priority('HPE',q,NOW)['threshold_met'])
        self.assertTrue(priority('HPE',{**q,'price':39.99},NOW)['threshold_met'])
        self.assertTrue(priority('SKS.AX',{**q,'price':5,'currency':'AUD'},NOW)['threshold_met'])
        self.assertTrue(priority('DUG.AX',{**q,'price':1.5,'currency':'AUD'},NOW)['threshold_met'])
        self.assertIsNone(priority('DUG.AX',{**q,'price':1.5},NOW)['threshold_met'])
        self.assertIsNone(priority('HPE',{**q,'quote_date':'2025-01-01'},NOW)['threshold_met'])
    def test_all_200_assessed_without_financial_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'watchlist.csv').write_text('ticker,name,sector\n'+''.join(f'T{i},Company,Technology\n' for i in range(200)))
            (root/'reports').mkdir()
            (root/'reports/priority_quotes_90.json').write_text(json.dumps({'quotes':{'HPE':{'price':39,'currency':'USD','quote_date':'2026-11-23','low_basis':'UNADJUSTED_DAILY_INTRADAY_LOW','low_52w':20}}}))
            out=build(root,now=NOW)
            self.assertEqual(next(r for r in out['companies'] if r['ticker']=='HPE')['trading_lows']['trading_low_52w'],20)
            self.assertEqual(out['coverage_comparison']['original_200_assessed_after'],200)
            self.assertEqual(out['coverage_comparison']['original_200_valued_after'],0)
            self.assertEqual(len(out['companies']),203)
            self.assertTrue(all(r['scenarios'] is None for r in out['companies']))
            self.assertEqual(out['ranked_pre_recovery_top10'],[])
if __name__=='__main__':unittest.main()
