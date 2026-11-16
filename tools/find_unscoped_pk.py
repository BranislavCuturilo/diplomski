# -*- coding: utf-8 -*-
"""Trazi u Django views.py mesta gde se objekat cita po pk/id BEZ helpera opsega.

    python tools/find_unscoped_pk.py [koren_projekta] [--helper for_user]

Mehanicki pola posla revizije: vraca KANDIDATE (fajl:red). Agent security ih
proverava jedan po jedan; alat ne odlucuje sam da je nesto propust.
"""
import argparse, os, re, sys

sys.stdout.reconfigure(encoding='utf-8')
CITANJE = re.compile(r'(get_object_or_404|\.get|\.filter)\s*\((?P<arg>[^)]*\b(pk|id)\s*=)')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('koren', nargs='?', default='.')
    ap.add_argument('--helper', default='for_user')
    a = ap.parse_args()
    nadjeno = 0
    for d, _, fajlovi in os.walk(a.koren):
        if any(x in d for x in ('migrations', '.venv', 'node_modules', '.git')):
            continue
        for f in fajlovi:
            if not (f == 'views.py' or (f.endswith('.py') and os.path.basename(d) == 'views')):
                continue
            put = os.path.join(d, f)
            for i, red in enumerate(open(put, encoding='utf-8', errors='replace'), 1):
                if CITANJE.search(red) and a.helper not in red:
                    nadjeno += 1
                    print('%s:%d  %s' % (put, i, red.strip()[:120]))
    print('kandidata: %d (helper: %s)' % (nadjeno, a.helper))


if __name__ == '__main__':
    main()
