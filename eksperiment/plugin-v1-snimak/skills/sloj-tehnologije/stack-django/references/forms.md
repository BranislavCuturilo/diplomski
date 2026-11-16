# Django forme

- **ModelForm validira samo polja koja su u formi.** `UniqueConstraint` nad
  `(owner, title)` gde `owner` nije u formi se NE proverava, pa `save()` baca
  `IntegrityError` umesto lepe greske. Postavi `form.instance.owner` PRE
  `is_valid()` i proveri jedinstvenost u `clean()`.
- **Vlasnik se nikad ne prima iz POST-a.** `owner` nije u `fields`; postavlja se
  iz `request.user` u prikazu.
- **Queryset polja izbora mora imati opseg.** `ModelChoiceField` za grupu
  podrazumevano nudi SVE grupe svih korisnika; u `__init__` forme:
  `self.fields["group"].queryset = Group.objects.for_user(user)`.
  Inace korisnik POST-om upise belesku u tudju grupu.
- **`save(commit=False)` pa `save_m2m()`**: bez drugog poziva M2M se ne cuva.
- `fields = "__all__"` je zabranjeno: svako novo polje modela postaje unos korisnika.
