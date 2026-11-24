import unittest,copy
from evidence_recovery_91 import digest
from reviewed_cashflow_92 import apply_reviewed_overlay
class ReviewedCashflowTests(unittest.TestCase):
 def fixture(self):
  base={'ticker':'LLY','financial_currency':'USD','annual_facts':{'operating_cash_flow':[],'capex':[]}}
  common={'unit':'USD','start':'2025-01-01','end':'2025-12-31','accession':'annual','filed':'2026-02-01','source_url':'https://issuer.example/annual','source_document_sha256':'a'*64}
  rows=[{'operating_cash_flow':{**common,'value':15},'capex':{**common,'value':5,'component_values':{'us-gaap:PaymentsToAcquireOtherPropertyPlantAndEquipment':5}}}]
  return base,{'companies':[{'ticker':'LLY','review_status':'PRIMARY_DOCUMENT_FIELDS_RECONCILED','periods':rows,'periods_sha256':digest(rows)}]}
 def test_reviewed_rows_survive_refresh_without_changing_filing_dates(self):
  c,r=self.fixture();out=apply_reviewed_overlay(c,r);self.assertEqual(out['annual_facts']['capex'][0]['filed'],'2026-02-01')
 def test_tampered_rows_are_not_used(self):
  c,r=self.fixture();r['companies'][0]['periods'][0]['capex']['value']=99
  self.assertFalse(apply_reviewed_overlay(c,r)['annual_facts']['capex'])
 def test_component_omission_not_assumed_zero(self):
  c,r=self.fixture();entry=r['companies'][0];entry['periods'][0]['capex']['component_values']={};entry['periods_sha256']=digest(entry['periods'])
  self.assertFalse(apply_reviewed_overlay(c,r)['annual_facts']['capex'])
