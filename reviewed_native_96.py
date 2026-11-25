"""Verified native-currency inline XBRL supplements where API ingestion lags."""
import copy,hashlib,json,re
from datetime import datetime
from bs4 import BeautifulSoup
from evidence_recovery_91 import digest
RULES={'TSM':{'cik':1046179,'currency':'TWD','income':'ifrs-full:ProfitLossAttributableToOwnersOfParent','ocf':'ifrs-full:CashFlowsFromUsedInOperatingActivities','capex_components':['ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities','ifrs-full:PurchaseOfIntangibleAssetsClassifiedAsInvestingActivities','ifrs-full:PaymentsOfLeaseLiabilitiesClassifiedAsFinancingActivities','ifrs-full:InterestPaidClassifiedAsFinancingActivities']},
'PDD':{'cik':1737806,'currency':'CNY','income':'us-gaap:NetIncomeLossAvailableToCommonStockholdersBasic','ocf':'us-gaap:NetCashProvidedByUsedInOperatingActivities','capex_components':['pdd:PaymentsToAcquirePropertyEquipmentAndSoftwareAndIntangibleAssets']}}

def extract(html,ticker,meta,now):
 rule=RULES.get(ticker)
 if not rule or not meta['url'].startswith(f"https://www.sec.gov/Archives/edgar/data/{rule['cik']}/") or meta['filed']>now.date().isoformat():return {}
 soup=BeautifulSoup(html,'html.parser');contexts={};units={}
 for u in soup.find_all(lambda x:x.name and x.name.split(':')[-1].lower()=='unit'):units[u.get('id')]=u.get_text('',strip=True)
 for c in soup.find_all(lambda x:x.name and x.name.split(':')[-1].lower()=='context'):
  if c.find(lambda x:x.name and x.name.split(':')[-1].lower() in ('explicitmember','typedmember')):continue
  identifier=c.find(lambda x:x.name and x.name.split(':')[-1].lower()=='identifier')
  try:
   if not identifier or int(identifier.get_text(strip=True))!=rule['cik']:continue
  except ValueError:continue
  start=c.find(lambda x:x.name and x.name.split(':')[-1].lower()=='startdate');end=c.find(lambda x:x.name and x.name.split(':')[-1].lower()=='enddate')
  if not start or not end:continue
  start,end=start.get_text(strip=True),end.get_text(strip=True)
  if end>now.date().isoformat() or not 330<=(datetime.fromisoformat(end)-datetime.fromisoformat(start)).days<=385:continue
  contexts[c.get('id')]=(start,end)
 tags={rule['income'],rule['ocf'],*rule['capex_components']};values={};conflicts=set();sha=hashlib.sha256(html.encode()).hexdigest()
 for f in soup.find_all(lambda x:x.name and 'nonfraction' in x.name.lower()):
  tag=f.get('name');ctx=contexts.get(f.get('contextref'))
  if tag not in tags or not ctx or units.get(f.get('unitref')) not in (rule['currency'],'iso4217:'+rule['currency']):continue
  token=f.get_text('',strip=True).replace(',','').replace(' ','')
  if not re.fullmatch(r'\d+(?:\.\d+)?',token):continue
  value=float(token)*10**int(f.get('scale','0'))*(-1 if f.get('sign')=='-' else 1);key=(*ctx,tag)
  if key in values and values[key]['value']!=value:conflicts.add(ctx)
  values[key]={'value':value,'unit':rule['currency'],'start':ctx[0],'end':ctx[1],'filed':meta['filed'],'accession':meta['accession'],'form':meta.get('form','20-F'),'tag':tag.split(':')[-1],'taxonomy':tag.split(':')[0],'source_url':meta['url'],'source_document_sha256':sha,'source_literal':token,'scale_to_units':10**int(f.get('scale','0'))}
 out={k:[] for k in ('net_income','operating_cash_flow','capex')}
 for ctx in sorted(set(k[:2] for k in values)):
  if ctx in conflicts or any((*ctx,tag) not in values for tag in tags):continue
  components=[values[(*ctx,t)] for t in rule['capex_components']]
  if any(c['value']<0 for c in components):continue
  out['net_income'].append(values[(*ctx,rule['income'])]);out['operating_cash_flow'].append(values[(*ctx,rule['ocf'])]);out['capex'].append({**components[0],'value':sum(c['value'] for c in components),'tag':'REVIEWED_NATIVE_CAPITAL_CASH_OUTFLOWS','components':components})
 return out

