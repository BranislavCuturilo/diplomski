# Skripte za merenje

Sistem agenata uci samo ako se meri. Ove skripte ne koriste model i ne trose tokene.

| Skripta | Meri | Koristi se za |
|---|---|---|
| `usage_report.py` | koliko je puta pozvan svaki agent i skill, i koliko tokena | sta se koristi, sta samo zauzima kontekst |
| `budget.py` | stalni trosak, trosak pri ucitavanju i trosak poziva agenta; opis skilla 300 do 450 znakova | rani alarm kada opis ili skill naraste |
| `evals.py` | da li ruter predlaze pravi skill za zadat upit (`evals.json`) | regresija: izmena rutera ne sme da pokvari stare slucajeve |
| `score.py` | zabelezen ucinak: pomogao / smetao / neutralan | odluka o popravci ili povlacenju agenta/skilla |
| `faza.py <ime>` | pocetak faze, u `.claude/usage/faze.jsonl` | deli rad na planiranje, delegiranje, implementaciju, kontrolni skup i poruku klijentu |
| `izvestaj_faza.py` | trajanje, tokeni, pokretanja, upiti i cena po fazi, agentu i modelu | odeljak 7.6 |
| `novi_projekat.py <putanja>` | ne meri; priprema prazan folder aplikacije (marker, sloj projekta, podesavanja, CLAUDE.md) | pocetak izrade |
| `priprema_poredjenja.py <folder>` | ne meri; dva cista okruzenja, isti `MVP.md` i dva ista upita (plan, izrada), snimak plugina, verzije alata | pocetak poredjenja |
| `poredjenje.py provera <folder>` | iz stvarnog pokretanja obe strane dokazuje sta sesija ima, u `provera.json` | pre prvog upita |
| `poredjenje.py trag <folder>` | posle prvog upita: transkript je u folderu strane, a ne u maticnom `~/.claude` | odmah po startu |
| `poredjenje.py slepo <folder>` | anonimne kopije X i Y i obrazac za ocenu coveka | pre ocenjivanja |
| `poredjenje.py izvestaj <folder>` | spaja merenje obe strane, nezavisno pokrece testove, dodaje ocenu po kljucu | odeljak 7.6 |

## Izvestaj po fazama

```
cd <projekat>
python <plugin>/scripts/izvestaj_faza.py [--transkripti <folder>] [--izlaz <folder>] [--prag 1800] [--cene <fajl>]
```

Izlaz: `.claude/usage/izvestaj_faza.md` i `.json`. Izvor su stvarni transkripti iz
`~/.claude/projects/<slug>/`, ukljucujuci podagente; slug je putanja projekta u kojoj je svaki
znak osim slova i cifre zamenjen crticom. Ne poziva model, koristi samo standardnu biblioteku.

| Pojam | Mehanicka definicija |
|---|---|
| tokeni | jedna API poruka jednom: isti message id se javlja u vise redova i u kopiji istorije, uzima se red sa najvecim `output_tokens` |
| zidno trajanje | od upisa faze do sledeceg upisa; poslednja faza do poslednje poruke |
| aktivno trajanje | zbir razmaka izmedju poruka istog pokretanja, bez cekanja na upit i bez razmaka preko `--prag`; paralelni agenti se sabiraju |
| pokretanje | jedan agent id, odnosno jedna sesija glavnog toka |
| upit | stvaran upit u glavnom toku transkripta; `prompts.jsonl` je kontrolni broj |
| **vracanje na doradu** | upis faze `implementacija` posle ranijeg upisa `kontrolni skup`, kada prethodni upis nije bio `implementacija` |
| rad bez cekanja coveka | zbir trajanja po upitu, umanjen za vreme u kome `AskUserQuestion` ceka odgovor |
| podpitanja coveku | pitanja iz `AskUserQuestion` plus svaki upit coveka posle prvog |
| tudja izmena | uspesna Edit/Write izmena fajla koji je poslednji menjalo drugo pokretanje; broji i planirano nadogradjivanje, pa je gornja granica |

**Tacnost.** U dve probe `cache_citanje` i `cache_upis` su jednaki onome sto prijavljuje sam CLI.
Ulazni i izlazni tokeni su manji za 1.190 do 1.411 i 177 do 356 po sesiji; takvi pozivi nisu
u transkriptu. Verovatno su to pozadinski pozivi alata, ali uzrok nije utvrdjen.

**Cene** su u `cene.json`, dolara po milion tokena, sa izvorom i datumom provere. Haiku 5.5 ima
skuplju tarifu za zahtev ciji je ceo prompt preko 100.000 tokena. Ako cene ili polje `izvor` nisu
podeseni, izvestaj ispisuje tokene i "cena nije podesena". Cena ne ukljucuje web pretrage i racuna standardnu brzinu.

## Kako se iz merenja uci

| Izvor | Postaje |
|---|---|
| greska koju je napisao agent | izmena skilla ili opisa agenta (ne samo ispravka koda) |
| pao test | pravilo + slucaj u `evals.json` sa poreklom |
| zahtev koji se ponavlja | skripta (ako se racuna) / skill (ako se rasudjuje) / workflow (isti posao nad mnogo fajlova) |
| primedba korisnika u razgovoru | najjaci signal: pravilo odmah, u pravi sloj |

Svaki slucaj u `evals.json` i svako pravilo navodi **poreklo**. Pravilo bez porekla
izgleda isto kao zaradjeno, i tako sistem trune.

## U CI-ju (GitHub Actions)

```
python scripts/budget.py --strict
python scripts/evals.py
```
