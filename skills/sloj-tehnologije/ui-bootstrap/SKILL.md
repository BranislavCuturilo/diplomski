---
name: ui-bootstrap
description: >
  Bootstrap 5 zamke zbog kojih CSS "ne radi" i stranica ne izgleda kao ostatak
  aplikacije. Ucitaj PRE izmene sablona ili CSS-a: lista, forma, kartica, tabela,
  dropdown, modal, responsive. Okidaci: "meni je odsecen", "font-size ne radi",
  "ne izgleda kao ostatak", "na telefonu", "responsive", "dugme ne radi", "slike",
  "ikonice", "tema", "izgled".
---

# ui-bootstrap

## Tri pravila koja se nikad ne preskacu

1. **Utility klase imaju `!important`.** `.fs-6`, `.p-3`, `.text-muted` pobedjuju
   tvoj CSS. Ako `font-size` "nema efekta", element ima utility klasu: ukloni je,
   ne dodaj `!important` sa svoje strane.

2. **Dropdown u `.table-responsive` biva odsecen**, jer kontejner ima `overflow`.
   Na dugmetu: `data-bs-boundary="viewport"`, ili meni van tabele, ili
   `data-bs-popper-config` sa `strategy: "fixed"`.

3. **Bootstrap 5 atributi imaju `-bs-`:** `data-bs-toggle`, `data-bs-target`.
   `data-toggle` (Bootstrap 4) tiho ne radi, bez greske u konzoli.

## Forme

- `<select>` dobija `.form-select`, ne `.form-control`.
- Greska polja: `.is-invalid` na polju **i** `.invalid-feedback` kao SLEDECI brat
  u DOM-u. Ako izmedju stoji drugi element, poruka se ne prikazuje.

## Standard: filter na listi i tabeli

Svaki filter sa vise vrednosti izgleda i ponasa se ISTO u svakom projektu:

- padajuci meni sa visestrukim izborom, sa poljem za pretragu na vrhu menija;
- izabrane vrednosti kao znacke ispod polja, svaka sa x za uklanjanje;
- dugme "Ponisti" kada je bar jedna vrednost izabrana;
- stanje filtera u URL-u (GET parametri), da se lista moze podeliti linkom.

Projekat koji hoce drugacije to pise u SVOM skillu (nivo 2), samo za tu razliku.

## Skripta stranice

Kvar je tih: jedan izuzetak u skripti ubija sve kasnije rukovaoce, a stranica ne pokazuje gresku.

- **Element koji sablon moze da sakrije trazi se uz proveru**, i stranica se ucitava bas u stanju
  u kome ga nema, uz nula gresaka u konzoli. Provera koju nisi izvrsio u tom stanju nije proverena.
- **`el.className = "..."` brise i klasu po kojoj je element nadjen.** Koristi `classList`.
- **Isti red se ne pravi dvaput.** Server ga iscrta jednom u `<template>`, a skripta klonira i puni
  imenovana mesta. Oznaka ili `className =` u skripti je druga kopija, koja promasi sledecu ispravku.

*Poreklo: sistem brain, stvarni kvarovi na stranicama sa uslovnim blokovima.*

## Slike i ikonice

- **Svaka slika i ikonica je u projektu**, ne sa tudjeg servera: aplikacija mora da radi bez mreze,
  a tudja adresa se menja bez najave. Ikonice su SVG, iz jednog skupa i jednog stila za celu aplikaciju.
- **Svaki `src` mora stvarno da se ucita.** Slomljena slika izgleda isto kao "ovde nema nicega".
  Provera u pregledacu: nula odgovora 404, a svaka `<img>` ima `naturalWidth` vece od 0.
  *Poreklo: sistem brain, galerija u kojoj se nestala datoteka nije razlikovala od praznog mesta.*
- Ukrasna ikonica ima `aria-hidden="true"`; slika ima `alt`, a ukrasna `alt=""`.

## Provera izgleda, posle svake izmene sablona ili CSS-a

Napisano pravilo nije dokaz da se primenilo. Izgled se proverava u pregledacu, ne u kodu:

1. snimak na 375, 768 i 1280 px; na 375 px `document.documentElement.scrollWidth` nije veci od sirine prozora;
2. nula gresaka u konzoli i nula neuspelih zahteva;
3. snimljena su i stanja posle akcije (izabran izbor, greska, zavrsni ekran), ne samo pocetni ekran,
   i to posle zavrsetka animacije;
4. testovi i dalje prolaze.

*Poreklo: 2026-11-10, stil igre Orkestrator: dve greske u CSS-u videle su se tek na snimku. Bootstrap
klasa `.h4` vracala je boju naslova preko jaceg selektora, a animacija bez boje dala je na trenutak beo
tekst na beloj pozadini.*

## Raspored

- Svaka `.row` ima direktnu decu `.col-*`; sadrzaj direktno u `.row` gubi razmake.
- Nova stranica kopira raspored postojece iste vrste (lista, detalj, forma), ne
  izmislja svoj. Odstupanje od susedne stranice je greska i kada lepse izgleda.
- Proveri na 375 px sirine: tabela bez `.table-responsive` izlazi van ekrana.
