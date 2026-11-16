# -*- coding: utf-8 -*-
"""Pokrece testove i vraca SAMO sazetak + pale testove (ne ceo izlaz).

U folderu sa manage.py koristi Django test runner, osim ako je pytest instaliran i podesen
(pytest.ini, conftest.py ili [tool.pytest] u pyproject.toml). Inace pytest.

    python tools/test_summary.py [--brzo] [putanja ili -k izraz ...]

--brzo: bez modula koji koriste pregledac (u njima se pojavljuje "playwright"). Na merenju 2026-11-12
ceo paket je trajao 388 s, a bez pregledaca 37 s; pregledac se pokrece jednom po upitu (craft-testing).

Izlazni kod je pytest-ov, ne od filtera: presuda se nikad ne cita iz "| tail".
Razlikuje kvar infrastrukture: ako >= 5 testova padne sa ISTOM porukom, to je
verovatno baza/mreza, ne kod, i tako se i javlja.
"""
import collections, importlib.util, os, re, subprocess, sys

sys.stdout.reconfigure(encoding='utf-8')
PRESKOCI = {'.git', 'venv', '.venv', 'node_modules', '__pycache__', 'staticfiles', 'site-packages', '.claude'}


def test_moduli():
    """(brzi, spori): putanje test modula u projektu; spor je modul koji koristi pregledac."""
    brzi, spori = [], []
    for koren, folderi, fajlovi in os.walk('.'):
        folderi[:] = sorted(f for f in folderi if f not in PRESKOCI)
        for ime in sorted(fajlovi):
            if ime.startswith('test') and ime.endswith('.py'):
                put = os.path.relpath(os.path.join(koren, ime))
                with open(put, encoding='utf-8', errors='replace') as f:
                    (spori if 'playwright' in f.read() else brzi).append(put)
    return brzi, spori


def argumenti():
    """Argumenti za test runner; --brzo se zamenjuje spiskom brzih modula ili iskljucenjem sporih."""
    ostalo = [a for a in sys.argv[1:] if a != '--brzo']
    if '--brzo' not in sys.argv[1:]:
        return ostalo
    brzi, spori = test_moduli()
    print('brzi paket: %d modula, bez pregledaca: %s' % (len(brzi), ', '.join(spori) or 'nema'))
    if os.path.exists('manage.py') and not pytest_podesen():
        oznake = [os.path.splitext(p)[0].replace(os.sep, '.') for p in brzi]
        return ostalo + (oznake if not [a for a in ostalo if not a.startswith('-')] else [])
    return ostalo + ['--ignore=%s' % p for p in spori]


def django_testovi():
    p = subprocess.run([sys.executable, 'manage.py', 'test', *argumenti()],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    izlaz = p.stdout + p.stderr
    pali = re.findall(r'^(?:FAIL|ERROR): (.+)$', izlaz, re.M)
    pokrenuto = re.search(r'^Ran (\d+) tests?', izlaz, re.M)
    if pokrenuto:
        print('%s pokrenuto, %d palo' % (pokrenuto.group(1), len(pali)))
    else:
        print('nema sazetka: testovi nisu pokrenuti (izlazni kod %d)' % p.returncode)
        print(izlaz[-600:])
    for r in pali[:20]:
        print(r[:160])
    print('EXIT=%d' % p.returncode)
    return p.returncode


def pytest_podesen():
    if importlib.util.find_spec('pytest') is None:
        return False
    if os.path.exists('pytest.ini') or os.path.exists('conftest.py'):
        return True
    if not os.path.exists('pyproject.toml'):
        return False
    with open('pyproject.toml', encoding='utf-8', errors='replace') as f:
        return '[tool.pytest' in f.read()


def main():
    if os.path.exists('manage.py') and not pytest_podesen():
        return django_testovi()
    p = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-rf', '--tb=line', *argumenti()],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    izlaz = p.stdout + p.stderr
    pali = [r for r in izlaz.splitlines() if r.startswith('FAILED ')]
    sazetak = next((r for r in reversed(izlaz.splitlines()) if re.search(r'\d+ (passed|failed|error)', r)), '')
    print(sazetak.strip('= ') or 'nema sazetka: pytest nije pokrenut (izlazni kod %d)' % p.returncode)
    for r in pali[:20]:
        print(r[7:][:160])
    if len(pali) > 20:
        print('... i jos %d' % (len(pali) - 20))
    poruke = collections.Counter(r.split(' - ', 1)[-1] for r in pali)
    if poruke and poruke.most_common(1)[0][1] >= 5:
        print('VEROVATNO INFRASTRUKTURA: %d testova pada sa istom porukom: %s'
              % (poruke.most_common(1)[0][1], poruke.most_common(1)[0][0][:120]))
    print('EXIT=%d' % p.returncode)
    return p.returncode


if __name__ == '__main__':
    sys.exit(main())
