# MVP: igra Orkestrator

## 1. Sta je

Edukativna igra na poteze, u pregledacu. Igrac vodi izradu veb aplikacije i za svaki zadatak bira
kako ce ga AI agent uraditi. Cilj je zavrsiti sa sto vise poena, u budzetu i roku.

Igra treba da nauci jednu stvar: **najbolji rezultat daje izbor prema tezini zadatka i posledici
greske**, a ne uvek najskuplji ili uvek najjeftiniji model.

Jedan igrac, jedna igra, bez naloga. Partija traje oko 5 minuta.

## 2. Opseg

| U MVP-u | Van MVP-a |
|---|---|
| jedna igra od 8 krugova | nalozi i prijava |
| cetiri izbora po krugu | cuvanje rezultata i rang lista |
| racun cene, vremena, ishoda i poena | vise jezika |
| zavrsna provera i zavrsni ekran sa lekcijama | isporuka na server, Docker, Nginx, MySQL |
| nova igra posle zavrsene | nivoi tezine, animacije, zvuk |

## 3. Tok igre

1. Nova igra: 8 krugova, zadaci uvek istim redom. Budzet i rok su vidljivi.
2. U svakom krugu igrac bira model, nivo razmisljanja, kontekst i podelu posla.
3. Server racuna cenu, minute i ishod. Igrac vidi samo cenu, minute, stanje budzeta i roka i status.
4. Posle 8. kruga zavrsna provera (kontrolni skup) izvrsava se sama.
5. Zavrsni ekran: poeni, ocena, ukupna cena i minuti, spisak tihih gresaka i lekcije.

### Ishod kruga

| Ishod | Sta igrac vidi | Posledica |
|---|---|---|
| uspeh | „готово“ | nista |
| neuspeh, zadatak nije tih | „враћено на дораду“ | cena i minuti puta 2, odmah; -5 poena |
| neuspeh, zadatak je tih | „готово“, isto kao uspeh | otkriva se na kontrolnom skupu |

### Kontrolni skup i poeni

- Igra pocinje sa **100 poena**. Poeni su najmanje 0.
- Za svaki tihi neuspeh: dodaje se 3 puta cena tog zadatka i jos jednom njegovi minuti; -25 poena.
- Prekoracenje ne prekida igru. Kazna je na kraju: budzet -30, rok -20.
- Ocena: 85 i vise „одличан оркестратор“, 65 do 84 „солидан“, 40 do 64 „скуп учитељ“, ispod 40 „пожар“.

### Lekcije na zavrsnom ekranu

Lekcija se prikazuje samo kada je uslov ispunjen. Uz nju stoji odeljak zavrsnog rada.

| Uslov | Lekcija | Odeljak |
|---|---|---|
| tihi neuspeh | Ако је грешка тиха, задатак остаје највишем разреду. | 4.2 |
| Opus na zadatku tezine 1 | Најскупљи модел није увек најбољи избор. | 3.2 |
| nivo max bar jednom | Изнад нивоа high цена расте, а квалитет не. | 3.3 |
| kontekst „sve“ bar jednom | Превише контекста квари резултат исто као премало. | 3.1 |
| 50 agenata bar jednom | Више агената не значи јефтиније. | 5.3 |

Na zavrsnom ekranu trajno pise: „Цене и нивои размишљања су стварни подаци; вероватноће, казне и
поени су измишљени параметри игре.“

## 4. Pravila koja se ne krse

1. **Skriveno ostaje na serveru dok igra traje.** Sansa, oznaka tihog zadatka, ishod tihog zadatka
   i seme ne smeju biti u HTML-u, JSON-u ni kolacicu.
2. **Ishod je cista funkcija semena i odluka.** Uspeh kruga:
   `random.Random("<seme>:<krug>").randint(1, 100) <= sansa`. Seme pravi server pri novoj igri.
   Isti ulaz daje isti ishod.
3. **Potez vazi samo za tekuci krug.** Zahtev nosi broj kruga i cetiri izbora. Drugi broj kruga ili
   zavrsena igra: 409. Nepoznat izbor ili neispravan zahtev: 400, stanje netaknuto. Klijent nikad
   ne salje cenu, poene ni ishod.

