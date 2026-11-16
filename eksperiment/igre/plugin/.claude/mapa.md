# Mapa projekta

Napravljena iz koda (`tools/mapa.py`); sadrzaj datoteka cita radnik, ne glavna sesija.

## Dokumenti

- `CLAUDE.md` (20 redova): Igra Orkestrator
- `DEPLOY.md` (519 redova): Orkestrator: postavljanje na server
- `MVP.md` (206 redova): MVP: igra Orkestrator
- `PLAN-dnevni-izazov.md` (100 redova): Plan: dnevni izazov (2026-11-12)
- `plan-bodovanje.md` (80 redova): 13. Novo bodovanje (2026-11-11)
- `plan-isporuka.md` (312 redova): 15. Javna isporuka (2026-11-11)
- `plan-jezik.md` (197 redova): 12. Srpski i engleski (2026-11-11)
- `plan-moderator.md` (355 redova): 14. Moderator (2026-11-11)
- `plan.md` (721 redova): Plan izrade: igra Orkestrator

## Rute

- `/` -> `views.pocetna` ime `pocetna` (`orkestrator/urls.py`)
- `/potez/` -> `views.potez` ime `potez` (`orkestrator/urls.py`)
- `/nova/` -> `views.nova` ime `nova` (`orkestrator/urls.py`)
- `/sacuvaj/` -> `views.sacuvaj` ime `sacuvaj` (`orkestrator/urls.py`)
- `/podeli/` -> `views.podeli` ime `podeli` (`orkestrator/urls.py`)
- `/dnevni/` -> `views.dnevni` ime `dnevni` (`orkestrator/urls.py`)
- `/dnevni/potez/` -> `views.potez` ime `dnevni_potez` (`orkestrator/urls.py`)
- `/dnevni/sacuvaj/` -> `views.sacuvaj` ime `dnevni_sacuvaj` (`orkestrator/urls.py`)
- `/dnevni/podeli/` -> `views.podeli` ime `dnevni_podeli` (`orkestrator/urls.py`)
- `/prijavi/` -> `views.prijavi` ime `prijavi` (`orkestrator/urls.py`)
- `/r/<str:token>/` -> `views.deljeno` ime `deljeno` (`orkestrator/urls.py`)
- `/jezik/` -> `views.jezik` ime `jezik` (`orkestrator/urls.py`)
- `/zdravlje/` -> `views.zdravlje` ime `zdravlje` (`orkestrator/urls.py`)
- `/moderator/prijava/` -> `moderacija.prijava` ime `moderator_prijava` (`orkestrator/urls.py`)
- `/moderator/odjava/` -> `moderacija.odjava` ime `moderator_odjava` (`orkestrator/urls.py`)
- `/moderator/` -> `moderacija.pregled` ime `moderator` (`orkestrator/urls.py`)
- `/moderator/rezultat/<int:broj>/` -> `moderacija.rezultat` ime `moderator_rezultat` (`orkestrator/urls.py`)
- `/moderator/rezultat/<int:broj>/ostavi/` -> `moderacija.ostavi` ime `moderator_ostavi` (`orkestrator/urls.py`)
- `/moderator/link/<int:broj>/` -> `moderacija.link` ime `moderator_link` (`orkestrator/urls.py`)
- `/moderator/izvoz/glavna.csv` -> `moderacija.izvoz_glavne` ime `moderator_izvoz_glavne` (`orkestrator/urls.py`)
- `/moderator/izvoz/dnevna.csv` -> `moderacija.izvoz_dana` ime `moderator_izvoz_dana` (`orkestrator/urls.py`)
- `/moderator/dnevnik/` -> `moderacija.dnevnik` ime `moderator_dnevnik` (`orkestrator/urls.py`)
- `/moderator/lozinka/` -> `moderacija.lozinka` ime `moderator_lozinka` (`orkestrator/urls.py`)
- `/moderator/nalozi/` -> `moderacija.spisak_naloga` ime `moderator_nalozi` (`orkestrator/urls.py`)
- `/moderator/nalozi/<int:broj>/` -> `moderacija.nalog` ime `moderator_nalozi_nalog` (`orkestrator/urls.py`)

## Modeli i polja

