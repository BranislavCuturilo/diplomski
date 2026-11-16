---
name: projekat-standardi
nivo: 2
preovladjuje: [craft-code, stack-django]
description: >
  Standardi igre Orkestrator: gde stoji motor igre, kako izgledaju prikazi, sesija,
  ekran i testovi, i koje tehnologije se ne koriste. Ucitaj PRE svake izmene koda,
  sablona ili testa u ovom projektu. Preovladjuje nad opstim pravilima kada im
  protivreci. Okidaci: bilo koja izmena koda, sablona ili testa u projektu.
---

# projekat-standardi (nivo 2)

Ovo su standardi OVOG projekta. Nisu nuzno najbolja praksa; nova funkcionalnost
mora izgledati kao postojeca.

## Tri pravila koja se nikad ne preskacu

1. **Motor je cist Python.** `igra/motor.py` ne uvozi Django: prima stanje i izbore,
   vraca novo stanje. Svi brojevi su u `igra/parametri.py`, nijedan u motoru.

2. **Stanje je recnik JSON tipova u `request.session["igra"]`** (obicna igra) **ili `request.session["dnevna"]`**
   (dnevni izazov, odluka 2026-11-12). Posle izmene kljuc se ponovo dodeljuje: izmena ugnezdenog
   recnika sama ne upisuje sesiju. Dnevno stanje nosi `dan` i nasumicnu `oznaka`; hes partije se
   racuna iz `oznaka`, jer dnevni igraci dele seme.

3. **Osam modela; nalozi samo za moderatore.** Aplikacija `igra` ima modele `Rezultat`,
   `NepodobnoIme`, `DeljeniRezultat`, `ZapisDnevnika` (nepromenljiv, 365 dana),
   `NalogModeratora`, `PokusajPrijave` (brojac neuspeha, zajednicki svim procesima) i `PrijavaImena`
   (prijava neprikladnog imena, jedna po rezultatu i sesiji, odluka 2026-11-12) i `ZavrsenaPartija` (dan, vrsta i poeni
   svake partije koja stigne do zavrsnog ekrana, samo za statistiku, 7 dana; odluka 2026-11-12) i njihove migracije; stanje partije je samo u sesiji. Moderator je
   `django.contrib.auth` korisnik sa dozvolom `igra.moderira`, glavni ima i
   `igra.upravlja_nalozima`; igraci nemaju naloge. Brisanje, i odluka da prijavljeno ime ostaje, ide
   samo kroz `igra/brisanje.py`, radnje nad nalozima samo kroz `igra/nalozi.py`; oba ponovo proveravaju
   ulogu pod bravom i upisuju dnevnik u istoj transakciji. Izmena ogranicenja na tabeli dnevnika prepravlja
   tabelu i brise okidace nepromenljivosti: ista migracija ih pravi ponovo (kao `0014`). Bez admina. Bez
   MySQL-a. Javna isporuka: Docker Compose, Nginx i gunicorn (`Dockerfile`, `compose.yaml`, `deploy/`).
   *Poreklo: odluke 2026-11-10, 2026-11-11 i 2026-11-12 u `projekat-odluke`.*

## Standardi

