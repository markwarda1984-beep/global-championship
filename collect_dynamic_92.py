"""Primary annual/quarterly/instant financial observations for Dynamic Earnings 9.2.
A source observation is never promoted into a valuation merely because it downloaded.
"""
from __future__ import annotations
import argparse,gzip,hashlib,json,math,os,re,time,threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from pathlib import Path
import requests
from evidence_recovery_91 import write,digest

PUBLIC_CONTACT='ChampionshipResearch https://github.com/markwarda1984-beep/global-championship'
METRICS={
 'revenue':[('us-gaap','RevenueFromContractWithCustomerExcludingAssessedTax'),('us-gaap','Revenues'),('us-gaap','SalesRevenueNet'),('ifrs-full','Revenue')],
 'net_income':[('us-gaap','NetIncomeLossAvailableToCommonStockholdersBasic'),('us-gaap','NetIncomeLoss'),('us-gaap','ProfitLoss'),('ifrs-full','ProfitLossAttributableToOwnersOfParent'),('ifrs-full','ProfitLoss')],
 'eps_diluted':[('us-gaap','EarningsPerShareDiluted'),('ifrs-full','DilutedEarningsLossPerShare')],
 'eps_basic':[('us-gaap','EarningsPerShareBasic'),('ifrs-full','BasicEarningsLossPerShare')],
 'diluted_weighted_shares':[('us-gaap','WeightedAverageNumberOfDilutedSharesOutstanding'),('ifrs-full','AdjustedWeightedAverageShares')],
 'issued_shares':[('dei','EntityCommonStockSharesOutstanding'),('us-gaap','CommonStockSharesOutstanding'),('ifrs-full','NumberOfSharesOutstanding')],
 'operating_cash_flow':[('us-gaap','NetCashProvidedByUsedInOperatingActivities'),('ifrs-full','CashFlowsFromUsedInOperatingActivities')],
 'capex':[('us-gaap','PaymentsToAcquirePropertyPlantAndEquipment'),('us-gaap','PaymentsToAcquireProductiveAssets'),('ifrs-full','PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities')],
 'cash':[('us-gaap','CashAndCashEquivalentsAtCarryingValue'),('ifrs-full','CashAndCashEquivalents')],
 'debt_current':[('us-gaap','DebtCurrent'),('us-gaap','LongTermDebtCurrent'),('ifrs-full','CurrentBorrowings')],
 'debt_noncurrent':[('us-gaap','LongTermDebtNoncurrent'),('us-gaap','LongTermDebt'),('ifrs-full','NoncurrentBorrowings')],
 'equity':[('us-gaap','StockholdersEquity'),('ifrs-full','EquityAttributableToOwnersOfParent'),('ifrs-full','Equity')],
 'assets':[('us-gaap','Assets'),('ifrs-full','Assets')],
 'tax_expense':[('us-gaap','IncomeTaxExpenseBenefit'),('ifrs-full','IncomeTaxExpenseContinuingOperations')],
 'pretax_profit':[('us-gaap','IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest'),('us-gaap','IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments'),('ifrs-full','ProfitLossBeforeTax')],
 'acquisition_cash_paid':[('us-gaap','PaymentsToAcquireBusinessesNetOfCashAcquired'),('ifrs-full','CashFlowsUsedInObtainingControlOfSubsidiariesOrOtherBusinesses')],
 'stock_based_compensation':[('us-gaap','ShareBasedCompensation')],
 'goodwill_impairment':[('us-gaap','GoodwillImpairmentLoss'),('ifrs-full','ImpairmentLossRecognisedInProfitOrLossGoodwill')],
 'intangibles_amortization':[('us-gaap','AmortizationOfIntangibleAssets'),('ifrs-full','AmortisationExpense')]
}
INSTANT={'issued_shares','cash','debt_current','debt_noncurrent','equity','assets'}
def date(value):
 try:return datetime.fromisoformat(value).date()
 except (ValueError,TypeError):return None
def finite(value):return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)
def period_type(start,end):
 if not start:return 'INSTANT'
 days=(end-start).days
 if 75<=days<=105:return 'QUARTER'
 if 150<=days<=210:return 'HALF_YEAR_OR_YTD'
 if 240<=days<=310:return 'NINE_MONTH_YTD'
 if 330<=days<=385:return 'ANNUAL'
 return None

