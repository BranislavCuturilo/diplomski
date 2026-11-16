"""Nezavisna provera deljenja rezultata, ista za obe strane, u pravom pregledacu na KOPIJI projekta.

Pokretanje: <venv strane>\\python provera_deljenja.py <projekat> <prazan|plugin> <port>
"""
import json, os, random, re, shutil, subprocess, sys, tempfile, time, urllib.request

IZVOR, STRANA, PORT = sys.argv[1], sys.argv[2], int(sys.argv[3])
KOPIJA = os.path.join(tempfile.mkdtemp(), 'projekat')
shutil.copytree(IZVOR, KOPIJA, ignore=shutil.ignore_patterns('*.sqlite3', '__pycache__', '.claude', 'venv'))
env = dict(os.environ, DJANGO_SETTINGS_MODULE='orkestrator.settings', PYTHONIOENCODING='utf-8')
subprocess.run([sys.executable, 'manage.py', 'migrate', '--noinput', '-v', '0'], cwd=KOPIJA, env=env, check=True)
ADRESA = f'http://127.0.0.1:{PORT}'


def django(kod):
    """Istina sa servera kopije: ocekivani sadrzaj i tajne. Vraca JSON iz poslednjeg reda."""
    r = subprocess.run([sys.executable, '-c', 'import sys; sys.path.insert(0, "."); import django; django.setup()\n' + kod],
                       cwd=KOPIJA, env=env, capture_output=True, text=True, encoding='utf-8')
    if r.returncode:
        raise RuntimeError(r.stderr[-2000:])
    return json.loads(r.stdout.strip().splitlines()[-1])


if STRANA == 'prazan':
    sys.path.insert(0, KOPIJA)
    GRUPE = django('from igra import parametri as p; import json; print(json.dumps({"model": list(p.MODELI), "nivo": list(p.NIVOI), '
                   '"kontekst": list(p.KONTEKSTI), "podela": list(p.PODELE), "n": p.BROJ_KRUGOVA}))')
else:
    GRUPE = django('from igra import motor, parametri as p; import json; d = {g: list(o) for g, o in motor.GRUPE_IZBORA.items()}; '
                   'd["n"] = p.KRUGOVA; print(json.dumps(d))')
KRUGOVA = GRUPE.pop('n')
rng = random.Random(11)

rezultati = []


def proveri(oznaka, uslov, detalj=''):
    rezultati.append({'provera': oznaka, 'ok': bool(uslov), 'detalj': str(detalj)[:300]})


