# MVP: igra Orkestrator

## 1. Sta je

Edukativna igra na poteze, u pregledacu. Igrac vodi izradu veb aplikacije i za svaki zadatak bira
kako ce ga AI agent uraditi. Cilj je zavrsiti sa sto vise poena, u budzetu i roku.

Igra treba da nauci jednu stvar: **najbolji rezultat daje izbor prema tezini zadatka i posledici
greske**, a ne uvek najskuplji ili uvek najjeftiniji model.

Jedan igrac, jedna igra, bez naloga. Partija traje oko 5 minuta. Naloge imaju samo moderatori.

## 2. Opseg

| U MVP-u | Van MVP-a |
|---|---|
| jedna igra od 8 krugova | nalozi igraca |
| cetiri izbora po krugu | jezici osim srpskog i engleskog |
| racun cene, vremena, ishoda i poena | MySQL |
| zavrsna provera i zavrsni ekran sa lekcijama | nivoi tezine, animacije |
| nova igra posle zavrsene | |
| cuvanje rezultata i rang lista 10 najboljih (dodato 2026-11-10) | |
| deljenje rezultata linkom (dodato 2026-11-10) | |
| srpski i engleski, izbor jezika se pamti (dodato 2026-11-11) | |
| moderator i glavni moderator: prijava, brisanje rezultata i linka, dnevnik, upravljanje nalozima (dodato 2026-11-11) | |
| javna isporuka na https://orkestrator.example (dodato 2026-11-11) | |
| prijava neprikladnog imena sa rang liste i odluka moderatora (dodato 2026-11-12) | |
| strana „Kako se igra“, zvuk ishoda kruga, poslednjih 10 partija u ovom pregledacu, statistika za moderatora (7 dana), javna rang lista u JSON-u (dodato 2026-11-12) | |

## 3. Tok igre

1. Nova igra: 8 krugova, zadaci uvek istim redom. Budzet i rok su vidljivi.
2. U svakom krugu igrac bira model, nivo razmisljanja, kontekst i podelu posla.
3. Server racuna cenu, minute i ishod. Igrac vidi samo cenu, minute, stanje budzeta i roka i status.
4. Posle 8. kruga zavrsna provera (kontrolni skup) izvrsava se sama.
5. Zavrsni ekran: poeni, ocena, ukupna cena i minuti, spisak tihih gresaka i lekcije.
6. Posle zavrsene partije igrac moze da upise ime i sacuva rezultat. Strana prikazuje 10 najboljih
   sacuvanih rezultata: ime, poeni, ocena, datum.
7. Posle zavrsene partije igrac moze da zatrazi link za deljenje i posalje ga drugome.

### Deljenje rezultata

- Link nastaje klikom na „Подели резултат“ na zavrsnom ekranu, jednom po partiji; ponovni klik daje isti link.
  Deljenje ne zavisi od upisa na rang listu.
- Link otvara stranicu samo za citanje: poeni, ocena, ukupna cena i minuti, tihe greske, lekcije, datum
  deljenja i ime, ako je partija sacuvana na rang listi. Dugme „Играј и ти“ vodi na pocetnu stranu.
  Igra se sa te stranice ne moze nastaviti, a otvaranje linka ne menja igru onoga ko ga otvara.
- Link istice 30 dana posle nastanka; posle toga stranica kaze da rezultat vise nije dostupan.
  Stari zapisi se brisu komandom.
- Link se ne moze pogoditi i ne nosi seme ni drugi skriveni podatak.
- Link vodi na https://orkestrator.example/r/<token>/.

### Rang lista

- Jedan upis po zavrsenoj partiji. Klijent salje samo ime; poeni i ocena dolaze iz stanja partije na serveru.
- Ime ima 1 do 20 znakova, bez praznog prostora na pocetku i kraju. Ista imena su dozvoljena.
- Ime koje je, posle normalizacije (velika i mala slova, cirilica i latinica, dijakritici, razmaci),
  jednako stavci sifarnika nepodobnih imena odbija se jednom opstom porukom. Pocetni sifarnik
  pripremamo mi, a klijent ga pregleda; stavke i sacuvani rezultati menjaju se rucno, komandama.
  Sifarnik nikad ne ide klijentu.
- „Нова игра“ pita za potvrdu usred partije i na zavrsnom ekranu dok rezultat nije sacuvan.
- Redosled: vise poena je iznad; kod jednakih poena ranije sacuvan rezultat je iznad.
- Datum se prikazuje kao 10.11.2026 na srpskom i 2026-11-10 na engleskom.
- Red osvojen po ranijim pravilima bodovanja (pre 2026-11-11) nosi oznaku „старо бодовање“, a ispod
  liste stoji objasnjenje. Sacuvani poeni i deljeni linkovi se nikad ne preracunavaju.
- Lista je odeljak na istoj strani kao igra, vidljiv od prvog ucitavanja. Nova igra usred partije
  ostaje dozvoljena, pa lista nagradjuje i srecu; to je prihvaceno.

### Moderator

- Moderator se prijavljuje imenom i lozinkom (najmanje 12 znakova). Posle 5 neuspesnih pokusaja
  za isto ime prijava je blokirana 15 minuta. Sesija istice posle 8 h neaktivnosti. Prijava i
  odjava ne prekidaju partiju u toku.
- Moderator brise rezultat sa rang liste ili deljeni link, uz potvrdu na posebnoj strani. Brisanje
  je trajno. Partija obrisanog rezultata se ne cuva ponovo, a partija obrisanog linka ne dobija nov;
  obrisan link izgleda isto kao istekao.
