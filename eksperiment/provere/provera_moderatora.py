"""Nezavisna provera moderatora (autorizacija, brisanje, dnevnik), ista za obe strane, na test bazi.

Pokretanje: <venv strane>\\python provera_moderatora.py <projekat> <prazan|plugin>
"""
import json, os, random, re, sys, tempfile

PROJEKAT, STRANA = sys.argv[1], sys.argv[2]
sys.path.insert(0, PROJEKAT); os.chdir(PROJEKAT)
os.environ['DJANGO_SETTINGS_MODULE'] = 'orkestrator.settings'
import django
django.setup()
from django.db import connection
from django.test import Client
from django.test.utils import setup_test_environment
setup_test_environment()
connection.settings_dict.setdefault('TEST', {})['NAME'] = os.path.join(tempfile.mkdtemp(), 'mod.sqlite3')
connection.creation.create_test_db(verbosity=0, keepdb=False, serialize=False)
from django.contrib.auth import get_user_model
from igra.models import Rezultat

User = get_user_model()
LOZ = 'Vrlo-Duga-Lozinka-2026!'
rng = random.Random(3)
rezultati = []


def proveri(oznaka, uslov, detalj=''):
    rezultati.append({'provera': oznaka, 'ok': bool(uslov), 'detalj': str(detalj)[:400]})


if STRANA == 'prazan':
    from igra import moderacija, parametri as p
    from igra.models import Dogadjaj as Dnevnik, Partija
    GRUPE = {'model': p.MODELI, 'nivo': p.NIVOI, 'kontekst': p.KONTEKSTI, 'podela': p.PODELE}
    POLJA = ('ime', 'lozinka')

    def napravi_moderatora(ime):
        return moderacija.dodaj_moderatora(None, ime, LOZ, LOZ)

    def url_rezultat(r):
        return f'/moderator/rezultat/{r.pk}/obrisi/'

    def link_i_url(c):
        c.get('/kraj/')
        pa = Partija.objects.get(pk=c.session['partija_id'])
        return f'/partija/{pa.kod}/', f'/moderator/link/{pa.kod}/obrisi/'
else:
    from igra import motor, nalozi
    from igra.models import ZapisDnevnika as Dnevnik, DeljeniRezultat
    GRUPE = motor.GRUPE_IZBORA
    POLJA = ('username', 'password')

    def napravi_moderatora(ime):
        u = nalozi.dodaj(None, ime, LOZ, glavni=True)
        u = User.objects.get(username=ime)
        u.nalog_moderatora.mora_promeniti = False
        u.nalog_moderatora.save()
        return u

    def url_rezultat(r):
        return f'/moderator/rezultat/{r.pk}/'

    def link_i_url(c):
        url = c.post('/podeli/').json()['url']
        token = url.rstrip('/').rsplit('/', 1)[-1]
        red = DeljeniRezultat.objects.get(token=token)
        return f'/r/{token}/', f'/moderator/link/{red.pk}/'


def izbori():
    return {g: rng.choice(sorted(o)) for g, o in GRUPE.items()}


def odigraj(c):
    if STRANA == 'prazan':
        c.post('/nova/')
        for k in range(1, 9):
            c.post('/api/potez/', json.dumps(dict(izbori(), krug=k)), content_type='application/json')
    else:
        c.get('/')
        for k in range(1, 9):
            c.post('/potez/', json.dumps({'krug': k, 'izbori': izbori()}), content_type='application/json')


def sacuvaj(c, ime):
    if STRANA == 'prazan':
        return c.post('/rezultat/', {'ime': ime})
    return c.post('/sacuvaj/', json.dumps({'ime': ime}), content_type='application/json')


def prijavi(c, ime, loz, **dodatno):
    return c.post('/moderator/prijava/', {POLJA[0]: ime, POLJA[1]: loz, **dodatno})


# podaci: tri partije sacuvane, jedna podeljena, jedno ime sa HTML-om
igraci = {}
for ime in ('Prvi', 'Drugi', '<img src=x onerror=alert(1)>'[:20]):
    c = Client(); odigraj(c); r = sacuvaj(c, ime)
    igraci[ime] = c
assert Rezultat.objects.count() == 3, Rezultat.objects.count()
javni_link, url_brisanja_linka = link_i_url(igraci['Drugi'])
meta = Rezultat.objects.get(ime='Prvi')
napravi_moderatora('mod1')
obican = User.objects.create_user('obican', password=LOZ)

STRANE_MODERATORA = ['/moderator/', '/moderator/dnevnik/', url_rezultat(meta), url_brisanja_linka, '/moderator/nalozi/']

# 1. bez prijave
anon = Client()
kodovi = {u: anon.get(u).status_code for u in STRANE_MODERATORA}
proveri('bez prijave: nijedna strana moderatora se ne prikazuje (200)', all(k != 200 for k in kodovi.values()), kodovi)
r = anon.post(url_rezultat(meta))
proveri('bez prijave: POST brisanja ne brise', Rezultat.objects.filter(pk=meta.pk).exists(), r.status_code)

