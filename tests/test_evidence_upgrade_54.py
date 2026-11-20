"""Offline proof tests: never contact live filings or brokers."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import Mock,patch
import evidence_upgrade_54 as e
import intelligence_layer_51 as intel
NOW=datetime(2026,11,21,tzinfo=timezone.utc)

class FakeResponse:
    def __init__(self,body=b'',status=200,mime='text/html'):
        self.body=body;self.status_code=status
        self.headers={'Content-Type':mime,'Content-Length':str(len(body))}
    def iter_content(self,chunk_size=32768):
        for i in range(0,len(self.body),chunk_size):yield self.body[i:i+chunk_size]
    def close(self):pass

def doc(text):
    return b'<!doctype html><html><body><article><h1>Investor release</h1><p>'+text.encode()+b'</p></article></body></html>'

RECORD={'ticker':'PENG','company':'Penguin Solutions','evidence_url':'https://ir.penguinsolutions.com/press.html','evidence_date':'2026-11-16'}
CLAIMS={'PENG':{'issuer_aliases':['Penguin Solutions'],'claims':[{'id':'m','required_terms':['Marvell','collaborat','Penguin Solutions']}]}}

class SourceTests(unittest.TestCase):
    def test_official_html_claim_verified_as_issuer_report_only(self):
        ss=Mock();ss.get.return_value=FakeResponse(doc('16 November 2026. Penguin Solutions announces collaboration with Marvell for technology. ' * 5))
        o=e.check_primary_content(RECORD,CLAIMS,ss,allow_network=True,now=NOW)
        self.assertTrue(o['claim_verified']);self.assertTrue(o['document_read'])
        self.assertEqual(o['issuer_claims_supported_in_source'][0]['page'],1)
        self.assertIn('NOT_INDEPENDENTLY_AUDITED',o['issuer_claims_supported_in_source'][0]['verification_level'])
        self.assertEqual(len(o['sha256']),64)
    def test_claim_without_disclosure_date_is_not_verified(self):
        ss=Mock();ss.get.return_value=FakeResponse(doc('Penguin Solutions and Marvell collaborate on equipment. '*5))
        out=e.check_primary_content(RECORD,CLAIMS,ss,allow_network=True,now=NOW)
        self.assertTrue(out['issuer_claims_found_in_text'])
        self.assertFalse(out['claim_verified'])
        self.assertIn('ISSUER_DISCLOSURE_DATE_NOT_CONFIRMED_IN_CONTENT',out['evidence_flags'])
    def test_no_matching_claim_stays_false(self):
        ss=Mock();ss.get.return_value=FakeResponse(doc('Penguin Solutions reports equipment deliveries. '*6))
        o=e.check_primary_content(RECORD,CLAIMS,ss,allow_network=True,now=NOW)
        self.assertTrue(o['issuer_in_document']);self.assertFalse(o['claim_verified'])
        self.assertIn('NO_DATED_CLAIM_SUPPORT_CONFIRMED',o['evidence_flags'])
    def test_no_issuer_stays_false(self):
        ss=Mock();ss.get.return_value=FakeResponse(doc('Marvell collaborates with a different entity. '*8))
        o=e.check_primary_content(RECORD,CLAIMS,ss,allow_network=True,now=NOW)
        self.assertFalse(o['issuer_in_document']);self.assertFalse(o['claim_verified'])
    def test_url_slug_cannot_verify_claim(self):
        ss=Mock();ss.get.return_value=FakeResponse(doc('Penguin Solutions announces a financial statement. '*5))
        r={**RECORD,'evidence_url':'https://ir.penguinsolutions.com/marvell-collaboration'}
        o=e.check_primary_content(r,CLAIMS,ss,allow_network=True,now=NOW)
        self.assertFalse(o['claim_verified'])
    def test_untrusted_source_not_fetched(self):
        ss=Mock()
        o=e.check_primary_content({**RECORD,'evidence_url':'https://evil.example/press.html'},CLAIMS,ss,allow_network=True,now=NOW)
        self.assertFalse(o['claim_verified']);ss.get.assert_not_called()
    def test_source_redirect_blocked(self):
        ss=Mock();ss.get.return_value=FakeResponse(status=302)
        o=e.check_primary_content(RECORD,CLAIMS,ss,allow_network=True,now=NOW)
        self.assertFalse(o['claim_verified']);self.assertIn('DOCUMENT_HTTP_302',o['evidence_flags'])
    def test_no_substantive_fetch_offline(self):
        o=e.check_primary_content(RECORD,CLAIMS,None,allow_network=False,now=NOW)
        self.assertFalse(o['document_read']);self.assertFalse(o['claim_verified'])
    def test_non_html_or_pdf_rejected(self):
        ss=Mock();ss.get.return_value=FakeResponse(b'\x00'*300,mime='application/octet-stream')
        o=e.check_primary_content(RECORD,CLAIMS,ss,allow_network=True,now=NOW)
        self.assertEqual(o['extraction_status'],'UNSUPPORTED_CONTENT_TYPE')
    def test_pdf_extraction_from_static_pdf_fixture(self):
        # Base64 fixture generated before packaging; CI needs only pypdf.
        import base64
        data=base64.b64decode('JVBERi0xLjMKJZOMi54gUmVwb3J0TGFiIEdlbmVyYXRlZCBQREYgZG9jdW1lbnQgKG9wZW5zb3VyY2UpCjEgMCBvYmoKPDwKL0YxIDIgMCBSCj4+CmVuZG9iagoyIDAgb2JqCjw8Ci9CYXNlRm9udCAvSGVsdmV0aWNhIC9FbmNvZGluZyAvV2luQW5zaUVuY29kaW5nIC9OYW1lIC9GMSAvU3VidHlwZSAvVHlwZTEgL1R5cGUgL0ZvbnQKPj4KZW5kb2JqCjMgMCBvYmoKPDwKL0NvbnRlbnRzIDcgMCBSIC9NZWRpYUJveCBbIDAgMCA2MTIgNzkyIF0gL1BhcmVudCA2IDAgUiAvUmVzb3VyY2VzIDw8Ci9Gb250IDEgMCBSIC9Qcm9jU2V0IFsgL1BERiAvVGV4dCAvSW1hZ2VCIC9JbWFnZUMgL0ltYWdlSSBdCj4+IC9Sb3RhdGUgMCAvVHJhbnMgPDwKCj4+IAogIC9UeXBlIC9QYWdlCj4+CmVuZG9iago0IDAgb2JqCjw8Ci9QYWdlTW9kZSAvVXNlTm9uZSAvUGFnZXMgNiAwIFIgL1R5cGUgL0NhdGFsb2cKPj4KZW5kb2JqCjUgMCBvYmoKPDwKL0F1dGhvciAoYW5vbnltb3VzKSAvQ3JlYXRpb25EYXRlIChEOjIwMjYxMTIwMjIwNjAzKzAwJzAwJykgL0NyZWF0b3IgKGFub255bW91cykgL0tleXdvcmRzICgpIC9Nb2REYXRlIChEOjIwMjYxMTIwMjIwNjAzKzAwJzAwJykgL1Byb2R1Y2VyIChSZXBvcnRMYWIgUERGIExpYnJhcnkgLSBcKG9wZW5zb3VyY2VcKSkgCiAgL1N1YmplY3QgKHVuc3BlY2lmaWVkKSAvVGl0bGUgKHVudGl0bGVkKSAvVHJhcHBlZCAvRmFsc2UKPj4KZW5kb2JqCjYgMCBvYmoKPDwKL0NvdW50IDEgL0tpZHMgWyAzIDAgUiBdIC9UeXBlIC9QYWdlcwo+PgplbmRvYmoKNyAwIG9iago8PAovRmlsdGVyIFsgL0FTQ0lJODVEZWNvZGUgL0ZsYXRlRGVjb2RlIF0gL0xlbmd0aCAyMDIKPj4Kc3RyZWFtCkdhclcxWW1TPyUoa2hXSWBKcy5aKWk4WVFGQWBbcCRjTW5CT249XnE6S2ktbVVHdDZTXyR0Vi9HNyUnLHFLVVRvLnRkWGU1cVFJczpxRzQzPkhDUCFFcVEhZyMmVywxb1UsISVZTHRYal88OWtcJFM2QT9nbFw2O2hWMXRicDBEJ0psJVlhZyIqbjZMQEk+aFU1P3RvIkUiPWM6Qi4+YihUQWchSydnKlpIRU0+ODNVWjZuTktvIlM0TVUkUERWNHI4OmwyIVVnfj5lbmRzdHJlYW0KZW5kb2JqCnhyZWYKMCA4CjAwMDAwMDAwMDAgNjU1MzUgZiAKMDAwMDAwMDA2MSAwMDAwMCBuIAowMDAwMDAwMDkyIDAwMDAwIG4gCjAwMDAwMDAxOTkgMDAwMDAgbiAKMDAwMDAwMDM5MiAwMDAwMCBuIAowMDAwMDAwNDYwIDAwMDAwIG4gCjAwMDAwMDA3MjEgMDAwMDAgbiAKMDAwMDAwMDc4MCAwMDAwMCBuIAp0cmFpbGVyCjw8Ci9JRCAKWzxkMDQ4NGQ3YTYxYzJkMTAyNjY4OTQ5MGVmZjVkMWM1Mj48ZDA0ODRkN2E2MWMyZDEwMjY2ODk0OTBlZmY1ZDFjNTI+XQolIFJlcG9ydExhYiBnZW5lcmF0ZWQgUERGIGRvY3VtZW50IC0tIGRpZ2VzdCAob3BlbnNvdXJjZSkKCi9JbmZvIDUgMCBSCi9Sb290IDQgMCBSCi9TaXplIDgKPj4Kc3RhcnR4cmVmCjEwNzIKJSVFT0YK')
        pages,reason=e.source_pages(data,'application/pdf')
        self.assertEqual(reason,'PDF_TEXT_EXTRACTED')
        self.assertEqual(len(pages),1)
        self.assertIn('Penguin Solutions',pages[0][1])
    def test_new_sec_filer_without_claim_rule_identified_but_not_promoted(self):
        ss=Mock();ss.get.return_value=FakeResponse(doc('Some Registered Corporation reports financial results. '*6))
        rec={'ticker':'ZZ','company':'Some Registered Corporation',
             'evidence_url':'https://www.sec.gov/Archives/edgar/data/1/a.htm'}
        o=e.check_primary_content(rec,{},ss,allow_network=True,now=NOW)
        self.assertTrue(o['issuer_in_document']);self.assertFalse(o['claim_verified'])
    def test_queue_counts_substantive_claims_not_links(self):
        q={'records':[{'ticker':'PENG','company':'Penguin Solutions','source_url':RECORD['evidence_url'],
                        'status':'PENDING_EVIDENCE','gaps':[], 'evidence_date':'2026-11-16'}]}
        ss=Mock();ss.get.return_value=FakeResponse(doc('16 November 2026. Penguin Solutions collaborated with Marvell for equipment. '*4))
        out=e.enrich_queue(q,CLAIMS,ss,NOW,True)
        self.assertEqual(out['claim_verified_count'],1)
        self.assertFalse(out['orders_enabled'])
        self.assertTrue(out['records'][0]['substantive_evidence']['document_read'])

class FinancialTests(unittest.TestCase):
    def test_explicit_sec_units_and_period_used(self):
        x={'facts':{'dei':{'EntityCommonStockSharesOutstanding':{'units':{'shares':[
            {'form':'10-Q','filed':'2026-11-16','end':'2026-09-30','val':100_000_000,'accn':'a'}]}}},
            'us-gaap':{'NetCashProvidedByUsedInOperatingActivities':{'units':{'USD':[
                {'form':'10-Q','filed':'2026-11-16','start':'2026-07-01','end':'2026-09-30','val':250_000_000,'accn':'a'}]}},
                'PaymentsToAcquirePropertyPlantAndEquipment':{'units':{'USD':[
                {'form':'10-Q','filed':'2026-11-16','start':'2026-07-01','end':'2026-09-30','val':50_000_000,'accn':'a'}]}}}},
            'cik':123,'entityName':'Test Corporation'}
        out=e.primary_sec_financials('TEST',x,NOW)
        self.assertEqual(out['shares_outstanding']['value'],100_000_000)
        self.assertEqual(out['free_cash_flow_same_period']['value_usd'],200_000_000)
        model={'shares_input':100_000_000,'fcf_input':200_000_000,'fundamental_currency':'USD',
               'fiscal_as_of':'2026-09-30','model_type':'FCF_TO_EQUITY'}
        check=e.verify_model_economics(model,{'status':'ok','facts':out,'source_url':'https://data.sec.gov/facts'})
        self.assertTrue(check['model_primary_verified'])
        self.assertEqual(check['dilution_reference_ratio'],1.0)
    def test_mismatched_share_count_fails(self):
        x={'shares_outstanding':{'value':200},'free_cash_flow_same_period':{'value_usd':100,'period_end':'2026-09-30'}}
        o=e.verify_model_economics({'shares_input':100,'fcf_input':100,'fiscal_as_of':'2026-09-30','fundamental_currency':'USD'},
                                   {'status':'ok','facts':x})
        self.assertFalse(o['model_primary_verified']);self.assertIn('PRIMARY_VS_VENDOR_SHARES_DISAGREE_OVER_10PCT',o['flags'])
    def test_wrong_fcf_period_fails(self):
        x={'shares_outstanding':{'value':100},'free_cash_flow_same_period':{'value_usd':100,'period_end':'2026-06-30'}}
        o=e.verify_model_economics({'shares_input':100,'fcf_input':100,'fiscal_as_of':'2026-09-30','fundamental_currency':'USD'},
                                   {'status':'ok','facts':x})
        self.assertFalse(o['model_primary_verified']);self.assertIn('MODEL_FCF_AND_SEC_FILING_PERIOD_NOT_IDENTICAL',o['flags'])
    def test_unverified_higher_upside_not_ranking_eligible(self):
        scan={'stocks':[{'ticker':'AAA','last_daily_close':100,'currency':'USD'}]}
        valuation={'stocks':[{'ticker':'AAA','model_status':'INDICATIVE','bear_value':20,'base_value':1000,'bull_value':2000}]}
        out=e.asymmetry_report(scan,valuation,{},NOW)
        self.assertEqual(out['evidence_qualified_count'],0)
        self.assertEqual(out['unverified_model_count'],1)
        self.assertFalse(out['orders_enabled'])
    def test_dilution_stress_mathematics(self):
        scan={'stocks':[{'ticker':'AAA','last_daily_close':100,'currency':'USD'}]}
        model={'ticker':'AAA','model_status':'INDICATIVE','bear_value':80,'base_value':130,'bull_value':200,
               'shares_input':100,'fcf_input':200,'fiscal_as_of':'2026-09-30','fundamental_currency':'USD'}
        filing={'companies':{'AAA':{'status':'ok','facts':{'shares_outstanding':{'value':100},
                'free_cash_flow_same_period':{'value_usd':200,'period_end':'2026-09-30'}}}}}
        result=e.asymmetry_report(scan,{'stocks':[model]},filing,NOW)
        self.assertEqual(result['evidence_qualified_count'],1)
        row=result['evidence_qualified_top10'][0]
        self.assertAlmostEqual(row['dilution_adjusted_values']['bear'],80/1.15,delta=.01)
        self.assertAlmostEqual(row['dilution_adjusted_values']['base'],130/1.05,delta=.01)
        self.assertFalse(row['verified_buy_signal'])
    def test_invalid_dilution_rejected(self):
        with self.assertRaises(ValueError):e.asymmetry_report({}, {}, {}, NOW,stress_bear=-.1)
    def test_sec_not_contacted_offline(self):
        out=e.fetch_sec_financials([],None,NOW,user_agent='',allow_network=False)
        self.assertFalse(out['orders_enabled']);self.assertIn('NOT_FETCHED',out['status'])

class OffsetTests(unittest.TestCase):
    def test_dual_offset_rates_and_confirmation(self):
        cfg=json.loads((Path(__file__).resolve().parents[1]/'settings/intelligence_51.json').read_text())
        out=intel.after_tax_comparison({'ranked_top_10':[]},cfg,{},NOW)
        rates={x['id']:x for x in out['offset_rate_scenarios']}
        self.assertEqual(rates['illustrative_5_8']['offset_savings_aud'],62.83)
        self.assertEqual(rates['unconfirmed_6_01']['offset_savings_aud'],65.11)
        self.assertEqual(rates['unconfirmed_6_01']['confirmation'],'UNCONFIRMED_NOT_LIVE')
        self.assertEqual(out['fees_aud']['buy'],3)
        self.assertFalse(out['orders_enabled'])
    def test_after_tax_both_rate_benchmarks(self):
        cfg=json.loads((Path(__file__).resolve().parents[1]/'settings/intelligence_51.json').read_text())
        t={'ranked_top_10':[{'rank':1,'ticker':'X','currency':'AUD','last_daily_close':100,
               'bear_value':90,'base_value':140,'bull_value':180}]}
        out=intel.after_tax_comparison(t,cfg,{},NOW)
        checks=out['ranked_research_scenarios'][0]['hypothetical_outcomes']['base']['income_158k']['offset_comparisons_by_rate']
        self.assertEqual(len(checks),2)
        self.assertGreater(checks['illustrative_5_8']['net_profit_minus_offset_aud'],checks['unconfirmed_6_01']['net_profit_minus_offset_aud'])

if __name__=='__main__':unittest.main()
