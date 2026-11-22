CHAMPIONSHIP 7.0 — EXPERIMENTAL PREVIEW

This is NOT a production valuation replacement. It reads the existing 6.0 report and produces parallel research scenarios for eligible stable companies. All other companies remain explicitly NOT_RECALCULATED. No new primary data is fetched; source freshness must be reviewed. The model uses recent cash flow, bounded observed growth, volatility-sensitive assumed rates, a ten-year fade model and observed dilution stress. Historical multiples and true point-in-time backtesting are not implemented. Cyclicals and specialist sectors retain 6.0 only. Rates are heuristic, not independently calibrated. No orders or buy approvals.

INSTALL
1. Extract ZIP. In your existing local global-championship checkout, copy revision_70.py, report_70.py and test_revision_70.py to repository root. Alternatively run python install_70.py PATH_TO_REPOSITORY from extracted files.
2. Copy .github/workflows/revision70.yml into the existing repository .github/workflows folder. Do not replace other files or workflows.
3. From repository root run:
   python -m unittest -v test_revision_70
   python report_70.py
4. Inspect reports/valuation_70_preview.json. Check source_published_at, coverage, company assumptions and scenario changes. No price should be treated as validated entry.
5. Commit only the three Python files and new workflow. Push. In GitHub Actions select Championship 7.0 preview and Run workflow. Download its artifact after success. Scheduled runs read the existing committed 6.0 report; do not guarantee that it has refreshed. The current ChatGPT review automation is unchanged and does not automatically consume this artifact.
6. Roll back by removing these four newly added files. Existing 6.0 files remain untouched.

Local testing: four synthetic unit tests passed. Real repository report compatibility and workflow execution have not been verified. Production adoption requires live report verification, full-sector models, evidence-based calibration and historical walk-forward tests. Do not use the preview to authorize trades.
