## 15. Javna isporuka (2026-11-11)

Status: **plan; nista nije pokrenuto ni izmenjeno.** Ceka odgovore na P1-P4 (15.1).
Zahtev klijenta: igra ide javno na `https://orkestrator.example`, nekoliko hiljada igraca dnevno; projekat se priprema, a postavljanje radi klijentov administrator po nasem uputstvu.
Izvori: `orkestrator/settings.py`, `orkestrator/greske.py`, `orkestrator/urls.py`, `igra/views.py`, `igra/forme.py`, plan-moderator.md 14.10, plan.md 11.7 i D2, MVP 2, 3 i 6, `projekat-standardi`, skillovi `django-nginx-docker`, `craft-git`, `craft-security`, agent `devops`.

**Sukob (stani i pitaj, `projekat-standardi`, „Kako agent postupa“):** zahtev trazi server, proxy i TLS. To se kosi sa CLAUDE.md:6 (django-nginx-docker „se ovde ne koristi“), `projekat-standardi` pravilom 3 („Bez Docker-a, Nginx-a“, SKILL.md:31) i MVP:19 (isporuka je van MVP-a). Odgovor na P1 se upisuje kao odluka (15.14).

**Odgovori korisnika 2026-11-11: P1 A, P2 A, P3 A, P4 A (sve preporuke). Dokumenti iz 15.14 (osim MVP-a) azurirani pre T1.**

### 15.1 Pitanja za korisnika

| # | Pitanje | Opcije | Preporuka i razlog |
|---|---|---|---|
| P1 | Server i nacin rada (OS nije poznat) | **A** Linux, Docker Compose: Nginx + gunicorn; **B** Linux, systemd + Nginx, venv; **C** Windows Server, waitress + IIS ili Caddy | **A.** Slika nosi Python 3.14 i `DJANGO_SETTINGS_MODULE`, pa administrator ne gradi Python. Debian i Ubuntu LTS nose stariji Python (proverava se na serveru). Isti postupak radi lokalno i na serveru. Vazi `django-nginx-docker`. C trazi drugi skup proba. |
| P2 | Brojac neuspeha prijave pri vise procesa (15.2) | **A** brojac u bazi: novi model `PokusajPrijave`, `UPDATE ... broj = broj + 1` pod IMMEDIATE bravom; **B** Memcached: nov kontejner i zavisnost `pymemcache`; **C** jedan proces sa nitima, LocMem ostaje | **A.** Nema novog servisa ni zavisnosti, blokada prezivi restart i isporuku, a kopija baze je jedna. Trazi sesti model, pa i odluku u `projekat-odluke`. C stavlja ceo sajt na jedan proces (GIL, oko 50 z/s) i brise blokade pri svakoj isporuci. |
| P3 | Nadogradnja zavisnosti | **A** Django 6.0 na 6.0.8 i sqlparse 0.5.4 na 0.6.0 pre isporuke; **B** isporuka na 6.0, a proxy odbija multipart | **A, obavezno za javni rad.** CVE-2026-33033 (DoS kroz multipart) pogadja svaki POST bez prijave, jer CSRF provera parsira telo. Blokada multipart-a na Nginx-u ostaje kao druga linija, ne kao zamena. |
| P4 | Kako kod stize administratoru (projekat nije git repozitorijum) | **A** `git init` lokalno (`.gitignore`, oznaka `v1.0.0`), administrator dobija `git archive` zip; **B** privatni udaljeni repozitorijum, server radi `git fetch` pa `git reset --hard v1.0.0`; **C** gotova slika u registru | **A.** Arhiva sadrzi tacno ono sto je u git-u, pa `db.sqlite3*`, `.claude/usage` (pun tekst upita) i `.env` ne mogu da procure. Server ne treba pristup repozitorijumu. B je bolja ako isporuka postane cesta. |

**Preporuke koje vaze bez pitanja:**
- SQLite ostaje, u WAL modu.
- Nginx radi TLS, staticke fajlove i ogranicenje brzine; WhiteNoise se ne uvodi.
- Podesavanja su podeljena na `settings.py` i `settings_prod.py`.
- CSP preko ugradjenog mehanizma Django 6.0.
- HSTS u dva koraka, bez preload-a.
- Brojac zahteva po IP-u je na proxy-ju.
- Ruta `zdravlje/` koja ne pravi sesiju.
- Komanda `baza_kopija` (VACUUM INTO).
- Prazna baza na serveru.
- Sopstvene strane 400, 403, 404 i 500 na oba jezika.
- Log bez tokena, lozinke i tela zahteva.
- Link za deljenje bez nove promenljive podesavanja.
- Detalji su u 15.3-15.7.

### 15.2 Procena opterecenja (racun; brojevi oznaceni sa ~ nisu mereni, meri ih T2)

