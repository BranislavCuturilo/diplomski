# Poredjenje: prazan Claude Code i plugin

- Koren: `C:\poredjenje-orkestrator`

| mera | prazan | plugin |
|---|---|---|
| zidno trajanje | 67 h 41 min | 68 h 22 min |
| rad bez cekanja coveka | 2 h 15 min | 19 h 18 min |
| cekanje coveka | 65 h 26 min | 49 h 03 min |
| aktivno, zbir svih agenata | 2 h 00 min | 41 h 39 min |
| planiranje: rad | 3 min 57 s | 14 min 28 s |
| planiranje: tokena | 203.065 | 1.393.378 |
| planiranje: cena | 0.9536 $ | 3.0542 $ |
| izrada: rad | 12 min 05 s | 1 h 37 min |
| izrada: tokena | 933.492 | 17.709.016 |
| izrada: cena | 1.9302 $ | 22.7500 $ |
| stil: rad | 7 min 31 s | 1 h 11 min |
| stil: tokena | 1.510.707 | 28.443.430 |
| stil: cena | 2.6089 $ | 14.2245 $ |
| rang: rad | 4 min 41 s | 1 h 46 min |
| rang: tokena | 1.219.714 | 56.117.589 |
| rang: cena | 2.4640 $ | 34.5791 $ |
| deljenje: rad | 4 min 07 s | 1 h 16 min |
| deljenje: tokena | 2.035.606 | 43.983.258 |
| deljenje: cena | 1.7122 $ | 28.4916 $ |
| jezik: rad | 11 min 31 s | 1 h 41 min |
| jezik: tokena | 5.961.485 | 84.280.789 |
| jezik: cena | 4.0132 $ | 43.7356 $ |
| bodovanje: rad | 3 min 55 s | 1 h 58 min |
| bodovanje: tokena | 1.571.387 | 58.457.083 |
| bodovanje: cena | 1.4826 $ | 33.1693 $ |
| moderator: rad | 15 min 20 s | 2 h 24 min |
| moderator: tokena | 5.873.485 | 97.018.515 |
| moderator: cena | 4.0507 $ | 49.5875 $ |
| javno: rad | 24 min 37 s | 3 h 49 min |
| javno: tokena | 6.479.939 | 143.399.671 |
| javno: cena | 3.8493 $ | 81.4193 $ |
| izazov: rad | 2 min 30 s | 1 h 06 min |
| izazov: tokena | 625.658 | 21.752.850 |
| izazov: cena | 0.4875 $ | 9.8373 $ |
| csv: rad | 3 min 01 s | 17 min 51 s |
| csv: tokena | 502.647 | 4.143.504 |
| csv: cena | 0.7007 $ | 2.4802 $ |
| prijava: rad | 24 min 33 s | 56 min 16 s |
| prijava: tokena | 14.044.194 | 50.244.265 |
| prijava: cena | 13.4544 $ | 33.5610 $ |
| pet: rad | 17 min 46 s | 57 min 11 s |
| pet: tokena | 10.476.131 | 37.942.204 |
| pet: cena | 6.0478 $ | 14.9930 $ |
| upita coveka | 13 | 14 |
| podpitanja coveku, bez propisanih upita | 4 | 49 |
|   pitanja alatom | 4 | 48 |
|   poruke posle prvog upita, sa propisanim | 12 | 13 |
| API poruka | 323 | 3.996 |
| pokretanja (sesije i agenti) | 5 | 95 |
| ulazni tokeni | 656 | 8.134 |
| izlazni tokeni | 636.022 | 6.992.383 |
| citanje iz kesa | 48.751.002 | 615.591.904 |
| upis u kes | 2.049.830 | 22.293.131 |
| tokena ukupno | 51.437.510 | 644.885.552 |
| izlaznih tokena u minuti | 4690.7 | 6034.3 |
| cena | 43.7550 $ | 371.8825 $ |
| vracanja na doradu | 0 | 25 |
| testovi, nezavisno pokretanje | 303 pokrenuto, 0 palo (izlazni kod 0) | 703 pokrenuto, 0 palo (izlazni kod 0) |
| pozivi agenata i skillova | 0 | 142 |
| upisa hooka plugina | 0 | 112 |
| ocena coveka, prosek od 5 | nije ocenjeno | nije ocenjeno |

## Po modelu

| strana | model | ulaz | izlaz | cache citanje | cache upis | cena |
|---|---|---|---|---|---|---|
| prazan | claude-opus-5-5 | 530 | 496.063 | 34.651.126 | 1.619.939 | 29.8131 $ |
| prazan | claude-fable-5-2 | 106 | 128.295 | 13.565.252 | 350.541 | 13.4544 $ |
| prazan | claude-sonnet-5-5 | 20 | 11.664 | 534.624 | 79.350 | 0.4875 $ |
| plugin | claude-opus-5-5 | 6.532 | 5.814.801 | 510.396.954 | 18.856.633 | 317.5387 $ |
| plugin | claude-sonnet-5-5 | 1.134 | 716.858 | 54.158.590 | 2.175.470 | 18.1333 $ |
| plugin | claude-fable-5-2 | 258 | 289.621 | 46.410.519 | 721.580 | 31.6710 $ |
| plugin | claude-haiku-5-5 | 172 | 101.786 | 2.958.759 | 241.522 | 0.1107 $ |
| plugin | claude-opus-4-8 | 38 | 69.317 | 1.667.082 | 297.926 | 4.4287 $ |

## Ogranicenja

- Svaka strana je izvedena jednom: rezultat pokazuje sta se desilo u ovom slucaju, a ne statisticki pouzdanu razliku.
- Cena je obracun po ceni programskog interfejsa, bez obzira na nacin placanja.
- Obe strane imaju isti MVP.md; strana sa pluginom ima i gotove standarde koda, sto je deo onoga sto se poredi.
- Pravila plugina dopunjena su pre merenja zamkama izabranim za tehnologije ove igre.
