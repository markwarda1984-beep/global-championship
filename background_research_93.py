"""Bounded resumable issuer research. No orders, guessed financials, or auto-approved new models."""
from __future__ import annotations
import argparse,copy,csv,hashlib,json,math,os,re,shutil,tempfile,time
from datetime import datetime,timedelta,timezone
from pathlib import Path
from urllib.parse import urlparse,urljoin,quote
import requests
from bs4 import BeautifulSoup
from evidence_recovery_91 import recover_series,digest
from background_evidence_93 import merge_evidence
from recover_documents_91 import cover_shares,cover_ratio,primary_document
from share_classes_92 import REVIEWED_EQUAL_CLASSES,equal_class_counts
from reviewed_cashflow_92 import RULES,extract,apply_reviewed_overlay

SCHEMA='9.3-background-research-1'
PUBLIC_CONTACT='ChampionshipResearch https://github.com/markwarda1984-beep/global-championship'
HOSTS={'data.sec.gov','www.sec.gov','www.asx.com.au','announcements.asx.com.au'}

def read(path,default):return json.loads(path.read_text()) if path.exists() else copy.deepcopy(default)
def write(path,obj):
 path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_suffix(path.suffix+'.tmp')
 temp.write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n');temp.replace(path)
def stamp(value):
 try:
  d=datetime.fromisoformat(value)
  return d if d.tzinfo else None
 except (TypeError,ValueError):return None

class ProviderBlocked(Exception):pass
class Fetcher:
 def __init__(self,state,now,deadline,session=None):
  self.state=state;self.now=now;self.deadline=deadline;self.session=session or requests.Session();self.requests=0;self.retrieved=0
  self.session.headers.update({'User-Agent':os.environ.get('SEC_USER_AGENT') or PUBLIC_CONTACT})
 def get(self,url):
  host=urlparse(url).hostname
  if urlparse(url).scheme!='https' or host not in HOSTS or urlparse(url).port not in (None,443):raise ValueError('Unapproved primary source host')
  due=stamp(self.state.setdefault('provider_cooldowns',{}).get(host))
  if due and due>self.now:raise ProviderBlocked(host+' cooldown')
  if time.monotonic()>self.deadline:raise TimeoutError('Run time budget exhausted')
  time.sleep(.2);self.requests+=1
  response=self.session.get(url,timeout=(10,35),stream=True,allow_redirects=False)
  try:
   if response.status_code in (403,429):
    self.state['provider_cooldowns'][host]=(self.now+timedelta(hours=24)).isoformat()
    if host.endswith('sec.gov'):
     for sec in ('data.sec.gov','www.sec.gov'):self.state['provider_cooldowns'][sec]=(self.now+timedelta(hours=24)).isoformat()
    raise ProviderBlocked(host+' HTTP '+str(response.status_code))
   if 300<=response.status_code<400:
    raise ValueError('Source redirect needs review; not followed automatically')
   response.raise_for_status();chunks=[];size=0
   for block in response.iter_content(65536):
    size+=len(block)
    if size>20_000_000:raise ValueError('Source exceeds bounded document size')
    chunks.append(block)
   body=b''.join(chunks);self.retrieved+=1
   return body.decode('utf-8',errors='replace'),hashlib.sha256(body).hexdigest()
  finally:response.close()

def choose_batch(rows,state,now,limit):
 due=[]
 for row in rows:
  if row.get('scenarios') is not None:continue
  saved=state.get('companies',{}).get(row['ticker'],{});when=stamp(saved.get('next_attempt_utc'))
  if when and when>now:continue
  # Every never-attempted company gets a turn before completed attempts are repeated.
  due.append((bool(saved.get('last_attempt_utc')),0 if row['ticker'] in ('HPE','SKS.AX','DUG.AX') else 1,saved.get('last_attempt_utc',''),row['ticker'],row))
 return [x[-1] for x in sorted(due,key=lambda x:x[:4])[:limit]]

