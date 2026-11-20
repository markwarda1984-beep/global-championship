"""Research-only compatibility bridge. Championship 6.0 is the ONLY active source of entry levels.

Legacy Yahoo watch-entry, manually entered provisional levels, and technical zones
are not intrinsic valuations. Old schema columns remain readable but are retired.
Never promotes legacy buy flags, never sends orders, and refuses mismatched price dates.
"""
import json
import math
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VALID_STATUS = 'PRIMARY_INPUTS_VALIDATED_FORECASTS_HYPOTHETICAL'


def numeric(value):
    try:
        n = float(value)
        return n if math.isfinite(n) and n > 0 else None
    except (ValueError, TypeError, OverflowError):
        return None


def checked_championship60(c60, tickers):
    if not isinstance(c60, dict) or not c60:
        return {}
    if c60.get('orders_enabled') is not False or c60.get('orders_generated') != 0:
        raise ValueError('Unsafe Championship 6.0 report')
    if c60.get('original_watchlist_count') != 200 or c60.get('reported_count') != len(c60.get('companies', [])):
        raise ValueError('Incomplete Championship 6.0 report')
    result={}
    for row in c60['companies']:
        if not isinstance(row, dict) or row.get('orders_enabled') is not False:
            raise ValueError('Unsafe or malformed Championship 6.0 row')
        t=str(row.get('ticker','')).upper()
        if not t or t in result: raise ValueError('Duplicate/missing 6.0 ticker')
        result[t]=row
    if not tickers <= set(result):
        raise ValueError('Some original 200 names missing from 6.0')
    return result


def evidence_entry(r, ticker, price, ccy, quote_date):
    if not r or r.get('validation_status') != VALID_STATUS:
        return None
    source=r.get('primary_source_evidence') or {}
    if not source.get('source_hash_sha256') or not source.get('url'):
        return None
    if r.get('missing_evidence_flags') or r.get('orders_enabled') is not False or r.get('research_only') is not True:
        return None
    if r.get('price_currency') != ccy or r.get('price_as_of') != quote_date:
        return None
    if price is None or numeric(r.get('latest_dated_price')) != price:
        return None
    entries=r.get('margin_of_safety_entries') or {}
    if not all(numeric(entries.get(f'{n}pct')) for n in (10,15,20)):
        return None
    if r.get('selected_margin_of_safety_pct') not in (10,15,20):
        return None
    selected=numeric(r.get('selected_entry'))
    if not selected or abs(selected-entries[f"{r['selected_margin_of_safety_pct']}pct"])>0.0002:
        return None
    if not (numeric(r.get('bear')) and numeric(r.get('base')) and numeric(r.get('bull'))):
        return None
    return r