| Velicina | Racun | Rezultat |
|---|---|---|
| igraci | gornje citanje „nekoliko hiljada“; 1,5 partija po igracu | 5.000/dan, rezerva 10.000 |
| zahtevi po partiji | 8 `potez` + 1 `nova` + 0,3 `sacuvaj` + 0,2 `podeli` + 0,1 `jezik` ≈ 10 POST; GET `/` ≈ 2; statika ide Nginx-u | 12 dinamickih |
| dan | 5.000 × 1,5 × 12 | 90.000, prosek 1,04 z/s |
| vrh | 15% dana u jednom satu: 3,75 z/s; odeljenje od 30 ucenika krene zajedno: ×3 | **≈11 z/s** (10.000/dan: ≈22 z/s) |
| cilj projektovanja | rezerva za link koji se siri drustvenim mrezama | **50 z/s** |
| upisi | 10 od 12 zahteva pise (POST i prvi GET nove sesije) | 42 upisa/s na cilju |
| trajanje upisne transakcije S | BEGIN IMMEDIATE, citanje sesije, motor, UPDATE, COMMIT sa fsync (WAL, `synchronous` ostaje FULL) | ~2-8 ms |
| zauzetost brave | ρ = 42 × S | 0,08-0,34 |
| cekanje na bravu | M/D/1: ρ / (2(1−ρ)) × S | ≤2 ms; busy timeout 5 s je daleko |
| plafon upisa | 1 / S | 125-500/s, 3-12× iznad cilja |
| CPU | ~5-25 ms po zahtevu; 50 × 20 ms = 1,0 CPU-s/s | 2 vCPU, 2× rezerva |
| procesi | Little: 50 z/s × 0,02 s = 1 zahtev istovremeno u proseku | gunicorn `sync`, **4 radnika**, timeout 30 s; Nginx baferuje spore klijente |
| sesije | novi posetioci 5.000 + botovi ~5.000 dnevno; zivot 14 dana; red ~1-3 KB | ~140.000 redova, 140-420 MB uz dnevni `clearsessions`; bez njega +10-30 MB dnevno, bez kraja |
| disk | baza ≤0,5 GB; kopije 7 dnevnih + 4 nedeljne ≈5,5 GB; slike i logovi ≈2 GB | 2 vCPU, 2 GB RAM, ≥20 GB SSD i kopije van servera |

**Zakljucak.** SQLite i jedan server izdrzavaju vrh i za 10.000 igraca dnevno, pod tri uslova:
- **WAL mora da se ukljuci.** Danas ga nema (settings.py:56-63). U rollback journal modu citaoci (`/`, `deljeno`, rang) i pisac se medjusobno blokiraju tokom COMMIT-a, pa vise procesa daje „database is locked“.
- **PBKDF2 sme da zauzme najvise jednog radnika.** Svaki pokusaj prijave trosi stotine ms CPU-a (settings.py:103-104). Cetiri istovremena pokusaja zauzmu sva 4 radnika i igra stane. Zato Nginx propusta prijave globalnom stopom 2/s, nalet 5, bez `nodelay` (visak ceka do 2,5 s), uz najvise 3 istovremene POST prijave po IP-u. Prvobitni globalni `limit_conn` 1 je odbacen posle revizije T4 (S1: jedan spor POST blokira sve prijave).
- **Rast sesija se cisti** (15.5, 15.6).

**LocMem pri vise procesa** (settings.py:97-111, forme.py:54-75):
- Svaki radnik ima svoj brojac. Umesto 5 pokusaja po imenu na 15 minuta prolazi 5 × 4 = 20.
- Poruka o blokadi zavisi od toga koji radnik odgovara.
- Restart radnika i svaka isporuka brisu sve blokade.
- `add` + `incr` su atomicni samo unutar jednog procesa.
- Zato je potreban zajednicki brojac (P2).
- plan-moderator.md:357 jos kaze „pri isporuci `DatabaseCache`“. To protivreci 14.10:367 i komentaru u settings.py:94-96 i ispravlja se (15.14).

### 15.3 Arhitektura na serveru (uz P1 A)

Internet → Nginx :443 (TLS, HTTP/2; :80 daje 301) → gunicorn :8000, samo u compose mrezi, port se ne objavljuje → Django → SQLite `/data/db.sqlite3` na imenovanom volumenu, van slike.

