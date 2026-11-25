"""Verify published native financials and receipt math, independently of workflow status."""
import argparse,json,math
from pathlib import Path
from datetime import datetime
from evidence_recovery_91 import write
from reviewed_bank_96 import verified

def check(root,mode='scan'):
 suffix='weekly' if mode=='weekly' else 'latest';p=root/'reports'
 historical=json.loads((p/f'valuation_90_{suffix}.json').read_text());dynamic=json.loads((p/f'dynamic_earnings_92_{suffix}.json').read_text())
 rows={r['ticker']:r for r in historical['companies'] if r['universe']=='ORIGINAL_200'}
 previous=json.loads((root/'settings/recovery_baseline_95.json').read_text())['supported_tickers']
 baseline=set(previous)|{'CNI','EOG','WOW.AX','COL.AX','TLS.AX'}
 supported={t for t,r in rows.items() if r['scenarios']};assert len(rows)==200 and len(baseline)==103 and baseline<=supported
 native=json.loads((p/'reviewed_native_96.json').read_text())['companies'];bank=json.loads((p/'reviewed_bank_96.json').read_text())['companies']['IBN']
 assert verified(bank,datetime.fromisoformat(historical['published_at_utc']))
 checks={}
 for t,ratio in [('TSM',5),('PDD',4),('IBN',2)]:
  row=rows[t];assert row['scenarios'] and not row['missing_inputs'];audit=row['reconciliation'];assert audit['status']=='RECONCILED'
  shares=audit['ordinary_share_count_before_receipt_conversion'];denominator=audit['listed_receipt_equivalent_denominator']
  assert audit['ordinary_shares_per_receipt']==ratio and denominator==shares/ratio
  fx=audit['fx_source'];assert fx['from']==audit['financial_currency'] and fx['to']=='USD' and fx['rate']>0
  assert 0<=(datetime.fromisoformat(historical['published_at_utc']).date()-datetime.fromisoformat(fx['as_of']).date()).days<=7
  checks[t]={'native_currency':audit['financial_currency'],'ordinary_shares':shares,'ordinary_shares_per_receipt':ratio,'receipt_equivalent_denominator':denominator,'fx_rate':fx['rate'],'fx_as_of':fx['as_of'],'historical_scenarios_usd':row['scenarios'],'primary_document_urls':audit['supplemental_primary_document_urls']}
 for t,ocf,cost in [('TSM',2274975600000,1305182700000),('PDD',106938690000,1145077000)]:
  facts=native[t]['annual_facts'];o=next(r for r in facts['operating_cash_flow'] if r['end']=='2025-12-31');c=next(r for r in facts['capex'] if r['end']=='2025-12-31')
  assert o['value']==ocf and c['value']==cost and c['value']==sum(x['value'] for x in c['components'])
  checks[t]['verified_2025_cash_after_deductions_native']=ocf-cost
  if t=='TSM':assert len(c['components'])==4 and any('Lease' in x['tag'] for x in c['components']) and any('InterestPaid' in x['tag'] for x in c['components'])
 facts=bank['annual_facts'];ni=next(r['value'] for r in facts['net_income'] if r['end']=='2026-03-31');eq=next(r['value'] for r in facts['equity'] if r['end']=='2026-03-31')
 assert ni==560374700000 and eq==4090932600000
 assert rows['IBN']['assumptions']['accounting_basis']=='US_GAAP_RECONCILED_FROM_INDIAN_GAAP'
 checks['IBN'].update(verified_2026_owner_income_inr=ni,verified_2026_owner_equity_inr=eq)
 result={'published_at_utc':historical['published_at_utc'],'baseline_89':89,'resumed_checkpoint':98,'previous_published':103,'historical_supported':len(supported),'gain_since_resume':len(supported)-98,'remaining_unsupported':200-len(supported),'forward_supported_original_200':sum(bool(r['forward']) for r in dynamic['companies'] if r['universe']=='ORIGINAL_200'),'lost_previously_supported':sorted(baseline-supported),'new_since_103':sorted(supported-baseline),'financial_checks':checks,'orders_enabled':False,'orders_generated':0}
 assert historical['orders_enabled'] is False and dynamic['orders_enabled'] is False
 write(p/f'recovery_96_{suffix}.json',result);print(json.dumps(result,indent=2));return result
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--mode',choices=['scan','weekly'],default='scan');a.add_argument('--root',type=Path,default=Path(__file__).resolve().parent);opts=a.parse_args();check(opts.root,opts.mode)
