# Sloj 3: sloj spoja tehnologija

Pravila koja postoje **tek kada se dve tehnologije sretnu**. Ni Django ni
MySQL pojedinacno nemaju problem sa velikim i malim slovima u jedinstvenom
polju; zajedno ga imaju. Takvo pravilo ne pripada ni `stack-django` ni
opstem sloju.

## Kako se konfigurise skill u ovom sloju

```
<tehnologija-a>-<tehnologija-b>/
  SKILL.md
```

Ime nosi OBE tehnologije. Opis navodi obe, da se ucita samo kada su obe u projektu:

```yaml
---
name: django-mysql
description: >
  Django na MySQL/MariaDB ... Ucitaj kada projekat koristi Django I MySQL ...
---
```

## Pravila za ovaj sloj

- **Test pripadnosti:** da li pravilo prestaje da vazi ako zamenis JEDNU od dve tehnologije? Da → ovde.
- Ne ponavljati pravila iz slojeva 1 i 2, samo ono sto nastaje na spoju.
- Projekat bira koje spojeve ucitava (u `CLAUDE.md` projekta: "spojevi: django-mysql, django-nginx-docker").

## Skillovi u ovom sloju

| Skill | Spoj |
|---|---|
| `django-mysql` | Django ORM i migracije na MySQL-u |
| `django-ssr-bootstrap` | Django sabloni koje iscrtava server + Bootstrap 5 |
| `django-nginx-docker` | Django iza Nginx-a, u Docker-u, sa TLS-om |
