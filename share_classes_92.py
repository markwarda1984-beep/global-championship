"""Reconcile explicitly reviewed economically equal common classes from issuer XBRL.
Never sum preferred shares, Up-C interests, or classes with different distributions.
"""
import hashlib,json,re
from pathlib import Path
from datetime import datetime,timezone
from bs4 import BeautifulSoup
from evidence_recovery_91 import write,digest

REVIEWED_EQUAL_CLASSES={
 'META':'have identical liquidation and dividend rights but different voting rights',
 'DDOG':'The rights of the holders of Class A and Class B common stock are identical, except with respect to voting and conversion.',
 'NET':'The rights of the holders of Class A and Class B common stock are identical, except with respect to voting and conversion.',
 'TEAM':'As the liquidation and dividend rights for both Class A and Class B Common Stock are identical',
 'XYZ':'have identical liquidation and dividend rights but different voting rights',
 'DUOL':'The rights of Class A and Class B common stock are identical, except with respect to voting and conversion.',
 'RDDT':'Holders of our Class A and Class B common stock have identical rights except with respect to voting, conversion, and transfer rights, and therefore share equally in our net income or losses.'}
MEMBERS={'us-gaap:CommonClassAMember','us-gaap:CommonClassBMember'}

def equal_class_counts(html,required_excerpt,now):
 soup=BeautifulSoup(html,'html.parser');plain=' '.join(soup.get_text(' ',strip=True).split())
 if required_excerpt not in plain:return []
 return class_counts(soup,MEMBERS,now,required_excerpt)

def class_counts(soup,members,now,required_excerpt):
 contexts={};unknown_contexts=set()
 for c in soup.find_all(lambda x:x.name and x.name.split(':')[-1].lower()=='context'):
  instant=c.find(lambda x:x.name and x.name.split(':')[-1].lower()=='instant')
  dims=c.find_all(lambda x:x.name and x.name.split(':')[-1].lower() in ('explicitmember','typedmember'))
  if not instant:continue
  if len(dims)!=1:
   unknown_contexts.add(c.get("id"));continue
  member=dims[0].get_text(strip=True)
  if member not in members:
   unknown_contexts.add(c.get('id'));continue
  end=instant.get_text(strip=True)
  if end>now.date().isoformat():continue
  contexts[c.get('id')]=(end,member)
 values={};conflicts=set()
 for f in soup.find_all(lambda x:x.name and 'nonfraction' in x.name.lower()):
  concept=f.get('name','').split(':')[-1]
  if concept not in ('EntityCommonStockSharesOutstanding','CommonStockSharesOutstanding'):continue
  if concept=='EntityCommonStockSharesOutstanding' and f.get('contextref') in unknown_contexts:return []
  ctx=contexts.get(f.get('contextref'))
  if not ctx:continue
  token=f.get_text('',strip=True).replace(',','').replace(' ','')
  if not re.fullmatch(r'\d+(?:\.\d+)?',token):continue
  value=float(token)*10**int(f.get('scale','0'));key=(concept,*ctx)
  if key in values and values[key]!=value:conflicts.add((concept,ctx[0]))
  values[key]=value
 results={}
 for concept,end,_ in values:
  if (concept,end) in conflicts:continue
  parts={m:values.get((concept,end,m)) for m in members}
  if any(v is None or v<=0 for v in parts.values()):continue
  r={'value':sum(parts.values()),'unit':'shares','start':None,'end':end,'tag':concept,
     'taxonomy':'dei' if concept.startswith('Entity') else 'us-gaap','class_components':parts,
     'share_basis':'REVIEWED_ECONOMICALLY_EQUAL_COMMON_CLASSES','equality_source_excerpt':required_excerpt}
  if end not in results or concept.startswith('Entity'):results[end]=r
 return sorted(results.values(),key=lambda r:r['end'])

def run(root,documents):
 evidence_path=root/'reports/primary_evidence_91.json';evidence=json.loads(evidence_path.read_text());audit=[];now=datetime.now(timezone.utc)
 for ticker,excerpt in REVIEWED_EQUAL_CLASSES.items():
  path=documents/f'{ticker}-cover.html';source=documents/f'{ticker}-source.json'
  if not path.exists() or not source.exists():continue
  html=path.read_text();meta=json.loads(source.read_text());counts=equal_class_counts(html,excerpt,now)
  if not counts:continue
  sha=hashlib.sha256(html.encode()).hexdigest()
  for r in counts:r.update(source_url=meta['url'],accession=meta['accession'],filed=meta['filed'],form=meta['form'],source_document_sha256=sha)
  company=evidence['companies'][ticker];old=company['annual_facts']['shares'];merged={r['end']:r for r in old};merged.update({r['end']:r for r in counts})
  company['annual_facts']['shares']=sorted(merged.values(),key=lambda r:r['end'])[-20:];company['latest_share_count']=counts[-1];company['evidence_hash_sha256']=digest(company['annual_facts'])
  audit.append({'ticker':ticker,'source_url':meta['url'],'source_document_sha256':sha,'source_excerpt':excerpt,'dated_counts':counts,'orders_enabled':False})
 write(evidence_path,evidence);write(root/'reports/share_class_recovery_92.json',{'published_at_utc':now.isoformat(),'companies':audit,'orders_enabled':False})
 print('Reviewed and reconciled',len(audit),'issuers')
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--documents',type=Path,required=True);a=p.parse_args();run(Path(__file__).resolve().parent,a.documents)
