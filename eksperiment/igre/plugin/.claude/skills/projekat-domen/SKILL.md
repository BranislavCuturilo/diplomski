---
name: projekat-domen
nivo: 2
description: >
  Pravila igre Orkestrator: zadaci, izbor modela, nivoa razmisljanja, konteksta
  i podele, tiha greska, kontrolni skup, budzet, rok i poeni. Ucitaj PRE izmene
  motora igre, prikaza, testova ili teksta na ekranu. Okidaci: "motor", "potez",
  "krug", "budzet", "rok", "tiha greska", "kontrolni skup", "seme", "pravila igre".
---

# projekat-domen (nivo 2)

Orkestrator je edukativna igra na poteze: igrac vodi izradu veb aplikacije i za
svaki zadatak bira kako ce ga agent uraditi. Uci pravila iz zavrsnog rada.

## Tri pravila koja se nikad ne preskacu

1. **Skriveno ostaje na serveru dok igra traje.** Sansa, oznaka `tiha`, ishod tihog
   zadatka i seme ne smeju u HTML, JSON ni kolacic. Zato `SESSION_ENGINE` ostaje
   baza: sesija u potpisanom kolacicu je citljiva klijentu.
   *Poreklo: odluka korisnika 2026-11-08, sva logika igre je na serveru.*
   Rang lista nosi samo ime, poene, ocenu, datum, oznaku da je red bodovan po ranijim pravilima i
   javnu oznaku reda za prijavu imena (HMAC partije: nije id, a partija se iz nje ne izvodi);
   sifarnik nepodobnih imena nikad ne ide klijentu.
   Prijave imena, njihov broj i odluka moderatora ne idu igracu: odgovor na prijavu je isti za novu,
   ponovljenu i vec pregledanu.
   Deljeni rezultat nosi samo zavrsni ekran, ime sa rang liste i datum; link je nasumican token,
   nezavisan od semena i partije.
   Dnevnik vide samo moderatori; ne nosi token linka, a hes partije cuva samo za proveru i nikad
   ga ne prikazuje. Obrisan link daje isti odgovor kao istekao.
   Uspeh i tih neuspeh nose isti kljuc statusa `gotovo` na oba jezika; baza i JSON cuvaju
   kljuceve, ne tekst.

2. **Ishod je cista funkcija semena i odluka.** Uspeh kruga: `random.Random("<seme>:<krug>").randint(1, 100) <= sansa`.
   Nikad globalni `random`, sat ni redosled skupa. Seme pravi server pri novoj igri;
   klijent ga ne zadaje. Zato isti ulaz daje isti ishod, a dupli klik ne menja rezultat.

3. **Potez vazi samo za tekuci krug.** POST nosi broj kruga i cetiri izbora.
   Drugi broj kruga ili igra koja je zavrsena: 409. Nepoznat izbor: 400, stanje netaknuto.
   Klijent nikad ne salje cenu, poene ni ishod.
   Cuvanje rezultata nosi samo ime; poeni i ocena dolaze iz stanja; jednom po zavrsenoj
   partiji, drugi pokusaj je 409.

## Tok igre

1. Nova igra: 8 krugova, zadaci redom iz `references/parametri.md`, budzet i rok vidljivi.
2. Krug: igrac bira model, nivo razmisljanja, kontekst i podelu; server racuna cenu, minute i ishod.
3. Odgovor kruga sadrzi samo: cena, minuti, stanje budzeta i roka, i status.

| Ishod | Sta igrac vidi | Posledica |
|---|---|---|
| uspeh | `gotovo` | nista |
| neuspeh, zadatak nije tih | `vraceno na doradu` | cena i minuti puta 2, odmah; -5 poena |
| neuspeh, zadatak je tih | `gotovo`, **isto kao uspeh** | otkriva se na kontrolnom skupu |