def build(scan, valuation=None, championship_60=None):
    stocks=scan['stocks']
    symbols=[str(x['ticker']).upper() for x in stocks]
    if len(symbols)!=200 or len(set(symbols))!=200:
        raise ValueError('Scan must contain exactly 200 unique stocks')
    if scan.get('orders_enabled') is True or scan.get('trade_execution_enabled') is True:
        raise ValueError('Unsafe legacy scanner state')
    val=valuation or {}
    valrows=val.get('stocks', [])
    val_by={str(x['ticker']).upper():x for x in valrows}
    c60=checked_championship60(championship_60,set(symbols))
    out=[]
    for stock in stocks:
        ticker=str(stock['ticker']).upper()
        last=numeric(stock.get('price'))
        currency=stock.get('currency')
        date=stock.get('quote_date')
        row60=c60.get(ticker)
        passed=evidence_entry(row60,ticker,last,currency,date)
        selected=numeric(passed.get('selected_entry')) if passed else None
        distance=round((last/selected-1)*100,2) if last and selected else None
        model=val_by.get(ticker,{})
        status=VALID_STATUS if passed else 'NOT VALIDATED'
        out.append({
            'ticker':ticker,'company':stock.get('name'),'currency':currency,
            'last_daily_close':last,'quote_date':date,
            # Compatibility keys are null by design: never resurrect US$33.3938.
            'provisional_entry':None,
            'entry_basis':'RETIRED — UNVERIFIED ENTRY CALCULATION DISABLED',
            'pct_above_entry':None,'absolute_distance_pct':None,
            'entry_retirement_version':'CHAMPIONSHIP_6_0_ONLY',
            'validation_status_60':status,
            'verified_intrinsic_value_60':numeric(passed.get('verified_intrinsic_value')) if passed else None,
            'bear_60':numeric(passed.get('bear')) if passed else None,
            'base_60':numeric(passed.get('base')) if passed else None,
            'bull_60':numeric(passed.get('bull')) if passed else None,
            'margin_of_safety_entries_60':(passed.get('margin_of_safety_entries') if passed else
                                           {'10pct':None,'15pct':None,'20pct':None}),
            'selected_entry_60':selected,
            'selected_margin_of_safety_pct_60':passed.get('selected_margin_of_safety_pct') if passed else None,
            'pct_above_selected_entry_60':distance,
            'source_confidence_60':row60.get('source_confidence','NOT COLLECTED') if row60 else 'NOT COLLECTED',
            'missing_evidence_flags_60':row60.get('missing_evidence_flags', ['CHAMPIONSHIP_6_0_REPORT_MISSING']) if row60 else ['CHAMPIONSHIP_6_0_REPORT_MISSING'],
            'data_status':stock.get('data_status'),
            'model_status':model.get('model_status') or 'NO WEEKLY MODEL',
            'valuation_as_of_utc':val.get('summary',{}).get('timestamp_utc'),
            'buy_readiness_pct':None,
            'buy_readiness_status':(passed.get('buy_readiness',{}).get('status') if passed else 'NOT VALIDATED — NO ENTRY LEVEL'),
            'decision':'RESEARCH ONLY — NOT AN ORDER',
        })
    closest=sorted([r for r in out if r['pct_above_selected_entry_60'] is not None],
                   key=lambda r:(abs(r['pct_above_selected_entry_60']),r['ticker']))[:10]
    return {
        'schema_version':'6.0-report-bridge-entry-retirement-1',
        'published_at_utc':datetime.now(timezone.utc).isoformat(),
        'scan_utc':scan.get('scan_utc'),'scan_sydney':scan.get('scan_sydney'),
        'price_source':scan.get('data_quality'),
        'valuation_as_of_utc':val.get('summary',{}).get('timestamp_utc'),
        'valuation_source':val.get('summary',{}).get('source'),
        'universe_count':200,
        'price_available_count':sum(r['last_daily_close'] is not None for r in out),
        'model_available_count':sum(r['model_status'].startswith('INDICATIVE') for r in out),
        'valuation_rows_count':len(valrows),
        'closest_to_buy_top_10':closest,  # retained legacy key; 6.0 research ONLY
        'closest_research_entries_top_10_60':closest,
        'entry_eligible_count_60':len([r for r in out if r['selected_entry_60'] is not None]),
        'retired_legacy_provisional_entry_count':200,
        'stocks':out,'bitcoin':scan.get('bitcoin',{}),
        'research_only':True,'orders_enabled':False,
        'warning':'Legacy provisional entries (including NVIDIA old unverified target) RETIRED. '
                  'Only validated issuer-primary 6.0 scenario research entries can appear. '
                  'They are NOT executable orders or independently guaranteed values.',
    }


def main():
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument('--scan',default='data/latest.json')
    p.add_argument('--valuation',default='reports/valuation_latest.json')
    p.add_argument('--championship60',default='reports/valuation_60_latest.json')
    p.add_argument('--output',default='reports/latest.json')
    a=p.parse_args()
    scan=json.loads((ROOT/a.scan).read_text(encoding='utf-8'))
    path=ROOT/a.valuation
    valuation=json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None
    vpath=ROOT/a.championship60
    c60=json.loads(vpath.read_text(encoding='utf-8')) if vpath.is_file() else None
    report=build(scan,valuation,c60)
    dst=ROOT/a.output
    dst.parent.mkdir(parents=True,exist_ok=True)
    dst.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print('Retired legacy provisional entries; evidence-qualified 6.0 research entries:',report['entry_eligible_count_60'])

if __name__=='__main__': main()
