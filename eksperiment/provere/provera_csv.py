"""Nezavisna provera CSV izvoza za moderatora, ista za obe strane, na test bazi.

Imena idu kroz pravo cuvanje (kao kod igraca). CSV se cita sa ';' (srpski Excel) i sa ',' (engleski Excel):
celija koja pocinje sa = + - @ tab ili CR je formula koju Excel izvrsava.
Pokretanje: <venv strane>\\python provera_csv.py <projekat> <prazan|plugin>
"""
import csv, io, json, os, random, re, sys, tempfile

PROJEKAT, STRANA = sys.argv[1], sys.argv[2]
sys.path.insert(0, PROJEKAT); os.chdir(PROJEKAT)
os.environ['DJANGO_SETTINGS_MODULE'] = 'orkestrator.settings'
import django
django.setup()
from django.db import connection
from django.test import Client
from django.test.utils import setup_test_environment
setup_test_environment()
connection.settings_dict.setdefault('TEST', {})['NAME'] = os.path.join(tempfile.mkdtemp(), 'csv.sqlite3')
connection.creation.create_test_db(verbosity=0, keepdb=False, serialize=False)
from django.contrib.auth import get_user_model
from igra.models import Rezultat

User = get_user_model()
LOZ = 'Vrlo-Duga-Lozinka-2026!'
rng = random.Random(4)
rezultati = []
FORMULA = ('=', '+', '-', '@', '\t', '\r')


def proveri(oznaka, uslov, detalj=''):
    rezultati.append({'provera': oznaka, 'ok': bool(uslov), 'detalj': str(detalj)[:500]})


if STRANA == 'prazan':
    from igra import moderacija, parametri as p
    GRUPE = {'model': p.MODELI, 'nivo': p.NIVOI, 'kontekst': p.KONTEKSTI, 'podela': p.PODELE}
    POLJA = ('ime', 'lozinka')
    URL_GLAVNA, URL_DNEVNA = '/moderator/izvoz/?lista=glavna', '/moderator/izvoz/?lista=dnevna'

    def napravi_moderatora(ime):
        moderacija.dodaj_moderatora(None, ime, LOZ, LOZ)

    def odigraj(c, dnevna=False):
        c.get('/'); c.post('/dnevna/' if dnevna else '/nova/')
        for k in range(1, 9):
            c.post('/api/potez/', json.dumps(dict(izbori(), krug=k)), content_type='application/json')

    def sacuvaj(c, ime, dnevna=False):
        return c.post('/rezultat/', {'ime': ime})
else:
    from igra import motor, nalozi
    GRUPE = motor.GRUPE_IZBORA
    POLJA = ('username', 'password')
    URL_GLAVNA, URL_DNEVNA = '/moderator/izvoz/glavna.csv', '/moderator/izvoz/dnevna.csv'

    def napravi_moderatora(ime):
        nalozi.dodaj(None, ime, LOZ, glavni=True)
        u = User.objects.get(username=ime); u.nalog_moderatora.mora_promeniti = False; u.nalog_moderatora.save()

    def odigraj(c, dnevna=False):
        c.get('/dnevni/' if dnevna else '/')
        for k in range(1, 9):
            c.post('/dnevni/potez/' if dnevna else '/potez/', json.dumps({'krug': k, 'izbori': izbori()}), content_type='application/json')

    def sacuvaj(c, ime, dnevna=False):
        return c.post('/dnevni/sacuvaj/' if dnevna else '/sacuvaj/', json.dumps({'ime': ime}), content_type='application/json')


def izbori():
    return {g: rng.choice(sorted(o)) for g, o in GRUPE.items()}


IMENA = ['=1+1', '+1+1', '-1+1', '@SUM(1)', 'x,=1+1', 'x;=1+1', 'a"b', '\t=1+1', 'Петар Ђорђевић',
         'Igrac10', 'Igrac11', 'Igrac12']
sacuvana = []
for ime in IMENA:
    c = Client(); odigraj(c); r = sacuvaj(c, ime)
    if r.status_code in (200, 302) and Rezultat.objects.filter(ime=ime).exists():
        sacuvana.append(ime)
dnevni_igrac = Client(); odigraj(dnevni_igrac, dnevna=True); sacuvaj(dnevni_igrac, 'DnevniIgrac', dnevna=True)
napravi_moderatora('mod1')
User.objects.create_user('obican', password=LOZ)

# autorizacija
for oznaka, klijent in (('bez prijave', Client()), ('nalog bez uloge', None)):
    if klijent is None:
        klijent = Client(); klijent.force_login(User.objects.get(username='obican'))
    r = klijent.get(URL_GLAVNA)
    proveri(f'izvoz {oznaka}: nema datoteke', r.status_code != 200 or 'csv' not in r.get('Content-Type', ''), r.status_code)

mod = Client()
mod.post('/moderator/prijava/', {POLJA[0]: 'mod1', POLJA[1]: LOZ})
r = mod.get(URL_GLAVNA)
sirovo = r.content
proveri('moderator dobija CSV kao datoteku (text/csv, attachment)', r.status_code == 200 and 'text/csv' in r.get('Content-Type', '')
        and 'attachment' in r.get('Content-Disposition', ''), (r.status_code, r.get('Content-Type'), r.get('Content-Disposition')))
proveri('UTF-8 sa BOM (cirilica u Excel-u)', sirovo.startswith(b'\xef\xbb\xbf'), sirovo[:3])
tekst = sirovo.decode('utf-8-sig')
zaglavlje = tekst.splitlines()[0] if tekst else ''
proveri('separator ; (srpski Excel)', zaglavlje.count(';') >= 3, zaglavlje)
proveri('cirilicno ime tacno u datoteci', 'Петар Ђорђевић' in tekst if 'Петар Ђорђевић' in sacuvana else True)
redovi = list(csv.reader(io.StringIO(tekst), delimiter=';'))
proveri('cela lista, ne samo prvih 10', len(redovi) - 1 >= len(sacuvana), f'redova {len(redovi) - 1}, sacuvano {len(sacuvana)}')
proveri('dnevni rezultat nije u glavnoj listi', 'DnevniIgrac' not in tekst)
tajne = [x for x in re.findall(r'[0-9a-f]{32,}', tekst)]
proveri('bez semena, hesa ili tokena u datoteci', not tajne, tajne[:2])

# ubacivanje formule, citano kao srpski i kao engleski Excel
for sep, excel in ((';', 'srpski'), (',', 'engleski')):
    celije = [c for red in csv.reader(io.StringIO(tekst), delimiter=sep) for c in red]
    opasne = [c for c in celije if c[:1] in FORMULA and not re.fullmatch(r'-?\d+([.,]\d+)?', c)]
    proveri(f'nijedna celija ne pocinje formulom ({excel} Excel, separator {sep!r})', not opasne, opasne[:5])

r = mod.get(URL_DNEVNA)
d = r.content.decode('utf-8-sig', 'replace')
proveri('dnevni izvoz sadrzi dnevni, a ne glavne rezultate', r.status_code == 200 and 'DnevniIgrac' in d and 'Igrac10' not in d, r.status_code)

print(json.dumps({'strana': STRANA, 'sacuvana_imena': sacuvana, 'prolazi': sum(x['ok'] for x in rezultati), 'ukupno': len(rezultati),
                  'provere': rezultati}, ensure_ascii=False, indent=1))
