# -*- coding: utf-8 -*-
"""Mapa projekta iz koda: sta gde stoji, bez sadrzaja datoteka.

Glavna sesija u paralelnom rezimu cita ovu mapu umesto projekta i iz nje pise zadatke radnicima
(skill craft-delegiranje). Mapa se pravi iz koda pri svakom pokretanju, pa ne zastareva.

    python tools/mapa.py [koren] [--izlaz mapa.md]

Delovi: dokumenti, rute, modeli sa poljima, Python moduli sa funkcijama i klasama, sabloni,
staticke datoteke, testovi (oznaka [pregledac] za Playwright), migracije, prevodi, komande.
"""
import argparse, ast, os, re, sys

PRESKOCI = {'.git', 'venv', '.venv', 'node_modules', '__pycache__', 'staticfiles', '.claude', 'site-packages', 'kopije'}
NAJVISE_IMENA = 25
RUTA = re.compile(r"""(?:re_)?path\(\s*['"]([^'"]*)['"]\s*,\s*([\w.]+)(?:[^)]*?name\s*=\s*['"]([\w-]+)['"])?""")


def datoteke(koren):
    for d, folderi, fajlovi in os.walk(koren):
        folderi[:] = sorted(f for f in folderi if f not in PRESKOCI and not f.startswith('.'))
        for ime in sorted(fajlovi):
            yield os.path.relpath(os.path.join(d, ime), koren).replace(os.sep, '/')


def procitaj(koren, put):
    with open(os.path.join(koren, put), encoding='utf-8', errors='replace') as f:
        return f.read()


def redova(tekst):
    return sum(1 for r in tekst.splitlines() if r.strip())


def polja_modela(klasa):
    polja = []
    for cvor in klasa.body:
        if isinstance(cvor, ast.Assign) and isinstance(cvor.value, ast.Call):
            poziv = cvor.value.func
            ime_poziva = poziv.attr if isinstance(poziv, ast.Attribute) else getattr(poziv, 'id', '')
            if ime_poziva.endswith(('Field', 'Key')):
                polja += [t.id for t in cvor.targets if isinstance(t, ast.Name)]
    return polja


