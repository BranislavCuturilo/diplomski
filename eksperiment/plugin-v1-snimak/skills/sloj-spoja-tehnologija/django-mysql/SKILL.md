---
name: django-mysql
description: >
  Zamke koje nastaju tek kada Django radi nad MySQL/MariaDB bazom: velika i mala
  slova u jedinstvenim poljima, migracije koje se ne vracaju, kodna strana.
  Ucitaj kada projekat koristi Django I MySQL, pre modela sa unique poljem ili
  migracije. Okidaci: "MySQL", "MariaDB", "duplikat", "migracija pukla na pola".
---

# django-mysql

## Tri pravila koja se nikad ne preskacu

1. **Podrazumevana kolacija ne razlikuje velika i mala slova.** `unique=True` na
   `username` odbija "Ana" ako postoji "ana", a `filter(name="ana")` vraca i "Ana".
   Na Postgres-u je obrnuto, pa test na SQLite/Postgres prolazi, a produkcija ne.
   Odluka mora biti izricita: ili `db_collation="utf8mb4_bin"`, ili namerno
   case-insensitive i tako testirano.

2. **DDL u MySQL-u nije transakcioni.** Migracija koja padne na pola ostavlja
   polovicnu semu; Django je ne vraca. Jedna migracija = jedna promena seme, i
   data migracija ODVOJENO od promene seme.

3. **Kodna strana `utf8mb4`, nikad `utf8`.** MySQL-ov `utf8` je 3-bajtni: emoji i
   neki znakovi pucaju pri upisu. U `DATABASES`: `"OPTIONS": {"charset": "utf8mb4"}`,
   a baza i tabele kreirane sa `utf8mb4`.

## Ostalo

- `TextField` ne moze imati `unique=True` (MySQL trazi duzinu kljuca). Koristi
  `CharField(max_length=...)` ili hash kolonu.
- `sql_mode` mora sadrzati `STRICT_TRANS_TABLES`, inace MySQL tiho skracuje
  predugacak tekst umesto da baci gresku.
- `select_for_update()` radi samo unutar `transaction.atomic()`; van nje Django baca gresku tek u runtime-u.
