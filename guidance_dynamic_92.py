"""Reviewed issuer-specific guidance rules; unknown text stays a candidate."""
import re
from datetime import datetime
from bs4 import BeautifulSoup
from evidence_recovery_91 import digest

def extract_hpe(html, metadata, company, now):
    if company.get('cik')!=1645590 or company.get('financial_currency')!='USD':return None
    text=' '.join(BeautifulSoup(html,'html.parser').get_text(' ',strip=True).split())
    match=re.search(r'Fiscal (20\d{2}) Full Year Outlook(.{0,2400})',text,re.I)
    if not match:return None
    year,paragraph=match.groups()
    end=max((r['end'] for r in company.get('annual_facts',{}).get('net_income',[])),default='')
    if not end:return None
    target=year+end[4:]
    if target<now.date().isoformat() or int(year)>now.year+2:return None
    eps=re.search(r'(?<!non-)\bGAAP diluted net EPS to be in the range of \$(\d+(?:\.\d+)?) to \$(\d+(?:\.\d+)?)',paragraph,re.I)
    if not eps:return None
    low,high=map(float,eps.groups())
    if not 0<low<=high:return None
    facts={'ticker':'HPE','currency':'USD','target_period_end':target,'metric':'GAAP_DILUTED_EPS',
           'per_share_basis':'LISTED_DILUTED_COMMON_SHARE','low':low,'high':high}
    adjusted=re.search(r'non-GAAP diluted net EPS estimates? to be in the range of \$(\d+(?:\.\d+)?) to \$(\d+(?:\.\d+)?)',paragraph,re.I)
    exclusions=re.search(r'excludes net after-tax adjustments.{0,30}?approximately \$(\d+(?:\.\d+)?) per diluted share',paragraph,re.I)
    if adjusted and exclusions:
        nlo,nhi=map(float,adjusted.groups());bridge=float(exclusions.group(1))
        if abs(nlo-bridge-low)>.011 or abs(nhi-bridge-high)>.011:return None
        facts.update(non_gaap_eps_low=nlo,non_gaap_eps_high=nhi,non_gaap_eps_aftertax_exclusions=bridge)
    return {'issuer':company['issuer_name'],'source_url':metadata['url'],
            'source_document_sha256':metadata['sha256'],'accession_or_document_id':metadata['accession'],
            'as_of':end,'published_at':metadata['filed'],'review_status':'PRIMARY_DOCUMENT_FIELDS_RECONCILED',
            'parser':'REVIEWED_HPE_EXPLICIT_ANNUAL_GAAP_GUIDANCE_RULE_1','source_location':'Fiscal '+year+' Full Year Outlook',
            'facts':facts,'facts_sha256':digest(facts),'acquisition_regime_change':True,'orders_enabled':False}

def earnings_exhibit_links(html, base_url):
    from urllib.parse import urljoin,urlparse
    urls=[]
    for a in BeautifulSoup(html,'html.parser').find_all('a',href=True):
        label=a.get_text(' ',strip=True);href=a['href']
        if not re.search(r'99[.\-_]?1|earnings.{0,20}release',label+' '+href,re.I):continue
        url=urljoin(base_url,href)
        if urlparse(url).hostname=='www.sec.gov' and urlparse(url).scheme=='https' and '/Archives/edgar/data/' in url:
            urls.append(url)
    return list(dict.fromkeys(urls))[:1]
