"""Championship 5.4 evidence gate: read-only primary disclosure verification.

A document containing an issuer-reported statement is NOT independent verification
of underlying economics. No text extraction, SEC data or scenario authorises a trade.
All inaccessible, ambiguous, missing or stale evidence fails closed.
"""
from __future__ import annotations
import hashlib
import io
import json
import math
import re
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SCHEMA = '5.4-substantive-evidence-1'
MAX_BYTES = 2_750_000
MAX_PDF_PAGES = 16
MAX_HTML_CHARS = 250_000
ALLOWED_FILINGS = {'www.sec.gov', 'sec.gov', 'data.sec.gov', 'dug.com', 'www.dug.com',
                   'announcements.asx.com.au', 'ir.penguinsolutions.com', 'ir.bitdeer.com'}
REPORT_FORMS = {'10-K','10-Q','10-K/A','10-Q/A','20-F','40-F'}


def clean(s: Any) -> str:
    return re.sub(r'\s+', ' ', str(s or '')).strip()


def strict_url(url: str, allowed: set[str] | None = None) -> bool:
    try:
        p = urlparse(url)
        return p.scheme == 'https' and p.hostname in (allowed or ALLOWED_FILINGS) and not p.username and not p.password and not p.port and not p.fragment
    except ValueError:
        return False


def number(value: Any) -> float | None:
    try:
        v = float(value)
        return v if math.isfinite(v) and v > 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.suppress = 0
    def handle_starttag(self, tag, attrs):
        if tag in ('style','script','noscript','svg'):
            self.suppress += 1
        elif tag in ('p','div','li','tr','h1','h2','h3','br','article','section'):
            self.parts.append('\n')
    def handle_endtag(self, tag):
        if tag in ('style','script','noscript','svg'):
            self.suppress = max(0, self.suppress - 1)
        elif tag in ('p','div','li','tr','h1','h2','h3','article','section'):
            self.parts.append('\n')
    def handle_data(self, data):
        if not self.suppress:
            self.parts.append(data)


def source_pages(data: bytes, mime: str) -> tuple[list[tuple[int, str]], str]:
    """Extract bounded actual PDF/HTML text. Never interpret URL slugs as evidence."""
    if data.startswith(b'%PDF-'):
        try:
            from pypdf import PdfReader
            pdf = PdfReader(io.BytesIO(data), strict=False)
            if pdf.is_encrypted:
                return [], 'ENCRYPTED_PDF'
            pages = [(i + 1, clean(p.extract_text() or ''))
                     for i, p in enumerate(pdf.pages[:MAX_PDF_PAGES])]
            return [(p,t) for p,t in pages if len(t) >= 70], 'PDF_TEXT_EXTRACTED'
        except Exception:
            return [], 'PDF_EXTRACTION_ERROR'
    if mime not in ('text/html','application/xhtml+xml'):
        return [], 'UNSUPPORTED_CONTENT_TYPE'
    if not (b'<html' in data[:1500].lower() or b'<!doctype html' in data[:1500].lower()):
        return [], 'NOT_HTML_DOCUMENT'
    try:
        parser = TextParser()
        parser.feed(data.decode('utf-8', errors='replace')[:MAX_HTML_CHARS])
        text = clean(''.join(parser.parts))
        return ([(1,text)] if len(text) > 100 else []), 'HTML_TEXT_EXTRACTED'
    except Exception:
        return [], 'HTML_EXTRACTION_ERROR'