- **Slika:** `python:3.14-slim` sa fiksnim digest-om. `pip install -r requirements.txt`. `collectstatic` ide u build fazi. `ENV DJANGO_SETTINGS_MODULE=orkestrator.settings_prod` je u Dockerfile-u, pa ne zavisi od administratora. Proces ne radi kao root.
- **Migracija** je poseban korak isporuke (`docker compose run --rm app python manage.py migrate`), nikad u `CMD` (django-nginx-docker, pravilo 3).
- **Statika:** Nginx servira `STATIC_ROOT` direktno. Devops bira multi-stage kopiju ili deljeni volumen.
  - `ManifestStaticFilesStorage` se ne koristi: bootstrap-5.3.8.min.css:6 nosi `sourceMappingURL` na `.map` koji ne postoji, pa bi `collectstatic` pao.
  - Bootstrap (verzija u imenu datoteke) dobija `Cache-Control` od 1 godine.
  - `igra.js` i `igra.css` dobijaju `no-cache` uz ETag: posle isporuke niko ne ostaje na staroj skripti.
  - gzip ide za CSS i JS.
- **TLS:** Let's Encrypt (certbot, webroot, obnova timerom) ili sertifikat klijenta. `.example` je rezervisan TLD (RFC 2606), pa sertifikat za njega ne postoji. Stvarni domen ide samo kroz `.env` (`DOMEN`), nikad u kod.
- **Nginx kao ivica:**
  - Nepoznat `Host` ide na `default_server`, koji zatvara vezu (444); Django ga ni ne vidi.
  - Nginx postavlja `Host $host` i `X-Forwarded-Proto $scheme` i PREPISUJE ga uvek.
  - Ako klijent ima CDN ili balanser ispred, DEPLOY.md opisuje `real_ip`; bez toga ogranicenje po IP-u broji CDN.
- **Periodicni zadaci:** cron ili systemd timer na domacinu poziva `docker compose exec -T app python manage.py ...`, bez dodatnog kontejnera (15.6).
- Sva konfiguracija je u `Dockerfile`, `compose.yaml`, `.dockerignore` i `deploy/`. Tajne su u `.env` van git-a (`env_file`).

### 15.4 Podesavanja

`settings.py` ostaje lokalni i testni modul. `settings_prod.py` radi `from .settings import *` i menja samo ono sto trazi HTTPS ili server. Testovi rade pod `settings.py` i ne kvare se: Playwright ide preko http-a, a `SECURE_SSL_REDIRECT` bi ga preusmerio.

| Podesavanje | `settings.py` (lokalno, testovi) | `settings_prod.py` |
|---|---|---|
| `DEBUG` | True (settings.py:13) | False |
| `SECRET_KEY` | kao danas (settings.py:8-11) | `os.environ["DJANGO_SECRET_KEY"]`, bez rezerve: pada glasno. Ne menja se izmedju verzija (sesije); rotacija samo kroz `SECRET_KEY_FALLBACKS`. |
| `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` | kao danas | iz okruzenja; poreklo sa semom `https://` |
| `SECURE_PROXY_SSL_HEADER` | - | `("HTTP_X_FORWARDED_PROTO", "https")` |
| `SECURE_SSL_REDIRECT` | False | True (druga linija iza Nginx-a) |
| `SESSION_`, `CSRF_`, `LANGUAGE_COOKIE_SECURE` | False (settings.py:78-79, 135) | True. Imena kolacica se ne menjaju, jer `igra.js` cita `csrftoken`. |
| `SECURE_HSTS_SECONDS` | 0 | iz `DJANGO_HSTS_SEKUNDI`: prvo 3600, posle 14 dana bez problema 31536000. Bez `includeSubDomains` (poddomeni nepoznati) i bez preload-a. W005 i W021 se utisavaju izricito, uz razlog u komentaru. |
| nosniff, Referrer `same-origin`, COOP, `X-Frame-Options: DENY` | Django podrazumevano, vec aktivno | isto; `deljeno` zadrzava `no-referrer` (views.py:387) |
| CSP (danas je nema) | **novo, u osnovnim podesavanjima**, pa vazi i u testovima: Django 6.0 `ContentSecurityPolicyMiddleware` + `SECURE_CSP` (opis ispod tabele) | isto |
| `DATABASES` | dodaje se `init_command` `PRAGMA journal_mode=WAL` i `timeout` 5 | `NAME` iz `DJANGO_BAZA` (`/data/db.sqlite3`) |
| `DATA_UPLOAD_MAX_MEMORY_SIZE` / `_NUMBER_FIELDS` | 16 KB / 50 (JSON telo je ionako najvise 2 KB, views.py:26) | isto |
| `STATIC_ROOT` | - | `BASE_DIR / "staticfiles"` |
| `LOGGING` | podrazumevano | opis ispod tabele |
| `CACHES["prijava"]` | uklanja se uz P2 A | - |

**CSP, vrednost:** `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:` (data: je za SVG u Bootstrap CSS-u); `object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'`. Sabloni nemaju inline skriptu ni `style=` (provereno grep-om). `json_script` nije izvrsna skripta, a `igra.js` menja stil kroz CSSOM, sto CSP dozvoljava.

