# -*- coding: utf-8 -*-
"""Staticka evaluacija rutera: za svaki upit iz evals.json, da li hooks/prompt_router.py
predlaze ocekivani skill. Ne trosi model.

    python scripts/evals.py

Novi slucaj se dodaje kada ruter promasi u stvarnom radu, uz "poreklo".
"""
import json, os, subprocess, sys

sys.stdout.reconfigure(encoding='utf-8')
KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUTER = os.path.join(KOREN, 'hooks', 'prompt_router.py')


def predlog(upit):
    p = subprocess.run([sys.executable, RUTER], input=json.dumps({'prompt': upit}),
                       capture_output=True, text=True, encoding='utf-8')
    return p.stdout


def main():
    slucajevi = json.load(open(os.path.join(KOREN, 'scripts', 'evals.json'), encoding='utf-8'))
    pali = 0
    for s in slucajevi:
        izlaz = predlog(s['upit'])
        nedostaje = [x for x in s['ocekuje'] if x not in izlaz]
        if nedostaje:
            pali += 1
            print('PAO  %-50s nedostaje: %s' % (s['upit'][:50], ', '.join(nedostaje)))
    print('%d/%d proslo' % (len(slucajevi) - pali, len(slucajevi)))
    return 1 if pali else 0


if __name__ == '__main__':
    sys.exit(main())