def check_primary_content(record: dict, claim_rules: dict, session: Any,
                          *, allow_network: bool, now: datetime) -> dict:
    """Verify issuer in document and explicitly configured claim phrases nearby.

    A matched phrase proves ONLY that the identified issuer's document reports it.
    We do NOT assert independent truth, profitability, valuation or transaction.
    """
    url = str(record.get('evidence_url') or record.get('source_url') or '')
    ticker = str(record.get('ticker') or '').upper()
    issuer = claim_rules.get(ticker) if isinstance(claim_rules, dict) else None
    if issuer is None and len(clean(record.get('company'))) >= 9:
        # A new SEC filer can be issuer-identified without inventing a claim.
        issuer = {'issuer_aliases':[clean(record.get('company'))], 'claims':[]}
    out = {'ticker':ticker, 'source_url':url, 'document_read':False,
           'issuer_in_document':False, 'claim_verified':False,
           'issuer_claims_supported_in_source':[], 'evidence_flags':[],
           'checked_at_utc':now.isoformat(), 'orders_enabled':False}
    if not strict_url(url):
        out['evidence_flags'].append('UNTRUSTED_OR_UNSUPPORTED_SOURCE_HOST'); return out
    if not issuer or not isinstance(issuer.get('issuer_aliases'),list) or not issuer['issuer_aliases']:
        out['evidence_flags'].append('NO_CONFIGURED_ISSUER_IDENTITY'); return out
    if not allow_network or session is None:
        out['evidence_flags'].append('DOCUMENT_NOT_FETCHED'); return out
    try:
        response = session.get(url,timeout=18,allow_redirects=False,stream=True)
        try:
            status = int(response.status_code)
            out['http_status'] = status
            if status != 200:
                out['evidence_flags'].append('DOCUMENT_HTTP_'+str(status)); return out
            length = response.headers.get('Content-Length')
            if length and int(length)>MAX_BYTES:
                out['evidence_flags'].append('DOCUMENT_TOO_LARGE'); return out
            mime = str(response.headers.get('Content-Type','')).split(';')[0].strip().lower()
            chunks = [];total=0
            for chunk in response.iter_content(chunk_size=32768):
                total+=len(chunk)
                if total>MAX_BYTES:
                    out['evidence_flags'].append('DOCUMENT_TOO_LARGE'); return out
                chunks.append(chunk)
            body=b''.join(chunks)
        finally:
            response.close()
    except Exception as exc:
        out['evidence_flags'].append('DOCUMENT_FETCH_'+type(exc).__name__.upper());return out
    pages, extraction = source_pages(body,mime)
    out.update(extraction_status=extraction,sha256=hashlib.sha256(body).hexdigest(),
               document_size_bytes=len(body),content_type=mime,extracted_pages=len(pages))
    if not pages:
        out['evidence_flags'].append('DOCUMENT_TEXT_UNAVAILABLE');return out
    out['document_read']=True
    whole=' '.join(t.lower() for _,t in pages)
    date_context=' '.join(t[:7000] for _,t in pages[:2]).lower()[:12000]
    # Multi-word issuer aliases use word boundaries; a bare symbol like EOS is insufficient.
    aliases=[clean(a).lower() for a in issuer['issuer_aliases'] if len(clean(a))>=8]
    if not any(re.search(r'(?<!\w)'+re.escape(x)+r'(?!\w)',whole) for x in aliases):
        out['evidence_flags'].append('ISSUER_NAME_NOT_IN_CONTENT');return out
    out['issuer_in_document']=True
    # Issuer disclosure date is a separate field, not inferred from the URL slug.
    # A recognised date anywhere in an issuer-authored document supports source dating
    # but is not proof that the financial assertion is true or belongs to that period.
    declared=str(record.get('evidence_date') or '')[:10]
    out['declared_source_date']=declared or None
    out['document_date_found']=False
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}',declared):
        try:
            from datetime import date
            d=date.fromisoformat(declared)
            month_full=d.strftime('%B');month_short=d.strftime('%b')
            patterns=[declared, d.strftime('%d/%m/%Y'), d.strftime('%d-%m-%Y'),
                 f'{d.day} {month_full} {d.year}', f'{month_full} {d.day}, {d.year}',
                 f'{d.day} {month_short} {d.year}', f'{month_short} {d.day}, {d.year}']
            out['document_date_found']=any(re.search(r'(?<!\w)'+re.escape(pattern)+r'(?!\w)',date_context,re.I)
                                          for pattern in patterns)
        except ValueError:
            pass
    if not out['document_date_found']:
        out['evidence_flags'].append('ISSUER_DISCLOSURE_DATE_NOT_CONFIRMED_IN_CONTENT')
    claims=issuer.get('claims',[])
    if not claims:
        out['evidence_flags'].append('NO_EXPLICIT_CLAIM_TO_TEST');return out
    for claim in claims:
        if not isinstance(claim,dict) or not claim.get('id') or not claim.get('required_terms'):
            continue
        terms=[clean(x).lower() for x in claim['required_terms'] if len(clean(x))>=3]
        if len(terms)<2:continue
        found=None
        # A bounded 1000-character window is required; wide scattered keywords do not qualify.
        for page,text in pages:
            low=text.lower()
            for t in terms:
                for match in list(re.finditer(re.escape(t),low))[:40]:
                    lo=max(0,match.start()-400);hi=min(len(text),match.end()+600)
                    passage=low[lo:hi]
                    if all(term in passage for term in terms):
                        found=(page,clean(text[lo:hi])[:850]);break
                if found:break
            if found:break
        if found:
            out['issuer_claims_supported_in_source'].append({'claim_id':claim['id'],
                'verification_level':'ISSUER_REPORTS_STATEMENT_NOT_INDEPENDENTLY_AUDITED',
                'source_url':url,'page':found[0],'evidence_excerpt':found[1],
                'checked_at_utc':now.isoformat(),'sha256':out['sha256']})
        else:
            out['evidence_flags'].append('CLAIM_NOT_LOCATED_'+str(claim['id'])[:55])
    out['issuer_claims_found_in_text']=bool(out['issuer_claims_supported_in_source'])
    # Distinguish an exact reported statement from a dated verified disclosure.
    out['claim_verified']=bool(out['issuer_claims_found_in_text'] and out['document_date_found'])
    if not out['claim_verified']:out['evidence_flags'].append('NO_DATED_CLAIM_SUPPORT_CONFIRMED')
    return out


