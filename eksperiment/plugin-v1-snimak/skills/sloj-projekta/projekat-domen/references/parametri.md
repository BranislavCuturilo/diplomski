# Parametri igre Orkestrator

U kodu zive samo u `igra/parametri.py`. Kolona poreklo razdvaja stvarne podatke od
izmisljenih; u radu se izmisljeni navode kao parametri igre, nikad kao merenje.

## Zadaci (ovim redom)

| Krug | Zadatak | Tezina | Tih |
|---|---|---|---|
| 1 | Prevod pocetne strane | 1 | ne |
| 2 | Sablon liste i forme | 1 | ne |
| 3 | CSS i prilagodjavanje telefonu | 1 | ne |
| 4 | CRUD prikazi | 2 | ne |
| 5 | Model podataka i migracija | 3 | da |
| 6 | Provera prava pristupa | 3 | da |
| 7 | Automatski testovi | 2 | ne |
| 8 | Bezbednosna revizija | 3 | da |

Tih zadatak igrac ne vidi kao tih do zavrsnog ekrana.

## Racun

```
tokeni = baza_tokena[tezina] * nivo.tokeni * kontekst.tokeni * podela.tokeni
cena   = tokeni / 1000000 * model.cena
minuti = baza_minuta[tezina] * model.brzina * nivo.brzina * podela.brzina
sansa  = model.sansa[tezina] + nivo.bonus[tezina] + kontekst.bonus[tezina] + podela.bonus,
         ogranicena na 5..99
```

Budzet **24 $**, rok **150 min**. Izmisljeno, podeseno simulacijom.

| Tezina | Baza tokena | Baza minuta | Poreklo |
|---|---|---|---|
| 1 | 100.000 | 5 | izmisljeno |
| 2 | 300.000 | 15 | izmisljeno |
| 3 | 600.000 | 30 | izmisljeno |

## Model

| Model | Ulaz $/M | Izlaz $/M | Cena igre $/M | Brzina | Sansa t1 / t2 / t3 |
|---|---|---|---|---|---|
| Haiku | 0,10 | 0,50 | 0,18 | 0,5 | 90 / 65 / 30 |
| Sonnet | 2 | 10 | 3,60 | 0,8 | 95 / 85 / 60 |
| Opus | 4 | 20 | 7,20 | 1,0 | 97 / 92 / 85 |

Poreklo: ulaz i izlaz su stvarne cene (Anthropic, Pricing, provereno 2026-11-08;
Haiku za upit do 100.000 tokena). Cena igre je 0,8 ulaza + 0,2 izlaza (ponder izmisljen).
Brzina i sanse su izmisljene; smer brzine prati odeljak 3.2 rada.

## Nivo razmisljanja

| Nivo | Tokeni | Brzina | Bonus t1 / t2 / t3 |
|---|---|---|---|
| low | 0,33 | 0,6 | 0 / -15 / -25 |
| high | 1 | 1 | 0 / 0 / 0 |
| max | 2,9 | 1,6 | +1 / +1 / +1 |

Poreklo: tokeni su odnos cene po zadatku iz tabele u odeljku 3.3 (1,29 i 11,24 prema 3,88).
Bonus za `max` prati isti izvor (+0,6 procentnih poena). Ostalo izmisljeno.

## Kontekst

| Kontekst | Tokeni | Bonus t1 / t2 / t3 |
|---|---|---|
| malo | 0,6 | 0 / -15 / -25 |
| taman | 1 | 0 / 0 / 0 |
| sve | 1,8 | -10 / -10 / -10 |

Poreklo: izmisljeno; smer prati odeljak 3.1 rada.

## Podela

| Podela | Tokeni | Brzina | Bonus |
|---|---|---|---|
| sam | 1 | 1 | 0 |
| 3 agenta | 1,3 | 0,5 | 0 |
| 50 agenata | 3,6 | 2,1 | -10 |

Poreklo: 3,6 i 2,1 su odnos tokena i vremena u prvom testu iz tabele u odeljku 5.3 rada
(101 prema 28 miliona, 90 prema 43 min). Ostalo izmisljeno.

## Provera balansa (obavezan test)

Simulacija 5.000 semena, srednji poeni, 2026-11-08:

| Strategija | Poeni |
|---|---|
| po tezini (Haiku, Sonnet, Opus), 3 agenta na tezini 2 | 72,8 |
| Opus samo za tihe zadatke, ostalo Haiku | 69,8 |
| sve Opus, high | 68,0 |
| sve Sonnet, high | 60,1 |
| obrnuto: Opus lako, Haiku tesko | 45,4 |
| sve Opus, max, kontekst sve | 29,1 |
| sve Haiku, low, malo | 20,8 |
| sve Haiku, 50 agenata | 14,4 |

Gde strategija nista ne navodi, vazi nivo high, kontekst taman i podela sam. U strategiji
"obrnuto" tezina 2 ide Sonnetu.

Test mora da potvrdi poredak: prva strategija > sve Opus high > sve Haiku low malo.
Promena parametra koja obrne poredak znaci da igra uci pogresno.