4. Posle 8. kruga kontrolni skup se izvrsava sam: za svaki tih neuspeh dodaje 3 puta
   cenu tog zadatka i jos jednom njegove minute; -35 poena (pravila 1: -25).
5. Prekoracenje se ne prekida: igra ide do kraja, a kazna je na kraju: budzet -10 za svakih
   zapocetih 10% prekoracenja, najvise -50 (pravila 1: -30 za svako); rok -20. Procenat je ceo
   broj zaokruzen navise, racun u celim brojevima (tacno 10% je -10). Poeni su najmanje 0, a pocinju od 100.
6. Zavrsni ekran: poeni, ocena, ukupna cena i minuti, prekoracenje budzeta u procentima i njegova
   kazna (samo snimci koji ih nose), spisak tihih gresaka, lekcije.
7. Posle zavrsene partije igrac moze jednom da sacuva rezultat pod imenom od 1 do 20 znakova.
   Ime jednako stavci sifarnika posle normalizacije (velika i mala slova, cirilica i latinica,
   dijakritici, razmaci) se odbija jednom opstom porukom. Rang lista: 10 najboljih, vise poena
   iznad, kod jednakih ranije sacuvan iznad; ime, poeni, ocena, datum (10.11.2026).
   `Нова игра` pita za potvrdu usred partije i na zavrsnom ekranu dok rezultat nije sacuvan.
8. Posle zavrsene partije igrac moze da napravi link za deljenje, jednom po partiji (ponovni
   klik daje isti link), nezavisno od rang liste. Link otvara stranu samo za citanje: zavrsni
   ekran, datum deljenja i ime ako je partija sacuvana; vazi 30 dana, posle toga strana kaze
   da rezultat vise nije dostupan.
9. Moderator, prijavljen imenom i lozinkom, brise rezultat sa rang liste ili deljeni link uz
   potvrdu; brisanje je trajno i upisano u dnevnik (ko, sta, kada, snimak). Partija obrisanog
   rezultata se ne cuva ponovo; partija obrisanog linka ne dobija nov. Glavni moderator upravlja
   nalozima i ulogom glavnog; uvek ostaje bar jedan aktivan glavni. Igraci nemaju naloge.

10. **Dnevni izazov** (od 2026-11-12). Svakog dana (Europe/Belgrade) svi igraci igraju istu partiju:
    isti zadaci (redosled je fiksan) i isti ishodi, jer je seme dana tajni HMAC datuma, koji server
    pravi i koji nikad ne ide klijentu. Igra se jednom po sesiji i danu, bez „Нова игра“. Partija pamti
    dan pocetka i cuva se na listu tog dana. Pocetni ekran pokazuje i rang listu dana: 10 najboljih
    sa danasnjim danom, ista polja i isti redosled kao glavna; posle ponoci je prazna. Dnevni rezultat
    ne ide na glavnu listu, obican ne ide na listu dana. Bodovanje, deljenje i moderacija su isti.
    Hes partije se racuna iz nasumicne `oznake` partije, ne iz semena.

11. **Prijava neprikladnog imena** (od 2026-11-12). Ispod glavne liste i liste dana igrac bira ime sa
    liste i prijavljuje ga. Prijaviti se moze samo red koji je na ekranu (10 najboljih glavne liste ili
    liste danas), iz sesije koja ima partiju, jednom po sesiji i redu; po rezultatu se belezi najvise
    100 prijava. Prijava nista ne sakriva i nista ne brise. Moderator na strani „Преглед“ vidi
    prijavljena imena (broj prijava, prva prijava) i odlucuje: brise rezultat (kao tok 9) ili ostavlja
    ime. Odluka da ime ostaje ide u dnevnik („одбачена пријава имена“), brise prijave i vazi dok je zapis
    u dnevniku: kasnije prijave istog rezultata se ne beleze. Prijave liste ranijeg dana se brisu, jer ta
    lista vise nije na ekranu.