def enrich_queue(queue: dict, rules: dict, session: Any, now: datetime,
                 allow_network: bool) -> dict:
    enriched=dict(queue);records=[]
    for item in queue.get('records',[]):
        rec=dict(item)
        check=check_primary_content({**rec,'evidence_url':rec.get('source_url')},rules,session,
                                    allow_network=allow_network,now=now)
        rec['substantive_evidence']=check
        rec['primary_claim_verified']=check['claim_verified']
        rec['primary_source_verified']=bool(check['document_read'] and check['issuer_in_document'])
        rec['in_source_verified_research_queue']=rec['primary_source_verified']
        if not check['claim_verified']:
            rec['gaps']=list(dict.fromkeys([*rec.get('gaps',[]),'PRIMARY_CLAIM_NOT_SUBSTANTIATED_IN_DOCUMENT']))
        rec['decision']='SOURCE-CHECKED RESEARCH ONLY — ISSUER CLAIM IS NOT INDEPENDENTLY AUDITED'
        records.append(rec)
    enriched.update(schema_version=SCHEMA,records=records,
       source_verified_reference_count=sum(x['primary_source_verified'] for x in records),
       not_yet_verified_count=sum(not x['primary_source_verified'] for x in records),
       claim_verified_count=sum(x['primary_claim_verified'] for x in records),
       warning='Issuer/source text and configured claims checked. Matches show only what issuer reports; do not independently validate financial statements, economics, or investment merit.',
       orders_enabled=False,original_200_unchanged=True)
    return enriched


def latest_xbrl_fact(companyfacts: dict, taxonomy: str, tag: str, units: str,
                     now: datetime, *, require_instant: bool) -> dict | None:
    candidates=companyfacts.get('facts',{}).get(taxonomy,{}).get(tag,{}).get('units',{}).get(units,[])
    if not isinstance(candidates,list):return None
    allowed=[]
    for x in candidates:
        if x.get('form') not in REPORT_FORMS:continue
        filed=x.get('filed');end=x.get('end')
        try:
            f=datetime.fromisoformat(filed).replace(tzinfo=timezone.utc)
            e=datetime.fromisoformat(end).replace(tzinfo=timezone.utc)
        except (ValueError,TypeError):continue
        if (now-f).days not in range(0,551) or e>now or (now-e).days>600:continue
        val=number(x.get('val'))
        if not val:continue
        start=x.get('start')
        if require_instant and start:continue
        if not require_instant:
            if not start:continue
            try: span=(e-datetime.fromisoformat(start).replace(tzinfo=timezone.utc)).days
            except (ValueError,TypeError):continue
            if not 70<=span<=400:continue
        allowed.append((filed,end,x))
    if not allowed:return None
    best=sorted(allowed,key=lambda a:(a[0],a[1]),reverse=True)[0][-1]
    return {'value':best['val'],'unit':units,'start':best.get('start'),'end':best.get('end'),
            'form':best.get('form'),'filed':best.get('filed'),'accession':best.get('accn')}


