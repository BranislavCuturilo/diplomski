"""Jednokratno: treci propisani upit i dopuna skilla ui-bootstrap pre faze stila, u postojecem poredjenju.

Skill se kopira u snimak plugina koji koristi sesija, a manifest belezi sta je i zasto promenjeno posle izrade.
"""
import hashlib, json, os, shutil, sys

sys.path.insert(0, r'C:\posao\diplomski\scripts')
import priprema_poredjenja as p

KOREN = r'C:\poredjenje-orkestrator'
DEO = os.path.join('skills', 'sloj-tehnologije', 'ui-bootstrap', 'SKILL.md')
izvor = os.path.join(p.PLUGIN, DEO)
cilj = os.path.join(KOREN, 'plugin', 'config', 'skills', 'diplomski', DEO)
shutil.copyfile(izvor, cilj)
with open(cilj, 'rb') as f:
    otisak = hashlib.sha256(f.read()).hexdigest()

p.upisi(os.path.join(KOREN, 'UPIT-stil.txt'), p.UPIT_STIL + '\n')
put = os.path.join(KOREN, 'manifest.json')
with open(put, encoding='utf-8') as f:
    m = json.load(f)
m['upit_stil'] = p.UPIT_STIL
m['dopuna_pre_stila'] = {'datum': '2026-11-10', 'fajl': DEO.replace(os.sep, '/'), 'sha256': otisak,
                         'razlog': 'odluka coveka: provere izgleda (telefon, konzola, slike) idu u skill, ne u upit'}
p.upisi(put, json.dumps(m, ensure_ascii=False, indent=1) + '\n')
print('skill u snimku:', otisak[:12])
print(open(os.path.join(KOREN, 'UPIT-stil.txt'), encoding='utf-8').read())