- `Rezultat` (`igra/models.py`): id, ime, poeni, ocena, pravila, sacuvan, partija, dan
- `NepodobnoIme` (`igra/models.py`): id, kljuc
- `DeljeniRezultat` (`igra/models.py`): id, token, partija, zavrsni, nastao, istice
- `ZapisDnevnika` (`igra/models.py`): id, kada, radnja, ko, nad, red, partija, snimak
- `NalogModeratora` (`igra/models.py`): korisnik, mora_promeniti
- `PokusajPrijave` (`igra/models.py`): kljuc, broj, istice
- `PrijavaImena` (`igra/models.py`): id, rezultat, sesija, kada

## Python moduli

- `manage.py` (18 redova): funkcije main
- `deploy/opterecenje.py` (310 redova): klase _HttpsSaSni, Klijent, Merenje, Partija; funkcije upamti_kolacice, procenat, zdravlje, pokreni, izvestaj, main
- `deploy/proba-prijave.py` (140 redova): funkcije kontekst, tls_veza, procitaj_odgovor, rani_odgovor, obicna_prijava, main
- `igra/apps.py` (3 redova): klase IgraConfig
- `igra/brisanje.py` (106 redova): klase NemaReda, NemaPrijava; funkcije _redovi, _snimak, obrisi_rezultate, obrisi_deljene, odbaci_prijave
- `igra/forme.py` (160 redova): klase PrijavaForma, PotvrdaForma, LozinkaNalogaForma, DodajForma, PromenaLozinkeForma; funkcije _kljuc, rezervisi_pokusaj, zabelezi_neuspeh, obrisi_neuspehe, _proveri_sopstvenu, _polje_lozinke
- `igra/imena.py` (78 redova): funkcije ime_ispravno, kljuc_imena
- `igra/models.py` (305 redova): klase RezultatQuerySet, NepodobnoImeQuerySet, DeljeniRezultatQuerySet, ZapisQuerySet, PokusajPrijaveQuerySet, PrijavaImenaQuerySet; funkcije proveri_ime, _jedna_od
- `igra/moderacija.py` (509 redova): funkcije _kontekst, _zabranjeno, _nema, _ponovo, moderator_potreban, glavni_potreban, _rezultati, _prijavljeni, _lista_reda, _deljeni, _opis_rezultata, _mesto, _opis_prijavljenog, _opis_linka, _opis_naloga, _opis_snimka, _opis_zapisa, _sledeca, prijava, odjava, _token_iz_unosa, pregled, _celija, _csv, izvoz_glavne ... (+14)
- `igra/motor.py` (327 redova): klase NepoznatIzbor, PogresanKrug, IgraZavrsena, IgraNijeZavrsena, VecSacuvano; funkcije nova_igra, dan_partije, pravila, proveri_izbore, racun, uspeh_kruga, _zadatak, odigraj_potez, kontrolni_skup, oceni, nadogradi, sacuvani_red, za_cuvanje, oznaci_sacuvano, za_deljenje, deljeni_prikaz, podeljeni_red, oznaci_podeljeno, oznaka_partije, lekcije, _javno, procene, javne_opcije, _javni_limit, _javni_poslednji ... (+2)
- `igra/nalozi.py` (276 redova): klase Odbijeno; funkcije _dozvola, uloga, moderatori, aktivni_glavni, id_glavnih, ime_zauzeto, moderator_po_imenu, proveri_ulogu, ima_aktivnog_glavnog, _procitaj, _postoji_glavni, _glavni_je_moderator, _zahtevaj_promenu, _upisi, _hes, _isti_hes, _upisi_hes, dodaj, deaktiviraj, aktiviraj, postavi_lozinku, dodeli_ulogu, oduzmi_ulogu, promeni_svoju
- `igra/parametri.py` (206 redova): funkcije gettext_noop
- `igra/tekstovi.py` (186 redova): funkcije _format, datum, datum_vreme, ocena, blokada, opcije, _poruke, _moguce_kazne_budzeta, _budzet_kazne, za_skriptu
- `igra/views.py` (497 redova): funkcije _nova_igra, _danas, _dnevno_seme, _nova_dnevna, _datum_dana, _stanje, _dan_stanja, _lista, _podrzan_jezik, _jezik_upita, _json_telo, _procitaj_zahtev, _procitaj_ime, _procitaj_prijavu, _oznaka_reda, _red_na_listama, _sesija_prijave, _odbijen_potez, _sacuvana_partija, _javni_rang, _odbijeno_cuvanje, _odgovor_deljenja, _odbijeno_deljenje, _javni_deljeni, _novi_deljeni ... (+11)
- `igra/management/commands/baza_kopija.py` (50 redova): klase Command
- `igra/management/commands/deljeni.py` (45 redova): klase Command; funkcije imena_sa_rang_liste, opis_deljenog
- `igra/management/commands/deljeni_obrisi.py` (30 redova): klase Command
- `igra/management/commands/deljeni_ocisti.py` (12 redova): klase Command
- `igra/management/commands/dnevnik_ocisti.py` (28 redova): klase Command
- `igra/management/commands/moderator_deaktiviraj.py` (18 redova): klase Command
- `igra/management/commands/moderator_dodaj.py` (41 redova): klase Command
- `igra/management/commands/moderator_glavni.py` (23 redova): klase Command
- `igra/management/commands/moderator_lozinka.py` (29 redova): klase Command
- `igra/management/commands/moderatori.py` (77 redova): klase Command; funkcije greska_odbijanja, greska_validacije, nalog_po_imenu, unesi_lozinku, brojevi, _da
- `igra/management/commands/nepodobno_dodaj.py` (59 redova): klase Command
- `igra/management/commands/nepodobno_ukloni.py` (25 redova): klase Command
- `igra/management/commands/rezultat_obrisi.py` (26 redova): klase Command
- `igra/management/commands/rezultati.py` (37 redova): klase Command; funkcije opis_reda, _dan
- `orkestrator/greske.py` (41 redova): klase FilterBezPromenljivih, FilterLoga; funkcije _ocisti
- `orkestrator/settings_prod.py` (84 redova): funkcije _nije_postavljena, _obavezno, _spisak

