"""Run once from the repository root, after copying report_bridge.py and tests."""
from pathlib import Path

p=Path('.github/workflows/scan.yml')
s=p.read_text()
assert 'name: Championship intensive 200-stock scan' in s
assert 'permissions:\n  contents: read' in s
assert '      - name: Upload all 200 rows, dashboard and JSON' in s
s=s.replace('permissions:\n  contents: read','permissions:\n  contents: write',1)
s=s.replace("      - 'opportunity_engine.py'", "      - 'opportunity_engine.py'\n      - 'report_bridge.py'",1)
s=s.replace('      - name: Upload all 200 rows, dashboard and JSON', '''      - name: Build 200-stock report for ChatGPT
        run: python report_bridge.py
      - name: Publish machine-readable report to repository
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add reports/latest.json
          if ! git diff --cached --quiet; then
            git commit -m "data: refresh Championship 200-stock report [skip ci]"
            git pull --rebase origin main
            git push origin HEAD:main
          fi
      - name: Upload all 200 rows, dashboard and JSON''',1)
p.write_text(s)

p=Path('.github/workflows/valuation.yml')
s=p.read_text()
assert 'name: Championship 4.0 weekly valuation research' in s
assert 'permissions:\n  contents: read' in s
assert '      - name: Upload all 200 valuation research rows and data provenance' in s
s=s.replace('permissions:\n  contents: read','permissions:\n  contents: write',1)
s=s.replace('      - name: Upload all 200 valuation research rows and data provenance', '''      - name: Prepare weekly valuation report
        run: |
          mkdir -p reports
          cp data/valuation_200.json reports/valuation_latest.json
      - name: Publish weekly valuation report to repository
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add reports/valuation_latest.json
          if ! git diff --cached --quiet; then
            git commit -m "data: refresh Championship valuation [skip ci]"
            git pull --rebase origin main
            git push origin HEAD:main
          fi
      - name: Upload all 200 valuation research rows and data provenance''',1)
p.write_text(s)
print('Updated both workflows. Check git diff and tests before commit.')