**LOGGING:**
- Izlaz je stdout, odakle ga cita `docker logs` uz rotaciju.
- `django.request` loguje od nivoa ERROR, `django.security` od WARNING.
- Filter u `orkestrator/greske.py` menja `/r/<token>/` u `/r/-/`.
- U log nikad ne idu telo zahteva, kolacici ni lozinka.
- Bez `ADMINS` i bez mejla.
- Pristupni log gunicorn-a je iskljucen; Nginx log maskira token kroz `map` i cuva se 14 dana.

**Sopstvene strane** `templates/{400,403,404,500}.html`:
- Samostalne su: bez upita bazi i bez konteksta prikaza.
- Tekst ide kroz `{% translate %}`, na jeziku iz `LocaleMiddleware`.
- 500 bez `DEBUG` vise ne prikazuje tehnicku stranu, a 404 ne nabraja rute.
- `deljeno` i moderatorska 403 zadrzavaju svoje strane, iste bajtove.

### 15.5 Zastita od zloupotrebe

**Ogranicenje brzine je na Nginx-u** (`limit_req`, odgovor 429). Na proxy-ju zato sto ne trazi novu zavisnost, zahtev ne stigne do Python-a, a brojac je zajednicki svim radnicima. Granice dozvoljavaju skolsko odeljenje iza jednog NAT-a (30 igraca).

| Putanja | Granica po IP-u |
|---|---|
| `POST /potez/` | 10/s, nalet 60 |
| `POST /sacuvaj/`, `/podeli/`, `/jezik/` | 2/s, nalet 30 |
| `POST /nova/` | 30/min, nalet 60 (zona `nova`, revizija T4 N1) |
| `GET /` | 30/min, nalet 60 (zona `strana`); po adresi najvise ~86.400 novih redova sesije dnevno |
| `GET /` bez kolacica `sessionid` (pravi sesiju) | 30/min, nalet 60; kljuc kroz `map $cookie_sessionid` |
| `GET /r/` | 5/s, nalet 30 |
| `/moderator/prijava/` | 6/min, nalet 5 po IP-u; globalno 2/s, nalet 5, bez `nodelay`; najvise 3 istovremene po IP-u; telo 4 KB, `client_body_timeout` 5 s; 429 je nasa dvojezicna strana |
| ostatak `/moderator/` | 5/s |

- Ogranicenje po imenu u aplikaciji ostaje (P2). `igra.js` 429 prikazuje kao opstu gresku (citanje teksta pa JSON-a, igra.js:410-412); qa to proverava.
- **Telo zahteva:**
  - Nginx: `client_max_body_size 16k`, `client_body_timeout 10s`, multipart daje 415. Nijedna forma ni `fetch` ne salje multipart (grep: samo `application/json`, igra.js:432, 646).
  - Django ogranicenja su u 15.4.
- **Rast tabele sesija:** svaki posetilac bez kolacica pravi red (views.py:190-194, odluka P4 iz plan.md:14). Mere:
  - dnevni `clearsessions`;
  - ogranicenje novih sesija iznad;
  - `robots.txt`;
  - uzbuna kada disk predje 80%.
  - Napad sa jednog IP-a je ogranicen na oko 43.000 redova dnevno.
  - Zdravstvena provera gadja `zdravlje/`, nikad `/`: provera na 30 s napravila bi 2.880 sesija dnevno.
  - Ako pracenje pokaze rast, sledeci korak je sesija tek na prvom potezu. To menja P4, pa trazi novo pitanje; nije u ovom planu.
- **Spam rang liste:**
  - Cuvanje trazi celu partiju i 9 POST-ova. Ostaju ogranicenje brzine, sifarnik i moderator.
  - Preostali rizik: skripta igra mnogo partija i puni prvih 10. Prihvata se; klijent obezbedjuje moderatore (15.8).
- **CVE-2026-33033:** pokriva ga P3 A; blokada multipart-a na proxy-ju je dodatak.
- **Zdravstvena provera:** `GET /zdravlje/`.
  - Vraca 200 `{"ok": true}` posle jednog citanja baze.
  - `never_cache`, bez sesije i bez Set-Cookie.
  - Provera iz kontejnera salje `Host: $DOMEN` i `X-Forwarded-Proto: https`; inace dobija 400 ili 301.

### 15.6 Odrzavanje

| Zadatak | Kada | Komanda |
|---|---|---|
| istekle sesije | svaki dan 04:10 | `clearsessions` |
| istekli linkovi | svaki dan 04:20 | `deljeni_ocisti` |
| dnevnik stariji od 365 dana | nedeljno | `dnevnik_ocisti` (podrazumevano 365) |
| kopija baze | svaki dan 03:30 | `baza_kopija /kopije/db-<datum>.sqlite3` (opis ispod tabele) |
| provera povratka | mesecno, rucno po DEPLOY.md | kopija u privremeni direktorijum, `integrity_check`, `check`, broj redova po tabeli |

