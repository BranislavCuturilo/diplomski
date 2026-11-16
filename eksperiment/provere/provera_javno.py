"""Nezavisna provera pripreme za javni rad, ista za obe strane, na KOPIJI projekta sa produkcionim podesavanjima.

Koraci administratora se izvode onako kako ih uputstvo strane navodi (migrate, createcachetable ako ga trazi,
collectstatic). Zatim aplikacija radi iza zamisljenog proksija: Host orkestrator.example, X-Forwarded-Proto https.
Pokretanje: <venv strane>\\python provera_javno.py <projekat> <prazan|plugin> <port>
"""
import http.client, json, os, re, shutil, sqlite3, subprocess, sys, tempfile, threading, time, urllib.parse
from http.cookies import SimpleCookie

IZVOR, STRANA, PORT = sys.argv[1], sys.argv[2], int(sys.argv[3])
RAD = tempfile.mkdtemp()
KOPIJA = os.path.join(RAD, 'projekat')
shutil.copytree(IZVOR, KOPIJA, ignore=shutil.ignore_patterns('*.sqlite3', '*.sqlite3.*', '__pycache__', '.claude', 'venv', '.git', 'staticfiles'))
DOMEN = 'orkestrator.example'
KLJUC = 'k' + 'Zx9#Lq2@Wm4$Rt6^Yp8&Uv1*Bn3(Hc5)Fd7_Gj0-Ks2+Ma4=Pe6' * 2
BAZA = os.path.join(RAD, 'baza.sqlite3')
if STRANA == 'prazan':
    MODUL = 'orkestrator.settings_produkcija'
    OKR = {'ORKESTRATOR_SECRET_KEY': KLJUC, 'ORKESTRATOR_DOMEN': DOMEN, 'ORKESTRATOR_BAZA': BAZA,
           'ORKESTRATOR_STATIC': os.path.join(RAD, 'static')}
    TAJNA = 'ORKESTRATOR_SECRET_KEY'
    KORACI = [['migrate', '--noinput'], ['createcachetable'], ['collectstatic', '--noinput']]
else:
    MODUL = 'orkestrator.settings_prod'
    OKR = {'DJANGO_SECRET_KEY': KLJUC, 'DJANGO_ALLOWED_HOSTS': DOMEN, 'DJANGO_CSRF_TRUSTED_ORIGINS': f'https://{DOMEN}',
           'DJANGO_BAZA': BAZA, 'DJANGO_HSTS_SEKUNDI': '3600'}
    TAJNA = 'DJANGO_SECRET_KEY'
    KORACI = [['collectstatic', '--noinput'], ['migrate', '--noinput']]
env = dict(os.environ, DJANGO_SETTINGS_MODULE=MODUL, PYTHONIOENCODING='utf-8', **OKR)
rezultati = []


def proveri(oznaka, uslov, detalj=''):
    rezultati.append({'provera': oznaka, 'ok': bool(uslov), 'detalj': str(detalj)[:500]})


def manage(*arg, okruzenje=None):
    return subprocess.run([sys.executable, 'manage.py', *arg], cwd=KOPIJA, env=okruzenje or env, capture_output=True, text=True,
                          encoding='utf-8', errors='replace')


# 1. bez tajnog kljuca aplikacija ne krece
bez = {k: v for k, v in env.items() if k != TAJNA}
r = manage('check', okruzenje=bez)
proveri('bez tajnog kljuca aplikacija odbija da krene i imenuje promenljivu', r.returncode != 0 and TAJNA in (r.stderr + r.stdout),
        (r.stderr + r.stdout)[-200:])

# 2. koraci administratora
for korak in KORACI:
    r = manage(*korak)
    proveri(f'korak iz uputstva prolazi: {" ".join(korak)}', r.returncode == 0, (r.stderr or r.stdout)[-300:])
r = manage('check', '--deploy')
upozorenja = re.findall(r'\(security\.\w+\)', r.stdout + r.stderr)
proveri('check --deploy bez upozorenja', r.returncode == 0 and not upozorenja, (upozorenja or (r.stdout + r.stderr)[-200:]))

