"""Evidence/consensus safeguards: deterministic, zero network access, zero trades."""
import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock

import championship_60 as core
import forward_research_60 as fr

NOW=datetime(2026,11,21,0,0,tzinfo=timezone.utc)
GOOD_TEXT=("<html><body><h1>NVIDIA CORPORATION</h1><p>November 17, 2026</p>"
 "<p>NVIDIA's outlook for the fourth quarter of fiscal 2027, which includes an additional week, is as follows:</p>"
 "<p>Revenue is expected to be $130.0 billion, plus or minus 3%.</p></body></html>").encode()


class FakeFrame:
    def __init__(self,data):self.data=data
    def to_dict(self,kind):
        assert kind=='index'
        return self.data


class Response:
    status_code=200
    def __init__(self,payload=None,content=b'',status=200):
        self.data=payload;self.content=content;self.status_code=status
    def json(self):return self.data


class Session:
    def __init__(self,listed=None):
        self.headers={};self.requested=[];self.listed=listed or []
    def get(self,url,**kwargs):
        self.requested.append(url)
        if 'company_tickers_exchange' in url:
            return Response({'fields':['ticker','cik','exchange'],
                      'data':[[t,i+1,'NASDAQ'] for i,t in enumerate(self.listed)]})
        if 'q3fy27pr.htm' in url:return Response(content=GOOD_TEXT)
        cik=int(url.split('CIK')[-1].split('.')[0]);return Response({'cik':cik,'entityName':'Test Corporation','facts':{}})


