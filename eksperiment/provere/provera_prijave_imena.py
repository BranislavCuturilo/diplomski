"""Nezavisna provera prijave neprikladnog imena, ista za obe strane, na test bazi.

Pokretanje: <venv strane>\\python provera_prijave_imena.py <projekat> <prazan|plugin>
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
connection.settings_dict.setdefault('TEST', {})['NAME'] = os.path.join(tempfile.mkdtemp(), 'pr.sqlite3')
connection.creation.create_test_db(verbosity=0, keepdb=False, serialize=False)
from django.contrib.auth import get_user_model
from igra.models import Rezultat, PrijavaImena

User = get_user_model()
LOZ = 'Vrlo-Duga-Lozinka-2026!'
rng = random.Random(6)
rezultati = []


def proveri(oznaka, uslov, detalj=''):
    rezultati.append({'provera': oznaka, 'ok': bool(uslov), 'detalj': str(detalj)[:400]})


if STRANA == 'prazan':
    from igra import moderacija, parametri as p
    GRUPE = {'model': p.MODELI, 'nivo': p.NIVOI, 'kontekst': p.KONTEKSTI, 'podela': p.PODELE}
    POLJA, STRANA_PRIJAVA = ('ime', 'lozinka'), '/moderator/prijavljena-imena/'

    def napravi_moderatora(ime):
        moderacija.dodaj_moderatora(None, ime, LOZ, LOZ)

    def odigraj(c):
        c.get('/'); c.post('/nova/')
        for k in range(1, 9):
            c.post('/api/potez/', json.dumps(dict(izbori(), krug=k)), content_type='application/json')

    def sacuvaj(c, ime):
        return c.post('/rezultat/', {'ime': ime})

    def prijavi(c, r, metod='post', pk=None):
        put = '/rezultat/%d/prijavi/' % (pk if pk is not None else r.pk)
        return c.get(put) if metod == 'get' else c.post(put)

    def zadrzi(m, r):
        return m.post('/moderator/rezultat/%d/zadrzi/' % r.pk)

    def obrisi(m, r):
        return m.post('/moderator/rezultat/%d/obrisi/' % r.pk)
else:
    from igra import motor, nalozi, views
    GRUPE = motor.GRUPE_IZBORA
    POLJA, STRANA_PRIJAVA = ('username', 'password'), '/moderator/'

    def napravi_moderatora(ime):
        nalozi.dodaj(None, ime, LOZ, glavni=True)
        u = User.objects.get(username=ime); u.nalog_moderatora.mora_promeniti = False; u.nalog_moderatora.save()

    def odigraj(c):
        c.get('/')
        for k in range(1, 9):
            c.post('/potez/', json.dumps({'krug': k, 'izbori': izbori()}), content_type='application/json')

    def sacuvaj(c, ime):
        return c.post('/sacuvaj/', json.dumps({'ime': ime}), content_type='application/json')

    def prijavi(c, r, metod='post', pk=None):
        if c.session.get('igra') is None:
            c.get('/')                      # igrac sa partijom, kao svaki posetilac strane
        oznaka = views._oznaka_reda(r) if r is not None else 'x' * 43
        if metod == 'get':
            return c.get('/prijavi/')
        return c.post('/prijavi/', json.dumps({'red': oznaka}), content_type='application/json')

    def zadrzi(m, r):
        return m.post('/moderator/rezultat/%d/ostavi/' % r.pk)

    def obrisi(m, r):
        return m.post('/moderator/rezultat/%d/' % r.pk)


def deo_prijava(html):
    """Samo deo strane sa prijavljenim imenima: plugin na istoj strani prikazuje i celu rang listu."""
    if STRANA == 'prazan':
        return html
    i = html.find('id="mod-prijavljena"')
    j = html.find('<section', i + 1)
    return html[i:j if j > 0 else None] if i >= 0 else ''


def izbori():
    return {g: rng.choice(sorted(o)) for g, o in GRUPE.items()}


def broj(r):
    return PrijavaImena.objects.filter(rezultat=r).count()


def otvorene(r):
    """Prijave o kojima moderator jos nije odlucio, po definiciji strane (prazna oznacava resene, plugin ih brise)."""
    upit = PrijavaImena.objects.filter(rezultat=r)
    return upit.filter(resena=False).count() if STRANA == 'prazan' else upit.count()


IMENA = ['<b>Zlo</b>', 'Ruzno'] + ['Igrac%02d' % i for i in range(11)]
for ime in IMENA:
    c = Client(); odigraj(c); sacuvaj(c, ime)
po_rangu = sorted(Rezultat.objects.all(), key=lambda x: (-x.poeni, x.sacuvan, x.pk))
na_listi, van_liste = po_rangu[:10], po_rangu[10:]
zlo = next((r for r in na_listi if r.ime == '<b>Zlo</b>'), na_listi[0])
ruzno = next((r for r in na_listi if r.ime == 'Ruzno' and r != zlo), na_listi[1])
treci = next(r for r in na_listi if r not in (zlo, ruzno))
napravi_moderatora('mod1')
User.objects.create_user('obican', password=LOZ)

# igrac prijavljuje
igrac = Client()
pre = broj(zlo)
prijavi(igrac, zlo, metod='get')
proveri('GET na adresu prijave ne belezi prijavu', broj(zlo) == pre)
strogi = Client(enforce_csrf_checks=True); strogi.get('/')
r = prijavi(strogi, zlo)
proveri('prijava bez CSRF tokena odbijena', r.status_code == 403 and broj(zlo) == pre, r.status_code)
r = prijavi(igrac, zlo)
proveri('igrac prijavljuje ime sa liste', broj(zlo) >= 1, r.status_code)
javna = Client().get('/').content.decode()
proveri('prijava ne sakriva i ne brise ime', Rezultat.objects.filter(pk=zlo.pk).exists() and ('Zlo' in javna), '')
r = prijavi(Client(), van_liste[0] if van_liste else None)
proveri('ime van prvih 10 ne moze da se prijavi', r.status_code >= 400 and broj(van_liste[0]) == 0 if van_liste else True, r.status_code)
r = prijavi(Client(), None, pk=999999) if STRANA == 'prazan' else prijavi(Client(), None)
proveri('nepostojeci red: 4xx, ne 500', 400 <= r.status_code < 500, r.status_code)

# poplava
for _ in range(50):
    prijavi(igrac, zlo)
proveri('50 prijava iz iste sesije: najvise 1 zapis te sesije', broj(zlo) <= 1 if STRANA == 'prazan' else
        PrijavaImena.objects.filter(rezultat=zlo).values('sesija').distinct().count() == broj(zlo), broj(zlo))
for _ in range(150):
    prijavi(Client(), ruzno)
proveri('150 prijava iz 150 sesija: broj zapisa ogranicen', broj(ruzno) <= 100, broj(ruzno))

# moderator
for oznaka, kl in (('bez prijave', Client()), ('nalog bez uloge', None)):
    if kl is None:
        kl = Client(); kl.force_login(User.objects.get(username='obican'))
    r = kl.get(STRANA_PRIJAVA)
    proveri(f'spisak prijava {oznaka}: nije dostupan', r.status_code != 200, r.status_code)
mod = Client(); mod.post('/moderator/prijava/', {POLJA[0]: 'mod1', POLJA[1]: LOZ})
strana = deo_prijava(mod.get(STRANA_PRIJAVA).content.decode())
proveri('moderator vidi prijavljena imena', 'Ruzno' in strana and 'Zlo' in strana, strana[:120])
proveri('ime sa HTML-om u spisku je izbegnuto', '<b>Zlo</b>' not in strana)
proveri('spisak ne otkriva sesiju prijavioca', igrac.session.session_key not in strana)

# odluke
r = zadrzi(mod, zlo)
prijavi(Client(), zlo)
strana = deo_prijava(mod.get(STRANA_PRIJAVA).content.decode())
proveri('"zadrzi": ime nestaje sa spiska i nova prijava ga ne vraca', 'Zlo' not in strana and otvorene(zlo) == 0
        and Rezultat.objects.filter(pk=zlo.pk).exists(), (r.status_code, otvorene(zlo)))
r = obrisi(mod, ruzno)
proveri('"obrisi": rezultat i njegove prijave nestaju', not Rezultat.objects.filter(pk=ruzno.pk).exists() and broj(ruzno) == 0, r.status_code)
r = prijavi(Client(), ruzno)
proveri('prijava obrisanog rezultata: 4xx, nista se ne belezi', r.status_code >= 400 and broj(ruzno) == 0, r.status_code)
dnevnik = mod.get('/moderator/dnevnik/').content.decode()
proveri('dnevnik belezi obe odluke moderatora', 'Ruzno' in dnevnik and 'Zlo' in dnevnik, '')
r = Client().post(('/moderator/rezultat/%d/zadrzi/' if STRANA == 'prazan' else '/moderator/rezultat/%d/ostavi/') % treci.pk)
proveri('odluka bez prijave moderatora odbijena', r.status_code in (302, 403) and Rezultat.objects.filter(pk=treci.pk).exists(), r.status_code)

print(json.dumps({'strana': STRANA, 'prolazi': sum(x['ok'] for x in rezultati), 'ukupno': len(rezultati), 'provere': rezultati},
                 ensure_ascii=False, indent=1))
