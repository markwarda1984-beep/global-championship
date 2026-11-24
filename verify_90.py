"""Published research schema checks; deliberately fails incomplete cohorts."""
import argparse
import json
from pathlib import Path
from championship_90 import PRIORITIES

def verify(root, mode):
    suffix='weekly' if mode=='weekly' else 'latest'
    report=json.loads((root/f'reports/valuation_90_{suffix}.json').read_text())
    rows=report['companies']; mapping={r['ticker']:r for r in rows}
    assert report['schema_version'].startswith('9.0')
    assert len(mapping)==len(rows)==report['reported_count']
    assert sum(r['universe']=='ORIGINAL_200' for r in rows)==200
    assert report['orders_enabled'] is False and report['orders_generated']==0
    assert set(PRIORITIES)<=set(mapping)
    for r in rows:
        assert r['orders_enabled'] is False and r['buy_signal'] is False
        if r['assessment_status']=='MISSING_EVIDENCE': assert r['scenarios'] is None and r['base_upside_pct'] is None
        else: assert not r['missing_inputs'] and r['reconciliation']['status'].startswith('RECONCILED')
    for t,rule in PRIORITIES.items():
        assert all(mapping[t]['priority_entry'][k]==v for k,v in rule.items())
    for r in report['ranked_pre_recovery_top10']:
        assert r['scenarios'] and r['base_upside_pct']>=25 and r['recovery_from_5d_low_pct']<=3
    c=report['coverage_comparison']
    assert c['original_200_assessed_after']==200
    assert c['original_200_valued_after']==sum(r['scenarios'] is not None for r in rows if r['universe']=='ORIGINAL_200')
    print(json.dumps(c,indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['scan','weekly'],default='scan');a=p.parse_args();verify(Path(__file__).resolve().parent,a.mode)
