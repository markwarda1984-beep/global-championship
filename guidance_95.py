"""Reviewed issuer-specific annual GAAP EPS rules, including points and floors.
Quarterly guidance and non-GAAP-only outlooks never become annual GAAP inputs.
"""
import hashlib,re
from datetime import date,datetime,timedelta
from bs4 import BeautifulSoup
from evidence_recovery_91 import digest
CIKS={'ADBE':796343,'DELL':1571996,'UNH':731766}
ADBE_CALENDAR={'source_url':'https://www.sec.gov/Archives/edgar/data/796343/000079634326000003/adbe-20251128.htm','accession':'0000796343-26-000003','published_at':'2026-01-15','excerpt':'Our fiscal year is a 52- or 53-week year that ends on the Friday closest to November 30.','reviewed_guidance_year':2026}

def extract(ticker,html,meta,company,now):
 if ticker not in CIKS or company.get('cik')!=CIKS[ticker] or company.get('financial_currency')!='USD':return None
 if not meta.get('url','').startswith(f'https://www.sec.gov/Archives/edgar/data/{CIKS[ticker]}/'):return None
 if hashlib.sha256(html.encode()).hexdigest()!=meta.get('sha256') or meta['filed']>now.date().isoformat():return None
 text=' '.join(BeautifulSoup(html,'html.parser').get_text(' ',strip=True).split());shape='RANGE';calendar=None
 if ticker=='ADBE':
  m=re.search(r'table summarizes Adobe[’\']s updated FY(20\d\d) targets:(.{0,1800})',text)
  if not m or int(m[1])!=ADBE_CALENDAR['reviewed_guidance_year']:return None
  year=int(m[1]);scope=m[2];eps=re.search(r'Earnings per share\s*\d*\s*GAAP:\s*\$(\d+\.\d+) to \$(\d+\.\d+)',scope)
  if not eps or not re.search(r'diluted share count.{0,60}FY'+str(year),scope):return None
  lo,hi=map(float,eps.groups());anchor=date(year,11,30);fridays=[anchor+timedelta(days=i) for i in range(-6,7) if (anchor+timedelta(days=i)).weekday()==4];target=min(fridays,key=lambda d:abs((d-anchor).days));calendar=ADBE_CALENDAR;scope=eps[0]
 elif ticker=='DELL':
  m=re.search(r'Full-Year Guidance FY(\d\d) Previous FY\1 Updated(.{0,700})',text)
  if not m:return None
  eps=re.search(r'(?<!Non-)GAAP diluted EPS\s*\$\s*(\d+\.\d+)\s*\$\s*(\d+\.\d+)',m[2]);end=re.search(r'Fiscal Year Ending\s+([A-Z][a-z]+ \d{1,2}, 20\d\d)',text)
  if not eps or not end:return None
  target=datetime.strptime(end[1],'%B %d, %Y').date()
  if target.year!=2000+int(m[1]):return None
  lo=hi=float(eps[2]);scope=eps[0];shape='POINT'
 else:
  m=re.search(r'Updated Full Year (20\d\d) Earnings Outlook to At Least \$(\d+\.\d+) Per Share; Adjusted Earnings',text)
  if not m:return None
  year=int(m[1]);target=date(year,12,31);lo=hi=float(m[2]);scope=m[0];shape='FLOOR'
  # The forward reconciliation explicitly identifies the GAAP diluted floor.
  if not re.search(r'(?<!Adjusted )Diluted earnings per share\s*\.+.{0,110}At least \$'+re.escape(m[2]),text,re.I):return None
 if target<now.date() or not 0<lo<=hi:return None
 facts={'ticker':ticker,'currency':'USD','target_period_end':target.isoformat(),'metric':'GAAP_DILUTED_EPS','per_share_basis':'LISTED_DILUTED_COMMON_SHARE','low':lo,'high':hi,'guidance_shape':shape,'scenario_eps_note':'A guided floor is held constant in every earnings scenario; no upper earnings estimate is invented.' if shape=='FLOOR' else 'A management point estimate is held constant across earnings scenarios.' if shape=='POINT' else 'Explicit management annual GAAP diluted EPS range.'}
 if shape=='FLOOR':facts['high_is_guided_ceiling']=False
 return {'issuer':company['issuer_name'],'source_url':meta['url'],'source_document_sha256':meta['sha256'],'accession_or_document_id':meta['accession'],'as_of':meta['filed'],'published_at':meta['filed'],'review_status':'PRIMARY_DOCUMENT_FIELDS_RECONCILED','parser':'REVIEWED_'+ticker+'_ANNUAL_GAAP_EPS_95','source_location':'Annual outlook; '+shape,'source_excerpt':scope,'fiscal_calendar_evidence':calendar,'facts':facts,'facts_sha256':digest(facts),'orders_enabled':False}
