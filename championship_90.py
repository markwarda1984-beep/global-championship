"""Evidence-gated global research overlay. Never routes orders.

Legacy 6.0 files and validation semantics remain intact. All forecasts and
valuation parameters are explicit assumptions, never invented financial facts.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

PRIORITIES = {'HPE': {'currency': 'USD', 'threshold': 40.0, 'operator': '<'},
              'SKS.AX': {'currency': 'AUD', 'threshold': 5.0, 'operator': '<='},
              'DUG.AX': {'currency': 'AUD', 'threshold': 1.5, 'operator': '<='}}

def number(x):
    return float(x) if isinstance(x, (float, int)) and not isinstance(x, bool) and math.isfinite(x) else None

def positive(x):
    n = number(x)
    return n if n is not None and n > 0 else None

def read(p, default=None):
    return json.loads(p.read_text()) if p.exists() else default

def write(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, allow_nan=False) + '\n')

def recent(value, now, days):
    try:
        d = datetime.fromisoformat(str(value).replace('Z', '+00:00')).date()
        return 0 <= (now.date() - d).days <= days
    except (ValueError, TypeError):
        return False

def trading_lows(lows, closes):
    """Sessions, including latest session. Previous five excludes latest.
    Close-only fallbacks are separately labelled, never called trading lows.
    """
    out = {}
    valid = bool(lows) and len(lows) == len(closes) and all(positive(x) for x in lows)
    for n, key in ((5, '5d'), (30, '30d'), (252, '52w')):
        out['low_' + key] = min(lows[-n:]) if valid and len(lows) >= n else None
        out['close_low_' + key] = min(closes[-n:]) if len(closes) >= n and all(positive(x) for x in closes[-n:]) else None
    out['previous_5d_low'] = min(lows[-6:-1]) if valid and len(lows) >= 6 else None
    out['low_basis'] = 'UNADJUSTED_DAILY_INTRADAY_LOW' if valid else 'INTRADAY_LOW_UNAVAILABLE'
    out['available_sessions'] = len(closes)
    return out

def evidence_record(record, now, max_age=550):
    """Require a dated document and exact numeric field map hashed as stored.
    Ingestion is a reviewed adapter boundary, not a claim to audit issuer facts.
    """
    if not isinstance(record, dict):
        return False
    url = urlparse(str(record.get('source_url', '')))
    facts = record.get('facts')
    return bool(url.scheme == 'https' and url.hostname and record.get('issuer')
                and record.get('accession_or_document_id') and facts
                and recent(record.get('as_of'), now, max_age)
                and recent(record.get('published_at'), now, max_age)
                and record.get('review_status') == 'PRIMARY_DOCUMENT_FIELDS_RECONCILED'
                and record.get('facts_sha256') == hashlib.sha256(json.dumps(facts, sort_keys=True).encode()).hexdigest())

def reconcile(primary, quote_currency, basis, fx, now, foreign=False):
    """Convert aggregate statement values to quote currency per listed share.
    ADR ratio means ordinary shares PER listed receipt; never infer from price.
    """
    p = copy.deepcopy(primary)
    # Keep latest shares independent when caller objects share references.
    if p.get('latest_share_count'): p['latest_share_count'] = dict(p['latest_share_count'])
    audit = {'status': 'BLOCKED', 'flags': [], 'financial_currency': None,
             'quote_currency': quote_currency, 'ordinary_shares_per_receipt': None,
             'primary_source_url': primary.get('source_url'), 'primary_evidence_hash': primary.get('evidence_hash_sha256')}
    units = {r.get('unit') for k, rows in p.get('annual_facts', {}).items() if k != 'shares' for r in rows}
    if len(units) != 1 or not next(iter(units), None):
        audit['flags'].append('MIXED_OR_MISSING_STATEMENT_CURRENCY')
        return None, audit
    currency = next(iter(units)); audit['financial_currency'] = currency
    ratio = 1.0
    if foreign or basis:
        if not evidence_record(basis, now):
            audit['flags'].append('DATED_PRIMARY_LISTED_SHARE_BASIS_REQUIRED')
            return None, audit
        f = basis['facts']; ratio = positive(f.get('ordinary_shares_per_receipt'))
        if not ratio or f.get('ticker') != p.get('ticker') or f.get('quote_currency') != quote_currency:
            audit['flags'].append('LISTED_SHARE_BASIS_MISMATCH')
            return None, audit
        primary_shares = positive((p.get('latest_share_count') or {}).get('value'))
        check = positive(f.get('ordinary_shares_outstanding'))
        if not check or not primary_shares or abs(check / primary_shares - 1) > .05:
            audit['flags'].append('PRIMARY_SHARE_COUNT_DISCREPANCY')
            return None, audit
    if basis and evidence_record(basis, now):
        for action in basis['facts'].get('splits', []):
            factor = positive(action.get('new_per_old'))
            effective = action.get('effective_date')
            if not factor or not recent(effective, now, 550):
                audit['flags'].append('INVALID_OR_UNDATED_CORPORATE_ACTION')
                return None, audit
            for record in p.get('annual_facts', {}).get('shares', []):
                if record['end'] < effective: record['value'] *= factor
            latest = p.get('latest_share_count')
            if latest and latest['end'] < effective:
                p['latest_share_count'] = {**latest, 'value': latest['value'] * factor}
    rate = 1.0
    if currency != quote_currency:
        if not isinstance(fx, dict) or fx.get('from') != currency or fx.get('to') != quote_currency or not positive(fx.get('rate')) or not recent(fx.get('as_of'), now, 7) or not str(fx.get('source_url', '')).startswith('https://'):
            audit['flags'].append('DATED_DIRECTIONAL_FX_REQUIRED')
            return None, audit
        rate = fx['rate']
    if p.get('latest_share_count'):
        p['latest_share_count'] = dict(p['latest_share_count'])
    for k, rows in p.get('annual_facts', {}).items():
        for r in rows:
            r['value'] = r['value'] / ratio if k == 'shares' else r['value'] * rate
            if k != 'shares': r['unit'] = quote_currency
    if p.get('latest_share_count'):
        p['latest_share_count']['value'] /= ratio
    audit.update(status='RECONCILED', ordinary_shares_per_receipt=ratio, fx_rate=rate,
                 fx_source=fx if currency != quote_currency else None,
                 share_basis_source=basis, share_count_basis='LISTED_RECEIPTS' if ratio != 1 else 'ORDINARY_SHARES')
    return p, audit

def specialist(method, record, now):
    """Per-share sector models. Every required input must be sourced, including
    zero debt/cash; no median multiples substituted for absent economics.
    """
    requirements = {
        'PROPERTY_ASSET_NAV_OR_AFFO': ('affo', 'shares'),
        'HOLDING_COMPANY_ASSET_NAV': ('appraised_assets', 'total_liabilities', 'shares'),
        'SPECIALIST_FINANCIAL_CAPITAL_STRUCTURE': ('tangible_common_equity', 'normalized_roe', 'shares'),
        'PROJECT_RISK_ADJUSTED_NAV': ('risk_adjusted_project_npv', 'cash', 'debt', 'remaining_funding', 'shares')}
    required = requirements.get(method)
    if not required:
        return None, [], None
    if not evidence_record(record, now):
        return None, ['SECTOR_PRIMARY_DOCUMENT_ADAPTER_REQUIRED'], {'required_fields': list(required)}
    f = record['facts']; missing = [k for k in required if number(f.get(k)) is None]
    if missing or not positive(f.get('shares')):
        return None, ['SECTOR_INPUT_MISSING_' + k.upper() for k in (missing or ['shares'])], None
    if any(f[k] < 0 for k in required):
        return None, ['NEGATIVE_SPECIALIST_INPUT_REQUIRES_REVIEW'], None
    sh = f['shares']
    if method == 'PROPERTY_ASSET_NAV_OR_AFFO':
        if not positive(f['affo']): return None, ['POSITIVE_RECURRING_AFFO_REQUIRED'], None
        # AFFO attributable to common equity; debt is already serviced.
        vals = {k: f['affo'] / sh / y for k, y in [('bear', .10), ('base', .08), ('bull', .065)]}
        assumption = {'affo_equity_yields': {'bear': .10, 'base': .08, 'bull': .065}}
    elif method == 'HOLDING_COMPANY_ASSET_NAV':
        vals = {k: (f['appraised_assets'] * (1-h) - f['total_liabilities']) / sh for k, h in [('bear', .30), ('base', .15), ('bull', 0)]}
        assumption = {'asset_haircuts': {'bear': .30, 'base': .15, 'bull': 0}}
    elif method == 'SPECIALIST_FINANCIAL_CAPITAL_STRUCTURE':
        if f['normalized_roe'] > .5: return None, ['ROE_MUST_BE_DECIMAL_AND_NORMALIZED'], None
        vals = {k: f['tangible_common_equity'] / sh * max(0, (f['normalized_roe']-.02)/(r-.02)) for k, r in [('bear', .18), ('base', .14), ('bull', .11)]}
        assumption = {'cost_of_equity': {'bear': .18, 'base': .14, 'bull': .11}, 'terminal_growth': .02}
    else:
        vals = {k: (f['risk_adjusted_project_npv']*scale + f['cash'] - f['debt'] - f['remaining_funding']) / sh for k, scale in [('bear', .5), ('base', 1), ('bull', 1.25)]}
        assumption = {'risk_adjusted_npv_sensitivity': {'bear': .5, 'base': 1, 'bull': 1.25}}
    if not all(positive(v) for v in vals.values()): return None, ['NONPOSITIVE_SECTOR_EQUITY_VALUE'], assumption
    return vals, [], {'forecast_assumptions': assumption, 'source': record}

def priority(ticker, q, now):
    rule = PRIORITIES.get(ticker)
    if not rule: return None
    price = positive(q.get('price')); valid = bool(price and q.get('currency') == rule['currency'] and recent(q.get('quote_date'), now, 7))
    hit = (price < rule['threshold'] if rule['operator'] == '<' else price <= rule['threshold']) if valid else None
    low = positive(q.get('previous_5d_low'))
    return {**rule, 'threshold_met': hit, 'below_previous_5d_low': price < low if valid and low else None,
            'rule_source': 'USER_CONFIRMED_2026_11_24', 'purpose': 'PRIORITY_RESEARCH_ENTRY_REVIEW', 'orders_enabled': False}

def build(root, mode='scan', now=None):
    from championship_60 import universe, latest_quote, method, scenario_values, combine_periods, ADR_OR_OVERSEAS_SHARE_BASIS, validate_cfg, DEFAULT_ASSUMPTIONS, evaluate_all
    now = now or datetime.now(timezone.utc)
    names, original = universe(root)
    # Priority discovery membership never changes the fixed 200.
    for t in PRIORITIES:
        if not any(x['ticker'] == t for x in names):
            names.append({'ticker': t, 'company': t, 'category': 'Industrial services' if t == 'SKS.AX' else 'AI infrastructure', 'universe': 'DISCOVERY'})
    quotes = latest_quote(root, original)
    extra = read(root/'reports/priority_quotes_90.json', {}) or {}
    
    for ticker, quote in extra.get('quotes', {}).items():
        if quote.get('quote_date', '') >= quotes.get(ticker, {}).get('quote_date', ''):
            quotes[ticker] = quote
    registry = read(root/'reports/discovery_watchlist.json', {}) or {}
    for ticker, candidate in registry.get('candidates', {}).items():
        if ticker not in original and ticker not in extra.get('quotes', {}):
            quotes[ticker] = candidate.get('last_quote') or {}
    legacy_name = 'valuation_60_weekly.json' if mode == 'weekly' else 'valuation_60_latest.json'
    legacy = read(root/'reports'/legacy_name, {}) or {}
    old = {r['ticker']: r for r in legacy.get('companies', [])}
    cache = (read(root/'reports/primary_series_cache_60.json', {}) or {}).get('companies', {})
    adapters = read(root/'settings/primary_adapters_90.json', {}) or {}
    cfg = validate_cfg(read(root/'settings/championship_60.json', DEFAULT_ASSUMPTIONS))
    # Recompute legacy eligibility against identical evidence/time, avoiding
    # false coverage gains from comparing an older weekly snapshot.
    comparable = {r['ticker']: r for r in evaluate_all(root, now, cfg)['companies']}
    rows = []
    for name in names:
        t = name['ticker']; q = quotes.get(t, {}); src = cache.get(t, {}); prior = old.get(t, {})
        sector = method(t, name['category']); price = positive(q.get('price'))
        vals = None; assumptions = None; flags = []; audit = {'status': 'NO_PRIMARY_SERIES'}
        adapter = adapters.get(t, {})
        if src.get('status') == 'OFFICIAL_SEC_COMPANYFACTS_RETRIEVED' and recent(src.get('observed_utc'), now, cfg['sec_refresh_days']+4):
            normalized, audit = reconcile(src, q.get('currency'), adapter.get('share_basis'), adapter.get('fx'), now,
                                          t in ADR_OR_OVERSEAS_SHARE_BASIS or name['category'] == 'International')
            if normalized:
                vals, assumptions, flags = scenario_values(sector, combine_periods(normalized), normalized, cfg, now)
            else: flags += audit['flags']
        else: flags.append('CURRENT_PRIMARY_STATEMENT_SERIES_REQUIRED')
        if vals is None:
            sector_vals, sector_flags, sector_assumptions = specialist(sector, adapter.get('sector'), now)
            if sector_vals:
                record = adapter['sector']; facts = record['facts']
                # Adapter numbers explicitly use listed-share and quote-currency basis.
                if facts.get('ticker') == t and facts.get('currency') == q.get('currency') and facts.get('share_basis') == 'LISTED_SHARES':
                    vals, flags, assumptions = sector_vals, [], sector_assumptions
                    audit = {'status': 'RECONCILED_SECTOR_DOCUMENT', 'source': record}
                else: flags.append('SECTOR_CURRENCY_OR_LISTED_SHARE_BASIS_MISMATCH')
            elif sector_flags: flags += sector_flags
        if not price or not recent(q.get('quote_date'), now, 7):
            flags.append('CURRENT_DATED_QUOTE_REQUIRED'); vals = None
        if flags: vals = None
        upside = (vals['base']/price-1)*100 if vals and price else None
        low5 = positive(q.get('low_5d')); recovery = (price/low5-1)*100 if price and low5 else None
        previous = positive(q.get('previous_5d_low'))
        before_recovery = bool(recovery is not None and recovery <= 3)
        eligible = bool(vals and upside is not None and upside >= 25 and before_recovery)
        row = {'ticker': t, 'universe': name['universe'], 'sector_method': sector,
               'assessment_status': 'PRIMARY_INPUTS_RECONCILED_FORECASTS_HYPOTHETICAL' if vals else 'MISSING_EVIDENCE',
               'price': price, 'currency': q.get('currency'), 'quote_date': q.get('quote_date'),
               'scenarios': vals, 'base_upside_pct': round(upside, 2) if upside is not None else None,
               'preferred_25_50pct_upside': bool(upside is not None and 25 <= upside <= 50),
               'pre_recovery_candidate': eligible, 'recovery_from_5d_low_pct': recovery,
               'new_5d_low': price < previous if price and previous else None,
               'trading_lows': {k: q.get(k) for k in ('low_5d','low_30d','trading_low_52w','previous_5d_low','low_basis','available_sessions')},
               'priority_entry': priority(t, q, now), 'reconciliation': audit,
               'missing_inputs': sorted(set(flags)), 'assumptions': assumptions,
               'legacy_validation_status': prior.get('validation_status'),
               'research_only': True, 'orders_enabled': False, 'buy_signal': False}
        rows.append(row)
    fixed = [r for r in rows if r['universe'] == 'ORIGINAL_200']
    assert len(fixed) == 200 and len({r['ticker'] for r in rows}) == len(rows)
    before = sum(comparable.get(r['ticker'], {}).get('validation_status') == 'PRIMARY_INPUTS_VALIDATED_FORECASTS_HYPOTHETICAL' for r in fixed)
    after = sum(r['scenarios'] is not None for r in fixed)
    ranked = sorted([r for r in rows if r['pre_recovery_candidate']], key=lambda r: (not r['preferred_25_50pct_upside'], r['recovery_from_5d_low_pct'], -r['base_upside_pct'], r['ticker']))
    coverage = {'original_200_assessed_before': sum(r['ticker'] in old for r in fixed), 'original_200_assessed_after': 200,
                'original_200_valued_before': before, 'original_200_valued_after': after, 'change': after-before,
                'newly_valued': [r['ticker'] for r in fixed if r['scenarios'] and comparable.get(r['ticker'], {}).get('validation_status') != 'PRIMARY_INPUTS_VALIDATED_FORECASTS_HYPOTHETICAL'],
                'lost_valuation': [r['ticker'] for r in fixed if not r['scenarios'] and comparable.get(r['ticker'], {}).get('validation_status') == 'PRIMARY_INPUTS_VALIDATED_FORECASTS_HYPOTHETICAL'],
                'comparison_basis': 'SAME_RUN_LEGACY_60_VS_90_FIXED_200', 'legacy_source_published_at': legacy.get('published_at_utc'), 'legacy_recomputed_at': now.isoformat()}
    out = {'schema_version': '9.0-research-1', 'published_at_utc': now.isoformat(), 'mode': mode,
           'original_watchlist_count': 200, 'reported_count': len(rows), 'companies': rows,
           'ranked_pre_recovery_top10': ranked[:10], 'coverage_comparison': coverage,
           'ranking_assumptions': {'minimum_base_upside_pct':25, 'preferred_maximum_upside_pct':50, 'maximum_recovery_from_5d_low_pct':3},
           'scope_note': 'All 200 assessed; missing issuer statements, ADR terms, FX or sector facts remain null. No guaranteed returns. Daily bars are not live quotes.',
           'orders_enabled':False, 'orders_generated':0}
    suffix = 'weekly' if mode == 'weekly' else 'latest'
    write(root/f'reports/valuation_90_{suffix}.json', out)
    write(root/f'reports/coverage_90_{suffix}.json', coverage)
    if mode == 'scan':
        path = root/'reports/latest.json'; bridge = read(path, {})
        if bridge and 'stocks' in bridge:
            mapping = {r['ticker']:r for r in rows}
            for r in bridge['stocks']:
                x = mapping.get(r['ticker'], {})
                r['championship_90'] = {k:x.get(k) for k in ('assessment_status','trading_lows','priority_entry','base_upside_pct','pre_recovery_candidate')}
            bridge['championship_90_report'] = 'reports/valuation_90_latest.json'
            write(path, bridge)
    return out

def collect_priority_quotes(root):
    from scan import fetch_batch, currency_for
    now = datetime.now(timezone.utc); quotes = {}
    raw = fetch_batch(list(PRIORITIES))
    for t, q in raw.items():
        quotes[t] = {'price':q['closes'][-1], 'currency':q.get('currency') or currency_for(t), 'quote_date':q['quote_date'], **trading_lows(q.get('lows', []), q['closes'])}
    out = {'published_at_utc':now.isoformat(), 'quotes':quotes, 'missing_tickers':sorted(set(PRIORITIES)-set(quotes)), 'orders_enabled':False}
    write(root/'reports/priority_quotes_90.json', out)
    return out

def main():
    p=argparse.ArgumentParser(); p.add_argument('--mode', choices=['scan','weekly','quotes'], default='scan'); p.add_argument('--root', type=Path, default=Path(__file__).resolve().parent)
    a=p.parse_args()
    out=collect_priority_quotes(a.root) if a.mode == 'quotes' else build(a.root,a.mode)
    print(json.dumps(out.get('coverage_comparison', {'mode':a.mode, 'orders_enabled':False}), indent=2))
if __name__ == '__main__': main()
