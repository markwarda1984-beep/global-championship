"""Issuer-reviewed equal economic classes; never infer economic rights from labels."""
import copy,hashlib,json
from datetime import datetime
from bs4 import BeautifulSoup
from share_classes_92 import class_counts
from evidence_recovery_91 import digest

def policy_valid(policy,now):
 try:
  age=(now.date()-datetime.fromisoformat(policy['reviewed_as_of']).date()).days
  return policy['review_status']=='PRIMARY_DOCUMENT_FIELDS_RECONCILED' and 0<=age<=550 and len(set(policy['members']))==len(policy['members']) and len(policy['members'])>=2 and len(policy['rights_document_sha256'])==64
 except (KeyError,TypeError,ValueError):return False

def reviewed_counts(html,ticker,policy,meta,now,rights_html):
 if not policy_valid(policy,now):return []
 if hashlib.sha256(rights_html.encode()).hexdigest()!=policy['rights_document_sha256']:return []
 if policy['economic_rights_excerpt'] not in ' '.join(BeautifulSoup(rights_html,'html.parser').get_text(' ',strip=True).split()):return []
 prefix=f"https://www.sec.gov/Archives/edgar/data/{int(policy['cik'])}/"
 if not meta.get('url','').startswith(prefix) or not policy['rights_source_url'].startswith(prefix):return []
 soup=BeautifulSoup(html,'html.parser')
 identifiers=soup.find_all(lambda x:x.name and x.name.split(':')[-1].lower()=='identifier')
 try:
  if not identifiers or any(int(x.get_text(strip=True))!=int(policy['cik']) for x in identifiers):return []
 except ValueError:return []
 # Only the issuer cover's dated outstanding counts are approved here.
 # Rounded note-table totals can include treasury or different capital scopes.
 rows=[r for r in class_counts(soup,set(policy['members']),now,policy['economic_rights_excerpt']) if r['taxonomy']=='dei']
 sha=hashlib.sha256(html.encode()).hexdigest()
 for row in rows:
  row.update(source_url=meta['url'],accession=meta['accession'],filed=meta['filed'],form=meta['form'],source_document_sha256=sha,
             rights_source_url=policy['rights_source_url'],rights_document_sha256=policy['rights_document_sha256'])
 return rows

def apply_overlay(company,report,policies,now):
 """Retain approved dated counts across facts refresh; newer complete counts win."""
 if report.get('orders_enabled') is True:raise ValueError('Unsafe share evidence')
 ticker=company.get('ticker');entry=report.get('companies',{}).get(ticker);policy=policies.get('companies',{}).get(ticker)
 if not entry or not policy or not policy_valid(policy,now) or int(company.get('cik',0))!=int(policy['cik']):return company
 rows=entry.get('counts',[])
 if entry.get('counts_sha256')!=digest(rows):return company
 valid=[]
 for r in rows:
  parts=r.get('class_components',{})
  try:
   good=set(parts)==set(policy['members']) and all(isinstance(v,(int,float)) and not isinstance(v,bool) and v>0 for v in parts.values()) and sum(parts.values())==r['value'] and r['unit']=='shares' and r['rights_document_sha256']==policy['rights_document_sha256'] and r['rights_source_url']==policy['rights_source_url'] and r['equality_source_excerpt']==policy['economic_rights_excerpt'] and r['source_url'].startswith(f"https://www.sec.gov/Archives/edgar/data/{int(policy['cik'])}/") and len(r['source_document_sha256'])==64 and r['end']<=r['filed']<=now.date().isoformat()
  except (KeyError,TypeError,ValueError):good=False
  if not good:return company
  valid.append(r)
 if not valid:return company
 company=copy.deepcopy(company);by={r['end']:r for r in company['annual_facts']['shares']};by.update({r['end']:r for r in valid})
 company['annual_facts']['shares']=sorted(by.values(),key=lambda r:r['end'])[-20:]
 latest=max(valid,key=lambda r:r['end']);previous=company.get('latest_share_count')
 if not previous or latest['end']>=previous['end']:company['latest_share_count']=latest
 company['evidence_hash_sha256']=digest(company['annual_facts']);return company
