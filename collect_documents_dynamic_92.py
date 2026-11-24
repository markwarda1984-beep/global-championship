"""Bounded public issuer-document collection; candidates never self-approve.

This inventory is distinct from valuation coverage. A PDF, a financial table,
and a completed financial model are three different outcomes.
"""
from __future__ import annotations
import argparse, gzip, hashlib, json, re, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
import fitz, requests
from bs4 import BeautifulSoup
from championship_90 import read, write

def inspect_document(body, url):
    if body.startswith(b'%PDF'):
        with fitz.open(stream=body,filetype='pdf') as doc:
            pages=[p.get_text(sort=True) for p in doc]
        kind='PDF'
    else:
        text=BeautifulSoup(body,'html.parser').get_text(' ',strip=True)
        if re.search(r'captcha|access denied|verify you are human',text[:1000],re.I):
            raise ValueError('PROVIDER_VERIFICATION_REQUIRED')
        pages=[text];kind='HTML'
    sections={};patterns={
        'income':r'(?:consolidated.{0,100}(?:income|earnings|profit)|statement.{0,30}(?:profit|income|earnings))',
        'balance':r'(?:consolidated.{0,100}(?:balance|financial position)|balance sheet|statement.{0,30}financial position)',
        'cash_flow':r'(?:consolidated.{0,100}cash.{0,5}flow|statement.{0,30}cash.{0,5}flow)'}
    for i,text in enumerate(pages):
        normalized=' '.join(text.split())
        for key,pattern in patterns.items():
            match=re.search(pattern,normalized[:5000] if kind=='PDF' else normalized,re.I)
            if key not in sections and match:
                sections[key]={'page':i+1 if kind=='PDF' else None,
                               'locator':match.group(0),'heading_excerpt':normalized[max(0,match.start()-60):match.end()+300]}
    return {'format':kind,'page_count':len(pages) if kind=='PDF' else None,
            'statement_sections_detected':sections,'all_three_sections_detected':len(sections)==3,
            'issuer_identity_review_required':True,'financial_table_values_reviewed':False,
            'counts_toward_supported_valuation_coverage':False,
            'content_excerpt':pages[0][:500] if pages else ''}

def collect_one(root, ticker, max_documents=1, now=None, session=None):
    now=now or datetime.now(timezone.utc);session=session or requests.Session()
    session.headers['User-Agent']='ChampionshipResearch https://github.com/markwarda1984-beep/global-championship'
    config=read(root/'settings/dynamic_sources_92.json',{})
    path=root/'reports/dynamic_documents_92.json';state=read(path,{'documents':{},'attempts':{},'orders_enabled':False})
    state.setdefault('provider_cooldowns',{})
    cache=root/'.source-cache';cache.mkdir(exist_ok=True)
    attempted=0
    for source in config.get('documents',{}).get(ticker,[]):
        if attempted>=max_documents:break
        url=source['url'];key=hashlib.sha256(url.encode()).hexdigest()
        if urlparse(url).scheme!='https' or not urlparse(url).hostname:continue
        host=urlparse(url).hostname;cooldown=state['provider_cooldowns'].get(host)
        if cooldown and datetime.fromisoformat(cooldown)>now:continue
        old=state['documents'].get(key);prior=state['attempts'].get(key,{})
        if old and (now-datetime.fromisoformat(old['observed_utc'])).total_seconds()<7*86400:continue
        if prior.get('retry_after_utc') and datetime.fromisoformat(prior['retry_after_utc'])>now:continue
        attempted+=1;attempt={'ticker':ticker,'source_url':url,'attempted_at_utc':now.isoformat()}
        try:
            response=session.get(url,timeout=(10,40),stream=True,allow_redirects=False)
            try:
                if response.status_code in (403,429):raise ValueError('PROVIDER_COOLDOWN_HTTP_'+str(response.status_code))
                if 300<=response.status_code<400:raise ValueError('SOURCE_REDIRECT_NEEDS_REVIEW')
                response.raise_for_status();parts=[];size=0
                for part in response.iter_content(65536):
                    size+=len(part)
                    if size>80_000_000:raise ValueError('DOCUMENT_EXCEEDS_80MB_BOUND')
                    parts.append(part)
                body=b''.join(parts)
            finally:response.close()
            inspection=inspect_document(body,url)
            sha=hashlib.sha256(body).hexdigest();(cache/(sha+'.raw')).write_bytes(body)
            doc={'ticker':ticker,'source_url':url,'source_document_sha256':sha,'observed_utc':now.isoformat(),
                 'source_registration':source,**inspection}
            state['documents'][key]=doc;attempt['status']='PRIMARY_DOCUMENT_RETRIEVED_REVIEW_REQUIRED'
            # Re-observation of an IDENTICAL previously reviewed document may
            # refresh its retrieval time. A changed PDF cannot inherit approval.
            for name in ('dynamic_manual_periods_92.json','dynamic_release_periods_92.json','dynamic_historical_records_92.json'):
                target=root/'reports'/name;data=read(target,{})
                rec=data.get('companies',{}).get(ticker)
                if not rec:continue
                facts=[f for vals in (rec.get('metrics') or rec.get('annual_facts') or {}).values() for f in vals]
                newest=max((f.get('period_end') or f.get('end') or '' for f in facts),default='')
                if facts and any(f.get('source_document_sha256')==sha and (f.get('period_end') or f.get('end'))==newest for f in facts):
                    rec['observed_utc']=now.isoformat();write(target,data)
        except (requests.RequestException,ValueError,RuntimeError) as exc:
            if 'PROVIDER_' in str(exc):state['provider_cooldowns'][host]=(now+timedelta(hours=24)).isoformat()
            attempt.update(status='SOURCE_UNAVAILABLE_OR_REVIEW_REQUIRED',reason=str(exc)[:120],
                           retry_after_utc=(now+timedelta(hours=24)).isoformat())
        state['attempts'][key]=attempt
        write(path,state)
    return state