- Dnevnik pokazuje ko je sta obrisao ili promenio i kada, sa snimkom (ime, poeni, ocena, datum).
  Vide ga svi moderatori, samo za citanje; cuva se 365 dana. Brisanja koja razvijalac radi
  komandama su u dnevniku kao „развијалац (команда)“.
- Glavni moderator jos dodaje, deaktivira i aktivira moderatore, postavlja im lozinke i dodeljuje i
  oduzima ulogu glavnog, uz potvrdu sopstvenom lozinkom. Uvek ostaje bar jedan aktivan glavni;
  niko ne deaktivira sebe. Pocetnu lozinku vlasnik menja pri prvoj prijavi.
- Prvog glavnog moderatora pravi administrator komandom, po DEPLOY.md. Igraci nemaju naloge.

### Prijava neprikladnog imena

- Ispod rang liste igrac otvara „Пријави неприкладно име“, bira ime sa liste i salje prijavu. Prijaviti se
  moze samo ime koje je na listi na ekranu, jednom iz istog pregledaca; po rezultatu se belezi najvise 100 prijava.
- Prijava nista ne sakriva i nista ne brise: ime ostaje na listi dok moderator ne odluci. Igrac uvek dobija
  istu potvrdu i ne vidi ni tudje prijave ni odluku.
- Moderator na strani „Преглед“ vidi prijavljena imena, sa brojem prijava i trenutkom prve, i odlucuje:
  „Обриши“ (brisanje rezultata, uz potvrdu, kao i do sada) ili „Остави“. Ostavljeno ime se vise ne pojavljuje
  medju prijavljenima, a odluka je u dnevniku kao „одбачена пријава имена“.
- Broj prijava je samo znak: bez naloga jedna osoba moze da posalje vise prijava iz vise pregledaca.

### Ishod kruga

| Ishod | Sta igrac vidi | Posledica |
|---|---|---|
| uspeh | „готово“ | nista |
| neuspeh, zadatak nije tih | „враћено на дораду“ | cena i minuti puta 2, odmah; -5 poena |
| neuspeh, zadatak je tih | „готово“, isto kao uspeh | otkriva se na kontrolnom skupu |

### Kontrolni skup i poeni

- Igra pocinje sa **100 poena**. Poeni su najmanje 0.
- Za svaki tihi neuspeh: dodaje se 3 puta cena tog zadatka i jos jednom njegovi minuti; -35 poena.
- Prekoracenje ne prekida igru. Kazna je na kraju: budzet -10 za svakih zapocetih 10% prekoracenja,
  najvise -50 (tacno 10% je -10, 10,01% je -20); rok -20. Zavrsni ekran pokazuje prekoracenje budzeta
  u procentima i njegovu kaznu.
- Bodovanje vazi od 2026-11-11 (pravila 2). Partija se boduje po pravilima sa kojima je pocela;
  ranija pravila (pravila 1): tihi neuspeh -25, budzet -30 za svako prekoracenje.
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
   ne salje cenu, poene ni ishod; pri cuvanju rezultata salje samo ime.

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

- Python, Django, SQLite. Radi lokalno za razvoj, a javno iza Nginx-a i TLS-a, u Docker-u.
- Bootstrap 5 i JavaScript bez biblioteka, npm-a i koraka gradnje.
- Automatski testovi kroz Django test runner, a tok igre kroz Playwright. pytest nije potreban.
- Tekst na ekranu postoji na srpskom (cirilicom) i engleskom; nazivi modela i nivoa (Haiku, low)
  su isti na oba jezika. Igrac bira jezik, izbor se pamti u kolacicu jezika, a novi posetilac
  dobija jezik pregledaca (engleski ako ga pregledac trazi, inace srpski). Ceo tekst na ekranu,
  ukljucujuci statuse, ocene, lekcije, trajnu napomenu, poruke gresaka i dijaloge, postoji na oba
  jezika. Rang lista i deljena strana su na jeziku onoga ko gleda; ime igraca se ne prevodi.
  Engleske ocene, lekcije i napomenu klijent pregleda pre isporuke.

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
| 9 | Zavrsena partija se moze sacuvati tacno jednom, sa poenima i ocenom sa servera; rang lista prikazuje 10 najboljih po pravilima iz odeljka 3, a red po ranijim pravilima bodovanja nosi oznaku. |
| 10 | Link za deljenje otvara rezultat te partije samo za citanje, istice posle 30 dana i ne otkriva skrivene podatke. |
| 11 | Igra, rang lista i deljena strana rade na srpskom i engleskom; izbor jezika se pamti, nijedan tekst na ekranu nije ostao nepreveden, a promena jezika ne menja tok ni ishod partije. |
| 12 | Samo prijavljen moderator brise rezultat ili link, uz potvrdu; nalozima upravlja samo glavni moderator i uvek ostaje bar jedan aktivan glavni; svako brisanje i svaka radnja nad nalogom je u dnevniku; obrisana partija se ne cuva ni ne deli ponovo; prijava i odjava ne prekidaju partiju. |
| 13 | Igra radi na https://orkestrator.example; `check --deploy` je bez nalaza; periodicni zadaci i kopije rade, a povratak kopije je proban; DEPLOY.md je proveren od praznog servera. |
| 14 | Igrac prijavljuje ime sa rang liste, a prijava nista ne sakriva; samo prijavljen moderator vidi prijavljena imena i odlucuje: brise rezultat ili ostavlja ime; obe odluke su u dnevniku, a ostavljeno ime se ne vraca medju prijavljena. |

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
