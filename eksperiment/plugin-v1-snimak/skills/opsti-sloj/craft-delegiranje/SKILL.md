---
name: craft-delegiranje
description: >
  Kada se posao predaje podagentu a kada se radi sam, kako se pise zadatak i sta
  se radi sa izvestajem. Ucitaj PRE prvog pokretanja agenta i kada posao izgleda
  dovoljno sirok za paralelni rad. Okidaci: "podeli posao", "pokreni agente",
  "paralelno", "talas", "podagent", "delegiraj", "agent je vratio los rezultat".
---

# craft-delegiranje

Delegiranje nije besplatno: podagent krece od praznog konteksta, ponovo istrazuje
i vraca izvestaj koji neko mora da procita.

## Tri pravila koja se nikad ne preskacu

1. **Nezavisni poslovi idu u JEDNU poruku.** Pozivi u istoj poruci rade istovremeno,
   a u zasebnim porukama jedan za drugim, iako izgledaju isto. Prvo nabroji sve
   nezavisne delove, pa ih pokreni zajedno, najvise 3 po talasu. Redom ide samo
   stvarna zavisnost: B treba izlaz A.
   *Poreklo: merenje u sistemu brain, 172 od 235 pokretanja bila su pojedinacna, oko 1.264 s zidnog vremena.*

2. **Zadatak je jedino sto podagent zna.** Navedi cilj, tacne datoteke, dogovorena
   imena (URL, polja, sabloni) da se delovi slazu, sta je vec utvrdjeno i oblik
   izvestaja. Podagent nema alat Skill: za skill van njegovog zaglavlja navedi
   putanju datoteke da je procita.

3. **Izvestaj se prihvata, ili se posao ponavlja razred vise.** Ne radi isti posao
   ponovo u glavnoj sesiji. Rezultat kome se ne moze verovati znaci los zadatak ili
   preslab razred. Prenesi i sta podagent NIJE mogao da utvrdi.

## Kontrolni skup posle izmene

- Agenti za proveru dobijaju spisak izmenjenih datoteka i proveravaju samo njih i ono sto od njih zavisi.
- Bezbednosnu reviziju pokreni samo ako izmena dira ulaz, sesiju, stanje, URL-ove, cuvanje podataka ili
  ono sto se salje klijentu. Izmena samo izgleda to ne dira.
- Ceo paket testova se pokrece uvek; on je jeftin, a pregled nije.

*Poreklo: poredjenje 2026-11-10, provera je bila 66 % cene, a u fazi stila je pokrenuta i bezbednosna revizija.*

## Ne delegiraj

- posao od nekoliko poziva alata;
- ponovno citanje sopstvene izmene (nezavisan pregled je nesto drugo);
- ono sto trazi istoriju razgovora;
- jedan mali posao iseckan da bi izgledao paralelno.

## Oblik izvestaja

Trazi zakljucak i mesto u kodu, nikad sadrzaj datoteka: izvestaj ostaje u kontekstu
glavne sesije do kraja rada.
