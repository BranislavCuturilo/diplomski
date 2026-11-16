# -*- coding: utf-8 -*-
"""Oznacava rizicne operacije u Django migracijama (vidi stack-django/references/migrations.md).

    python tools/check_migrations.py [koren_projekta] [--samo-nove N]

--samo-nove N: proverava samo N najnovijih migracija po aplikaciji.
"""
import argparse, glob, os, re, sys

sys.stdout.reconfigure(encoding='utf-8')
PROVERE = [
    (re.compile(r'AddField\((?:(?!null=True).)*?\)\s*,?\s*$', re.S), None),   # rucno ispod
    (re.compile(r'RemoveField\('), 'brisanje kolone: podaci se gube; da li je pre toga isporuceno citanje bez nje?'),
    (re.compile(r'RunPython\(\s*\w+\s*\)'), 'RunPython bez obrnute funkcije'),
    (re.compile(r'^from \w+\.models import', re.M), 'import modela u migraciji; koristi apps.get_model'),
    (re.compile(r'AlterField\([^)]*unique=True'), 'unique na postojecoj koloni: prvo nadji i ocisti duplikate'),
]


def add_not_null(tekst):
    """AddField bez null=True i bez default = pada ili zakljucava punu tabelu."""
    nalazi = []
    for m in re.finditer(r'migrations\.AddField\((.*?)\n\s{8}\)', tekst, re.S):
        telo = m.group(1)
        if 'null=True' not in telo and 'ManyToMany' not in telo:
            polje = re.search(r"name=['\"](\w+)", telo)
            nalazi.append('NOT NULL kolona "%s": na punoj tabeli ide u 3 koraka (nullable, popuni, NOT NULL)'
                          % (polje.group(1) if polje else '?'))
    return nalazi


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('koren', nargs='?', default='.')
    ap.add_argument('--samo-nove', type=int, default=0)
    a = ap.parse_args()
    ukupno = 0
    for folder in glob.glob(os.path.join(a.koren, '**', 'migrations'), recursive=True):
        fajlovi = sorted(f for f in glob.glob(os.path.join(folder, '[0-9]*.py')))
        if a.samo_nove:
            fajlovi = fajlovi[-a.samo_nove:]
        for put in fajlovi:
            t = open(put, encoding='utf-8', errors='replace').read()
            nalazi = add_not_null(t) + [poruka for obrazac, poruka in PROVERE[1:] if obrazac.search(t)]
            for n in nalazi:
                ukupno += 1
                print('%s: %s' % (os.path.relpath(put, a.koren), n))
    print('rizicnih operacija: %d' % ukupno)


if __name__ == '__main__':
    main()