def filing_selection(meta):
 recent=meta['filings']['recent'];valid=[i for i,f in enumerate(recent['form']) if f in ('10-K','10-Q','20-F','40-F')]
 annual=[i for i in valid if recent['form'][i] in ('10-K','20-F','40-F')]
 return recent,list(dict.fromkeys(([valid[0]] if valid else [])+([annual[0]] if annual else [])))

def note_candidates(html):
 """Human review material only; unknown tags never enter the valuation engine."""
 soup=BeautifulSoup(html,'html.parser');out=[]
 for row in soup.find_all('tr'):
  label=' '.join(row.get_text(' ',strip=True).split())
  if len(label)>1000 or not re.search(r'capital expenditures|purchases of.*(?:equipment|property)|shares outstanding|net cash.*operating',label,re.I):continue
  tags=sorted({f.get('name') for f in row.find_all(lambda x:x.name and 'nonfraction' in x.name.lower()) if f.get('name')})
  if tags:out.append({'row_excerpt':label[:300],'inline_concepts':tags[:8],'usable_for_valuation':False})
  if len(out)>=24:break
 return out

def collect_sec(ticker,company,fetcher,delta,notes,now,overlay):
 cik=company['cik'];url=f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json'
 text,sha=fetcher.get(url);raw=json.loads(text);rec=recover_series(ticker,raw,now,cik);rec=apply_reviewed_overlay(rec,overlay)
 sources=[{'url':url,'sha256':sha}];parsed=0;doc_errors=[]
 # Save a successfully fetched facts record even if a later source fails.
 delta['companies'][ticker]=rec
 meta_text,meta_sha=fetcher.get(f'https://data.sec.gov/submissions/CIK{cik:010d}.json');meta=json.loads(meta_text)
 if int(meta.get('cik',0))!=int(cik):raise ValueError('Submission issuer identity mismatch')
 recent,chosen=filing_selection(meta)
 for idx in chosen:
  acc=recent['accessionNumber'][idx];document=recent['primaryDocument'][idx]
  if '..' in document or document.startswith('/'):continue
  url=f'https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace("-","")}/{quote(document,safe="/")}'
  try:html,doc_sha=fetcher.get(url)
  except (requests.RequestException,ValueError) as exc:
   doc_errors.append(type(exc).__name__);continue
  except ProviderBlocked:raise
  metadata={'url':url,'accession':acc,'filed':recent['filingDate'][idx],'form':recent['form'][idx]}
  sources.append({'url':url,'sha256':doc_sha,'filed':metadata['filed'],'form':metadata['form']})
  notes.setdefault(ticker,{'documents':[]})['documents'].append({**sources[-1],'unreviewed_candidates':note_candidates(html)})
  notes[ticker]['documents']=notes[ticker]['documents'][-4:]
  shares=cover_shares(html)
  if ticker in REVIEWED_EQUAL_CLASSES:
   reviewed=equal_class_counts(html,REVIEWED_EQUAL_CLASSES[ticker],now)
   if reviewed:shares=reviewed
  shares=[s for s in shares if s['end']<=now.date().isoformat()]
  for s in shares:s.update(source_url=url,source_document_sha256=doc_sha,filed=metadata['filed'],accession=acc,form=metadata['form'])
  if shares:
   by={r['end']:r for r in rec['annual_facts']['shares']};by.update({r['end']:r for r in shares})
   rec['annual_facts']['shares']=sorted(by.values(),key=lambda r:r['end'])[-20:]
   current=rec.get('latest_share_count')
   if not current or shares[-1]['end']>=current['end']:rec['latest_share_count']=shares[-1]
   parsed+=len(shares)
  if ticker in RULES:
   cash=extract(html,RULES[ticker]['components'],RULES[ticker]['labels'],metadata,now)
   if cash:
    entry={'ticker':ticker,'review_status':'PRIMARY_DOCUMENT_FIELDS_RECONCILED','periods':cash,'periods_sha256':digest(cash)}
    rec=apply_reviewed_overlay(rec,{'companies':[entry]});parsed+=len(cash)
  ratio,excerpt=cover_ratio(html,ticker);count=rec.get('latest_share_count')
  if ratio and count and count['end']<=metadata['filed']:
   basis=primary_document({'issuer_name':rec['issuer_name'],'source_url':url,'as_of':count['end'],'published_at':metadata['filed'],'accession':acc,'document_sha256':doc_sha,
        'extraction_method':'REVIEWED_EXISTING_COVER_PARSER','excerpt':excerpt,
        'facts':{'ticker':ticker,'quote_currency':'AUD' if ticker.endswith('.AX') else 'USD','ordinary_shares_per_receipt':ratio,'ordinary_shares_outstanding':count['value']}})
   previous=delta['adapters'].get(ticker,{}).get('share_basis',{})
   if basis['as_of']>=previous.get('as_of',''):delta['adapters'].setdefault(ticker,{})['share_basis']=basis
 rec['evidence_hash_sha256']=digest(rec['annual_facts']);delta['companies'][ticker]=rec
 return {'sources':sources,'parsed_observations':parsed,'document_errors':doc_errors,'unreviewed_documents':max(0,len(sources)-1)}

