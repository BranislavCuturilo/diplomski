# Sloj 4: sloj projekta

Pravila **jedne aplikacije**. Zive u repozitorijumu projekta
(`<projekat>/.claude/skills/`), pa ih dobija svako ko klonira projekat, u istoj
verziji kao i kod.

**Projektni skill preovladjuje nad svim slojevima iznad.** To ne znaci da je
bolji, nego da je STANDARD te aplikacije. Ako je aplikacija legacy i sve je u
jednom fajlu, nova funkcionalnost se pise tako, a ne po `craft-code`.

## Nivoi unutar projekta

| Nivo | Sta je | Preovladjuje nad |
|---|---|---|
| 1 | slojevi 1-3 (opsti, tehnologija, spoj) | nicim |
| 2 | projektni skillovi (`projekat-*`) | nivoom 1 |
| 3 | odluke korisnika za sukob dva skilla na nivou 2 | nivoom 2 |

**Sukob na istom nivou se ne resava precutno.** Agent staje, pita korisnika, a
odgovor se upisuje u skill nivoa 3 sa datumom i razlogom. Sledeca sesija ne pita ponovo.

## Kako se konfigurise projektni skill

```yaml
---
name: projekat-standardi
nivo: 2
preovladjuje: [craft-code, stack-django]   # izricito: nad kojim pravilima
description: >
  Standardi igre Orkestrator ... Ucitaj PRE svake izmene u ovom projektu.
---
```

Telo navodi za svako pravilo: **sta**, **zasto u ovoj aplikaciji**, i koje opste
pravilo time pada.

## Skillovi u ovom sloju (primer: igra Orkestrator)

| Skill | Nivo |
|---|---|
| `projekat-standardi` | 2 |
| `projekat-domen` | 2 |
| `projekat-odluke` | 3 |