def primary_sec_financials(ticker: str,companyfacts: dict,now: datetime) -> dict:
    """Read official SEC financial tags; do not conflate annual / quarterly / TTM."""
    out={'ticker':ticker,'data_source':'SEC_XBRL_COMPANYFACTS','issuer_name':companyfacts.get('entityName'),
         'shares_outstanding':None,'operating_cash_flow':None,'capital_expenditure':None,
         'free_cash_flow_same_period':None,'economic_inputs_verified':False,'flags':[],
         'orders_enabled':False}
    shares=latest_xbrl_fact(companyfacts,'dei','EntityCommonStockSharesOutstanding','shares',now,require_instant=True)
    if shares is None:
        shares=latest_xbrl_fact(companyfacts,'us-gaap','CommonStockSharesOutstanding','shares',now,require_instant=True)
    if shares is None:out['flags'].append('PRIMARY_SHARES_OUTSTANDING_MISSING')
    out['shares_outstanding']=shares
    ocf=latest_xbrl_fact(companyfacts,'us-gaap','NetCashProvidedByUsedInOperatingActivities','USD',now,require_instant=False)
    cap=latest_xbrl_fact(companyfacts,'us-gaap','PaymentsToAcquirePropertyPlantAndEquipment','USD',now,require_instant=False)
    out['operating_cash_flow']=ocf;out['capital_expenditure']=cap
    if ocf and cap and (ocf['start'],ocf['end'])==(cap['start'],cap['end']) and ocf['accession']==cap['accession']:
        out['free_cash_flow_same_period']={'value_usd':round(ocf['value']-cap['value'],2),
           'period_start':ocf['start'],'period_end':ocf['end'],'accession':ocf['accession'],
           'source':'SEC_XBRL_TAGS_OCF_MINUS_CAPEX'}
    else:
        out['flags'].append('NO_MATCHED_OCF_CAPEX_PERIOD_FROM_SAME_FILING')
    out['economic_inputs_verified']=bool(shares and out['free_cash_flow_same_period'])
    if not isinstance(companyfacts.get('cik'),(int,str)):
        out['flags'].append('SEC_CIK_MISSING')
    return out


def verify_model_economics(model: dict, sec_facts: dict | None) -> dict:
    """Cross-check model shares and FCF against matching SEC primary facts.

    False or absent evidence => rank ineligible. Never double-count dilution.
    """
    out={'model_primary_verified':False,'verified_shares':None,'dilution_reference_ratio':None,'flags':[],
         'filing_url':None,'filing_share_count':None,'issuer_reported_fcf':None}
    if not isinstance(sec_facts,dict) or sec_facts.get('status')!='ok':
        out['flags'].append('SEC_PRIMARY_FINANCIALS_UNAVAILABLE');return out
    facts=sec_facts.get('facts',{})
    shares=facts.get('shares_outstanding') or {}
    fin_shares=number(shares.get('value'));feed_shares=number(model.get('shares_input'))
    if not fin_shares or not feed_shares:
        out['flags'].append('ISSUED_SHARE_COUNTS_NOT_COMPARABLE');return out
    ratio=feed_shares/fin_shares
    out['filing_share_count']=fin_shares
    out['verified_shares']=fin_shares
    out['dilution_reference_ratio']=round(ratio,5)
    if not 0.90<=ratio<=1.10:
        out['flags'].append('PRIMARY_VS_VENDOR_SHARES_DISAGREE_OVER_10PCT');return out
    if model.get('model_type')=='FINANCIAL_BOOK_ROE':
        out['flags'].append('BANK_ROE_BOOK_INPUTS_NOT_PRIMARY_VERIFIED');return out
    fcf=facts.get('free_cash_flow_same_period') or {}
    value=number(fcf.get('value_usd'))
    model_fcf=number(model.get('fcf_input'))
    if not value or not model_fcf or str(model.get('fundamental_currency')).upper()!='USD':
        out['flags'].append('FCF_MISSING_OR_CURRENCY_NOT_USD');return out
    # Different accounting periods are not equated. Only compare similar periods.
    fiscal=str(model.get('fiscal_as_of') or '')[:10]
    as_of=str(fcf.get('period_end') or '')
    if not fiscal or not as_of or fiscal != as_of:
        out['flags'].append('MODEL_FCF_AND_SEC_FILING_PERIOD_NOT_IDENTICAL');return out
    deviation=abs(value/model_fcf-1)
    out['issuer_reported_fcf']={'value_usd':value,'period_end':as_of,'deviation_from_vendor_pct':round(100*deviation,2)}
    if deviation>0.25:
        out['flags'].append('FCF_SOURCE_DISAGREEMENT_OVER_25PCT');return out
    out['model_primary_verified']=True
    out['filing_url']=sec_facts.get('source_url')
    return out


