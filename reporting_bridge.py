"""Bounded API reporting views. Detailed reports remain authoritative and untouched."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LIMIT = 100_000

def encoded(value):
    return (json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)+'\n').encode()

def publish(root=ROOT, mode='scan'):
    reports = root/'reports'
    out = reports/'bridge'
    out.mkdir(exist_ok=True)
    inputs = {}
    def read(name, required=False):
        path = reports/name
        if not path.exists():
            if required: raise ValueError('Missing required report '+name)
            inputs[name] = {'missing': True}
            return {}
        raw = path.read_bytes()
        value = json.loads(raw)
        if value.get('orders_enabled') is True: raise ValueError('Unsafe report '+name)
        inputs[name] = {'path': 'reports/'+name, 'sha256': hashlib.sha256(raw).hexdigest(),
                        'as_of_utc': value.get('published_at_utc'), 'missing': False}
        return value
    suffix = 'weekly' if mode == 'weekly' else 'latest'
    val = read('valuation_90_'+suffix+'.json', True)
    dyn = read('dynamic_earnings_92_'+suffix+'.json', True)
    sessions = read('session_quotes_95_'+suffix+'.json')
    legacy = read('latest.json')
    entries = read('valuation_60_'+suffix+'.json')
    weekly = read('dynamic_earnings_92_weekly.json')
    priority = read('priority_quotes_90.json')
    april = read('april_2026_valuation_comparison.json')
    radar = read('discovery_latest.json')
    radar_watchlist = read('discovery_watchlist.json')
    by = lambda d, k='companies': d.get(k, {}) if isinstance(d.get(k), dict) else {r['ticker']: r for r in d.get(k, [])}
    ds, ss, ls, es = by(dyn), by(sessions), by(legacy, 'stocks'), by(entries)
    now = datetime.now(timezone.utc).isoformat()
    files = {}
    def write(name, obj):
        raw = encoded(obj)
        if len(raw) >= LIMIT: raise ValueError('Bridge exceeds byte limit: '+name)
        (out/name).write_bytes(raw)
        files[name] = {'path': 'reports/bridge/'+name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    def envelope(**kw):
        return dict(schema_version='1.0', published_at_utc=now, mode=mode, research_only=True,
                    orders_enabled=False, orders_generated=0, **kw)
    def chunks(name, rows):
        parts=[]; batch=[]
        for row in rows:
            if len(encoded(envelope(rows=batch+[row]))) >= 90_000 and batch:
                parts.append(batch); batch=[]
            batch.append(row)
        if batch: parts.append(batch)
        refs=[]
        for i, part in enumerate(parts, 1):
            filename=f'{name}_{i:03d}.json'
            write(filename,envelope(rows=part))
            refs.append(dict(files[filename], count=len(part)))
        write(name+'.json', envelope(count=len(rows), chunks=refs))
    rows=[]; discovery=[]
    for v in val['companies']:
        t=v['ticker']; d=ds.get(t, {}); l=ls.get(t, {}); e=es.get(t, {}); s=ss.get(t, {})
        f=d.get('forward') or {}; h=d.get('historical') or {}
        rec=v.get('reconciliation') or {}
        selected=e.get('selected_entry') if e.get('validation_status') != 'NOT VALIDATED' else None
        price=v.get('price')
        distance=round((price/selected-1)*100, 4) if isinstance(selected,(int,float)) and selected>0 and isinstance(price,(int,float)) else None
        compact_sessions={}
        for key in ('pre_market','regular','after_hours'):
            q=(s.get('sessions') or {}).get(key) or {}
            compact_sessions[key]={k:q.get(k) for k in ('price','currency','as_of_utc','session','freshness','source_url')}
            compact_sessions[key]['missing']=q.get('price') is None or q.get('as_of_utc') is None
        row={'ticker':t,'currency':v.get('currency'),'price':price,'quote_date':v.get('quote_date'),
             'price_session':'DAILY_CLOSE','price_source':v.get('price_source'),
             'historical':{'scenarios':v.get('scenarios'),'status':v.get('assessment_status')},
             'forward':{'scenarios':f.get('scenarios'),'status':f.get('status'),
                        'source_url':(f.get('guidance_source') or {}).get('source_url')},
             'entry_limit':selected,'entry_status':e.get('validation_status','MISSING'),
             'entry_source':'reports/valuation_60_'+suffix+'.json',
             'priority_entry':v.get('priority_entry'),'pct_above_entry':distance,
             'missing_flags':{'historical':v.get('missing_inputs',[]),'forward':d.get('forward_missing_inputs',['DYNAMIC_ROW_MISSING']),
                              'entry':e.get('missing_evidence_flags',[]),'price':price is None},
             'forward_validation_blockers':d.get('forward_validation_blockers'),
             'sources':{'historical_url':rec.get('primary_source_url'),'historical_hash':rec.get('primary_evidence_hash'),
                        'valuation_report':'reports/valuation_90_'+suffix+'.json','dynamic_report':'reports/dynamic_earnings_92_'+suffix+'.json'},
             'sessions':compact_sessions,'session_status':s.get('status','MISSING'),
             'april_2026':{'status':'MISSING_VERIFIED_COMPARABLE_BASELINE','valuation':None},
             'buy_signal':False}
        (rows if v.get('universe')=='ORIGINAL_200' else discovery).append(row)
    if len(rows)!=200 or len({r['ticker'] for r in rows})!=200: raise ValueError('Expected 200 unique original stocks')
    chunks('dashboard', rows)
    chunks('discovery', discovery)
    candidates=radar_watchlist.get('candidates', {})
    chunks('discovery_candidates', list(candidates.values()) if isinstance(candidates,dict) else candidates)
    write('discovery_radar_summary.json', envelope(source_as_of_utc=radar.get('published_at_utc'), missing=not bool(radar), summary={k:v for k,v in radar.items() if k not in ('active_watchlist','orders_enabled')}, source='reports/discovery_latest.json'))
    ranked=sorted((r for r in rows if r['pct_above_entry'] is not None), key=lambda r:(abs(r['pct_above_entry']),r['ticker']))
    # Explicit legacy evidence gate; newer scenario values never become invented entry limits.
    chunks('closest_top30', [dict(r,rank=i+1) for i,r in enumerate(ranked[:30])])
    chunks('closest_top10', [dict(r,rank=i+1) for i,r in enumerate(ranked[:10])])
    chunks('forward_rankings', dyn.get('validated_forward_rankings',[]))
    chunks('pre_recovery_rankings', dyn.get('validated_pre_recovery_rankings',[]))
    chunks('priority_quotes',[dict(r, daily_bar_source=priority.get('quotes',{}).get(r['ticker'])) for r in rows+discovery if r['priority_entry'] is not None])
    chunks('april_2026_comparison',[{'ticker':r['ticker'],**r['april_2026']} for r in rows])
    write('coverage.json',envelope(coverage=dyn.get('coverage_comparison'),historical_supported=sum(bool(r['historical']['scenarios']) for r in rows),forward_supported=sum(bool(r['forward']['scenarios']) for r in rows),universe_count=200))
    chunks('weekly_valuations', [{'ticker':r['ticker'],'price':r.get('price'),'currency':r.get('currency'),'quote_date':r.get('quote_date'),'historical':{k:(r.get('historical') or {}).get(k) for k in ('scenarios','status','missing_inputs','report')},'forward':{k:(r.get('forward') or {}).get(k) for k in ('scenarios','status','eps_basis')},'forward_source':((r.get('forward') or {}).get('guidance_source') or {}).get('source_url'),'forward_missing_inputs':r.get('forward_missing_inputs'),'forward_validation_blockers':r.get('forward_validation_blockers'),'priority_entry':r.get('priority_entry')} for r in weekly.get('companies',[])])
    write('weekly_summary.json',envelope(source_as_of_utc=weekly.get('published_at_utc'),coverage=weekly.get('coverage_comparison'),missing=not bool(weekly),source='reports/dynamic_earnings_92_weekly.json'))
    manifest=envelope(universe_count=200,discovery_count=len(discovery),files=files,inputs=inputs,
        ranking_method='Absolute percentage distance to existing evidence-gated 6.0 entry; research only; no new entry thresholds',
        april_status='MISSING_VERIFIED_COMPARABLE_BASELINE',brokers=dyn.get('broker_preferences'),
        policy=dyn.get('policy'),retrieval='Read this manifest at one Git commit SHA; fetch all paths at that same SHA and verify sha256. Index files point to bounded chunks.',
        detailed_reports_preserved=True)
    write('manifest.json',manifest)
    active=set(files)
    for path in out.glob('*.json'):
        if path.name not in active: path.unlink()
    verify(out)
    return manifest

def verify(out):
    manifest=json.loads((out/'manifest.json').read_text())
    for name, info in manifest['files'].items():
        raw=(out/name).read_bytes()
        assert len(raw)<LIMIT and len(raw)==info['bytes']
        assert hashlib.sha256(raw).hexdigest()==info['sha256']
    index=json.loads((out/'dashboard.json').read_text())
    rows=[r for c in index['chunks'] for r in json.loads((out/Path(c['path']).name).read_text())['rows']]
    assert len(rows)==len({r['ticker'] for r in rows})==200
    print('Verified bounded reporting bridge: 200 stocks,',len(manifest['files'])+1,'files')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['scan','weekly'],default='scan');p.add_argument('--verify',action='store_true');a=p.parse_args()
    verify(ROOT/'reports/bridge') if a.verify else publish(mode=a.mode)
