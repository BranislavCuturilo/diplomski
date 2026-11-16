"""Nezavisna provera pet funkcionalnosti (pravila, istorija, statistika, javni JSON), ista za obe strane.

Pokretanje: <venv strane>\\python provera_pet.py <projekat> <prazan|plugin>
"""
import datetime as dt, glob, json, os, random, re, sys, tempfile
from unittest import mock

PROJEKAT, STRANA = sys.argv[1], sys.argv[2]
sys.path.insert(0, PROJEKAT); os.chdir(PROJEKAT)
os.environ['DJANGO_SETTINGS_MODULE'] = 'orkestrator.settings'
import django
django.setup()
from django.db import connection
from django.test import Client
from django.test.utils import setup_test_environment
setup_test_environment()
connection.settings_dict.setdefault('TEST', {})['NAME'] = os.path.join(tempfile.mkdtemp(), 'pet.sqlite3')
connection.creation.create_test_db(verbosity=0, keepdb=False, serialize=False)
from django.contrib.auth import get_user_model

User = get_user_model()
LOZ = 'Vrlo-Duga-Lozinka-2026!'
UTC = dt.timezone.utc
rng = random.Random(8)
rezultati = []
CIRILICA = re.compile(r'[Ѐ-ӿ]')


def proveri(oznaka, uslov, detalj=''):
    rezultati.append({'provera': oznaka, 'ok': bool(uslov), 'detalj': str(detalj)[:300]})


if STRANA == 'prazan':
    from igra import moderacija, parametri as p
    GRUPE = {'model': p.MODELI, 'nivo': p.NIVOI, 'kontekst': p.KONTEKSTI, 'podela': p.PODELE}
    POLJA, JEZIK = ('ime', 'lozinka'), ('jezik', 'en')

    def napravi_moderatora(ime):
        moderacija.dodaj_moderatora(None, ime, LOZ, LOZ)

    def odigraj(c, do=8):
        c.get('/'); c.post('/nova/')
        for k in range(1, do + 1):
            c.post('/api/potez/', json.dumps(dict(izbori(), krug=k)), content_type='application/json')
        if do == 8:
            c.get('/kraj/')

    def istorija(html):
        i = html.find('id="moje-partije"')
        if i < 0:
            return 0, ''
        deo = html[i:html.find('</section>', i)]
        return deo.count('moja-partija'), deo

    def red_dana(html, dan):
        for red in re.findall(r'<tr class="dan-statistike.*?</tr>', html, re.S):
            if dan.strftime('%d.%m.%Y') in red:
                return int(re.search(r'vrednost-broja">(\d+)', red).group(1))
        return None

    def broj_dana(html):
        return len(re.findall(r'<tr class="dan-statistike', html))
else:
    from igra import motor, nalozi
    GRUPE = motor.GRUPE_IZBORA
    POLJA, JEZIK = ('username', 'password'), ('django_language', 'en')

    def napravi_moderatora(ime):
        nalozi.dodaj(None, ime, LOZ, glavni=True)
        u = User.objects.get(username=ime); u.nalog_moderatora.mora_promeniti = False; u.nalog_moderatora.save()

    def odigraj(c, do=8):
        if c.session.get('igra') is None or c.session['igra'].get('zavrsena'):
            c.get('/') if c.session.get('igra') is None else c.post('/nova/')
        for k in range(1, do + 1):
            c.post('/potez/', json.dumps({'krug': k, 'izbori': izbori()}), content_type='application/json')
        c.get('/')

    def istorija(html):
        i = html.find('id="istorija"')
        if i < 0:
            return 0, ''
        deo = html[i:html.find('</section>', i)]
        return deo.count('<td class="rang-datum">'), deo

    def red_dana(html, dan):
        for red in re.findall(r'<tr>\s*<th scope="row" class="rang-datum">.*?</tr>', html, re.S):
            if dan.strftime('%d.%m.%Y') in red or dan.isoformat() in red:
                return int(re.findall(r'<td class="rang-broj">(\d+)', red)[0])
        return None

    def broj_dana(html):
        return len(re.findall(r'<th scope="row" class="rang-datum">', html))


def izbori():
    return {g: rng.choice(sorted(o)) for g, o in GRUPE.items()}


def vidljiv_tekst(html):
    html = re.sub(r'<(script|style)\b.*?</\1>', ' ', html, flags=re.S)
    return re.sub(r'<[^>]+>', ' ', html)