**Kopija baze:**
- `baza_kopija` je nova komanda: `VACUUM INTO`, pa `PRAGMA integrity_check` na kopiji; nalaz koji nije `ok` je greska komande.
- Nikad se ne kopira fajl dok aplikacija radi, jer bez `-wal` kopija nije dosledna.
- Cuva se 7 dnevnih i 4 nedeljne kopije, a nedeljna i van servera.
- Kopija sadrzi sesije (seme partija u toku) i heseve lozinki, pa je sifrovana i sa ogranicenim pristupom.
- Skripta `deploy/odrzavanje.sh` svaki korak oznacava pre izvrsavanja (craft-git); neuspeh je fatalan i ide u log domacina.

**Isporuka nove verzije:**
1. Najava kratkog prekida u satu najmanjeg saobracaja.
2. Kopija baze.
3. `docker compose build`.
4. `migrate` kao poseban korak.
5. `up -d`.
6. `deploy/provera.sh`.

Sesije prezive isporuku: u bazi su, `SECRET_KEY` je isti, a nova verzija mora da cita staro stanje sesije (obrazac `motor.nadogradi`).

**Povratak na prethodnu verziju:**
- Vraca se prethodna oznaka slike (`orkestrator:<verzija>`).
- Ako je bilo migracije, vraca se kopija napravljena pre nje. Gube se upisi od tada.

**Pracenje:**
- Spoljna provera `https://<domen>/zdravlje/` na 1-5 min.
- `healthcheck` u compose-u.
- Docker log `json-file` (`max-size` 10m, `max-file` 5).
- Uzbuna za disk 80% i istek sertifikata za 14 dana.
- Ko dobija uzbunu odlucuje klijent.

### 15.7 Deljeni link

- `_odgovor_deljenja` vec gradi URL iz zahteva (views.py:145), a `get_host()` proverava `ALLOWED_HOSTS`. Iza Nginx-a koji prosledjuje `Host` i `X-Forwarded-Proto` daje `https://orkestrator.example/r/<token>/` bez izmene koda i bez nove promenljive.
- Pogresno podesen proxy pada glasno (400, nema linka), a ne tiho sa tudjim hostom.
- `USE_X_FORWARDED_HOST` ostaje iskljucen.
- Recenica MVP:48 („link radi samo na racunaru igraca“) i napomena D2 (plan.md:881) prestaju da vaze (15.14).

### 15.8 Privatnost: sta klijent mora da odluci (nije pravni savet)

- **Kolacici:**
  - `sessionid` (stanje igre, prijava moderatora) i `csrftoken` (zastita) su tehnicki neophodni.
  - `django_language` nastaje tek na izbor igraca.
  - Nema analitike ni resursa trece strane (Bootstrap je lokalan).
  - Klijent odlucuje da li mu treba obavestenje o kolacicima i da li mu je dovoljno obavestenje bez pristanka.
- **Licni podaci:**
  - ime na rang listi cuva se bez roka;
  - snimak u dnevniku 365 dana;
  - nalozi moderatora;
  - IP adrese u logu Nginx-a, predlog 14 dana.
  - Klijent odlucuje o roku cuvanja imena, o kontaktu za zahtev za brisanje (put postoji: moderator brise) i o tome da li igru koriste maloletnici.
- **Obavestenje o privatnosti:** tekst i rukovalac podacima su na klijentu. Ako obavestenje bude strana u igri, to je nov zahtev (sablon i prevod).
- **Pre pustanja (go/no-go, odobrava klijent):**
  - pregledan engleski (ocene, lekcije, napomena);
  - pregledan sifarnik (65 stavki);
  - odluka o privatnosti;
  - imenovani moderatori;
  - domen i sertifikat;
  - mesto za kopije van servera.

### 15.9 Sta ide u isporuku

| Ide | Ne ide (`.gitignore` i `.dockerignore`) |
|---|---|
| `orkestrator/`, `igra/` (bez `tests/` u slici), `templates/`, `static/`, `locale/` (`.po` i `.mo`), `manage.py`, `requirements.txt`, `Dockerfile`, `compose.yaml`, `deploy/`, `DEPLOY.md` | `db.sqlite3`, `db.sqlite3.pre-*` (4 kopije u korenu, sa sesijama), `.claude/` (posebno `usage/` sa punim tekstom upita), `plan*.md`, `MVP.md`, `__pycache__/` (u njemu je i zaostali `test_zz_privremeno`), `.env`, `staticfiles/`, scratchpad (van projekta) |

