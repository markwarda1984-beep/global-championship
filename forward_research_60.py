"""Championship 6.0: dated, read-only forward estimates and issuer guidance research.

Issuer guidance is evidence of what MANAGEMENT forecast, not an independently
verified earnings estimate. Yahoo analyst consensus is SECONDARY and cannot
validate fair value, cash flows, recommendations, purchase entries or orders.
Missing numbers remain None. Offline deterministic tests use injected fetchers.
"""
from __future__ import annotations

import argparse
import hashlib
import html
from html.parser import HTMLParser
import json
import math
import os
import re
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

import championship_60 as core

SCHEMA = '6.0-dated-forward-estimates-1'
GUIDANCE_SCHEMA = '6.0-issuer-guidance-evidence-1'
QUARTERS = {'0q', '+1q', '0y', '+1y'}
OFFICIAL_NVDA_URL = 'https://www.sec.gov/Archives/edgar/data/1045810/000104581026000088/q3fy27pr.htm'
ALLOWED_ISSUER_SOURCES = {'www.sec.gov', 'investor.nvidia.com', 'nvidianews.nvidia.com'}
MAX_GUIDANCE_BYTES = 1_600_000


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(); self.ignore=0; self.parts=[]
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style','nav'):self.ignore+=1
    def handle_endtag(self,tag):
        if tag in ('script','style','nav') and self.ignore:self.ignore-=1
    def handle_data(self,data):
        if not self.ignore:self.parts.append(data)


def _date(value):
    try:return date.fromisoformat(str(value)[:10])
    except (TypeError,ValueError):return None


def _utc_time(value):
    try:
        out=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        if out.tzinfo is None:return None
        return out.astimezone(timezone.utc)
    except (ValueError,TypeError,OverflowError):return None


def _number(v):
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except (ValueError,TypeError,OverflowError):return None


def _valid_url(url):
    p=urlparse(url)
    return p.scheme=='https' and p.hostname in ALLOWED_ISSUER_SOURCES and not p.username and not p.password and p.port in (None,443)


def issuer_guidance_from_document(ticker:str,url:str,body:bytes,now:datetime)->dict:
    """Match issuer/date/period/value in official body, never from URL/title alone."""
    info={'ticker':ticker,'source_url':url,'checked_at_utc':now.isoformat(),
          'status':'NOT VALIDATED','reported_guidance':None,'evidence_sha256':None,
          'evidence_excerpt':None,'orders_enabled':False}
    if ticker!='NVDA' or not _valid_url(url) or not body or len(body)>MAX_GUIDANCE_BYTES:
        info['status']='SOURCE_NOT_SUPPORTED_OR_INVALID';return info
    parser=_Text();parser.feed(body.decode('utf-8','replace'))
    text=' '.join(' '.join(parser.parts).split())
    if not (re.search(r'\bNVIDIA\b',text,re.I) and re.search(r'November\s+17,?\s+2026',text,re.I)):
        info['status']='ISSUER_OR_DISCLOSURE_DATE_NOT_CONFIRMED';return info
    start=re.search(r'outlook\s+for\s+the\s+fourth\s+quarter\s+of\s+fiscal\s+2027',text,re.I)
    if not start:
        info['status']='EXACT_FISCAL_PERIOD_NOT_CONFIRMED';return info
    subset=text[start.end():start.end()+1800]
    match=re.search(r'Revenue\s+is\s+expected\s+to\s+be\s+\$([\d.,]+)\s+billion\s*,?\s*plus\s+or\s+minus\s+([\d.]+)\s*%',subset,re.I)
    if not match:
        info['status']='GUIDANCE_VALUE_NOT_FOUND_IN_BODY';return info
    rev=_number(match.group(1).replace(',',''))
    tol=_number(match.group(2))
    if rev is None or not 1<=rev<=1000 or tol is None or not 0<tol<=25:
        info['status']='GUIDANCE_OUTSIDE_FORMAT_BOUNDS';return info
    info.update(status='ISSUER_REPORTED_GUIDANCE_CONFIRMED_IN_FILING_EXHIBIT',
       reported_guidance={'metric':'quarterly_revenue','period':'FY2027_Q4',
         'revenue_usd_billions':rev,'management_plus_minus_pct':tol,
         'issuer_report_date':'2026-11-17',
         'forecast_kind':'MANAGEMENT_GUIDANCE_NOT_ANALYST_EPS_CONSENSUS',
         'not_independently_verified':True},
       evidence_sha256=hashlib.sha256(body).hexdigest(),
       evidence_excerpt=text[start.start():start.end()+match.end()+100][:600])
    return info


