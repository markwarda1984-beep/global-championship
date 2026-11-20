"""Championship 6.0: evidence-gated, full-cycle, read-only intrinsic-value research.

Original research framework informed by public cyclical-analysis principles; NOT
Cory Cramer's proprietary method or investment endorsement. SEC issuer-reported
facts are primary-source evidence, not independently audited by this program.
Forecasts are explicit hypotheses, never verified facts. All missing evidence
fails closed: intrinsic value, entries, readiness and ranking are null/not validated.
No broker APIs or order execution.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
import os
import re
import statistics
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SCHEMA = '6.0-full-cycle-primary-evidence-1'
CACHE_SCHEMA = '6.0-primary-series-cache-1'
FORM_TYPES = {'10-K', '10-K/A', '20-F', '20-F/A', '40-F', '40-F/A'}
INSTANT_FORM_TYPES = FORM_TYPES | {'10-Q','10-Q/A'}
DEFAULT_ASSUMPTIONS = {
    'schema_version':'6.0-model-settings-1',
    'max_new_sec_companies_per_discovery_run':12,
    'sec_refresh_days':30,
    'minimum_recent_price_max_age_days':7,
    'minimum_stable_annual_years':4,
    'minimum_cyclical_annual_years':7,
    'minimum_bank_annual_years':4,
    'dilution_stress_pct':{'bear':15,'base':5,'bull':0},
    'dcf':{'forecast_years':5,'base_cost_of_equity_pct':14,'bear_cost_of_equity_pct':18,
           'bull_cost_of_equity_pct':12,'terminal_growth_pct':2,
           'growth_cap_low_pct':-5,'growth_cap_high_pct':8,
           'bear_growth_adjustment_pct':-5,'bull_growth_adjustment_pct':4},
    'normalized_earnings':{'base_capitalization_yield_pct':10,'bear_yield_pct':14,'bull_yield_pct':8,
                            'earnings_weight_pct':40},
    'cyclical':{'base_capitalization_yield_pct':12,'bear_yield_pct':18,
                'bull_yield_pct':9,'normalization_years':7},
    'bank_book':{'cost_of_equity_base_pct':13,'bear_pct':17,'bull_pct':11,
                 'terminal_growth_pct':2},
    'safety':{'levels_pct':[10,15,20],'default_pct':15},
    'momentum':{'positive_20d_threshold_pct':3,'negative_20d_threshold_pct':-3,
                 'positive_earnings_yoy_pct':5,'negative_earnings_yoy_pct':-5},
    'asset_nav':'REQUIRES_VALIDATED_ISSUER_ASSET_APPRAISALS_WITH_LIABILITIES_AND_SHARE_BASIS',
    'forward_earnings':'MODELLED_FROM_VERIFIED_HISTORY_NOT_VERIFIED_COMPANY_GUIDANCE',
    'source_risk':'No independent audit, business-quality guarantee, or validated long-run forecast. No trades.'
}

BANKS={'JPM','BAC','GS','MS','C','WFC','PGR','CBA.AX','NAB.AX','WBC.AX','ANZ.AX',
       'MQG.AX','QBE.AX','SUN.AX','IAG.AX','HSBC','UBS','RY','TD','IBN'}
SPECIAL_ASSET={'BRK-B','BN','MSTR','GMG.AX','SCG.AX'}
REITS={'GMG.AX','SCG.AX'}
BIOTECH={'SLS','OKLO','SMR'}  # project-stage companies require specialist project/rNPV work
RESOURCE={'CAT','DE','URI','BA','BHP.AX','RIO.AX','FMG.AX','MIN.AX','WDS.AX','LYC.AX','LOT.AX','GG8.AX',
          'SFR.AX','PDN.AX','BOE.AX','PLS.AX','STO.AX','XOM','CVX','COP','OXY','SLB',
          'EOG','MPC','VLO','CCJ','UEC','UUUU','LEU','FCX','NEM','AEM','PAAS','SHEL',
          'BP','TTE','EQNR','CNQ','SU'}
FIN_SPECIAL={'COIN','HOOD','SOFI','AFRM','BLK','SCHW','KKR','BX','APO','NU'}
ADR_OR_OVERSEAS_SHARE_BASIS={'BABA','BIDU','JD','PDD','TCEHY','NTES','TSM','ASML',
    'NVO','AZN','NVS','ARM','IBN','INFY','SHEL','BP','TTE','EQNR','HSBC','UBS'}
TAG_MAP={
    'shares':[('dei','EntityCommonStockSharesOutstanding','shares'),('us-gaap','CommonStockSharesOutstanding','shares')],
    'revenue':[('us-gaap','RevenueFromContractWithCustomerExcludingAssessedTax','USD'),
               ('us-gaap','Revenues','USD'),('us-gaap','SalesRevenueNet','USD')],
    'net_income':[('us-gaap','NetIncomeLoss','USD'),('us-gaap','ProfitLoss','USD')],
    'operating_cash_flow':[('us-gaap','NetCashProvidedByUsedInOperatingActivities','USD')],
    'capex':[('us-gaap','PaymentsToAcquirePropertyPlantAndEquipment','USD')],
    'equity':[('us-gaap','StockholdersEquity','USD')],
    'assets':[('us-gaap','Assets','USD')],
    'liabilities':[('us-gaap','Liabilities','USD')],
}


def read(path:Path,default:Any=None)->Any:
    try: return json.loads(path.read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError): return default


def write(path:Path,obj:Any)->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
    tmp.replace(path)


def pos(value:Any)->float|None:
    try:
        v=float(value)
        return v if math.isfinite(v) and v>0 else None
    except (TypeError,ValueError,OverflowError):return None


def finite(value:Any)->float|None:
    try:
        v=float(value)
        return v if math.isfinite(v) else None
    except (TypeError,ValueError,OverflowError):return None


def dt(value:Any)->date|None:
    try:return date.fromisoformat(str(value)[:10])
    except (ValueError,TypeError):return None


def pct_delta(new:float|None,old:float|None)->float|None:
    return round((new/old-1)*100,2) if new is not None and old is not None and old>0 else None


def validate_cfg(cfg:dict)->dict:
    x=cfg
    if not isinstance(x,dict):raise ValueError('6.0 model settings must be an object')
    if not 1<=int(x['max_new_sec_companies_per_discovery_run'])<=25:raise ValueError('SEC batch size unsafe')
    if not 2<=int(x['minimum_stable_annual_years'])<=8:raise ValueError('Insufficient stable history constraint')
    if not 5<=int(x['minimum_cyclical_annual_years'])<=12:raise ValueError('Cyclical history must include a full proxy cycle')
    if sorted(x['safety']['levels_pct'])!=[10,15,20]:raise ValueError('Safety levels must be 10/15/20')
    d=x['dcf']
    if not 3<=int(d['forecast_years'])<=10:raise ValueError('DCF horizon unsafe')
    rates=[d[k]/100 for k in ('bear_cost_of_equity_pct','base_cost_of_equity_pct','bull_cost_of_equity_pct')]
    t=d['terminal_growth_pct']/100
    if not all(t+.035<r<.50 for r in rates):raise ValueError('Discount rates must exceed terminal growth')
    if not all(0<=v<=50 for v in x['dilution_stress_pct'].values()):raise ValueError('Dilution out of bounds')
    return x


def watchlist(root:Path)->list[dict]:
    with (root/'watchlist.csv').open(newline='',encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
    tickers=[str(r.get('ticker','')).upper().strip() for r in rows]
    if len(tickers)!=200 or len(set(tickers))!=200 or not all(tickers):
        raise ValueError('Original 200-stock watchlist cannot be altered')
    return rows


def universe(root:Path)->tuple[list[dict],set[str]]:
    original=watchlist(root)
    names={str(x['ticker']).upper():{'ticker':str(x['ticker']).upper(),
          'company':x.get('name',''),'category':x.get('sector',''),'universe':'ORIGINAL_200'} for x in original}
    discovery=read(root/'reports/discovery_watchlist.json',{}) or {}
    if discovery.get('orders_enabled') is True or discovery.get('original_200_unchanged') is False:
        raise ValueError('Discovery safety guard failed')
    for ticker,c in (discovery.get('candidates') or {}).items():
        if ticker in names or not re.fullmatch(r'[A-Z0-9.\-]{1,12}',ticker):continue
        if not isinstance(c,dict):continue
        if c.get('status') not in ('MONITOR','PENDING_EVIDENCE','ARCHIVED_MONITORING'):continue
        names[ticker]={'ticker':ticker,'company':c.get('company',''),
                       'category':c.get('theme','DISCOVERY'), 'universe':'DISCOVERY',
                       'discovery_status':c.get('status')}
    return list(names.values()),set(x['ticker'] for x in original)


def method(ticker:str,category:str)->str:
    c=category.lower()
    if ticker in REITS or 'reit' in c:return 'PROPERTY_ASSET_NAV_OR_AFFO'
    if ticker in BANKS:return 'BANK_INSURER_JUSTIFIED_BOOK'
    if ticker in SPECIAL_ASSET:return 'HOLDING_COMPANY_ASSET_NAV'
    if ticker in FIN_SPECIAL:return 'SPECIALIST_FINANCIAL_CAPITAL_STRUCTURE'
    if ticker in BIOTECH or ('biotech' in c and ticker not in ('LLY','NVO')):return 'PROJECT_RISK_ADJUSTED_NAV'
    if ticker in RESOURCE or any(k in c for k in ('resources','mining','uranium','rare earth','oil','cyclical')):
        return 'FULL_CYCLE_NORMALIZED_EARNINGS'
    if 'defence' in c:return 'NORMALIZED_EARNINGS_AND_DCF'
    return 'NORMALIZED_EARNINGS_AND_DCF'


def bounded_facts(source:dict,tag:str,now:datetime,*,annual:bool)->list[dict]:
    """Read issuer-XBRL tagged numbers, with dates and filing accession provenance."""
    results=[]
    for taxonomy,concept,unit in TAG_MAP[tag]:
        data=source.get('facts',{}).get(taxonomy,{}).get(concept,{}).get('units',{}).get(unit,[])
        if not isinstance(data,list):continue
        for item in data:
            if not isinstance(item,dict) or item.get('form') not in (FORM_TYPES if annual else INSTANT_FORM_TYPES):continue
            end=dt(item.get('end'));filed=dt(item.get('filed'));start=dt(item.get('start'))
            if not end or not filed or end>now.date() or filed>now.date():continue
            if (now.date()-filed).days<0 or (now.date()-end).days>4200:continue
            if annual and (not start or not 330<=(end-start).days<=385):continue
            if not annual and start:continue
            n=finite(item.get('val'))
            if n is None or (tag in ('shares','assets','equity') and n<=0):continue
            results.append({'value':n,'unit':unit,'start':str(start) if start else None,
                  'end':str(end),'filed':str(filed),'form':item['form'],
                  'accession':item.get('accn'),'tag':concept,'taxonomy':taxonomy})
        if results:break  # never mix different revenue/equity concepts in the same series
    chosen={}
    for f in results:
        k=f['end']
        if k not in chosen or (f['filed'],f['accession'] or '')>(chosen[k]['filed'],chosen[k]['accession'] or ''):
            chosen[k]=f
    return sorted(chosen.values(),key=lambda f:f['end'])


def primary_series(ticker:str,raw:dict,now:datetime,cik:int)->dict:
    if not isinstance(raw,dict) or int(raw.get('cik',0))!=int(cik) or not raw.get('entityName'):
        raise ValueError('SEC CIK or issuer name missing/mismatched')
    f={key:bounded_facts(raw,key,now,annual=(key not in ('shares','equity','assets','liabilities')))
       for key in TAG_MAP}
    # Recent share count, no silent mixing of 20-year-old share basis.
    shares=[x for x in f['shares'] if dt(x['end']) and (now.date()-dt(x['end'])).days<=500]
    most_recent=max(shares,key=lambda x:x['end']) if shares else None
    series={key:f[key][-12:] if key not in ('shares',) else f[key][-8:] for key in f}
    return {'ticker':ticker,'issuer_name':str(raw['entityName'])[:160],
            'cik':int(cik),'source_url':f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json',
            'observed_utc':now.isoformat(),'status':'OFFICIAL_SEC_COMPANYFACTS_RETRIEVED',
            'primary_source_type':'ISSUER_XBRL_SEC','primary_statements_are_issuer_reported':True,
            'latest_share_count':most_recent,'annual_facts':series,
            'evidence_hash_sha256':hashlib.sha256(json.dumps(series,sort_keys=True).encode()).hexdigest(),
            'orders_enabled':False}


def combine_periods(row:dict)->list[dict]:
    """A fiscal-year FCF exists only if OCF and CAPEX use exactly the same interval."""
    f=row.get('annual_facts',{})
    oo={x['end']:x for x in f.get('operating_cash_flow',[]) if x.get('start')}
    cc={x['end']:x for x in f.get('capex',[]) if x.get('start')}
    ni={x['end']:x for x in f.get('net_income',[]) if x.get('start')}
    rev={x['end']:x for x in f.get('revenue',[]) if x.get('start')}
    result=[]
    for end in sorted(set(oo)|set(ni)|set(rev)):
        o=oo.get(end);c=cc.get(end)
        fcf=(o['value']-c['value']) if (o and c and o['start']==c['start']
             and o.get('accession') and o['accession']==c.get('accession')) else None
        result.append({'year_end':end,'net_income':ni.get(end,{}).get('value'),
             'revenue':rev.get(end,{}).get('value'), 'fcf':fcf,
             'fcf_source_accessions':[o.get('accession'),c.get('accession')] if fcf is not None else [],
             'earnings_accession':ni.get(end,{}).get('accession'),
             'cash_period_start':o['start'] if fcf is not None else None,
             'cash_period_end':end if fcf is not None else None})
    return result


def dated_recent(iso:Any,now:datetime,days:int=550)->bool:
    x=dt(iso)
    return bool(x and 0<=(now.date()-x).days<=days)


def contiguous_history(periods:list[dict],key:str,years:int,now:datetime)->list[dict]|None:
    vals=[x for x in periods if finite(x.get(key)) is not None]
    if len(vals)<years:return None
    recent=vals[-years:]
    if not dated_recent(recent[-1]['year_end'],now,days=550):return None
    for a,b in zip(recent,recent[1:]):
        d=(dt(b['year_end'])-dt(a['year_end'])).days
        if not 330<=d<=400:return None
    return recent


def dcf(fcf_per_share:float,growth:float,discount:float,terminal:float,years:int)->float:
    if fcf_per_share<=0 or discount<=terminal+.035 or years<3 or not -.20<=growth<=.25:
        raise ValueError('Unsafe DCF assumptions')
    cash=fcf_per_share;pv=0
    for year in range(1,years+1):
        cash*=1+growth
        pv+=cash/(1+discount)**year
    return pv+cash*(1+terminal)/(discount-terminal)/(1+discount)**years


def stress_adjust(x:float,stress_pct:float)->float:
    return x/(1+stress_pct/100)


def momentum(row:dict,history:list[dict],cfg:dict)->dict:
    vals=history
    a=finite(vals[-1].get('net_income')) if len(vals)>=1 else None
    b=finite(vals[-2].get('net_income')) if len(vals)>=2 else None
    ey=pct_delta(a,b) if a is not None and b is not None and b>0 else None
    cp=finite(row.get('change_20d_pct'))
    c63=finite(row.get('change_63d_pct'))
    sma50=pos(row.get('sma_50'));sma200=pos(row.get('sma_200'))
    price=pos(row.get('price')) or pos(row.get('last_daily_close'))
    price_signal='UNAVAILABLE'
    if cp is not None and c63 is not None:
        if cp>=cfg['momentum']['positive_20d_threshold_pct'] and c63>0 and (not sma50 or (price and price>=sma50)):
            price_signal='POSITIVE'
        elif cp<=cfg['momentum']['negative_20d_threshold_pct'] or c63<0:
            price_signal='NEGATIVE'
        else: price_signal='MIXED'
    earnings_signal=('UNAVAILABLE' if ey is None else 'IMPROVING' if ey>=cfg['momentum']['positive_earnings_yoy_pct']
                     else 'DECLINING' if ey<=cfg['momentum']['negative_earnings_yoy_pct'] else 'FLAT')
    safety=15
    if earnings_signal=='IMPROVING' and price_signal=='POSITIVE':safety=10
    elif earnings_signal=='DECLINING' or price_signal=='NEGATIVE':safety=20
    return {'earnings_yoy_pct':ey,'earnings_signal':earnings_signal,
       'price_change_20d_pct':cp,'price_change_63d_pct':c63,
       'price_signal':price_signal,'evidence':'SEC issuer reported annual net income; Yahoo daily-bar momentum',
       'momentum_selected_margin_of_safety_pct':safety,
       'warning':'Momentum selects safety among 10/15/20 ONLY AFTER primary valuation validation.'}


def scenario_values(sector:str,periods:list[dict],primary:dict,cfg:dict,now:datetime)->tuple[dict|None,dict,list[str]]:
    """Return primary-backed valuation hypotheses and assumptions, or NULL. No vendor valuations."""
    flags=[];assumptions={}
    shares=primary.get('latest_share_count') or {}
    sh=pos(shares.get('value'))
    if not sh or not dated_recent(shares.get('end'),now,500):
        return None,assumptions,['CURRENT_PRIMARY_SHARE_COUNT_MISSING']
    prior_shares=[x for x in primary.get('annual_facts',{}).get('shares',[])
         if pos(x.get('value')) and dt(x.get('end')) and 120<=(dt(shares['end'])-dt(x['end'])).days<=550]
    if not prior_shares:
        return None,assumptions,['SECOND_INDEPENDENT_DATED_PRIMARY_SHARE_COUNT_REQUIRED']
    prior=max(prior_shares,key=lambda x:x['end'])
    variation=abs(sh/prior['value']-1)
    if variation>.15:
        return None,assumptions,['PRIMARY_SHARE_BASIS_CHANGE_OVER_15PCT_SPLIT_OR_DILUTION_REVIEW']
    assumptions['historical_filing_share_count_check']={'current_shares':sh,'prior_shares':prior['value'],
          'prior_as_of':prior['end'],'observed_share_basis_change_pct':round((sh/prior['value']-1)*100,3)}
    if sector in ('HOLDING_COMPANY_ASSET_NAV','PROPERTY_ASSET_NAV_OR_AFFO',
                  'SPECIALIST_FINANCIAL_CAPITAL_STRUCTURE','PROJECT_RISK_ADJUSTED_NAV'):
        return None,assumptions,['SPECIALIST_ASSET_OR_PIPELINE_EVIDENCE_REQUIRED',
            'PROPERTY_APPRAISAL_OR_AFFO_OR_RESERVE_VALUE_NOT_VERIFIED']
    pct=cfg['dilution_stress_pct'];d=cfg['dcf'];n=d['forecast_years']
    if sector=='BANK_INSURER_JUSTIFIED_BOOK':
        yrs=cfg['minimum_bank_annual_years']
        inc=contiguous_history(periods,'net_income',yrs,now)
        if not inc:return None,assumptions,['MULTIYEAR_NET_INCOME_INSUFFICIENT']
        equity=[x for x in primary.get('annual_facts',{}).get('equity',[]) if pos(x.get('value'))]
        if len(equity)<yrs:return None,assumptions,['PRIMARY_EQUITY_HISTORY_INSUFFICIENT']
        eq_now=equity[-1];eq_ago=equity[-2]
        if not dated_recent(eq_now['end'],now,550):return None,assumptions,['PRIMARY_EQUITY_STALE']
        if not 330<=(dt(eq_now['end'])-dt(eq_ago['end'])).days<=400:
            return None,assumptions,['EQUITY_YEAR_COMPARABILITY_UNVERIFIED']
        if eq_now['value']<=0 or eq_ago['value']<=0:return None,assumptions,['NEGATIVE_PRIMARY_EQUITY']
        avg_income=statistics.median(x['net_income'] for x in inc)
        if avg_income<=0:return None,assumptions,['NONPOSITIVE_CYCLE_NET_INCOME']
        avg_equity=(eq_now['value']+eq_ago['value'])/2
        roe=avg_income/avg_equity
        g=cfg['bank_book']['terminal_growth_pct']/100
        if not .03<=roe<=.40:return None,assumptions,['ROE_OUTSIDE_REASONABLE_RANGE']
        book=eq_now['value']/sh
        def intrinsic(ke):return book*max(0,(roe-g)/(ke-g))
        val={k:stress_adjust(intrinsic(cfg['bank_book'][key]/100),pct[k.split('_')[0]])
             for k,key in [('bear','bear_pct'),('base','cost_of_equity_base_pct'),('bull','bull_pct')]}
        assumptions={'formula':'BOOK_VALUE_PER_SHARE × (NORMALIZED_ROE - g)/(COST_OF_EQUITY-g)',
           'book_value_per_share_primary':round(book,6),'median_annual_net_income_primary':round(avg_income,2),
           'normalized_roe_assumption_from_filed_history_pct':round(roe*100,3),
           'discount_rates_pct':{k:cfg['bank_book'][z] for k,z in [('bear','bear_pct'),('base','cost_of_equity_base_pct'),('bull','bull_pct')]},
           'growth_pct':cfg['bank_book']['terminal_growth_pct'],'years_observed':yrs,
           'provenance':'SEC XBRL filed net-income, shareholders equity and issued shares; forecast cost of equity remains ASSUMPTION'}
    elif sector=='FULL_CYCLE_NORMALIZED_EARNINGS':
        yrs=cfg['minimum_cyclical_annual_years']
        ni=contiguous_history(periods,'net_income',yrs,now)
        fcf=contiguous_history(periods,'fcf',yrs,now)
        if not ni or not fcf:return None,assumptions,['CYCLICAL_FULL_CYCLE_SEVEN_YEARS_NOT_EVIDENCED']
        if any(x['fcf'] is None for x in fcf):return None,assumptions,['FCF_PERIODS_NOT_RECONCILED']
        normalized_earn=statistics.median(x['net_income'] for x in ni)
        normalized_fcf=statistics.median(x['fcf'] for x in fcf)
        if normalized_fcf<=0 or normalized_earn<=0:return None,assumptions,['NORMALIZED_CYCLE_NONPOSITIVE']
        # Original full-cycle earnings + owner-cashflow conservative blend, without peak extrapolation.
        normal_per_share=(normalized_earn*.5+normalized_fcf*.5)/sh
        cy=cfg['cyclical']
        val={k:stress_adjust(normal_per_share/(cy[z]/100),pct[k])
             for k,z in [('bear','bear_yield_pct'),('base','base_capitalization_yield_pct'),('bull','bull_yield_pct')]}
        assumptions={'formula':'(MEDIAN_7Y_EARNINGS + MEDIAN_7Y_FREE_CASH_FLOW)/2 ÷ capitalization_yield ÷ diluted_shares',
          'annual_years':yrs,'earnings_median_filed':round(normalized_earn,2),
          'fcf_median_filed':round(normalized_fcf,2),
          'capitalization_yields_pct':{k:cy[z] for k,z in [('bear','bear_yield_pct'),('base','base_capitalization_yield_pct'),('bull','bull_yield_pct')]},
          'cycle_limitation':'7 years is a proxy; commodity reserve NAV and full multi-cycle durability are unverified'}
    else:
        yrs=cfg['minimum_stable_annual_years']
        ni=contiguous_history(periods,'net_income',yrs,now)
        cf=contiguous_history(periods,'fcf',yrs,now)
        if not ni or not cf:return None,assumptions,['MINIMUM_FOUR_YEAR_PRIMARY_EARNINGS_AND_FCF_HISTORY_MISSING']
        f=[x['fcf'] for x in cf]
        ni_v=[x['net_income'] for x in ni]
        if min(f)<=0 or statistics.median(ni_v)<=0:return None,assumptions,['LOSS_OR_NEGATIVE_FREE_CASH_FLOW_NEEDS_SPECIALIST_MODEL']
        # Cap historical observed growth; do not call it verified future guidance.
        median_fcf=statistics.median(f)
        growth=(f[-1]/f[0])**(1/(yrs-1))-1 if f[0]>0 and f[-1]>0 else 0
        growth=max(d['growth_cap_low_pct']/100,min(d['growth_cap_high_pct']/100,growth))
        start=median_fcf/sh
        t=d['terminal_growth_pct']/100
        def rate(k):return d[k]/100
        vals={
         'bear':dcf(start*.75,max(-.12,growth+d['bear_growth_adjustment_pct']/100),rate('bear_cost_of_equity_pct'),t,n),
         'base':dcf(start,growth,rate('base_cost_of_equity_pct'),t,n),
         'bull':dcf(start*1.15,min(.18,growth+d['bull_growth_adjustment_pct']/100),rate('bull_cost_of_equity_pct'),t,n),
        }
        # Earnings cross-check; a valuation requiring an inconsistent NI basis does not pass.
        norm_ni=statistics.median(ni_v)
        earnings_per_share=norm_ni/sh
        if earnings_per_share<=0:return None,assumptions,['NORMALIZED_EARNINGS_NONPOSITIVE']
        ne=cfg['normalized_earnings'];w=ne['earnings_weight_pct']/100
        earn_vals={'bear':earnings_per_share/(ne['bear_yield_pct']/100),
                   'base':earnings_per_share/(ne['base_capitalization_yield_pct']/100),
                   'bull':earnings_per_share/(ne['bull_yield_pct']/100)}
        val={k:stress_adjust((1-w)*vals[k]+w*earn_vals[k],pct[k]) for k in ('bear','base','bull')}
        forward_net_income_estimate=ni_v[-1]*(1+growth)
        assumptions={'formula':'BLEND: 60% 5-YEAR EQUITY FCF DCF + 40% NORMALIZED EARNINGS CAPITALIZATION',
           'cashflow_median_of_filed_years':round(median_fcf,2),
           'median_annual_net_income_filed':round(norm_ni,2),
           'historical_fcf_cagr_observed_pct':round(((f[-1]/f[0])**(1/(yrs-1))-1)*100,3),
           'assumed_forward_growth_capped_pct':round(growth*100,3),
           'illustrative_next_year_net_income_not_issuer_guidance':round(forward_net_income_estimate,2),
           'dcf_forecast_years':n,'base_discount_pct':d['base_cost_of_equity_pct'],
           'bear_discount_pct':d['bear_cost_of_equity_pct'],'bull_discount_pct':d['bull_cost_of_equity_pct'],
           'terminal_growth_pct':d['terminal_growth_pct'],'earnings_capitalization_yields_pct':{
           'bear':ne['bear_yield_pct'],'base':ne['base_capitalization_yield_pct'],'bull':ne['bull_yield_pct']},
           'earnings_weight_pct':ne['earnings_weight_pct'],
           'history_years':yrs,
           'forecast_status':'ANALYST_HYPOTHESIS_NOT_VERIFIED_FORWARD_GUIDANCE'}
    if not all(pos(x) for x in val.values()):return None,assumptions,['NONPOSITIVE_OR_INVALID_VALUATION']
    if not val['bear']<=val['base']<=val['bull']:
        return None,assumptions,['BEAR_BASE_BULL_SCENARIO_ORDER_INCONSISTENT']
    assumptions['historical_filing_share_count_check']={'current_shares':sh,'prior_shares':prior['value'],
          'prior_as_of':prior['end'],'observed_share_basis_change_pct':round((sh/prior['value']-1)*100,3)}
    assumptions['hypothetical_future_issuance_pct']=pct
    assumptions['issued_share_count_primary']=sh
    assumptions['source_dates']={'shares':shares.get('end'),'net_income_fiscal_years':[
        x['year_end'] for x in periods if x.get('net_income') is not None][-9:]}
    return {k:round(val[k],4) for k in ('bear','base','bull')},assumptions,flags


def asset_nav_book_proxy(primary:dict,now:datetime)->dict|None:
    """Filed net-book-assets per share, NEVER property appraisal or intrinsic value.

    A genuine asset-based market NAV additionally requires an issuer-supported asset
    valuation/appraisal, audited debt and liabilities, and capital structure review.
    Without them we expose this as context only and block all entry targets.
    """
    f=primary.get('annual_facts',{})
    a={x['end']:x for x in f.get('assets',[]) if pos(x.get('value'))}
    l={x['end']:x for x in f.get('liabilities',[]) if finite(x.get('value')) is not None}
    common=sorted(set(a)&set(l))
    shares=primary.get('latest_share_count') or {}
    if not common or not pos(shares.get('value')):return None
    end=common[-1]
    if not dated_recent(end,now,550):return None
    if abs((dt(end)-dt(shares['end'])).days)>450:return None
    book=(a[end]['value']-l[end]['value'])/shares['value']
    if not math.isfinite(book):return None
    return {'filed_book_net_assets_per_share_not_market_nav':round(book,4),
            'unit':'USD/share','as_of':end,'primary_source':primary.get('source_url'),
            'valuation_status':'INFORMATION_ONLY_NOT_INTRINSIC_VALUE',
            'blockers':['ISSUER_APPRAISED_ASSET_MARKET_VALUE_NOT_EVIDENCED',
                        'GOODWILL_INTANGIBLES_AND_CONTINGENT_LIABILITIES_NOT_RECONCILED']}


def asset_nav_formula(appraised_asset_value:float,fully_loaded_liabilities:float,
                      primary_shares:float,*,bear_haircut_pct:float=25,
                      base_haircut_pct:float=10,bull_haircut_pct:float=0)->dict:
    """A specialist asset-model math primitive; cannot be used without verified
    external appraisal evidence and all liabilities. No automatic NAV guesses.
    """
    if not pos(appraised_asset_value) or not pos(primary_shares):raise ValueError('Asset NAV evidence missing')
    debt=finite(fully_loaded_liabilities)
    if debt is None or debt<0:raise ValueError('Liabilities must be confirmed')
    if not 0<=bull_haircut_pct<=base_haircut_pct<=bear_haircut_pct<=70:
        raise ValueError('Unsafe asset scenario haircuts')
    vals={k:(appraised_asset_value*(1-h/100)-debt)/primary_shares for k,h in
          (('bear',bear_haircut_pct),('base',base_haircut_pct),('bull',bull_haircut_pct))}
    if any(x<=0 for x in vals.values()):raise ValueError('Net assets insufficient for NAV estimate')
    return {k:round(v,4) for k,v in vals.items()}


def latest_quote(root:Path,original:set[str])->dict[str,dict]:
    # Scanner source is daily bars, never a real-time executable bid/ask.
    raw=read(root/'data/latest.json',{}) or {}
    prices={str(x.get('ticker')).upper():x for x in raw.get('stocks',[]) if isinstance(x,dict)}
    bridge=read(root/'reports/latest.json',{}) or {}
    for r in bridge.get('stocks',[]):
        p=prices.setdefault(str(r.get('ticker')).upper(),{})
        p.setdefault('price',r.get('last_daily_close'))
        p.setdefault('quote_date',r.get('quote_date'))
        p.setdefault('currency',r.get('currency'))
    d=read(root/'reports/discovery_watchlist.json',{}) or {}
    for ticker,c in (d.get('candidates') or {}).items():
        if ticker in original:continue
        q=c.get('last_quote') or {}
        prices[ticker]={'price':q.get('price'), 'quote_date':q.get('quote_date'),
            'currency':q.get('currency'), 'stale_days':q.get('stale_days'),
            'price_source':'DISCOVERY_DAILY_HISTORY_NOT_LIVE'}
    return prices


def missing_row(name:dict,price:dict,sector:str,now:datetime,flags:list[str],mom:dict)->dict:
    return {'ticker':name['ticker'],'company':name['company'],'universe':name['universe'],
       'sector_method':sector,'validation_status':'NOT VALIDATED',
       'verified_intrinsic_value':None,'bear':None,'base':None,'bull':None,
       'margin_of_safety_entries':{'10pct':None,'15pct':None,'20pct':None},
       'price_distance_to_entries_pct':{'10pct':None,'15pct':None,'20pct':None},
       'selected_margin_of_safety_pct':None,'selected_entry':None,
       'latest_dated_price':pos(price.get('price')) or pos(price.get('last_daily_close')),
       'price_currency':price.get('currency'), 'price_as_of':price.get('quote_date'),
       'earnings_momentum':{'status':mom['earnings_signal'],'change_pct':mom['earnings_yoy_pct']},
       'earnings_revisions':{'status':'NOT VALIDATED — NO PRIMARY GUIDANCE OR CONSENSUS REVISION SERIES',
                            'upward_revisions':None,'downward_revisions':None,
                            'estimated_eps_change_pct':None,
                            'evidence_note':'Annual income growth is NOT an earnings estimate revision'},
       'price_momentum':{'status':mom['price_signal'],'change_20d_pct':mom['price_change_20d_pct'],
                          'change_63d_pct':mom['price_change_63d_pct']},
       'source_confidence':'INSUFFICIENT_PRIMARY_ECONOMIC_EVIDENCE',
       'primary_source_evidence':None,'assumptions':None,
       'asset_book_nav_reference':None,
       'missing_evidence_flags':sorted(set(flags)),
       'risks':['Filing data, share basis, forecast and source gaps prevent evidence-qualified valuation'],
       'buy_readiness':{'status':'NOT VALIDATED','score_pct':None,'reason':'No approved purchase target'},
       'research_only':True,'orders_enabled':False}


def evaluate_all(root:Path,now:datetime,cfg:dict)->dict:
    names,original=universe(root)
    prices=latest_quote(root,original)
    cache=read(root/'reports/primary_series_cache_60.json',{}) or {}
    if cache and cache.get('orders_enabled') is True:raise ValueError('Unsafe evidence cache')
    report=[];verified=0;flag_totals={}
    for name in names:
        t=name['ticker'];sector=method(t,name['category']);p=prices.get(t,{}) or {}
        src=(cache.get('companies') or {}).get(t,{})
        periods=combine_periods(src)
        mom=momentum(p,periods,cfg)
        price=pos(p.get('price')) or pos(p.get('last_daily_close'))
        quote_date=p.get('quote_date')
        flags=[]
        if not price:flags.append('DATED_PRICE_NOT_AVAILABLE')
        elif not dated_recent(quote_date,now,cfg['minimum_recent_price_max_age_days']):flags.append('PRICE_STALE_OR_UNDATED')
        if src.get('status')!='OFFICIAL_SEC_COMPANYFACTS_RETRIEVED':
            flags.append(src.get('status') or ('ASX_PRIMARY_STATEMENT_ADAPTER_REQUIRED' if t.endswith('.AX') else 'PRIMARY_XBRL_NOT_COLLECTED'))
        elif not dated_recent(src.get('observed_utc'),now,cfg['sec_refresh_days']+4):
            flags.append('PRIMARY_EVIDENCE_CACHE_STALE')
        if price and src.get('status')=='OFFICIAL_SEC_COMPANYFACTS_RETRIEVED' and not flags:
            currency=str(p.get('currency') or '').upper()
            if currency!='USD':flags.append('QUOTE_PRIMARY_FILING_CURRENCY_OR_ADR_RATIO_UNVERIFIED')
            if t.endswith('.AX'):flags.append('ASX_ACCOUNTING_AND_SHARE_BASIS_NOT_VERIFIED')
            if t in ADR_OR_OVERSEAS_SHARE_BASIS or name['category']=='International':
                flags.append('ADR_OR_FOREIGN_PRIMARY_SHARE_BASIS_NOT_RECONCILED')
        values=None;assumptions={}
        if not flags:
            values,assumptions,model_flags=scenario_values(sector,periods,src,cfg,now)
            flags.extend(model_flags)
        if not flags and values:
            verified+=1
            safety=mom['momentum_selected_margin_of_safety_pct']
            base=values['base']
            entries={f'{p}pct':round(base*(1-p/100),4) for p in (10,15,20)}
            distances={k:round((price/v-1)*100,2) if price and v else None for k,v in entries.items()}
            selected=entries[f'{safety}pct']
            row=missing_row(name,p,sector,now,[],mom)
            row.update(validation_status='PRIMARY_INPUTS_VALIDATED_FORECASTS_HYPOTHETICAL',
                 verified_intrinsic_value=base,bear=values['bear'],base=base,bull=values['bull'],
                 margin_of_safety_entries=entries,price_distance_to_entries_pct=distances,
                 selected_margin_of_safety_pct=safety,selected_entry=selected,
                 source_confidence='ISSUER_REPORTED_SEC_XBRL_MULTIPERIOD_NOT_INDEPENDENTLY_AUDITED',
                 primary_source_evidence={'url':src['source_url'],'cik':src['cik'],
                  'issuer':src['issuer_name'],'share_count_record':src['latest_share_count'],
                  'source_hash_sha256':src['evidence_hash_sha256'],
                  'annual_statements_used':[x for x in periods if x.get('fcf') is not None][-10:]},
                 assumptions=assumptions,missing_evidence_flags=[],
                 risks=['Forecast growth, discount rates and future dilution are scenarios, not issuer-verified outcomes',
                        'Historical cycles may not repeat; financing, debt, FX and corporate actions require review',
                        'SEC XBRL facts are issuer reported, not independently audited by this system'],
                 buy_readiness={'status':'RESEARCH_READY_HUMAN_DILIGENCE_REQUIRED' if price<=selected else 'WAIT_FOR_MARGIN_OF_SAFETY',
                    'score_pct':None,'reason':'Evidence-qualified scenario; no automatic trade approval'})
        else:row=missing_row(name,p,sector,now,flags,mom)
        if sector in ('PROPERTY_ASSET_NAV_OR_AFFO','HOLDING_COMPANY_ASSET_NAV'):
            row['asset_book_nav_reference']=asset_nav_book_proxy(src,now)
        sector_risks={'FULL_CYCLE_NORMALIZED_EARNINGS':['Peak commodity/industrial cycle earnings can make price/earnings falsely cheap', 'Balance-sheet survival across trough not yet independently assessed'],
          'BANK_INSURER_JUSTIFIED_BOOK':['Credit losses, underwriting reserves and regulatory capital may invalidate book-value ROE estimates'],
          'PROPERTY_ASSET_NAV_OR_AFFO':['Property appraisals, lease duration, debt maturities and AFFO must be verified'],
          'HOLDING_COMPANY_ASSET_NAV':['Consolidated book assets may not represent realizable NAV; goodwill and cross-holdings require review'],
          'PROJECT_RISK_ADJUSTED_NAV':['Clinical, permitting and project financing probabilities are unverified'],
          'NORMALIZED_EARNINGS_AND_DCF':['Forecast-growth extrapolation, capital intensity and competitive durability remain unverified']}
        row['risks']=list(dict.fromkeys([*row['risks'],*sector_risks.get(sector,[])]))
        row['report_as_of_utc']=now.isoformat()
        for flag in row['missing_evidence_flags']:flag_totals[flag]=flag_totals.get(flag,0)+1
        report.append(row)
    if len([x for x in report if x['universe']=='ORIGINAL_200'])!=200:raise ValueError('200 changed')
    if any(x.get('orders_enabled') is not False or x.get('research_only') is not True for x in report):
        raise ValueError('No-trading invariant violated')
    return {'schema_version':SCHEMA,'published_at_utc':now.isoformat(),
        'original_watchlist_count':200,'discovery_company_count':len(report)-200,
        'reported_count':len(report),'validated_inputs_count':verified,
        'not_validated_count':len(report)-verified,
        'ranked_research_top10':sorted([
             {'ticker':x['ticker'],'base':x['base'],
              'bear':x['bear'],'bull':x['bull'],'price':x['latest_dated_price'],
              'asymmetric_base_upside_pct':pct_delta(x['base'],x['latest_dated_price']),
              'bear_downside_pct':pct_delta(x['bear'],x['latest_dated_price']),
              'asymmetry_ratio_not_probability':round(
                 max(0.,x['base']/x['latest_dated_price']-1) /
                 max(.05,1-x['bear']/x['latest_dated_price']),4),
              'momentum_mos_pct':x['selected_margin_of_safety_pct']}
              for x in report if x['validation_status']!='NOT VALIDATED'],
              key=lambda x:(-(max(0.,(x['base']/x['price']-1)) / max(.05,(1-x['bear']/x['price']))),x['ticker']))[:10],
        'missing_evidence_flag_counts':flag_totals,
        'companies':report,'value_definition':'Evidence-backed inputs and ASSUMED forecasts. Estimated intrinsic value is NOT an objective certified value.',
        'data_completeness_warning':'Cyclicals require seven years of issuer earnings/FCF. Specialist sectors cannot be auto-valued without relevant issuer assets/AFFO/clinical economics.',
        'ranking_method':'Base upside divided by max(5%, loss to bear scenario), no likelihood, excludes NOT VALIDATED',
        'price_source':'Yahoo daily bars from existing Championship scanner; not executable or live bid/ask',
        'research_only':True,'orders_enabled':False,'orders_generated':0,
        'validated_buy_signal_count':0}


def fetch_update(root:Path,now:datetime,cfg:dict,*,offline:bool=False,session:Any=None)->dict:
    """Bounded incremental issuer-XBRL collection, one owner: discovery workflow.

    No proxy, authentication bypass or retries on 403/429. Never re-label source errors
    as absence of filings. Reports for all non-covered stocks remain NOT VALIDATED.
    """
    names,original=universe(root)
    cache=read(root/'reports/primary_series_cache_60.json',{}) or {}
    companies=cache.get('companies',{}) if isinstance(cache.get('companies'),dict) else {}
    out={'schema_version':CACHE_SCHEMA,'published_at_utc':now.isoformat(),
         'source':'SEC issuer-filed XBRL companyfacts; bounded incremental research',
         'original_200_unchanged':True,'companies':companies.copy(),'orders_enabled':False,
         'discovery_pipeline_preserved':True}
    if offline or session is None:
        out['update_status']='OFFLINE_NO_NETWORK';return out
    try:
        previous_retry=datetime.fromisoformat(str(cache.get('global_retry_after_utc') or '').replace('Z','+00:00'))
    except ValueError:previous_retry=None
    if previous_retry and previous_retry>now:
        out['update_status']='GLOBAL_PROVIDER_COOLDOWN_ACTIVE'
        out['global_retry_after_utc']=cache.get('global_retry_after_utc')
        return out
    ua=os.environ.get('SEC_USER_AGENT','').strip()
    if '@' not in ua:
        out['update_status']='SEC_CONTACT_REQUIRED';return out
    session.headers.update({'User-Agent':ua,'Accept':'application/json','Accept-Encoding':'gzip, deflate'})
    try:
        r=session.get('https://www.sec.gov/files/company_tickers_exchange.json',timeout=18,allow_redirects=False)
        if r.status_code!=200:raise RuntimeError(f'SEC_DIRECTORY_HTTP_{r.status_code}')
        payload=r.json();fields=[str(x).lower() for x in payload['fields']]
        indexes=[fields.index(x) for x in ('ticker','cik','exchange')]
        listed={str(x[indexes[0]]).upper():int(x[indexes[1]]) for x in payload['data']
                if str(x[indexes[2]]).upper() in {'NASDAQ','NYSE','NYSE AMERICAN','NYSE ARCA'}}
    except Exception as exc:
        out.update(update_status='DIRECTORY_UNAVAILABLE',reason=str(exc)[:180]);return out
    # Cycle all available stocks; discovery candidates are first and never modify original 200.
    failures=cache.get('temporary_failures',{}) if isinstance(cache.get('temporary_failures'),dict) else {}
    eligible=[x for x in names if x['ticker'] in listed]
    eligible.sort(key=lambda x:(0 if x['universe']=='DISCOVERY' else 1,x['ticker']))
    def needs_refresh(t):
        c=companies.get(t,{})
        f=failures.get(t,{})
        retry=dt(f.get('retry_after_utc'))
        if retry and retry>now.date():return False
        return not dated_recent(c.get('observed_utc'),now,cfg['sec_refresh_days'])
    selected=[x for x in eligible if needs_refresh(x['ticker'])][:cfg['max_new_sec_companies_per_discovery_run']]
    result=[]
    out['temporary_failures']=failures.copy()
    for name in selected:
        t=name['ticker'];cik=listed[t];url=f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json'
        try:
            r=session.get(url,timeout=18,allow_redirects=False)
            if r.status_code!=200:
                result.append({'ticker':t,'status':f'SEC_HTTP_{r.status_code}'})
                out['temporary_failures'][t]={'status':f'SEC_HTTP_{r.status_code}',
                   'retry_after_utc':(now+timedelta(days=1)).isoformat()}
                if r.status_code in (403,429):
                    out['global_retry_after_utc']=(now+timedelta(hours=6)).isoformat()
                    out['provider_limitation']='ACCESS_DENIED_OR_RATE_LIMITED'
                    break
                continue
            raw=r.json()
            row=primary_series(t,raw,now,cik)
            out['companies'][t]=row
            out['temporary_failures'].pop(t,None)
            result.append({'ticker':t,'status':'SEC_PRIMARY_SERIES_COLLECTED',
                'annual_fcf_periods':len(combine_periods(row))})
        except Exception as exc:
            result.append({'ticker':t,'status':'PRIMARY_FETCH_FAILURE','reason':type(exc).__name__})
            out['temporary_failures'][t]={'status':'PRIMARY_FETCH_FAILURE',
                'retry_after_utc':(now+timedelta(days=1)).isoformat()}
        time.sleep(.35) # no aggressive retry; SEC may enforce tighter access rules
    out['run_attempts']=result
    out['update_status']=('NO_REFRESH_DUE' if not selected else 'OK'
          if result and all(x['status']=='SEC_PRIMARY_SERIES_COLLECTED' for x in result) else 'PARTIAL_OR_UNAVAILABLE')
    out['available_company_records']=len(out['companies'])
    out['non_sec_listed_count']=len(names)-len(eligible)
    return out


def run(root:Path,mode:str,offline:bool=False,session:Any=None,now:datetime|None=None)->dict:
    now=now or datetime.now(timezone.utc)
    cfg=validate_cfg(read(root/'settings/championship_60.json',DEFAULT_ASSUMPTIONS))
    if mode=='evidence-update':
        out=fetch_update(root,now,cfg,offline=offline,session=session)
        write(root/'reports/primary_series_cache_60.json',out)
        return {'status':out['update_status'],'attempts':out.get('run_attempts',[]),
                'cache_companies':out.get('available_company_records',len(out['companies'])),
                'orders_enabled':False}
    if mode not in ('scan','weekly'):raise ValueError('Unknown mode')
    out=evaluate_all(root,now,cfg)
    target='valuation_60_weekly.json' if mode=='weekly' else 'valuation_60_latest.json'
    write(root/'reports'/target,out)
    write(root/'reports'/('valuation_60_weekly_summary.json' if mode=='weekly' else 'valuation_60_summary.json'),
      {k:v for k,v in out.items() if k!='companies'})
    return {'status':'RESEARCH_ONLY','reported':out['reported_count'],
            'validated':out['validated_inputs_count'],'not_validated':out['not_validated_count'],
            'orders_enabled':False}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--mode',required=True,choices=['evidence-update','scan','weekly'])
    p.add_argument('--root',type=Path,default=Path(__file__).resolve().parent)
    p.add_argument('--offline',action='store_true')
    a=p.parse_args()
    session=None
    if a.mode=='evidence-update' and not a.offline:
        import requests
        session=requests.Session()
    print(json.dumps(run(a.root,a.mode,a.offline,session=session),indent=2))

if __name__=='__main__':main()
