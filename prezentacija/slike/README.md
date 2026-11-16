# Slike za odbranu

Sve slike se prave ponovo skriptama; rucno se ne menjaju.

| Folder | Skripta | Sta je |
|---|---|---|
| `igra-prazan/` | `scripts/snimci_igre.py <projekat> prazan <folder>` | igra koju je napravio Claude Code bez plugina |
| `igra-plugin/` | `scripts/snimci_igre.py <projekat> plugin <folder>` | igra koju je napravio Claude Code sa pluginom |
| `grafici/` | `scripts/grafici_prezentacije.py <folder>` | rezultati poredjenja (cena, vreme, nalazi) |

Snimci se prave na kopiji projekta sa svezom bazom: 6 probnih igraca sa razumnim izborima, pa partija
kroz interfejs, cuvanje imena "Бранислав", deljenje, pravila, engleski, moderator (jedno brisanje za
dnevnik) i telefon (390 px). Skripta se pokrece venv-om strane, jer koristi njen Django i Playwright.

## Predlog po slajdu

| Slajd | Slike |
|---|---|
| Sta je napravljeno | `igra-*/01-pocetna`, `igra-*/02-krug-izbor` (jedna pored druge) |
| Tok igre | `03-posle-kruga`, `04-zavrsni-ekran`, `06-deljeni-rezultat` |
| Funkcionalnosti iz runde 2 i 3 | `05-rang-lista-posle-cuvanja`, `08-engleski`, `09-moderator-pregled`, `11-moderator-dnevnik` |
| Telefon | `12-telefon-krug`, `13-telefon-posle-kruga` |
| Cena | `grafici/01-cena-po-zahtevu`, `grafici/04-cena-po-agentu-v1` |
| Glavni rezultat | `grafici/02-odnos-po-verziji` |
| Kvalitet | `grafici/03-nalazi-provere` |
| Paralelni rad | `grafici/05-runda7-tok` |
| Optimizacija | `grafici/06-trajanje-testova` |

## Napomene

- Visoke slike (cela strana): `01`, `04`, `07`, `09`; za slajd ih iseci na deo koji se pokazuje.
- `igra-prazan/04` i `06` sadrze lokalni link (`127.0.0.1`), jer je igra pokrenuta lokalno.
- Grafici: paleta skilla dataviz (plava = prazna sesija, narandzasta = plugin), proverena validatorom;
  decimalni zarez; izvori podataka su u fusnoti svakog grafika.
