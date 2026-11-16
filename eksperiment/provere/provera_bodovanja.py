"""Nezavisna provera novog bodovanja, ista za obe strane.

A) 2000 nasumicnih partija: poeni strane = moja formula (staro i novo pravilo), uz brojanje granica.
B) Nadogradnja: baza PRE izmene (stari rezultat, stari link, partija u toku), pa migracija, pa sta igrac vidi.

Pokretanje: <venv strane>\\python provera_bodovanja.py <projekat> <prazan|plugin>
"""
import json, math, os, random, re, shutil, sqlite3, subprocess, sys, tempfile
from decimal import Decimal as D, ROUND_CEILING

IZVOR, STRANA = sys.argv[1], sys.argv[2]
KOPIJA = os.path.join(tempfile.mkdtemp(), 'projekat')
shutil.copytree(IZVOR, KOPIJA, ignore=shutil.ignore_patterns('*.sqlite3', '*.sqlite3.*', '__pycache__', '.claude', 'venv'))
os.chdir(KOPIJA); sys.path.insert(0, KOPIJA)
os.environ['DJANGO_SETTINGS_MODULE'] = 'orkestrator.settings'
PRE = '0003' if STRANA == 'prazan' else '0005'
env = dict(os.environ, PYTHONIOENCODING='utf-8')
subprocess.run([sys.executable, 'manage.py', 'migrate', 'igra', PRE, '--noinput', '-v', '0'], check=True, env=env)
subprocess.run([sys.executable, 'manage.py', 'migrate', 'sessions', '--noinput', '-v', '0'], check=True, env=env)
import django
django.setup()

rezultati = []


def proveri(oznaka, uslov, detalj=''):
    rezultati.append({'provera': oznaka, 'ok': bool(uslov), 'detalj': str(detalj)[:500]})


BUDZET, ROK = D(24), D(150)


def moja_kazna_budzeta(cena, novo):
    preko = cena - BUDZET
    if preko <= 0:
        return 0, None
    if not novo:
        return 30, preko * 100 / BUDZET
    procenat = preko * 100 / BUDZET
    koraci = int((procenat / 10).to_integral_value(rounding=ROUND_CEILING))
    return min(50, 10 * koraci), procenat


def moji_poeni(dorade, tihe, cena, rok_preko, novo):
    kazna, procenat = moja_kazna_budzeta(cena, novo)
    poeni = 100 - 5 * dorade - (35 if novo else 25) * tihe - kazna - (20 if rok_preko else 0)
    return max(0, poeni), procenat


rng = random.Random(2026)
if STRANA == 'prazan':
    from igra import pravila, parametri as p
    GRUPE = {'model': list(p.MODELI), 'nivo': list(p.NIVOI), 'kontekst': list(p.KONTEKSTI), 'podela': list(p.PODELE)}

    def izbori():
        return pravila.Izbori(**{g: rng.choice(o) for g, o in GRUPE.items()})

    def igraj(seme, potezi, verzija):
        r = pravila.konacni_rezultat(seme, potezi, verzija)
        krugovi = pravila._odigraj_sve(seme, potezi)
        dorade = sum(k.vrsta == pravila.DORADA for k in krugovi)
        return r.poeni, dorade, len(r.tihe_greske), D(r.ukupna_cena), r.ukupni_minuti > p.ROK
else:
    from igra import motor, parametri as p
    GRUPE = {g: list(o) for g, o in motor.GRUPE_IZBORA.items()}

    def izbori():
        return {g: rng.choice(o) for g, o in GRUPE.items()}

    def igraj(seme, potezi, verzija):
        s = motor.nova_igra(seme)
        if verzija == 1:
            s.pop('pravila', None)
        for k, iz in enumerate(potezi, 1):
            s = motor.odigraj_potez(s, k, iz)
        r = s['rezultat']
        dorade = sum(1 for x in s['istorija'] if x['ishod'] == motor.DORADA)
        return r['poeni'], dorade, len(r['tihe_greske']), D(repr(r['ukupna_cena'])), r['rok_prekoracen']

