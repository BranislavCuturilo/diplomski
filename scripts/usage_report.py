# -*- coding: utf-8 -*-
"""Izvestaj o koriscenju agenata i skillova iz .claude/usage/usage.jsonl (pise ga hooks/log_usage.py).

    python scripts/usage_report.py [--dana 30]

Ispisuje jednu tabelu; agent/skill koji POSTOJI a nije pozvan ni jednom ide na kraj
kao kandidat za popravku opisa ili povlacenje.
"""
import argparse, collections, datetime, glob, json, os, sys

sys.stdout.reconfigure(encoding='utf-8')
KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dana', type=int, default=30)
    ap.add_argument('--log', default=os.path.join('.claude', 'usage', 'usage.jsonl'))
    a = ap.parse_args()
    od = datetime.datetime.now() - datetime.timedelta(days=a.dana)
    pozivi, tokeni = collections.Counter(), collections.Counter()
    if os.path.exists(a.log):
        with open(a.log, encoding='utf-8') as f:
            for red in f:
                z = json.loads(red)
                if datetime.datetime.fromisoformat(z['at']) < od:
                    continue
                k = (z['vrsta'], z['ime'].split(':')[-1])
                pozivi[k] += 1
                tokeni[k] += z.get('tokeni') or 0
    print('%-8s %-24s %7s %12s' % ('vrsta', 'ime', 'poziva', 'tokena'))
    for (v, i), n in pozivi.most_common():
        print('%-8s %-24s %7d %12d' % (v, i, n, tokeni[(v, i)]))
    postoje = {('agent', os.path.basename(p)[:-3]) for p in glob.glob(os.path.join(KOREN, 'agents', '*.md'))}
    postoje |= {('skill', os.path.basename(os.path.dirname(p)))
                for p in glob.glob(os.path.join(KOREN, 'skills', '*', '*', 'SKILL.md'))}
    nikad = sorted(postoje - set(pozivi))
    if nikad:
        print('\nNIJEDNOM pozvani za %d dana (proveri opis ili povuci):' % a.dana)
        for v, i in nikad:
            print('  %s %s' % (v, i))


if __name__ == '__main__':
    main()