def apply(company,report):
 if report and report.get('orders_enabled') is not False:raise ValueError('Unsafe native evidence')
 ticker=company.get('ticker');entry=report.get('companies',{}).get(ticker)
 if not entry or ticker not in RULES or int(company.get('cik',0))!=RULES[ticker]['cik']:return company
 facts=entry.get('annual_facts',{})
 if entry.get('review_status')!='PRIMARY_DOCUMENT_FIELDS_RECONCILED' or entry.get('facts_sha256')!=digest(facts):return company
 out=copy.deepcopy(company)
 for metric,rows in facts.items():
  if metric not in ('net_income','operating_cash_flow','capex'):continue
  previous={(r['start'],r['end'],r['unit']):r for r in out['annual_facts'].get(metric,[])}
  for r in rows:
   if r['unit']!=RULES[ticker]['currency'] or not re.fullmatch('[0-9a-f]{64}',r.get('source_document_sha256','')):raise ValueError('Native statement provenance mismatch')
   key=(r['start'],r['end'],r['unit']);old=previous.get(key)
   if old is None or r['filed']>=old.get('filed',''):previous[key]=r
  out['annual_facts'][metric]=sorted(previous.values(),key=lambda r:r['end'])[-12:]
 out['evidence_hash_sha256']=digest(out['annual_facts']);return out

def api_cash_supplement(ticker,raw,now):
 """Normalize all disclosed TSM years to the same conservative cash definition."""
 if ticker!='TSM' or int(raw.get('cik',0))!=1046179:return {'operating_cash_flow':[],'capex':[]}
 from evidence_recovery_91 import candidates
 rule=RULES[ticker];parts=[]
 for tag in rule['capex_components']:
  taxonomy,concept=tag.split(':');rr=candidates(raw,'capex',now,[(taxonomy,concept)])
  parts.append({(r['start'],r['end'],r['accession']):r for r in rr if r['unit']=='TWD' and r['taxonomy']==taxonomy and r['tag']==concept})
 operating={(r['start'],r['end'],r['accession']):r for r in candidates(raw,'operating_cash_flow',now) if r['unit']=='TWD'}
 common=set(operating)
 for p in parts:common&=p.keys()
 out={'operating_cash_flow':[],'capex':[]};sha=digest(raw);url='https://data.sec.gov/api/xbrl/companyfacts/CIK0001046179.json'
 for key in sorted(common):
  provenance={'source_document_sha256':sha,'source_hash_basis':'CANONICAL_SEC_JSON','source_url':url};components=[{**p[key],**provenance} for p in parts]
  o={**operating[key],**provenance};out['operating_cash_flow'].append(o);out['capex'].append({**components[0],'value':sum(r['value'] for r in components),'tag':'REVIEWED_NATIVE_CAPITAL_CASH_OUTFLOWS','components':components})
 return out

def dynamic_record(ticker,entry,observed_utc):
 """Keep reported PPE separate from the extra owner-cash deductions."""
 metrics={}
 for metric,rows in entry['annual_facts'].items():
  for row in rows:
   parts=[(metric,row)]
   if metric=='capex' and ticker=='TSM':
    components=row.get('components',[])
    if len(components)!=4:continue
    parts=list(zip(['capex','capitalized_intangibles','lease_principal','financing_interest_paid'],components))
   for name,f in parts:
    metrics.setdefault(name,[]).append({**f,'metric':name,'currency':f['unit'],'period_start':f['start'],'period_end':f['end'],'period_type':'ANNUAL','accounting_basis':'IFRS' if ticker=='TSM' else 'US_GAAP','is_management_forecast':False})
 return {'ticker':ticker,'metrics':metrics,'facts_sha256':digest(metrics),'observed_utc':observed_utc,'orders_enabled':False,'owner_cashflow_components_reviewed':ticker=='TSM','owner_cashflow_required_components':['capitalized_intangibles','lease_principal','financing_interest_paid'] if ticker=='TSM' else []}
