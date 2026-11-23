CHAMPIONSHIP 8.0 — SAFE FIRST-STAGE EXPLOSIVE MOVE AUDIT

This is a RETROSPECTIVE research-only component, not a real-time 100% winner detector.
It flags historical daily moves >=50% or relative volume >=3x within reports/latest.csv,
if those column names exist. It explicitly marks every flagged candidate UNDETERMINED
until first-party filings, dilution, liquidity, pre-move timestamps and losing controls
are independently verified. No orders, signals or trades.

INSTALL
1. Copy explosive_move_audit_80.py to the repository root.
2. Copy tests/test_explosive_move_audit_80.py to the existing tests directory.
3. Add the following TWO workflow steps to .github/workflows/discovery.yml
   immediately after the existing 'Run entire offline test suite' step OR after
   the discovery run; ensure the audit step runs after latest.csv is available:

      - name: Audit historical explosive moves (research only)
        run: python explosive_move_audit_80.py
      - name: Verify audit cannot produce trades
        run: |
          python - <<'PY'
          import json
          x=json.load(open('reports/explosive_move_audit_80.json'))
          assert x['orders_enabled'] is False
          assert x['buy_signals_generated'] == 0
          assert not x['live_premarket_detector']
          PY

4. In the workflow's existing 'git add' section, add:
      git add reports/explosive_move_audit_80.json
5. Upload changes using GitSync -> Upload Changes (NOT overwrite).
6. Check Actions success and verify reports/explosive_move_audit_80.json.

LIMITATIONS: This does not yet ingest official filings or executable premarket quotes.
It does NOT claim to detect moves before they happen. Existing 200 stock list unchanged.
