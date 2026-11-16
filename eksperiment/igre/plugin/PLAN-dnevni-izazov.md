# Plan: dnevni izazov (2026-11-12)

Zahtev: svakog dana svi igraju istu partiju (isti zadaci, isti ishodi); pocetni ekran pored glavne igre
prikazuje i rang listu dana. Obicna igra, glavna lista i bodovanje ostaju isti. Iznad praga (seme baze sa
podacima, poeni koji se cuvaju, isporuka): planer pa talasi.

## Pitanja

Pitanja coveku: **nema**. Nista nije nepovratno pre isporuke i nista se ne kosi sa tekstom klijenta. Sve
ispod su odluke po preporuci ("Odluke za potvrdu" na kraju).
Utvrdjeno u kodu: zadaci idu fiksnim redom (`parametri.ZADACI`, krug 1-8), pa su "isti zadaci" isti sami
od sebe. "Isti ishodi" daje isto seme: `uspeh_kruga` baca istu kocku po krugu, a sansa zavisi od izbora.

**Glavni nalaz:** `motor.oznaka_partije` = sha256(seme). Sa istim semenom svi dnevni igraci dobijaju isti
hes, pa `Rezultat.partija` (unique) pusta samo prvog igraca, a brisanje jednog reda (dnevnik po partiji)
blokira sve. Zato dnevno stanje nosi nasumicnu `oznaka`, a hes se racuna iz nje.

## Dogovorena imena

| Sta | Ime |
|---|---|
| kljuc sesije | `igra` (obicna, ostaje), `dnevna` (nova) |
| nova polja stanja (samo dnevna) | `dan` = "YYYY-MM-DD" (Europe/Belgrade, dan pocetka), `oznaka` = `secrets.token_hex(16)` |
| motor | `nova_igra(seme, dan=None, oznaka=None)`: kljucevi samo kad nisu None; `dan_partije(stanje)` = `stanje.get("dan")`; `oznaka_partije` hesira `stanje.get("oznaka", stanje["seme"])`; `za_cuvanje` dodaje `"dan"` (ISO ili None, prikaz pretvara u `date`) |
| seme dana (views) | `_danas()` = `timezone.localdate()` (jedino mesto koje cita dan; testovi ga zamenjuju); `_dnevno_seme(dan)` = `salted_hmac("igra.dnevni_izazov", dan.isoformat(), algorithm="sha256").hexdigest()`; `_nova_dnevna(dan)` |
| prikazi | `potez`, `sacuvaj`, `podeli` dobijaju `vrsta="obicna"`; `SESIJA = {"obicna": "igra", "dnevna": "dnevna"}`; nov `dnevni` (GET, `ensure_csrf_cookie`, `never_cache`) |
| URL (name) | `dnevni/` (`dnevni`), `dnevni/potez/` (`dnevni_potez`), `dnevni/sacuvaj/` (`dnevni_sacuvaj`), `dnevni/podeli/` (`dnevni_podeli`), sa `{"vrsta": "dnevna"}` u `path`. **Nema** `dnevni/nova/` |
| model | `Rezultat.dan = DateField(null=True, blank=True, editable=False)`; indeks `igra_dan_rang_idx` (`dan`, `-poeni`, `sacuvan`, `id`); migracija `0013_rezultat_dan.py` (AddField + AddIndex, bez RunPython) |
| QuerySet | `glavna()` = `dan__isnull=True`; `dana(dan)` = `dan=dan`; `po_rangu` i `najboljih` ostaju; SVAKI citac liste ide kroz `glavna()` ili `dana()` |
| kontekst sablona | `vrsta` ("obicna"/"dnevna"), `adrese` {`potez`, `sacuvaj`, `podeli`, `strana`}, `dnevni` {`datum`} (samo dnevna strana), `rang` (lista ove strane), `rang_dana` (samo pocetna) |
| json_script | postojeci `stanje-igre`, `rang-lista`, `tekstovi`; nov `rang-dana` (samo pocetna, isti oblik `{lista, sacuvano, moj}`) |
| HTML id | `#rang-dana`, `#rang-dana-naslov`, `#rang-dana-tabela`, `#rang-dana-redovi`, `#rang-dana-prazno`, `#dnevni-dugme` (link na `dnevni`), `#nazad-dugme` (dnevna strana -> `pocetna`) |
| greske i statusi | bez novih: `nema_igre`, `igra_zavrsena`, `pogresan_krug`, `vec_sacuvano`, `igra_nije_zavrsena`, `deljenje_isteklo`; `gotovo`/`vraceno na doradu` isti |
| tekst (sr -> en) | "Дневни изазов" -> "Daily challenge"; "Ранг листа дана" -> "Today's leaderboard"; "Играј дневни изазов" -> "Play the daily challenge"; "Назад на главну игру" -> "Back to the main game"; "Данас још нема сачуваних резултата." -> "No saved results today yet."; "Данас сви играју исту партију: исти задаци и исти исходи. Дневни изазов се игра једном." -> "Today everyone plays the same game: the same tasks and the same outcomes. The daily challenge is played once."; moderator: "Главна ранг листа" -> "Main leaderboard", "Дневни изазов, данас" -> "Daily challenge, today", oznaka u dnevniku "дневни изазов" -> "daily challenge" |