| Pravilo | Zasto u ovom projektu | Koje opste pravilo pada |
|---|---|---|
| Django i SQLite (WAL), jedna aplikacija `igra`; `settings.py` lokalno i u testovima, `settings_prod.py` na serveru; ruta `zdravlje` (GET, JSON, bez sesije); komanda `baza_kopija`; strane gresaka `400`, `403`, `404`, `500.html` | jedan server izdrzava procenjeno opterecenje (plan 15.2) | nijedno |
| Dnevni izazov: rute `dnevni/`, `dnevni/potez/`, `dnevni/sacuvaj/`, `dnevni/podeli/` (bez `dnevni/nova/`); `potez`, `sacuvaj` i `podeli` primaju `vrsta`; `Rezultat.dan` (null = obicna igra); svaki citac liste ide kroz `glavna()` ili `dana(dan)`; dan cita samo `_danas()` u `views.py`; seme dana kroz `_dnevno_seme`, nikad iz sirovog datuma | isti kod za obe igre, liste se ne mesaju | nijedno |
| Prikazi su funkcije: `pocetna` (GET), `potez` (POST, JSON), `nova` (POST), `sacuvaj` (POST, JSON), `podeli` (POST, JSON), `prijavi` (POST, JSON), `deljeno` (GET, samo citanje), `jezik` (POST, Django `set_language`) | tanki prikazi i Django `set_language`; motor racuna, `sacuvaj` i `podeli` jos upisuju model u istoj transakciji sa sesijom; `deljeno` ne dira sesiju ni CSRF kolacic; moderatorski prikazi su u `igra/moderacija.py`, pod `moderator_potreban`, a `nalozi*` pod `glavni_potreban` (403); obicne forme sa POST i preusmerenjem, bez skripte; `sacuvaj`, `podeli` i `prijavi` proveravaju dnevnik | stack-django: primeri u `views.md` su klase |
| Istorija pregledaca: kljuc sesije `istorija`, najvise `p.ISTORIJA_MAKS` stavki, samo polja javna na zavrsnom ekranu; upis i `ZavrsenaPartija` u `potez`, u istoj bravi (`_upisi_istoriju`, `_zabelezi_zavrsenu`); `odjava` prenosi `istorija` uz `igra` i `dnevna` | "svoje partije" bez naloga igraca (odluka 2026-11-12) | nijedno |
| Javna rang lista: `api/rang-lista/` (GET, JSON, bez sesije i kolacica, CORS `*`, kes 60 s, zona `api` u Nginx-u); polja kao na strani, kljuc ocene, ISO datum, nikad id ni oznaka reda | partneri preuzimaju listu (odluka 2026-11-12) | nijedno |
| Prijava imena: ruta `prijavi/` (jedna za obe strane, bez `vrsta`), telo `{"red": oznaka}`; red liste nosi javnu oznaku `red` iz `_oznaka_reda` (HMAC partije, nikad id); prijavu upisuje samo sesija sa partijom, a ne upisuje sesiju; moderator odlucuje na pregledu: postojeca potvrda brisanja ili `moderator/rezultat/<id>/ostavi/` (samo POST) | klijent imenuje red bez id-a i partije; prijava nista ne sakriva | nijedno |
| `igra/imena.py` je cist Python kao motor: pravila imena i `kljuc_imena` | testira se bez servera | nijedno |
| Datum za prikaz formatira prikaz, `%d.%m.%Y` u `TIME_ZONE = 'Europe/Belgrade'`; skripta ga samo ispisuje | isti datum u svakom pregledacu | nijedno |
| Rucne izmene podataka: komande `nepodobno_dodaj`, `nepodobno_ukloni`, `rezultati`, `rezultat_obrisi`, `deljeni`, `deljeni_obrisi`, `deljeni_ocisti`, `moderator_dodaj`, `moderator_lozinka`, `moderator_glavni`, `moderator_deaktiviraj`, `moderatori`, `dnevnik_ocisti`; brisanja kroz komande pisu dnevnik; lozinka samo kroz `getpass` | nema admina; razvijalac je rezerva za naloge | nijedno |
| Tri sablona: `templates/igra/igra.html` (igra), `deljeno.html` (deljeni rezultat, samo citanje) i `kako.html` (pravila i primer kruga, `kako-se-igra/`, bez sesije; brojevi iz `parametri` i motora, bez sanse i tihih zadataka); zajednicki delovi `_ikone.html`, `_zavrsni.html`, `_glava.html`, `_polje.html` i `_prijava.html` (blok prijave imena ispod svake liste) kroz `{% include %}`; moderatorske strane u `templates/igra/moderator/` nasledjuju `osnova.html` | zavrsni ekran izgleda isto na obe strane, bez kopije | nijedno |
| `static/igra/igra.js`, bez biblioteka i bez koraka gradnje; ista skripta na obe strane, grana po `#deljeni-rezultat` | browser samo prikazuje stanje | nijedno |
| Zvuk ishoda kruga: Web Audio u `igra.js`, bez datoteka; bira se SAMO po javnom kljucu statusa; izbor u `localStorage` `orkestrator.zvuk`, podrazumevano iskljucen | uspeh i tih neuspeh zvuce isto (odluka 2026-11-12) | nijedno |
| Bootstrap 5 preko jednog `<link>` sa tacnom verzijom | bez npm-a | nijedno |
| Tekst na ekranu na srpskom (cirilica) i engleskom, kroz Django i18n; izvor (msgid) je odobren srpski tekst; kod latinicom bez dijakritika | srpski ostaje izvor, engleski se menja samo u `.po` | nijedno |
| Motor i `parametri.py` vracaju kljuceve, nikad prevedeni tekst; tekst u `parametri.py` oznacen lokalnom `gettext_noop`, bez uvoza Django-a; prevode samo `igra/tekstovi.py` i sabloni | motor ostaje cist, JSON ne zavisi od jezika | nijedno |
| Tekst skripte stize kroz `json_script` `tekstovi`, bez `JavaScriptCatalog`; skripta samo popunjava `%(ime)s` | jedan katalog, bez dodatnog zahteva | nijedno |
| Formati po jeziku (datum, zarez, novac, minuti) u `tekstovi.FORMATI`, nikad u `.po`; datum `d.m.Y` za `sr`, `Y-m-d` za `en` | craft-i18n: kodovi formata se ne prevode | nijedno |
| Katalozi `locale/{en,sr}/LC_MESSAGES/django.po` i `.mo` su u projektu; `sr` nosi samo mnozinu | server i testovi bez gettext-a u PATH-u | nijedno |
| Komande i log ostaju srpski latinicom | jedan jezik za pretragu | nijedno |
| Jezik: prikaz `jezik` na `jezik/` (samo POST) propusta samo kod iz `LANGUAGES` (inace 400 bez kolacica), pa zove Django `set_language`; nikad `set_language` direktno, jer prihvata svaki kod sa Django katalogom i keš prevoda raste bez granice (revizija 2026-11-11); kolacic 365 dana, bez prefiksa u URL-u; deljena strana menja jezik linkom `?jezik=` bez kolacica | link za deljenje je isti za sve jezike | nijedno |
| Testovi: `igra/tests/test_motor.py`, `test_prikazi.py`, `test_tok.py` | motor i `imena` bez servera, prikazi i komande kroz Django klijent, tok kroz Playwright | qa: pytest; ovde Django test runner, jer pytest nije instaliran |
| Pokretanje testova: `python "${CLAUDE_PLUGIN_ROOT}/tools/test_summary.py" --brzo` tokom rada, bez `--brzo` jednom na kraju | vraca samo sazetak; pregledac je 90 % trajanja | nijedno |

## Kako agent postupa

0. Standard je podrazumevana vrednost, ne zabrana. Zahtev klijenta koji trazi nesto sto standard
   iskljucuje (model, nalog, Docker) menja standard BEZ pitanja; promena se upisuje u
   `projekat-odluke` i u ovaj fajl.
1. Ako opste pravilo i ovaj skill kazu razlicito: vazi ovaj skill.
2. Ako dva skilla NIVOA 2 kazu razlicito: STANI, pitaj korisnika, upisi odluku u
   `projekat-odluke` (nivo 3).