def fetch_guidance(root:Path,now:datetime,session:Any,*,offline:bool=False)->dict:
    """Bounded primary SEC 8-K exhibit fetch. Never silently use known web snippets."""
    old=core.read(root/'reports/issuer_guidance_60.json',{}) or {}
    prev=(old.get('companies') or {}).get('NVDA') if isinstance(old.get('companies'),dict) else None
    out={'schema_version':GUIDANCE_SCHEMA,'published_at_utc':now.isoformat(),
         'companies':dict(old.get('companies') or {}),'status':'NOT_FETCHED',
         'orders_enabled':False,'research_only':True,
         'note':'Issuer guidance is a forecast, NOT analyst EPS estimates or a valuation input.'}
    if offline or session is None:
        out['status']='OFFLINE_PRESERVE_PREVIOUS';return out
    retry=_utc_time(old.get('provider_cooldown_until_utc'))
    if retry and retry>now:
        out['status']='ISSUER_PROVIDER_COOLDOWN_ACTIVE'
        out['provider_cooldown_until_utc']=old.get('provider_cooldown_until_utc')
        return out
    if prev and prev.get('status')=='ISSUER_REPORTED_GUIDANCE_CONFIRMED_IN_FILING_EXHIBIT':
        checked=_date(prev.get('checked_at_utc'))
        if checked and 0<=(now.date()-checked).days<=7:
            out['status']='FRESH_PRIMARY_SOURCE_REUSED';return out
    if '@' not in os.environ.get('SEC_USER_AGENT',''):
        out['status']='SEC_CONTACT_REQUIRED';return out
    try:
        r=session.get(OFFICIAL_NVDA_URL,timeout=15,allow_redirects=False,headers={'User-Agent':os.environ['SEC_USER_AGENT'],'Accept':'text/html'})
        if r.status_code!=200:
            out['status']=f'ISSUER_SOURCE_HTTP_{r.status_code}'
            if r.status_code in (403,429):
                out['provider_cooldown_until_utc']=(now+timedelta(hours=18)).isoformat()
            return out
        content=r.content
        if len(content)>MAX_GUIDANCE_BYTES:
            out['status']='DOCUMENT_TOO_LARGE';return out
        rec=issuer_guidance_from_document('NVDA',OFFICIAL_NVDA_URL,content,now)
        out['companies']['NVDA']=rec
        out['status']=rec['status']
    except Exception as exc:
        out['status']='ISSUER_SOURCE_FETCH_FAILED'
        out['error_type']=type(exc).__name__
    return out


def _estimate_periods(frame)->dict:
    """Normalize yfinance analyst EPS estimates, retaining every data-quality doubt."""
    if frame is None or not hasattr(frame,'to_dict'):return {}
    try:data=frame.to_dict('index')
    except (ValueError,TypeError,KeyError):return {}
    out={}
    for k,row in data.items():
        p=str(k)
        if p not in QUARTERS or not isinstance(row,dict):continue
        avg=_number(row.get('avg'))
        lo=_number(row.get('low'));hi=_number(row.get('high'))
        n=_number(row.get('numberOfAnalysts'))
        if avg is None or abs(avg)>1e5 or (lo is not None and avg<lo) or (hi is not None and avg>hi):continue
        if n is not None and not (0<n<=1000):n=None
        end=row.get('fiscal_period_end') or row.get('fiscalEndDate')
        fd=_date(end)
        out[p]={'consensus_eps_average':round(avg,6),'low':round(lo,6) if lo is not None else None,
                'high':round(hi,6) if hi is not None else None,'analysts_count':int(n) if n is not None else None,
                'fiscal_period_end':fd.isoformat() if fd else None,
                'period_identity_validated':bool(fd),
                'data_quality':'SECONDARY_UNOFFICIAL_YAHOO_DATA_NOT_PRIMARY_VERIFIED'}
    return out


