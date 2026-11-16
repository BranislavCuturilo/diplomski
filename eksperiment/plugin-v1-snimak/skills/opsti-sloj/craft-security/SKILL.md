---
name: craft-security
description: >
  Bezbednosna pravila nastala iz stvarnih propusta, za svaki jezik. Ucitaj PRE
  koda koji cita ili pise tudje podatke: upit, endpoint sa id-em, provera prava,
  model sa vlasnikom, upload, kljuc ili lozinka. Okidaci: "da li korisnik A moze
  da vidi podatke korisnika B", "dozvole", "login", "pristup", "bezbednost",
  "security review", "IDOR".
---

# craft-security

## Tri pravila koja se nikad ne propustaju

1. **Svaki upit je ogranicen opsegom korisnika.** Ne postoji "ovaj upit je interni".
   Opseg se primenjuje u JEDNOM sloju (menadzer, repozitorijum), ne u svakom prikazu.

2. **Endpoint koji prima id proverava pravo kroz ISTI helper kao lista.**
   Najcesci stvarni propust: lista je filtrirana, detalj nije.
   Pravilo vazi za **svaki id u zahtevu**, ne samo za glavni:
   ```
   POST /transfer   { from_warehouse: 7, item: 12 }
   ```
   Provereno pravo nad `item`, a `from_warehouse` procitan bez provere =
   korisnik prebacuje robu iz tudjeg magacina.
   *Poreklo: incident, endpoint "izdaj robu".*

3. **GET nikad ne menja stanje.** CSRF zastita ne pokriva bezbedne metode, pa
   `GET /delete?id=5` izvrsava slika u tudjem mejlu.

## Zamke koje model sam ne vidi

- **Zastita koju niko ne poziva je gora od nepostojece**: kod se cita kao zasticen.
  Posle pisanja provere, `grep` da li je pozvana.
- **Polje `*_encrypted` mora stvarno biti sifrovano.** Ime polja nije zastita.
  *Poreklo: revizija nasla lozinke u cistom tekstu iza takvog imena.*
- **Poruka o gresci ne otkriva postojanje.** "Nemate pravo" za tudji objekat
  odaje da objekat postoji; vraca se isto kao za nepostojeci (404).
- **Upload:** ime datoteke od korisnika se nikad ne koristi kao putanja; tip se
  proverava po sadrzaju, ne po nastavku.
- **Tajne:** ni u kodu, ni u logu, ni u poruci greske, ni u testu.
- **Neispravan ulaz je 400, ne 500.** Ispravan JSON koji nije objekat (`"x"`, `[1]`, `5`, `null`),
  broj gde se ocekuje tekst, tekst gde se ocekuje broj i logicka vrednost umesto broja moraju
  dobiti 400, a stanje ostaje netaknuto. Telo zahteva cita jedna funkcija, ne svaki endpoint.
  *Poreklo: sistem brain, trag steka na obican unos klijenta.*

## Reference

| Posao | Otvori |
|---|---|
| endpoint sa id-em, provera prava | `references/authorization.md` |
