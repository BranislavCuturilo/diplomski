"""test_summary.py --brzo na kopiji pravog projekta strane: koliko traje i koliko testova pokrece."""
import os, shutil, subprocess, sys, tempfile, time

STRANA = sys.argv[1]
kopija = os.path.join(tempfile.mkdtemp(), 'p')
shutil.copytree(rf'C:\poredjenje-orkestrator\{STRANA}\projekat', kopija,
                ignore=shutil.ignore_patterns('*.sqlite3', '*.sqlite3.*', '__pycache__', '.git', 'staticfiles'))
t0 = time.time()
r = subprocess.run([rf'C:\poredjenje-orkestrator\{STRANA}\venv\Scripts\python.exe', r'C:\posao\diplomski\tools\test_summary.py', '--brzo'],
                   cwd=kopija, capture_output=True, text=True, encoding='utf-8', errors='replace')
print(STRANA, '%.0f s' % (time.time() - t0), r.returncode)
print(r.stdout[-600:])
