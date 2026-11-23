"""Research-only retrospective explosive-move audit; never a trade signal."""
import csv, json, math
from pathlib import Path
from datetime import datetime, timezone

def num(value):
    try:
        v=float(value)
        return v if math.isfinite(v) else None
    except (ValueError, TypeError): return None

def audit(root=Path('.')):
    root=Path(root); reports=root/'reports'; reports.mkdir(parents=True,exist_ok=True)
    source=reports/'latest.csv'; rows=[]; fields=[]
    if source.exists():
        with source.open(encoding='utf-8-sig',newline='') as f:
            reader=csv.DictReader(f); fields=reader.fieldnames or []; rows=list(reader)
    candidates=('return_1d_pct','return_1d','change_1d_pct','daily_change_pct')
    col=next((x for x in candidates if x in fields),None)
    volcol=next((x for x in ('volume_ratio','relative_volume','rvol','volume_ratio_20d') if x in fields),None)
    flagged=[]
    if col:
        for row in rows:
            change=num(row.get(col)); volume=num(row.get(volcol)) if volcol else None
            if change is None or not (change>=50 or (volume is not None and volume>=3)):continue
            flagged.append({'ticker':row.get('ticker'),'historical_daily_change_pct':change,
                'relative_volume':volume,'explosive_move':change>=50,
                'unusual_volume':volume is not None and volume>=3,
                'pre_move_signal_verified':False,'filing_catalyst_verified':False,
                'dilution_checked':False,'execution_verified':False,
                'missed_valid_buy':'UNDETERMINED','classification':'RETROSPECTIVE_RESEARCH_ONLY',
                'next_steps':['Verify pre-move official filing timestamp','Inspect dilution and financing',
                              'Reconstruct executable pre-move spread and liquidity',
                              'Compare against losing candidates without hindsight bias']})
    flagged.sort(key=lambda x:abs(x['historical_daily_change_pct']),reverse=True)
    output={'schema_version':'8.0-research-only','generated_at_utc':datetime.now(timezone.utc).isoformat(),
        'source':'reports/latest.csv historical daily bars','rows_examined':len(rows),
        'available_columns':fields,'price_change_column':col,
        'status':'HISTORICAL_SCREEN_ONLY' if col else 'INSUFFICIENT_DAILY_CHANGE_DATA',
        'coverage_limit':'Fixed 200 only; no comprehensive premarket feed or full-market gainer detection',
        'live_premarket_detector':False,'automated_filing_validation':False,
        'validated_missed_buy_audit':False,'orders_enabled':False,'buy_signals_generated':0,
        'flagged':flagged[:40]}
    (reports/'explosive_move_audit_80.json').write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
    return output

if __name__=='__main__':
    report=audit()
    print(json.dumps({k:report[k] for k in ('status','rows_examined','price_change_column','orders_enabled')}))
