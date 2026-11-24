"""Independent published-output checks and a reproducible coverage comparison."""
import argparse,json
from pathlib import Path
from collections import Counter
from evidence_recovery_91 import write
EXPECTED_SHARES={'NKE':1485308829,'REGN':103447859,'MA':871176114,'CME':357933884,'LEU':20618450}

def check(root,mode='scan'):
 suffix='weekly' if mode=='weekly' else 'latest';r=root/'reports'
 model=json.loads((r/f'valuation_90_{suffix}.json').read_text());rows={x['ticker']:x for x in model['companies'] if x['universe']=='ORIGINAL_200'}
 baseline=json.loads((root/'settings/recovery_baseline_94.json').read_text());supported={t for t,x in rows.items() if x['scenarios'] is not None}
 assert len(rows)==200 and set(baseline['supported_tickers'])<=supported
 new=sorted(supported-set(baseline['supported_tickers']));assert set(EXPECTED_SHARES)|{'COP'}<=set(new)
 counts=json.loads((r/'reviewed_share_counts_94.json').read_text())['companies']
 for t,expected in EXPECTED_SHARES.items():
  latest=max(counts[t]['counts'],key=lambda x:x['end']);assert latest['value']==expected and sum(latest['class_components'].values())==expected
  assert all(x['taxonomy']=='dei' for x in counts[t]['counts'])
  used=rows[t]['assumptions']['issued_share_count_primary']
  as_of=rows[t]['assumptions']['source_dates']['shares']
  if as_of==latest['end']:assert used==expected
  else:
   background=json.loads((r/'background_evidence_93.json').read_text())['companies'][t]['latest_share_count']
   assert as_of==background['end'] and as_of>latest['end'] and used==background['value']==sum(background['class_components'].values())
  assert rows[t]['scenarios']['bear']<=rows[t]['scenarios']['base']<=rows[t]['scenarios']['bull']
 cash=json.loads((r/'reviewed_cashflow_92.json').read_text());cop=next(x for x in cash['companies'] if x['ticker']=='COP');last=max(cop['periods'],key=lambda x:x['capex']['end'])
 assert last['capex']['end']=='2025-12-31' and last['capex']['value']==12553000000 and last['operating_cash_flow']['value']==19796000000
 assert last['operating_cash_flow']['accession']==last['capex']['accession']
 assert model['orders_enabled'] is False and model['orders_generated']==0
 result={'source_valuation_report':f'valuation_90_{suffix}.json','original_200_count':200,'original_supported_baseline':89,'pre_repair_supported_count':92,'supported_after':len(supported),'net_gain_this_repair':len(supported)-92,'net_gain_from_original_baseline':len(supported)-89,'previously_supported_lost':[],'newly_supported_this_repair':new,'still_unsupported':200-len(supported),'remaining_blockers':dict(Counter(b for t,x in rows.items() if t not in supported for b in x['missing_inputs'])),'financial_checks':{'reviewed_share_denominators':EXPECTED_SHARES,'COP_2025_OCF_USD':19796000000,'COP_2025_capital_expenditure_and_investments_USD':12553000000,'COP_2025_conservative_cash_flow_USD':7243000000},'scope':'Historical supported models; these additions are not validated forward buy opportunities. Missing specialist inputs remain null.','orders_enabled':False,'orders_generated':0}
 write(r/f'recovery_94_{suffix}.json',result);print(json.dumps(result,indent=2));return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path(__file__).resolve().parent);p.add_argument('--mode',choices=['scan','weekly'],default='scan');a=p.parse_args();check(a.root,a.mode)