- `requirements.txt` danas ne postoji. Pravi se iz cistog venv-a sa tacnim verzijama:
  - `Django==6.0.8`, `asgiref`, `sqlparse==0.6.0`, `gunicorn`;
  - `tzdata`, za `zoneinfo` u slim slici.
  - Testni alati (`playwright`) idu u `requirements-razvoj.txt`.
- Baza na serveru je **prazna**: `migrate`, pa sifarnik iz migracije 0002. Lokalna rang lista su probni podaci.
  - Backend proverava da li je lokalni sifarnik menjan komandama (broj stavki naspram migracije) i nalaz upisuje u izvestaj.
- Prvog glavnog moderatora pravi administrator: `docker compose exec app python manage.py moderator_dodaj IME --glavni` (getpass, TTY).

### 15.10 DEPLOY.md, sadrzaj (pise devops)

1. Zahtevi: Linux, Docker Engine + compose, 2 vCPU, 2 GB, 20 GB, domen u DNS-u, portovi 80 i 443.
2. Preuzimanje koda (P4), provera kontrolnog zbira arhive.
3. `.env` iz `deploy/env.primer`: generisanje `DJANGO_SECRET_KEY`, gde se cuva van servera, sta znaci gubitak.
4. Sertifikat: prvi i obnova.
5. Build, `migrate`, `up -d`; `check --deploy` u kontejneru.
6. Prvi glavni moderator i prva prijava (promena lozinke).
7. Provera posle postavljanja: `deploy/provera.sh` i rucna partija na telefonu.
8. Periodicni zadaci (cron) i provera da su se izvrsili.
9. Kopije: gde, koliko, povratak korak po korak, mesecna proba.
10. Nova verzija i povratak na prethodnu (15.6).
11. HSTS: kada se podize na godinu dana i zasto se ne vraca.
12. Pracenje i logovi: gde su, rotacija, sta je uzbuna.
13. CDN ili balanser ispred (`real_ip`); otkljucavanje moderatora; zamena kompromitovanog naloga (`moderator_deaktiviraj`).

### 15.11 Testovi i dokazi

| Faza | Dokaz |
|---|---|
| T1 backend | `pip install -r requirements.txt` u cistom venv-u (Python 3.14), pa ceo paket `test_summary.py` EXIT=0. `pip-audit -r requirements.txt` bez nalaza. `check --deploy --fail-level WARNING` pod `settings_prod` sa postavljenim okruzenjem: 0 nalaza. Bez `DJANGO_SECRET_KEY` pokretanje pada. `makemigrations --check`. Kopija `db.sqlite3.pre-0012-*`, pa `migrate`. `PRAGMA journal_mode` vraca `wal`. Proba p5 (scratchpad\sec\r2) ponovljena protiv novog brojaca, iz dva procesa. |
| T1 frontend | sve cetiri strane renderovane pod `DEBUG=False` na sr i en, bez upita bazi; pregledac se ne pokrece do T4 (izvestaj to navodi) |
| T1 devops | `docker compose config` bez gresaka; `nginx -t` u kontejneru |
| T2 devops | **proba lokalno u Docker-u** (samopotpisan sertifikat, domen u hosts datoteci), `deploy/provera.sh`, spisak ispod tabele. Zatim opterecenje i proba povratka kopije (ispod). Ako Docker Desktop nije instaliran, proba ide na klijentovom staging-u, a izvestaj kaze da lokalno NIJE pokrenuta. |
| T3 | `msgattrib --untranslated --no-obsolete` za en je prazan |
| T4 qa | Nove klase u `test_prikazi.py` (spisak ispod tabele). U `test_tok.py`: ceo tok uz CSP bez gresaka u konzoli, 404 i 429 na 375 px. Snimci 320, 375 i 1440 px. |
| T4 security | Pregleda `settings_prod.py`, `deploy/nginx.conf` (prepisan X-Forwarded-Proto, gunicorn nedostupan spolja, limiti, 444), brojac pod bravom, filter loga, sadrzaj arhive i slike (nema baze, `.claude/` ni `.env`), CSP i kolacice. Grep logova posle probe ne nalazi token, lozinku ni seme. |

**T2, `deploy/provera.sh` proverava:**
- 80 daje 301; HSTS je prisutan;
- `/static/` stize bez prolaska kroz gunicorn;
- `GET /` daje kolacic sa `Secure`;
- `POST /potez/` preko https sa CSRF daje 200;
- `podeli` vraca `https://` URL;
- sedma prijava u minuti daje 429;
- multipart daje 415, telo od 32 KB daje 413;
- nepoznat Host daje 444;
- `/zdravlje/` daje 200 bez `Set-Cookie`.

**T2, opterecenje i povratak:**
- Skripta je stdlib, u scratchpad-u: 50 z/s, odnos 10 POST : 2 GET, 5 minuta.
- Ocekuje se p95 < 300 ms, 0 odgovora 5xx i 0 „database is locked“.
- Izmereno S se upisuje u 15.2.
- Proba povratka kopije.

