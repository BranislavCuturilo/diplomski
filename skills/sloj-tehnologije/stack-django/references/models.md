# Django modeli

- **`full_clean()` ne proverava M2M veze.** U trenutku validacije objekat jos nema
  pk, pa M2M nije postavljen. Pravilo nad M2M (npr. "najvise 5 oznaka") ide u
  formu ili servis, ili u signal `m2m_changed`.
- **Ogranicenje u bazi, ne samo u `clean()`.** `UniqueConstraint` i
  `CheckConstraint` u `Meta.constraints`; `clean()` stiti samo forme.
- **`unique=True` + soft delete:** obrisan red i dalje zauzima vrednost. Koristi
  `UniqueConstraint(fields=[...], condition=Q(deleted_at__isnull=True))`.
- **`on_delete=CASCADE` na vlasniku podataka** brise istoriju sa njim. Za
  dokumente koji moraju ostati: `PROTECT` ili soft delete.
- **Menadzer sa opsegom:** svaki model sa vlasnikom ima `objects` sa metodom
  `for_user(user)`. Neograniceni pristup samo kroz izricito imenovan menadzer
  (`all_objects`), da se u pregledu vidi.
- **`__str__` ne sme da pravi upit** (npr. `self.group.name`), jer se poziva u
  admin listi za svaki red: N+1.
