"""Dynamic earnings research, separate from preserved historical valuations.

Facts retain their native units, duration, accounting basis and source. Missing
data is never replaced with zero or a vendor forecast. No brokerage API exists.
"""
from __future__ import annotations
import argparse, gzip, hashlib, json, math, statistics, re
from datetime import datetime, timezone, date
from pathlib import Path
from championship_90 import read, write, recent, number, positive, evidence_record

SCENARIOS = ('bear', 'base', 'bull')

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()

def valid_record(record, now):
    return (record.get('orders_enabled') is False
            and record.get('facts_sha256') == digest(record.get('metrics', {}))
            and recent(record.get('observed_utc'), now, 14))

def load_periods(root, now):
    path = root/'reports/dynamic_sec_periods_92.json.gz'
    sec = json.loads(gzip.decompress(path.read_bytes())) if path.exists() else {}
    records = {t:r for t,r in sec.get('companies', {}).items() if valid_record(r, now)}
    background=read(root/'reports/background_evidence_93.json',{}) or {}
    if background and (background.get('orders_enabled') is not False or background.get('orders_generated')!=0):
        raise ValueError('Unsafe background dynamic evidence')
    for ticker,record in background.get('dynamic_periods',{}).items():
        if (record.get('ticker')==ticker and valid_record(record,now)
                and record.get('observed_utc','')>=records.get(ticker,{}).get('observed_utc','')):
            records[ticker]=record
    for filename in ('dynamic_manual_periods_92.json', 'dynamic_release_periods_92.json'):
        for ticker, record in (read(root/'reports'/filename, {}) or {}).get('companies', {}).items():
            if not valid_record(record, now): continue
            merged = records.setdefault(ticker, {'metrics':{}, 'orders_enabled':False})
            for metric, facts in record.get('metrics', {}).items():
                # Explicit reviewed release facts supersede delayed XBRL for the
                # identical duration/unit only; older intervals remain available.
                by = {(r['period_start'],r['period_end'],r['unit']):r for r in merged['metrics'].get(metric, [])}
                by.update({(r['period_start'],r['period_end'],r['unit']):r for r in facts})
                merged['metrics'][metric] = list(by.values())
            merged['observed_utc'] = record['observed_utc']
            merged['owner_cashflow_components_reviewed'] = record.get('owner_cashflow_components_reviewed',False)
    from championship_90 import verified_pdf_record
    for ticker,record in (read(root/'reports/dynamic_historical_records_92.json',{}) or {}).get('companies',{}).items():
        if ticker in records or not verified_pdf_record(record,now):continue
        metrics={}
        for key,facts in record['annual_facts'].items():
            metric='issued_shares' if key=='shares' else key
            metrics[metric]=[{**f,'metric':metric,'period_start':f.get('start'),'period_end':f['end'],
                              'period_type':'ANNUAL' if f.get('start') else 'INSTANT',
                              'currency':None if key=='shares' else f['unit'],'accounting_basis':'AASB_IFRS'} for f in facts]
        records[ticker]={'ticker':ticker,'metrics':metrics,'observed_utc':record['observed_utc'],'orders_enabled':False}
    return records

def observations(record, metric, kind=None, currency=None, now=None):
    out=[]
    for fact in record.get('metrics', {}).get(metric, []):
        if number(fact.get('value')) is None or not fact.get('accession'): continue
        if not str(fact.get('source_url','')).startswith('https://'): continue
        if kind and fact.get('period_type') != kind: continue
        if currency and fact.get('currency') != currency: continue
        if now and (not recent(fact.get('filed'),now,4200) or not recent(fact.get('period_end'),now,4200)): continue
        out.append(fact)
    return sorted(out, key=lambda f:(f['period_end'],f.get('filed',''),f.get('concept_preference',0)))

def latest(record, metric, kind=None, currency=None, now=None):
    rows=observations(record,metric,kind,currency,now)
    return rows[-1] if rows else None

def growth(current, previous):
    if current is None or previous is None: return {'status':'MISSING_COMPARABLE_PERIOD','pct':None}
    if previous <= 0: return {'status':'TURNAROUND' if current>0 else 'LOSS_BASE_NOT_PERCENT_COMPARABLE','pct':None}
    return {'status':'COMPARABLE_REPORTED_GROWTH','pct':round((current/previous-1)*100,3)}

