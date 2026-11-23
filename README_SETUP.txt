Championship 8.1 — timestamped SEC filing pointers + cohort audit (research only)

1. Extract files into your global-championship repository root, preserving tests/.
2. In repo root, run: python install_workflow_81.py
3. Run: python -m unittest discover -s tests -p 'test_catalyst_radar_81.py' -v
4. Commit and push catalyst_radar_81.py, tests/test_catalyst_radar_81.py,
   install_workflow_81.py, and .github/workflows/discovery.yml.
5. In GitHub Actions, run the Discovery workflow and inspect the 8.1 step and
   reports/catalyst_radar_81_latest.json artifact.

No trades. No automatic buys. SEC 8-K Atom feed is not a full global catalyst
source; its metadata is NOT independently verified filing content. No true
premarket prices, dilution validation, or proven missed-opportunity backtest.
This stage records timestamps and both winners and losers for future research.
SEC_USER_AGENT must contain a real contact email or SEC collection is skipped.

NOTE: This does not modify the fixed 200-stock list, valuation engine or
existing 8.0 retrospective audit. GitHub app currently lacks write access,
so uploading and committing must be performed by the repo owner.
