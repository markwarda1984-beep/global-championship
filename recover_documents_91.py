"""Recover listed-share terms and missing outstanding-share facts from SEC covers.
No ratio or share count is inferred from prices or market capitalisation.
"""
import argparse
import copy
import hashlib
import json
import os
import re
import time
from datetime import datetime,timezone
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from championship_60 import ADR_OR_OVERSEAS_SHARE_BASIS
from evidence_recovery_91 import write,digest

WORDS={'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10,'twenty':20,'one-half':.5,'half':.5}

def primary_document(record):
 return {'issuer':record['issuer_name'],'source_url':record['source_url'],'as_of':record['as_of'],'published_at':record['published_at'],
         'accession_or_document_id':record['accession'],'review_status':'PRIMARY_DOCUMENT_FIELDS_RECONCILED',
         'facts':record['facts'],'facts_sha256':digest(record['facts']),
         'source_document_sha256':record['document_sha256'],'extraction_method':record['extraction_method'],'source_excerpt':record['excerpt']}

def cover_ratio(html,ticker):
 soup=BeautifulSoup(html,'html.parser')
 for hidden in soup.find_all(['ix:header','ix:hidden','head','script','style']):hidden.decompose()
 plain=' '.join(soup.get_text(' ',strip=True).split())
 header=re.search(r'title of each class',plain,re.I)
 if not header:return None,None
 tail=plain[header.start():]
 ending=re.search(r'Securities registered or to be registered pursuant to Section 12\(g\)|Securities registered pursuant to Section 12\(g\)',tail,re.I)
 cover=tail[:ending.start()] if ending else tail[:4000]
 if not re.search(r'(?<![A-Z0-9])'+re.escape(ticker)+r'(?![A-Z0-9])',cover):return None,None
 pattern=r'(?:each\s+(?:of which\s+)?)?represent(?:ing|s)\s+(?:of\s+)?([\d.,]+|one-half|half|one|two|three|four|five|six|seven|eight|nine|ten|twenty)(?:\s*\(\d+\))?\s+(?:(?:class\s+[a-z]|ordinary|common|registered|B|A)\s+){0,4}shares?'
 matches=[]
 for m in re.finditer(pattern,plain,re.I):
  context=plain[max(0,m.start()-100):m.end()+50]
  if not re.search(r'depositary|depository|ADS|ADR',context,re.I):continue
  token=m.group(1).lower();ratio=WORDS.get(token)
  if ratio is None:
   try:ratio=float(token.replace(',',''))
   except ValueError:continue
  if 0<ratio<=100:matches.append((ratio,context[:180]))
 if matches:return matches[0] if len({r for r,_ in matches})==1 else (None,None)
 # ADR footnote or registration-only underlying shares never establish 1:1.
 if re.search(r'depositary|depository|\bADS\b|\bADR\b',cover,re.I) or '*' in cover:return None,None
 if re.search(r'(ordinary|common|registered)\s+(?:stock|shares?)',cover,re.I):return 1.0,cover[:180]
 return None,None

def cover_shares(html):
 soup=BeautifulSoup(html,'html.parser');contexts={}
 for c in soup.find_all(lambda x:x.name and x.name.split(':')[-1].lower()=='context'):
  instant=c.find(lambda x:x.name and x.name.split(':')[-1].lower()=='instant')
  if instant:
   dimensions=[x.get_text(' ',strip=True) for x in c.find_all(lambda x:x.name and x.name.split(':')[-1].lower() in ('explicitmember','typedmember'))]
   contexts[c.get('id')]=(instant.get_text(strip=True),dimensions)
 found=[]
 for f in soup.find_all(lambda x:x.name and 'nonfraction' in x.name.lower() and x.get('name','').endswith(':EntityCommonStockSharesOutstanding')):
  context=contexts.get(f.get('contextref'))
  if not context or context[1]:continue # do not sum economic share classes blindly
  token=f.get_text('',strip=True).replace(',','').replace(' ','')
  if not re.fullmatch(r'\d+(?:\.\d+)?',token):continue
  value=float(token)*10**int(f.get('scale','0'))
  if value>0:found.append({'value':value,'unit':'shares','start':None,'end':context[0],'tag':'EntityCommonStockSharesOutstanding','taxonomy':'dei'})
 found={r['end']:r for r in found}
 return sorted(found.values(),key=lambda r:r['end'])

def run(root,raw_dir,contact):
 now=datetime.now(timezone.utc);raw_dir.mkdir(parents=True,exist_ok=True)
 src_path=root/'reports/primary_evidence_91.json';src=json.loads(src_path.read_text())
 names={r['ticker']:r for r in __import__('csv').DictReader((root/'watchlist.csv').open())}
 adapters_path=root/'settings/primary_adapters_90.json';adapters=json.loads(adapters_path.read_text())
 notes=[];session=requests.Session();session.headers['User-Agent']=contact
 stopped=False
 for ticker,company in src['companies'].items():
  foreign=ticker in ADR_OR_OVERSEAS_SHARE_BASIS or names[ticker]['sector']=='International'
  if foreign: adapters.setdefault(ticker,{}).pop('share_basis',None)
  missing=not company.get('latest_share_count')
  if not foreign and not missing:continue
  result={'ticker':ticker,'orders_enabled':False};cik=company['cik']
  try:
   if stopped:result['status']='PROVIDER_COOLDOWN';notes.append(result);continue
   meta_path=raw_dir/f'{cik:010d}-submissions.json'
   if not meta_path.exists():
    r=session.get(f'https://data.sec.gov/submissions/CIK{cik:010d}.json',timeout=30)
    if r.status_code in (403,429):stopped=True;r.raise_for_status()
    r.raise_for_status();meta_path.write_text(r.text);time.sleep(.2)
   recent=json.loads(meta_path.read_text())['filings']['recent']
   indices=[i for i,f in enumerate(recent['form']) if f in ('10-K','10-Q','20-F','40-F')]
   # Annual cover identifies ADR terms; quarterly cover may repair recent shares.
   annual=[i for i in indices if recent['form'][i] in ('10-K','20-F','40-F')]
   chosen=annual[0] if foreign and annual else indices[0]
   acc=recent['accessionNumber'][chosen];date=recent['filingDate'][chosen]
   document=recent['primaryDocument'][chosen];url=f'https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace("-","")}/{document}'
   html_path=raw_dir/f'{ticker}-cover.html'
   if not html_path.exists():
    r=session.get(url,timeout=40)
    if r.status_code in (403,429):stopped=True;r.raise_for_status()
    r.raise_for_status();html_path.write_text(r.text);time.sleep(.2)
   html=html_path.read_text();sha=hashlib.sha256(html.encode()).hexdigest()
   shares=cover_shares(html)
   from share_classes_92 import REVIEWED_EQUAL_CLASSES,equal_class_counts
   if ticker in REVIEWED_EQUAL_CLASSES:
    reconciled=equal_class_counts(html,REVIEWED_EQUAL_CLASSES[ticker],now)
    if reconciled:shares=reconciled
   for s in shares:s['source_document_sha256']=sha
   for s in shares:s.update(filed=date,form=recent['form'][chosen],accession=acc,source_url=url)
   if shares:
    prior=company['annual_facts']['shares'];periods={r['end']:r for r in prior}
    periods.update({r['end']:r for r in shares});company['annual_facts']['shares']=sorted(periods.values(),key=lambda r:r['end'])[-20:]
    current=company.get('latest_share_count')
    if not current or shares[-1]['end']>current['end']:company['latest_share_count']=shares[-1]
    company['evidence_hash_sha256']=digest(company['annual_facts'])
   ratio,excerpt=cover_ratio(html,ticker)
   count=company.get('latest_share_count')
   if foreign and ratio and count:
    record={'issuer_name':company['issuer_name'],'source_url':url,'as_of':count['end'],'published_at':date,'accession':acc,'document_sha256':sha,
            'extraction_method':'INLINE_XBRL_CURRENT_SHARES_AND_EXPLICIT_REGISTERED_SECURITY_ROW', 'excerpt':excerpt,
            'facts':{'ticker':ticker,'quote_currency':'USD','ordinary_shares_per_receipt':ratio,'ordinary_shares_outstanding':count['value']}}
    adapters.setdefault(ticker,{})['share_basis']=primary_document(record)
    result.update(status='PRIMARY_LISTING_TERMS_EXTRACTED',ratio=ratio,source_url=url,shares_recovered=len(shares))
   else:result.update(status='PRIMARY_DOCUMENT_COLLECTED_REVIEW_REQUIRED',source_url=url,shares_recovered=len(shares),ratio=ratio)
  except (requests.RequestException,ValueError,IndexError,KeyError) as exc:result.update(status='PRIMARY_DOCUMENT_UNAVAILABLE',reason=str(exc)[:150])
  notes.append(result);write(src_path,src);write(adapters_path,adapters)
  write(root/'reports/share_basis_recovery_91.json',{'published_at_utc':now.isoformat(),'companies':notes,'orders_enabled':False})
 print(json.dumps({'documents_assessed':len(notes),'share_basis_records':len(adapters),'provider_blocked':stopped}))
 return notes
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path(__file__).resolve().parent);p.add_argument('--raw-dir',type=Path,default=Path('/tmp/championship91-documents'));p.add_argument('--only-if-due',action='store_true');a=p.parse_args()
 if a.only_if_due:
  cached=a.root/'reports/share_basis_recovery_91.json'
  if cached.exists():
   existing=json.loads(cached.read_text());stamp=datetime.fromisoformat(existing['published_at_utc'])
   if (datetime.now(timezone.utc)-stamp).days<7:
    print('Share-basis document refresh not yet due; preserving source dates');raise SystemExit(0)
 contact=os.environ.get('SEC_USER_AGENT','').strip()
 if '@' not in contact:
  if a.only_if_due:
   print('SEC_USER_AGENT contact is not configured; preserving dated share-basis evidence.');raise SystemExit(0)
  raise SystemExit('SEC_USER_AGENT contact required')
 run(a.root,a.raw_dir,contact)
