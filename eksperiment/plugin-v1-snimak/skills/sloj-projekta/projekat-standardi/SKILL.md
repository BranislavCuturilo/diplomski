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

2. **Stanje je recnik JSON tipova u `request.session["igra"]`.** Posle izmene kljuc
   se ponovo dodeljuje: izmena ugnezdenog recnika sama ne upisuje sesiju.

3. **Bez modela i bez naloga.** Aplikacija `igra` nema svoje migracije; koristi se
   samo tabela sesija. Bez Docker-a, Nginx-a i MySQL-a.

## Standardi

| Pravilo | Zasto u ovom projektu | Koje opste pravilo pada |
|---|---|---|
| Django i SQLite, jedna aplikacija `igra` | mikro primer, sve radi lokalno | nijedno |
| Prikazi su funkcije: `pocetna` (GET), `potez` (POST, JSON), `nova` (POST) | tri tanka prikaza, pozivaju motor | stack-django: primeri u `views.md` su klase |
| Jedan sablon `templates/igra/igra.html` | igra je jedan ekran | nijedno |
| `static/igra/igra.js`, bez biblioteka i bez koraka gradnje | browser samo prikazuje stanje | nijedno |
| Bootstrap 5 preko jednog `<link>` sa tacnom verzijom | bez npm-a | nijedno |
| Tekst na ekranu cirilicom, kod latinicom bez dijakritika | jezik rada | nijedno |
| Testovi: `igra/tests/test_motor.py`, `test_prikazi.py`, `test_tok.py` | motor bez servera, prikazi kroz Django klijent, tok kroz Playwright | qa: pytest; ovde Django test runner, jer pytest nije instaliran |
| Pokretanje testova: `python "${CLAUDE_PLUGIN_ROOT}/tools/test_summary.py"` | vraca samo sazetak | nijedno |

## Kako agent postupa

1. Ako opste pravilo i ovaj skill kazu razlicito: vazi ovaj skill.
2. Ako dva skilla NIVOA 2 kazu razlicito: STANI, pitaj korisnika, upisi odluku u
   `projekat-odluke` (nivo 3).
