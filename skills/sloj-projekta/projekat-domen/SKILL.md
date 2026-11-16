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

2. **Ishod je cista funkcija semena i odluka.** Uspeh kruga: `random.Random("<seme>:<krug>").randint(1, 100) <= sansa`.
   Nikad globalni `random`, sat ni redosled skupa. Seme pravi server pri novoj igri;
   klijent ga ne zadaje. Zato isti ulaz daje isti ishod, a dupli klik ne menja rezultat.

3. **Potez vazi samo za tekuci krug.** POST nosi broj kruga i cetiri izbora.
   Drugi broj kruga ili igra koja je zavrsena: 409. Nepoznat izbor: 400, stanje netaknuto.
   Klijent nikad ne salje cenu, poene ni ishod.

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
   cenu tog zadatka i jos jednom njegove minute; -25 poena.
5. Prekoracenje se ne prekida: igra ide do kraja, a kazna je na kraju
   (budzet -30, rok -20). Poeni su najmanje 0, a pocinju od 100.
6. Zavrsni ekran: poeni, ocena, ukupna cena i minuti, spisak tihih gresaka, lekcije.

Ocena: 85 i vise odlican orkestrator, 65 do 84 solidan, 40 do 64 skup ucitelj, ispod 40 pozar.

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

Ceo tekst na ekranu je cirilicom. Brojevi su u `references/parametri.md`: tu je i
poreklo svakog broja.