def _revision_history(history:list[dict])->dict:
    """Only compare dated observations with identical explicit fiscal-end identity."""
    out={}
    for key in ('0q','+1q','0y','+1y'):
        records=[]
        for snap in history:
            item=(snap.get('periods') or {}).get(key)
            if item and isinstance(item,dict) and _date(item.get('fiscal_period_end')):
                records.append((snap.get('observed_at_utc'),item))
        records=[x for x in records if x[0]]
        records.sort(key=lambda x:x[0])
        if len(records)<2:
            out[key]={'status':'NOT VALIDATED — COMPARABLE DATED REVISIONS UNAVAILABLE','revision_pct':None}
            continue
        a,b=records[-2:]
        first=a[1]['consensus_eps_average'];second=b[1]['consensus_eps_average']
        if a[1].get('fiscal_period_end')!=b[1].get('fiscal_period_end') or first==0 or a[0]==b[0]:
            out[key]={'status':'NOT VALIDATED — FORECAST_PERIOD_MISMATCH','revision_pct':None}
        else:
            out[key]={'status':'SECONDARY_VENDOR_REVISION_RESEARCH_ONLY',
                      'revision_pct':round((second-first)/abs(first)*100,3),
                      'fiscal_period_end':b[1]['fiscal_period_end'],
                      'previous_observed_at_utc':a[0],'current_observed_at_utc':b[0],
                      'independently_verified':False}
    return out


def collect_estimates(root:Path,now:datetime,cfg:dict,fetcher=None,*,offline=False)->dict:
    names,original=core.universe(root)
    previous=core.read(root/'reports/forward_estimates_60.json',{}) or {}
    companies=dict(previous.get('companies') or {})
    priority=[str(x).upper() for x in cfg.get('priority_tickers',['NVDA'])]
    p_index={t:i for i,t in enumerate(priority)}
    names.sort(key=lambda x:(p_index.get(x['ticker'],10000),
                            0 if x['universe']=='DISCOVERY' else 1,x['ticker']))
    budget=int(cfg.get('max_new_forward_estimates_per_discovery_run',8))
    if not 1<=budget<=20:raise ValueError('Forward estimates batch budget unsafe')
    fetched=[];statuses={};cooldown=previous.get('provider_cooldown_until_utc')
    active_cooldown=bool(_utc_time(cooldown) and _utc_time(cooldown)>now)
    failures=dict(previous.get('temporary_failures') or {})
    attempted=[]
    for x in names:
        t=x['ticker']; old=companies.get(t,{})
        obs=_date(old.get('observed_at_utc'))
        refresh_days=(cfg.get('priority_forward_estimates_refresh_days',7)
                      if t in p_index else cfg.get('forward_estimates_refresh_days',14))
        if old.get('status')=='UNOFFICIAL_CONSENSUS_SNAPSHOT' and obs and (now.date()-obs).days<refresh_days:
            statuses[t]='CACHED_SECONDARY_SNAPSHOT'
            continue
        retry=_date((failures.get(t) or {}).get('retry_after_utc'))
        if retry and retry>now.date():
            statuses[t]='PROVIDER_PER_TICKER_COOLDOWN'
            continue
        if offline or fetcher is None or active_cooldown or len(attempted)>=budget:
            statuses[t]='NOT_COLLECTED_OR_COOLDOWN'
            continue
        attempted.append(t)
        try:
            if not offline and len(attempted)>1:
                import time
                time.sleep(.5)
            frame=fetcher(t)
            periods=_estimate_periods(frame)
            if not periods:
                statuses[t]='PROVIDER_ESTIMATES_MISSING'
                failures[t]={'status':'PROVIDER_ESTIMATES_MISSING',
                             'retry_after_utc':(now+timedelta(days=3)).isoformat()}
                continue
            obs={'observed_at_utc':now.isoformat(),'periods':periods}
            hist=list(old.get('history') or [])
            if not hist or hist[-1].get('observed_at_utc')!=obs['observed_at_utc']:hist.append(obs)
            hist=hist[-8:]
            companies[t]={'ticker':t,'status':'UNOFFICIAL_CONSENSUS_SNAPSHOT',
                 'observed_at_utc':now.isoformat(),
                 'source':'Yahoo Finance via unofficial yfinance',
                 'source_url':f'https://finance.yahoo.com/quote/{t}/analysis/',
                 'source_type':'SECONDARY_VENDOR_NOT_PRIMARY_FILING',
                 'forecast_currency':'UNVERIFIED','eps_share_basis':'UNVERIFIED',
                 'history':hist,'periods':periods,'revisions':_revision_history(hist),
                 'usable_for_intrinsic_validation':False,'orders_enabled':False}
            statuses[t]='SECONDARY_ESTIMATES_RECORDED';fetched.append(t)
            failures.pop(t,None)
        except Exception as exc:
            reason=type(exc).__name__
            statuses[t]='ESTIMATES_PROVIDER_ERROR_'+reason
            failures[t]={'status':'ESTIMATES_PROVIDER_ERROR_'+reason,
                         'retry_after_utc':(now+timedelta(days=1)).isoformat()}
            if any(k in str(exc).lower() for k in ('429','rate limit','too many requests')):
                cooldown=(now+timedelta(hours=12)).isoformat()
                active_cooldown=True
    return {'schema_version':SCHEMA,'published_at_utc':now.isoformat(),
        'universe_count':len(names),'original_200_count':len(original),'discovery_count':len(names)-len(original),
        'companies':companies,'per_ticker_status':statuses,'attempts_this_run':attempted,
        'successful_snapshots_this_run':fetched,'temporary_failures':failures,
        'snapshot_count':sum(v.get('status')=='UNOFFICIAL_CONSENSUS_SNAPSHOT' for v in companies.values()),
        'provider_cooldown_until_utc':cooldown,'orders_enabled':False,'research_only':True,
        'warning':'Consensus estimates are unofficial SECONDARY forecasts. No period-identity means no verified revisions. They MUST NOT validate intrinsic value, EPS share basis, buy entries or order readiness.'}


