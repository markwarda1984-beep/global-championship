"""Install a parallel research overlay into an existing 6.0 checkout."""
from pathlib import Path
import shutil
import sys

def main():
    root=Path(sys.argv[1] if len(sys.argv)>1 else '.').resolve()
    src=Path(__file__).resolve().parent
    engine=root/'championship_60.py'
    if not engine.exists():raise SystemExit('Run against existing Championship 6.0 repository')
    for name in ('revision_70.py','report_70.py','test_revision_70.py'):
        dest=root/name
        if src/name != dest:shutil.copy2(src/name,dest)
    print('Overlay installed. Existing engine and workflows unchanged.')
if __name__=='__main__':main()
