"""Idempotently insert 8.1 audit into existing discovery workflow without replacing it."""
from pathlib import Path
p=Path('.github/workflows/discovery.yml')
if not p.exists():
    raise SystemExit('Run from the repository root: .github/workflows/discovery.yml not found')
s=p.read_text()
anchor='      - name: Verify primary-source provenance and prepare underfollowed research queue'
step=('      - name: Run Championship 8.1 timestamped catalyst research\n'
      '        env:\n'
      '          SEC_USER_AGENT: ${{ secrets.SEC_USER_AGENT }}\n'
      '        run: python catalyst_radar_81.py\n')
if 'run: python catalyst_radar_81.py' not in s:
    if anchor not in s: raise SystemExit('Expected workflow anchor missing; no changes made')
    s=s.replace(anchor,step+anchor,1)
# Ensure code changes trigger CI, without affecting existing triggers.
trigger="      - '.github/workflows/discovery.yml'"
if "      - 'catalyst_radar_81.py'" not in s:
    if trigger not in s: raise SystemExit('Workflow push path anchor missing; no changes made')
    s=s.replace(trigger,"      - 'catalyst_radar_81.py'\n      - 'tests/test_catalyst_radar_81.py'\n"+trigger,1)
# Include new report in the artifact; don't alter existing publishing code.
artifact='            reports/issuer_guidance_60.json'
if '            reports/catalyst_radar_81_latest.json' not in s:
    if artifact not in s: raise SystemExit('Artifact anchor missing; no changes made')
    s=s.replace(artifact,artifact+'\n            reports/catalyst_radar_81_latest.json',1)
p.write_text(s)
print('Workflow updated; run tests and commit. Existing workflow steps preserved.')