def update(root:Path,*,now:datetime|None=None,offline=False,fetcher=None,session=None)->dict:
    now=now or datetime.now(timezone.utc)
    cfg=core.validate_cfg(core.read(root/'settings/championship_60.json',core.DEFAULT_ASSUMPTIONS))
    if not offline and fetcher is None:
        import yfinance as yf
        fetcher=lambda ticker:yf.Ticker(ticker).get_earnings_estimate()
    if not offline and session is None:
        import requests
        session=requests.Session()
    estimates=collect_estimates(root,now,cfg,fetcher,offline=offline)
    guidance=fetch_guidance(root,now,session,offline=offline)
    core.write(root/'reports/forward_estimates_60.json',estimates)
    core.write(root/'reports/issuer_guidance_60.json',guidance)
    return {'estimated_universe':estimates['universe_count'],
       'secondary_snapshots':estimates['snapshot_count'],
       'issuer_guidance_status':guidance['status'],'orders_enabled':False}


def attach(out:dict,root:Path)->dict:
    """Attach sourced research metadata without changing valuation status or targets."""
    estimates=core.read(root/'reports/forward_estimates_60.json',{}) or {}
    guidance=core.read(root/'reports/issuer_guidance_60.json',{}) or {}
    covered=estimates.get('companies') or {};mg=guidance.get('companies') or {}
    for row in out.get('companies',[]):
        t=row['ticker'];snap=covered.get(t,{})
        row['external_forward_earnings']={
           'status':snap.get('status','NOT COLLECTED'),
           'periods':snap.get('periods',{}),
           'source':snap.get('source'), 'source_url':snap.get('source_url'),
           'as_of_utc':snap.get('observed_at_utc'),
           'data_quality':'UNOFFICIAL_SECONDARY_ESTIMATES_NOT_VERIFIED',
           'usable_to_validate_intrinsic_value':False}
        revis=snap.get('revisions',{})
        row['earnings_revisions']={
           'status':'SECONDARY_ONLY_NOT_VALIDATED' if revis else 'NOT VALIDATED — DATED CONSENSUS REVISION SERIES UNAVAILABLE',
           'period_revisions':revis,'verified_revision_signal':None,
           'can_override_primary_evidence':False}
        row['issuer_forward_guidance']=(mg.get(t) if t in mg else {
           'status':'NO_SUBSTANTIVE_PRIMARY_GUIDANCE_DOCUMENT_COLLECTED',
           'reported_guidance':None})
        if row['validation_status']=='NOT VALIDATED':
            assert row['verified_intrinsic_value'] is None and row['selected_entry'] is None
        if row['orders_enabled'] is not False:raise ValueError('Trading safeguard violated')
    out['forward_research_coverage']={
      'company_snapshot_count':estimates.get('snapshot_count',0),
      'issuer_guidance_evidence_count':sum(x.get('status')=='ISSUER_REPORTED_GUIDANCE_CONFIRMED_IN_FILING_EXHIBIT' for x in mg.values()),
      'secondary_estimates_do_not_validate_intrinsic':True}
    return out



