"""Verify published financial outputs without regenerating them."""
import argparse,json,math
from pathlib import Path
from dynamic_earnings_92 import verify

def close(a,b):
    assert isinstance(a,(int,float)) and math.isfinite(a)
    assert abs(a-b)<=max(.00011,abs(b)*1e-8),(a,b)

def check(root,mode='scan'):
    suffix='weekly' if mode=='weekly' else 'latest'
    path=root/f'reports/dynamic_earnings_92_{suffix}.json'
    report=json.loads(path.read_text());coverage=verify(report)
    cases=report['validation_cases'];hpe=cases['HPE'];sks=cases['SKS.AX'];dug=cases['DUG.AX']
    for ticker,row in cases.items():
        assert row['orders_enabled'] is False and row['buy_signal'] is False
        if row['forward']:
            model=row['forward'];facts=model['guidance_source']['facts'];multiples=model['assumptions']['policy']['earnings_multiples']
            if facts['metric']=='GAAP_DILUTED_EPS':
                assert model['eps_basis']=='DIRECT_ISSUER_GAAP_DILUTED_EPS'
                close(model['scenarios']['base'],(facts['low']+facts['high'])/2*multiples['base'])
                if facts.get('non_gaap_eps_aftertax_exclusions') is not None:
                    close(facts['non_gaap_eps_low']-facts['non_gaap_eps_aftertax_exclusions'],facts['low'])
                    close(facts['non_gaap_eps_high']-facts['non_gaap_eps_aftertax_exclusions'],facts['high'])
    assert hpe['historical']['scenarios']!=hpe['forward']['scenarios']
    assert sks['forward']['eps_basis']=='MODEL_AFTER_TAX_EPS_FROM_MANAGEMENT_PBT_NOT_GUIDED_EPS'
    assert len(sks['forward']['assumptions']['adjustments'])==3
    cash=dug['cash_flow'];assert cash['owner_cash_flow']<cash['simple_fcf']
    components=cash['owner_cashflow_components']
    close(cash['owner_cash_flow'],cash['simple_fcf']-sum(r['value'] for r in components.values() if r))
    if dug['forward'] is None:
        assert 'GUIDANCE_DOES_NOT_SUPPORT_COMMON_EQUITY_EARNINGS' in dug['forward_missing_inputs']
    assert dug['latest_primary_metrics']['net_income']['value']!=dug['latest_primary_metrics'].get('group_net_income',{}).get('value')
    for row in report['validated_pre_recovery_rankings']:
        assert row['credible_forward_candidate'] and row['recovery_context']['pre_recovery']
        assert row['forward_base_upside_pct']>=25
    for row in report['provisional_research_rankings']:
        if row['valuation_status'].startswith('PROVISIONAL'):assert row['counts_toward_supported_coverage'] is False
    assert report['broker_preferences']['trial_currency']=='AUD' and report['broker_preferences']['trial_budget']==1000
    summary={'verified_report':str(path),'coverage':coverage,
             'HPE_forward_base_USD':hpe['forward']['scenarios']['base'],
             'SKS_forward_base_AUD':sks['forward']['scenarios']['base'],
             'DUG_forward_valuation':dug['forward'],'DUG_owner_cash_flow_USD':cash['owner_cash_flow'],
             'provisional_research_rows':len(report['provisional_research_rankings']),
             'validated_pre_recovery_rows':len(report['validated_pre_recovery_rankings']),
             'orders_enabled':False,'orders_generated':0}
    print(json.dumps(summary,indent=2));return summary

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path(__file__).resolve().parent);p.add_argument('--mode',choices=['scan','weekly'],default='scan');a=p.parse_args();check(a.root,a.mode)
