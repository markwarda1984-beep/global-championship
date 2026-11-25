import copy,unittest
from datetime import datetime,timezone
from reviewed_bank_96 import parse,assemble,verified
from evidence_recovery_91 import digest
from refresh_fx_91 import required_pairs
NOW=datetime(2026,11,25,tzinfo=timezone.utc)
META={'url':'https://www.sec.gov/Archives/edgar/data/1103838/1/annual.htm','filed':'2026-07-20','accession':'test'}
def fixture(scale='Rupees in million',year=2026):
 return f'''ICICI Bank Limited fiscal year ended March 31, {year}
 number of outstanding Equity Shares of ICICI Bank Limited as of March 31, {year} was 7,160,112,569
 At June 30, {year}, total 7,173,615,744 equity shares were outstanding
 American Depositary Shares, each representing two Equity Shares of ICICI Bank Limited
 <table><tr><td>{scale} Year ended March 31, Note {year} {year-1} {year-2}</td></tr>
 <tr><td>Net income as per U.S. GAAP attributable to ICICI Bank stockholders</td><td>560,374.7</td><td>513,543.0</td><td>613,763.5</td></tr></table>
 <table><tr><td>{scale} At March 31, Note {year} {year-1}</td></tr>
 <tr><td>ICICI Bank stockholders’ equity as per U.S. GAAP</td><td>4,090,932.6</td><td>3,654,804.7</td></tr></table>'''
class BankEvidenceTests(unittest.TestCase):
 def test_owner_reconciliation_and_native_units(self):
  facts,basis=parse(fixture(),META)
  self.assertEqual(facts['net_income'][0]['value'],560374700000)
  self.assertEqual(facts['equity'][0]['value'],4090932600000)
  self.assertIsNone(facts['equity'][0]['start'])
  self.assertEqual(basis['facts']['ordinary_shares_per_receipt'],2)
  self.assertEqual(basis['facts']['ordinary_shares_outstanding'],7173615744)
  self.assertIn('June 30, 2026',facts['shares'][-1]['source_row'])
 def test_thousands_are_not_silently_treated_as_millions(self):
  with self.assertRaises(ValueError):parse(fixture('Rupees in thousand'),META)
 def test_no_substitution_of_group_income(self):
  with self.assertRaises(ValueError):parse(fixture().replace('Net income as per U.S. GAAP attributable to ICICI Bank stockholders','Net income as per U.S. GAAP'),META)
 def test_no_unverified_ads_ratio(self):
  with self.assertRaises(ValueError):parse(fixture().replace('representing two','representing three'),META)
 def test_issuer_identity_guard(self):
  with self.assertRaises(ValueError):parse(fixture(),{**META,'url':META['url'].replace('1103838','123')})
 def test_hash_and_real_locator_required(self):
  record,_=assemble([(fixture(),META)],NOW.isoformat());self.assertTrue(verified(record,NOW))
  record['annual_facts']['net_income'][0]['html_row_index']=None;record['evidence_hash_sha256']=digest(record['annual_facts']);self.assertFalse(verified(record,NOW))
 def test_fx_direction_includes_new_native_records(self):
  self.assertEqual(required_pairs({'IBN':{'annual_facts':{'equity':[{'unit':'INR'}]}}}),{'IBN':('INR','USD')})
if __name__=='__main__':unittest.main()
