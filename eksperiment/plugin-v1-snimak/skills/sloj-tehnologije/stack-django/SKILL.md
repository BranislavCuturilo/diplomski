---
name: stack-django
description: >
  Django zamke koje kostaju vreme, iznad craft-code i craft-security. Ucitaj PRE
  pisanja ili pregleda Django koda: models.py, views.py, forms.py, migracija,
  sablon, test, management komanda. Okidaci: "model", "view", "prikaz", "forma",
  "migracija", "queryset", "zasto full_clean pada", "validacija ne radi".
---

# stack-django

Ovaj fajl nosi samo ono sto vazi za SVAKU Django datoteku. Za konkretnu vrstu
datoteke otvori SAMO njenu referencu, ne sve.

## Tri pravila koja se nikad ne preskacu

1. **`Model.save()` ne poziva `full_clean()`.** Validacija iz `clean()` se ne
   izvrsava kada kod pozove `save()` direktno (servis, komanda, API). Servis koji
   kreira objekat poziva `full_clean()` izricito.

2. **`QuerySet.update()`, `bulk_create()` i `delete()` na querysetu zaobilaze
   `save()`, `delete()` modela i signale.** Logika u `save()` (npr. racunanje
   polja, audit) se tada ne izvrsava. Ako logika mora da se izvrsi: petlja kroz
   objekte ili ista logika u servisu.

3. **Objekat po pk-u se cita kroz menadzer sa opsegom:**
   ```python
   note = get_object_or_404(Note.objects.for_user(request.user), pk=pk)   # da
   note = get_object_or_404(Note, pk=pk)                                  # IDOR
   ```

## Usmerivac: otvori samo jedno

| Menjas | Otvori |
|---|---|
| `models.py` | `references/models.md` |
| prikaz, bilo koji | `references/views.md` |
| SAMO prikaz detalja | `references/detail-view.md` (ne i views.md) |
| `forms.py` | `references/forms.md` |
| migraciju | `references/migrations.md` |
| test | `references/testing.md` |
