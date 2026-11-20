Championship 4.0 report bridge — deployment bundle

STATUS: Code prepared and locally tested; NOT deployed to GitHub.

In GitHub Codespaces or a local clone of markwarda1984-beep/global-championship:
1. Copy report_bridge.py and install_bridge.py into repository root.
2. Copy tests/test_report_bridge.py into repository tests/.
3. Run: python -m unittest discover -s tests -v
4. Run: python install_bridge.py
5. Inspect: git diff
6. Run: python -m unittest discover -s tests -v
7. Commit and push all 4 files and the two modified workflow YAML files.
8. GitHub Settings > Actions > General > Workflow permissions: allow Read and write permissions, if available. Branch protection may block action pushes; use a dedicated reports branch if necessary.
9. Run weekly valuation workflow, then 200-stock scan from Actions. Confirm reports/valuation_latest.json and reports/latest.json are committed to main.
10. Verify ChatGPT can fetch reports/latest.json via GitHub connector.

IMPORTANT: No trades, no brokerage access. Closest to buy ranks ABSOLUTE distance to unverified price levels; it is NOT a buy ranking. Missing evidence => Buy Readiness NOT SCORED. Quotes are historical daily bars. Reports contain no personal credentials.