def tree(root):
    with (root/'watchlist.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['ticker','name','sector']);w.writeheader()
        for i in range(200):
            t=['AAPL','MSFT','NVDA'][i] if i<3 else 'S'+str(i).zfill(3)
            w.writerow({'ticker':t,'name':t,'sector':'Technology'})
    (root/'reports').mkdir()
    (root/'reports/discovery_watchlist.json').write_text(json.dumps({
      'original_200_unchanged':True,'orders_enabled':False,
      'candidates':{'PENG':{'company':'Penguin Solutions','status':'PENDING_EVIDENCE','theme':'AI'}}}))


class StrictGuidance(TestCase):
    def test_extracts_actual_nvda_guidance_with_excerpt_and_hash(self):
        rec=fr.issuer_guidance_from_document('NVDA',fr.OFFICIAL_NVDA_URL,GOOD_TEXT,NOW)
        self.assertEqual(rec['status'],'ISSUER_REPORTED_GUIDANCE_CONFIRMED_IN_FILING_EXHIBIT')
        self.assertEqual(rec['reported_guidance']['revenue_usd_billions'],130.0)
        self.assertEqual(rec['reported_guidance']['management_plus_minus_pct'],3.0)
        self.assertEqual(rec['reported_guidance']['forecast_kind'],'MANAGEMENT_GUIDANCE_NOT_ANALYST_EPS_CONSENSUS')
        self.assertEqual(len(rec['evidence_sha256']),64)
        self.assertFalse(rec['orders_enabled'])
    def test_wrong_issuer_blocks(self):
        body=GOOD_TEXT.replace(b'NVIDIA CORPORATION',b'Other Corporation').replace(b"NVIDIA's outlook",b"Other Company's outlook")
        r=fr.issuer_guidance_from_document('NVDA',fr.OFFICIAL_NVDA_URL,body,NOW)
        self.assertIsNone(r['reported_guidance'])
    def test_missing_date_blocks(self):
        r=fr.issuer_guidance_from_document('NVDA',fr.OFFICIAL_NVDA_URL,GOOD_TEXT.replace(b'November 17, 2026',b'Last Friday'),NOW)
        self.assertEqual(r['status'],'ISSUER_OR_DISCLOSURE_DATE_NOT_CONFIRMED')
    def test_missing_period_blocks(self):
        r=fr.issuer_guidance_from_document('NVDA',fr.OFFICIAL_NVDA_URL,GOOD_TEXT.replace(b'fourth quarter of fiscal 2027',b'next quarter'),NOW)
        self.assertIsNone(r['reported_guidance'])
    def test_missing_value_blocks(self):
        r=fr.issuer_guidance_from_document('NVDA',fr.OFFICIAL_NVDA_URL,GOOD_TEXT.replace(b'$130.0 billion',b'$soon billion'),NOW)
        self.assertIsNone(r['reported_guidance'])
    def test_no_url_slug_evidence(self):
        r=fr.issuer_guidance_from_document('NVDA','https://example.org/nvda/130',GOOD_TEXT,NOW)
        self.assertFalse(r['reported_guidance'])
    def test_wrong_company_cannot_repurpose_nvda_guidance(self):
        r=fr.issuer_guidance_from_document('PENG',fr.OFFICIAL_NVDA_URL,GOOD_TEXT,NOW)
        self.assertIsNone(r['reported_guidance'])
    def test_offline_preserves_previous_and_never_fakes(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'reports').mkdir()
            session=Session()
            a=fr.fetch_guidance(root,NOW,session,offline=True)
            self.assertEqual(a['status'],'OFFLINE_PRESERVE_PREVIOUS');self.assertEqual(session.requested,[])
    def test_403_does_not_claim_issuer_guidance(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'reports').mkdir()
            ss=Session();ss.get=lambda *_args,**_kwargs:Response(status=403)
            with mock.patch.dict(os.environ,{'SEC_USER_AGENT':'Research Team research@example.org'}):
                x=fr.fetch_guidance(root,NOW,ss)
            self.assertEqual(x['status'],'ISSUER_SOURCE_HTTP_403')
            self.assertFalse(x['companies'])


class UnofficialConsensus(TestCase):
    def test_valid_eps_snapshot_is_explicitly_secondary(self):
        frame=FakeFrame({'0y':{'avg':5.2,'low':4.1,'high':6.4,'numberOfAnalysts':21},
                        '+1y':{'avg':6.9,'numberOfAnalysts':19},
                        'other':{'avg':999}})
        data=fr._estimate_periods(frame)
        self.assertEqual(set(data),{'0y','+1y'})
        self.assertFalse(data['0y']['period_identity_validated'])
        self.assertIn('SECONDARY',data['0y']['data_quality'])
    def test_no_fabricated_estimate_if_no_data(self):
        self.assertEqual(fr._estimate_periods(None),{})
        self.assertEqual(fr._estimate_periods(FakeFrame({'0y':{'avg':float('nan')}})),{})
    def test_invalid_range_not_accepted(self):
        self.assertFalse(fr._estimate_periods(FakeFrame({'0y':{'avg':4,'low':5,'high':6}})))
    def test_revision_without_exact_fiscal_period_does_not_exist(self):
        hist=[{'observed_at_utc':'2026-10-01T00:00:00+00:00','periods':{'0y':{'consensus_eps_average':5,'fiscal_period_end':None}}},
              {'observed_at_utc':'2026-11-01T00:00:00+00:00','periods':{'0y':{'consensus_eps_average':6,'fiscal_period_end':None}}}]
        self.assertIsNone(fr._revision_history(hist)['0y']['revision_pct'])
    def test_revision_requires_same_fiscal_end(self):
        hist=[{'observed_at_utc':'2026-10-01T00:00:00+00:00','periods':{'0y':{'consensus_eps_average':5,'fiscal_period_end':'2026-12-31'}}},
              {'observed_at_utc':'2026-11-01T00:00:00+00:00','periods':{'0y':{'consensus_eps_average':6,'fiscal_period_end':'2027-12-31'}}}]
        self.assertIsNone(fr._revision_history(hist)['0y']['revision_pct'])
    def test_verified_only_as_secondary_revision_when_same_period(self):
        hist=[{'observed_at_utc':'2026-10-01T00:00:00+00:00','periods':{'0y':{'consensus_eps_average':5,'fiscal_period_end':'2026-12-31'}}},
              {'observed_at_utc':'2026-11-01T00:00:00+00:00','periods':{'0y':{'consensus_eps_average':6,'fiscal_period_end':'2026-12-31'}}}]
        o=fr._revision_history(hist)['0y'];self.assertEqual(o['revision_pct'],20)
        self.assertFalse(o['independently_verified'])
    def test_prioritize_nvda_even_among_alphabetical_aapl(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);tree(root)
            cfg={**core.DEFAULT_ASSUMPTIONS,'priority_tickers':['NVDA','PENG'],'max_new_forward_estimates_per_discovery_run':2}
            seen=[]
            def get(t):
                seen.append(t);return FakeFrame({'0y':{'avg':3.3,'low':2,'high':4.3,'numberOfAnalysts':2}})
            o=fr.collect_estimates(root,NOW,cfg,get)
            self.assertEqual(seen,['NVDA','PENG'])
            self.assertEqual(o['original_200_count'],200);self.assertEqual(o['discovery_count'],1)
            self.assertFalse(o['companies']['NVDA']['usable_for_intrinsic_validation'])
            self.assertFalse(o['orders_enabled'])
    def test_missing_yahoo_data_still_respects_max_request_budget(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);tree(root)
            cfg={**core.DEFAULT_ASSUMPTIONS,'priority_tickers':['NVDA','PENG'],
                 'max_new_forward_estimates_per_discovery_run':2}
            calls=[]
            def missing(t):calls.append(t);return None
            with mock.patch('time.sleep'):
                first=fr.collect_estimates(root,NOW,cfg,missing)
            self.assertEqual(calls,['NVDA','PENG'])
            self.assertEqual(first['attempts_this_run'],['NVDA','PENG'])
            self.assertEqual(len(first['temporary_failures']),2)
            core.write(root/'reports/forward_estimates_60.json',first)
            calls.clear()
            with mock.patch('time.sleep'):
                later=fr.collect_estimates(root,NOW,cfg,missing)
            self.assertEqual(calls,['AAPL','MSFT'])
            self.assertEqual(len(later['attempts_this_run']),2)
            self.assertEqual(later['per_ticker_status']['NVDA'],'PROVIDER_PER_TICKER_COOLDOWN')
    def test_sec_403_guidance_persists_cooldown_across_runs(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'reports').mkdir()
            class Forbidden:
                def __init__(self):self.requests=0
                def get(self,*args,**kwargs):self.requests+=1;return Response(status=403)
            session=Forbidden()
            with mock.patch.dict(os.environ,{'SEC_USER_AGENT':'Research Team research@example.org'}):
                previous=fr.fetch_guidance(root,NOW,session)
                core.write(root/'reports/issuer_guidance_60.json',previous)
                current=fr.fetch_guidance(root,NOW,session)
            self.assertEqual(session.requests,1)
            self.assertEqual(current['status'],'ISSUER_PROVIDER_COOLDOWN_ACTIVE')

    def test_no_automatic_buy_even_with_huge_vendor_estimate(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);tree(root)
            core.write(root/'reports/forward_estimates_60.json',{'companies':{'NVDA':{
               'status':'UNOFFICIAL_CONSENSUS_SNAPSHOT','periods':{'0y':{'consensus_eps_average':10000}},
               'source':'yfinance','revisions':{},'observed_at_utc':NOW.isoformat()}}})
            val={'companies':[{'ticker':'NVDA','validation_status':'NOT VALIDATED',
                    'verified_intrinsic_value':None,'selected_entry':None,'orders_enabled':False}]}
            out=fr.attach(val,root)
            a=out['companies'][0]
            self.assertIsNone(a['selected_entry']);self.assertEqual(a['validation_status'],'NOT VALIDATED')
            self.assertFalse(a['external_forward_earnings']['usable_to_validate_intrinsic_value'])
    def test_completeness_map_contains_all_200_and_discovery_even_offline(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);tree(root)
            x=fr.collect_estimates(root,NOW,{**core.DEFAULT_ASSUMPTIONS,'max_new_forward_estimates_per_discovery_run':8},None,offline=True)
            self.assertEqual(len(x['per_ticker_status']),201)
            self.assertEqual(x['snapshot_count'],0)
            self.assertEqual(x['per_ticker_status']['NVDA'],'NOT_COLLECTED_OR_COOLDOWN')
    def test_provider_429_gives_cooldown_no_invented_eps(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);tree(root)
            cfg={**core.DEFAULT_ASSUMPTIONS,'priority_tickers':['NVDA'],'max_new_forward_estimates_per_discovery_run':8}
            def fail(t):raise RuntimeError('429 Too Many Requests')
            o=fr.collect_estimates(root,NOW,cfg,fail)
            self.assertTrue(o['provider_cooldown_until_utc'])
            self.assertFalse(o['companies'])


class SecureSecPriority(TestCase):
    def test_nvda_has_priority_over_alphabetical_order(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);tree(root)
            cfg={**core.DEFAULT_ASSUMPTIONS,'priority_tickers':['NVDA','PENG'],
                 'max_new_sec_companies_per_discovery_run':2}
            ss=Session(listed=['AAPL','MSFT','NVDA','PENG'])
            with mock.patch.dict(os.environ,{'SEC_USER_AGENT':'Research Team research@example.org'}),mock.patch.object(core.time,'sleep'):
                out=core.fetch_update(root,NOW,cfg,session=ss)
            self.assertEqual(out['selected_issuer_tickers'],['NVDA','PENG'])
            self.assertEqual(len(out['companies']),2)
            self.assertTrue(out['research_priority_is_not_a_buy_signal'])
            self.assertFalse(out['orders_enabled'])
    def test_cyclicals_remain_null_with_no_annual_facts(self):
        out=core.primary_series('NVDA',{'cik':1,'entityName':'Nvidia','facts':{}},NOW,1)
        self.assertEqual(out['annual_facts']['operating_cash_flow'],[])
        self.assertFalse(core.combine_periods(out))
    def test_complete_coverage_report_never_ranks_unvalidated(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);tree(root)
            core.write(root/'reports/valuation_60_latest.json',{
             'companies':[{'ticker':'NVDA','validation_status':'NOT VALIDATED',
                      'base':None,'latest_dated_price':125.53,
                      'missing_evidence_flags':['PRIMARY_XBRL_NOT_COLLECTED']}],
             'orders_enabled':False})
            o=fr.coverage_report(root,NOW)
            self.assertEqual(o['reported_count'],201)
            self.assertEqual(o['validated_below_assumed_base_count'],0)
            nv=next(x for x in o['companies'] if x['ticker']=='NVDA')
            self.assertIsNone(nv['below_assumed_base_intrinsic_value'])
            self.assertFalse(nv['buy_signal'])
            self.assertEqual(nv['valuation_validation_status'],'NOT VALIDATED')
            self.assertFalse(o['orders_enabled'])
    def test_priority_research_list_never_fabricates_undervaluation(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);tree(root)
            core.write(root/'reports/valuation_60_latest.json',{'companies':[
               {'ticker':'AAPL','validation_status':'PRIMARY_INPUTS_VALIDATED_FORECASTS_HYPOTHETICAL',
                 'base':100,'selected_entry':85,'latest_dated_price':90,'missing_evidence_flags':[],
                 'primary_source_evidence':{'url':'https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json',
                                            'source_hash_sha256':'a'*64}},
               {'ticker':'NVDA','validation_status':'NOT VALIDATED','base':2000,
                 'latest_dated_price':1,'missing_evidence_flags':['PRIMARY_XBRL_NOT_COLLECTED']}]})
            x=fr.coverage_report(root,NOW)
            self.assertEqual(x['validated_below_assumed_base_count'],1)
            self.assertEqual(x['research_priority_order_not_buy_recommendations'][0],'NVDA')
            n=next(i for i in x['companies'] if i['ticker']=='NVDA')
            self.assertIsNone(n['below_assumed_base_intrinsic_value'])
            self.assertFalse(n['buy_signal'])
    def test_research_shortlist_requires_provenance_not_status_alone(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);tree(root)
            core.write(root/'reports/valuation_60_latest.json',{'companies':[
               {'ticker':'AAPL','validation_status':'PRIMARY_INPUTS_VALIDATED_FORECASTS_HYPOTHETICAL',
                 'base':300,'selected_entry':255,'latest_dated_price':200,'missing_evidence_flags':[]},
               {'ticker':'NVDA','validation_status':'NOT VALIDATED',
                 'base':1000,'selected_entry':100,'latest_dated_price':1,
                 'missing_evidence_flags':['PRIMARY_XBRL_NOT_COLLECTED']}]})
            x=fr.coverage_report(root,NOW)
            self.assertEqual(x['validated_below_assumed_base_count'],0)
            self.assertEqual(x['evidence_qualified_at_selected_margin_of_safety_count'],0)
            self.assertTrue(x['no_qualified_undervalued_candidates'])
            a=next(r for r in x['companies'] if r['ticker']=='AAPL')
            self.assertIn('PRIMARY_FILING_PROVENANCE_NOT_VERIFIABLE',a['missing_evidence_flags'])
            self.assertIsNone(a['selected_margin_of_safety_entry'])
            self.assertIsNone(a['below_selected_margin_of_safety_entry'])
    def test_separates_below_base_from_below_margin_of_safety(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);tree(root)
            src={'url':'https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json',
                 'source_hash_sha256':'b'*64}
            core.write(root/'reports/valuation_60_latest.json',{'companies':[
               {'ticker':'AAPL','validation_status':'PRIMARY_INPUTS_VALIDATED_FORECASTS_HYPOTHETICAL',
                 'base':100,'selected_entry':85,'selected_margin_of_safety_pct':15,
                 'latest_dated_price':90,'missing_evidence_flags':[],
                 'price_as_of':'2026-11-20','primary_source_evidence':src},
               {'ticker':'MSFT','validation_status':'PRIMARY_INPUTS_VALIDATED_FORECASTS_HYPOTHETICAL',
                 'base':150,'selected_entry':120,'selected_margin_of_safety_pct':20,
                 'latest_dated_price':105,'missing_evidence_flags':[],
                 'price_as_of':'2026-11-20','primary_source_evidence':src}]})
            x=fr.coverage_report(root,NOW)
            self.assertEqual(x['validated_below_assumed_base_count'],2)
            self.assertEqual(x['evidence_qualified_at_selected_margin_of_safety_count'],1)
            self.assertEqual([r['ticker'] for r in x['evidence_qualified_at_selected_margin_of_safety']],['MSFT'])
            self.assertEqual([r['ticker'] for r in x['evidence_qualified_below_base_research']],['MSFT','AAPL'])
            self.assertTrue(all(not r['buy_signal'] and not r['orders_enabled'] for r in x['evidence_qualified_below_base_research']))
    def test_unverified_source_hash_is_not_evidence(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);tree(root)
            core.write(root/'reports/valuation_60_latest.json',{'companies':[
              {'ticker':'AAPL','validation_status':'PRIMARY_INPUTS_VALIDATED_FORECASTS_HYPOTHETICAL',
               'base':1000,'selected_entry':800,'latest_dated_price':100,
               'missing_evidence_flags':[],'primary_source_evidence':{'url':'https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json',
               'source_hash_sha256':'bad'}}]})
            x=fr.coverage_report(root,NOW)
            self.assertEqual(x['evidence_qualified_at_selected_margin_of_safety_count'],0)
    def test_unverified_company_never_in_value_research_list(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);tree(root)
            core.write(root/'reports/valuation_60_latest.json',{'companies':[
              {'ticker':'NVDA','validation_status':'NOT VALIDATED','base':999,
               'selected_entry':100,'latest_dated_price':1,
               'missing_evidence_flags':['PRIMARY_XBRL_NOT_COLLECTED']}]})
            x=fr.coverage_report(root,NOW)
            self.assertEqual(x['evidence_qualified_below_base_research'],[])
            self.assertEqual(x['evidence_qualified_at_selected_margin_of_safety'],[])
            n=next(r for r in x['companies'] if r['ticker']=='NVDA')
            self.assertIsNone(n['base_upside_pct']);self.assertIsNone(n['selected_margin_of_safety_entry'])
    def test_forward_issuer_guidance_cannot_validate_nvidia(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);tree(root)
            src=fr.issuer_guidance_from_document('NVDA',fr.OFFICIAL_NVDA_URL,GOOD_TEXT,NOW)
            core.write(root/'reports/issuer_guidance_60.json',{'companies':{'NVDA':src}})
            val={'companies':[{'ticker':'NVDA','validation_status':'NOT VALIDATED',
                    'verified_intrinsic_value':None,'selected_entry':None,'orders_enabled':False}]}
            out=fr.attach(val,root)
            n=out['companies'][0]
            self.assertEqual(n['issuer_forward_guidance']['reported_guidance']['revenue_usd_billions'],130)
            self.assertEqual(n['validation_status'],'NOT VALIDATED')
            self.assertIsNone(n['verified_intrinsic_value'])
            self.assertIsNone(n['selected_entry'])

    def test_sec_priority_is_not_order_or_trading_decision(self):
        cfg={**core.DEFAULT_ASSUMPTIONS,'priority_tickers':['NVDA','SHEL'],'max_new_sec_companies_per_discovery_run':2}
        self.assertFalse(cfg.get('orders_enabled',False))

if __name__=='__main__':
    import unittest; unittest.main()
