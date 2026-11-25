"""Inspect actual financial/session outputs and publish a reproducible comparison."""
import argparse,json,hashlib,math
from pathlib import Path
from datetime import datetime
from collections import Counter
from evidence_recovery_91 import write

def check(root,mode='scan'):
 suffix='weekly' if mode=='weekly' else 'latest';p=root/'reports';baseline=json.loads((root/'settings/recovery_baseline_95.json').read_text());historical=json.loads((p/f'valuation_90_{suffix}.json').read_text());dynamic=json.loads((p/f'dynamic_earnings_92_{suffix}.json').read_text());sessions=json.loads((p/f'session_quotes_95_{suffix}.json').read_text())
 rows={r['ticker']:r for r in historical['companies'] if r['universe']=='ORIGINAL_200'};supported={t for t,r in rows.items() if r['scenarios'] is not None}
 assert len(rows)==200 and len(sessions['companies'])==200 and set(baseline['supported_tickers'])<=supported
 assert hashlib.sha256((root/'watchlist.csv').read_bytes()).hexdigest()==baseline['original_watchlist_sha256']
 assert {'CNI','EOG','WOW.AX','COL.AX','TLS.AX'}<=supported
 src=json.loads((p/'issuer_form_recovery_95.json').read_text())['companies'];financial_checks={}
 for t in ('CNI','EOG'):
  c=src[t];o=c['annual_facts']['operating_cash_flow'][-1];a=c['annual_facts']['capex'][-1]
  assert (o['start'],o['end'],o['accession'],o['unit'])==(a['start'],a['end'],a['accession'],a['unit'])
  if t=='CNI':assert o['value']==7049000000 and a['value']==3658000000 and o['unit']=='CAD'
  else:assert o['value']==10044000000 and a['value']==6115000000+479000000 and sum(a['component_values'].values())==a['value']
  financial_checks[t]={'operating_cash_flow':o['value'],'capital_spending':a['value'],'currency':o['unit']}
 pdf=json.loads((p/'issuer_primary_records_95.json').read_text())['companies']
 expected={'WOW.AX':(4948000000,3733000000,1219200000),'COL.AX':(3344000000,2431000000,1338600000),'TLS.AX':(7554000000,5442000000,11128345952)}
 for t,(ocf,spending,shares) in expected.items():
  c=pdf[t];a=c['annual_facts']['capex'][-1];o=c['annual_facts']['operating_cash_flow'][-1]
  assert o['value']==ocf and a['value']==spending==sum(x['value'] for x in a['components']) and c['latest_share_count']['value']==shares
  assert rows[t]['assumptions']['issued_share_count_primary']==shares
  financial_checks[t]={'owner_cash_flow_conservative':ocf-spending,'shares_net_of_trust':shares,'currency':'AUD'}
 fixed={r['ticker']:r for r in dynamic['companies'] if r['universe']=='ORIGINAL_200'}
 for t,low,high in [('ADBE',18.12,18.17),('DELL',28.24,28.24),('UNH',19.5,19.5)]:
  f=fixed[t]['forward'];assert f and f['eps_range']=={'low':low,'high':high}
  m=f['assumptions']['policy']['earnings_multiples'];eps={'bear':low,'base':(low+high)/2,'bull':high}
  for k in eps:assert abs(f['scenarios'][k]-eps[k]*m[k])<.00011
  financial_checks[t]={'forward_scenarios':f['scenarios'],'target_period_end':f['guidance_source']['facts']['target_period_end'],'guidance_shape':f['guidance_source']['facts']['guidance_shape']}
 assert sum(bool(r['forward']) for r in fixed.values())>=4
 for record in sessions['companies'].values():
  observed=datetime.fromisoformat(record['retrieved_at_utc']) if record.get('retrieved_at_utc') else None
  for label,sample in record['sessions'].items():
   if not sample:continue
   stamp=datetime.fromisoformat(sample['as_of_utc']);assert observed and stamp<=observed
   assert datetime.fromisoformat(sample['session_start_utc'])<=stamp<datetime.fromisoformat(sample['session_end_utc'])
   assert sample['session']==label.upper() and sample['price']>0 and math.isfinite(sample['price'])
 for obj in (historical,dynamic,sessions):assert obj['orders_enabled'] is False and obj['orders_generated']==0
 result={'baseline_historical_supported':98,'historical_supported_after':len(supported),'new_historical_supported':sorted(supported-set(baseline['supported_tickers'])),'lost_historical_supported':[],'still_unsupported':200-len(supported),'baseline_forward_supported':1,'forward_supported_after':sum(bool(r['forward']) for r in fixed.values()),'session_sample_counts':sessions['sample_counts'],'financial_checks':financial_checks,'remaining_work':dict(Counter(b for t,r in rows.items() if t not in supported for b in r['missing_inputs'])),'scope':'All 200 assessed. Source collection and workflow success are not financial validation. Remaining engineering work is not described as an external blocker.','orders_enabled':False,'orders_generated':0}
 write(p/f'recovery_95_{suffix}.json',result);print(json.dumps(result,indent=2));return result
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--root',type=Path,default=Path(__file__).resolve().parent);a.add_argument('--mode',choices=['scan','weekly'],default='scan');opts=a.parse_args();check(opts.root,opts.mode)