def collect_asx(ticker,fetcher,now):
 symbol=ticker.removesuffix('.AX');url=f'https://www.asx.com.au/asx/v2/statistics/announcements.do?asxCode={symbol}&by=asxCode&period=M6&timeframe=D'
 html,sha=fetcher.get(url);soup=BeautifulSoup(html,'html.parser');filings=[]
 for a in soup.find_all('a',href=True):
  title=' '.join(a.get_text(' ',strip=True).split())
  if not re.search(r'annual report|full.year.*report|appendix 4e|financial report',title,re.I):continue
  link=urljoin(url,a['href'])
  if urlparse(link).hostname not in HOSTS or urlparse(link).scheme!='https':continue
  filings.append({'title':title[:250],'url':link})
 return {'sources':[{'url':url,'sha256':sha}],'filings':filings,'parsed_observations':0,
         'research_status':'ISSUER_TABLE_EXTRACTION_REVIEW_REQUIRED','remaining_work':'Verify issuer-hosted annual report tables and a reviewed parser. ASX acknowledgement terms are not automatically accepted. Index links are not financial inputs.'}

def assess_without_overwriting_reports(root,now):
 from championship_90 import build
 with tempfile.TemporaryDirectory() as folder:
  scratch=Path(folder)
  for directory in ('reports','settings'):
   shutil.copytree(root/directory,scratch/directory)
  shutil.copyfile(root/'watchlist.csv',scratch/'watchlist.csv')
  if (root/'data/latest.json').exists():
   (scratch/'data').mkdir();shutil.copyfile(root/'data/latest.json',scratch/'data/latest.json')
  return build(scratch,'scan',now)

