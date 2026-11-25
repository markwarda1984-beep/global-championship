"""ICICI's issuer-filed U.S.-GAAP reconciliations; never mix Indian GAAP equity."""
import copy,hashlib,json,re
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from bs4 import BeautifulSoup
from evidence_recovery_91 import digest

CIK=1103838
LABELS={'net_income':'Net income as per U.S. GAAP attributable to ICICI Bank stockholders','equity':'ICICI Bank stockholders\' equity as per U.S. GAAP'}
def plain(x):return ' '.join(x.get_text(' ',strip=True).split()).replace('’',"'")

def parse(html,meta):
 if not meta['url'].startswith('https://www.sec.gov/Archives/edgar/data/1103838/'):raise ValueError('Bank issuer URL mismatch')
 soup=BeautifulSoup(html,'html.parser');text=plain(soup);year_match=re.search(r'fiscal year ended March 31, (20\d\d)',text,re.I)
 if not year_match or 'ICICI Bank Limited' not in text:raise ValueError('Bank fiscal period or identity not confirmed')
 year=int(year_match[1]);sha=hashlib.sha256(html.encode()).hexdigest();out={k:[] for k in ['net_income','equity','shares']}
 def fact(metric,value,end,label,index,scale=1000000):
  return {'value':value*scale,'unit':'shares' if metric=='shares' else 'INR','start':None if metric in ('shares','equity') else f'{int(end[:4])-1}-04-01','end':end,'filed':meta['filed'],'accession':meta['accession'],'form':'20-F','source_url':meta['url'],'source_document_sha256':sha,'html_row_index':index,'source_row':label,'source_scale':scale,'accounting_basis':'US_GAAP_RECONCILED_FROM_INDIAN_GAAP','tag':label,'taxonomy':'ISSUER_RECONCILED_TABLE'}
 rows=soup.find_all('tr')
 for metric,label in LABELS.items():
  matches=[(i,r) for i,r in enumerate(rows,1) if plain(r).startswith(label)]
  if len(matches)!=1:raise ValueError('Missing or ambiguous bank reconciliation row')
  index,row=matches[0];table_text=plain(row.find_parent('table'))
  if not table_text.startswith('Rupees in million'):raise ValueError('Bank reconciliation scale not verified')
  expected=3 if metric=='net_income' else 2
  headings=[int(y) for y in re.findall(r'\b20\d\d\b',table_text[:180])]
  if headings!=list(range(year,year-expected,-1)):raise ValueError('Bank reconciliation year columns not confirmed')
  amounts=re.findall(r'\(?-?\d[\d,]*\.\d+\)?',plain(row)[len(label):])
  if len(amounts)!=expected:raise ValueError('Unexpected bank value columns')
  for y,token in zip(headings,amounts):
   value=float(token.replace(',','').strip('()'))*(-1 if token.startswith('(') else 1)
   out[metric].append(fact(metric,value,f'{y}-03-31',label,index))
 shares=re.search(r'number of outstanding Equity Shares of ICICI Bank Limited as of March 31, '+str(year)+r' was ([\d,]+)',text,re.I)
 if not shares:raise ValueError('Dated ordinary-share count missing')
 out['shares'].append(fact('shares',int(shares[1].replace(',','')),f'{year}-03-31',shares[0],None,1))
 midyear=re.search(r'At June 30, '+str(year)+r', total ([\d,]+) equity shares were outstanding',text)
 if midyear:out['shares'].append(fact('shares',int(midyear[1].replace(',','')),f'{year}-06-30',midyear[0],None,1))
 excerpt='American Depositary Shares, each representing two Equity Shares of ICICI Bank Limited'
 if excerpt not in text:raise ValueError('Primary 2:1 receipt basis missing')
 latest=max(out['shares'],key=lambda r:r['end']);facts={'ticker':'IBN','quote_currency':'USD','ordinary_shares_per_receipt':2,'ordinary_shares_outstanding':latest['value']}
 basis={'issuer':'ICICI Bank Limited','source_url':meta['url'],'source_document_sha256':sha,'as_of':latest['end'],'published_at':meta['filed'],'accession_or_document_id':meta['accession'],'review_status':'PRIMARY_DOCUMENT_FIELDS_RECONCILED','facts':facts,'facts_sha256':digest(facts),'source_excerpt':excerpt}
 return out,basis