def asymmetry_report(scan:dict,valuation:dict,financials:dict, now:datetime,
                     *,stress_bear:float=.15,stress_base:float=.05,stress_bull:float=.0) -> dict:
    """Conservative scenario asymmetry, only rank if SEC economics and share count reconcile.
    Stress factors are hypotheticals, NOT observed future issuance.
    """
    if any(not 0<=x<=.75 for x in (stress_bear,stress_base,stress_bull)):
        raise ValueError('Invalid dilution stress inputs')
    m={str(x.get('ticker')):x for x in valuation.get('stocks',[]) if isinstance(x,dict)}
    facts=financials.get('companies',{}) if isinstance(financials,dict) else {}
    eligible=[];unverified=[];blocked_count=0
    for sr in scan.get('stocks',[]):
        ticker=str(sr.get('ticker',''))
        v=m.get(ticker) or {}
        if not str(v.get('model_status','')).startswith('INDICATIVE'):
            blocked_count+=1;continue
        price=number(sr.get('last_daily_close'))
        vals=[number(v.get(z)) for z in ('bear_value','base_value','bull_value')]
        if not price or any(x is None for x in vals) or not vals[0]<=vals[1]<=vals[2]:
            blocked_count+=1;continue
        check=verify_model_economics(v,facts.get(ticker))
        shares_ratio=check.get('dilution_reference_ratio')
        if not check['model_primary_verified']:
            # No verified correction multiplier; report sensitivity from vendor basis, label unverified.
            shares_ratio=1.0
        adjusted={name:round(value*shares_ratio/(1+stress),4)
                  for name,value,stress in zip(('bear','base','bull'),vals,(stress_bear,stress_base,stress_bull))}
        downside=max(0.,1-adjusted['bear']/price)
        base_up=adjusted['base']/price-1
        upside=max(0.,base_up)
        ratio=round(upside/max(.05,downside),3)
        row={'ticker':ticker,'company':sr.get('company'),'currency':sr.get('currency'),
             'last_daily_close':price,'dilution_adjusted_values':adjusted,
             'hypothetical_future_dilution_rates_pct':{'bear':round(stress_bear*100,2),
                'base':round(stress_base*100,2),'bull':round(stress_bull*100,2)},
             'issuer_filing_share_count':check.get('filing_share_count'),
             'vendor_share_count':number(v.get('shares_input')),
             'share_basis_adjustment':shares_ratio if check['model_primary_verified'] else None,
             'base_upside_pct':round(base_up*100,2),'bear_downside_pct':round(-downside*100,2),
             'asymmetry_ratio_not_probability':ratio,
             'source_flags':check['flags'], 'primary_model_economics_verified':check['model_primary_verified'],
             'verified_buy_signal':False,'orders_enabled':False,
             'valuation_warning':'Future issuance stresses assume no incremental value from proceeds; actual dilution, warrants, convertibles and capital raises require independent review'}
        if check['model_primary_verified'] and upside>0:
            eligible.append(row)
        else:
            row['rank_blocked_reason']='MISSING_PRIMARY_ECONOMIC_INPUT_VERIFICATION_OR_NO_BASE_UPSIDE'
            unverified.append(row)
    eligible.sort(key=lambda r:(-r['asymmetry_ratio_not_probability'],-r['base_upside_pct'],r['ticker']))
    unverified.sort(key=lambda r:(-r['asymmetry_ratio_not_probability'],r['ticker']))
    return {'schema_version':'5.4-asymmetry-evidence-gated-1','published_at_utc':now.isoformat(),
            'universe_count':len(scan.get('stocks',[])),
            'source_valuation_snapshot_utc':valuation.get('summary',{}).get('timestamp_utc'),
            'verification_coverage':'FIRST_PASS_SEC_FILINGS_FOR_PRELIMINARY_TOP10_ONLY; NOT ALL_200',
            'evidence_qualified_count':len(eligible),'unverified_model_count':len(unverified),
            'not_modelled_or_invalid_count':blocked_count,
            'evidence_qualified_top10':[{'rank':i+1,**x} for i,x in enumerate(eligible[:10])],
            'unverified_scenario_review_queue':[{'research_position':i+1,**x} for i,x in enumerate(unverified[:10])],
            'missing_evidence_policy':'DO NOT PROMOTE UNOFFICIAL YAHOO VALUATIONS INTO EVIDENCE-QUALIFIED TOP TEN',
            'future_dilution_stress_is_assumed_not_observed':True,
            'research_only':True,'orders_enabled':False,
            'warning':'No expected return or win probabilities; ratio compares hypothetical base upside to bear loss. No trading eligibility.'}


