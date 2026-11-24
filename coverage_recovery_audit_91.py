"""Publish a per-company source/valuation audit, including every unresolved gap."""
import csv,json
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from evidence_recovery_91 import write

def run(root):
 report=json.loads((root/'reports/valuation_90_latest.json').read_text());rows=[r for r in report['companies'] if r['universe']=='ORIGINAL_200']
 names={r['ticker']:r['name'] for r in csv.DictReader((root/'watchlist.csv').open())}
 recovered=json.loads((root/'reports/primary_evidence_91.json').read_text());source={r['ticker']:r for r in recovered['company_assessments']}
 asx_path=root/'reports/asx_source_recovery_91.json';asx={r['ticker']:r for r in json.loads(asx_path.read_text()).get('companies',[])} if asx_path.exists() else {}
 docs_path=root/'reports/share_basis_recovery_91.json';docs={r['ticker']:r for r in json.loads(docs_path.read_text()).get('companies',[])} if docs_path.exists() else {}
 reviewed_path=root/'reports/issuer_primary_records_91.json';reviewed=json.loads(reviewed_path.read_text()).get('companies',{}) if reviewed_path.exists() else {}
 results=[]
 for r in rows:
  t=r['ticker'];flags=r['missing_inputs'];s=source.get(t,{})
  if r['scenarios']:
   status='SUPPORTED_PRIMARY_INPUTS_FORECASTS_HYPOTHETICAL';next_step='Continue dated filing and price refresh; future outcomes remain assumptions.'
  elif t.endswith('.AX') and t not in reviewed and not s.get('current_shares'):
   status='ISSUER_TABLES_NOT_YET_RECONCILED';next_step='Extract and verify the linked issuer annual-report financial tables, currency scale and listed-share basis. Filing index alone is not a valuation.'
  elif any('SPECIALIST' in f or 'SECTOR_' in f or 'NONPOSITIVE' in f or 'NEGATIVE_FREE_CASH' in f for f in flags):
   status='BUSINESS_SPECIFIC_ECONOMICS_REQUIRED';next_step='Obtain relevant project, AFFO/NAV, capital, or loss-making-business economics; do not substitute generic multiples.'
  elif any('SHARE_BASIS_CHANGE' in f for f in flags):
   status='CORPORATE_ACTION_RECONCILIATION_REQUIRED';next_step='Resolve issued shares, buybacks, dilution and splits from the actual issuer filings.'
  elif any('SHARE_COUNT' in f or 'LISTED_SHARE_BASIS' in f for f in flags):
   status='SHARE_CLASS_OR_RECEIPT_EVIDENCE_REQUIRED';next_step='Verify complete economic share classes and exact receipt/CDI terms; no market-cap inference.'
  else:status='PRIMARY_HISTORY_OR_CURRENCY_GAP';next_step='Resolve the listed missing fields from dated primary statements; preserve nulls until supported.'
  results.append({'ticker':t,'company':names[t],'assessment_status':status,'has_supported_valuation':r['scenarios'] is not None,
                  'missing_inputs':flags,'financial_source':r['reconciliation'].get('primary_source_url') or reviewed.get(t,{}).get('source_url'),
                  'structured_filing_attempt':s,'annual_report_sources':asx.get(t,{}).get('filings',[]),
                  'share_basis_document_attempt':docs.get(t),'remaining_work':next_step,'orders_enabled':False})
 counts=Counter(r['assessment_status'] for r in results);coverage=report['coverage_comparison']
 out={'schema_version':'9.1-full-200-evidence-audit-1','published_at_utc':datetime.now(timezone.utc).isoformat(),'companies':results,
      'assessed_count':len(results),'supported_before':coverage['original_200_valued_before'],'supported_after':coverage['original_200_valued_after'],
      'newly_supported_count':len(coverage['newly_valued']),'still_unsupported_count':sum(not r['has_supported_valuation'] for r in results),
      'status_counts':dict(counts),'orders_enabled':False,'orders_generated':0}
 assert len(results)==200 and len({r['ticker'] for r in results})==200
 write(root/'reports/coverage_recovery_91.json',out)
 lines=['# Full 200-stock evidence recovery audit','',f"Supported valuations: **{out['supported_before']} → {out['supported_after']}**. Newly supported: **{out['newly_supported_count']}**. Still unsupported: **{out['still_unsupported_count']}**.",'',
 'All companies are assessed. An assessment, downloaded filing or source index does not by itself establish a supported valuation. Financial inputs are issuer-reported; forecast assumptions remain hypothetical. No orders are generated.','',
 '| Ticker | Company | Result | Remaining input flags |','|---|---|---|---|']
 for r in results:
  flags='; '.join(r['missing_inputs']) or 'None'
  lines.append(f"| {r['ticker']} | {r['company']} | {r['assessment_status']} | {flags} |")
 (root/'reports/coverage_recovery_91.md').write_text('\n'.join(lines)+'\n')
 return out
if __name__=='__main__':
 r=run(Path(__file__).resolve().parent);print(json.dumps({k:v for k,v in r.items() if k!='companies'},indent=2))