## Ponasanje (ugovor)

- `GET dnevni/`: nema `dnevna` u sesiji ili `dan` != `_danas()` -> nova dnevna partija danas. Inace ista
  partija (tekuca ili zavrsena). Ponovna igra istog dana ne postoji u istoj sesiji.
- `dnevni/potez|sacuvaj|podeli`: kao obicni, nad `session["dnevna"]`; bez stanja 409 `nema_igre` (ne pravi
  partiju). Potez i cuvanje posle ponoci rade po `dan` partije; red ide na listu tog dana.
- `nova` dira samo `igra`. Moderatorska `odjava` prenosi i `igra` i `dnevna` u novu sesiju.
- Pocetna: `rang` = `glavna()`; `rang_dana` = `dana(_danas())`, `moj` samo ako je `dnevna.dan` == danas.
- Seme dana i `oznaka` nikad u HTML/JSON/kolacic; `javni_prikaz` se ne menja (bez `dan`).
- Moderator `pregled`: dve tabele (`rezultati` = glavna, `rezultati_dana` = danas); `_mesto` broji u istoj
  listi (`dan` isti ili oba null); `javno` = mesto <= 10 i lista je glavna ili danasnja. `brisanje._snimak`
  dobija kljuc `dan` (ISO) samo za dnevni red; `_opis_snimka` ga prikazuje kao oznaku.
- Komanda `rezultati`: glavna lista kao do sada; `--dan YYYY-MM-DD` ispisuje listu tog dana; `opis_reda` dobija `dan=`.

## Faze, talasi, agent po datoteci

Pre svake faze: `faza.py <ime faze>` (planer ga nije pokrenuo: nema shell alat).

**Talas 1 (paralelno, 3 agenta)**

| Datoteka | Agent |
|---|---|
| `igra/motor.py`, `igra/models.py`, `igra/migrations/0013_rezultat_dan.py`, `igra/views.py`, `orkestrator/urls.py`, `igra/moderacija.py`, `igra/brisanje.py`, `igra/management/commands/rezultati.py` | backend-senior |
| `templates/igra/igra.html`, `templates/igra/_zavrsni.html` (`data-url-*` iz `adrese`, deljena strana bez forme kao do sada), `templates/igra/moderator/pregled.html`, `templates/igra/moderator/dnevnik.html`, `static/igra/igra.js` (crtanje liste parametrizovano ciljem; `rang-dana` samo citanje), `static/igra/igra.css` | frontend-medior |
| `deploy/nginx.conf` (`= /dnevni/` zona `strana`, `= /dnevni/potez/` zona `potez`, `^/dnevni/(sacuvaj\|podeli)/$` zona `akcije`), `deploy/provera.sh` (GET `/dnevni/` 200), `DEPLOY.md` (migracija 0013; promena `DJANGO_SECRET_KEY` menja partiju dana, raditi posle ponoci) | devops |

Dokaz: `manage.py check`, `makemigrations --check --dry-run` bez izmena, ceo postojeci paket kroz
`test_summary.py` prolazi (obicna igra nepromenjena); `nginx -t` u kontejneru; rucno `/` i `/dnevni/` bez greske u konzoli.

**Talas 2 (1 agent, treba tekst iz talasa 1)**

| Datoteka | Agent |
|---|---|
| `locale/en/LC_MESSAGES/django.po`, `.mo`; `locale/sr/LC_MESSAGES/django.po`, `.mo` (makemessages, en prevod, compilemessages) | frontend-medior |

Dokaz: nijedan nov `msgstr` prazan, `msgfmt --check` prolazi, `/dnevni/` na `en` pokazuje "Daily challenge".

**Talas 3: kontrolni skup (jedna poruka)**

| Datoteka | Agent |
|---|---|
| `igra/tests/test_motor.py`, `test_prikazi.py`, `test_tok.py` | qa |
| revizija izmenjenih datoteka (bez pisanja) | security |

