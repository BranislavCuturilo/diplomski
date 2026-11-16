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

## Kazne (po verziji pravila, `KAZNE` u `parametri.py`)

| Kazna | Pravila 1 (do 2026-11-11) | Pravila 2 (od 2026-11-11) |
|---|---|---|
| dorada | 5 | 5 |
| tiha greska | 25 | 35 |
| budzet, po zapocetom koraku od 10% | 30 | 10 |
| budzet, najvise | 30 | 50 |
| rok | 20 | 20 |

Poreklo: izmisljeno; pravila 2 su zahtev klijenta 2026-11-11. Pravila 1 su ista formula
(svako prekoracenje je bar jedan korak, najvise 30). `KAZNE[1]` ostaje dok postoje sesije
bez kljuca `pravila` ili sa verzijom 1. To se utvrdjuje upitom nad neisteklim sesijama, ne kalendarom,
jer svaki potez produzava sesiju. Podaci sesije su kodirani: sirov SQL (`LIKE '%pravila%'`) ih ne vidi,
pa ih treba dekodirati kroz `SessionStore`. Bez `KAZNE[1]` nezavrsena partija verzije 1 daje 500 na
8. potezu (`motor.kontrolni_skup`). Na dan 2026-11-11 baza ima 3 neistekle sesije verzije 1. CHECK na `Rezultat.pravila` nabraja verzije
`PRAVILA_STARA..PRAVILA_TEKUCA` (`pravila = 1 OR pravila = 2`, migracija 0008), ne kljuceve `KAZNE`: brisanje stare verzije iz
`KAZNE` ne dira CHECK, a nova verzija trazi migraciju. Koraci i najvisa kazna budzeta moraju biti
veci od 0 (test).

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

## Rang lista

Ime 1 do 20 znakova; prikazuje se 10 najboljih. Poreklo: zahtev klijenta, MVP 3 (2026-11-10).

Najvise 2 uzastopna kombinujuca znaka (kategorija M) posle NFC (`IME_MAKS_KOMBINUJUCIH`). Poreklo:
bezbednosna revizija 2026-11-10, nagomilani znakovi crtaju preko susednih redova liste. Imena iz pisama
koja redovno nose 3 i vise znakova (npr. hebrejski sa vokalima) se odbijaju; prihvaceno.

Lista dana: isti broj mesta (10) kao glavna, samo redovi sa `dan` = danas po Europe/Belgrade.
Poreklo: zahtev klijenta, dnevni izazov (2026-11-12).

## Prijava imena

Po rezultatu se belezi najvise 100 prijava (`PRIJAVA_NAJVISE`); preko toga prijava dobija isti odgovor, bez
upisa. Poreklo: odluka plana 2026-11-12, izmisljeno; moderatoru je dovoljno „mnogo“, a tabela prijava ne
raste bez granice. Broj prijava je slab znak: bez naloga jedna osoba pravi vise sesija (do oko 60 u minuti
po adresi, zone `strana` i `nova` u Nginx-u), pa stotinu prijava moze poteci od jedne. Zato prijava nista ne
sakriva, a odlucuje moderator.
Oznaka reda: HMAC-SHA256 partije sa solju, 32 heksadecimalne cifre (128 bita, `PRIJAVA_OZNAKA_DUZINA`).
Poreklo: odluka plana 2026-11-12, ista mera kao token za deljenje.

## Deljenje rezultata

Link vazi 30 dana od nastanka. Poreklo: zahtev klijenta, MVP 3 (2026-11-10).
Token: 16 nasumicnih bajtova iz `secrets` (128 bita), u URL-u 22 znaka base64url. Poreklo: odluka
plana 2026-11-10; dvostruko iznad najmanje entropije identifikatora sesije koju trazi OWASP Session
Management Cheat Sheet (64 bita).

## Moderator

Sesija 8 h neaktivnosti; 5 neuspeha za isto ime, pa 15 minuta blokade; lozinka najmanje 12
znakova; dnevnik 365 dana (`dnevnik_ocisti` ne prima manje od 14 dana sesije igre, jer hes partije
u dnevniku cuva garanciju da se obrisana partija ne sacuva ponovo). Poreklo: odluke 2026-11-11;
nisu parametri igre, zive u `settings.py`. Na serveru je brojac neuspeha u bazi (`PokusajPrijave`),
zajednicki svim procesima (odluka 2026-11-11); Nginx dodatno ogranicava prijavu po IP-u.

## Jezik

Kolacic jezika vazi 365 dana (u `settings.py`, nije parametar igre). Poreklo: odluka plana
2026-11-11; Django podrazumevano brise kolacic pri zatvaranju pregledaca, a MVP 6 trazi da se
izbor pamti. Datum: `d.m.Y` na srpskom, `Y-m-d` na engleskom (odluka korisnika J2, 2026-11-11).

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

Tabela iznad je za pravila 1. Pravila 2, ista simulacija (semena 0 do 4.999), 2026-11-11:

| Strategija | Pravila 1 | Pravila 2 |
|---|---|---|
| po tezini (Haiku, Sonnet, Opus), 3 agenta na tezini 2 | 72,71 | 71,64 |
| Opus samo za tihe zadatke, ostalo Haiku | 69,46 | 72,74 |
| sve Opus, high | 67,68 | 61,15 |
| sve Sonnet, high | 59,81 | 50,00 |
| obrnuto: Opus lako, Haiku tesko | 45,48 | 27,06 |
| sve Opus, max, kontekst sve | 29,16 | 11,38 |
| sve Haiku, low, malo | 20,77 | 3,38 |
| sve Haiku, 50 agenata | 14,29 | 5,64 |

U pravilima 2 „Opus samo za tihe“ je iznad „po tezini“; to prati lekciju 4.2 i prihvaceno je
(odluka korisnika 2026-11-11). Obavezni poredak vazi za obe verzije.

Gde strategija nista ne navodi, vazi nivo high, kontekst taman i podela sam. U strategiji
"obrnuto" tezina 2 ide Sonnetu.

Test mora da potvrdi poredak: prva strategija > sve Opus high > sve Haiku low malo.
Promena parametra koja obrne poredak znaci da igra uci pogresno.