12. **Od 2026-11-12.** Strana „Kako se igra“ (link sa pocetnog ekrana) objasnjava pravila i racuna primer
    jednog kruga motorom; ne pokazuje sansu, oznaku `tiha` ni koji su zadaci tihi. Zvuk ishoda kruga, iskljuciv i
    zapamcen u pregledacu, zavisi samo od javnog statusa: uspeh i tih neuspeh zvuce isto. Igrac vidi svojih
    poslednjih 10 zavrsenih partija (ovaj pregledac, sesija). Moderator vidi statistiku: broj partija koje su
    stigle do zavrsnog ekrana i prosek poena po danu, 7 dana. Partneri preuzimaju glavnu i danasnju listu u JSON-u
    na `api/rang-lista/`, sa istim poljima kao strana.

Ocena: 85 i vise odlican orkestrator, 65 do 84 solidan, 40 do 64 skup ucitelj, ispod 40 pozar.

## Verzije pravila

Partija se boduje po pravilima sa kojima je pocela (`pravila` u stanju; stanje bez kljuca je 1).
Pravila 2 vaze od 2026-11-11. Sacuvan red nosi verziju; red ranije verzije ima oznaku
„старо бодовање“ i objasnjenje ispod liste. Deljena strana oznaku nema. Sacuvani poeni i snimci
se nikad ne preracunavaju.

## Lekcije na zavrsnom ekranu

Lekcija se prikazuje samo kada je uslov ispunjen; uz nju stoji odeljak rada.

| Uslov | Lekcija | Odeljak |
|---|---|---|
| tih neuspeh | Ako je greska tiha, zadatak ostaje najvisem razredu. | 4.2 |
| Opus na zadatku tezine 1 | Najskuplji model nije uvek najbolji izbor. | 3.2 |
| nivo `max` bar jednom | Iznad nivoa high cena raste, a kvalitet ne. | 3.3 |
| kontekst `sve` bar jednom | Previse konteksta kvari rezultat isto kao premalo. | 3.1 |
| 50 agenata bar jednom | Vise agenata ne znaci jeftinije. | 5.3 |

## Sta mora da pise na ekranu

Na zavrsnom ekranu, trajno: "Cene i nivoi razmisljanja su stvarni podaci; verovatnoce,
kazne i poeni su izmisljeni parametri igre."

## Recnik

| Rec | Znacenje |
|---|---|
| krug | jedan zadatak i jedan izbor igraca |
| vidljiva dorada | `vraceno na doradu`, placa se odmah |
| tiha greska | neuspeh koji izgleda kao uspeh do kontrolnog skupa |
| kontrolni skup | zavrsna provera posle 8. kruga |
| rang lista | 10 najboljih sacuvanih rezultata |
| sifarnik | spisak nepodobnih imena, samo na serveru |
| deljeni rezultat | snimak zavrsnog ekrana, dostupan linkom 30 dana |
| moderator | nalog koji brise rezultate i linkove i odlucuje o prijavljenim imenima |
| glavni moderator | moderator koji upravlja nalozima |
| dnevnik | ko je sta obrisao, promenio ili odlucio i kada, 365 dana |
| prijava imena | igrac oznacava ime sa rang liste kao neprikladno; odlucuje moderator |
| oznaka reda | javna oznaka reda liste kojom pregledac prijavljuje ime; nije id ni partija |

Tekst na ekranu postoji na srpskom (cirilicom) i engleskom; Haiku, Sonnet, Opus, low, high,
max, CSS i CRUD su isti na oba jezika. Jezik bira igrac i pamti se u kolacicu; novi posetilac
dobija jezik pregledaca (engleski ako ga trazi, inace srpski). Rang lista i deljena strana su na
jeziku onoga ko gleda; ime igraca se ne prevodi. Engleski naziv igre je „Orchestrator“.
Engleske ocene, lekcije i napomena cekaju pregled klijenta. Brojevi su u
`references/parametri.md`: tu je i poreklo svakog broja.
