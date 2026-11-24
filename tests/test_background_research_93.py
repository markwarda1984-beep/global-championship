import copy,json,tempfile,time,unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
from unittest.mock import Mock,patch
from background_evidence_93 import merge_evidence,merge_adapters
from background_research_93 import choose_batch,Fetcher,ProviderBlocked,filing_selection,run,write,read,note_candidates
from evidence_recovery_91 import digest
NOW=datetime.now(timezone.utc)
def row(t,unsupported=True):return {'ticker':t,'universe':'ORIGINAL_200','scenarios':None if unsupported else {'base':1},'missing_inputs':['MISSING_PRIMARY'] if unsupported else []}
def record(t='TEST',date=None):
 facts={'net_income':[{'value':10,'unit':'USD','start':'2025-01-01','end':'2025-12-31'}]}
 return {'ticker':t,'annual_facts':facts,'source_url':'https://data.sec.gov/api/xbrl/companyfacts/CIK0000000001.json','status':'OFFICIAL_SEC_COMPANYFACTS_RETRIEVED','observed_utc':(date or NOW-timedelta(seconds=1)).isoformat(),'evidence_hash_sha256':digest(facts),'orders_enabled':False}
def delta(companies=None):return {'schema_version':'9.3-background-primary-evidence-1','companies':companies or {},'adapters':{},'orders_enabled':False,'orders_generated':0}
class BackgroundEvidenceTests(unittest.TestCase):
 def test_newer_valid_source_replaces_old_without_mutation(self):
  old={'TEST':record(date=NOW-timedelta(days=1))};d=delta({'TEST':record()});out=merge_evidence(old,d)
  self.assertEqual(out['TEST'],d['companies']['TEST']);self.assertNotEqual(old,out)
 def test_tampered_input_cannot_promote(self):
  r=record();r['annual_facts']['net_income'][0]['value']=1000
  self.assertEqual(merge_evidence({},delta({'TEST':r})),{})
 def test_unsafe_orders_rejected(self):
  d=delta();d['orders_enabled']=True
  with self.assertRaises(ValueError):merge_evidence({},d)
 def test_future_or_older_evidence_cannot_override(self):
  old={'TEST':record()}
  self.assertEqual(merge_evidence(old,delta({'TEST':record(date=NOW+timedelta(days=1))})),old)
  self.assertEqual(merge_evidence(old,delta({'TEST':record(date=NOW-timedelta(days=2))})),old)
 def test_non_primary_host_rejected(self):
  r=record();r['source_url']='https://example.com/facts';self.assertEqual(merge_evidence({},delta({'TEST':r})),{})
 def test_older_adapter_cannot_replace_newer(self):
  a={'TEST':{'share_basis':{'as_of':'2026-11-01'}}};d=delta();d['adapters']={'TEST':{'share_basis':{'as_of':'2026-10-01'}}}
  self.assertEqual(merge_adapters(a,d),a)
class BackgroundQueueTests(unittest.TestCase):
 def test_fair_rotation_before_repeat(self):
  state={'companies':{'DUG.AX':{'last_attempt_utc':(NOW-timedelta(days=9)).isoformat()}}}
  self.assertEqual(choose_batch([row('DUG.AX'),row('NEW')],state,NOW,1)[0]['ticker'],'NEW')
 def test_future_backoff_and_supported_cases_skipped(self):
  state={'companies':{'WAIT':{'next_attempt_utc':(NOW+timedelta(days=1)).isoformat()}}}
  self.assertEqual(choose_batch([row('WAIT'),row('DONE',False),row('NEXT')],state,NOW,20),[row('NEXT')])
 def test_priority_only_within_due_fair_cohort(self):
  self.assertEqual(choose_batch([row('AAA'),row('DUG.AX')],{},NOW,1)[0]['ticker'],'DUG.AX')
 def test_bounded_and_unique_latest_annual_selection(self):
  m={'filings':{'recent':{'form':['8-K','10-Q','10-K','10-K']}}}
  self.assertEqual(filing_selection(m)[1],[1,2])
 def test_candidate_tags_never_approved_as_financial_inputs(self):
  notes=note_candidates('<table><tr><td>Purchases of property and equipment</td><td><ix:nonfraction name="issuer:UnknownTag">10</ix:nonfraction></td></tr></table>')
  self.assertTrue(notes);self.assertFalse(notes[0]['usable_for_valuation'])
 def test_atomic_nan_failure_preserves_checkpoint(self):
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder)/'state.json';write(p,{'value':1})
   with self.assertRaises(ValueError):write(p,{'value':float('nan')})
   self.assertEqual(read(p,{}),{'value':1})
