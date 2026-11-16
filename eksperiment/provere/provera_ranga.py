"""Nezavisna provera rang liste, ista za obe strane. Pise se posle izrade, crnom kutijom kroz HTTP.

Pokretanje: <venv strane>\\python provera_ranga.py <projekat> <prazan|plugin>
Radi nad test bazom u memoriji; prava baza strane se ne dira.
"""
import json, os, random, re, sys

PROJEKAT, STRANA = sys.argv[1], sys.argv[2]
sys.path.insert(0, PROJEKAT)
os.chdir(PROJEKAT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'orkestrator.settings')
import django
django.setup()
from django.db import connection
from django.test import Client
from django.test.utils import setup_test_environment
setup_test_environment()
import tempfile
connection.settings_dict.setdefault('TEST', {})['NAME'] = os.path.join(tempfile.mkdtemp(), 'provera.sqlite3')
connection.creation.create_test_db(verbosity=0, keepdb=False, serialize=False)
from igra.models import Rezultat

if STRANA == 'prazan':
    from igra import parametri as p
    GRUPE = {'model': p.MODELI, 'nivo': p.NIVOI, 'kontekst': p.KONTEKSTI, 'podela': p.PODELE}
    KRUGOVA, IME_MAKS = p.BROJ_KRUGOVA, p.DUZINA_IMENA_MAX
else:
    from igra import motor, parametri as p
    GRUPE = motor.GRUPE_IZBORA
    KRUGOVA, IME_MAKS = p.KRUGOVA, p.IME_MAKS

rng = random.Random(7)


def izbori():
    return {g: rng.choice(sorted(o)) for g, o in GRUPE.items()}


def nova(c):
    if STRANA == 'prazan':
        return c.post('/nova/')
    if c.cookies.get('sessionid') is None:
        return c.get('/')
    return c.post('/nova/')


def potez(c, krug):
    if STRANA == 'prazan':
        telo = dict(izbori(), krug=krug)
        return c.post('/api/potez/', json.dumps(telo), content_type='application/json')
    return c.post('/potez/', json.dumps({'krug': krug, 'izbori': izbori()}), content_type='application/json')


def odigraj(c, do=None):
    r = nova(c)
    assert r.status_code in (200, 302), r.status_code
    for k in range(1, (do or KRUGOVA) + 1):
        r = potez(c, k)
        assert r.status_code == 200, (k, r.status_code, r.content[:200])


def sacuvaj(c, ime, visak=None):
    if STRANA == 'prazan':
        polja = {} if ime is None else {'ime': ime}
        polja.update(visak or {})
        return c.post('/rezultat/', polja)
    telo = {} if ime is None else {'ime': ime}
    telo.update(visak or {})
    return c.post('/sacuvaj/', json.dumps(telo), content_type='application/json')


rezultati = []


def proveri(oznaka, uslov, detalj=''):
    rezultati.append((oznaka, bool(uslov), detalj))


def broj():
    return Rezultat.objects.count()


# 1. cuvanje pre kraja partije
c = Client(); odigraj(c, do=3); n = broj()
r = sacuvaj(c, 'Rani')
proveri('cuvanje pre kraja partije odbijeno', 400 <= r.status_code < 500 and broj() == n, r.status_code)

# 2. falsifikovani poeni i ocena
c = Client(); odigraj(c); n = broj()
r = sacuvaj(c, 'Lazni', {'poeni': '999', 'ocena': 'Majstor'})
red = Rezultat.objects.order_by('-id').first() if broj() > n else None
proveri('poeni i ocena od klijenta ne ulaze u bazu',
        red is None or (red.poeni != 999 and red.ocena != 'Majstor'), f'{r.status_code}, red={red and (red.poeni, red.ocena)}')

# 3-6. neispravna imena, na zavrsenoj partiji; nijedno ne sme da napravi red ni 500
for oznaka, ime in [('prazno ime', ''), ('samo razmaci', '   '), ('bez polja ime', None),
                    ('predugo ime (5000)', 'a' * 5000), (f'ime od {IME_MAKS + 1} znakova', 'b' * (IME_MAKS + 1)),
                    ('NUL znak', 'a\x00b'), ('obrtanje smera U+202E', 'abc‮def'), ('nevidljivi U+200B', 'a​b'),
                    ('prelom reda', 'a\nb'), ('tab', 'a\tb')]:
    c = Client(); odigraj(c); n = broj()
    try:
        r = sacuvaj(c, ime); kod = r.status_code
    except Exception as e:  # izuzetak kroz test klijent je 500
        kod = f'izuzetak {type(e).__name__}'
    sacuvano = Rezultat.objects.order_by('-id').first().ime if broj() > n else None
    odbijeno = isinstance(kod, int) and 400 <= kod < 500 and broj() == n
    # prelom i tab smeju i da se pretvore u razmak: bitno je da kontrolni znak ne stigne u bazu
    ocisceno = ime in ('a\nb', 'a\tb') and sacuvano is not None and not any(z in sacuvano for z in '\n\t\r')
    proveri(f'odbijeno ili ocisceno: {oznaka}', odbijeno or ocisceno,
            f'{kod}, sacuvano={sacuvano!r}' if sacuvano is not None else kod)

