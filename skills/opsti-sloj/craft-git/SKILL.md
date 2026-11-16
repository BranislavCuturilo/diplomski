---
name: craft-git
description: >
  Pravila za git i isporuku za svaki stek: sta se nikad ne radi deljenoj grani,
  kako isporuka preuzima kod i kako pada glasno a ne tiho. Ucitaj PRE izmene
  CI/CD pipeline-a, deploy skripte, Docker/compose fajla ili prepisivanja istorije.
  Okidaci: "deploy", "force push", "rebase", "GitHub Actions", "nista se nije isporucilo".
---

# craft-git

## Tri pravila koja se nikad ne preskacu

1. **Deljena istorija se ne prepisuje.** Ni zbog greske u opisu commita.
   Server koji radi `git pull` posle force-push-a staje, a stari kontejner
   nastavlja da radi, pa izgleda kao da je isporuka prosla.
   *Poreklo: produkcija je danima vrtela stari kod.*

2. **Isporuka ne radi `git pull`, nego:**
   ```
   git fetch origin && git reset --hard origin/main
   ```
   Stanje servera je uvek tacno ono sto je na grani, bez spajanja.

3. **Ocekivani neuspeh komande se obradjuje izricito.** Pod `set -e`, `grep -q`
   koji ne nadje poklapanje vraca 1 i prekida isporuku.
   ```
   grep -q "pattern" file || true    # ocekivano: ponekad nema poklapanja
   ```
   *Poreklo: isporuka je padala posle migracije, ali samo kad nije bilo izmena prevoda.*

## Zamke

- Opis commita sa obrnutim navodnicima kroz `git commit -m "..."`: shell izvrsava
  sadrzaj izmedju njih. Koristi `git commit -F poruka.txt`.
- Svaki korak isporuke pise oznaku ("KORAK 3/7: migrate") pre izvrsavanja, da se
  iz loga vidi gde je stao.
- Korak koji sme da padne oznacava se kao takav u istom redu; svi ostali su fatalni.
- Nikad `git add -A` u repozitorijumu koji istovremeno menja vise procesa: dodaju se
  samo putanje koje si menjao.