def coverage_report(root:Path,now:datetime|None=None)->dict:
    """Explicit per-company evidence backlog, distinct from investment rankings."""
    now=now or datetime.now(timezone.utc)
    val=core.read(root/'reports/valuation_60_latest.json',{}) or {}
    cache=core.read(root/'reports/primary_series_cache_60.json',{}) or {}
    future=core.read(root/'reports/forward_estimates_60.json',{}) or {}
    guidance=core.read(root/'reports/issuer_guidance_60.json',{}) or {}
    names,original=core.universe(root)
    latest={x['ticker']:x for x in val.get('companies',[])}
    company_cache=cache.get('companies',{})
    snapshots=future.get('companies',{})
    guide=guidance.get('companies',{})
    rows=[]
    cfg=core.read(root/'settings/championship_60.json',core.DEFAULT_ASSUMPTIONS)
    important=[str(x).upper() for x in cfg.get('priority_tickers',['NVDA'])]
    for obj in names:
        ticker=obj['ticker'];current=latest.get(ticker,{})
        primary=company_cache.get(ticker,{})
        vendor=snapshots.get(ticker,{})
        g=guide.get(ticker,{})
        # A model status alone does not prove provenance.  For the strictly
        # evidence-qualified research lists, also require the actual issuer
        # record URL and source hash saved by the 6.0 filing parser.
        source=current.get('primary_source_evidence')
        qualified_status=current.get('validation_status')=='PRIMARY_INPUTS_VALIDATED_FORECASTS_HYPOTHETICAL'
        source_ok=(isinstance(source,dict)
                   and str(source.get('url','')).startswith('https://data.sec.gov/api/xbrl/companyfacts/CIK')
                   and bool(re.fullmatch(r'[0-9a-f]{64}',str(source.get('source_hash_sha256','')))))
        eligible=bool(qualified_status and source_ok and not current.get('missing_evidence_flags'))
        base=core.pos(current.get('base')) if eligible else None
        selected_entry=core.pos(current.get('selected_entry')) if eligible else None
        price=core.pos(current.get('latest_dated_price'))
        data_flags=list(current.get('missing_evidence_flags',[]))
        if qualified_status and not source_ok:
            data_flags.append('PRIMARY_FILING_PROVENANCE_NOT_VERIFIABLE')
        if not current:data_flags.append('NO_PUBLISHED_6_0_VALUATION_ROW')
        rows.append({
          'ticker':ticker,'company':obj.get('company'),'universe':obj['universe'],
          'research_priority_only':ticker in important,
          'primary_financial_evidence_status':primary.get('status','NO_PRIMARY_FINANCIAL_SERIES_COLLECTED'),
          'primary_facts_observed_at_utc':primary.get('observed_utc'),
          'primary_facts_url':primary.get('source_url'),
          'secondary_forward_eps_status':vendor.get('status','NOT_COLLECTED'),
          'secondary_forward_eps_snapshot_at_utc':vendor.get('observed_at_utc'),
          'issuer_guidance_status':g.get('status','NO_PRIMARY_GUIDANCE_COLLECTED'),
          'issuer_guidance_source':g.get('source_url'),
          'valuation_validation_status':current.get('validation_status','NOT VALIDATED'),
          'missing_evidence_flags':data_flags,
          'price_as_of':current.get('price_as_of'),
          'latest_dated_price':price,
          'qualifies_for_further_intrinsic_review':bool(eligible),
          'below_assumed_base_intrinsic_value':(price<base if price is not None and base is not None else None),
          'below_selected_margin_of_safety_entry':(price<=selected_entry if price is not None and selected_entry is not None else None),
          'evidence_qualified_base_value':base,
          'selected_margin_of_safety_entry':selected_entry,
          'base_upside_pct':(round((base/price-1)*100,2) if price is not None and base is not None else None),
          'selected_margin_of_safety_pct':(current.get('selected_margin_of_safety_pct') if selected_entry is not None else None),
          'buy_signal':False,'orders_enabled':False})
    byticker={r['ticker']:r for r in rows}
    order=[t for t in important if t in byticker]
    qualifies=[r['ticker'] for r in rows if r['below_assumed_base_intrinsic_value'] is True and r['ticker'] not in order]
    order.extend(sorted(qualifies))
    order.extend([r['ticker'] for r in rows if r['universe']=='DISCOVERY' and r['ticker'] not in order])
    undervalued=sorted((r for r in rows if r['below_assumed_base_intrinsic_value'] is True),
                       key=lambda x:(-x['base_upside_pct'],x['ticker']))
    at_entry=sorted((r for r in rows if r['below_selected_margin_of_safety_entry'] is True),
                    key=lambda x:(-x['base_upside_pct'],x['ticker']))
    def research_priority(row):
        return {'ticker':row['ticker'],'price_as_of':row['price_as_of'],
                'last_daily_close':row['latest_dated_price'],
                'evidence_qualified_base_value':row['evidence_qualified_base_value'],
                'base_upside_pct':row['base_upside_pct'],
                'selected_margin_of_safety_pct':row['selected_margin_of_safety_pct'],
                'selected_margin_of_safety_entry':row['selected_margin_of_safety_entry'],
                'status':'EVIDENCE_QUALIFIED_RESEARCH_ONLY_NOT_ORDER','buy_signal':False,
                'orders_enabled':False}
    results={
     'schema_version':'6.0-coverage-progress-1','published_at_utc':now.isoformat(),
     'original_watchlist_count':len(original),'discovery_count':len(names)-len(original),
     'reported_count':len(rows),'primary_series_records_count':sum(t in company_cache for t in byticker),
     'secondary_estimate_snapshots_count':sum(t in snapshots for t in byticker),
     'primary_guidance_supported_count':sum(g.get('status')=='ISSUER_REPORTED_GUIDANCE_CONFIRMED_IN_FILING_EXHIBIT' for g in guide.values()),
     'evidence_qualified_model_count':sum(r['qualifies_for_further_intrinsic_review'] for r in rows),
     'validated_below_assumed_base_count':len(undervalued),
     'evidence_qualified_at_selected_margin_of_safety_count':len(at_entry),
     'evidence_qualified_below_base_research':list(map(research_priority,undervalued[:20])),
     'evidence_qualified_at_selected_margin_of_safety':list(map(research_priority,at_entry[:20])),
     'no_qualified_undervalued_candidates':not bool(undervalued),
     'research_priority_order_not_buy_recommendations':order,
     'companies':rows,'research_only':True,'orders_enabled':False,'orders_generated':0,
     'warning':'No fabricated targets. Primary filings cover some SEC-listed names only. Vendor forward estimates are NOT primary-verified, sector-specific ASX/ADR/specialist valuation evidence remains unavailable, and no trading is permitted.'}
    if len(rows)<200 or sum(r['universe']=='ORIGINAL_200' for r in rows)!=200:
        raise ValueError('Coverage must include all 200 original stocks')
    if any(r['orders_enabled'] is not False for r in rows):raise ValueError('No trading allowed')
    core.write(root/'reports/coverage_60.json',results)
    return results


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--mode',choices=['update','coverage'],required=True)
    p.add_argument('--root',type=Path,default=Path(__file__).resolve().parent)
    p.add_argument('--offline',action='store_true')
    args=p.parse_args()
    if args.mode=='coverage':
        r=coverage_report(args.root)
        print(json.dumps({k:v for k,v in r.items() if k!='companies'},indent=2))
    else:print(json.dumps(update(args.root,offline=args.offline),indent=2))

if __name__=='__main__':main()
