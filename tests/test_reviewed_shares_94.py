"""Contract fixtures exercise boundaries; no fixture numbers feed production models."""
import copy,hashlib,unittest
from datetime import datetime,timezone
from reviewed_shares_94 import reviewed_counts,apply_overlay
from background_research_93 import choose_batch
from evidence_recovery_91 import digest
NOW=datetime(2026,11,24,tzinfo=timezone.utc)
RIGHTS='Class A and Class B share equally in dividends and liquidation.'
POLICY={'cik':123,'members':['us-gaap:CommonClassAMember','us-gaap:CommonClassBMember'],'review_status':'PRIMARY_DOCUMENT_FIELDS_RECONCILED','reviewed_as_of':'2026-02-01','economic_rights_excerpt':RIGHTS,'rights_source_url':'https://www.sec.gov/Archives/edgar/data/123/1/rights.htm','rights_document_sha256':hashlib.sha256(RIGHTS.encode()).hexdigest()}
META={'url':'https://www.sec.gov/Archives/edgar/data/123/2/quarter.htm','accession':'0000000123-26-000002','filed':'2026-10-01','form':'10-Q'}
def document(cik='123',extra='',b='20',concept='dei:EntityCommonStockSharesOutstanding'):
 return ''.join(f'<xbrli:context id="{c}"><xbrli:entity><xbrli:identifier>{cik}</xbrli:identifier><xbrli:segment><xbrldi:explicitMember>us-gaap:CommonClass{c}Member</xbrldi:explicitMember></xbrli:segment></xbrli:entity><xbrli:period><xbrli:instant>2026-09-25</xbrli:instant></xbrli:period></xbrli:context><ix:nonfraction name="{concept}" contextref="{c}">{v}</ix:nonfraction>' for c,v in [('A','100'),('B',b)])+extra
class ReviewedClassesTests(unittest.TestCase):
 def parse(self,html=None,policy=None,rights=RIGHTS):return reviewed_counts(html or document(),'TEST',policy or POLICY,META,NOW,rights)
 def test_verified_external_rights_allow_complete_quarter_cover(self):
  rows=self.parse();self.assertEqual(rows[0]['value'],120);self.assertEqual(rows[0]['rights_document_sha256'],POLICY['rights_document_sha256'])
 def test_changed_rights_need_new_review(self):self.assertEqual(self.parse(rights=RIGHTS+' Changed.'),[])
 def test_mismatched_issuer_rejected(self):self.assertEqual(self.parse(document(cik='456')),[])
 def test_stale_review_rejected(self):self.assertEqual(self.parse(policy={**POLICY,'reviewed_as_of':'2024-01-01'}),[])
 def test_unknown_third_economic_class_blocks_total(self):
  extra=document().replace('CommonClassAMember','CommonClassCMember').replace('id="A"','id="C"').replace('contextref="A"','contextref="C"')
  self.assertEqual(self.parse(document(extra=extra)),[])
 def test_missing_class_never_defaulted(self):self.assertEqual(self.parse(document(b='—')),[])
 def test_note_table_counts_not_treated_as_cover_counts(self):self.assertEqual(self.parse(document(concept='us-gaap:CommonStockSharesOutstanding')),[])
 def test_tampered_overlay_cannot_change_denominator(self):
  counts=self.parse();report={'companies':{'TEST':{'counts':counts,'counts_sha256':digest(counts)}}};company={'ticker':'TEST','cik':123,'annual_facts':{'shares':[]}}
  self.assertEqual(apply_overlay(company,report,{'companies':{'TEST':POLICY}},NOW)['latest_share_count']['value'],120)
  report['companies']['TEST']['counts'][0]['value']=1
  self.assertEqual(apply_overlay(company,report,{'companies':{'TEST':POLICY}},NOW),company)
 def test_rehashed_partial_class_overlay_rejected(self):
  counts=self.parse();counts[0]['class_components'].pop(POLICY['members'][1]);counts[0]['value']=100
  report={'companies':{'TEST':{'counts':counts,'counts_sha256':digest(counts)}}};c={'ticker':'TEST','cik':123,'annual_facts':{'shares':[]}}
  self.assertEqual(apply_overlay(c,report,{'companies':{'TEST':POLICY}},NOW),c)
 def test_recovered_issuers_remain_in_worker_refresh_rotation(self):
  row={'ticker':'NKE','scenarios':{'base':1}}
  self.assertEqual(choose_batch([row],{},NOW,20,['NKE']),[row])