def opis_modula(tekst):
    """(klase, funkcije, modeli{ime: polja}) najviseg nivoa; prazno za neispravan Python."""
    try:
        stablo = ast.parse(tekst)
    except SyntaxError:
        return [], [], {}
    klase, funkcije, modeli = [], [], {}
    for cvor in stablo.body:
        if isinstance(cvor, ast.ClassDef):
            baze = [ast.unparse(b) for b in cvor.bases]
            if any(b.endswith('Model') for b in baze):
                modeli[cvor.name] = polja_modela(cvor)
            else:
                klase.append(cvor.name)
        elif isinstance(cvor, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funkcije.append(cvor.name)
    return klase, funkcije, modeli


def skrati(imena):
    return ', '.join(imena[:NAJVISE_IMENA]) + (' ... (+%d)' % (len(imena) - NAJVISE_IMENA) if len(imena) > NAJVISE_IMENA else '')


def mapa(koren):
    sve = list(datoteke(koren))
    izlaz = ['# Mapa projekta', '', 'Napravljena iz koda (`tools/mapa.py`); sadrzaj datoteka cita radnik, ne glavna sesija.', '']

    dokumenti = [p for p in sve if p.endswith('.md') and '/' not in p.strip('./')]
    if dokumenti:
        izlaz += ['## Dokumenti', '']
        for p in dokumenti:
            tekst = procitaj(koren, p)
            naslov = next((r.lstrip('# ').strip() for r in tekst.splitlines() if r.startswith('#')), '')
            izlaz.append('- `%s` (%d redova): %s' % (p, redova(tekst), naslov))
        izlaz.append('')

    rute = []
    for p in (p for p in sve if p.endswith('urls.py')):
        for m in RUTA.finditer(procitaj(koren, p)):
            rute.append('- `/%s` -> `%s`%s (`%s`)' % (m.group(1), m.group(2), ' ime `%s`' % m.group(3) if m.group(3) else '', p))
    if rute:
        izlaz += ['## Rute', ''] + rute + ['']

    python = [p for p in sve if p.endswith('.py') and '/migrations/' not in '/' + p and '/tests/' not in '/' + p
              and not os.path.basename(p).startswith('test')]
    modeli_svi, moduli = [], []
    for p in python:
        tekst = procitaj(koren, p)
        klase, funkcije, modeli = opis_modula(tekst)
        modeli_svi += ['- `%s` (`%s`): %s' % (ime, p, skrati(polja)) for ime, polja in modeli.items()]
        if klase or funkcije:
            delovi = ([('klase ' + skrati(klase))] if klase else []) + ([('funkcije ' + skrati(funkcije))] if funkcije else [])
            moduli.append('- `%s` (%d redova): %s' % (p, redova(tekst), '; '.join(delovi)))
    if modeli_svi:
        izlaz += ['## Modeli i polja', ''] + modeli_svi + ['']
    if moduli:
        izlaz += ['## Python moduli', ''] + moduli + ['']

    sabloni = [p for p in sve if p.endswith('.html')]
    if sabloni:
        izlaz += ['## Sabloni', '']
        for p in sabloni:
            tekst = procitaj(koren, p)
            roditelj = re.search(r"{%\s*extends\s+['\"]([^'\"]+)", tekst)
            izlaz.append('- `%s` (%d redova)%s' % (p, redova(tekst), ', nasledjuje `%s`' % roditelj.group(1) if roditelj else ''))
        izlaz.append('')

    staticke = [p for p in sve if '/static/' in '/' + p and p.endswith(('.js', '.css')) and '.min.' not in p]
    if staticke:
        izlaz += ['## Staticke datoteke', ''] + ['- `%s` (%d redova)' % (p, redova(procitaj(koren, p))) for p in staticke] + ['']

    testovi = [p for p in sve if p.endswith('.py') and os.path.basename(p).startswith('test') and p != 'tools/mapa.py']
    if testovi:
        izlaz += ['## Testovi', '']
        for p in testovi:
            tekst = procitaj(koren, p)
            izlaz.append('- `%s`: %d testova%s' % (p, len(re.findall(r'^\s*def test', tekst, re.M)), ' [pregledac]' if 'playwright' in tekst else ''))
        izlaz.append('')

    migracije = {}
    for p in sve:
        if '/migrations/' in '/' + p and re.search(r'/\d{4}_\w+\.py$', p):
            app = p.split('/migrations/')[0]
            migracije.setdefault(app, []).append(os.path.basename(p)[:-3])
    if migracije:
        izlaz += ['## Migracije', ''] + ['- `%s`: %d, poslednja `%s`' % (a, len(m), max(m)) for a, m in sorted(migracije.items())] + ['']

    prevodi = [p for p in sve if p.endswith('.po')]
    if prevodi:
        izlaz += ['## Prevodi', ''] + ['- `%s`: %d poruka' % (p, len(re.findall(r'^msgid ', procitaj(koren, p), re.M)) - 1) for p in prevodi] + ['']

    komande = [p for p in sve if '/management/commands/' in p and p.endswith('.py') and not p.endswith('__init__.py')]
    if komande:
        izlaz += ['## Komande', '', '- ' + ', '.join('`%s`' % os.path.basename(p)[:-3] for p in komande), '']
    return '\n'.join(izlaz)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('koren', nargs='?', default='.')
    ap.add_argument('--izlaz')
    a = ap.parse_args()
    tekst = mapa(a.koren)
    if a.izlaz:
        with open(a.izlaz, 'w', encoding='utf-8') as f:
            f.write(tekst + '\n')
        print('mapa: %s (%d znakova, ~%d tokena)' % (a.izlaz, len(tekst), len(tekst) // 4))
    else:
        sys.stdout.reconfigure(encoding='utf-8')
        print(tekst)
    return 0


if __name__ == '__main__':
    sys.exit(main())
