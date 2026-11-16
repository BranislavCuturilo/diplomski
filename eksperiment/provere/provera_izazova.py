"""Nezavisna provera dnevnog izazova, ista za obe strane, na test bazi, sa podmetnutim vremenom.

Pokretanje: <venv strane>\\python provera_izazova.py <projekat> <prazan|plugin>
"""
import datetime as dt, json, os, random, re, sys, tempfile
from unittest import mock

PROJEKAT, STRANA = sys.argv[1], sys.argv[2]
sys.path.insert(0, PROJEKAT); os.chdir(PROJEKAT)
os.environ['DJANGO_SETTINGS_MODULE'] = 'orkestrator.settings'
import django
django.setup()
from django.db import connection
from django.test import Client, override_settings
from django.test.utils import setup_test_environment
from django.utils import timezone
setup_test_environment()
connection.settings_dict.setdefault('TEST', {})['NAME'] = os.path.join(tempfile.mkdtemp(), 'iz.sqlite3')
connection.creation.create_test_db(verbosity=0, keepdb=False, serialize=False)
from igra.models import Rezultat

UTC = dt.timezone.utc
rezultati = []


def proveri(oznaka, uslov, detalj=''):
    rezultati.append({'provera': oznaka, 'ok': bool(uslov), 'detalj': str(detalj)[:400]})


if STRANA == 'prazan':
    from igra import parametri as p, servis
    GRUPE = {'model': sorted(p.MODELI), 'nivo': sorted(p.NIVOI), 'kontekst': sorted(p.KONTEKSTI), 'podela': sorted(p.PODELE)}

    def pocni_dnevnu(c):
        c.get('/'); return c.post('/dnevna/')

    def potez(c, krug, iz):
        return c.post('/api/potez/', json.dumps(dict(iz, krug=krug)), content_type='application/json')

    def sacuvaj(c, ime):
        return c.post('/rezultat/', {'ime': ime})

    def seme(dan):
        return servis.dnevno_seme(dan)

    def dan_reda(r):
        return r.partija.dan

    def stanje_poena(c):
        from igra.models import Partija
        pa = Partija.objects.get(pk=c.session['partija_id'])
        return servis._konacni_rezultat(pa).poeni if pa.potezi.count() == 8 else None

    def krug_u_toku(c):
        from igra.models import Partija
        return Partija.objects.get(pk=c.session['partija_id']).potezi.count() + 1

    def dnevna_sekcija(html):
        i = html.find('id="dnevna-lista"'); return html[i:i + 4000] if i >= 0 else ''

    def glavna_sekcija(html):
        i = html.find('id="rang-lista"'); j = html.find('id="dnevna-lista"'); return html[i:j] if i >= 0 else ''

    def nova_obicna(c):
        c.post('/nova/')
else:
    from igra import motor, views
    GRUPE = {g: sorted(o) for g, o in motor.GRUPE_IZBORA.items()}

    def pocni_dnevnu(c):
        return c.get('/dnevni/')

    def potez(c, krug, iz):
        return c.post('/dnevni/potez/', json.dumps({'krug': krug, 'izbori': iz}), content_type='application/json')

    def sacuvaj(c, ime):
        return c.post('/dnevni/sacuvaj/', json.dumps({'ime': ime}), content_type='application/json')

    def seme(dan):
        return views._dnevno_seme(dan)

    def dan_reda(r):
        return r.dan

    def stanje_poena(c):
        s = c.session.get('dnevna') or {}
        return (s.get('rezultat') or {}).get('poeni') if s.get('zavrsena') else None

    def krug_u_toku(c):
        return (c.session.get('dnevna') or {}).get('krug')

    def json_blok(html, ime):
        m = re.search(r'<script id="%s" type="application/json">(.*?)</script>' % ime, html, re.S)
        return m.group(1) if m else ''

    def dnevna_sekcija(html):
        return json.loads(json_blok(html, 'rang-dana') or 'null').__repr__()

    def glavna_sekcija(html):
        return json.loads(json_blok(html, 'rang-lista') or 'null').__repr__()

    def nova_obicna(c):
        c.get('/')

rng = random.Random(1)
IZBORI = [{g: rng.choice(o) for g, o in GRUPE.items()} for _ in range(8)]


def odigraj_dnevnu(c, do=8, od=1):
    for k in range(od, do + 1):
        r = potez(c, k, IZBORI[k - 1])
        assert r.status_code == 200, (k, r.status_code, r.content[:200])


