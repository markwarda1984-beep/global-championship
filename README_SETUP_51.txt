CHAMPIONSHIP 5.1 INTELLIGENCE LAYER — OVERLAY FOR EXISTING CHAMPIONSHIP 5.2

This does NOT downgrade or replace Championship 5.2.

1. Extract this ZIP.
2. Copy its CONTENTS into your existing Documents/global-championship GitSync folder.
   Preserve .git, watchlist.csv, discovery_engine.py, scan.py, valuation_engine.py,
   report_bridge.py, SEC_USER_AGENT and all existing workflow schedules.
   Allow replacement of ONLY the three .github/workflows/*.yml files.
3. In GitSync choose THREE DOTS beside Sync Changes -> Upload Changes.
   DO NOT use Upload + Overwrite.
4. GitHub Actions should run the discovery, scanner, and valuation workflows
   automatically because these files were changed. All workflows remain no-trade.
5. Once uploaded, ask ChatGPT to verify the GitHub action jobs and these JSON files:
   reports/changes_latest.json
   reports/research_queue_latest.json
   reports/valuation_top10_latest.json
   reports/offset_comparison_latest.json
   reports/decision_journal.json
   reports/intelligence_latest.json
   reports/valuation_top10_weekly.json
   reports/offset_comparison_weekly.json

Optional local test: python -m unittest discover -s tests -v

The 5.1 intelligence layer is source-labelled research, never buy authorisation.
Live GitHub deployment has not occurred until your GitSync push succeeds.
