"""Championship 8.1: timestamped, research-only SEC catalyst watch and point-in-time audit.
No premarket executable feed; no orders, no inferred guaranteed missed buys.
"""
import csv
import json
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse

CATALYST = re.compile(r'\b(contract|agreement|approval|fda|earnings|guidance|acquisition|trial|award|merger)\b', re.I)
DILUTION = re.compile(r'\b(at.the.market|shelf registration|public offering|private placement|convertible|warrant|equity line|dilution|going concern)\b', re.I)


def utc_now():
    return datetime.now(timezone.utc)


def parse_utc(value):
    if not value:
        return None
    try:
        d = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def classify_filing(filing, observed_at):
    """Filing metadata only; keywords are screening flags, NOT confirmed event contents."""
    title = str(filing.get('title') or '')[:400]
    summary = str(filing.get('summary') or '')[:1500]
    url = str(filing.get('url') or '')
    timestamp = parse_utc(filing.get('published_at'))
    if urlparse(url).hostname not in ('www.sec.gov', 'sec.gov') or not url.startswith('https://'):
        return None
    if not timestamp or timestamp > observed_at + timedelta(minutes=5):
        return None
    body = title + ' ' + summary
    return {'ticker':filing.get('ticker'), 'published_at_utc':timestamp.isoformat(),
            'first_observed_at_utc':observed_at.isoformat(), 'url':url,
            'title':title, 'catalyst_keyword_flag':bool(CATALYST.search(body)),
            'dilution_keyword_flag':bool(DILUTION.search(body)),
            'primary_document_contents_verified':False,
            'timing_precedes_market_move_verified':False,
            'classification':'OFFICIAL_FILING_POINTER_ONLY'}


def evaluate_snapshot(current, previous):
    """Evaluate the full monitored cohort, not only winners; no forward returns guessed."""
    prior = {r['ticker']:r for r in previous.get('observations', []) if r.get('ticker')}
    out=[]
    for r in current:
        ticker=r.get('ticker')
        if not ticker:
            continue
        before=prior.get(ticker)
        prior_price=before.get('price') if before else None
        price=r.get('price')
        change=None
        if isinstance(price,(int,float)) and isinstance(prior_price,(int,float)) and prior_price>0:
            change=round((price/prior_price-1)*100,2)
        out.append({'ticker':ticker,'price':price,'previous_price':prior_price,
                    'observed_change_pct':change,
                    'previous_observed_at_utc':before.get('observed_at_utc') if before else None,
                    'observed_at_utc':r.get('observed_at_utc'),
                    'is_large_positive_move':change is not None and change>=50,
                    'is_large_negative_move':change is not None and change<=-50,
                    'entry_feasibility':'NOT_VERIFIED', 'signal_was_pre_move':'NOT_VERIFIED'})
    return out


def read_monitoring(root):
    """Use available 200-stock daily snapshot as a bounded cohort; no false live quote claim."""
    p=root/'reports'/'latest.csv'
    if not p.exists():
        return [],'missing_latest_csv'
    with p.open(newline='',encoding='utf-8-sig') as f:
        rows=list(csv.DictReader(f))
    if not rows:
        return [],'empty_latest_csv'
    fields=rows[0].keys()
    col=next((x for x in ('last_close','latest_close','last_price','price','close','last_daily_close') if x in fields),None)
    if not col:
        return [],'unrecognized_price_column'
    result=[]
    for r in rows:
        try:
            price=float(r[col]); price=price if 0<price<1e9 else None
        except (TypeError,ValueError):
            price=None
        result.append({'ticker':r.get('ticker'),'price':price,'observed_at_utc':utc_now().isoformat()})
    return result,'daily_bars_not_executable'


def run(root=Path('.'), offline=False, fetcher=None):
    root=Path(root); reports=root/'reports';reports.mkdir(parents=True,exist_ok=True)
    now=utc_now()
    old_path=reports/'catalyst_radar_81_latest.json'
    try:
        previous=json.loads(old_path.read_text()) if old_path.exists() else {}
    except (OSError,ValueError):
        previous={}
    observations, quote_status=read_monitoring(root)
    cohort=evaluate_snapshot(observations,previous)
    filings=[]; sec_status='offline_not_checked' if offline else 'not_configured'
    ua=os.getenv('SEC_USER_AGENT','')
    # Only access SEC when a legitimate contact address is configured. Never fabricate one.
    if not offline and re.search(r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b',ua):
        try:
            if fetcher is None:
                import requests
                def fetcher():
                    resp=requests.get('https://www.sec.gov/cgi-bin/browse-edgar',params={
                        'action':'getcurrent','type':'8-K','output':'atom','count':100},
                        headers={'User-Agent':ua,'Accept':'application/atom+xml'},timeout=18)
                    resp.raise_for_status()
                    return resp.text
            from xml.etree import ElementTree as ET
            xml=ET.fromstring(fetcher())
            ns={'a':'http://www.w3.org/2005/Atom'}
            for entry in xml.findall('a:entry',ns):
                link=entry.find('a:link',ns)
                url=link.get('href','') if link is not None else ''
                record=classify_filing({'url':url,'title':entry.findtext('a:title','',ns),
                    'summary':entry.findtext('a:summary','',ns),
                    'published_at':entry.findtext('a:updated','',ns)},now)
                if record and parse_utc(record['published_at_utc'])>=now-timedelta(days=3):
                    filings.append(record)
            sec_status='ok_filing_pointers_only'
        except Exception as exc:
            sec_status='source_error_'+type(exc).__name__
    report={'schema_version':'8.1-research-only','generated_at_utc':now.isoformat(),
            'orders_enabled':False,'buy_signals_generated':0,
            'live_premarket_quote_feed':False,'sec_status':sec_status,
            'quote_status':quote_status,'filing_pointers':filings,
            'observations':observations,'cohort_comparisons':cohort,
            'missed_opportunity_audit_validated':False,
            'limitations':['SEC feed contains filing pointers, not verified catalysts or dilution analysis',
                'SEC feed has no reliable ticker mapping in this module; never infer one',
                'daily prices are not premarket/executable and may be stale',
                'first observation is run time, not necessarily first public availability',
                'cohort comparison is observation-to-observation, not a controlled backtest',
                'winning and losing observations retained; no hindsight buy claims']}
    old_path.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    return report

if __name__=='__main__':
    r=run()
    print(json.dumps({k:r[k] for k in ('sec_status','quote_status','orders_enabled','missed_opportunity_audit_validated')}))
