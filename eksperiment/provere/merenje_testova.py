"""Meri trajanje brzog paketa (bez testova u pregledacu), serijski i paralelno, na kopiji projekta."""
import os, re, shutil, subprocess, sys, tempfile, time

STRANA = sys.argv[1]
IZVOR = rf'C:\poredjenje-orkestrator\{STRANA}\projekat'
PY = rf'C:\poredjenje-orkestrator\{STRANA}\venv\Scripts\python.exe'
kopija = os.path.join(tempfile.mkdtemp(), 'p')
shutil.copytree(IZVOR, kopija, ignore=shutil.ignore_patterns('*.sqlite3', '*.sqlite3.*', '__pycache__', '.git', 'staticfiles'))
testovi = os.path.join(kopija, 'igra', 'tests')
brzi = [f'igra.tests.{f[:-3]}' for f in sorted(os.listdir(testovi))
        if f.startswith('test_') and f.endswith('.py') and 'playwright' not in open(os.path.join(testovi, f), encoding='utf-8').read()]
print('brzi moduli:', brzi)
for oznaka, dodatno in (('serijski', []), ('paralelno', ['--parallel', 'auto'])):
    t0 = time.time()
    r = subprocess.run([PY, 'manage.py', 'test', *brzi, *dodatno], cwd=kopija, capture_output=True, text=True, encoding='utf-8', errors='replace')
    izlaz = r.stdout + r.stderr
    print(oznaka, 'exit', r.returncode, '%.0f s' % (time.time() - t0), re.findall(r'^(Ran .*|OK.*|FAILED.*)$', izlaz, re.M)[:3])
    if r.returncode:
        print(izlaz[-800:])