qa mora da pokrije: (1) isti dan -> isto seme u dve sesije, drugi dan drugacije; seme nije funkcija
samog datuma (zamena `SECRET_KEY` menja seme); (2) seme i njegov sha256 nisu ni u jednom odgovoru
(`dnevni`, potezi, `sacuvaj`, `podeli`, `deljeno`); (3) dva klijenta, isti izbori -> isti JSON svih 8 poteza;
(4) **dva igraca istog dana oba cuvaju** (bez IntegrityError), brisanje jednog ne blokira drugog;
(5) dnevni red nije na glavnoj listi, obicni nije na listi dana; lista dana samo danas, 10, redosled;
(6) ponovni `GET dnevni/` vraca istu partiju; sledeci dan nova; potez i `sacuvaj` posle ponoci upisuju stari `dan`;
(7) `nova` ne dira `dnevna`; `dnevni/nova/` 404; `dnevni/potez/` bez stanja 409; odjava moderatora cuva `dnevna`;
(8) migracija 0013 na bazi sa redovima: `dan` null, glavna lista ista; (9) `rang-dana` parsira u `dict`,
jezik `en` stvarno aktivan; (10) Playwright: pocetna -> dnevni -> 8 krugova -> cuvanje -> pocetna pokazuje red na listi dana.
security: curenje semena/oznake, `salted_hmac` so, sudar hesa partije, CSRF na novim POST rutama, odjava, ponovna igra kroz novu sesiju.
Dokaz: ceo paket zelen; na doradu samo visoki i srednji nalazi, najvise jedna ponovna provera.

**Dokumentacija (glavna sesija, uz talas 2):** `.claude/skills/projekat-odluke/SKILL.md` (nova odluka
"2026-11-12 · Dnevni izazov": sukob sa standardom 2 (jedan kljuc sesije), domenom 2 (seme samo nasumicno,
hes = sha256 semena) i domenom 7 (jedna lista); odluka = ovaj plan; razlog: zahtev klijenta),
`projekat-standardi/SKILL.md` (dva kljuca sesije, rute `dnevni*`, `Rezultat.dan`, i dalje sest modela),
`projekat-domen/SKILL.md` (tok "Dnevni izazov", lista dana, seme dana, hes partije iz oznake, recnik),
`projekat-domen/references/parametri.md` (lista dana = `RANG_MESTA`, dan po Europe/Belgrade, poreklo).

## Tacke bez povratka

- `migrate` 0013 na produkcionoj bazi: tek posle `baza_kopija` (DEPLOY.md); povratak brise dnevne redove.
  Odobrava korisnik pri isporuci.
- Isporuka (javni server): odobrava korisnik; izvodi klijentov administrator po DEPLOY.md.

## Rizici

- Bez naloga ponovna igra je moguca brisanjem kolacica; ko je odigrao zna kocku po krugu i moze bolje.
  Isto vazi za igrace koji razmenjuju ishode. Ne moze se zatvoriti bez naloga; prihvata se (odluka 1).
- Propusten citac liste bez `glavna()` mesa liste: test (5) i pretraga `objects.najboljih`/`po_rangu` u reviziji.
- Rotacija `SECRET_KEY` usred dana: dve razlicite partije istog dana (DEPLOY.md napomena).

## Odluke za potvrdu

1. Dnevna partija jednom po sesiji i danu: dnevna strana nema "Нова игра", ponovni ulaz vraca tekucu ili zavrsenu.
2. Cuvanje: polje `Rezultat.dan` (null = obicna), ne nov model; ostaje sest modela; brisanje, moderacija,
   dnevnik, deljenje i verzija pravila rade istim kodom; postojeci redovi dobijaju null, bez migracije podataka.
3. Lista dana: 10 najboljih sa `dan` = danas (Europe/Belgrade), isti redosled i ista polja kao glavna; posle
   ponoci prazna; ranijih dana nema na ekranu (ostaju u bazi, bez arhive).
4. Ponoc: partija pamti dan pocetka i cuva se na listu tog dana; ponovno ucitavanje dnevne strane posle
   ponoci pocinje partiju novog dana (nezavrsena ili nesacuvana jucerasnja se gubi).
5. Dnevni rezultat ne ide na glavnu listu, obican ne ide na listu dana.
6. Dnevna partija se boduje po tekucim pravilima (2); deljenje radi isto, deljena strana bez oznake dnevnog.
7. Moderator vidi glavnu listu i listu danas; starije dnevne redove brise samo komanda `rezultat_obrisi`;
   zapis dnevnika dnevnog reda nosi `dan`.
8. Engleski tekst pravimo mi; klijent ga pregleda zajedno sa ostalim engleskim tekstom.

Posle plana: implementacija u NOVOJ sesiji (kontekst planiranja joj ne treba).
