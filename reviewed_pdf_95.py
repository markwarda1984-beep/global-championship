"""Reproducible reviewed PDF adapters; changed documents require new review."""
import hashlib,json,re,tempfile,copy
from pathlib import Path
from datetime import datetime,timezone,timedelta,date
import fitz
from pdf_rows_dynamic_92 import rows
from evidence_recovery_91 import digest

def amount(token):
 if token in ('-','–','—'):return 0.
 value=float(token.replace(',','').strip('()'))
 return -value if token.startswith('(') else value

def parse(body,spec,now):
 sha=hashlib.sha256(body).hexdigest()
 if sha!=spec['sha256']:raise ValueError('Changed primary document requires review')
 with tempfile.TemporaryDirectory() as folder:
  (Path(folder)/(sha+'.raw')).write_bytes(body);doc=fitz.open(stream=body,filetype='pdf');years=spec['years'];out={k:[] for k in ['net_income','revenue','operating_cash_flow','capex','shares']}
  def table(page):
   rect=doc[page-1].rect;clip=(0,0,rect.width/2,rect.height) if rect.width>900 else None
   found=rows(sha,page,years,folder,clip)
   if not found:raise ValueError('Reviewed financial year columns not found')
   return found
  income=table(spec['income_page']);cash=table(spec['cash_page'])
  def selected(records,pattern,first=False):
   matches=[r for r in records if re.fullmatch(pattern,r['label'],re.I)]
   if not matches or (len(matches)!=1 and not first):raise ValueError('Missing or ambiguous source row: '+pattern)
   return matches[0]
  def fact(metric,year,raw,label,page,scale=1000000):
   end=spec['period_ends'][str(year)];prior=date.fromisoformat(end)-timedelta(weeks=spec.get('weeks',{}).get(str(year),52))+timedelta(days=1) if spec['retail_calendar'] else date(year-1,7,1)
   return {'metric':metric,'value':amount(raw)*scale,'unit':'shares' if metric=='shares' else 'AUD','currency':None if metric=='shares' else 'AUD','start':None if metric=='shares' else prior.isoformat(),'end':end,'period_start':None if metric=='shares' else prior.isoformat(),'period_end':end,'period_type':'INSTANT' if metric=='shares' else 'ANNUAL','filed':spec['published_at'],'filed_date_basis':'ISSUER_REPORT_AUTHORIZATION_DATE','source_url':spec['url'],'source_document_sha256':sha,'source_row':label,'source_literal':raw,'pdf_page':page,'scale_to_units':scale,'accession':'ISSUER-PDF-'+sha[:20],'form':'ISSUER_ANNUAL_REPORT','tag':label,'taxonomy':'ISSUER_AASB_TABLE','accounting_basis':'AASB_IFRS','is_management_forecast':False}
  for year in years:
   for metric,pattern in [('net_income',spec['income_label']),('revenue',spec['revenue_label'])]:
    r=selected(income,pattern,first=metric=='net_income' and spec.get('first_income_occurrence',False));out[metric].append(fact(metric,year,r['values'][str(year)],r['label'],spec['income_page']))
   r=selected(cash,spec['ocf_label']);out['operating_cash_flow'].append(fact('operating_cash_flow',year,r['values'][str(year)],r['label'],spec['cash_page']))
   components=[]
   for pattern in spec['cash_outflow_labels']:
    r=selected(cash,pattern);f=fact('capex_component',year,r['values'][str(year)],r['label'],spec['cash_page'])
    if f['value']>0:raise ValueError('Expected explicit cash outflow sign')
    f['value']=abs(f['value']);components.append(f)
   out['capex'].append({**components[0],'metric':'capex','value':sum(f['value'] for f in components),'tag':'PPE_INTANGIBLES_LEASES_AND_FINANCING_INTEREST_AS_DISCLOSED','components':components})
  if spec.get('shares_page'):
   text=' '.join(doc[spec['shares_page']-1].get_text().split());mode=spec['shares_mode']
   if mode in ('WOW_NET_ROUNDED','COL_NET_ROUNDED'):
    label='Contributed equity at end of period' if mode.startswith('WOW') else 'Total contributed equity';m=re.search(re.escape(label)+r'\s+([\d,.]+)\s+[\d,.]+\s+([\d,.]+)\s+[\d,.]+',text)
    if not m:raise ValueError('Net ordinary-share count row missing')
    counts=[m[1],m[2]];scale=1000000
   else:
    issued=re.search(r'As at 30 June 2026, there were ([\d,]+) \(2025: ([\d,]+)\)',text);trust=re.search(r'number of shares held by employee share plans totalled ([\d,]+) \(2025: ([\d,]+)\)',text)
    if not issued or not trust:raise ValueError('Issued and treasury counts must both be disclosed')
    counts=[str(int(issued[i].replace(',',''))-int(trust[i].replace(',',''))) for i in (1,2)];scale=1;label='Issued ordinary shares less explicitly disclosed consolidated employee-trust shares'
   for year,count in zip(years,counts):
    f=fact('shares',year,count,label,spec['shares_page'],scale);f['share_precision']='SOURCE_ROUNDED_0.1_MILLION' if scale==1000000 else 'EXACT_DISCLOSED_COUNTS';out['shares'].append(f)
  doc.close();return out