## 5. Parametri

Svi brojevi igre stoje na jednom mestu u kodu.

### Zadaci

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

### Racun

```
tokeni = baza_tokena[tezina] * nivo.tokeni * kontekst.tokeni * podela.tokeni
cena   = tokeni / 1000000 * model.cena
minuti = baza_minuta[tezina] * model.brzina * nivo.brzina * podela.brzina
sansa  = model.sansa[tezina] + nivo.bonus[tezina] + kontekst.bonus[tezina] + podela.bonus,
         ogranicena na 5..99
```

Budzet **24 $**, rok **150 min**.

| Tezina | Baza tokena | Baza minuta |
|---|---|---|
| 1 | 100.000 | 5 |
| 2 | 300.000 | 15 |
| 3 | 600.000 | 30 |

| Model | Cena igre $/M | Brzina | Sansa t1 / t2 / t3 |
|---|---|---|---|
| Haiku | 0,18 | 0,5 | 90 / 65 / 30 |
| Sonnet | 3,60 | 0,8 | 95 / 85 / 60 |
| Opus | 7,20 | 1,0 | 97 / 92 / 85 |

| Nivo | Tokeni | Brzina | Bonus t1 / t2 / t3 |
|---|---|---|---|
| low | 0,33 | 0,6 | 0 / -15 / -25 |
| high | 1 | 1 | 0 / 0 / 0 |
| max | 2,9 | 1,6 | +1 / +1 / +1 |

| Kontekst | Tokeni | Bonus t1 / t2 / t3 |
|---|---|---|
| malo | 0,6 | 0 / -15 / -25 |
| taman | 1 | 0 / 0 / 0 |
| sve | 1,8 | -10 / -10 / -10 |

| Podela | Tokeni | Brzina | Bonus |
|---|---|---|---|
| sam | 1 | 1 | 0 |
| 3 agenta | 1,3 | 0,5 | 0 |
| 50 agenata | 3,6 | 2,1 | -10 |

## 6. Tehnologija

- Python, Django, SQLite. Radi lokalno.
- Bootstrap 5 i JavaScript bez biblioteka, npm-a i koraka gradnje.
- Automatski testovi kroz Django test runner, a tok igre kroz Playwright. pytest nije potreban.
- Tekst na ekranu je cirilicom; nazivi modela i nivoa (Haiku, low) ostaju latinicom.

## 7. Kada je gotovo

| # | Uslov |
|---|---|
| 1 | Cela igra od 8 krugova moze da se odigra u pregledacu do zavrsnog ekrana. |
| 2 | Isto seme i isti izbori daju isti rezultat. |
| 3 | Dok igra traje, nijedan odgovor servera ne sadrzi skrivene podatke iz pravila 1. |
| 4 | Pogresan krug i zavrsena igra daju 409; nepoznat izbor i neispravan zahtev daju 400; stanje ostaje netaknuto. |
| 5 | Dupli klik na isti potez ne menja rezultat. |
| 6 | Ekran je upotrebljiv na sirini od 375 px, bez gresaka u konzoli. |
| 7 | Automatski testovi pokrivaju pravila igre, HTTP odgovore i tok kroz pregledac, i svi prolaze. |
| 8 | Test balansa prolazi. |

### Test balansa

Simulacija 5.000 semena (0 do 4.999), srednji poeni. Mora da vazi:
**po tezini > sve Opus, high > sve Haiku, low, malo**.

| Strategija | Izbori |
|---|---|
| po tezini | tezina 1 Haiku, tezina 2 Sonnet sa 3 agenta, tezina 3 Opus; nivo high, kontekst taman |
| sve Opus, high | Opus, nivo high, kontekst taman, sam |
| sve Haiku, low, malo | Haiku, nivo low, kontekst malo, sam |

Promena parametra koja obrne ovaj poredak znaci da igra uci pogresno.

## 8. Otvoreno za detaljan plan

Ovaj dokument namerno ne odredjuje:

- raspored datoteka i podelu na module;
- gde i kako se cuva stanje partije, uz pravilo 1;
- URL-ove, oblik zahteva i odgovora;
- izgled ekrana i raspored kontrola;
- organizaciju testova;
- redosled izrade i podelu posla.
