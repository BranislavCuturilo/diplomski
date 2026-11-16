# Sloj 2: sloj tehnologije

Pravila **jedne tehnologije**. Prefiksi: `stack-` (serverska), `ui-` (prikaz).
Ovaj sloj **dopunjuje** opsti sloj, ne ponavlja ga: `stack-django` ne pise ponovo
"proveri ovlascenje", vec KAKO se to u Django-u radi i gde se gresi.

## Kako se konfigurise skill u ovom sloju

```
stack-django/
  SKILL.md                 # usmerivac: zamke koje vaze za SVAKU Django datoteku
  references/
    models.md              # izvedeni skill za modele
    views.md               # izvedeni skill za prikaze uopste
    detail-view.md         # izveden iz views.md: SAMO prikaz detalja
    forms.md
    migrations.md
    testing.md
```

## Izvodjenje skillova

```
views.md  ──>  detail-view.md
```

Kada agent menja samo prikaz detalja, ucitava **samo** `detail-view.md`.
Zato izvedeni skill mora sam da nosi ono iz roditelja sto mu treba
(prepisuje 2-3 kljucna reda), a NE "vidi views.md" za kriticno pravilo.

Isto vazi za algoritme: opsti skill "sortiranje" moze imati izvedeni
"bubble sort u C-u" (malloc, rad sa pokazivacima). Za jezik koji nema
izvedeni skill ucitava se opsti.

## Pravila za ovaj sloj

- **Test pripadnosti:** da li je pravilo tacno u SVAKOM Django projektu? Da → ovde. Samo u jednom → sloj projekta.
- Navesti verziju kada zamka zavisi od nje (npr. "Django 4.0+: CSRF_TRUSTED_ORIGINS trazi semu").
- Opis skilla mora sadrzati reci koje korisnik kaze: "view", "prikaz", "forma", "migracija", "models.py".

## Skillovi u ovom sloju

| Skill | Pokriva |
|---|---|
| `stack-django` | modeli, prikazi, forme, migracije, testovi u Django-u |
| `ui-bootstrap` | Bootstrap 5 zamke: utility klase, dropdown u tabeli, validacija formi |
