"""Read-only merge boundary for the scheduled research worker's reviewed inputs."""
import copy,hashlib,json
from datetime import datetime,timezone
from urllib.parse import urlparse

def merge_evidence(companies,delta):
 if not delta:return companies
 if delta.get('orders_enabled') is not False or delta.get('orders_generated')!=0:raise ValueError('Unsafe background evidence')
 if delta.get('schema_version')!='9.3-background-primary-evidence-1':raise ValueError('Unknown background evidence schema')
 out=copy.deepcopy(companies)
 for ticker,record in delta.get('companies',{}).items():
  if record.get('ticker')!=ticker or record.get('orders_enabled') is not False:continue
  facts=record.get('annual_facts');url=urlparse(record.get('source_url',''))
  if record.get('status')!='OFFICIAL_SEC_COMPANYFACTS_RETRIEVED' or url.scheme!='https' or url.hostname!='data.sec.gov':continue
  if not facts or record.get('evidence_hash_sha256')!=hashlib.sha256(json.dumps(facts,sort_keys=True).encode()).hexdigest():continue
  old=out.get(ticker,{})
  try:
   date=datetime.fromisoformat(record['observed_utc']);prior=datetime.fromisoformat(old.get('observed_utc','1970-01-01T00:00:00+00:00'))
   if date.tzinfo is None or prior.tzinfo is None or date>datetime.now(timezone.utc):continue
  except (KeyError,TypeError,ValueError):continue
  if date>=prior:out[ticker]=copy.deepcopy(record)
 return out

def merge_adapters(adapters,delta):
 out=copy.deepcopy(adapters)
 if not delta:return out
 if delta.get('orders_enabled') is not False or delta.get('orders_generated')!=0:raise ValueError('Unsafe background adapters')
 for ticker,record in delta.get('adapters',{}).items():
  fx=record.get('fx')
  if fx and fx.get('as_of','')>=out.get(ticker,{}).get('fx',{}).get('as_of',''):
   out.setdefault(ticker,{})['fx']=copy.deepcopy(fx)
  basis=record.get('share_basis')
  if basis:
   old=out.get(ticker,{}).get('share_basis') or {}
   if basis.get('as_of','')>=old.get('as_of',''):out.setdefault(ticker,{})['share_basis']=copy.deepcopy(basis)
 return out
