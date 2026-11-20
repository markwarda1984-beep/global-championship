"""Publish a small, transparent, read-only 200-stock research snapshot.

No broker APIs, trade decisions, or claims of validated fair value.
"""
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def numeric(value):
    try:
        n = float(value)
        return n if math.isfinite(n) and n > 0 else None
    except (ValueError, TypeError, OverflowError):
        return None

def build(scan, valuation=None):
    stocks = scan['stocks']
    symbols = [str(x['ticker']).upper() for x in stocks]
    if len(symbols) != 200 or len(set(symbols)) != 200:
        raise ValueError('Scan must contain exactly 200 unique stocks')
    val_rows = (valuation or {}).get('stocks', [])
    val_by = {x['ticker'].upper(): x for x in val_rows}
    val_date = (valuation or {}).get('summary', {}).get('timestamp_utc')
    out = []
    for row in stocks:
        ticker = row['ticker'].upper()
        v = val_by.get(ticker, {})
        price = numeric(row.get('price'))
        validated = numeric(row.get('validated_buy_price')) if row.get('buy_validation') == 'VALIDATED' else None
        manual = numeric(row.get('manual_provisional_buy_price'))
        model = numeric(v.get('model_watch_entry')) if str(v.get('model_status', '')).startswith('INDICATIVE') else None
        historical = numeric(row.get('technical_watch_zone'))
        if validated:
            entry, category = validated, 'MANUALLY VALIDATED — VERIFY EVIDENCE'
        elif model and v.get('price_currency') == row.get('currency'):
            entry, category = model, 'UNVERIFIED FUNDAMENTAL MODEL'
        elif manual:
            entry, category = manual, 'MANUAL PROVISIONAL — UNVERIFIED'
        elif historical:
            entry, category = historical, 'STATISTICAL HISTORY — NOT FAIR VALUE'
        else:
            entry, category = None, 'NO ENTRY LEVEL'
        distance = round((price / entry - 1) * 100, 2) if price and entry else None
        out.append({
            'ticker': ticker, 'company': row.get('name'), 'currency': row.get('currency'),
            'last_daily_close': price, 'quote_date': row.get('quote_date'),
            'provisional_entry': entry, 'entry_basis': category,
            'pct_above_entry': distance, 'absolute_distance_pct': abs(distance) if distance is not None else None,
            'data_status': row.get('data_status'), 'model_status': v.get('model_status') or 'NO WEEKLY MODEL',
            'valuation_as_of_utc': val_date, 'buy_readiness_pct': None,
            'buy_readiness_status': 'NOT SCORED — independent evidence required',
            'decision': 'RESEARCH ONLY — NOT AN ORDER',
        })
    closest = sorted((x for x in out if x['absolute_distance_pct'] is not None),
                     key=lambda x: (x['absolute_distance_pct'], x['ticker']))[:10]
    return {
        'schema_version': '4.0-report-bridge-1',
        'published_at_utc': datetime.now(timezone.utc).isoformat(),
        'scan_utc': scan.get('scan_utc'), 'scan_sydney': scan.get('scan_sydney'),
        'price_source': scan.get('data_quality'), 'valuation_as_of_utc': val_date,
        'valuation_source': (valuation or {}).get('summary', {}).get('source'),
        'universe_count': 200, 'price_available_count': sum(x['last_daily_close'] is not None for x in out),
        'model_available_count': sum(x['model_status'].startswith('INDICATIVE') for x in out),
        'valuation_rows_count': len(val_rows), 'closest_to_buy_top_10': closest,
        'stocks': out, 'bitcoin': scan.get('bitcoin', {}),
        'research_only': True, 'orders_enabled': False,
        'warning': 'Daily closes are not executable. Statistical zones are not fair value. Model entries are unverified. Closest does not mean best or buy-ready.',
    }

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--scan', default='data/latest.json')
    parser.add_argument('--valuation', default='reports/valuation_latest.json')
    parser.add_argument('--output', default='reports/latest.json')
    args = parser.parse_args()
    scan = json.loads((ROOT / args.scan).read_text(encoding='utf-8'))
    path = ROOT / args.valuation
    valuation = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None
    result = build(scan, valuation)
    dest = ROOT / args.output
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f"Published research snapshot: {result['price_available_count']}/200 daily bars; {result['model_available_count']} indicative models; no trades")

if __name__ == '__main__':
    main()
