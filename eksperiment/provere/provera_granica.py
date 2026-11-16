"""Granice kazne za budzet: partije cija je cena TACNO 10/20/30/40 % iznad budzeta, i one odmah iznad.

Trazi ih kroz stalne strategije (ista cetiri izbora u svih 8 krugova) i mnogo semena, pa poredi poene
strane sa mojom formulom. Pokretanje: <venv strane>\\python provera_granica.py <projekat> <prazan|plugin>
"""
import itertools, json, os, random, sys
from decimal import Decimal as D, ROUND_CEILING

PROJEKAT, STRANA = sys.argv[1], sys.argv[2]
os.chdir(PROJEKAT); sys.path.insert(0, PROJEKAT)
os.environ['DJANGO_SETTINGS_MODULE'] = 'orkestrator.settings'
import django
django.setup()
BUDZET = D(24)


def kazna(cena):
    preko = cena - BUDZET
    if preko <= 0:
        return 0, D(0)
    procenat = preko * 100 / BUDZET
    return min(50, 10 * int((procenat / 10).to_integral_value(rounding=ROUND_CEILING))), procenat


if STRANA == 'prazan':
    from igra import pravila, parametri as p
    GRUPE = [list(p.MODELI), list(p.NIVOI), list(p.KONTEKSTI), list(p.PODELE)]

    def igraj(seme, iz):
        potezi = [pravila.Izbori(*iz)] * 8
        r = pravila.konacni_rezultat(seme, potezi, 2)
        krugovi = pravila._odigraj_sve(seme, potezi)
        return r.poeni, sum(k.vrsta == pravila.DORADA for k in krugovi), len(r.tihe_greske), D(r.ukupna_cena), r.ukupni_minuti > p.ROK
else:
    from igra import motor, parametri as p
    GRUPE = [list(o) for o in motor.GRUPE_IZBORA.values()]
    IMENA = list(motor.GRUPE_IZBORA)

    def igraj(seme, iz):
        s = motor.nova_igra(seme)
        for k in range(1, 9):
            s = motor.odigraj_potez(s, k, dict(zip(IMENA, iz)))
        r = s['rezultat']
        return (r['poeni'], sum(1 for x in s['istorija'] if x['ishod'] == motor.DORADA), len(r['tihe_greske']),
                D(repr(r['ukupna_cena'])).quantize(D('1e-9')), r['rok_prekoracen'])

rng = random.Random(77)
po_granici, razlike, ukupno = {}, [], 0
for iz in itertools.product(*GRUPE):
    for _ in range(25):
        seme = '%032x' % rng.getrandbits(128)
        poeni, dorade, tihe, cena, rok = igraj(seme, iz)
        k, procenat = kazna(cena)
        ocekivano = max(0, 100 - 5 * dorade - 35 * tihe - k - (20 if rok else 0))
        ukupno += 1
        if procenat > 0 and procenat % 10 == 0:
            po_granici[f'{procenat}% -> -{k}'] = po_granici.get(f'{procenat}% -> -{k}', 0) + 1
        if poeni != ocekivano:
            razlike.append((seme, iz, str(cena), str(procenat), poeni, ocekivano))
print(json.dumps({'strana': STRANA, 'partija': ukupno, 'tacno_na_granici': po_granici, 'razlika': len(razlike),
                  'primeri': razlike[:5]}, ensure_ascii=False, default=str))
