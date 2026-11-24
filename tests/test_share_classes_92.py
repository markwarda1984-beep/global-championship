import unittest
from datetime import datetime,timezone
from share_classes_92 import equal_class_counts
from refresh_fx_91 import required_pairs
NOW=datetime(2026,11,24,tzinfo=timezone.utc)
EXCERPT='Both classes have identical economic rights.'
def document(extra='',b='20'):
 return EXCERPT+''.join(f'<xbrli:context id="{member}"><xbrli:entity><xbrli:segment><xbrldi:explicitMember>us-gaap:CommonClass{member}Member</xbrldi:explicitMember>{extra}</xbrli:segment></xbrli:entity><xbrli:period><xbrli:instant>2026-09-30</xbrli:instant></xbrli:period></xbrli:context><ix:nonfraction name="us-gaap:CommonStockSharesOutstanding" contextref="{member}" scale="3">{value}</ix:nonfraction>' for member,value in [('A','100'),('B',b)])
class ShareReconciliationTests(unittest.TestCase):
 def test_complete_reviewed_equal_classes_scale_and_sum(self):
  r=equal_class_counts(document(),EXCERPT,NOW);self.assertEqual(r[0]['value'],120000);self.assertEqual(len(r[0]['class_components']),2)
 def test_no_equality_proof_no_aggregation(self):
  self.assertEqual(equal_class_counts(document(),'Different rights.',NOW),[])
 def test_missing_class_no_partial_denominator(self):
  self.assertEqual(equal_class_counts(document(b='—'),EXCERPT,NOW),[])
 def test_subsidiary_dimension_not_double_counted(self):
  self.assertEqual(equal_class_counts(document('<xbrldi:explicitMember>issuer:SubsidiaryMember</xbrldi:explicitMember>'),EXCERPT,NOW),[])
 def test_conflicting_values_same_class_blocked(self):
  s=document()+'<ix:nonfraction name="us-gaap:CommonStockSharesOutstanding" contextref="A" scale="3">101</ix:nonfraction>'
  self.assertEqual(equal_class_counts(s,EXCERPT,NOW),[])
 def test_asx_direction_uses_listed_currency(self):
  self.assertEqual(required_pairs({'BHP.AX':{'financial_currency':'USD'},'SAP':{'financial_currency':'EUR'},'HPE':{'financial_currency':'USD'}}),{'BHP.AX':('USD','AUD'),'SAP':('EUR','USD')})

 def test_additional_common_class_blocks_incomplete_total(self):
  c='<xbrli:context id="C"><xbrldi:explicitMember>us-gaap:CommonClassCMember</xbrldi:explicitMember><xbrli:instant>2026-09-30</xbrli:instant></xbrli:context><ix:nonfraction name="dei:EntityCommonStockSharesOutstanding" contextref="C">10</ix:nonfraction>'
  self.assertEqual(equal_class_counts(document()+c,EXCERPT,NOW),[])