SADA = dt.datetime(2026, 11, 12, 10, 0, tzinfo=UTC)          # 11:00 u Beogradu
with mock.patch('django.utils.timezone.now', return_value=SADA):
    # A. ista partija za sve
    a, b = Client(), Client()
    pocni_dnevnu(a); odigraj_dnevnu(a); pocni_dnevnu(b); odigraj_dnevnu(b)
    pa, pb = stanje_poena(a), stanje_poena(b)
    proveri('dva igraca, isti izbori: isti ishod', pa is not None and pa == pb, (pa, pb))
    if STRANA == 'prazan':
        from igra.models import Partija
        sa, sb = (Partija.objects.get(pk=x.session['partija_id']).seme for x in (a, b))
        o1, o2 = Client(), Client(); o1.post('/nova/'); o2.post('/nova/')
        so1, so2 = (Partija.objects.get(pk=x.session['partija_id']).seme for x in (o1, o2))
    else:
        sa, sb = a.session['dnevna']['seme'], b.session['dnevna']['seme']
        o1, o2 = Client(), Client(); o1.get('/'); o2.get('/')
        so1, so2 = o1.session['igra']['seme'], o2.session['igra']['seme']
    proveri('dnevna partija: isto seme za dva igraca; obicna: razlicito', sa == sb and so1 != so2 and sa != so1, '')

    # B. seme zavisi od tajnog kljuca
    with override_settings(SECRET_KEY='drugi-tajni-kljuc-' + 'x' * 50):
        drugo = seme(timezone.localdate())
    proveri('seme dana zavisi od tajnog kljuca', drugo != seme(timezone.localdate()))
    proveri('seme dana je drugacije sutra', seme(dt.date(2026, 11, 13)) != seme(dt.date(2026, 11, 12)))

    # C. seme ne izlazi klijentu
    c = Client(); r1 = pocni_dnevnu(c); r2 = c.get('/dnevni/' if STRANA == 'plugin' else '/')
    tekst = r1.content.decode() + r2.content.decode() + potez(c, 1, IZBORI[0]).content.decode()
    proveri('seme dana nije u strani ni u odgovoru poteza', seme(timezone.localdate()) not in tekst)

    # D/E. jednom po sesiji; ponovni pocetak usred partije nastavlja istu
    odigraj_dnevnu(c, do=3, od=2)
    pocni_dnevnu(c)
    proveri('ponovni pocetak usred partije nastavlja istu (krug 4)', krug_u_toku(c) == 4, krug_u_toku(c))
    odigraj_dnevnu(c, od=4)
    r = sacuvaj(c, 'Prvi')
    proveri('dnevni rezultat se cuva', Rezultat.objects.filter(ime='Prvi').exists(), r.status_code)
    pre = Rezultat.objects.count()
    pocni_dnevnu(c)
    r = potez(c, 1, IZBORI[0])
    r2 = sacuvaj(c, 'PrviOpet')
    proveri('posle odigrane dnevne: nova dnevna partija u istoj sesiji ne pocinje i nema drugog upisa',
            r.status_code >= 400 and Rezultat.objects.count() == pre, (r.status_code, r2.status_code))

    # F. vise igraca cuva rezultat istog dana
    for ime in ('Drugi', 'Treci'):
        x = Client(); pocni_dnevnu(x); odigraj_dnevnu(x); sacuvaj(x, ime)
    sacuvani = sorted(Rezultat.objects.filter(ime__in=['Prvi', 'Drugi', 'Treci']).values_list('ime', flat=True))
    proveri('vise igraca cuva rezultat iste dnevne partije', sacuvani == ['Drugi', 'Prvi', 'Treci'], sacuvani)

    # G. liste se ne mesaju
    o = Client(); nova_obicna(o)
    if STRANA == 'prazan':
        for k in range(1, 9):
            o.post('/api/potez/', json.dumps(dict(IZBORI[k - 1], krug=k)), content_type='application/json')
        o.post('/rezultat/', {'ime': 'Obicni'})
    else:
        for k in range(1, 9):
            o.post('/potez/', json.dumps({'krug': k, 'izbori': IZBORI[k - 1]}), content_type='application/json')
        o.post('/sacuvaj/', json.dumps({'ime': 'Obicni'}), content_type='application/json')
    html = Client().get('/').content.decode()
    dnevna, glavna = dnevna_sekcija(html), glavna_sekcija(html)
    proveri('lista dana ima dnevne, a nema obicni rezultat', all(i in dnevna for i in ('Prvi', 'Drugi', 'Treci')) and 'Obicni' not in dnevna,
            dnevna[:200])
    proveri('glavna lista ima obicni, a nema dnevne rezultate', 'Obicni' in glavna and not any(i in glavna for i in ('Drugi', 'Treci')),
            glavna[:200])

# H. ponoc: partija pocne u 23:59:50 po Beogradu, zavrsi se posle ponoci
pre_ponoci = dt.datetime(2026, 11, 12, 22, 59, 50, tzinfo=UTC)
posle_ponoci = dt.datetime(2026, 11, 12, 23, 0, 30, tzinfo=UTC)
p = Client()
with mock.patch('django.utils.timezone.now', return_value=pre_ponoci):
    pocni_dnevnu(p); odigraj_dnevnu(p, do=4)
with mock.patch('django.utils.timezone.now', return_value=posle_ponoci):
    odigraj_dnevnu(p, od=5)
    r = sacuvaj(p, 'Ponoc')
    red = Rezultat.objects.filter(ime='Ponoc').first()
    proveri('partija zapoceta pre ponoci cuva se na listu dana pocetka (12.11.)',
            red is not None and dan_reda(red) == dt.date(2026, 11, 12), (r.status_code, red and dan_reda(red)))
    html = Client().get('/').content.decode()
    proveri('posle ponoci lista dana je za novi dan (bez juce sacuvanih)', 'Ponoc' not in dnevna_sekcija(html) and 'Drugi' not in dnevna_sekcija(html))

# I. dan po beogradskom vremenu: 23:30 UTC 12.11. je vec 13.11. u Beogradu
with mock.patch('django.utils.timezone.now', return_value=dt.datetime(2026, 11, 12, 23, 30, tzinfo=UTC)):
    q = Client(); pocni_dnevnu(q); odigraj_dnevnu(q); sacuvaj(q, 'Beograd')
    red = Rezultat.objects.filter(ime='Beograd').first()
    proveri('dan se racuna po beogradskom vremenu (23:30 UTC = 13.11.)', red is not None and dan_reda(red) == dt.date(2026, 11, 13),
            red and dan_reda(red))

print(json.dumps({'strana': STRANA, 'prolazi': sum(x['ok'] for x in rezultati), 'ukupno': len(rezultati), 'provere': rezultati},
                 ensure_ascii=False, indent=1))
