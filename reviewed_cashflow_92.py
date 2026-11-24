"""Issuer-specific cash-flow rows reviewed against their actual annual statements."""
import hashlib,json,re
from pathlib import Path
from datetime import datetime,timezone
from bs4 import BeautifulSoup
from evidence_recovery_91 import write,digest
RULES={
 'LLY':{'components':['us-gaap:PaymentsToAcquireOtherPropertyPlantAndEquipment'],'labels':['Purchases of property and equipment']},
 'URI':{'components':['uri:PaymentsToAcquirePropertySubjectToOrAvailableForOperatingLease','uri:PaymentsToAcquirePropertyPlantAndEquipmentAndIntangibleAssets'],'labels':['Payments for purchases of rental equipment','Payments for purchases of non-rental equipment and intangible assets']}}

def extract(html,components,labels,meta,now):
 soup=BeautifulSoup(html,'html.parser');plain=' '.join(soup.get_text(' ',strip=True).split())
 if not all(label in plain for label in labels):return []
 contexts={};units={}
 for u in soup.find_all(lambda x:x.name and x.name.split(':')[-1].lower()=='unit'):
  units[u.get('id')]=' '.join(u.get_text(' ',strip=True).split())
 for c in soup.find_all(lambda x:x.name and x.name.split(':')[-1].lower()=='context'):
  if c.find(lambda x:x.name and x.name.split(':')[-1].lower() in ('explicitmember','typedmember')):continue
  dates={k:c.find(lambda x:x.name and x.name.split(':')[-1].lower()==k.lower()) for k in ['startDate','endDate']}
  if not all(dates.values()):continue
  start,end=[dates[k].get_text(strip=True) for k in ['startDate','endDate']]
  if end>now.date().isoformat():continue
  if not 330<=(datetime.fromisoformat(end)-datetime.fromisoformat(start)).days<=385:continue
  contexts[c.get('id')]=(start,end)
 wanted=components+['us-gaap:NetCashProvidedByUsedInOperatingActivities'];facts={};conflict=set()
 for f in soup.find_all(lambda x:x.name and 'nonfraction' in x.name.lower()):
  tag=f.get('name');context=contexts.get(f.get('contextref'));unit=units.get(f.get('unitref'),'')
  if tag not in wanted or not context or unit not in ('iso4217:USD','USD'):continue
  token=f.get_text('',strip=True).replace(',','').replace(' ','')
  if not re.fullmatch(r'\d+(?:\.\d+)?',token):continue
  value=float(token)*10**int(f.get('scale','0'))*(-1 if f.get('sign')=='-' else 1);key=(*context,tag)
  if key in facts and facts[key]!=value:conflict.add(context)
  facts[key]=value
 out=[]
 for context in sorted(set(k[:2] for k in facts)):
  if context in conflict or any((*context,t) not in facts for t in wanted):continue
  amounts={t:facts[(*context,t)] for t in components}
  if any(v<0 for v in amounts.values()):continue
  common={'unit':'USD','start':context[0],'end':context[1],'accession':meta['accession'],'filed':meta['filed'],'form':meta['form'],'source_url':meta['url'],'source_document_sha256':hashlib.sha256(html.encode()).hexdigest()}
  out.append({'operating_cash_flow':{**common,'value':facts[(*context,wanted[-1])],'tag':wanted[-1],'taxonomy':'us-gaap'},'capex':{**common,'value':sum(amounts.values()),'tag':'REVIEWED_COMPLETE_PPE_CASH_OUTFLOW_COMPONENTS','component_values':amounts,'source_row_labels':labels,'taxonomy':'issuer-reviewed-inline-xbrl'}})
 return out


def apply_reviewed_overlay(company,report):
 """Keep reviewed source rows across SEC refreshes, preserving their filing dates."""
 for entry in report.get('companies',[]):
  if entry.get('ticker')!=company.get('ticker') or entry.get('ticker') not in RULES:continue
  rows=entry.get('periods',[])
  if entry.get('review_status')!='PRIMARY_DOCUMENT_FIELDS_RECONCILED' or entry.get('periods_sha256')!=digest(rows):continue
  valid=True
  for row in rows:
   o,c=row.get('operating_cash_flow',{}),row.get('capex',{})
   components=c.get('component_values',{})
   if set(components)!=set(RULES[entry['ticker']]['components']):valid=False;break
   if any(not isinstance(v,(float,int)) or v<0 for v in components.values()):valid=False;break
   if c.get('value')!=sum(components.values()):valid=False;break
   if not all(o.get(k)==c.get(k) and c.get(k) for k in ('start','end','accession','unit')):valid=False;break
   if c.get('unit')!=company.get('financial_currency') or not str(c.get('source_url','')).startswith('https://') or not re.fullmatch('[0-9a-f]{64}',c.get('source_document_sha256','')):valid=False;break
  if not valid:continue
  for kind in ('operating_cash_flow','capex'):
   periods={(r['start'],r['end']):r for r in company['annual_facts'][kind]}
   for row in rows:
    f=row[kind];key=(f['start'],f['end']);current=periods.get(key)
    if not current or f['filed']>=current.get('filed',''):periods[key]=f
   company['annual_facts'][kind]=sorted(periods.values(),key=lambda r:r['end'])[-12:]
  company['evidence_hash_sha256']=digest(company['annual_facts'])
 return company

def run(root,documents):
 p=root/'reports/primary_evidence_91.json';d=json.loads(p.read_text());audit=[];now=datetime.now(timezone.utc)
 for t,rule in RULES.items():
  source=documents/f'{t}-annual-source.json';htmlpath=documents/f'{t}-annual.html'
  if not source.exists() or not htmlpath.exists():continue
  rows=extract(htmlpath.read_text(),rule['components'],rule['labels'],json.loads(source.read_text()),now)
  if not rows:continue
  c=d['companies'][t]
  for kind in ['operating_cash_flow','capex']:
   periods={(r['start'],r['end']):r for r in c['annual_facts'][kind]}
   periods.update({(r[kind]['start'],r[kind]['end']):r[kind] for r in rows});c['annual_facts'][kind]=sorted(periods.values(),key=lambda r:r['end'])[-12:]
  c['evidence_hash_sha256']=digest(c['annual_facts']);audit.append({'ticker':t,'rule':rule,'periods':rows,'periods_sha256':digest(rows),'review_status':'PRIMARY_DOCUMENT_FIELDS_RECONCILED','orders_enabled':False})
 write(p,d);write(root/'reports/reviewed_cashflow_92.json',{'published_at_utc':now.isoformat(),'companies':audit,'orders_enabled':False});print('Issuer cash-flow mappings reconciled:',len(audit))
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--documents',type=Path,required=True);a=p.parse_args();run(Path(__file__).resolve().parent,a.documents)
