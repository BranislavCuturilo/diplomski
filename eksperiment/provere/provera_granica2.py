"""Kazna za budzet tacno na granicama i odmah iznad. Pokretanje: <venv>\\python provera_granica2.py <projekat> <strana>"""
import json, os, sys
from decimal import Decimal as D

PROJEKAT, STRANA = sys.argv[1], sys.argv[2]
os.chdir(PROJEKAT); sys.path.insert(0, PROJEKAT)
os.environ['DJANGO_SETTINGS_MODULE'] = 'orkestrator.settings'
import django
django.setup()

# ukupna cena -> ocekivana kazna (budzet 24 $)
SLUCAJEVI = [('24', 0), ('24.01', 10), ('26.4', 10), ('26.41', 20), ('28.8', 20), ('28.81', 30), ('31.2', 30),
             ('33.6', 40), ('33.61', 50), ('36', 50), ('100', 50)]
dobijeno = {}
if STRANA == 'prazan':
    from igra import pravila, parametri as p
    for cena, _ in SLUCAJEVI:
        dobijeno[cena] = pravila.kazna_budzeta(D(cena), p.BODOVANJA[2])
else:
    from igra import motor
    izbori = {g: sorted(o)[0] for g, o in motor.GRUPE_IZBORA.items()}
    for broj in range(1000):   # seme bez tihe greske, da cena ne dobije dodatak koji zavisi od ishoda
        s = motor.nova_igra('%032x' % broj)
        for k in range(1, 8):
            s = motor.odigraj_potez(s, k, izbori)
        probni = motor.odigraj_potez(dict(s, potroseno=0), 8, izbori)
        if not probni['rezultat']['tihe_greske']:
            break
    dodatak = probni['rezultat']['ukupna_cena'] - 0   # cena 8. kruga sa dodacima, bez prethodnih
    for cena, _ in SLUCAJEVI:
        kraj = motor.odigraj_potez(dict(s, potroseno=float(D(cena)) - dodatak), 8, izbori)
        dobijeno[cena] = kraj['rezultat']['kazna_budzet'] if kraj['rezultat']['budzet_prekoracen'] else 0
        dobijeno[cena + ' (ukupno)'] = round(kraj['rezultat']['ukupna_cena'], 9)
losi = [(c, dobijeno[c], o) for c, o in SLUCAJEVI if dobijeno[c] != o]
print(json.dumps({'strana': STRANA, 'ispravno': len(SLUCAJEVI) - len(losi), 'od': len(SLUCAJEVI), 'losi': losi, 'dobijeno': dobijeno},
                 ensure_ascii=False, default=str))