## Sabloni

- `templates/400.html` (27 redova)
- `templates/403.html` (27 redova)
- `templates/403_csrf.html` (27 redova)
- `templates/404.html` (27 redova)
- `templates/500.html` (27 redova)
- `templates/igra/_glava.html` (9 redova)
- `templates/igra/_ikone.html` (55 redova)
- `templates/igra/_polje.html` (17 redova)
- `templates/igra/_prijava.html` (11 redova)
- `templates/igra/_zavrsni.html` (55 redova)
- `templates/igra/deljeno.html` (58 redova)
- `templates/igra/igra.html` (236 redova)
- `templates/igra/moderator/_rezultati.html` (23 redova)
- `templates/igra/moderator/dnevnik.html` (35 redova), nasledjuje `igra/moderator/osnova.html`
- `templates/igra/moderator/lozinka.html` (21 redova), nasledjuje `igra/moderator/osnova.html`
- `templates/igra/moderator/nalog.html` (86 redova), nasledjuje `igra/moderator/osnova.html`
- `templates/igra/moderator/nalozi.html` (44 redova), nasledjuje `igra/moderator/osnova.html`
- `templates/igra/moderator/osnova.html` (55 redova)
- `templates/igra/moderator/potvrda.html` (29 redova), nasledjuje `igra/moderator/osnova.html`
- `templates/igra/moderator/pregled.html` (107 redova), nasledjuje `igra/moderator/osnova.html`
- `templates/igra/moderator/prijava.html` (23 redova), nasledjuje `igra/moderator/osnova.html`
- `templates/igra/moderator/zabranjeno.html` (9 redova), nasledjuje `igra/moderator/osnova.html`

## Staticke datoteke

- `static/igra/igra.css` (1585 redova)
- `static/igra/igra.js` (954 redova)

## Testovi

- `igra/tests/test_motor.py`: 113 testova
- `igra/tests/test_prikazi.py`: 423 testova
- `igra/tests/test_tok.py`: 86 testova [pregledac]

## Migracije

- `igra`: 14, poslednja `0014_prijava_imena`

## Prevodi

- `locale/en/LC_MESSAGES/django.po`: 245 poruka
- `locale/sr/LC_MESSAGES/django.po`: 245 poruka

## Komande

- `baza_kopija`, `deljeni`, `deljeni_obrisi`, `deljeni_ocisti`, `dnevnik_ocisti`, `moderator_deaktiviraj`, `moderator_dodaj`, `moderator_glavni`, `moderator_lozinka`, `moderatori`, `nepodobno_dodaj`, `nepodobno_ukloni`, `rezultat_obrisi`, `rezultati`