**T4 qa, nove klase u `test_prikazi.py`** (pod `override_settings` sa produkcionim vrednostima):
- `podeli` daje `https://orkestrator.example/r/...`;
- strani Host daje 400 i nema linka;
- http bez zaglavlja daje 301;
- kolacici nose `Secure`;
- HSTS i CSP su na `/`, `deljeno` i moderatorskim stranama;
- 400, 403, 404 i 500 na sr i en, bez spiska ruta;
- `zdravlje` ne pravi red u `django_session`;
- brojac: sesti pokusaj je blokiran i posle praznjenja `caches`, a istovremeni pokusaji (niti) prolaze najvise 5 puta;
- telo vece od 16 KB daje 400, ne 500;
- `baza_kopija`: kopija prolazi `integrity_check` i ima iste redove.

### 15.12 Talasi i agenti po datoteci

| Talas | Datoteke | Agent |
|---|---|---|
| T0 | odgovori na P1-P4, odluke u `projekat-odluke`; `git init` (uz P4 A) | glavna sesija, uz korisnika |
| T1 (jedna poruka) | `requirements.txt`, `requirements-razvoj.txt`, `orkestrator/settings.py`, `orkestrator/settings_prod.py` (nova), `orkestrator/greske.py` (filter loga), `igra/models.py` i `igra/migrations/0012_pokusaj_prijave.py` (uz P2 A), `igra/forme.py`, `igra/views.py` (`zdravlje`), `orkestrator/urls.py`, `igra/management/commands/baza_kopija.py` (nova) | backend-senior |
| T1 | `templates/400.html`, `403.html`, `404.html`, `500.html` (nove), `static/igra/igra.css` ako treba | frontend-medior |
| T1 | `Dockerfile`, `.dockerignore`, `.gitignore`, `compose.yaml`, `deploy/nginx.conf`, `deploy/gunicorn.conf.py`, `deploy/env.primer`, `deploy/odrzavanje.sh`, `deploy/provera.sh`, `deploy/robots.txt`, `DEPLOY.md` | devops |
| T2 (jedna poruka) | `locale/{en,sr}/LC_MESSAGES/django.po` (`makemessages`) / proba u Docker-u i opterecenje | backend-senior / devops |
| T3 | en `.po`, `.mo` (`compilemessages`) | translate |
| T4 (jedna poruka) | `igra/tests/test_prikazi.py`, `test_tok.py` / samo citanje | qa / security |
| posle T4 | dokumenti iz 15.14, posle odobrenja korisnika; poruka klijentu uz DEPLOY.md i go/no-go spisak | glavna sesija |

**Ugovor** (menja ga samo glavna sesija):
- Okruzenje:
  - `DJANGO_SETTINGS_MODULE=orkestrator.settings_prod`, `DJANGO_SECRET_KEY`;
  - `DJANGO_ALLOWED_HOSTS` (zarezom), `DJANGO_CSRF_TRUSTED_ORIGINS`;
  - `DJANGO_BAZA=/data/db.sqlite3`, `DJANGO_HSTS_SEKUNDI`, `DOMEN`.
- `STATIC_ROOT=/app/staticfiles`; gunicorn `0.0.0.0:8000`, 4 radnika `sync`.
- Ruta `zdravlje/` (ime `zdravlje`), GET: `{"ok": true}`.
- Komanda `baza_kopija PUTANJA`: postojeca putanja daje `CommandError`.
- Imena kolacica i ruta se ne menjaju.

### 15.13 Rizici i tacke bez povratka

| Rizik | Mesto | Mera |
|---|---|---|
| Rad sa `DEBUG=True` i javnim kljucem | settings.py:8-13 | `settings_prod` bez rezerve za kljuc; modul je u Dockerfile-u; `check --deploy` je u proveri |
| „database is locked“ pod opterecenjem | settings.py:56-63 (nema WAL ni timeout-a) | WAL, `timeout` 5, proba opterecenja |
| Brojac prijave po procesu (20 pokusaja umesto 5) | settings.py:97-111, forme.py:54-75 | P2 |
| PBKDF2 zauzme sve radnike | forme.py, prijava | globalna stopa prijava 2/s bez `nodelay`, 6 pokusaja u minuti po IP-u (S1); IPv4 samo dok se ne uvede kljuc po /64 (S2) |
| Tabela sesija raste od botova | views.py:190-194 | `clearsessions`, ogranicenje novih sesija, uzbuna za disk |
| Petlja preusmeravanja ili 403 na POST-u iza proxy-ja | django-nginx-docker, pravila 1 i 2 | proxy zaglavlja, `CSRF_TRUSTED_ORIGINS`, provera POST-a preko https |
| Kopija baze ili upiti u isporuci | koren projekta, `.claude/usage/` | P4 A, `.dockerignore`, security proverava sliku |
| Token u logovima | views.py:145, Nginx log | filter i `map` |
| `collectstatic` pada na source map-i | bootstrap-5.3.8.min.css:6 | bez Manifest skladista |
| Stari tekst „pri isporuci DatabaseCache“ | plan-moderator.md:357 | ispravka (15.14) |
| Python 3.14 i gunicorn zajedno nisu provereni | - | dokaz T2 |