def extract(raw,ticker,now,source_url,observed_utc):
 observations={k:[] for k in METRICS}
 for metric,concepts in METRICS.items():
  selected={}
  for preference,(taxonomy,tag) in enumerate(concepts):
   for unit,records in raw.get('facts',{}).get(taxonomy,{}).get(tag,{}).get('units',{}).items():
    if metric.endswith('shares') and unit!='shares':continue
    if metric.startswith('eps_') and not re.fullmatch('[A-Z]{3}/shares',unit):continue
    if metric not in ('issued_shares','diluted_weighted_shares','eps_diluted','eps_basic') and not re.fullmatch('[A-Z]{3}',unit):continue
    for r in records:
     start,end,filed=date(r.get('start')),date(r.get('end')),date(r.get('filed'))
     if not end or not filed or end>now.date() or filed>now.date() or not finite(r.get('val')) or not r.get('accn'):continue
     if (now.date()-end).days>4200:continue
     if r.get('form') not in ('10-K','10-Q','20-F','40-F','6-K','10-K/A','20-F/A'):continue
     if metric in INSTANT and start:continue
     if metric not in INSTANT and not start:continue
     kind=period_type(start,end)
     if not kind:continue
     # Unit, duration and disclosure provenance remain attached to every value.
     currency=unit.split('/')[0] if unit!='shares' else None
     fact={'metric':metric,'value':float(r['val']),'unit':unit,'currency':currency,'period_start':str(start) if start else None,
       'period_end':str(end),'period_type':kind,'filed':str(filed),'accession':r['accn'],'form':r['form'],
       'source_url':source_url,'taxonomy':taxonomy,'concept':tag,'accounting_basis':'REGULATORY_SHARE_COUNT' if taxonomy=='dei' else 'IFRS' if taxonomy=='ifrs-full' else 'US_GAAP',
       'is_management_forecast':False,'source_type':'PRIMARY_ISSUER_XBRL','concept_preference':preference}
     key=(fact['period_start'],fact['period_end'],unit,kind)
     prior=selected.get(key)
     if prior is None or (-preference,str(filed),r['accn'])>(-prior['concept_preference'],prior['filed'],prior['accession']):selected[key]=fact
  observations[metric]=sorted(selected.values(),key=lambda r:(r['period_end'],r['period_start'] or '',r['filed']))[-48:]
 return {'ticker':ticker,'issuer':raw['entityName'],'cik':int(raw['cik']),'source_url':source_url,'observed_utc':observed_utc,
  'source_document_sha256':digest(raw),'hash_basis':'CANONICAL_SEC_JSON','status':'PRIMARY_PERIOD_OBSERVATIONS_EXTRACTED',
  'metrics':observations,'facts_sha256':digest(observations),'orders_enabled':False}

def collect(root,cache,only=None,limit=None):
 now=datetime.now(timezone.utc);cache.mkdir(parents=True,exist_ok=True);base=json.loads((root/'reports/primary_evidence_91.json').read_text())['companies']
 # The Resmed issuer identity is confirmed by its SEC filing, not inferred from price.
 identifiers={t:int(r['cik']) for t,r in base.items() if r.get('cik')};identifiers['RMD.AX']=943819
 if only is not None:identifiers={t:c for t,c in identifiers.items() if t in only}
 output=root/'reports/dynamic_sec_periods_92.json.gz';existing=json.loads(gzip.decompress(output.read_bytes())) if output.exists() else {'companies':{},'attempts':{}}
 if limit is not None:
  identifiers=dict(sorted(identifiers.items(),key=lambda item:(existing['companies'].get(item[0],{}).get('observed_utc',''),item[0]))[:limit])
 companies=existing['companies'];attempts=existing.get('attempts',{});blocked=threading.Event();lock=threading.Lock();local=threading.local()
 def work(item):
  ticker,cik=item;path=cache/f'{cik:010d}.json';meta=cache/f'{cik:010d}.metadata.json';url=f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json'
  result={'ticker':ticker,'source_url':url,'attempted_at_utc':now.isoformat(),'orders_enabled':False}
  try:
   if path.exists() and meta.exists():raw=json.loads(path.read_text());observed=json.loads(meta.read_text())['observed_utc']
   else:
    if blocked.is_set():return ticker,None,{**result,'status':'PROVIDER_COOLDOWN_NOT_ATTEMPTED'}
    if not hasattr(local,'session'):
     local.session=requests.Session();local.session.headers['User-Agent']=os.environ.get('SEC_USER_AGENT') or PUBLIC_CONTACT
    response=local.session.get(url,timeout=40)
    if response.status_code in (403,429):blocked.set()
    response.raise_for_status();raw=response.json();observed=datetime.now(timezone.utc).isoformat()
    if int(raw.get('cik',0))!=cik:raise ValueError('Issuer CIK mismatch')
    path.write_text(json.dumps(raw));meta.write_text(json.dumps({'observed_utc':observed,'source_url':url}));time.sleep(.35)
   rec=extract(raw,ticker,now,url,observed)
   return ticker,rec,{**result,'status':'PRIMARY_PERIODS_EXTRACTED','observation_count':sum(len(v) for v in rec['metrics'].values())}
  except (requests.RequestException,ValueError,KeyError) as exc:return ticker,None,{**result,'status':'SOURCE_FETCH_OR_PARSE_FAILED','reason':type(exc).__name__}
 with ThreadPoolExecutor(max_workers=3) as pool:
  for ticker,rec,status in pool.map(work,identifiers.items()):
   if rec:companies[ticker]=rec
   attempts[ticker]=status
   snapshot={'schema_version':'9.2-dynamic-primary-periods-1','published_at_utc':now.isoformat(),'companies':companies,'attempts':attempts,'orders_enabled':False,'orders_generated':0}
   with gzip.GzipFile(output,'wb',mtime=0) as stream:stream.write(json.dumps(snapshot,separators=(',',':')).encode())
   print(ticker,status['status'],flush=True)
 return companies
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path(__file__).resolve().parent);p.add_argument('--cache',type=Path,default=Path('/tmp/dynamic92-sec'));p.add_argument('--tickers',nargs='*');p.add_argument('--limit',type=int);a=p.parse_args()
 if a.limit is not None and not 1<=a.limit<=200:raise ValueError('Limit must be 1–200')
 collect(a.root,a.cache,a.tickers,a.limit)
