---
name: craft-testing
description: >
  Disciplina testiranja za svaki jezik: test nikad ne dira stvarne podatke ni
  spoljne sisteme, tvrdnja ne sme da prodje prazna, kvar infrastrukture se
  razlikuje od kvara koda. Ucitaj PRE pisanja, menjanja ili pokretanja testova.
  Okidaci: "napisi test", "pokreni testove", "test pada", "flaky", "QA", "test baza".
---

# craft-testing

## Tri pravila koja se nikad ne preskacu

1. **Test baza je fizicki odvojena od prave.** Ne drugi prefiks na istom serveru
   nego druga baza, uz DVE nezavisne zastite (proveri ime baze pre pokretanja +
   korisnik baze bez prava na produkciju). Brisanje tabela u testu ne postuje
   filtere po redu.
   *Poreklo: test suite je mogao da obrise produkcione podatke.*

2. **Svaki spoljni efekat se neutralise U ISTOJ izmeni u kojoj se uvodi.**
   Novi backend za fajlove, mejl, SMS, API klijent: test podesavanja ga gase
   odmah. Podesavanja testa NASLEDJUJU produkciona, pa nov servis "prolazi" tiho.
   *Poreklo: testovi su nedeljama slali fajlove na produkcioni server.*

3. **Test proces odbija svaki upis ka spoljnom sistemu.** Ne mock "gde se setim",
   nego zastita na nivou klijenta koja baca gresku ako je ukljucen rezim testa.
   *Poreklo: test je objavio komentar na stvarnom tiketu klijenta.*

## Brzi i ceo paket

- Tokom rada i posle svake ispravke: `test_summary.py --brzo` (bez testova kroz pregledac).
- Ceo paket, sa pregledacem, JEDNOM po upitu, nad konacnim kodom, i to radi poslednji koji menja kod.
  Ako je ceo paket vec prosao, a posle njega su menjani samo Python fajlovi van sablona i skripti,
  ne ponavlja se: dovoljno je `--brzo` i test te ispravke.
- *Poreklo: poredjenje 2026-11-12, ceo paket 388 s, bez pregledaca 37 s; glavna sesija ga je pokrenula
  ponovo 4 min posle `qa`, iako izgled nije menjan.*

## Tvrdnja koja ne moze proci prazno

```
for item in response.items: assert item.owner == user    # PROLAZI ako je lista prazna
assert len(response.items) == 2                           # prvo ovo
```

- **Tvrdnju dokazuje samo njen pad.** Pokvari ono sto test tvrdi, pokreni taj test, zahtevaj
  da padne, vrati izmenu. Rasudjivanje je upravo korak koji je proizveo praznu tvrdnju.
- **Tvrdnja da nesto NE postoji trazi stvarnu vrednost.** Trazi tacnu tajnu ili broj, ne ime
  polja, i prvo dokazi da bi je provera nasla tamo gde sme da bude.
- **Tvrdi nad najmanjim delom koji nosi tvrdnju**, ne nad celom stranicom: kratak tekst nadje
  se u zaglavlju ili meniju.

*Poreklo: sistem brain, tvrdnja je prolazila i posle brisanja kolone koju je proveravala.*

## Kvar infrastrukture ili koda

Zid identicnih gresaka usred pokretanja (iste poruke o konekciji u 40 testova)
= infrastruktura. Ne menja se kod; prijavljuje se i staje.

## Reference

| Posao | Otvori |
|---|---|
| novi servis, mejl, fajlovi, API u testovima | `references/side-effects.md` |