def run(root,batch_size=20,max_minutes=8,now=None,fetcher_factory=Fetcher,assessment=assess_without_overwriting_reports):
 now=now or datetime.now(timezone.utc)
 if not 1<=batch_size<=20 or not 1<=max_minutes<=12:raise ValueError('Batch/time bounds exceeded')
 reports=root/'reports';state_path=reports/'background_research_state_93.json';state=read(state_path,{'schema_version':SCHEMA,'companies':{},'provider_cooldowns':{},'orders_enabled':False,'orders_generated':0})
 if state.get('orders_enabled') is not False or state.get('orders_generated')!=0:raise ValueError('Unsafe research state')
 model=read(reports/'valuation_90_latest.json',{});rows=model.get('companies',[])
 assert sum(r['universe']=='ORIGINAL_200' for r in rows)==200,'Complete fixed-200 report required'
 unresolved=[r for r in rows if r.get('scenarios') is None]
 state.setdefault('baseline_original_unsupported',[r['ticker'] for r in unresolved if r['universe']=='ORIGINAL_200'])
 selected=choose_batch(rows,state,now,batch_size)
 path=reports/'background_evidence_93.json';delta=read(path,{'schema_version':'9.3-background-primary-evidence-1','companies':{},'adapters':{},'orders_enabled':False,'orders_generated':0})
 # Validate committed inputs before making any requests.
 merge_evidence({},delta)
 base=read(reports/'primary_evidence_91.json',{}).get('companies',{});companies=merge_evidence(base,delta)
 overlay=read(reports/'reviewed_cashflow_92.json',{});notes=read(reports/'background_source_notes_93.json',{'companies':{},'orders_enabled':False})
 fetcher=fetcher_factory(state,now,time.monotonic()+max_minutes*60);results=[]
 for row in selected:
  if time.monotonic()>fetcher.deadline:break
  ticker=row['ticker'];previous=state['companies'].get(ticker,{});before=fetcher.requests
  result={'ticker':ticker,'universe':row['universe'],'missing_inputs_before':row['missing_inputs'],'orders_enabled':False}
  try:
   company=companies.get(ticker)
   if company and company.get('cik'):
    result.update(collect_sec(ticker,company,fetcher,delta,notes['companies'],now,overlay));result['research_status']='PRIMARY_SERIES_REFRESHED_REASSESSMENT_PENDING'
   elif ticker.endswith('.AX'):result.update(collect_asx(ticker,fetcher,now))
   else:result.update(research_status='ISSUER_IDENTITY_REVIEW_REQUIRED',sources=[],parsed_observations=0)
  except ProviderBlocked as exc:result.update(research_status='PROVIDER_COOLDOWN',reason=str(exc),sources=[])
  except (requests.RequestException,ValueError,KeyError,IndexError,TimeoutError) as exc:
   # Do not include request headers or credentials in public reports.
   result.update(research_status='SOURCE_FETCH_OR_PARSE_FAILED',reason=type(exc).__name__,sources=[])
  result['collection_status']=result['research_status']
  made=fetcher.requests-before;attempts=previous.get('attempt_count',0)+(1 if made else 0)
  result.update(http_requests=made,last_attempt_utc=now.isoformat(),attempt_count=attempts)
  retry_hours=24 if result['research_status']=='PROVIDER_COOLDOWN' else min(168,2**min(attempts,7)) if result['research_status']=='SOURCE_FETCH_OR_PARSE_FAILED' else 168
  result['next_attempt_utc']=(now+timedelta(hours=retry_hours)).isoformat()
  state['companies'][ticker]={**previous,**result};results.append(result)
  delta['updated_at_utc']=now.isoformat();write(path,delta);write(state_path,state);write(reports/'background_source_notes_93.json',notes)
 # Ensure empty/no-due runs are equally reviewable and don't edit legacy reports.
 rates=read(reports/'fx_recovery_91.json',{}).get('rates',[])
 for ticker,company in delta['companies'].items():
  quote_currency='AUD' if ticker.endswith('.AX') else 'USD'
  for fx in rates:
   date=stamp(str(fx.get('as_of'))+'T00:00:00+00:00')
   if fx.get('from')==company.get('financial_currency') and fx.get('to')==quote_currency and date and 0<=(now-date).days<=7 and isinstance(fx.get('rate'),(float,int)) and fx['rate']>0:
    delta['adapters'].setdefault(ticker,{})['fx']=copy.deepcopy(fx)
 write(path,delta);after=assessment(root,now);mapping={r['ticker']:r for r in after['companies']};newly=[]
 for result in results:
  current=mapping[result['ticker']];supported=current['scenarios'] is not None
  result.update(supported_after=supported,missing_inputs_after=current['missing_inputs'])
  if supported:
   newly.append(result['ticker']);result['research_status']='SUPPORTED_BY_EXISTING_REVIEWED_MODEL'
  elif result['research_status']=='PRIMARY_SERIES_REFRESHED_REASSESSMENT_PENDING':
   result['research_status']='REVIEW_REQUIRED_AFTER_PRIMARY_REFRESH'
  state['companies'][result['ticker']].update(result)
 original=[r for r in after['companies'] if r['universe']=='ORIGINAL_200'];supported=sum(r['scenarios'] is not None for r in original)
 # Include all open cases, not just this batch, in the human review queue.
 names={r['ticker']:r.get('name',r['ticker']) for r in csv.DictReader((root/'watchlist.csv').open(encoding='utf-8-sig'))} if (root/'watchlist.csv').exists() else {}
 queue=[{'ticker':r['ticker'],'company':names.get(r['ticker'],r.get('company',r['ticker'])),'universe':r['universe'],'missing_inputs':r['missing_inputs'],
         'last_research_status':state['companies'].get(r['ticker'],{}).get('research_status','NOT_YET_ATTEMPTED'),
         'last_attempt_utc':state['companies'].get(r['ticker'],{}).get('last_attempt_utc'),'next_attempt_utc':state['companies'].get(r['ticker'],{}).get('next_attempt_utc'),
         'orders_enabled':False} for r in after['companies'] if r['scenarios'] is None]
 state['last_run_finished_utc']=datetime.now(timezone.utc).isoformat();write(state_path,state)
 run_id=os.environ.get('GITHUB_RUN_ID');summary={'schema_version':SCHEMA,'run_started_utc':now.isoformat(),'run_finished_utc':state['last_run_finished_utc'],
  'workflow_run_url':f'https://github.com/markwarda1984-beep/global-championship/actions/runs/{run_id}' if run_id and run_id.isdigit() else None,
  'schedule_description':'Six bounded batches daily at 00:45, 04:45, 08:45, 12:45, 16:45 and 20:45 Australia/Sydney',
  'batch_limit':batch_size,'selected_count':len(selected),'processed_count':len(results),'http_requests':fetcher.requests,'successful_source_retrievals':fetcher.retrieved,
  'original_200_supported_before':sum(r['scenarios'] is not None for r in rows if r['universe']=='ORIGINAL_200'),'original_200_supported_after':supported,
  'original_200_still_unsupported':200-supported,'newly_supported_this_batch':newly,'results':results,
  'source_health':'NO_CASES_DUE' if not results else 'PARTIAL_OR_UNAVAILABLE' if any(r['collection_status'] in ('PROVIDER_COOLDOWN','SOURCE_FETCH_OR_PARSE_FAILED') for r in results) else 'AVAILABLE_FOR_PROCESSED_BATCH',
  'limitations':['Existing reviewed parsers can promote supported cases; new sector economics and unverified issuer tables require review.','Source collection is not a supported valuation. No completion date or valuation for all companies is guaranteed.'],
  'orders_enabled':False,'orders_generated':0}
 write(reports/'background_research_latest_93.json',summary);write(reports/'background_review_queue_93.json',{'schema_version':SCHEMA,'companies':queue,'orders_enabled':False,'orders_generated':0})
 history=read(reports/'background_research_history_93.json',{'runs':[],'orders_enabled':False});history['runs']=(history['runs']+[{k:v for k,v in summary.items() if k not in ('results','limitations')}])[-100:];write(reports/'background_research_history_93.json',history)
 lines=['# Background evidence research','',f"Supported: **{supported}/200**. Still unresolved: **{200-supported}**.",'',f"This batch processed **{len(results)}** cases; retrieved **{fetcher.retrieved}** sources. Newly supported: **{', '.join(newly) or 'none'}**.",'',summary['schedule_description']+'.','',
 'Known parsers process verified issuer fields. New valuation methods and unverified tables stay in the review queue. No invented inputs; no orders.','',
 '| Ticker | Status | Outstanding fields |','|---|---|---|']
 for r in queue:lines.append(f"| {r['ticker']} | {r['last_research_status']} | {'; '.join(r['missing_inputs'])} |")
 (reports/'background_research_latest_93.md').write_text('\n'.join(lines)+'\n')
 print(json.dumps({k:v for k,v in summary.items() if k not in ('results','limitations')},indent=2));return summary

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parent);parser.add_argument('--batch-size',type=int,default=20);parser.add_argument('--max-minutes',type=int,default=8);a=parser.parse_args();run(a.root,a.batch_size,a.max_minutes)