def fetch_sec_financials(models:list[dict],session:Any, now:datetime, *, user_agent:str,
                         max_companies:int=10,existing:dict|None=None, allow_network:bool=True) -> dict:
    out={'schema_version':'5.4-sec-primary-financials-1','published_at_utc':now.isoformat(),
         'source':'SEC companyfacts XBRL, original filer data','companies':{},'orders_enabled':False,
         'network_access_configured':bool('@' in user_agent),'research_only':True}
    if not allow_network or not session or '@' not in user_agent:
        out['status']='NOT_FETCHED_OFFLINE_OR_MISSING_CONTACT';return out
    try:
        import requests
        session.headers.update({'User-Agent':user_agent,'Accept':'application/json'})
        url='https://www.sec.gov/files/company_tickers_exchange.json'
        r=session.get(url,timeout=18,allow_redirects=False)
        r.raise_for_status()
        mapping=r.json()
        fields=[str(x).lower() for x in mapping.get('fields',[])]
        index={k:fields.index(k) for k in ('cik','ticker','exchange')}
        valid_exchange={'NASDAQ','NYSE','NYSE AMERICAN','NYSE ARCA'}
        lookup={str(a[index['ticker']]).upper():int(a[index['cik']]) for a in mapping.get('data',[])
                if str(a[index['exchange']]).upper() in valid_exchange}
    except Exception as exc:
        out['status']='SEC_TICKER_DIRECTORY_UNAVAILABLE';out['reason']=type(exc).__name__;return out
    eligible=[m for m in models if str(m.get('model_status','')).startswith('INDICATIVE')]
    eligible=eligible[:max_companies]  # preserve Top-10 research priority order
    for m in eligible:
        ticker=str(m.get('ticker','')).upper()
        cik=lookup.get(ticker)
        if not cik:
            out['companies'][ticker]={'status':'NO_SEC_LISTING_MATCH','facts':{},'orders_enabled':False};continue
        url=f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json'
        try:
            r=session.get(url,timeout=18,allow_redirects=False)
            r.raise_for_status()
            raw=r.json()
            if int(raw.get('cik'))!=cik:
                raise ValueError('SEC companyfacts CIK mismatch')
            facts=primary_sec_financials(ticker,raw,now)
            out['companies'][ticker]={'status':'ok','source_url':url,'cik':cik,'facts':facts,'orders_enabled':False}
        except Exception as exc:
            out['companies'][ticker]={'status':'SEC_COMPANYFACTS_UNAVAILABLE','reason':type(exc).__name__,
                                      'source_url':url,'facts':{},'orders_enabled':False}
        # Complies with SEC fair access without attempting to defeat server restrictions.
        time.sleep(.35)
    out['status']='PARTIAL_OR_COMPLETE_WITH_PER_ISSUER_STATUS'
    out['verified_share_count_sources']=sum(bool((x.get('facts',{}).get('shares_outstanding')))
                                  for x in out['companies'].values())
    return out


def main() -> None:
    import argparse
    from pathlib import Path
    parser=argparse.ArgumentParser()
    parser.add_argument('--mode',choices=['financials'],required=True)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parent)
    parser.add_argument('--offline',action='store_true')
    args=parser.parse_args()
    root=args.root
    from intelligence_layer_51 import read,write,valuation_top10,assert_safety
    scan=read(root/'reports/latest.json')
    val=read(root/'reports/valuation_latest.json')
    assert_safety(scan)
    if not isinstance(val,dict):raise ValueError('Missing valuation report')
    report=valuation_top10(scan,val,datetime.now(timezone.utc))
    names=[x['ticker'] for x in report['ranked_top_10']]
    by_ticker={x.get('ticker'):x for x in val.get('stocks',[])}
    models=[by_ticker[x] for x in names if x in by_ticker]
    if args.offline:
        session=None
    else:
        import requests
        session=requests.Session()
    import os
    out=fetch_sec_financials(models,session,datetime.now(timezone.utc),
            user_agent=os.environ.get('SEC_USER_AGENT',''),
            max_companies=10,allow_network=not args.offline)
    out['sampled_model_tickers']=names
    out['coverage']='BOUNDED_FIRST_PASS_RESEARCH_TOP10_ONLY; NOT COMPLETE 200 STOCK FILING VERIFICATION'
    write(root/'reports/primary_financials_latest.json',out)
    print(json.dumps({'status':out.get('status'),'sampled_model_tickers':names,
                      'available_filing_shares':out.get('verified_share_count_sources',0),
                      'orders_enabled':False}))

if __name__=='__main__':
    main()