def assemble(documents,observed_utc):
 facts={'net_income':[],'equity':[],'shares':[]};basis=None
 for html,meta in sorted(documents,key=lambda item:item[1]['filed']):
  incoming,b=parse(html,meta)
  for key,values in incoming.items():
   old={(r['start'],r['end']):r for r in facts[key]};old.update({(r['start'],r['end']):r for r in values});facts[key]=sorted(old.values(),key=lambda r:r['end'])
  if not basis or b['as_of']>basis['as_of']:basis=b
 record={'ticker':'IBN','issuer_name':'ICICI Bank Limited','cik':CIK,'financial_currency':'INR','source_url':basis['source_url'],'observed_utc':observed_utc,'annual_facts':facts,'latest_share_count':facts['shares'][-1],'evidence_hash_sha256':digest(facts),'status':'ISSUER_ANNUAL_REPORT_FIELDS_RECONCILED','review_status':'PRIMARY_DOCUMENT_FIELDS_RECONCILED','extraction_version':'9.6_ICICI_REVIEWED_US_GAAP_RECONCILIATION','orders_enabled':False}
 return record,basis

def verified(record,now):
 if record.get('ticker')!='IBN' or record.get('cik')!=CIK or record.get('extraction_version')!='9.6_ICICI_REVIEWED_US_GAAP_RECONCILIATION':return False
 facts=record.get('annual_facts',{})
 if record.get('evidence_hash_sha256')!=digest(facts) or record.get('orders_enabled') is not False:return False
 for key,values in facts.items():
  for r in values:
   if r['unit']!=('shares' if key=='shares' else 'INR') or not r['source_url'].startswith('https://www.sec.gov/Archives/edgar/data/1103838/') or not re.fullmatch('[0-9a-f]{64}',r['source_document_sha256']) or r['filed']>now.date().isoformat() or (not r.get('html_row_index') and key!='shares'):return False
   if key=='shares' and not re.search(r'(March 31|June 30), '+r['end'][:4],r.get('source_row','')):return False
 return bool(facts.get('net_income') and facts.get('equity') and facts.get('shares'))

def collect(root,fetcher,now):
 text,_=fetcher.get('https://data.sec.gov/submissions/CIK0001103838.json');meta=json.loads(text)
 if int(meta.get('cik',0))!=CIK or 'IBN' not in meta.get('tickers',[]):raise ValueError('Bank submissions identity mismatch')
 recent=meta['filings']['recent'];annual=[i for i,f in enumerate(recent['form']) if f=='20-F'][:3];docs=[];sources=[]
 for idx in annual:
  acc=recent['accessionNumber'][idx];path=recent['primaryDocument'][idx]
  if '..' in path or path.startswith('/'):raise ValueError('Invalid issuer document path')
  url=f'https://www.sec.gov/Archives/edgar/data/{CIK}/{acc.replace("-","")}/{quote(path,safe="/")}'
  html,sha=fetcher.get(url);document={'url':url,'filed':recent['filingDate'][idx],'accession':acc,'form':'20-F'};docs.append((html,document));sources.append({'url':url,'sha256':sha})
 rec,basis=assemble(docs,now.isoformat());p=root/'reports/reviewed_bank_96.json';data={'companies':{'IBN':rec},'adapters':{'IBN':{'share_basis':basis}},'orders_enabled':False,'orders_generated':0}
 from background_research_93 import write
 write(p,data)
 return {'sources':sources,'parsed_observations':sum(len(v) for v in rec['annual_facts'].values()),'research_status':'REVIEWED_ISSUER_US_GAAP_BANK_RECONCILIATION_APPLIED'}