def comparable_prior(rows, current):
    """Same currency, taxonomy and duration; a nine-month total is not a quarter."""
    end=date.fromisoformat(current['period_end'])
    start=date.fromisoformat(current['period_start']) if current.get('period_start') else None
    matches=[]
    for row in rows:
        if row['unit']!=current['unit'] or row.get('accounting_basis')!=current.get('accounting_basis'): continue
        if row.get('period_type')!=current.get('period_type'): continue
        if not 350 <= (end-date.fromisoformat(row['period_end'])).days <= 380: continue
        if start and row.get('period_start'):
            duration=(end-start).days
            if abs(duration-(date.fromisoformat(row['period_end'])-date.fromisoformat(row['period_start'])).days)>10: continue
        matches.append(row)
    return max(matches,key=lambda r:r['filed']) if matches else None

def acceleration(record, metric, currency, now):
    quarters=observations(record,metric,'QUARTER',currency,now)
    if not quarters: return {'status':'QUARTERLY_DISCLOSURE_NOT_RECOVERED','latest':None,'yoy_pct':None,'acceleration_pp':None}
    current=quarters[-1];prior=comparable_prior(quarters,current)
    result=growth(current['value'],prior['value'] if prior else None)
    previous=[r for r in quarters if 65 <= (date.fromisoformat(current['period_end'])-date.fromisoformat(r['period_end'])).days <=115]
    previous=max(previous,key=lambda r:r['period_end']) if previous else None
    py=comparable_prior(quarters,previous) if previous else None
    previous_growth=growth(previous['value'] if previous else None,py['value'] if py else None)
    change=(result['pct']-previous_growth['pct']) if result['pct'] is not None and previous_growth['pct'] is not None else None
    return {'status':result['status'],'latest':current,'prior_year':prior,'yoy_pct':result['pct'],
            'previous_quarter_yoy_pct':previous_growth['pct'],'acceleration_pp':round(change,3) if change is not None else None,
            'comparison_note':'Reported results; acquisition and impairment effects are not organic growth.'}

def matched_cash(record, currency, now):
    ocf=latest(record,'operating_cash_flow',currency=currency,now=now)
    if not ocf: return {'status':'PRIMARY_OPERATING_CASH_FLOW_MISSING','simple_fcf':None,'owner_cash_flow':None}
    def same(metric):
        return next((r for r in reversed(observations(record,metric,currency=currency,now=now))
                     if (r['period_start'],r['period_end'],r['accession'])==(ocf['period_start'],ocf['period_end'],ocf['accession'])),None)
    capex=same('capex')
    adjustments={k:same(k) for k in ('capitalized_development','lease_principal','financing_lease_interest','financing_borrowing_interest')}
    simple=ocf['value']-capex['value'] if capex and capex['value']>=0 else None
    # Absence of a lease/development row in generic XBRL is NOT evidence of zero.
    owner=simple-sum(r['value'] for r in adjustments.values() if r) if simple is not None and record.get('owner_cashflow_components_reviewed') else None
    return {'status':'MATCHED_PERIOD_CASH_FLOW' if simple is not None else 'CAPEX_INTERVAL_OR_ACCESSION_NOT_RECONCILED',
            'period_type':ocf['period_type'],'operating_cash_flow':ocf,'capex':capex,'simple_fcf':simple,
            'owner_cash_flow':owner,'owner_cashflow_components':adjustments,
            'definition':'Owner cash flow also deducts capitalized development, lease principal and interest classified in financing. Missing components are not assumed zero.'}

