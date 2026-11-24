import copy, json, tempfile, unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from dynamic_earnings_92 import (build, verify, load_periods, growth, ttm,
    acceleration, matched_cash, forward, digest, recovery_context, provisional_model)
from collect_dynamic_92 import period_type
from collect_documents_dynamic_92 import inspect_document

ROOT=Path(__file__).resolve().parents[1]
NOW=datetime(2026,11,25,tzinfo=timezone.utc)

class DynamicFinancialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture=json.loads((ROOT/'tests/fixtures/dynamic_cases_92.json').read_text())
        cls.records=cls.fixture['records']
        cls.guidance=cls.fixture['guidance']
        cls.policy=cls.fixture['policy']
        cls.adapters=cls.fixture['adapters']
        cls.old={r['ticker']:r for r in cls.fixture['historical_report']['companies']}

    def model(self,ticker,guidance=None):
        return forward(guidance or self.guidance[ticker],self.old[ticker],self.records[ticker],self.policy,self.adapters,NOW)

    def test_hpe_gaap_guidance_not_adjusted_or_basic_share_count(self):
        out,missing=self.model('HPE')
        self.assertFalse(missing)
        self.assertEqual(out['scenarios'],{'bear':36.8,'base':53.62,'bull':71.64})
        self.assertEqual(out['eps_range'],{'low':3.68,'high':3.98})
        self.assertTrue(out['assumptions']['direct_diluted_eps_not_rescaled_by_issued_shares'])

    def test_hpe_current_quarter_attributable_common_income(self):
        facts=self.records['HPE']['metrics']
        current=lambda k:next(r['value'] for r in facts[k] if r['period_type']=='QUARTER' and r['period_end']=='2026-10-31')
        self.assertEqual(current('net_income'),1788000000)
        self.assertEqual(current('group_net_income'),1817000000)
        self.assertEqual(current('eps_diluted'),1.26)
        self.assertEqual(current('diluted_weighted_shares'),1445000000)

    def test_hpe_reported_fcf_and_simple_fcf_are_separate(self):
        cash=matched_cash(self.records['HPE'],'USD',NOW)
        self.assertEqual(cash['simple_fcf'],3862000000)
        self.assertIsNone(cash['owner_cash_flow'])
        f=next(r for r in self.records['HPE']['metrics']['reported_fcf'] if r['period_type']=='ANNUAL' and r['period_end']=='2026-10-31')
        self.assertEqual(f['value'],4496000000)

    def test_sks_pbt_is_converted_with_explicit_assumptions(self):
        out,missing=self.model('SKS.AX');self.assertFalse(missing)
        self.assertEqual(out['eps_basis'],'MODEL_AFTER_TAX_EPS_FROM_MANAGEMENT_PBT_NOT_GUIDED_EPS')
        self.assertEqual(len(out['assumptions']['adjustments']),3)
        self.assertAlmostEqual(out['scenarios']['base'],4.7386,places=4)

    def test_sks_owner_cashflow_includes_intangibles_and_lease_principal(self):
        cash=matched_cash(self.records['SKS.AX'],'AUD',NOW)
        self.assertEqual(cash['owner_cash_flow'],37879639)

    def test_dug_ebitda_update_is_not_eps_guidance(self):
        out,missing=self.model('DUG.AX')
        self.assertIsNone(out)
        self.assertIn('GUIDANCE_DOES_NOT_SUPPORT_COMMON_EQUITY_EARNINGS',missing)

    def test_dug_usd_cents_and_group_vs_owner_income(self):
        metrics=self.records['DUG.AX']['metrics']
        value=lambda k:next(r['value'] for r in metrics[k] if r['period_end']=='2026-06-30')
        self.assertEqual(value('net_income'),1820000)
        self.assertEqual(value('group_net_income'),2641000)
        self.assertEqual(value('eps_diluted'),.0131)
        self.assertEqual(value('lease_current')+value('lease_noncurrent'),42702000)

    def test_dug_lease_principal_and_financing_interest_reduce_owner_cash(self):
        cash=matched_cash(self.records['DUG.AX'],'USD',NOW)
        self.assertEqual(cash['simple_fcf'],9394000)
        self.assertEqual(cash['owner_cash_flow'],-5749000)

    def test_no_blanket_growth_cap_on_primary_guidance(self):
        g=copy.deepcopy(self.guidance['HPE']);g['facts']['low']=10;g['facts']['high']=12;g['facts']['non_gaap_eps_low']=11.37;g['facts']['non_gaap_eps_high']=13.37;g['facts_sha256']=digest(g['facts'])
        out,_=self.model('HPE',g)
        self.assertEqual(out['scenarios']['base'],154)

    def test_adjusted_eps_without_gaap_bridge_does_not_pass(self):
        g=copy.deepcopy(self.guidance['HPE']);g['facts']['metric']='NON_GAAP_DILUTED_EPS';g['facts_sha256']=digest(g['facts'])
        self.assertIsNone(self.model('HPE',g)[0])

    def test_mutated_guidance_hash_fails(self):
        g=copy.deepcopy(self.guidance['HPE']);g['facts']['low']=500
        self.assertIsNone(self.model('HPE',g)[0])

    def test_expired_guidance_fails(self):
        g=copy.deepcopy(self.guidance['HPE']);g['facts']['target_period_end']='2026-10-31';g['facts_sha256']=digest(g['facts'])
        self.assertIn('GUIDANCE_TARGET_PERIOD_ENDED',self.model('HPE',g)[1])

    def test_per_receipt_basis_is_required(self):
        g=copy.deepcopy(self.guidance['HPE']);g['facts'].pop('per_share_basis');g['facts_sha256']=digest(g['facts'])
        self.assertIn('GUIDANCE_PER_LISTED_SHARE_BASIS_REQUIRED',self.model('HPE',g)[1])

    def test_receipt_eps_is_not_rescaled_twice(self):
        row={**self.old['HPE'],'currency':'AUD'}
        adapters={'HPE':{'fx':{'from':'USD','to':'AUD','rate':1.5,'as_of':'2026-11-25'}}}
        out,_=forward(self.guidance['HPE'],row,self.records['HPE'],self.policy,adapters,NOW)
        self.assertEqual(out['scenarios']['base'],80.43)

    def test_no_adr_eps_basis_inference_for_provisional_model(self):
        self.assertIsNone(provisional_model(self.records['RMD.AX'],self.old['RMD.AX'],self.policy,self.adapters,NOW))

    def test_turnaround_is_not_infinite_percentage_growth(self):
        self.assertEqual(growth(20,-10),{'status':'TURNAROUND','pct':None})

    def test_background_hpe_parser_requires_explicit_annual_gaap_range(self):
        from guidance_dynamic_92 import extract_hpe
        company={'cik':1645590,'financial_currency':'USD','issuer_name':'HPE','annual_facts':{'net_income':[{'end':'2026-10-31'}]}}
        meta={'url':'https://www.sec.gov/Archives/edgar/data/1645590/a/ex99.htm','sha256':'a'*64,'accession':'a','filed':'2026-11-23'}
        html='<p>Fiscal 2027 Full Year Outlook HPE estimates GAAP diluted net EPS to be in the range of $3.68 to $3.98.</p>'
        rec=extract_hpe(html,meta,company,NOW)
        self.assertEqual(rec['facts']['target_period_end'],'2027-10-31')
        self.assertEqual(rec['facts']['low'],3.68)
        self.assertIsNone(extract_hpe(html.replace('GAAP diluted','non-GAAP diluted'),meta,company,NOW))
        self.assertIsNone(extract_hpe(html.replace('Full Year','First Quarter'),meta,company,NOW))

    def test_unrelated_issuer_cannot_use_hpe_guidance_rule(self):
        from guidance_dynamic_92 import extract_hpe
        self.assertIsNone(extract_hpe('Fiscal 2027 Full Year Outlook',{}, {'cik':1},NOW))

    def test_failed_scan_fallback_preserves_original_quote_timestamp(self):
        from championship_60 import latest_quote
        from championship_90 import write
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            write(root/'data/latest.json',{'stocks':[{'ticker':'AAA','price':None,'quote_date':None}]})
            write(root/'reports/latest.json',{'stocks':[{'ticker':'AAA','last_daily_close':None}]})
            write(root/'reports/valuation_90_latest.json',{'companies':[{'ticker':'AAA','price':12.5,'quote_date':'2026-11-20','currency':'USD','trading_lows':{'low_5d':12}}]})
            quote=latest_quote(root,{'AAA'})['AAA']
            self.assertEqual(quote['price'],12.5)
            self.assertEqual(quote['quote_date'],'2026-11-20')
            self.assertIn('FALLBACK_NOT_LIVE',quote['price_source'])

    def test_ytd_is_not_a_quarter(self):
        from datetime import date
        self.assertEqual(period_type(date(2026,1,1),date(2026,9,30)),'NINE_MONTH_YTD')
        record={'metrics':{'revenue':[{'period_type':'NINE_MONTH_YTD','value':300,'accession':'a','period_start':'2026-01-01','period_end':'2026-09-30','filed':'2026-11-01','source_url':'https://www.sec.gov/a','currency':'USD','unit':'USD'}]}}
        self.assertEqual(acceleration(record,'revenue','USD',NOW)['status'],'QUARTERLY_DISCLOSURE_NOT_RECOVERED')

    def test_ttm_requires_same_comparative_accession_and_intervals(self):
        def fact(start,end,value,kind,accession):return {'period_start':start,'period_end':end,'value':value,'period_type':kind,'accession':accession,'filed':'2026-11-01','accounting_basis':'US_GAAP','source_url':'https://www.sec.gov/a','currency':'USD','unit':'USD'}
        rows=[fact('2025-01-01','2025-12-31',100,'ANNUAL','annual'),fact('2025-01-01','2025-09-30',70,'NINE_MONTH_YTD','q3'),fact('2026-01-01','2026-09-30',90,'NINE_MONTH_YTD','q3')]
        rec={'metrics':{'net_income':rows}}
        self.assertEqual(ttm(rec,'net_income','USD',NOW)['value'],120)
        rows[1]['accession']='other';self.assertIsNone(ttm(rec,'net_income','USD',NOW))
        self.assertIsNone(ttm(rec,'eps_diluted','USD',NOW))

    def test_cash_does_not_pair_different_periods(self):
        record=copy.deepcopy(self.records['DUG.AX']);record['metrics']['capex'][-1]['accession']='unrelated'
        self.assertIsNone(matched_cash(record,'USD',NOW)['simple_fcf'])

    def test_volatility_aware_timing_allows_more_than_three_percent(self):
        row={'price':108,'trading_lows':{'low_5d':100,'previous_5d_low':100}}
        quote={'history':[100,115]*15}
        self.assertTrue(recovery_context(row,quote)['pre_recovery'])
        self.assertFalse(recovery_context(row,{})['pre_recovery'])

    def test_captcha_never_counts_as_a_financial_statement(self):
        with self.assertRaises(ValueError):inspect_document(b'<html>Please verify you are human</html>','https://issuer.example/a')

    def test_three_sections_are_candidates_not_approved_numbers(self):
        r=inspect_document(b'<html>Consolidated income statement. Consolidated balance sheet. Consolidated statement of cash flows.</html>','https://issuer.example/a')
        self.assertTrue(r['all_three_sections_detected'])
        self.assertFalse(r['financial_table_values_reviewed'])
        self.assertFalse(r['counts_toward_supported_valuation_coverage'])

    def test_all_200_baseline_and_priority_rules_survive(self):
        import shutil
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            from championship_90 import write
            write(root/'settings/dynamic_baseline_92.json',self.fixture['baseline'])
            write(root/'settings/dynamic_earnings_92.json',self.policy)
            write(root/'settings/primary_adapters_90.json',self.adapters)
            write(root/'reports/dynamic_guidance_92.json',{'companies':self.guidance})
            write(root/'reports/valuation_90_latest.json',self.fixture['historical_report'])
            with patch('dynamic_earnings_92.load_periods',return_value=copy.deepcopy(self.records)):
                result=build(root,now=NOW)
            coverage=verify(result)
            self.assertEqual(coverage['baseline_supported'],89)
            self.assertGreaterEqual(coverage['historical_supported_after'],92)
            self.assertFalse(coverage['lost_historical_supported'])
            self.assertEqual(result['broker_preferences']['trial_budget'],1000)
            self.assertEqual(result['broker_preferences']['stocks'],'Webull')
            self.assertEqual(result['broker_preferences']['crypto'],'Kraken')
            self.assertNotEqual(result['validation_cases']['HPE']['historical']['scenarios'],result['validation_cases']['HPE']['forward']['scenarios'])
            self.assertEqual(result['validation_cases']['HPE']['priority_entry']['threshold'],40)
            self.assertEqual(result['validation_cases']['SKS.AX']['priority_entry']['threshold'],5)
            self.assertEqual(result['validation_cases']['DUG.AX']['priority_entry']['threshold'],1.5)

if __name__=='__main__':unittest.main()
