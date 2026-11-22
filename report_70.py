import json
from pathlib import Path
from revision_70 import stable_revision

def main():
    src=Path('reports/valuation_60_latest.json')
    data=json.loads(src.read_text())
    rows=[]
    for x in data['companies']:
        row={'ticker':x['ticker'],'legacy_base':x.get('base'),'price':x.get('latest_dated_price'),'revision':None,'orders_enabled':False}
        a=x.get('assumptions') or {}; evidence=x.get('primary_source_evidence') or {}
        if x.get('validation_status')=='PRIMARY_INPUTS_VALIDATED_FORECASTS_HYPOTHETICAL' and 'dcf_forecast_years' in a:
            p=sorted(evidence.get('annual_statements_used',[]),key=lambda z:z['year_end'])[-a['history_years']:]
            if len(p)==a['history_years'] and all(z.get('fcf') is not None and z.get('net_income') is not None for z in p):
                rev=stable_revision([z['fcf'] for z in p],[z['net_income'] for z in p],a['issued_share_count_primary'],max(0,a['historical_filing_share_count_check']['observed_share_basis_change_pct']/100),{})
                if rev:
                    base=rev['scenarios']['base'];rev['indicative_entries']={str(i):base*(1-i/100) for i in (10,15,20)};row['revision']=rev
        row['status']='RESEARCH_SCENARIO' if row['revision'] else 'NOT_RECALCULATED'
        rows.append(row)
    out={'schema_version':'7.0-experimental','source_published_at':data.get('published_at_utc'),'original_watchlist_count':data['original_watchlist_count'],'research_only':True,'orders_enabled':False,'recalculated_count':sum(r['revision'] is not None for r in rows),'companies':rows}
    Path('reports/valuation_70_preview.json').write_text(json.dumps(out,indent=2,allow_nan=False))
if __name__=='__main__':main()