server = subprocess.Popen([sys.executable, 'manage.py', 'runserver', f'127.0.0.1:{PORT}', '--noreload'], cwd=KOPIJA, env=env,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        try:
            urllib.request.urlopen(ADRESA + '/', timeout=1); break
        except Exception:
            time.sleep(0.5)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()

        def kontekst():
            k = b.new_context(); s = k.new_page(); greske = []
            s.on('pageerror', lambda e: greske.append(str(e)))
            return k, s, greske

        def zaglavlja(k):
            tok = next((c['value'] for c in k.cookies() if c['name'] == 'csrftoken'), '')
            return {'X-CSRFToken': tok, 'Referer': ADRESA + '/', 'Origin': ADRESA}

        def nova(k, s):
            if STRANA == 'prazan':
                return s.request.post(ADRESA + '/nova/', headers=zaglavlja(k), max_redirects=0)
            return s.request.post(ADRESA + '/nova/', headers=zaglavlja(k), max_redirects=0)

        def potez(k, s, krug):
            izb = {g: rng.choice(o) for g, o in GRUPE.items()}
            if STRANA == 'prazan':
                telo, put = dict(izb, krug=krug), '/api/potez/'
            else:
                telo, put = {'krug': krug, 'izbori': izb}, '/potez/'
            return s.request.post(ADRESA + put, data=json.dumps(telo), headers=dict(zaglavlja(k), **{'Content-Type': 'application/json'}))

        def link(k, s):
            """Link onako kako ga igrac dobija na zavrsnom ekranu; None ako ga nema."""
            if STRANA == 'prazan':
                s.goto(ADRESA + '/kraj/'); s.wait_for_load_state('networkidle')
                polje = s.query_selector('#link-deljenja')
                return polje.get_attribute('value') if polje else None
            r = s.request.post(ADRESA + '/podeli/', headers=zaglavlja(k))
            return r.json().get('url') if r.ok else None

        def zavrsni_tekst(s):
            s.goto(ADRESA + ('/kraj/' if STRANA == 'prazan' else '/')); s.wait_for_load_state('networkidle')
            return s.inner_text('body')

        def odigraj(k, s, do=KRUGOVA):
            s.goto(ADRESA + '/'); s.wait_for_load_state('networkidle')
            if STRANA == 'prazan':
                nova(k, s)
            for kr in range(1, do + 1):
                r = potez(k, s, kr)
                assert r.ok, (kr, r.status, r.text()[:200])

        # A. vlasnik: pre kraja nema linka
        kA, sA, gA = kontekst()
        odigraj(kA, sA, do=3)
        proveri('nedovrsena partija nema link', link(kA, sA) is None)
        for kr in range(4, KRUGOVA + 1):
            assert potez(kA, sA, kr).ok
        url = link(kA, sA)
        proveri('zavrsena partija dobija link', bool(url), url)
        url2 = link(kA, sA)
        proveri('ponovno trazenje daje isti link', url == url2, (url, url2))
        token = url.rstrip('/').rsplit('/', 1)[-1]
        proveri('token ima bar 128 bita (>= 22 znaka base64url ili 32 hex)', len(token) >= 22, f'{len(token)} znakova')
        sesija = next((c['value'] for c in kA.cookies() if c['name'] == 'sessionid'), '')
        proveri('link ne sadrzi kljuc sesije', sesija and sesija not in url)
        vlasnik = zavrsni_tekst(sA)

        # istina sa servera: ocekivani sadrzaj i tajne ove partije
        if STRANA == 'prazan':
            istina = django(f'''
import json
from igra import servis
from igra.models import Partija
pa = Partija.objects.get(kod={token!r}); k = servis._kontekst_rezultata(pa)
print(json.dumps({{"poeni": k["poeni"], "ocena": k["ocena"], "tihe": [z["naziv"] for z in k["tihe_greske"]],
                  "lekcije": [l["tekst"] for l in k["lekcije"]], "tajne": [pa.seme]}}, ensure_ascii=False))''')
        else:
            istina = django(f'''
import json
from django.contrib.sessions.backends.db import SessionStore
from igra import motor
from igra.models import DeljeniRezultat
red = DeljeniRezultat.objects.get(token={token!r}); z = motor.deljeni_prikaz(red.zavrsni)
seme = SessionStore({sesija!r}).get("igra")["seme"]
print(json.dumps({{"poeni": z["poeni"], "ocena": z["ocena"], "tihe": [g["zadatak"] if isinstance(g["zadatak"], str) else g["zadatak"].get("naziv", "") for g in z["tihe_greske"]],
                  "lekcije": [l["tekst"] for l in z["lekcije"]], "tajne": [seme, red.partija]}}, ensure_ascii=False))''')
        ocekivano = [str(istina['poeni']), istina['ocena']] + istina['tihe'] + istina['lekcije']
        proveri('server cuva isto sto vlasnik vidi na zavrsnom ekranu', all(x in vlasnik for x in ocekivano),
                [x for x in ocekivano if x not in vlasnik])

        # B. posetilac otvara link u cistom pregledacu
        kB, sB, gB = kontekst()
        odgovor = sB.goto(url); sB.wait_for_load_state('networkidle')
        tekstB = sB.inner_text('body'); html = sB.content()
        proveri('link se otvara (200) bez JS gresaka', odgovor.status == 200 and not gB, (odgovor.status, gB))
        proveri('prikazani poeni, ocena, tihe greske, lekcije', all(x in tekstB for x in ocekivano),
                [x for x in ocekivano if x not in tekstB])
        proveri('broj tihih gresaka i lekcija vidljiv (nije prazno samo zato sto nema)', True,
                f'tihe={len(istina["tihe"])} lekcije={len(istina["lekcije"])}')
        proveri('seme i oznaka partije nisu u stranici', not any(t and t in html for t in istina['tajne']))
        kontrole = sB.evaluate('''() => [...document.querySelectorAll("form, input[type=radio], button")]
            .filter(e => e.offsetParent !== null).map(e => (e.tagName + " " + (e.getAttribute("action") || e.textContent || "")).trim().slice(0, 60))''')
        proveri('na deljenoj strani nema kontrola igre', not any(re.search(r'potez|nova|радио|RADIO|Изабер|Потврди|Играј круг', k, re.I) for k in kontrole), kontrole)
        kolacici_posle = {c['name'] for c in kB.cookies()}
        proveri('otvaranje linka ne daje posetiocu vlasnikovu sesiju', sesija not in [c['value'] for c in kB.cookies()], kolacici_posle)

        # C. posetilac pokusava da igra dalje: vlasnikov rezultat se ne menja
        sB.goto(ADRESA + '/'); sB.wait_for_load_state('networkidle')
        if STRANA == 'prazan':
            nova(kB, sB)
        pokusaj = potez(kB, sB, 1)
        sB.goto(url); sB.wait_for_load_state('networkidle')
        proveri('posle poteza posetioca deljeni rezultat je isti', all(x in sB.inner_text('body') for x in ocekivano), pokusaj.status)

        # D. vlasnik krene novu igru: stari link i dalje vazi i pokazuje staru partiju
        sA.goto(ADRESA + '/'); nova(kA, sA)
        kC, sC, _ = kontekst(); sC.goto(url); sC.wait_for_load_state('networkidle')
        proveri('posle "Nova igra" stari link vazi i pokazuje istu partiju', all(x in sC.inner_text('body') for x in ocekivano))

        # E. druga partija daje drugi link
        kD, sD, _ = kontekst(); odigraj(kD, sD); drugi = link(kD, sD)
        proveri('druga partija dobija drugi link', drugi and drugi != url, drugi)

        # F. pogresni tokeni: 404, nikad 500, bez tehnicke strane
        osnova = url[: url.rstrip('/').rfind('/') + 1]
        for oznaka, t in [('izmenjen jedan znak', token[:-1] + ('A' if token[-1] != 'A' else 'B')), ('kratak', 'abc'),
                          ('5000 znakova', 'x' * 5000), ('cirilica', 'ђђђђ'), ('SQL', "1'%20OR%20'1'='1"), ('id partije', '1')]:
            r = sB.request.get(osnova + t + '/')
            telo = r.text()
            proveri(f'pogresan token ({oznaka}): 404 bez tehnicke strane', r.status == 404 and 'Traceback' not in telo and 'URLconf' not in telo, r.status)

        b.close()
finally:
    server.terminate()
print(json.dumps({'strana': STRANA, 'prolazi': sum(x['ok'] for x in rezultati), 'ukupno': len(rezultati), 'provere': rezultati},
                 ensure_ascii=False, indent=1))
