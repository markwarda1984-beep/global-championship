"""Timestamped provider session samples, separate from historical valuation closes."""
import argparse,csv,hashlib,json,math,threading,time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import quote
import requests

def utc(epoch):return datetime.fromtimestamp(epoch,timezone.utc).isoformat()
def positive(x):return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) and x>0

def parse(payload,ticker,now,source_url,expected_currency=None):
 out={'ticker':ticker,'status':'NO_VERIFIED_SESSION_SAMPLES','source_url':source_url,'retrieved_at_utc':now.isoformat(),'source_document_sha256':hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest(),'source_hash_basis':'CANONICAL_PROVIDER_JSON','sessions':{k:None for k in ('pre_market','regular','after_hours')},'orders_enabled':False}
 results=payload.get('chart',{}).get('result') or []
 if len(results)!=1:return out
 result=results[0];meta=result.get('meta',{})
 if meta.get('symbol','').upper()!=ticker.upper():raise ValueError('Quote symbol mismatch')
 out.update(currency=meta.get('currency'),exchange_timezone=meta.get('exchangeTimezoneName'),extended_hours_supported=meta.get('hasPrePostMarketData'))
 if expected_currency and meta.get('currency')!=expected_currency:
  out['status']='SESSION_CURRENCY_MISMATCH_REVIEW_REQUIRED';return out
 periods=meta.get('currentTradingPeriod') or {};ranges={}
 for provider,key in [('pre','pre_market'),('regular','regular'),('post','after_hours')]:
  p=periods.get(provider) or {};start,end=p.get('start'),p.get('end')
  if positive(start) and positive(end) and start<end:ranges[key]=(start,end)
 timestamps=result.get('timestamp') or [];quotes=result.get('indicators',{}).get('quote') or []
 if len(quotes)!=1:return out
 closes=quotes[0].get('close') or []
 if len(timestamps)!=len(closes):raise ValueError('Chart timestamp/price length mismatch')
 for epoch,price in zip(timestamps,closes):
  if not positive(epoch) or epoch>now.timestamp() or not positive(price):continue
  for key,(start,end) in ranges.items():
   if not start<=epoch<end:continue
   previous=out['sessions'][key]
   if previous and epoch<=previous['provider_epoch']:continue
   age=now.timestamp()-epoch
   out['sessions'][key]={'price':price,'currency':meta.get('currency'),'as_of_utc':utc(epoch),'provider_epoch':epoch,'session':key.upper(),'session_start_utc':utc(start),'session_end_utc':utc(end),'sample_age_seconds':round(age,1),'freshness':'RECENT_AT_RETRIEVAL_NOT_LIVE' if age<=900 else 'DATED_SESSION_SAMPLE_NOT_LIVE','timestamp_basis':'PROVIDER_ONE_MINUTE_CHART_SAMPLE_NOT_EXECUTABLE_TICK','source_url':source_url}
 if any(out['sessions'].values()):out['status']='TIMESTAMPED_SESSION_SAMPLES_AVAILABLE'
 if meta.get('hasPrePostMarketData') is False:out['extended_hours_status']='PROVIDER_DOES_NOT_ADVERTISE_EXTENDED_HOURS'
 else:out['extended_hours_status']='AVAILABLE' if out['sessions']['pre_market'] or out['sessions']['after_hours'] else 'NO_VERIFIED_EXTENDED_HOURS_SAMPLE_RETURNED'
 return out

def collect(root,now=None,limit=None,mode='scan'):
 from scan import load_watchlist,currency_for
 now=now or datetime.now(timezone.utc);watchlist=load_watchlist(root/'watchlist.csv');currencies={r['ticker']:currency_for(r['ticker']) for r in watchlist};symbols=list(currencies);selected=symbols[:limit] if limit else symbols
 stop=threading.Event();lock=threading.Lock();last=[0.];deadline=time.monotonic()+180
 def work(t):
  url=f'https://query1.finance.yahoo.com/v8/finance/chart/{quote(t,safe="")}?interval=1m&range=1d&includePrePost=true'
  if stop.is_set() or time.monotonic()>deadline:return t,{'ticker':t,'status':'PROVIDER_COOLDOWN_OR_RUN_BUDGET','sessions':{},'source_url':url,'orders_enabled':False}
  try:
   with lock:
    time.sleep(max(0,.2-(time.monotonic()-last[0])));last[0]=time.monotonic()
   response=requests.get(url,headers={'User-Agent':'Mozilla/5.0'},timeout=(5,12))
   if response.status_code in (403,429):stop.set()
   response.raise_for_status();return t,parse(response.json(),t,datetime.now(timezone.utc),url,currencies[t])
  except (requests.RequestException,ValueError,KeyError,TypeError) as exc:return t,{'ticker':t,'status':'SESSION_SOURCE_UNAVAILABLE','reason':type(exc).__name__,'sessions':{},'source_url':url,'orders_enabled':False}
 with ThreadPoolExecutor(max_workers=4) as pool:records=dict(pool.map(work,selected))
 for t in symbols:records.setdefault(t,{'ticker':t,'status':'NOT_REQUESTED_IN_BOUNDED_RUN','sessions':{},'orders_enabled':False})
 report={'schema_version':'9.5-market-sessions-1','published_at_utc':datetime.now(timezone.utc).isoformat(),'original_200_count':len(symbols),'companies':records,'sample_counts':{k:sum(bool(r['sessions'].get(k)) for r in records.values()) for k in ('pre_market','regular','after_hours')},'orders_enabled':False,'orders_generated':0}
 filename='session_quotes_95_weekly.json' if mode=='weekly' else 'session_quotes_95_latest.json'
 path=root/'reports'/filename;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
 data=root/'data/latest.json'
 if data.exists():
  scan=json.loads(data.read_text())
  for row in scan.get('stocks',[]):
   row['market_sessions']=records.get(row['ticker']);row['valuation_price_session']='DAILY_CLOSE'
   for label in ('pre_market','regular','after_hours'):
    sample=(row['market_sessions'] or {}).get('sessions',{}).get(label) or {}
    row[label+'_price']=sample.get('price');row[label+'_as_of_utc']=sample.get('as_of_utc')
  scan['session_quotes_report']='reports/'+filename;data.write_text(json.dumps(scan,indent=2,allow_nan=False)+'\n')
  from scan import render_html
  (root/'data/index.html').write_text(render_html(scan),encoding='utf-8')
 print(json.dumps({'original_200_count':len(symbols),'sample_counts':report['sample_counts'],'orders_generated':0}));return report
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path(__file__).resolve().parent);p.add_argument('--limit',type=int);p.add_argument('--mode',choices=['scan','weekly'],default='scan');a=p.parse_args();collect(a.root,limit=a.limit,mode=a.mode)