class BackgroundSourceTests(unittest.TestCase):
 def test_403_stops_sec_hosts_and_persists_cooldown(self):
  session=Mock();session.get.return_value.status_code=403;state={};f=Fetcher(state,NOW,time.monotonic()+60,session)
  with patch('background_research_93.time.sleep'):
   with self.assertRaises(ProviderBlocked):f.get('https://data.sec.gov/submissions/CIK1.json')
   with self.assertRaises(ProviderBlocked):f.get('https://www.sec.gov/Archives/a.html')
  self.assertEqual(session.get.call_count,1);self.assertIn('www.sec.gov',state['provider_cooldowns'])
 def test_unapproved_host_never_requested(self):
  session=Mock();f=Fetcher({},NOW,time.monotonic()+60,session)
  with self.assertRaises(ValueError):f.get('http://127.0.0.1/private')
  session.get.assert_not_called()
 def test_redirect_never_followed_to_unapproved_host(self):
  session=Mock();session.get.return_value.status_code=302;f=Fetcher({},NOW,time.monotonic()+60,session)
  with patch('background_research_93.time.sleep'):
   with self.assertRaises(ValueError):f.get('https://www.asx.com.au/report')
  self.assertFalse(session.get.call_args.kwargs['allow_redirects'])
class WorkerCheckpointTests(unittest.TestCase):
 def fixture(self,root):
  rows=[row('AAA.AX'),row('BBB.AX')]+[row(f'T{i}',False) for i in range(198)]
  write(root/'reports/valuation_90_latest.json',{'companies':rows})
  return rows
 def test_actual_checkpoint_rotates_and_reassesses_all_200(self):
  class Fake:
   def __init__(self,state,now,deadline):self.deadline=deadline;self.requests=0;self.retrieved=0
   def get(self,url):self.requests+=1;self.retrieved+=1;return '<a href="/annual">Annual Report</a>','a'*64
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);rows=self.fixture(root);assess=lambda root,now:{'companies':copy.deepcopy(rows)}
   a=run(root,1,1,NOW,Fake,assess);b=run(root,1,1,NOW+timedelta(hours=4),Fake,assess)
   self.assertEqual(a['results'][0]['ticker'],'AAA.AX');self.assertEqual(b['results'][0]['ticker'],'BBB.AX')
   self.assertEqual(b['original_200_still_unsupported'],2)
   self.assertEqual(read(root/'reports/valuation_90_latest.json',{})['companies'],rows)
 def test_failed_source_is_saved_with_backoff_not_called_validated(self):
  class Fail:
   def __init__(self,state,now,deadline):self.deadline=deadline;self.requests=0;self.retrieved=0
   def get(self,url):self.requests+=1;raise ValueError('bad source')
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);rows=self.fixture(root);out=run(root,1,1,NOW,Fail,lambda root,now:{'companies':rows})
   self.assertEqual(out['source_health'],'PARTIAL_OR_UNAVAILABLE');self.assertEqual(out['newly_supported_this_batch'],[])
   saved=read(root/'reports/background_research_state_93.json',{})['companies']['AAA.AX']
   self.assertEqual(saved['attempt_count'],1);self.assertGreater(saved['next_attempt_utc'],NOW.isoformat())
 def test_oversized_batch_rejected_before_source_calls(self):
  with self.assertRaises(ValueError):run(Path('/unused'),21)
