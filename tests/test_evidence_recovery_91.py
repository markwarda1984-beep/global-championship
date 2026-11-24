import unittest
from datetime import datetime,timezone
from evidence_recovery_91 import recover_series
from recover_documents_91 import cover_ratio,cover_shares
from championship_60 import combine_periods
NOW=datetime(2026,11,24,tzinfo=timezone.utc)
def fact(value,end='2025-12-31',start='2025-01-01',accession='issuer-annual',form='10-K'):
 out={'val':value,'end':end,'accn':accession,'filed':'2026-02-01','form':form}
 if start:out['start']=start
 return out
class RecoveryTests(unittest.TestCase):
 def test_obsolete_tags_do_not_truncate_new_cashflow_or_revenue(self):
  facts={'us-gaap':{
   'RevenueFromContractWithCustomerExcludingAssessedTax':{'units':{'USD':[fact(10,'2020-12-31','2020-01-01')]}},
   'Revenues':{'units':{'USD':[fact(50)]}},'NetIncomeLoss':{'units':{'USD':[fact(8)]}},
   'NetCashProvidedByUsedInOperatingActivities':{'units':{'USD':[fact(20)]}},
   'PaymentsToAcquirePropertyPlantAndEquipment':{'units':{'USD':[fact(2,'2020-12-31','2020-01-01')]}},
   'PaymentsToAcquireProductiveAssets':{'units':{'USD':[fact(6)]}}}}
  out=recover_series('TEST',{'cik':1,'entityName':'Issuer','facts':facts},NOW,1)
  periods=combine_periods(out);self.assertEqual(periods[-1]['revenue'],50);self.assertEqual(periods[-1]['fcf'],14)
 def test_same_accession_and_currency_required(self):
  facts={'us-gaap':{'NetIncomeLoss':{'units':{'USD':[fact(8)]}},'NetCashProvidedByUsedInOperatingActivities':{'units':{'USD':[fact(20)]}},'PaymentsToAcquireProductiveAssets':{'units':{'USD':[fact(6,accession='different')]}}}}
  out=recover_series('TEST',{'cik':1,'entityName':'Issuer','facts':facts},NOW,1)
  self.assertTrue(all(p['fcf'] is None for p in combine_periods(out)))
 def test_ifrs_native_currency_and_annual_equity(self):
  facts={'ifrs-full':{'ProfitLoss':{'units':{'EUR':[fact(8,form='20-F')]}},'CashFlowsFromUsedInOperatingActivities':{'units':{'EUR':[fact(20,form='20-F')]}},'PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities':{'units':{'EUR':[fact(6,form='20-F')]}},'Equity':{'units':{'EUR':[fact(90,start=None,form='20-F'),fact(91,end='2025-09-30',start=None,form='10-Q')]}}}}
  out=recover_series('TEST',{'cik':1,'entityName':'Issuer','facts':facts},NOW,1)
  self.assertEqual(out['financial_currency'],'EUR');self.assertEqual(combine_periods(out)[-1]['fcf'],14)
  self.assertEqual(len(out['annual_facts']['equity']),1)
 def test_no_future_or_negative_capex_invention(self):
  facts={'us-gaap':{'NetIncomeLoss':{'units':{'USD':[fact(8)]}},'NetCashProvidedByUsedInOperatingActivities':{'units':{'USD':[fact(20)]}},'PaymentsToAcquireProductiveAssets':{'units':{'USD':[fact(-6)]}}}}
  out=recover_series('TEST',{'cik':1,'entityName':'Issuer','facts':facts},NOW,1)
  self.assertFalse(out['annual_facts']['capex'])
 def test_ratio_requires_explicit_ticker_security_row(self):
  html='<table><tr><th>Title of each class</th><th>Trading symbol</th></tr><tr><td>American Depositary Shares, each representing five ordinary shares</td><td>TEST</td></tr></table>'
  self.assertEqual(cover_ratio(html,'TEST')[0],5)
  self.assertIsNone(cover_ratio(html,'OTHER')[0])
  self.assertIsNone(cover_ratio('<p>TEST price is 5 times ordinary stock.</p>','TEST')[0])
 def test_ordinary_listing_one_to_one_and_conflicting_ratios(self):
  self.assertEqual(cover_ratio('<table><tr><th>Title of each class</th><th>Trading symbol</th></tr><tr><td>Common Stock, $0.001 par value</td><td>TEST</td></tr></table>','TEST')[0],1)
  html='<table><tr><th>Title of each class</th><th>Trading symbol</th></tr><tr><td>American Depositary Shares each representing two ordinary shares TEST</td></tr><tr><td>American Depositary Shares each representing five ordinary shares TEST</td></tr></table>'
  self.assertIsNone(cover_ratio(html,'TEST')[0])
 def test_inline_shares_require_instant_and_no_classes(self):
  html='<xbrli:context id="a"><xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period></xbrli:context><ix:nonfraction name="dei:EntityCommonStockSharesOutstanding" contextref="a" scale="3">1,234</ix:nonfraction>'
  self.assertEqual(cover_shares(html)[0]['value'],1234000)
  html=html.replace('<xbrli:period>','<xbrldi:explicitmember>ClassA</xbrldi:explicitmember><xbrli:period>')
  self.assertEqual(cover_shares(html),[])

 def test_underlying_security_registration_does_not_imply_receipt_one_to_one(self):
  html='<table><tr><th>Title of each class</th><th>Trading symbol</th></tr><tr><td>Common shares*</td><td>TEST</td></tr></table><p>* American Depositary Shares each representing five (5) common shares.</p>'
  self.assertEqual(cover_ratio(html,'TEST')[0],5)
  self.assertIsNone(cover_ratio(html.replace('each representing five (5) common shares','with terms described elsewhere'),'TEST')[0])
 def test_pdf_evidence_mutation_is_rejected(self):
  import hashlib,json
  from championship_90 import verified_pdf_record
  f={'net_income':[{'value':10,'end':'2026-06-30','source_url':'https://issuer.example/annual.pdf','source_document_sha256':'a'*64,'pdf_page':3}]}
  r={'status':'ISSUER_ANNUAL_REPORT_FIELDS_RECONCILED','review_status':'PRIMARY_DOCUMENT_FIELDS_RECONCILED','annual_facts':f,'evidence_hash_sha256':hashlib.sha256(json.dumps(f,sort_keys=True).encode()).hexdigest()}
  self.assertTrue(verified_pdf_record(r,NOW))
  f['net_income'][0]['value']=20
  self.assertFalse(verified_pdf_record(r,NOW))