# 3. server iza zamisljenog proksija
server = subprocess.Popen([sys.executable, 'manage.py', 'runserver', f'127.0.0.1:{PORT}', '--noreload', '--insecure'], cwd=KOPIJA,
                          env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def zahtev(metod, put, telo=None, kol=None, host=DOMEN, https=True, zaglavlja=None):
    c = http.client.HTTPConnection('127.0.0.1', PORT, timeout=120)
    h = {'Host': host}
    if https:
        h['X-Forwarded-Proto'] = 'https'
        h['Origin'] = f'https://{DOMEN}'; h['Referer'] = f'https://{DOMEN}/'
    if kol:
        h['Cookie'] = '; '.join(f'{k}={v}' for k, v in kol.items())
        if 'csrftoken' in kol:
            h['X-CSRFToken'] = kol['csrftoken']
    h.update(zaglavlja or {})
    c.request(metod, put, body=telo, headers=h)
    r = c.getresponse(); podaci = r.read()
    if kol is not None:
        for v in r.headers.get_all('Set-Cookie') or []:
            for k, m in SimpleCookie(v).items():
                kol[k] = m.value
    return r, podaci


try:
    for _ in range(80):
        try:
            zahtev('GET', '/'); break
        except Exception:
            time.sleep(0.5)
    r, telo = zahtev('GET', '/', https=False)
    proveri('http preusmerava na https', r.status in (301, 308) and (r.getheader('Location') or '').startswith('https://'), (r.status, r.getheader('Location')))
    r, telo = zahtev('GET', '/', host='zlo.example')
    proveri('nepoznat Host odbijen (400)', r.status == 400, r.status)
    kol = {}
    r, telo = zahtev('GET', '/', kol={})
    html = telo.decode('utf-8', 'replace')
    proveri('pocetna strana radi (200)', r.status == 200, r.status)
    kolacici = r.headers.get_all('Set-Cookie') or []
    proveri('svi kolacici samo preko HTTPS-a (Secure)', kolacici and all('secure' in k.lower() for k in kolacici), kolacici)
    proveri('HSTS zaglavlje postoji', int(re.search(r'max-age=(\d+)', r.getheader('Strict-Transport-Security') or 'max-age=0').group(1)) > 0,
            r.getheader('Strict-Transport-Security'))
    proveri('zaglavlja: nosniff, X-Frame-Options, Referrer-Policy',
            r.getheader('X-Content-Type-Options') == 'nosniff' and r.getheader('X-Frame-Options') and r.getheader('Referrer-Policy'),
            (r.getheader('X-Content-Type-Options'), r.getheader('X-Frame-Options'), r.getheader('Referrer-Policy')))
    staticki = re.findall(r'/static/[^"\']+\.(?:css|js)', html)
    postoje = [os.path.exists(os.path.join(OKR.get('ORKESTRATOR_STATIC', os.path.join(KOPIJA, 'staticfiles')), s[len('/static/'):])) for s in staticki]
    # Hes u imenu (dug kes) ili isto ime uz no-cache u nginx-u: oba su ispravna; bitno je da datoteke postoje.
    proveri('staticke datoteke iz strane postoje u direktorijumu koji servira nginx', staticki and all(postoje),
            list(zip(staticki, postoje))[:4])
    r, telo = zahtev('GET', '/nepostoji-xyz/')
    proveri('404 bez tehnicke strane', r.status == 404 and b'URLconf' not in telo and b'Traceback' not in telo, r.status)

    # 4. neuspela prijava moderatora pod produkcionim podesavanjima (kes ili tabela brojaca)
    k2 = {}; zahtev('GET', '/moderator/prijava/', kol=k2)
    polja = ('ime', 'lozinka') if STRANA == 'prazan' else ('username', 'password')
    telo_p = urllib.parse.urlencode({polja[0]: 'niko', polja[1]: 'pogresna-lozinka-123', 'csrfmiddlewaretoken': k2.get('csrftoken', '')})
    r, _ = zahtev('POST', '/moderator/prijava/', telo_p, kol=k2, zaglavlja={'Content-Type': 'application/x-www-form-urlencoded'})
    proveri('neuspela prijava radi bez greske 500', r.status < 500, r.status)

    # 5. opterecenje: 40 igraca istovremeno, cela partija i cuvanje
    sys.path.insert(0, KOPIJA)
    os.environ.update(env); os.chdir(KOPIJA)
    import django; django.setup()
    if STRANA == 'prazan':
        from igra import parametri as p
        izb = {'model': sorted(p.MODELI)[0], 'nivo': sorted(p.NIVOI)[0], 'kontekst': sorted(p.KONTEKSTI)[0], 'podela': sorted(p.PODELE)[0]}
    else:
        from igra import motor
        izb = {g: sorted(o)[0] for g, o in motor.GRUPE_IZBORA.items()}
    kodovi, greske = [], []
    start = threading.Barrier(40)

    def igrac(n):
        try:
            k = {}
            zahtev('GET', '/', kol=k)
            start.wait()
            if STRANA == 'prazan':
                kodovi.append(zahtev('POST', '/nova/', '', kol=k, zaglavlja={'Content-Type': 'application/x-www-form-urlencoded'})[0].status)
            for kr in range(1, 9):
                telo_z = json.dumps(dict(izb, krug=kr)) if STRANA == 'prazan' else json.dumps({'krug': kr, 'izbori': izb})
                kodovi.append(zahtev('POST', '/api/potez/' if STRANA == 'prazan' else '/potez/', telo_z, kol=k,
                                     zaglavlja={'Content-Type': 'application/json'})[0].status)
            if STRANA == 'prazan':
                kodovi.append(zahtev('POST', '/rezultat/', urllib.parse.urlencode({'ime': f'Opt{n}'}), kol=k,
                                     zaglavlja={'Content-Type': 'application/x-www-form-urlencoded'})[0].status)
            else:
                kodovi.append(zahtev('POST', '/sacuvaj/', json.dumps({'ime': f'Opt{n}'}), kol=k, zaglavlja={'Content-Type': 'application/json'})[0].status)
        except Exception as e:
            greske.append(type(e).__name__)
    t0 = time.time()
    niti = [threading.Thread(target=igrac, args=(n,)) for n in range(40)]
    [t.start() for t in niti]; [t.join() for t in niti]
    sacuvano = sqlite3.connect(BAZA).execute("SELECT COUNT(*) FROM igra_rezultat WHERE ime LIKE 'Opt%'").fetchone()[0]
    proveri('40 istovremenih igraca: bez 5xx i svi rezultati sacuvani', not [k for k in kodovi if k >= 500] and not greske and sacuvano == 40,
            f'5xx {len([k for k in kodovi if k >= 500])}, izuzeci {greske[:3]}, sacuvano {sacuvano}/40, {time.time() - t0:.1f} s')
finally:
    server.terminate()

# 6. rezervna kopija iz uputstva
komanda = 'rezervna_kopija' if STRANA == 'prazan' else 'baza_kopija'
odrediste = os.path.join(RAD, 'kopije'); os.makedirs(odrediste)
pomoc = manage(komanda, '--help').stdout
# prazan: direktorijum (podrazumevani ili zadat); plugin: putanja nove datoteke (PUTANJA, ne sme da postoji)
argumenti = [os.path.join(odrediste, 'kopija.sqlite3')] if STRANA == 'plugin' else (
    [odrediste] if re.search(r'usage: .*' + komanda + r' .*\b(odrediste|putanja|dir|direktorijum|izlaz|path)\b', pomoc, re.I | re.S) else [])
r = manage(komanda, *argumenti)
nadjene = [os.path.join(d, f) for d, _, fs in os.walk(RAD) for f in fs if f.endswith('.sqlite3') and 'baza.sqlite3' not in f and 'projekat' not in d]
ispravna = False
for f in nadjene:
    try:
        ispravna = sqlite3.connect(f).execute('PRAGMA integrity_check').fetchone()[0] == 'ok' or ispravna
    except Exception:
        pass
proveri('rezervna kopija nastaje i ispravna je (integrity_check)', r.returncode == 0 and ispravna,
        f'izlaz {r.returncode}, kopije {nadjene[:2]}, {(r.stderr or r.stdout)[-200:]}')

print(json.dumps({'strana': STRANA, 'prolazi': sum(x['ok'] for x in rezultati), 'ukupno': len(rezultati), 'provere': rezultati},
                 ensure_ascii=False, indent=1))
