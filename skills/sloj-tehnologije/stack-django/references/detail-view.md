# Django prikaz detalja (izveden iz views.md)

Ucitava se UMESTO `views.md` kada se menja samo prikaz detalja. Zato ovde
stoje i dva pravila iz roditelja bez kojih detalj nije bezbedan.

## Iz roditelja (prepisano namerno)

- `LoginRequiredMixin` prvi u nasledjivanju.
- Opseg u `get_queryset()`:
  ```python
  class NoteDetail(LoginRequiredMixin, DetailView):
      model = Note
      def get_queryset(self):
          return Note.objects.for_user(self.request.user).select_related("group")
  ```

## Samo za detalj

- **Tudji objekat = 404, ne 403.** `get_queryset` sa opsegom to daje sam.
- **Povezane kolekcije na detalju** (npr. beleske grupe) prolaze ISTI opseg:
  `group.notes.all()` u sablonu zaobilazi opseg ako beleske imaju svog vlasnika.
  Prosledi ih kroz `get_context_data` iz menadzera.
- **Dugmad za akcije** (izmeni, obrisi) prikazuju se samo ako korisnik sme; ali
  skrivanje dugmeta NIJE zastita, endpoint akcije proverava sam.
- **Test:** vlasnik vidi (200), drugi korisnik dobija 404, neprijavljen ide na login.