# 6b. zamke koje je nasla kontrola plugina, proverene na obe strane
for oznaka, ime in [('nevidljivo ime (hangul popunjivac U+3164)', 'ㅤㅤㅤ'),
                    ('naslagani znaci (a + 12 x U+0301)', 'a' + '́' * 12)]:
    c = Client(); odigraj(c); n = broj()
    r = sacuvaj(c, ime)
    proveri(f'[nalaz plugina] odbijeno: {oznaka}', broj() == n and 400 <= r.status_code < 500, r.status_code)

# 7. granica: tacno najduze ime i cirilica prolaze
c = Client(); odigraj(c); n = broj()
r = sacuvaj(c, 'Ж' * IME_MAKS)
proveri(f'ime od tacno {IME_MAKS} cirilicnih znakova prihvaceno', broj() == n + 1, r.status_code)

# 8. XSS u imenu
c = Client(); odigraj(c); n = broj()
zlo = '<img src=x onerror=alert(1)>'[:IME_MAKS]
r = sacuvaj(c, zlo)
strana = Client().get('/').content.decode('utf-8')
if broj() > n:
    proveri('XSS ime prikazano izbegnuto', '<img src=x' not in strana and '&lt;img' in strana)
else:
    proveri('XSS ime: odbijeno pri cuvanju (nije prikazano)', True, r.status_code)

# 9. dvostruko cuvanje iste partije
c = Client(); odigraj(c); n = broj()
r1 = sacuvaj(c, 'Dvaput'); r2 = sacuvaj(c, 'Dvaput2')
proveri('drugo cuvanje iste partije odbijeno', broj() == n + 1 and 400 <= r2.status_code < 500, (r1.status_code, r2.status_code))

# 10. stara partija posle nove igre
c = Client(); odigraj(c); nova(c); n = broj()
r = sacuvaj(c, 'Stara')
proveri('posle "Nova igra" stara partija se ne cuva', broj() == n and 400 <= r.status_code < 500, r.status_code)

# 11. CSRF
c = Client(enforce_csrf_checks=True); odigraj_csrf = True
try:
    # potez i nova traze token; uzmi ga iz kolacica kao sto radi stranica
    c.get('/')
    tok = c.cookies.get('csrftoken')
    zaglavlje = {'HTTP_X_CSRFTOKEN': tok.value} if tok else {}
    if STRANA == 'prazan':
        c.post('/nova/', {'csrfmiddlewaretoken': tok.value if tok else ''})
    for k in range(1, KRUGOVA + 1):
        if STRANA == 'prazan':
            c.post('/api/potez/', json.dumps(dict(izbori(), krug=k)), content_type='application/json', **zaglavlje)
        else:
            c.post('/potez/', json.dumps({'krug': k, 'izbori': izbori()}), content_type='application/json', **zaglavlje)
    n = broj()
    r = sacuvaj(c, 'BezTokena')
    proveri('cuvanje bez CSRF tokena odbijeno (403)', r.status_code == 403 and broj() == n, r.status_code)
except AssertionError as e:
    proveri('cuvanje bez CSRF tokena odbijeno (403)', False, f'priprema pala: {e}')

# 12. losa tela zahteva
c = Client(); odigraj(c); n = broj()
if STRANA == 'prazan':
    r = c.post('/rezultat/', 'nije forma', content_type='text/plain')
else:
    r = c.post('/sacuvaj/', '{"ime":', content_type='application/json')
proveri('neispravno telo zahteva daje 4xx, ne 500', 400 <= r.status_code < 500 and broj() == n, r.status_code)
r = c.get('/rezultat/' if STRANA == 'prazan' else '/sacuvaj/')
proveri('GET na adresu cuvanja ne pise (405)', r.status_code == 405, r.status_code)

# 13. top 10: 12 partija sa razlicitim ishodima, prikaz tacno 10, pravi redosled
Rezultat.objects.all().delete()
for i in range(12):
    c = Client(); odigraj(c)
    r = sacuvaj(c, f'Igrac{i:02d}')
    assert broj() == i + 1, (i, r.status_code, r.content[:200])
strana = Client().get('/').content.decode('utf-8')
prikazani = sorted({m for m in re.findall(r'Igrac\d\d', strana)}, key=strana.index)
redosled = [x.ime for x in sorted(Rezultat.objects.all(), key=lambda x: (-x.poeni, x.sacuvan, x.pk))]
proveri('pocetni ekran nove posete prikazuje tacno 10', len(prikazani) == 10, len(prikazani))
proveri('redosled: vise poena iznad, kod jednakih raniji', prikazani == redosled[:10],
        f'prikaz={prikazani} ocekivano={redosled[:10]} poeni={[x.poeni for x in sorted(Rezultat.objects.all(), key=lambda x: (-x.poeni, x.sacuvan, x.pk))]}')
proveri('datum u obliku dd.mm.gggg', re.search(r'\b\d{2}\.\d{2}\.\d{4}\b', strana) is not None)
proveri('ocena vidljiva u listi', any(x.ocena in strana for x in Rezultat.objects.all()))

# 14. tajne partije ne idu u prikaz
if STRANA == 'prazan':
    tajne = list(Rezultat.objects.values_list('partija__seme', flat=True))
else:
    tajne = list(Rezultat.objects.values_list('partija', flat=True))
proveri('seme ni oznaka partije nisu u pocetnoj strani', not any(t in strana for t in tajne))

print(json.dumps({'strana': STRANA, 'prolazi': sum(ok for _, ok, _ in rezultati), 'ukupno': len(rezultati),
                  'provere': [{'provera': o, 'ok': ok, 'detalj': str(d)} for o, ok, d in rezultati]}, ensure_ascii=False, indent=1))