DAN1 = dt.datetime(2026, 11, 12, 10, 0, tzinfo=UTC)
with mock.patch('django.utils.timezone.now', return_value=DAN1):
    # pravila
    r = Client().get('/kako-se-igra/')
    tekst = vidljiv_tekst(r.content.decode())
    proveri('"Kako se igra": strana radi', r.status_code == 200, r.status_code)
    pocetna = Client().get('/').content.decode()
    proveri('"Kako se igra": link sa pocetnog ekrana', '/kako-se-igra/' in pocetna)
    proveri('"Kako se igra": tekuca pravila (35 za tihu gresku, najvise 50 za budzet)',
            re.search(r'35', tekst) and re.search(r'50', tekst), '')
    en = Client(); en.cookies[JEZIK[0]] = JEZIK[1]
    ostaci = [m for m in re.findall(r'\S*[Ѐ-ӿ]+\S*', vidljiv_tekst(en.get('/kako-se-igra/').content.decode())) if 'Српски' not in m]
    proveri('"Kako se igra" na engleskom bez cirilice', not ostaci, ostaci[:8])

    # istorija
    a = Client()
    for _ in range(12):
        odigraj(a)
    broj_a, deo_a = istorija(a.get('/').content.decode())
    proveri('istorija: najvise 10 zavrsenih partija', broj_a == 10, broj_a)
    b = Client(); odigraj(b)   # prazna strana na "/" pokazuje igru dok je partija u toku, pa B nema nedovrsenu
    broj_b, _ = istorija(b.get('/').content.decode())
    proveri('istorija drugog igraca: samo njegova zavrsena partija', broj_b == 1, broj_b)
    if STRANA == 'prazan':
        from igra.models import Partija
        semena = list(Partija.objects.values_list('seme', flat=True))
    else:
        semena = [a.session['igra']['seme'], b.session['igra']['seme']]
    proveri('istorija ne otkriva seme', not any(s in deo_a for s in semena))

# statistika: 13 partija 12.11, jedna u 23:30 UTC 12.11 = 13.11 u Beogradu
with mock.patch('django.utils.timezone.now', return_value=dt.datetime(2026, 11, 12, 23, 30, tzinfo=UTC)):
    c = Client(); odigraj(c)
napravi_moderatora('mod1'); User.objects.create_user('obican', password=LOZ)
with mock.patch('django.utils.timezone.now', return_value=dt.datetime(2026, 11, 13, 10, 0, tzinfo=UTC)):
    proveri('statistika bez prijave nije dostupna', Client().get('/moderator/statistika/').status_code != 200)
    o = Client(); o.force_login(User.objects.get(username='obican'))
    proveri('statistika za nalog bez uloge nije dostupna', o.get('/moderator/statistika/').status_code != 200)
    m = Client(); m.post('/moderator/prijava/', {POLJA[0]: 'mod1', POLJA[1]: LOZ})
    r = m.get('/moderator/statistika/'); html = r.content.decode()
    proveri('moderator vidi statistiku', r.status_code == 200, r.status_code)
    proveri('statistika ima 7 dana', broj_dana(html) == 7, broj_dana(html))
    proveri('12.11: 13 zavrsenih partija', red_dana(html, dt.date(2026, 11, 12)) == 13, red_dana(html, dt.date(2026, 11, 12)))
    proveri('partija u 23:30 UTC broji se za 13.11 (Beograd)', red_dana(html, dt.date(2026, 11, 13)) == 1, red_dana(html, dt.date(2026, 11, 13)))
    proveri('dan bez partija je 0', red_dana(html, dt.date(2026, 11, 10)) == 0, red_dana(html, dt.date(2026, 11, 10)))

    # javni JSON
    r = Client().get('/api/rang-lista/')
    proveri('JSON: 200 i application/json', r.status_code == 200 and 'json' in r.get('Content-Type', ''), (r.status_code, r.get('Content-Type')))
    proveri('JSON: ne postavlja kolacice', not r.cookies, list(r.cookies))
    proveri('JSON: dozvoljen sa drugog sajta (CORS)', r.get('Access-Control-Allow-Origin') is not None, r.get('Access-Control-Allow-Origin'))
    proveri('JSON: kesira se kratko', 'max-age' in r.get('Cache-Control', ''), r.get('Cache-Control'))
    podaci = json.loads(r.content) if r.status_code == 200 else {}
    kljucevi = set()

    def skupi(x):
        if isinstance(x, dict):
            for k, v in x.items():
                kljucevi.add(k); skupi(v)
        elif isinstance(x, list):
            for v in x:
                skupi(v)
    skupi(podaci)
    proveri('JSON: bez internih kljuceva (seme, partija, id, token, sesija)',
            not kljucevi & {'seme', 'partija', 'id', 'pk', 'token', 'sesija', 'kod'}, sorted(kljucevi))
    tekst = json.dumps(podaci)
    proveri('JSON: bez semena partija', not any(s in tekst for s in semena))
    proveri('JSON: POST nije dozvoljen', Client().post('/api/rang-lista/').status_code in (403, 405), '')

deploy = ' '.join(open(f, encoding='utf-8', errors='replace').read() for f in glob.glob('deploy/**/*.conf', recursive=True))
proveri('nginx ogranicava broj zahteva za /api/rang-lista/', re.search(r'/api/[^{]*\{[^}]*limit_req', deploy, re.S) is not None)

print(json.dumps({'strana': STRANA, 'prolazi': sum(x['ok'] for x in rezultati), 'ukupno': len(rezultati), 'provere': rezultati},
                 ensure_ascii=False, indent=1))
