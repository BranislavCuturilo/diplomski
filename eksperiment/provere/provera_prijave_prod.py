"""Napad na ograničenje prijave preko pravog servera, isto za obe strane, na KOPIJI projekta.

A) trka: 40 istovremenih pokusaja sa 40 razlicitih lozinki, od kojih je jedna tacna, na svezem nalogu.
   Sa ispravnim ogranicenjem (5 pokusaja) tacna prolazi u oko 5/40 slucajeva; bez njega skoro uvek.
B) istiskivanje: nalog se zakljuca sa 5 promasaja, pa 320 promasaja na nasumicna imena, pa tacna lozinka.
Pokretanje: <venv strane>\\python provera_prijave.py <projekat> <prazan|plugin> <port>
"""
import http.client, json, os, random, re, shutil, subprocess, sys, tempfile, threading, time, urllib.parse, urllib.request
from http.cookies import SimpleCookie

IZVOR, STRANA, PORT = sys.argv[1], sys.argv[2], int(sys.argv[3])
KOPIJA = os.path.join(tempfile.mkdtemp(), 'projekat')
shutil.copytree(IZVOR, KOPIJA, ignore=shutil.ignore_patterns('*.sqlite3', '*.sqlite3.*', '__pycache__', '.claude', 'venv'))
KLJUC = 'k' + 'Zx9#Lq2@Wm4$Rt6^Yp8&Uv1*Bn3(Hc5)Fd7_Gj0-Ks2+Ma4=Pe6' * 2
BAZA = os.path.join(os.path.dirname(KOPIJA), 'baza.sqlite3')
if STRANA == 'prazan':
    OKR = {'DJANGO_SETTINGS_MODULE': 'orkestrator.settings_produkcija', 'ORKESTRATOR_SECRET_KEY': KLJUC, 'ORKESTRATOR_DOMEN': 'orkestrator.example',
           'ORKESTRATOR_BAZA': BAZA, 'ORKESTRATOR_STATIC': os.path.join(os.path.dirname(KOPIJA), 'static')}
else:
    OKR = {'DJANGO_SETTINGS_MODULE': 'orkestrator.settings_prod', 'DJANGO_SECRET_KEY': KLJUC, 'DJANGO_ALLOWED_HOSTS': 'orkestrator.example',
           'DJANGO_CSRF_TRUSTED_ORIGINS': 'https://orkestrator.example', 'DJANGO_BAZA': BAZA}
env = dict(os.environ, PYTHONIOENCODING='utf-8', **OKR)
subprocess.run([sys.executable, 'manage.py', 'migrate', '--noinput', '-v', '0'], cwd=KOPIJA, env=env, check=True)
if STRANA == 'prazan':
    subprocess.run([sys.executable, 'manage.py', 'createcachetable'], cwd=KOPIJA, env=env, check=True)
subprocess.run([sys.executable, 'manage.py', 'collectstatic', '--noinput', '-v', '0'], cwd=KOPIJA, env=env, check=True)
LOZ = 'Vrlo-Duga-Lozinka-2026!'
PROBA = 24
IMENA = [f'mod{i}' for i in range(PROBA)] + ['zakljucan']
NAPRAVI = '''
import sys; sys.path.insert(0, "."); import django; django.setup()
from django.contrib.auth import get_user_model
LOZ = %r
for ime in %r:
    if %r == "prazan":
        from igra import moderacija; moderacija.dodaj_moderatora(None, ime, LOZ, LOZ)
    else:
        from igra import nalozi; nalozi.dodaj(None, ime, LOZ, glavni=True)
        u = get_user_model().objects.get(username=ime); u.nalog_moderatora.mora_promeniti = False; u.nalog_moderatora.save()
''' % (LOZ, IMENA, STRANA)
subprocess.run([sys.executable, '-c', NAPRAVI], cwd=KOPIJA, env=env, check=True)
POLJA = ('ime', 'lozinka') if STRANA == 'prazan' else ('username', 'password')
server = subprocess.Popen([sys.executable, 'manage.py', 'runserver', f'127.0.0.1:{PORT}', '--noreload', '--insecure'], cwd=KOPIJA, env=env,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def kolacici_i_token():
    c = http.client.HTTPConnection('127.0.0.1', PORT, timeout=120)
    c.request('GET', '/moderator/prijava/', headers={'Host': 'orkestrator.example', 'X-Forwarded-Proto': 'https'}); r = c.getresponse(); r.read()
    kol = {}
    for v in r.headers.get_all('Set-Cookie') or []:
        for k, m in SimpleCookie(v).items():
            kol[k] = m.value
    return kol


def pokusaj(kol, ime, loz):
    c = http.client.HTTPConnection('127.0.0.1', PORT, timeout=300)
    telo = urllib.parse.urlencode({POLJA[0]: ime, POLJA[1]: loz, 'csrfmiddlewaretoken': kol['csrftoken']})
    c.request('POST', '/moderator/prijava/', body=telo, headers={
        'Content-Type': 'application/x-www-form-urlencoded', 'Cookie': '; '.join(f'{k}={v}' for k, v in kol.items()),
        'Origin': 'https://orkestrator.example', 'Referer': 'https://orkestrator.example/moderator/prijava/', 'Host': 'orkestrator.example', 'X-Forwarded-Proto': 'https'})
    r = c.getresponse(); r.read()
    return r.status == 302 and '/moderator/prijava' not in (r.getheader('Location') or '')


rezultat = {'strana': STRANA}
try:
    for _ in range(80):
        try:
            kolacici_i_token(); break
        except Exception:
            time.sleep(0.5)
    rng = random.Random(9)
    # A) trka
    uspeh, trajanja = 0, []
    for i in range(PROBA):
        kol = kolacici_i_token()
        tacna = rng.randrange(40)
        lozinke = [LOZ if j == tacna else f'pogresna-{i}-{j}-xyz' for j in range(40)]
        ishodi = [None] * 40
        start = threading.Barrier(40)

        def nit(j):
            start.wait(); ishodi[j] = pokusaj(dict(kol), f'mod{i}', lozinke[j])
        t0 = time.time()
        niti = [threading.Thread(target=nit, args=(j,)) for j in range(40)]
        [t.start() for t in niti]; [t.join() for t in niti]
        trajanja.append(round(time.time() - t0, 1))
        uspeh += bool(ishodi[tacna])
    rezultat['trka'] = {'proba': PROBA, 'tacna_prosla': uspeh, 'ocekivano_sa_ogranicenjem': f'oko {PROBA * 5 / 40:.0f}', 'sekundi_po_probi': trajanja}
    raise SystemExit(print(json.dumps(dict(rezultat, podesavanja='produkcija'), ensure_ascii=False)))
    # B) istiskivanje blokade
    kol = kolacici_i_token()
    for _ in range(6):
        pokusaj(kol, 'zakljucan', 'pogresna-lozinka')
    zakljucan_pre = not pokusaj(kol, 'zakljucan', LOZ)
    t0 = time.time()
    for n in range(320):
        pokusaj(kol, f'nasumicno{n}-{rng.random()}', 'pogresna-lozinka')
    posle = pokusaj(kolacici_i_token(), 'zakljucan', LOZ)
    rezultat['istiskivanje'] = {'zakljucan_pre_poplave': zakljucan_pre, 'tacna_prosla_posle_320_imena': posle,
                                'sekundi_poplave': round(time.time() - t0)}
finally:
    server.terminate()
print(json.dumps(rezultat, ensure_ascii=False))