# 2. prijavljen korisnik koji nije moderator
c = Client(); c.force_login(obican)
kodovi = {u: c.get(u).status_code for u in STRANE_MODERATORA}
proveri('nalog bez uloge moderatora: nema pristupa', all(k != 200 for k in kodovi.values()), kodovi)
c.post(url_rezultat(meta)); c.post(url_brisanja_linka)
proveri('nalog bez uloge: brisanje ne prolazi', Rezultat.objects.filter(pk=meta.pk).exists() and Client().get(javni_link).status_code == 200)

# 3. prijava: nabrajanje naloga i preusmeravanje
r1 = prijavi(Client(), 'mod1', 'pogresna-lozinka-123'); r2 = prijavi(Client(), 'nepostoji', 'pogresna-lozinka-123')
cisto = lambda t: re.sub(r'value="[^"]*"', '', re.sub(r'csrfmiddlewaretoken" value="[^"]*"', '', t)).replace('nepostoji', 'mod1')
proveri('pogresna lozinka i nepostojece ime daju isti odgovor', r1.status_code == r2.status_code and cisto(r1.content.decode()) == cisto(r2.content.decode()),
        (r1.status_code, r2.status_code))
r = prijavi(Client(), 'mod1', LOZ, next='https://zlo.example/')
proveri('posle prijave nema preusmeravanja van sajta', 'zlo.example' not in r.get('Location', ''), (r.status_code, r.get('Location')))
mod = Client(); stari_kljuc = (mod.get('/'), mod.session.session_key)[1]
r = prijavi(mod, 'mod1', LOZ)
proveri('prijava moderatora uspeva', r.status_code == 302 and mod.get('/moderator/').status_code == 200, r.status_code)
proveri('kljuc sesije se menja pri prijavi (fiksacija)', mod.session.session_key != stari_kljuc)
proveri('lozinka u bazi je hes', User.objects.get(username='mod1').password.split('$')[0] in ('pbkdf2_sha256', 'argon2', 'bcrypt_sha256', 'scrypt'),
        User.objects.get(username='mod1').password.split('$')[0])
r = mod.get('/moderator/')
proveri('strana moderatora se ne kesira', any(x in r.get('Cache-Control', '') for x in ('no-cache', 'no-store', 'private', 'max-age=0')), r.get('Cache-Control'))
proveri('ime sa HTML-om u panelu moderatora je izbegnuto', '<img src=x' not in r.content.decode(), '')

# 4. brisanje: GET ne brise, CSRF, pa pravo brisanje
mod.get(url_rezultat(meta))
proveri('GET na adresu brisanja ne brise', Rezultat.objects.filter(pk=meta.pk).exists())
strogi = Client(enforce_csrf_checks=True); prijavi_strogo = strogi.get('/moderator/prijava/')
strogi.force_login(User.objects.get(username='mod1'))
r = strogi.post(url_rezultat(meta))
proveri('brisanje bez CSRF tokena odbijeno', r.status_code == 403 and Rezultat.objects.filter(pk=meta.pk).exists(), r.status_code)
pre = Dnevnik.objects.count()
r = mod.post(url_rezultat(meta))
proveri('moderator brise rezultat', not Rezultat.objects.filter(pk=meta.pk).exists(), r.status_code)
proveri('rezultat nestao sa rang liste', 'Prvi' not in Client().get('/').content.decode())
r = mod.post(url_brisanja_linka)
proveri('moderator brise link; link daje 404', Client().get(javni_link).status_code == 404, r.status_code)
proveri('nepostojeci id: 404, ne 500', mod.post(url_rezultat(type('x', (), {'pk': 999999})())).status_code in (302, 404), '')
dnevnik = mod.get('/moderator/dnevnik/').content.decode()
proveri('dnevnik: oba brisanja, ko i kada', Dnevnik.objects.count() >= pre + 2 and 'mod1' in dnevnik and 'Prvi' in dnevnik
        and re.search(r'\d{1,2}[.:]\d{2}', dnevnik), f'zapisa {Dnevnik.objects.count() - pre}')

# 5. obrisana partija se ne vraca
r = sacuvaj(igraci['Prvi'], 'PrviOpet')
proveri('obrisan rezultat ne moze ponovo da se sacuva', not Rezultat.objects.filter(ime='PrviOpet').exists(), r.status_code)

# 6. iskljucen moderator gubi pristup u otvorenoj sesiji
u = User.objects.get(username='mod1'); u.is_active = False; u.save()
proveri('iskljucen moderator odmah gubi pristup', mod.get('/moderator/').status_code != 200)
u.is_active = True; u.save()

# 7. dnevnik i u bazi (dubinska zastita; zahtev to ne trazi izricito)
try:
    from django.db import transaction
    with transaction.atomic():
        izmenjeno = Dnevnik.objects.all().update(**({'ime_igraca': 'lazno'} if STRANA == 'prazan' else {'radnja': Dnevnik.objects.first().radnja}))
    zasticen = False
except Exception as e:
    zasticen = True; izmenjeno = type(e).__name__
proveri('[dubinska] dnevnik se ne moze izmeniti ni direktno u bazi', zasticen, izmenjeno)

print(json.dumps({'strana': STRANA, 'prolazi': sum(x['ok'] for x in rezultati), 'ukupno': len(rezultati), 'provere': rezultati},
                 ensure_ascii=False, indent=1))
