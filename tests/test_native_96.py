import hashlib,json,unittest
from datetime import datetime,timezone,date
from reviewed_native_96 import extract,RULES,dynamic_record
from dynamic_earnings_92 import matched_cash
from evidence_recovery_91 import digest
from verify_outputs_95 import guidance_expectation
NOW=datetime(2026,11,25,tzinfo=timezone.utc)
META={'url':'https://www.sec.gov/Archives/edgar/data/1046179/1/annual.htm','accession':'a','filed':'2026-04-01','form':'20-F'}
def html(currency='TWD',missing=None,quarter=False,dimensions='',extra=''):
 start='2025-10-01' if quarter else '2025-01-01';tags=[RULES['TSM']['income'],RULES['TSM']['ocf'],*RULES['TSM']['capex_components']]
 context=f'<xbrli:context id="annual"><xbrli:entity><xbrli:identifier>1046179</xbrli:identifier>{dimensions}</xbrli:entity><xbrli:period><xbrli:startDate>{start}</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period></xbrli:context>'
 unit=f'<xbrli:unit id="currency"><xbrli:measure>iso4217:{currency}</xbrli:measure></xbrli:unit>'
 facts=''.join(f'<ix:nonfraction name="{tag}" contextref="annual" unitref="currency" scale="6">{v}</ix:nonfraction>' for tag,v in zip(tags,[100,200,50,10,5,3]) if tag!=missing)
 return context+unit+facts+extra
class NativeFinancialTests(unittest.TestCase):
 def extract(self,doc=None):return extract(doc or html(),'TSM',META,NOW)
 def test_native_scale_and_complete_disjoint_outflows(self):
  r=self.extract();self.assertEqual(r['net_income'][0]['value'],100000000);self.assertEqual(r['capex'][0]['value'],68000000);self.assertEqual(len(r['capex'][0]['components']),4)
 def test_convenience_usd_not_a_native_statement(self):self.assertFalse(any(self.extract(html('USD')).values()))
 def test_missing_cost_not_filled_with_zero(self):self.assertFalse(any(self.extract(html(missing=RULES['TSM']['capex_components'][-1])).values()))
 def test_quarter_does_not_enter_annual_history(self):self.assertFalse(any(self.extract(html(quarter=True)).values()))
 def test_subsidiary_context_cannot_be_consolidated(self):
  dim='<xbrldi:explicitMember>issuer:SubsidiaryMember</xbrldi:explicitMember>';self.assertFalse(any(self.extract(html(dimensions=dim)).values()))
 def test_conflicting_same_unit_fact_rejects_period(self):
  extra=f'<ix:nonfraction name="{RULES["TSM"]["income"]}" contextref="annual" unitref="currency" scale="6">101</ix:nonfraction>';self.assertFalse(any(self.extract(html(extra=extra)).values()))
 def test_owner_cash_components_not_double_counted(self):
  facts=self.extract();rec=dynamic_record('TSM',{'annual_facts':facts},NOW.isoformat());cash=matched_cash(rec,'TWD',NOW);self.assertEqual(cash['simple_fcf'],150000000);self.assertEqual(cash['owner_cash_flow'],132000000)
 def test_aggregate_financing_interest_does_not_imply_missing_components_zero(self):
  facts=self.extract();rec=dynamic_record('TSM',{'annual_facts':facts},NOW.isoformat());rec['metrics']['lease_principal']=[];self.assertIsNone(matched_cash(rec,'TWD',NOW)['owner_cash_flow'])
 def test_wrong_issuer_url_rejected(self):
  meta={**META,'url':'https://www.sec.gov/Archives/edgar/data/1/a.htm'};self.assertEqual(extract(html(),'TSM',meta,NOW),{})
class GuidanceLifecycleTests(unittest.TestCase):
 def test_expired_guidance_is_a_valid_missing_output(self):
  seed={'published_at':'2026-09-10','facts':{'target_period_end':'2026-11-27'}};self.assertFalse(guidance_expectation(seed,None,date(2026,11,28))[1])
 def test_new_issuer_guidance_is_not_compared_to_frozen_old_eps(self):
  seed={'published_at':'2026-11-24','facts':{'target_period_end':'2027-01-29','low':28.24}};fresh={'published_at':'2026-12-01','facts':{'target_period_end':'2027-01-29','low':30.24}};expected,active=guidance_expectation(seed,fresh,date(2026,12,2));self.assertTrue(active);self.assertEqual(expected['facts']['low'],30.24)
 def test_old_worker_guidance_cannot_hide_newer_reviewed_seed(self):
  seed={'published_at':'2026-11-24','facts':{'target_period_end':'2027-01-29'}};old={'published_at':'2026-11-01','facts':{'target_period_end':'2026-12-31'}};self.assertEqual(guidance_expectation(seed,old,date(2026,11,25))[0],seed)
