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
| jedna igra od 8 krugova | nalozi i prijava za igrace |
| cetiri izbora po krugu | jezici osim srpskog i engleskog |
| racun cene, vremena, ishoda i poena | Docker, MySQL/PostgreSQL, vise servera |
| zavrsna provera i zavrsni ekran sa lekcijama | nivoi tezine, animacije, muzika |
| nova igra posle zavrsene | |
| cuvanje rezultata i rang lista (izmena klijenta) | |
| link za deljenje rezultata (izmena klijenta) | |
| srpski i engleski jezik (izmena klijenta) | |
| moderator: brisanje rezultata i linkova, dnevnik (izmena klijenta) | |
| priprema za javni server https://orkestrator.example (izmena klijenta) | |
| prijava neprikladnog imena sa rang liste, o kojoj odlucuje moderator (izmena klijenta) | |
| stranica „Kako se igra“ sa pravilima i primerom kruga (izmena klijenta) | |
| zvuk ishoda kruga, koji igrac ukljucuje i iskljucuje (izmena klijenta) | |
| poslednjih 10 zavrsenih partija igraca (izmena klijenta) | |
| statistika moderatora za poslednjih 7 dana (izmena klijenta) | |
| javna rang lista u JSON obliku za partnere (izmena klijenta) | |

## 3. Tok igre

1. Nova igra: 8 krugova, zadaci uvek istim redom. Budzet i rok su vidljivi.
2. U svakom krugu igrac bira model, nivo razmisljanja, kontekst i podelu posla.
3. Server racuna cenu, minute i ishod. Igrac vidi samo cenu, minute, stanje budzeta i roka i status.
4. Posle 8. kruga zavrsna provera (kontrolni skup) izvrsava se sama.
5. Zavrsni ekran: poeni, ocena, ukupna cena i minuti, spisak tihih gresaka i lekcije.
6. Posle zavrsene partije igrac moze da upise ime i sacuva rezultat. Pocetni ekran prikazuje
   10 najboljih rezultata: ime, poeni, ocena, datum.
7. Na zavrsnom ekranu igrac dobija link koji moze da posalje drugome. Link otvara stranicu sa
   rezultatom te partije (poeni, ocena, tihe greske, lekcije), bez mogucnosti da se igra nastavi.
8. Igrac na svakom ekranu bira srpski ili engleski. Izbor se pamti, a ceo tekst na ekranu,
   ukljucujuci lekcije i napomenu, postoji na oba jezika.

### Moderator (izmena klijenta)

- Moderator se prijavljuje imenom i lozinkom na `/moderator/`. Igraci i dalje igraju bez naloga.
- Prvog moderatora pravi razvijalac: `python manage.py moderator <ime>`. Moderator na sajtu moze da
  doda novog moderatora i da iskljuci ili ponovo ukljuci drugog (ne sebe).
- Moderator moze da obrise rezultat sa rang liste ili deljeni link. Brisanje je konacno: obrisan
  rezultat se ne moze ponovo sacuvati, a za partiju sa obrisanim linkom ne pravi se novi. Igrac na
  zavrsnom ekranu vidi da je moderator uklonio rezultat ili link.
- Dnevnik pokazuje ko je sta uradio i kada (brisanja, odluke o prijavljenim imenima i promene
  moderatora). Dnevnik se ne moze menjati.
- Lozinka se cuva samo kao hes. Posle 5 neuspelih prijava za isto ime prijava je zakljucana 15 minuta.

### Prijava imena (izmena klijenta)

- Uz svako ime na rang listi (i na rang listi dana) stoji link za prijavu neprikladnog imena. Igrac
  prijavu potvrdjuje na posebnoj stranici. Nalog mu nije potreban i ne pamti se ko je prijavio.
- Moze se prijaviti samo ime koje je u tom trenutku na rang listi. Vise prijava istog rezultata je
  jedna prijava.
- Prijavljeno ime ostaje na rang listi dok moderator ne odluci.
- Moderator na `/moderator/prijavljena-imena/` vidi prijavljena imena i za svako odlucuje: brise
  rezultat (konacno, kao i svako brisanje) ili ga zadrzava. Zadrzan rezultat igraci vise ne mogu da
  prijave. Obe odluke su u dnevniku.

### Kako se igra (izmena klijenta)

- Pocetni ekran ima link na stranicu „Kako se igra“: cilj, tok jednog kruga sa svim opcijama i
  njihovim mnoziocima, tri ishoda kruga, poeni, kazne i ocene, i sta postoji posle igre.
- Primer jednog kruga koristi izmisljen zadatak koji nije u igri; cena i minuti su izracunati
  istim pravilima kao u igri. Iznosi kazni dolaze iz tekuceg bodovanja.
- Pravilo 1 vazi i ovde: stranica ne navodi prave zadatke, njihovu tezinu, koji su tihi ni sanse.

### Zvuk (izmena klijenta)

- Na ekranu igre je dugme za zvuk ishoda kruga. Podrazumevano je iskljuceno, a izbor se pamti u
  pregledacu.
- Zvuk zavisi samo od statusa koji igrac vidi: tihi neuspeh zvuci isto kao uspeh.

### Moje partije (izmena klijenta)

- Pocetni ekran pokazuje poslednjih 10 zavrsenih partija igraca u tom pregledacu, najnoviju prvu:
  vreme zavrsetka, poeni, ocena, oznaka dnevnog izazova i sacuvano ime. Red vodi na podeljen rezultat.
- Igrac i dalje nema nalog: prepoznaje se po nasumicnom kljucu u kolacicu, godinu dana od poslednje
  nove partije. Drugi pregledac ili obrisani kolacici znace praznu istoriju.

### Statistika (izmena klijenta)