def audit(root, now=None, mode='canonical'):
    now=now or datetime.now(timezone.utc);baseline=read(root/'settings/dynamic_baseline_92.json',{})
    old=read(root/'reports/coverage_recovery_91.json',{})
    missing_statements=set(baseline.get('missing_current_statement_tickers',[]))
    documents=read(root/'reports/dynamic_documents_92.json',{})
    file=root/'reports/dynamic_sec_periods_92.json.gz'
    sec=json.loads(gzip.decompress(file.read_bytes())) if file.exists() else {}
    background=read(root/'reports/background_evidence_93.json',{})
    companies={**sec.get('companies',{}),**background.get('dynamic_periods',{})}
    config=read(root/'settings/dynamic_sources_92.json',{});out={}
    for row in old.get('companies',[]):
        ticker=row['ticker']
        if ticker in baseline.get('valued_tickers',[]):continue
        record=companies.get(ticker);docs=[d for d in documents.get('documents',{}).values() if d['ticker']==ticker]
        out[ticker]={'ticker':ticker,'missing_current_statement_priority':ticker in missing_statements,
                     'structured_primary_periods_recovered':bool(record),'structured_source_url':record.get('source_url') if record else None,
                     'structured_observation_count':sum(len(v) for v in (record or {}).get('metrics',{}).values()),
                     'documents':docs,'all_three_statement_sections_detected':any(d['all_three_sections_detected'] for d in docs),
                     'identity_review':config.get('identity_aliases',{}).get(ticker),
                     'remaining_model_inputs':row['missing_inputs'],'financial_model_supported':False,
                     'note':'Source recovery is not completed financial reconciliation. See dynamic valuation report for current model eligibility.',
                     'orders_enabled':False}
    if mode=='canonical':
        from background_research_93 import assess_without_overwriting_reports
        current=assess_without_overwriting_reports(root,now)
    else:
        current=read(root/('reports/valuation_90_weekly.json' if mode=='weekly' else 'reports/valuation_90_latest.json'),{})
    mapping={r['ticker']:r for r in current.get('companies',[])}
    for ticker,row in out.items():
        row['financial_model_supported']=bool(mapping.get(ticker,{}).get('scenarios'))
        row['remaining_model_inputs']=mapping.get(ticker,{}).get('missing_inputs',row['remaining_model_inputs'])
    result={'schema_version':'9.2-primary-source-recovery-1','published_at_utc':now.isoformat(),
            'baseline_outstanding_count':111,'missing_current_statement_priority_count':len(missing_statements),
            'outstanding_companies_assessed':len(out),
            'structured_primary_recovered':sum(r['structured_primary_periods_recovered'] for r in out.values()),
            'primary_documents_retrieved':sum(bool(r['documents']) for r in out.values()),
            'three_statement_sections_detected_unreviewed':sum(r['all_three_statement_sections_detected'] for r in out.values()),
            'remaining_model_count':sum(not r['financial_model_supported'] for r in out.values()),
            'companies':out,'orders_enabled':False,'orders_generated':0}
    filename='dynamic_source_recovery_92.json' if mode=='canonical' else f'dynamic_source_recovery_92_{mode}.json'
    write(root/'reports'/filename,result)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path(__file__).resolve().parent)
    p.add_argument('--tickers',nargs='*');p.add_argument('--max-documents',type=int,default=6);p.add_argument('--audit-suffix',choices=['canonical','scan','weekly'],default='canonical');a=p.parse_args()
    if not 0<=a.max_documents<=100:raise ValueError('Document bound must be 0–100')
    tickers=a.tickers or list(read(a.root/'settings/dynamic_sources_92.json',{}).get('issuer_indices',{}))
    state=read(a.root/'reports/dynamic_documents_92.json',{})
    priority=set(read(a.root/'settings/dynamic_baseline_92.json',{}).get('missing_current_statement_tickers',[]))
    def last_attempt(ticker):
        times=[r['attempted_at_utc'] for r in state.get('attempts',{}).values() if r['ticker']==ticker]
        return max(times) if times else ''
    if not a.tickers:tickers.sort(key=lambda t:(bool(last_attempt(t)),t not in priority,last_attempt(t),t))
    for ticker in tickers[:a.max_documents]:collect_one(a.root,ticker,max_documents=1)
    print(json.dumps({k:v for k,v in audit(a.root,mode=a.audit_suffix).items() if k!='companies'},indent=2))