def merge_record(ticker,existing,parsed,now):
 facts=copy.deepcopy(existing.get('annual_facts',{}))
 for metric,items in parsed.items():
  old={(r.get('start'),r['end']):r for r in facts.get(metric,[])};old.update({(r.get('start'),r['end']):r for r in items});facts[metric]=sorted(old.values(),key=lambda r:r['end'])
 shares=facts.get('shares',[]);latest=shares[-1] if shares else None
 return {'ticker':ticker,'issuer_name':{'WOW.AX':'Woolworths Group Limited','COL.AX':'Coles Group Limited','TLS.AX':'Telstra Group Limited'}[ticker],'financial_currency':'AUD','status':'ISSUER_ANNUAL_REPORT_FIELDS_RECONCILED','review_status':'PRIMARY_DOCUMENT_FIELDS_RECONCILED','source_url':(facts.get('net_income') or [{}])[-1].get('source_url'),'observed_utc':now.isoformat(),'annual_facts':facts,'latest_share_count':latest,'evidence_hash_sha256':digest(facts),'orders_enabled':False,'extraction_version':'9.5_REVIEWED_ROTATION_AND_COLUMN_AWARE_PDF','cash_flow_scope':'Conservative operating cash less explicitly disclosed PPE, intangibles, lease principal and any finance costs paid in financing; no missing amount assumed zero.'}

def collect_one(root,ticker,fetcher,now):
 cfg=json.loads((root/'settings/reviewed_pdf_95.json').read_text()) if (root/'settings/reviewed_pdf_95.json').exists() else {}
 specs=cfg.get('companies',{}).get(ticker)
 if not specs:return None
 report_path=root/'reports/issuer_primary_records_95.json';report=json.loads(report_path.read_text()) if report_path.exists() else {'companies':{},'orders_enabled':False};state=report.setdefault('source_checks',{})
 spec=min(specs,key=lambda s:state.get(s['sha256'],{}).get('checked_at_utc',''))
 body,sha=fetcher.get_bytes(spec['url'],max_bytes=80_000_000);parsed=parse(body,spec,now);report['companies'][ticker]=merge_record(ticker,report['companies'].get(ticker,{}),parsed,now);state[sha]={'checked_at_utc':now.isoformat(),'source_url':spec['url'],'sha256':sha}
 from background_research_93 import write
 write(report_path,report)
 return {'sources':[{'url':spec['url'],'sha256':sha}],'parsed_observations':sum(len(v) for v in parsed.values()),'research_status':'REVIEWED_PRIMARY_PDF_ADAPTER_APPLIED'}
