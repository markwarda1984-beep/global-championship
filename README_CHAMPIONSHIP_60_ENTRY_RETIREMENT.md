# Championship 6.0 active-entry retirement patch

The original fixed `watchlist.csv` (200 rows), `scan.py`, 5.2 discovery, schedules, 6.0 primary engine and JSON paths are preserved. This patch fixes conflicting active research reports.

- **Historical US$33.3938 NVDA was an UNVERIFIED Yahoo-derived 4.0 calculation, not a real intrinsic buy value**. `reports/latest.json` `provisional_entry` and `pct_above_entry` are now ALWAYS null, including NVDA. Existing columns remain for backward compatibility.
- `reports/latest.json` adds verified 6.0 `selected_entry_60`, `margin_of_safety_entries_60`, 6.0 valuation and missing-evidence fields. All are NULL when the primary evidence gate fails.
- `reports/valuation_latest.json` and newly generated `data/valuation_200.csv/.json` keep unofficial scenario diagnostics but DO NOT compute `model_watch_entry`, `model_deep_entry`, or `pct_to_watch_entry`. These keys remain NULL.
- `reports/valuation_top10_latest.json` and `_weekly.json` ONLY show evidence-qualified Championship 6.0 research. If no full validation exists, Top 10 is empty.
- `reports/offset_comparison*.json` retain both mortgage-rate benchmarks, fees, FX and Australian tax and do NOT simulate an unverified company target.
- Technical history in `data/latest.json` remains historical context only; CSV manually labelled buy levels cannot bypass 6.0. The 200-company opportunity triage no longer publishes manual provisional buy prices.
- `reports/valuation_60*.json` remain the authoritative full 200 plus discovery evidence reports.
- 6 daily scanner runs, 6 daily 5.2 discovery runs and existing weekly valuation schedule remain unchanged.
- All reports research only, no trades and no orders. Six-attempt safe GitHub publication remains unchanged.

## Install
Extract into the EXISTING `Documents/global-championship` working copy, keeping `.git`, then GitSync → three dots → **Upload Changes** (not overwrite). Running the workflows manually is optional because the changed workflows trigger push events.

## Verify
Run the scan, discovery, and weekly valuation workflows; all tests must pass and JSON published to main. Check `reports/latest.json` NVDA: `provisional_entry=null`, and `reports/valuation_latest.json` NVDA `model_watch_entry=null`. Check `reports/valuation_60_latest.json` NVDA still `NOT VALIDATED` until filings pass.

Do not place trades.
