# Django prikazi (uopste)

- **Svaki CBV koji cita po pk-u preklapa `get_queryset()`**, ne `get_object()`.
  `get_queryset()` vazi i za detalj, i za izmenu, i za brisanje; jedna tacka.
- **`LoginRequiredMixin` ide PRVI u nasledjivanju**, levo od `DetailView`:
  `class NoteDetail(LoginRequiredMixin, DetailView)`. Desno nema efekta.
- **Akcija bez sablona** (POST koji menja stanje i preusmerava) nema
  `get_queryset` iz okvira: proveru opsega pises sam, kroz isti menadzer.
- **Posle uspesnog POST-a uvek redirect** (Post/Redirect/Get), inace osvezavanje
  stranice ponovo salje formu.
- **`select_related` / `prefetch_related`** za svaku vezu koja se prikazuje u
  listi; sablon koji u petlji cita `note.group.name` bez toga = upit po redu.
- **Paginacija na svakoj listi.** Lista bez paginacije radi na test podacima i
  pada na produkciji.
