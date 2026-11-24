"""Find annual filings for every ASX name without claiming missing tables parsed.
ASX's document acknowledgement gate is never accepted automatically.
"""
import csv,json,re,time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urljoin,urlparse
import requests
from bs4 import BeautifulSoup
from evidence_recovery_91 import write

def collect(root):
 names=[r for r in csv.DictReader((root/'watchlist.csv').open()) if r['ticker'].endswith('.AX')]
 # Preserve priority research names outside the original fixed 200.
 names += [{'ticker':'SKS.AX','name':'SKS Technologies'},{'ticker':'DUG.AX','name':'DUG Technology'}]
 session=requests.Session();out=[]
 for meta in names:
  ticker=meta['ticker'];symbol=ticker[:-3]
  url=f'https://www.asx.com.au/asx/v2/statistics/announcements.do?asxCode={symbol}&by=asxCode&period=M6&timeframe=D'
  rec={'ticker':ticker,'issuer':meta['name'],'index_url':url,'observed_utc':datetime.now(timezone.utc).isoformat(),'orders_enabled':False}
  try:
   r=session.get(url,timeout=25);r.raise_for_status();soup=BeautifulSoup(r.text,'html.parser');filings=[]
   for a in soup.find_all('a',href=True):
    title=' '.join(a.get_text(' ',strip=True).split())
    if re.search(r'annual report|full.year.*report|appendix 4e|financial report',title,re.I):
     link=urljoin(url,a['href']);host=urlparse(link).hostname
     if host not in ('www.asx.com.au','announcements.asx.com.au'):continue
     parent=a.find_parent('tr');context=' '.join(parent.get_text(' ',strip=True).split()) if parent else title
     filings.append({'title':title,'url':link,'publication_context':context[:450]})
   rec.update(status='PRIMARY_FILING_INDEX_COLLECTED' if filings else 'NO_ANNUAL_REPORT_IN_SIX_MONTH_INDEX',filings=filings,
              financial_inputs_verified=False,remaining_work='Acquire issuer-hosted annual report, reconcile currency/unit scale, dated issued shares and relevant annual tables; no missing field is defaulted to zero.')
  except requests.RequestException as e:rec.update(status='PRIMARY_FILING_INDEX_UNAVAILABLE',reason=str(e)[:180],financial_inputs_verified=False)
  out.append(rec);write(root/'reports/asx_source_recovery_91.json',{'schema_version':'9.1-asx-primary-source-inventory-1','companies':out,'original_asx_count':39,'orders_enabled':False})
  time.sleep(.2)
 return out
if __name__=='__main__':
 out=collect(Path(__file__).resolve().parent);print(json.dumps({'asx_names_assessed':len(out),'indices_with_filings':sum(bool(x.get('filings')) for x in out)}))