def ttm(record, metric, currency, now):
    """Annual + current YTD - same prior YTD, never add diluted EPS denominators."""
    if metric.startswith('eps_') or 'shares' in metric: return None
    all_rows=observations(record,metric,currency=currency,now=now)
    annual=[r for r in all_rows if r['period_type']=='ANNUAL']
    ytd=[r for r in all_rows if r['period_type'] in ('QUARTER','HALF_YEAR_OR_YTD','NINE_MONTH_YTD')]
    if not annual or not ytd:return None
    a=annual[-1];c=ytd[-1];p=comparable_prior(ytd,c)
    if not p or c['accession']!=p['accession'] or c.get('accounting_basis')!=a.get('accounting_basis'):return None
    ae=date.fromisoformat(a['period_end']);cs=date.fromisoformat(c['period_start'])
    if not 0<(cs-ae).days<=8:return None
    if p['period_start']!=a['period_start']:return None
    return {'value':a['value']+c['value']-p['value'],'currency':currency,'period_end':c['period_end'],
            'formula':'ANNUAL + CURRENT_YTD - PRIOR_YTD','source_components':[a,c,p]}

def recovery_context(row, quote):
    """Scale distance by observed daily volatility, not a blanket percent cut-off.
    Missing history leaves timing unknown and remains visible in research.
    """
    price=positive(row.get('price'));lows=row.get('trading_lows') or {}
    low=positive(lows.get('low_5d'));previous=positive(lows.get('previous_5d_low'))
    history=quote.get('history') or []
    daily=[math.log(b/a) for a,b in zip(history,history[1:]) if positive(a) and positive(b)]
    volatility=statistics.stdev(daily[-20:]) if len(daily)>=15 else None
    distance=math.log(price/low) if price and low else None
    sigma=distance/volatility if distance is not None and volatility and volatility>0 else None
    new_low=bool(price and previous and price<=previous)
    early=new_low or (sigma is not None and sigma<=1)
    return {'status':'AT_OR_BELOW_PREVIOUS_FIVE_DAY_LOW' if new_low else 'WITHIN_ONE_OBSERVED_DAILY_VOLATILITY_OF_LOW' if early else 'RECOVERY_ALREADY_UNDERWAY' if sigma is not None else 'TIMING_EVIDENCE_UNAVAILABLE',
            'pre_recovery':early,'distance_from_5d_low_in_daily_sigma':sigma,
            'observed_daily_log_return_stddev':volatility,'sessions_observed':len(history),
            'basis':'Volatility-aware research timing; recovering companies remain visible in provisional and validated forward rankings.'}

def provisional_model(record, row, policy, adapters, now):
    """Zero-growth sensitivity, explicitly not management guidance or coverage.
    Use reported annual diluted EPS directly; never multiply a quarter by four.
    """
    from championship_60 import ADR_OR_OVERSEAS_SHARE_BASIS
    if row['ticker'] in ADR_OR_OVERSEAS_SHARE_BASIS or row['ticker']=='RMD.AX':
        return None # XBRL USD/shares does not prove whether EPS is per receipt.
    currency=row.get('reconciliation',{}).get('financial_currency') or row.get('currency')
    eps=latest(record,'eps_diluted','ANNUAL',currency,now)
    model=policy['sector_policies'].get(row['sector_method'])
    if not eps or eps['value']<=0 or not recent(eps['period_end'],now,550) or not model:return None
    ratio=rate=1.
    if currency!=row['currency']:
        adapter=adapters.get(row['ticker'],{});fx=adapter.get('fx');basis=adapter.get('share_basis')
        if not fx or not evidence_record(basis,now) or fx.get('from')!=currency or fx.get('to')!=row['currency'] or not recent(fx.get('as_of'),now,7):return None
        ratio=positive(basis['facts'].get('ordinary_shares_per_receipt'));rate=positive(fx.get('rate'))
        if not ratio or not rate:return None
    return {'status':'PROVISIONAL_RESEARCH_ONLY_NOT_VALIDATED_FORWARD_EARNINGS','scenarios':{k:round(eps['value']*model['earnings_multiples'][k]*ratio*rate,4) for k in SCENARIOS},
            'currency':row['currency'],'source':eps,'assumptions':{'earnings_growth':0,'earnings_multiples':model['earnings_multiples'],
            'note':'Latest reported annual diluted EPS held constant only for sensitivity. Not management guidance, normalized earnings or an entry recommendation.'},
            'counts_toward_supported_coverage':False}

