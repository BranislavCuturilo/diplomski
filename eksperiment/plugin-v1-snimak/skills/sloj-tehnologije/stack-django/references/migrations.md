# Django migracije

`makemigrations` pise migraciju koja radi na praznoj bazi. Na punoj ne mora.

- **NOT NULL kolona na punoj tabeli** ide u tri migracije: dodaj kao nullable →
  data migracija popuni → izmeni u NOT NULL. Jedna migracija sa `default=` drzi
  zakljucanu tabelu dok upisuje sve redove.
- **Unique ogranicenje na punoj tabeli:** prvo upit koji nalazi duplikate, pa
  ciscenje, pa ogranicenje. Inace migracija pada na produkciji, ne na testu.
- **`RunPython` koristi `apps.get_model("app", "Model")`**, nikad import modela:
  importovan model je danasnji, a migracija se izvrsava nad starom semom.
- **Svaka data migracija ima obrnutu funkciju** (makar `migrations.RunPython.noop`
  uz komentar zasto je nepovratna).
- **Preimenovanje polja:** `makemigrations` ponekad napravi brisanje + dodavanje
  (gubitak podataka). Uvek proceni generisanu migraciju; mora biti `RenameField`.
- Nikad ne menjaj migraciju koja je vec isporucena; pisi novu.
