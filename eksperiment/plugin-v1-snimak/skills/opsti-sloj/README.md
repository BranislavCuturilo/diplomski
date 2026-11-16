# Sloj 1: opsti sloj

Pravila koja vaze za **svaki programski jezik i svaki radni okvir**, zauvek.
Prefiks imena: `craft-`.

## Kako se konfigurise skill u ovom sloju

```
craft-<oblast>/
  SKILL.md          # usmerivac: samo pravila koja se NIKAD ne smeju propustiti + tabela referenci
  references/       # detalji po situaciji; ne kostaju nista dok se ne otvore
    <tema>.md
```

Zaglavlje `SKILL.md`:

```yaml
---
name: craft-security
description: >          # 300-450 znakova. Recnikom KORISNIKA, ne strucnjaka:
  ...                   # "da li klijent A vidi podatke klijenta B", ne samo "IDOR".
---
```

## Pravila za ovaj sloj

- **Test pripadnosti:** zameni "Django" sa "Rails" i "MySQL" sa "Postgres". Ako je pravilo i dalje tacno, pripada ovde.
- **Ni jednog imena tehnologije u pravilu.** Primer u kodu sme biti na bilo kom jeziku, ali je samo ilustracija.
- **Svako pravilo navodi poreklo:** incident, merenje ili pozajmljena ideja sa datumom preispitivanja.
- Telo `SKILL.md` do ~200 redova. Preko toga: deli u `references/`.

## Skillovi u ovom sloju

| Skill | Pokriva |
|---|---|
| `craft-code` | gde logika zivi, greske, granice funkcija, sta se ne radi "usput" |
| `craft-security` | opseg podataka, ovlascenje po id-u, neproverljiv ulaz, tajne |
| `craft-testing` | testovi bez stvarnih spoljnih efekata, test koji ne moze proci prazno |
| `craft-git` | deljena istorija, isporuka koja ne pada tiho |
| `craft-i18n` | prevodi koji ne lome poruke |
| `craft-delegiranje` | kada i kako se posao predaje podagentu, jedna poruka, oblik izvestaja |
