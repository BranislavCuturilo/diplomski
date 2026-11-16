"""Trka: dva istovremena poteza istog kruga iz iste sesije. Partija sme da napreduje tacno jednom.

Pokretanje: <venv strane>\\python provera_trke.py <projekat> <prazan|plugin> <port>
"""
import http.client, json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.request
from http.cookies import SimpleCookie

IZVOR, STRANA, PORT = sys.argv[1], sys.argv[2], int(sys.argv[3])
KOPIJA = os.path.join(tempfile.mkdtemp(), 'projekat')
shutil.copytree(IZVOR, KOPIJA, ignore=shutil.ignore_patterns('*.sqlite3', '__pycache__', '.claude', 'venv'))
env = dict(os.environ, DJANGO_SETTINGS_MODULE='orkestrator.settings', PYTHONIOENCODING='utf-8')
subprocess.run([sys.executable, 'manage.py', 'migrate', '--noinput', '-v', '0'], cwd=KOPIJA, env=env, check=True)
dodatno = ['--insecure'] if STRANA == 'prazan' else []
server = subprocess.Popen([sys.executable, 'manage.py', 'runserver', f'127.0.0.1:{PORT}', '--noreload'] + dodatno, cwd=KOPIJA, env=env,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
IZB = {'model': 'haiku', 'nivo': None, 'kontekst': None, 'podela': None}


def zahtev(metod, put, telo=None, kolacici=None, zaglavlja=None):
    c = http.client.HTTPConnection('127.0.0.1', PORT, timeout=30)
    h = {'Host': f'127.0.0.1:{PORT}', 'Origin': f'http://127.0.0.1:{PORT}', 'Referer': f'http://127.0.0.1:{PORT}/'}
    if kolacici:
        h['Cookie'] = '; '.join(f'{k}={v}' for k, v in kolacici.items())
    h.update(zaglavlja or {})
    c.request(metod, put, body=telo, headers=h)
    r = c.getresponse(); podaci = r.read()
    for v in r.headers.get_all('Set-Cookie') or []:
        for k, m in SimpleCookie(v).items():
            kolacici[k] = m.value
    return r.status, podaci


try:
    for _ in range(60):
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{PORT}/', timeout=1); break
        except Exception:
            time.sleep(0.5)
    sys.path.insert(0, KOPIJA); os.chdir(KOPIJA)
    import django; django.setup()
    if STRANA == 'prazan':
        from igra import parametri as p
        grupe = {'model': p.MODELI, 'nivo': p.NIVOI, 'kontekst': p.KONTEKSTI, 'podela': p.PODELE}
    else:
        from igra import motor
        grupe = motor.GRUPE_IZBORA
    izbori = {g: sorted(o)[0] for g, o in grupe.items()}

    ishodi = []
    for pokusaj in range(15):
        kol = {}
        zahtev('GET', '/', kolacici=kol)
        csrf = {'X-CSRFToken': kol.get('csrftoken', '')}
        if STRANA == 'prazan':
            zahtev('POST', '/nova/', 'csrfmiddlewaretoken=' + kol.get('csrftoken', ''), kol,
                   dict(csrf, **{'Content-Type': 'application/x-www-form-urlencoded'}))
            put, telo = '/api/potez/', json.dumps(dict(izbori, krug=1))
        else:
            put, telo = '/potez/', json.dumps({'krug': 1, 'izbori': izbori})
        z = dict(csrf, **{'Content-Type': 'application/json'})
        kodovi = []
        start = threading.Barrier(2)

        def posalji():
            start.wait()
            kodovi.append(zahtev('POST', put, telo, dict(kol), z)[0])
        niti = [threading.Thread(target=posalji) for _ in range(2)]
        [t.start() for t in niti]; [t.join() for t in niti]
        # stanje posle trke: krug 2 mora da prodje, ponovljen krug 1 mora da bude odbijen
        telo2 = json.dumps(dict(izbori, krug=2)) if STRANA == 'prazan' else json.dumps({'krug': 2, 'izbori': izbori})
        k2 = zahtev('POST', put, telo2, dict(kol), z)[0]
        ishodi.append({'trka': sorted(kodovi), 'krug2': k2})
    dobri = [i for i in ishodi if i['trka'].count(200) == 1 and i['krug2'] == 200]
    print(json.dumps({'strana': STRANA, 'ispravno': len(dobri), 'od': len(ishodi), 'primeri': ishodi[:5]}, ensure_ascii=False))
finally:
    server.terminate()