def forward(guidance, row, periods, policy, adapters, now):
    if not guidance or not evidence_record(guidance,now,400):return None,['CURRENT_REVIEWED_MANAGEMENT_GUIDANCE_REQUIRED']
    if not re.fullmatch('[0-9a-f]{64}',guidance.get('source_document_sha256','')):return None,['GUIDANCE_DOCUMENT_HASH_REQUIRED']
    facts=guidance['facts'];target=facts.get('target_period_end')
    if not target or date.fromisoformat(target)<now.date():return None,['GUIDANCE_TARGET_PERIOD_ENDED']
    if facts.get('ticker')!=row['ticker']:return None,['GUIDANCE_IDENTITY_MISMATCH']
    currency=facts.get('currency');kind=facts.get('metric');adjustments=[]
    if kind=='GAAP_DILUTED_EPS':
        if facts.get('per_share_basis')!='LISTED_DILUTED_COMMON_SHARE':return None,['GUIDANCE_PER_LISTED_SHARE_BASIS_REQUIRED']
        lo,hi=number(facts.get('low')),number(facts.get('high'))
        adjustment=number(facts.get('non_gaap_eps_aftertax_exclusions'))
        if adjustment is not None:
            nlo,nhi=number(facts.get('non_gaap_eps_low')),number(facts.get('non_gaap_eps_high'))
            if any(v is None for v in (lo,hi,nlo,nhi)) or abs(nlo-adjustment-lo)>.011 or abs(nhi-adjustment-hi)>.011:
                return None,['GAAP_AND_ADJUSTED_GUIDANCE_BRIDGE_MISMATCH']
        basis='DIRECT_ISSUER_GAAP_DILUTED_EPS'
    elif kind=='PRETAX_PROFIT_POINT':
        # Never report PBT as EPS or silently assume a statutory tax rate.
        pretax=latest(periods,'pretax_profit','ANNUAL',currency,now)
        tax=latest(periods,'tax_expense','ANNUAL',currency,now)
        group=latest(periods,'group_net_income','ANNUAL',currency,now)
        owner=latest(periods,'net_income','ANNUAL',currency,now)
        shares=latest(periods,'issued_shares','INSTANT',now=now)
        if not all([pretax,tax,group,owner,shares]) or not positive(pretax['value']) or not positive(group['value']):return None,['AFTER_TAX_OWNER_ALLOCATION_AND_SHARE_BASIS_REQUIRED']
        if len({(r['period_end'],r['accession']) for r in [pretax,tax,group,owner]})!=1:return None,['TAX_AND_OWNER_PERIOD_MISMATCH']
        taxrate=tax['value']/pretax['value'];owner_ratio=owner['value']/group['value']
        if not 0<=taxrate<=.5 or not 0<owner_ratio<=1:return None,['TAX_OR_NCI_ALLOCATION_REQUIRES_REVIEW']
        point=positive(facts.get('point'))
        if point is None:return None,['POSITIVE_GUIDED_PRETAX_PROFIT_REQUIRED']
        lo=point*(1-taxrate)*owner_ratio/shares['value'];hi=lo
        basis='MODEL_AFTER_TAX_EPS_FROM_MANAGEMENT_PBT_NOT_GUIDED_EPS'
        adjustments=[{'name':'Latest actual effective tax rate held constant','assumption':taxrate,'sources':[pretax,tax]},
                     {'name':'Latest actual owner allocation held constant','assumption':owner_ratio,'sources':[group,owner]},
                     {'name':'Conservative future share issuance stress','assumption':policy['future_issuance_stress'],'source':shares}]
    else:return None,['GUIDANCE_DOES_NOT_SUPPORT_COMMON_EQUITY_EARNINGS']
    if lo is None or hi is None or not 0<lo<=hi:return None,['INVALID_OR_NONPOSITIVE_GUIDANCE_RANGE']
    if currency!=row['currency']:
        fx=adapters.get(row['ticker'],{}).get('fx')
        if not fx or fx.get('from')!=currency or fx.get('to')!=row['currency'] or not recent(fx.get('as_of'),now,7):return None,['DATED_DIRECTIONAL_FORWARD_FX_REQUIRED']
        rate=positive(fx.get('rate'))
        ratio=1.
        if kind!='GAAP_DILUTED_EPS':
            share=adapters.get(row['ticker'],{}).get('share_basis')
            if not evidence_record(share,now):return None,['FORWARD_LISTED_SHARE_BASIS_REQUIRED']
            ratio=positive(share['facts'].get('ordinary_shares_per_receipt'))
        if not rate or not ratio:return None,['FORWARD_FX_OR_RECEIPT_RATIO_INVALID']
    else:rate=ratio=1.
    # Multiples are fixed policy assumptions; never chosen to force 25–50% upside.
    model=policy['sector_policies'].get(row['sector_method'])
    if not model:return None,['FORWARD_SECTOR_MODEL_NOT_IMPLEMENTED']
    eps={'bear':lo,'base':(lo+hi)/2,'bull':hi}
    stress=policy['future_issuance_stress'] if kind=='PRETAX_PROFIT_POINT' else dict.fromkeys(SCENARIOS,0)
    values={k:round(eps[k]*model['earnings_multiples'][k]*rate*ratio/(1+stress[k]),4) for k in SCENARIOS}
    return {'scenarios':values,'currency':row['currency'],'earnings_currency':currency,'eps_basis':basis,
            'eps_range':{'low':lo,'high':hi},'guidance_source':guidance,'assumptions':{'policy':model,'adjustments':adjustments,
            'multiple_status':'RESEARCH_ASSUMPTIONS_NOT_VERIFIED_INTRINSIC_VALUES','direct_diluted_eps_not_rescaled_by_issued_shares':kind=='GAAP_DILUTED_EPS'},
            'status':'PRIMARY_GUIDANCE_BACKED_MODEL_FORECASTS_HYPOTHETICAL'},[]