# A) svojstvo nad 2000 partija
razlike, granice, preko, tihe_uk = {1: [], 2: []}, 0, 0, 0
for i in range(2000):
    seme = '%032x' % rng.getrandbits(128)
    potezi = [izbori() for _ in range(8)]
    for verzija in (1, 2):
        poeni, dorade, tihe, cena, rok = igraj(seme, potezi, verzija)
        moji, procenat = moji_poeni(dorade, tihe, cena.quantize(D('1e-9')) if STRANA == 'plugin' else cena, rok, verzija == 2)
        if poeni != moji:
            razlike[verzija].append((seme, poeni, moji, str(cena), str(procenat)))
        if verzija == 2:
            tihe_uk += tihe
            if procenat is not None:
                preko += 1
                if procenat % 10 == 0:
                    granice += 1
proveri('2000 partija, nova pravila: poeni = moja formula', not razlike[2], f'{len(razlike[2])} razlika, npr. {razlike[2][:3]}')
proveri('2000 partija, stara pravila: poeni = moja formula', not razlike[1], f'{len(razlike[1])} razlika, npr. {razlike[1][:3]}')
proveri('provera je pogodila granice', granice > 0 and preko > 100 and tihe_uk > 100,
        f'prekoracenja {preko}, tacno na granici 10/20/30/40 % {granice}, tihih gresaka {tihe_uk}')

# B) nadogradnja: stari podaci upisani u bazu PRE migracije, kao da ih je napravio stari kod
#    Biram partiju u kojoj staro i novo pravilo daju razlicite poene.
while True:
    seme = '%032x' % rng.getrandbits(128)
    potezi = [izbori() for _ in range(8)]
    staro = igraj(seme, potezi, 1)[0]; novo = igraj(seme, potezi, 2)[0]
    if staro != novo and staro > 0:
        break
while True:
    seme_u_toku = '%032x' % rng.getrandbits(128)
    potezi_u_toku = [izbori() for _ in range(8)]
    staro_u_toku = igraj(seme_u_toku, potezi_u_toku, 1)[0]; novo_u_toku = igraj(seme_u_toku, potezi_u_toku, 2)[0]
    if staro_u_toku != novo_u_toku:
        break

baza = sqlite3.connect('db.sqlite3')
kolone = lambda t: [r[1] for r in baza.execute(f'PRAGMA table_info({t})')]
from django.contrib.sessions.backends.db import SessionStore
TOKEN = 'StaRiLinkStaRiLinkAAAA'
if STRANA == 'prazan':
    ocena_staro = pravila.konacni_rezultat(seme, potezi, 1).ocena
    baza.execute('INSERT INTO igra_partija (id, seme, napravljena, kod) VALUES (501, ?, "2026-11-01 10:00:00", ?)', (seme, TOKEN))
    for k, iz in enumerate(potezi, 1):
        baza.execute('INSERT INTO igra_potez (partija_id, krug, model, nivo, kontekst, podela) VALUES (501, ?, ?, ?, ?, ?)', (k, *iz))
    baza.execute('INSERT INTO igra_rezultat (partija_id, ime, poeni, ocena, sacuvan) VALUES (501, "StariIgrac", ?, ?, "2026-11-01 10:05:00")',
                 (staro, ocena_staro))
    baza.execute('INSERT INTO igra_partija (id, seme, napravljena, kod) VALUES (502, ?, "2026-11-11 10:00:00", NULL)', (seme_u_toku,))
    for k, iz in enumerate(potezi_u_toku[:4], 1):
        baza.execute('INSERT INTO igra_potez (partija_id, krug, model, nivo, kontekst, podela) VALUES (502, ?, ?, ?, ?, ?)', (k, *iz))
    baza.commit()
    sesija = SessionStore(); sesija['partija_id'] = 502; sesija.create()