- Moderator na `/moderator/statistika/` vidi, za danas i 6 dana pre, broj zavrsenih partija i
  prosecne poene, po danu zavrsetka (vreme Europe/Belgrade), i zbir za ceo period.

### Javna rang lista (izmena klijenta)

- `GET /api/rang-lista/` vraca JSON sa glavnom rang listom i listom danasnjeg dana, istih 10 redova
  kao na pocetnom ekranu: mesto, ime, poeni, ocena na oba jezika i vreme cuvanja. Bez prijave,
  dostupno sa bilo kog sajta, kesira se 60 sekundi.

### Jezik (izmena klijenta)

- Podrazumevani jezik je srpski. Promena jezika ne menja partiju, pravila ni rezultat.
- Ime koje je igrac upisao prikazuje se onako kako je upisano, na oba jezika.

### Deljenje rezultata (izmena klijenta)

- Link postoji samo za zavrsenu partiju i ne sadrzi seme ni broj partije, vec nasumican kod.
- Stranica sa linka samo prikazuje rezultat: nema poteza, cuvanja ni promene sesije onoga ko je otvori.

### Rang lista (izmena klijenta)

- Rezultat se cuva samo za zavrsenu partiju, najvise jednom po partiji.
- Klijent salje samo ime. Poene i ocenu racuna server.
- Ime je obavezno, do 30 znakova posle uklanjanja suvisnih razmaka.

### Ishod kruga

| Ishod | Sta igrac vidi | Posledica |
|---|---|---|
| uspeh | „готово“ | nista |
| neuspeh, zadatak nije tih | „враћено на дораду“ | cena i minuti puta 2, odmah; -5 poena |
| neuspeh, zadatak je tih | „готово“, isto kao uspeh | otkriva se na kontrolnom skupu |

### Kontrolni skup i poeni

- Igra pocinje sa **100 poena**. Poeni su najmanje 0.
- Za svaki tihi neuspeh: dodaje se 3 puta cena tog zadatka i jos jednom njegovi minuti; -35 poena.
- Prekoracenje ne prekida igru. Kazne su na kraju:
  - budzet: -10 za svakih zapocetih 10 % prekoracenja, najvise -50 (npr. 0,01 % do 10 % preko: -10;
    10,01 % do 20 %: -20; preko 40 %: -50);
  - rok: -20.
- Ocena: 85 i vise „одличан оркестратор“, 65 do 84 „солидан“, 40 do 64 „скуп учитељ“, ispod 40 „пожар“.

### Bodovanje (izmena klijenta)

- Do izmene: tihi neuspeh -25, svako prekoracenje budzeta -30. Sve ostalo je isto.
- Novo bodovanje vazi za partije zapocete posle izmene. Svaka partija pamti bodovanje sa kojim je
  pocela, pa partija zapoceta pre izmene i zavrsava se po starom.
- Rezultati na rang listi, zavrsni ekrani i podeljeni linkovi starih partija ostaju sa istim poenima
  i ocenom.

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

- Python, Django, SQLite. Radi lokalno i na jednom javnom Linux serveru (nginx, gunicorn, systemd).
- Bootstrap 5 i JavaScript bez biblioteka, npm-a i koraka gradnje.
- Automatski testovi kroz Django test runner, a tok igre kroz Playwright. pytest nije potreban.
- Tekst na ekranu je cirilicom ili na engleskom, po izboru igraca; nazivi modela i nivoa (Haiku, low)
  ostaju latinicom na oba jezika.

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
| 9 | Rezultat zavrsene partije moze da se sacuva jednom; pocetni ekran prikazuje 10 najboljih. |
| 10 | Zavrsni ekran daje link koji drugome prikazuje rezultat te partije, bez nastavka igre. |
| 11 | Igrac bira srpski ili engleski, izbor se pamti, a ceo tekst na ekranu postoji na oba jezika. |
| 12 | Nove partije se boduju po izmeni klijenta; poeni starih partija nigde se ne menjaju. |
| 13 | Prijavljen moderator brise rezultat ili link konacno, i svako brisanje je u dnevniku sa imenom i vremenom; igraci igraju bez naloga. |
| 14 | Sa produkcionim podesavanjima `check --deploy` prolazi bez upozorenja, sajt radi samo preko HTTPS-a, a vise procesa servera nad istom bazom podnosi nekoliko hiljada igraca dnevno bez gresaka. |
| 15 | Igrac bez naloga prijavljuje ime sa rang liste; moderator vidi prijavljena imena i za svako brise ili zadrzava rezultat, a odluka je u dnevniku. |
| 16 | Sa pocetnog ekrana se otvara „Kako se igra“ sa pravilima i primerom kruga, bez skrivenih podataka iz pravila 1. |
| 17 | Igrac ukljucuje i iskljucuje zvuk ishoda kruga, izbor se pamti, a tihi neuspeh zvuci kao uspeh. |
| 18 | Pocetni ekran pokazuje poslednjih 10 zavrsenih partija igraca, bez naloga. |
| 19 | Moderator vidi broj zavrsenih partija i prosecne poene po danu za poslednjih 7 dana. |
| 20 | Partneri preuzimaju rang listu u JSON obliku sa javne adrese. |

### Javni server (izmena klijenta)

Igra je javna na https://orkestrator.example, za nekoliko hiljada igraca dnevno. Server postavlja
klijentov administrator po `deploy/UPUTSTVO.md`. Pravilo 1 vazi i tamo: DEBUG je uvek iskljucen,
pa ni stranica greske ne prikazuje seme ili druge skrivene podatke.

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

## 9. Uslovi izrade

- Python, Django i Playwright sa pregledacem su vec instalirani.
- Ako pokreces server, izaberi slobodan port: na istom racunaru moze da radi i druga izrada.