**Tacke bez povratka:**
- **Nadogradnja Django-a.** Vraca se pinom. Odobrava korisnik (P3).
- **`migrate` 0012 na lokalnoj bazi.** Prethodi joj kopija; pokrece backend-senior. Odobrava korisnik potvrdom plana.
- **Javno pustanje (DNS na server).** Odobrava klijent posle go/no-go spiska (15.8).
- **HSTS na godinu dana.** Pregledaci pamte zahtev za HTTPS i ne mogu da se vrate. Odobrava klijent posle 14 dana rada. Preload samo uz posebnu odluku.
- **Gubitak `SECRET_KEY`.** Gase se sve sesije i partije. Kljuc cuva administrator van servera.
- **Svaka migracija produkcione baze.** Kopija pre nje; pokrece administrator.

### 15.14 Izmene dokumenata (predlog; planer ih ne menja)

1. **`projekat-odluke`, novi unos.** „## 2026-11-11 · Javna isporuka. Sukob: zahtev klijenta (javno na internetu, nekoliko hiljada igraca dnevno) protivreci CLAUDE.md (django-nginx-docker se ne koristi), `projekat-standardi` pravilu 3 (bez Docker-a i Nginx-a) i MVP 2 (isporuka van opsega). Odluka: <P1>; SQLite u WAL modu ostaje; `settings_prod.py`; ogranicenje brzine na Nginx-u; brojac prijave <P2>; Django 6.0.8 <P3>; kod stize <P4>. Odlucio: korisnik, <datum>.“ Uz P2 A jos jedan unos: sesti model `PokusajPrijave`.
2. **`projekat-standardi`, pravilo 3.** „Bez Docker-a, Nginx-a i MySQL-a“ postaje „Bez MySQL-a. Javna isporuka: Docker Compose, Nginx i gunicorn (`Dockerfile`, `compose.yaml`, `deploy/`), po odluci 2026-11-11.“ Uz P2 A „Pet modela“ postaje „Sest modela“ i dodaje se `PokusajPrijave`.
3. **`projekat-standardi`, tabela.**
   - Red „Django i SQLite“: „SQLite u WAL modu, i na serveru; `settings.py` lokalno i u testovima, `settings_prod.py` na serveru“.
   - Prikazima se dodaje „`zdravlje` (GET, JSON, bez sesije)“.
   - Komandama se dodaje `baza_kopija`.
   - Sablonima se dodaju „strane gresaka `400`, `403`, `404`, `500.html`“.
4. **`MVP.md`** (menja korisnik):
   - Odeljak 2: u MVP-u „javna isporuka na https://orkestrator.example (dodato 2026-11-11)“; van MVP-a ostaje „MySQL“.
   - MVP:48 postaje „Link vodi na https://orkestrator.example/r/<token>/.“
   - MVP:80 postaje „Prvog glavnog moderatora pravi administrator komandom, po DEPLOY.md.“
   - Odeljak 6: „Radi lokalno za razvoj, a javno iza Nginx-a i TLS-a, u Docker-u.“
   - Uslov 13: „Igra radi na https://orkestrator.example; `check --deploy` je bez nalaza; periodicni zadaci i kopije rade, a povratak kopije je proban; DEPLOY.md je proveren od praznog servera.“
5. **`CLAUDE.md`.**
   - Red 6: „Skill `django-mysql` se ovde ne koristi; `django-nginx-docker` vazi za `settings_prod.py`, `Dockerfile`, `compose.yaml` i `deploy/`.“
   - Red implementacije: „`backend-senior`; `frontend-medior`; `devops` | ...; Docker, Nginx, periodicni zadaci i DEPLOY.md“.
6. **plan-moderator.md:357.** „pri isporuci `DatabaseCache`“ postaje „pri isporuci zajednicki brojac (15.2, P2); `DatabaseCache` ne“.
7. **`projekat-domen/references/parametri.md`, odeljak „Moderator“, dodatak:** „Na serveru brojac je zajednicki svim procesima (odluka P2); Nginx dodatno ogranicava prijavu po IP-u.“

**Posle odobrenja: implementacija u NOVOJ sesiji**; kontekst planiranja ne treba implementaciji.
