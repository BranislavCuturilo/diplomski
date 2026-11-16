"""Jednokratno: upisuje upite runde 3 u postojece poredjenje i belezi ih u manifest. Plugin se ne menja."""
import json, os, sys

sys.path.insert(0, r'C:\posao\diplomski\scripts')
import priprema_poredjenja as p

KOREN = r'C:\poredjenje-orkestrator'
for ime, tekst in p.UPITI_FAJLOVI[6:]:
    p.upisi(os.path.join(KOREN, ime), tekst + '\n')
put = os.path.join(KOREN, 'manifest.json')
with open(put, encoding='utf-8') as f:
    m = json.load(f)
m['upiti'] = dict(p.UPITI_FAJLOVI)
m['runda_3'] = {'datum': '2026-11-11', 'plugin_menjan': False,
                'razlog': 'na zahtev coveka: namerno izabrani zahtevi u kojima greska skupo kosta (podaci, autorizacija, javni rad)'}
p.upisi(put, json.dumps(m, ensure_ascii=False, indent=1) + '\n')
print('upisano:', ', '.join(ime for ime, _ in p.UPITI_FAJLOVI[6:]))
