"""Jednokratno: postojeca, vec prijavljena okruzenja prebacuje na rad kroz ekstenziju."""
import json, os, sys

sys.path.insert(0, r'C:\posao\diplomski\scripts')
import priprema_poredjenja as p

KOREN = r'C:\poredjenje-orkestrator'
for s in p.STRANE:
    p.upisi_okruzenje_strane(KOREN, s)
    stari = os.path.join(KOREN, s, 'pokreni.cmd')
    if os.path.exists(stari):
        os.remove(stari)
p.upisi_pokretanje(KOREN, r'C:\posao\diplomski\scripts\poredjenje.py')
put = os.path.join(KOREN, 'manifest.json')
with open(put, encoding='utf-8') as f:
    m = json.load(f)
m.pop('komande', None)
m['claude'] = p.verzija_alata()
m['podesavanja'] = p.PODESAVANJA_STRANE
p.upisi(put, json.dumps(m, ensure_ascii=False, indent=1) + '\n')
print('azurirano; alat', m['claude'])
