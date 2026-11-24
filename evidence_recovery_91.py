"""Collect issuer-filed facts for every fixed-universe company.

Fixes obsolete-tag truncation, reads IFRS and native currencies, aligns bank
balance-sheet dates with annual earnings. Never estimates missing financials.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
import requests
from championship_60 import finite, dt, FORM_TYPES, INSTANT_FORM_TYPES, combine_periods

VERSION='9.1-primary-fact-recovery-1'
CONCEPTS={
 'shares':[('dei','EntityCommonStockSharesOutstanding'),('us-gaap','CommonStockSharesOutstanding'),('ifrs-full','NumberOfSharesOutstanding')],
 'net_income':[('us-gaap','NetIncomeLossAvailableToCommonStockholdersBasic'),('us-gaap','NetIncomeLoss'),('us-gaap','ProfitLoss'),('ifrs-full','ProfitLossAttributableToOwnersOfParent'),('ifrs-full','ProfitLoss')],
 'revenue':[('us-gaap','RevenueFromContractWithCustomerExcludingAssessedTax'),('us-gaap','Revenues'),('us-gaap','SalesRevenueNet'),('us-gaap','RevenueFromContractWithCustomerIncludingAssessedTax'),('ifrs-full','Revenue')],
 'operating_cash_flow':[('us-gaap','NetCashProvidedByUsedInOperatingActivities'),('us-gaap','NetCashProvidedByUsedInOperatingActivitiesContinuingOperations'),('ifrs-full','CashFlowsFromUsedInOperatingActivities')],
 'capex':[('us-gaap','PaymentsToAcquirePropertyPlantAndEquipment'),('us-gaap','PaymentsToAcquireProductiveAssets'),('ifrs-full','PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities'),('ifrs-full','PurchaseOfPropertyPlantAndEquipmentIntangibleAssetsOtherThanGoodwillInvestmentPropertyAndOtherNoncurrentAssets'),('ifrs-full','PurchaseOfPropertyPlantAndEquipment'),('ifrs-full','PaymentsToAcquirePropertyPlantAndEquipment')],
 'equity':[('us-gaap','StockholdersEquity'),('ifrs-full','EquityAttributableToOwnersOfParent'),('ifrs-full','Equity')],
 'assets':[('us-gaap','Assets'),('ifrs-full','Assets')],
 'liabilities':[('us-gaap','Liabilities'),('ifrs-full','Liabilities')]
}

def digest(data):return hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
def write(path, data):
 path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')

# Reviewed against Lilly's annual cash-flow row 'Purchases of property and equipment'.
ISSUER_EXTRA_CONCEPTS={'LLY':{'capex':[('us-gaap','PaymentsToAcquireOtherPropertyPlantAndEquipment')]}}

def candidates(raw, kind, now, extra=()):
 out=[];annual=kind in ('net_income','revenue','operating_cash_flow','capex')
 for preference,(taxonomy,tag) in enumerate(CONCEPTS[kind]+list(extra)):
  units=raw.get('facts',{}).get(taxonomy,{}).get(tag,{}).get('units',{})
  for unit,records in units.items():
   if (kind=='shares' and unit!='shares') or (kind!='shares' and not re.fullmatch('[A-Z]{3}',unit)):continue
   for r in records:
    start,end,filed=dt(r.get('start')),dt(r.get('end')),dt(r.get('filed'));value=finite(r.get('val'))
    if value is None or not end or not filed or end>now.date() or filed>now.date() or not r.get('accn'):continue
    if (now.date()-end).days>4200:continue
    if r.get('form') not in (FORM_TYPES if annual else INSTANT_FORM_TYPES):continue
    if annual and (not start or not 330<=(end-start).days<=385):continue
    if not annual and start:continue
    if kind=='shares' and value<=0:continue
    if kind=='capex' and value<0:continue  # never silently reverse statement signs
    out.append({'value':value,'unit':unit,'start':str(start) if start else None,'end':str(end),
                'filed':str(filed),'accession':r['accn'],'form':r['form'],'taxonomy':taxonomy,'tag':tag,'concept_preference':preference})
 return out

def select(records, currency=None):
 """Choose a compatible concept per fiscal period; never stop at an old tag.
 Latest filing wins within the preferred available concept for each period.
 """
 out={}
 for r in records:
  if currency and r['unit']!=currency:continue
  key=(r['start'],r['end'],r['unit'])
  prior=out.get(key)
  # Prefer equity attributable to common/parent over consolidated total equity.
  if prior is None or (-r['concept_preference'],r['filed'],r['accession'])>(-prior['concept_preference'],prior['filed'],prior['accession']):out[key]=r
 return sorted(out.values(),key=lambda r:(r['end'],r['filed']))

def recover_series(ticker,raw,now,cik):
 if int(raw.get('cik',0))!=int(cik) or not raw.get('entityName'):raise ValueError('CIK/issuer mismatch')
 all_records={k:candidates(raw,k,now,ISSUER_EXTRA_CONCEPTS.get(ticker,{}).get(k,())) for k in CONCEPTS}
 income=select(all_records['net_income'])
 newest=max(income,key=lambda r:r['end']) if income else None
 currency=newest['unit'] if newest else None
 series={k:select(v,currency if k!='shares' else None) for k,v in all_records.items()}
 # OCF and CAPEX must refer to the same fiscal interval AND filed document.
 # Select both jointly before deduplication, retaining latest common accession.
 cash={}
 for k in ('operating_cash_flow','capex'):
  by={}
  for r in all_records[k]:
   if r['unit']==currency:
    key=(r['start'],r['end'],r['accession'])
    if key not in by or r['concept_preference']<by[key]['concept_preference']:by[key]=r
  cash[k]=by
 pairs={}
 for key in cash['operating_cash_flow'].keys()&cash['capex'].keys():
  o,c=cash['operating_cash_flow'][key],cash['capex'][key]
  period=key[:2]
  if period not in pairs or (o['filed'],o['accession'])>(pairs[period][0]['filed'],pairs[period][0]['accession']):pairs[period]=(o,c)
 for idx,k in enumerate(('operating_cash_flow','capex')):
  series[k]=[pairs[key][idx] for key in sorted(pairs,key=lambda z:z[1])]
 # Banks need comparable annual equity, not the last two quarterly instants.
 annual_ends={r['end'] for r in series['net_income']}
 series['equity']=[r for r in series['equity'] if r['end'] in annual_ends]
 shares=[r for r in series['shares'] if 0<=(now.date()-dt(r['end'])).days<=500]
 latest=shares[-1] if shares else None
 series={k:v[-12:] if k!='shares' else v[-20:] for k,v in series.items()}
 return {'ticker':ticker,'issuer_name':raw['entityName'],'cik':int(cik),'source_url':f'https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json',
         'observed_utc':now.isoformat(),'status':'OFFICIAL_SEC_COMPANYFACTS_RETRIEVED','primary_source_type':'ISSUER_XBRL_SEC',
         'latest_share_count':latest,'annual_facts':series,'financial_currency':currency,
         'evidence_hash_sha256':digest(series),'raw_document_sha256':digest(raw),'extraction_version':VERSION,
         'coverage':{k:len(v) for k,v in series.items()},'orders_enabled':False}

def collect(root, raw_dir, contact, force=False, limit=None):
 now=datetime.now(timezone.utc);raw_dir.mkdir(parents=True,exist_ok=True)
 names=list(csv.DictReader((root/'watchlist.csv').open(encoding='utf-8-sig')))
 assert len(names)==200 and len({r['ticker'] for r in names})==200
 old_path=root/'reports/primary_evidence_91.json'; old=json.loads(old_path.read_text()) if old_path.exists() else {}
 companies=old.get('companies',{}).copy();assessments=[]
 session=requests.Session();session.headers.update({'User-Agent':contact,'Accept':'application/json'})
 directory=session.get('https://www.sec.gov/files/company_tickers_exchange.json',timeout=30)
 directory.raise_for_status();d=directory.json();fields=d['fields']
 listed={str(r[fields.index('ticker')]).upper():int(r[fields.index('cik')]) for r in d['data']}
 # ASX dual-listed issuers: SEC ticker is resolved from the official directory.
 aliases={'BHP.AX':'BHP','RIO.AX':'RIO','WDS.AX':'WDS','RMD.AX':'RMD'}
 attempted=0;blocked=False
 for meta in names:
  ticker=meta['ticker'];symbol=aliases.get(ticker,ticker);cik=listed.get(symbol)
  row={'ticker':ticker,'original_universe':True,'cik':cik,'orders_enabled':False}
  if not cik:
   row.update(status='NON_SEC_PRIMARY_FILING_REQUIRED',reason='No exact ticker or reviewed dual-listing alias in official SEC directory; ASX/issuer annual report collection required')
  elif blocked:
   row.update(status='PROVIDER_COOLDOWN_NOT_ATTEMPTED')
  else:
   local=raw_dir/f'{cik:010d}.json'
   try:
    if not local.exists() or force:
     if limit is not None and attempted>=limit:
      row['status']='BOUNDED_RUN_LIMIT';assessments.append(row);continue
     attempted+=1
     r=session.get(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json',timeout=30)
     if r.status_code in (403,429):
      row['status']=f'SEC_HTTP_{r.status_code}';blocked=True;assessments.append(row);continue
     r.raise_for_status();local.write_text(r.text);time.sleep(.2)
    raw=json.loads(local.read_text());rec=recover_series(ticker,raw,now,cik)
    overlay=root/'reports/reviewed_cashflow_92.json'
    if overlay.exists():
     from reviewed_cashflow_92 import apply_reviewed_overlay
     rec=apply_reviewed_overlay(rec,json.loads(overlay.read_text()))
    companies[ticker]=rec
    row.update(status='PRIMARY_FACTS_RECOVERED',currency=rec['financial_currency'],annual_fcf_periods=sum(x['fcf'] is not None for x in combine_periods(rec)),current_shares=bool(rec['latest_share_count']),source_url=rec['source_url'])
   except (requests.RequestException,ValueError,KeyError) as exc:
    row.update(status='PRIMARY_FETCH_OR_PARSE_FAILED',error=str(exc)[:160])
  assessments.append(row)
  out={'schema_version':VERSION,'published_at_utc':now.isoformat(),'original_200_count':200,'companies':companies,'company_assessments':assessments,'orders_enabled':False,'orders_generated':0}
  write(old_path,out) # recoverable checkpoints, no fabricated successful status
 out['all_200_attempt_status_recorded']=len(assessments)==200
 out['http_requests']=attempted
 write(old_path,out)
 print(json.dumps({'assessed':len(assessments),'recovered':len(companies),'requests':attempted,'provider_blocked':blocked}))
 return out
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path(__file__).resolve().parent);p.add_argument('--raw-dir',type=Path,default=Path('/tmp/championship91-raw'));p.add_argument('--force',action='store_true');p.add_argument('--limit',type=int);p.add_argument('--only-if-due',action='store_true')
 a=p.parse_args()
 if a.only_if_due:
  cached=a.root/'reports/primary_evidence_91.json'
  if cached.exists():
   existing=json.loads(cached.read_text());stamp=datetime.fromisoformat(existing['published_at_utc'])
   if existing.get('schema_version')==VERSION and (datetime.now(timezone.utc)-stamp).days<7:
    print('Verified issuer evidence refresh not yet due; preserving original source dates');raise SystemExit(0)
 contact=os.environ.get('SEC_USER_AGENT','').strip()
 if '@' not in contact:
  if a.only_if_due:
   print('SEC_USER_AGENT contact is not configured; keeping dated evidence unchanged. Staleness gates still apply.');raise SystemExit(0)
  raise SystemExit('SEC_USER_AGENT must identify a contact for issuer filing requests')
 collect(a.root,a.raw_dir,contact,a.force,a.limit)