def build(root, mode='scan', now=None):
    now=now or datetime.now(timezone.utc)
    suffix='weekly' if mode=='weekly' else 'latest'
    historical=read(root/f'reports/valuation_90_{suffix}.json',{})
    baseline=read(root/'settings/dynamic_baseline_92.json',{})
    policy=read(root/'settings/dynamic_earnings_92.json',{})
    adapters=read(root/'settings/primary_adapters_90.json',{})
    guidance=(read(root/'reports/dynamic_guidance_92.json',{}) or {}).get('companies',{})
    for ticker,g in (read(root/'reports/background_evidence_93.json',{}) or {}).get('guidance',{}).items():
        if evidence_record(g,now,400) and g.get('published_at','')>=guidance.get(ticker,{}).get('published_at',''):
            guidance[ticker]=g
    source_audit=(read(root/'reports/dynamic_source_recovery_92.json',{}) or {}).get('companies',{})
    records=load_periods(root,now);rows=[]
    primary=(read(root/'reports/primary_evidence_91.json',{}) or {}).get('companies',{})
    raw_quotes={r['ticker']:r for r in (read(root/'data/latest.json',{}) or {}).get('stocks',[])}
    if not raw_quotes:
        raw_quotes={r['ticker']:r for r in (read(root/'data/latest.json',{}) or {}).get('companies',[])}
    for ticker,quote in (read(root/'reports/priority_quotes_90.json',{}) or {}).get('quotes',{}).items():
        if quote.get('history') and quote.get('quote_date','')>=raw_quotes.get(ticker,{}).get('quote_date',''):
            raw_quotes[ticker]=quote
    for old in historical.get('companies',[]):
        ticker=old['ticker'];record=records.get(ticker,{})
        # Source financial currency is independent of quote currency.
        currency=old.get('reconciliation',{}).get('financial_currency') or primary.get(ticker,{}).get('financial_currency') or (latest(record,'revenue',now=now) or latest(record,'net_income',now=now) or {}).get('currency')
        income=latest(record,'net_income',currency=currency,now=now)
        eps=latest(record,'eps_diluted',currency=currency,now=now)
        cash=matched_cash(record,currency,now)
        metrics={k:latest(record,k,currency=None if k.endswith('shares') else currency,now=now) for k in
                 ('revenue','net_income','group_net_income','eps_diluted','cash','debt_current','debt_noncurrent','lease_current','lease_noncurrent','issued_shares','diluted_weighted_shares','acquisition_cash_paid','stock_based_compensation','goodwill_impairment','fair_value_gain')}
        vals,missing=forward(guidance.get(ticker),old,record,policy,adapters,now)
        provisional=provisional_model(record,old,policy,adapters,now) if vals is None else None
        timing=recovery_context(old,raw_quotes.get(ticker,{}))
        flags=[]
        if 'FALLBACK' in old.get('price_source',''):flags.append('LATEST_QUOTE_REFRESH_FAILED_USING_ORIGINAL_DATED_SNAPSHOT')
        if metrics['acquisition_cash_paid'] and metrics['acquisition_cash_paid']['value']>0:flags.append('ACQUISITIONS_REPORTED_GROWTH_NOT_ORGANIC')
        if guidance.get(ticker,{}).get('acquisition_regime_change'):flags.append('ACQUISITION_REGIME_CHANGE_HISTORICAL_AND_FORWARD_NOT_COMPARABLE')
        if cash['owner_cash_flow'] is None:flags.append('OWNER_CASHFLOW_COMPONENTS_NOT_FULLY_RECONCILED')
        elif cash['owner_cash_flow']<0:flags.append('NEGATIVE_OWNER_CASH_FLOW_AFTER_LEASES_AND_INTEREST')
        balance=[metrics[k] for k in ('cash','debt_current','debt_noncurrent')]
        if not all(balance) or len({r['period_end'] for r in balance if r})!=1 or any(not recent(r['period_end'],now,200) for r in balance if r):flags.append('COMPLETE_DEBT_AND_CASH_RECONCILIATION_REQUIRED')
        if metrics['debt_noncurrent'] and metrics['debt_noncurrent'].get('concept')=='LongTermDebt':flags.append('DEBT_CLASSIFICATION_OVERLAP_REVIEW')
        if metrics['fair_value_gain'] and metrics['fair_value_gain']['value']!=0:flags.append('FAIR_VALUE_GAIN_NOT_RECURRING_OPERATING_EARNINGS')
        if not income or not recent(income['period_end'],now,550):flags.append('CURRENT_COMMON_EARNINGS_NOT_RECOVERED')
        shares=observations(record,'issued_shares',now=now)
        share_change=None
        if shares:
            previous=[r for r in shares if 120<=(date.fromisoformat(shares[-1]['period_end'])-date.fromisoformat(r['period_end'])).days<=550]
            if previous and previous[-1]['value']>0:share_change=round((shares[-1]['value']/previous[-1]['value']-1)*100,3)
        if share_change is None:flags.append('DATED_DILUTION_COMPARISON_REQUIRED')
        elif abs(share_change)>15:flags.append('MATERIAL_DILUTION_OR_SPLIT_REVIEW_REQUIRED')
        price=positive(old.get('price'));upside=(vals['scenarios']['base']/price-1)*100 if vals and price else None
        preferred=upside is not None and 25<=upside<=50
        low=positive(old.get('trading_lows',{}).get('low_5d'))
        recovery=(price/low-1)*100 if price and low else None
        contextual={'ACQUISITIONS_REPORTED_GROWTH_NOT_ORGANIC','ACQUISITION_REGIME_CHANGE_HISTORICAL_AND_FORWARD_NOT_COMPARABLE'}
        blocking_flags=[f for f in flags if f not in contextual]
        credible=bool(vals and not blocking_flags and recent(old.get('quote_date'),now,7))
        rows.append({'ticker':ticker,'universe':old['universe'],'sector_method':old['sector_method'],
            'price':old.get('price'),'currency':old.get('currency'),'quote_date':old.get('quote_date'),
            'price_source':old.get('price_source'),
            'historical':{'scenarios':old.get('scenarios'),'assumptions':old.get('assumptions'),'missing_inputs':old.get('missing_inputs'),
                          'status':old['assessment_status'],'report':f'reports/valuation_90_{suffix}.json'},
            'forward':vals,'provisional_forward':provisional,'forward_missing_inputs':missing,'forward_base_upside_pct':round(upside,2) if upside is not None else None,
            'financial_currency':currency,'latest_primary_metrics':metrics,'cash_flow':cash,
            'quarterly_revenue':acceleration(record,'revenue',currency,now),'quarterly_earnings':acceleration(record,'net_income',currency,now),
            'ttm_net_income':ttm(record,'net_income',currency,now),'issued_share_change_pct':share_change,
            'acquisition_adjustments':{'reported_acquisition_cash_paid':metrics['acquisition_cash_paid'],
                'amortization':latest(record,'intangibles_amortization',currency=currency,now=now),
                'acquisition_charges':latest(record,'acquisition_charges',currency=currency,now=now),
                'organic_revenue_growth_pct':None,'proforma_earnings_adjustment':None,
                'status':'REPORTED_COSTS_SEPARATE; PRO_FORMA_AND_ORGANIC_BRIDGES_REQUIRE_PRIMARY_DISCLOSURE',
                'non_gaap_eps_not_substituted_for_gaap':True},
            'adjustment_and_risk_flags':flags,'credible_forward_candidate':credible,
            'forward_validation_blockers':blocking_flags,
            'preferred_25_50pct_upside':preferred,'pre_recovery_candidate':bool(credible and upside is not None and upside>=25 and timing['pre_recovery']),
            'recovery_context':timing,
            'recovery_from_5d_low_pct':recovery,'trading_lows':old.get('trading_lows'),'priority_entry':old.get('priority_entry'),
            'source_recovery':source_audit.get(ticker),'research_only':True,'orders_enabled':False,'buy_signal':False})
    fixed=[r for r in rows if r['universe']=='ORIGINAL_200']
    assert len(fixed)==200 and len({r['ticker'] for r in fixed})==200
    supported={r['ticker'] for r in fixed if r['historical']['scenarios']}
    before=set(baseline['valued_tickers']);lost=sorted(before-supported)
    coverage={'baseline_supported':baseline['supported_count'],'baseline_total':200,'baseline_commit':baseline['source_commit'],
              'historical_supported_after':len(supported),'net_historical_improvement':len(supported)-len(before),
              'new_historical_supported':sorted(supported-before),'lost_historical_supported':lost,
              'forward_supported_original_200':sum(bool(r['forward']) for r in fixed),
              'supported_union_original_200':sum(bool(r['historical']['scenarios'] or r['forward']) for r in fixed),
              'still_historically_unsupported':200-len(supported),'all_200_assessed':len(fixed),
              'comparison_note':'New forward views of existing names do not increase historical coverage; downloaded sources are not valuations.'}
    ranked=sorted([r for r in rows if r['pre_recovery_candidate']],key=lambda r:(not r['preferred_25_50pct_upside'],r['recovery_from_5d_low_pct'],-r['forward_base_upside_pct'],r['ticker']))[:10]
    research=[]
    for r in rows:
        view=r['forward'] or r['provisional_forward']
        if not view:continue
        p=positive(r['price']);u=(view['scenarios']['base']/p-1)*100 if p else None
        research.append({'ticker':r['ticker'],'valuation_status':view['status'],'base_upside_pct':round(u,2) if u is not None else None,
                         'preferred_25_50pct_upside':u is not None and 25<=u<=50,'recovery_context':r['recovery_context'],
                         'blocking_inputs':r['forward_missing_inputs'],'risk_flags':r['adjustment_and_risk_flags'],
                         'counts_toward_supported_coverage':r['forward'] is not None,'buy_signal':False,'orders_enabled':False})
    research.sort(key=lambda r:(not r['preferred_25_50pct_upside'],r['base_upside_pct'] is None,-(r['base_upside_pct'] or 0),r['ticker']))
    out={'schema_version':'9.2-dynamic-earnings-1','published_at_utc':now.isoformat(),'mode':mode,'coverage_comparison':coverage,
         'companies':rows,'ranked_pre_recovery_top10':ranked,'validated_pre_recovery_rankings':ranked,
         'validated_forward_rankings':[r for r in research if next(x for x in rows if x['ticker']==r['ticker'])['credible_forward_candidate']],
         'provisional_research_rankings':research,
         'validation_cases':{t:next(r for r in rows if r['ticker']==t) for t in ('HPE','SKS.AX','DUG.AX')},
         'broker_preferences':{'stocks':'Webull','crypto':'Kraken','trial_budget':1000,'trial_currency':'AUD','availability':'NOT_VERIFIED_IN_USER_ACCOUNTS','execution_enabled':False},
         'policy':policy,'orders_enabled':False,'orders_generated':0,
         'limitations':['Quarterly cash flow may be YTD only. Missing quarterly disclosure is null.',
                        'Management guidance is separately reviewed and expires at its target period end.',
                        'Valuation multiples, tax persistence and share stress are model assumptions, not issuer forecasts.',
                        'Daily prices are dated snapshots; historical valuations and forward hypotheses are separate.']}
    write(root/f'reports/dynamic_earnings_92_{suffix}.json',out)
    text=['# Championship 9.2 Dynamic Earnings Intelligence','',f"Historical coverage: **{len(before)}/200 → {len(supported)}/200** ({len(supported)-len(before):+d}).",
          f"Previously supported lost: {len(lost)}. New: {', '.join(sorted(supported-before)) or 'none'}.",
          f"Still unsupported historically: {200-len(supported)}. Source recovery is reported separately.",'',
          '| Case | Historical base | Forward base | Currency | Entry review threshold | Forward status |',
          '|---|---:|---:|---|---|---|']
    for t,r in out['validation_cases'].items():
        p=r['priority_entry'];text.append(f"| {t} | {(r['historical']['scenarios'] or {}).get('base','—')} | {((r['forward'] or {}).get('scenarios') or {}).get('base','—')} | {r['currency']} | {p['operator']} {p['threshold']} | {', '.join(r['forward_missing_inputs']) or r['forward']['eps_basis']} |")
    text+=['','Webull / Kraken. Research only; no orders or buy signals.','',
           'Forward ranges use primary management guidance and explicit policy assumptions. HPE GAAP and adjusted EPS remain separate. SKS PBT is converted with explicit tax, owner-allocation and dilution assumptions. DUG EBITDA is not EPS; no unsupported forward valuation is generated.','',
           '## Preferred opportunities before recovery','']
    text += [f"- {r['ticker']}: {r['forward_base_upside_pct']}% modeled base upside; {r['recovery_from_5d_low_pct']:.2f}% above the five-day trading low." for r in ranked] or ['No company currently passes every evidence, risk and 25–50% pre-recovery gate.']
    (root/f'reports/dynamic_earnings_92_{suffix}.md').write_text('\n'.join(text)+'\n')
    if mode=='scan':
        path=root/'reports/latest.json';bridge=read(path,{})
        if bridge and 'stocks' in bridge:
            bridge['championship_92_report']='reports/dynamic_earnings_92_latest.json'
            bridge['coverage_comparison_92']=coverage
            bridge['broker_preferences_92']=out['broker_preferences']
            mapping={r['ticker']:r for r in rows}
            for stock in bridge['stocks']:
                r=mapping.get(stock['ticker'],{})
                stock['championship_92']={k:r.get(k) for k in ('forward','forward_missing_inputs','adjustment_and_risk_flags','pre_recovery_candidate')}
            write(path,bridge)
    return out

def verify(out):
    c=out['coverage_comparison']
    assert c['all_200_assessed']==200 and out['orders_enabled'] is False and out['orders_generated']==0
    assert not c['lost_historical_supported'],c['lost_historical_supported']
    assert c['historical_supported_after']>=c['baseline_supported']==89
    for r in out['companies']:
        assert r['orders_enabled'] is False and r['buy_signal'] is False
        for view in ('historical','forward'):
            values=(r.get(view) or {}).get('scenarios')
            if values:assert 0<values['bear']<=values['base']<=values['bull']
    from championship_90 import PRIORITIES
    for t,rule in PRIORITIES.items():
        p=out['validation_cases'][t]['priority_entry']
        assert all(p[k]==rule[k] for k in ('currency','threshold','operator'))
    return c

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parent)
    parser.add_argument('--mode',choices=['scan','weekly'],default='scan');args=parser.parse_args()
    print(json.dumps(verify(build(args.root,args.mode)),indent=2))