else:
    s = motor.nova_igra(seme); s.pop('pravila', None)
    for k, iz in enumerate(potezi, 1):
        s = motor.odigraj_potez(s, k, iz)
    zavrsni = motor.za_deljenje(s)
    for kljuc in ('budzet_procenat', 'kazna_budzet'):   # polja koja je dodala ova izmena; stari snimak ih nema
        zavrsni.pop(kljuc, None)
    zavrsni = json.loads(json.dumps(zavrsni, default=str))
    import hashlib
    oznaka = hashlib.sha256(seme.encode()).hexdigest()
    baza.execute('INSERT INTO igra_rezultat (ime, poeni, ocena, sacuvan, partija) VALUES ("StariIgrac", ?, ?, "2026-11-01 10:05:00", ?)',
                 (staro, s['rezultat']['ocena'], oznaka))
    baza.execute('INSERT INTO igra_deljenirezultat (token, partija, zavrsni, nastao, istice) VALUES (?, ?, ?, "2026-11-01 10:06:00", "2099-01-01 00:00:00")',
                 (TOKEN, oznaka, json.dumps(zavrsni)))
    baza.commit()
    u_toku = motor.nova_igra(seme_u_toku); u_toku.pop('pravila', None)
    for k, iz in enumerate(potezi_u_toku[:4], 1):
        u_toku = motor.odigraj_potez(u_toku, k, iz)
    sesija = SessionStore(); sesija['igra'] = json.loads(json.dumps(u_toku, default=str)); sesija.create()
baza.close()
r = subprocess.run([sys.executable, 'manage.py', 'migrate', '--noinput', '-v', '0'], capture_output=True, text=True, env=env)
proveri('migracija prolazi nad bazom sa starim podacima', r.returncode == 0, r.stderr[-400:])

from django.test import Client
from django.test.utils import setup_test_environment
setup_test_environment()
c = Client()
pocetna = c.get('/').content.decode('utf-8')
deo = pocetna[pocetna.find('StariIgrac') - 600: pocetna.find('StariIgrac') + 900] if 'StariIgrac' in pocetna else ''
proveri('rang lista: stari rezultat zadrzava stare poene', 'StariIgrac' in pocetna and re.search(rf'\b{staro}\b', deo),
        f'staro={staro} novo={novo}')
deljena = c.get(('/partija/' if STRANA == 'prazan' else '/r/') + TOKEN + '/')
tekst = deljena.content.decode('utf-8')
nadjeni = re.findall(r'"poeni":\s*(\d+)', tekst) or re.findall(r'poeni[^>]*>\s*(\d+)\s*<', tekst)
proveri('stari deljeni link: status 200 i stari poeni, ne novi', deljena.status_code == 200 and str(staro) in nadjeni and str(novo) not in nadjeni,
        f'status {deljena.status_code}, nadjeno {nadjeni}, staro={staro}, novo={novo}')

c2 = Client(); c2.cookies['sessionid'] = sesija.session_key
for k, iz in enumerate(potezi_u_toku[4:], 5):
    if STRANA == 'prazan':
        odg = c2.post('/api/potez/', json.dumps(dict(iz._asdict(), krug=k)), content_type='application/json')
    else:
        odg = c2.post('/potez/', json.dumps({'krug': k, 'izbori': iz}), content_type='application/json')
if STRANA == 'prazan':
    kraj = c2.get('/kraj/').content.decode('utf-8')
    poeni_kraj = re.findall(r'poeni[^>]*>\s*(\d+)\s*<', kraj)
else:
    poeni_kraj = [str(odg.json().get('zavrsni', {}).get('poeni'))] if odg.status_code == 200 else [f'status {odg.status_code}']
proveri('partija zapoceta pre izmene zavrsava po starim pravilima (odluka obe strane)', str(staro_u_toku) in poeni_kraj,
        f'nadjeno {poeni_kraj}, staro={staro_u_toku}, novo={novo_u_toku}')

print(json.dumps({'strana': STRANA, 'prolazi': sum(x['ok'] for x in rezultati), 'ukupno': len(rezultati), 'provere': rezultati},
                 ensure_ascii=False, indent=1))
