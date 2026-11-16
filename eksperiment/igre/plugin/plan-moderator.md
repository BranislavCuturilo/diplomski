## 14. Moderator (2026-11-11)

Status: **sva pitanja su odlucena (M1-M4, N1), a zastite potvrdjene (14.11); talas T1 moze da pocne.** Nista nije pokrenuto.
Zahtev klijenta: moderator se prijavljuje imenom i lozinkom, brise rezultat sa rang liste ili deljeni link i vidi ko je sta obrisao i kada. Igraci i dalje igraju bez naloga. Prvog moderatora pravi razvijalac.
Izvori: `projekat-standardi` pravilo 3; MVP 2 i MVP 6; plan 10.4 (plan.md:466), 11.4, 11.8 i 11.11; kod `orkestrator/settings.py`, `igra/views.py`, `igra/models.py` i komande.

**Odgovoreno (ne pita se ponovo):**

| # | Odluka |
|---|---|
| M1 | Nalozi kroz `django.contrib.auth`, uz dozvolu `igra.moderira`; bez admina i bez grupa. |
| M2 | Moderatorima se upravlja na strani; prvog pravi razvijalac komandom. |
| M3 | Brisanje je tvrdo; dnevnik cuva snimak. |
| M4 | Dnevnik se cuva 365 dana; cisti ga `dnevnik_ocisti`. |
| N1 | Nalozima upravlja samo glavni moderator (dozvola `igra.upravlja_nalozima`). Obican moderator brise, cita dnevnik i menja sopstvenu lozinku. |
| zastite | Obavezna promena pocetne lozinke i potvrda sopstvenom lozinkom za radnje nad tudjim nalozima. |
| preporuke | Prihvacene: sr i en; bez admina i bez `createsuperuser`; ogranicenje pokusaja prijave; potvrda brisanja na posebnoj strani, bez skripte; obrisan link daje isti 404 kao istekao; brisanje rezultata i linka su nezavisni; sesija moderatora traje 8 h; prijava i odjava cuvaju partiju; sifarnik ostaje na komandama. |

### 14.1 Sukob i sta vise ne vazi

| Mesto | Kaze | Sada |
|---|---|---|
| `projekat-standardi` pravilo 3 | „Tri modela, bez naloga ... bez admina“ | Nalozi postoje samo za moderatore. Modela je pet (novi: `ZapisDnevnika` i `NalogModeratora`). Admina i dalje nema. Odluka se upisuje u `projekat-odluke` (14.12). |
| MVP 2 | „nalozi i prijava“ su van MVP-a | Nalog moderatora je u MVP-u; nalozi igraca ostaju van. Menja korisnik. |
| plan.md:322 (10.1) | „`INSTALLED_APPS` se ne menja“ | Dodaju se `django.contrib.contenttypes` i `django.contrib.auth`. |
| plan.md:466, 11.8 | Garancija „partija obrisanog reda se ne cuva / ne deli ponovo“ stoji na oznaci u sesiji i na id-u reda | Stoji na dnevniku (`ZapisDnevnika.partija`), nezavisno od id-a (14.4). |
| plan.md:468 (10.4) | Ime igraca ide samo kroz `json_script` i `textContent` | I dalje vazi za igru i deljenu stranu. Moderatorske strane nemaju skriptu, pa ime ide kroz autoescape `{{ }}` u `<bdi>`; nikad kroz `|safe` ni u atribut. |

Ne menjaju se motor, `parametri.py`, `imena.py` ni `igra.js`. Ne menjaju se ni tabele `igra_rezultat` i `igra_deljenirezultat`, pa se ne prepravljaju, a `sqlite_sequence` ostaje kakav je.

### 14.2 Prijava i sesija

**`settings.py`:**
- `INSTALLED_APPS`: dodaju se `contenttypes` i `auth`, ispred `igra`. Bez `admin`, bez `messages` i bez context processora `auth`.
- `MIDDLEWARE`: `AuthenticationMiddleware` odmah posle `SessionMiddleware`. `request.user` je lenj; igra i `deljeno` ga ne citaju, pa ni sesiju ne diraju (to cuva `test_strana_ne_pravi_sesiju`).
- `AUTH_PASSWORD_VALIDATORS`: cetiri Django validatora; `MinimumLengthValidator` sa `min_length: 12`. Hes ostaje podrazumevani PBKDF2-SHA256.
- `LOGIN_URL = "moderator_prijava"`. `CACHES` se navodi izricito: `LocMemCache`.
- Nove vrednosti: `MODERATOR_SESIJA_SEKUNDI = 8 * 3600`, `PRIJAVA_POKUSAJA = 5`, `PRIJAVA_BLOKADA_SEKUNDI = 900`, `DNEVNIK_DANA = 365`.
- Kolacici sesije: `SESSION_COOKIE_HTTPONLY = True` i `SESSION_COOKIE_SAMESITE = "Lax"`, oba izricito.
- `SESSION_COOKIE_SECURE` i `CSRF_COOKIE_SECURE` su `False`, uz komentar „lokalni http; pri isporuci True“.
- `CSRF_COOKIE_HTTPONLY = False` ostaje, jer skripta cita CSRF kolacic.

**Jedna sesija (isti `sessionid`) za igru i za moderatora:**
- `login()` zove `cycle_key()`: kljuc je nov, a podaci ostaju, pa partija u toku prezivi prijavu.
- `login()` zove i `rotate_token`. `igra.js` cita `csrftoken` pri svakom POST-u (igra.js:433, 647, 726), pa kartica igre radi dalje.
- `logout()` brise sesiju, a s njom i partiju. Zato `odjava` radi ovako: `igra = session.get("igra")`, zatim `logout(request)`, pa `session["igra"] = igra` ako je partija postojala.
- Posle prijave `set_expiry(MODERATOR_SESIJA_SEKUNDI)`. Isti rok vazi i za partiju u tom pregledacu, sve do odjave.
- Kada glavni postavi tudju lozinku, hes sesije se promeni i Django brise sesiju vlasnika, a s njom i njegovu partiju. Prihvaceno.
- Deaktiviran nalog `ModelBackend.get_user` vec od sledeceg zahteva vraca kao anonimnog. Sesija ostaje, pa partija nije izgubljena.

**`prijava`** (GET i POST; `@sensitive_post_parameters("password")`, `@never_cache`):
```
kljuc = "prijava:" + sha256(username.casefold())
ako cache[kljuc] >= PRIJAVA_POKUSAJA: poruka blokade; authenticate se ne zove
PrijavaForma (AuthenticationForm): confirm_login_allowed odbija ko nije moderator (14.3), istom porukom
uspeh: cache.delete(kljuc); login(); set_expiry; redirect na next (url_has_allowed_host_and_scheme) ili na "moderator"
neuspeh: brojac + 1, rok PRIJAVA_BLOKADA_SEKUNDI; ista poruka za pogresno ime, pogresnu lozinku i neaktivan nalog
```
- Brojac pokusaja vodi se po imenu, ne po IP-u. Broji i nepostojece ime, pa ne odaje da li nalog postoji.
- Isti brojac (kljuc po imenu onoga ko radi) vazi i za potvrdu sopstvenom lozinkom (14.5).
- `sensitive_post_parameters` stoji na svakom prikazu koji prima lozinku. Razlog: `DEBUG = True` (settings.py:13), a `FilterBezPromenljivih` (greske.py:6-8) ne skriva POST podatke.
- `odjava` prima samo POST, uz CSRF.

### 14.3 Ovlascenje i uloge

| Uloga | Uslov | Sme |
|---|---|---|
| moderator | aktivan, ima `igra.moderira` i `NalogModeratora` | pregled, brisanje, dnevnik, sopstvena lozinka |
| glavni | moderator i jos `igra.upravlja_nalozima` | sve sto i moderator, plus `nalozi*` |

**Gde stoje dozvole.** Obe dozvole su u `ZapisDnevnika.Meta.permissions`. Pravi ih `post_migrate`, pa postoje i posle `flush` u `test_tok`. Dodeljuju se direktno korisniku, kroz `user_permissions`, bez grupa: `flush` grupe brise, a migracije sa podacima ih ne vracaju.

**Provera.** Ide kroz jedan pomocnik `moderacija.uloga(user)`, koji vraca `None`, `"moderator"` ili `"glavni"`. Pomocnik zahteva `is_active`, `not is_superuser` (superuser bi kroz `has_perm` imao sve) i postojanje `NalogModeratora`.

**Dekoratori.** `moderator_potreban` stoji na svakoj ruti `moderator*` osim prijave. `glavni_potreban` ga obuhvata i stoji na svakoj ruti `moderator_nalozi*`. Redosled provera:
1. nije moderator: 302 na prijavu (GET i POST);
2. `mora_promeniti`: 302 na `moderator_lozinka` (propustaju se samo `moderator_lozinka` i `moderator_odjava`);
3. ruta `nalozi*` i uloga nije glavni: **403**, sa sablonom `moderator/zabranjeno.html` na jeziku korisnika. Telo je isto za svaku `nalozi*` rutu i svaki id.

**Zasto 403, a ne 404.** Obican moderator je prijavljen i zna da glavni postoji, pa ruta nije tajna. Pravilo craft-security „ne odaj postojanje“ vazi za objekte: 403 se vraca pre citanja id-a, pa ne govori koji nalozi postoje. 404 bi samo otezao otkrivanje greske u dodeli uloge. Stavka „Модератори“ u meniju vidi se samo glavnom. Ovaj 403 se ne oslanja na globalni `403.html`, jer bi Django van njega dao neprevedenu stranu.

**Opseg naloga.** `moderacija.moderatori()` je jedini queryset korisnika na strani: svi sa `NalogModeratora`, i aktivni i neaktivni. `nalozi/<id>/` cita kroz njega, pa id van opsega daje 404, i to tek kada je uloga glavni vec proverena.

**Ponovna provera pod bravom.** Svaki servis (14.4, 14.5), unutar `transaction.atomic()` (IMMEDIATE), ponovo cita iz baze onoga ko radi. Svezi objekat znaci da nema starog `_perm_cache`. Provera ide kroz `_proveri_ulogu(ko, potrebna)`, jer je `request.user` procitan pre brave.

**IDOR ovde nije problem samo dok vaze svi ovi uslovi:**
1. Svi moderatori imaju isti, pun opseg nad rezultatima i linkovima, a svi glavni nad nalozima.
2. Id rezultata ili linka cita se kroz isti queryset kao lista.
3. Id naloga cita se kroz `moderatori()`.
4. Nijedan prikaz igraca ne prima id.
5. Svaka ruta ima odgovarajuci dekorator, sto proverava test koji nabraja rute.

### 14.4 Brisanje (tvrdo) i garancija

**Servis `igra/brisanje.py`** je jedini put brisanja, i za prikaze i za komande:
```
obrisi_rezultate(ids, ko: User | None) -> list[ZapisDnevnika]
obrisi_deljene(ids, ko: User | None) -> list[ZapisDnevnika]
  transaction.atomic(); _proveri_ulogu(ko, "moderator") ako ko nije None
  redovi po id-u; ako ijedan fali: NemaReda(ids), nista se ne brise
  za svaki red: ZapisDnevnika(radnja, ko, red=id, partija=red.partija, snimak=...).full_clean(); save()
  QuerySet.delete() nad tim id-jevima, u istoj transakciji (modeli nemaju delete() ni signale)
```

**Komande.** `rezultat_obrisi` (rezultat_obrisi.py:27), `deljeni_obrisi` (deljeni_obrisi.py:31) i `nepodobno_dodaj --obrisi-rezultate` (nepodobno_dodaj.py:59) idu kroz servis sa `ko=None`. U dnevniku se prikazuju kao „развијалац (команда)“. `deljeni_ocisti` ostaje kakav je: to je ciscenje isteklih linkova, ne moderacija, pa ne pise u dnevnik.

**Garancija „partija obrisanog reda se ne cuva ponovo“.**
- Danas je drzi oznaka `sacuvan` u sesiji (views.py:100-113). Kada se tabela prepravi, brojac se vraca i oznaka moze da pokaze na tudji red.
- Zato dnevnik cuva `partija` (sha256 semena), a `sacuvaj` i `podeli` ga proveravaju pod istom bravom.
- Pravilo 1 ostaje ispunjeno. `partija` nije seme nego hes 128 nasumicnih bita. Vec postoji u `Rezultat.partija` pod istim uslovom: nikad u odgovoru, sablonu ni ispisu.
- `sacuvaj` (views.py:286-293): posle `za_cuvanje`, ako `ZapisDnevnika.objects.obrisana("rezultat_obrisan", partija)`, vraca 409 `vec_sacuvano`.
- `podeli` (views.py:333-339): ako reda nema i `obrisana("link_obrisan", partija)`, vraca 409 `deljenje_isteklo`, sa oznakom `podeljeno` ili bez nje. Tekst poruke postaje „Линк за ову партију више није доступан.“
- Stari link daje isti 404 i iste bajtove kao istekao link.
- `dnevnik_ocisti` posle 365 dana brise i `partija`. To je bezbedno: sesija zavrsene partije istice posle 14 dana (`SESSION_COOKIE_AGE`; GET `/` sesiju ne upisuje), pa tada stanje partije vise ne postoji. Test proverava `DNEVNIK_DANA * 86400 > SESSION_COOKIE_AGE`.
- Linkovi koje je obrisao `deljeni_ocisti` nemaju zapis u dnevniku; za njih vazi rizik iz 11.11.

**Snimak u dnevniku.** Obe vrste brisanja imaju tacno `{ime, poeni, ocena, datum}`:
- rezultat: `datum` je trenutak cuvanja (`sacuvan`), a `ocena` je kljuc;
- link: `ime` je ime sa rang liste u trenutku brisanja ili `null`, a `datum` je `nastao`.

Token linka se ne cuva, ni kao hes: to je tajna pristupa, a dnevnik citaju svi moderatori 365 dana.

**Na strani:**
- Rang lista odmah ostaje bez reda, a 11. rezultat ulazi.
- Igrac ciji je rezultat obrisan vidi „sacuvano van liste“.
- Ime nestaje sa deljene strane (views.py:157 trazi po partiji).
- Brisanje rezultata ne brise link iste partije, i obrnuto.
- Obrisano se ne moze vratiti.

**Potvrda brisanja:**
- GET prikazuje snimak i ne menja nista.
- POST sa `{% csrf_token %}` brise, pa PRG na `moderator?poruka=obrisano`.
- Ako reda nema, a dnevnik ima zapis za taj id: `poruka=vec_obrisano`. Inace 404.
- Nepoznata vrednost `poruka` se ignorise.

### 14.5 Nalozi moderatora

**Servis `igra/nalozi.py`.** Svaka funkcija radi ovim redom:
1. `transaction.atomic()` (IMMEDIATE);
2. `_proveri_ulogu(ko, "glavni")`, ako `ko` nije None;
3. izmena;
4. provera nepromenljivih pravila ispod;
5. upis `ZapisDnevnika`.

Ako pravilo ne vazi, baca se `Odbijeno(kod)` i nista nije upisano.

| Funkcija | Ko | Pravila | Radnja |
|---|---|---|---|
| `dodaj(ko, ime, lozinka, glavni=False)` | glavni ili komanda | ime po `UnicodeUsernameValidator`, jedinstveno bez obzira na velika i mala slova (`username__iexact`); `validate_password`; `User` (`is_staff = is_superuser = False`), `moderira`, uz `glavni` i `upravlja_nalozima`; `NalogModeratora(mora_promeniti=True)` | `moderator_dodat` (snimak `{"glavni": bool}`) |
| `deaktiviraj(ko, nad)` | glavni ili komanda | `nad` iz `moderatori()`, aktivan, `nad != ko`; `is_active = False`; ako je `nad` bio glavni, uloga se oduzima u istoj transakciji | `moderator_deaktiviran` (snimak `{"glavni": bool}`) |
| `aktiviraj(ko, nad, lozinka)` | glavni ili komanda | `nad` neaktivan; nova lozinka, `is_active = True`, `mora_promeniti = True`; vraca se kao obican moderator | `moderator_aktiviran` |
| `postavi_lozinku(ko, nad, lozinka)` | glavni ili komanda | `nad != ko`; validatori; `set_password` gasi sve sesije `nad`; `mora_promeniti = True` | `lozinka_postavljena` |
| `dodeli_ulogu(ko, nad)` | glavni ili komanda | `nad` je aktivan moderator i nije glavni | `uloga_dodeljena` |
| `oduzmi_ulogu(ko, nad)` | glavni ili komanda | `nad` je glavni; dozvoljeno i `nad == ko` | `uloga_oduzeta` |
| `promeni_svoju(korisnik, stara, nova)` | svaki moderator | `PasswordChangeForm`; `mora_promeniti = False`; prikaz zove `update_session_auth_hash` | `lozinka_promenjena` |

**Nepromenljiva pravila.** Proveravaju se posle izmene, pod istom bravom, u servisu (ne u prikazu), pa vaze i za komande:
1. **Postoji bar jedan aktivan glavni:** `User.objects.filter(is_active=True, user_permissions=<upravlja_nalozima>).exists()`. Zato poslednjem aktivnom glavnom ne moze da se oduzme uloga, ni da bude deaktiviran, ni da sam sebi oduzme ulogu. Kod: `poslednji_glavni`.
2. **Niko ne deaktivira sebe** (`nad == ko`). Kod: `ne_sebe`. Za komandu (`ko=None`) ovo pravilo ne postoji, a pravilo 1 vazi.
3. **Glavni je uvek i moderator:** `upravlja_nalozima` bez `moderira` je nemoguc. Test to proverava.

Zato sto servis ponovo cita onoga ko radi, dva glavna koja istovremeno deaktiviraju jedan drugog ne ostavljaju nijednog: drugi zahtev ceka bravu, cita da njegov `ko` vise nije aktivan i dobija `Odbijeno`.

**Odluke plana (bez pitanja):**
- **Ko je glavni.** Glavni postaje onaj koga razvijalac napravi komandom `moderator_dodaj IME --glavni`. Ako aktivnog glavnog nema, komanda bez `--glavni` daje `CommandError` sa uputstvom. Tako je prvi moderator uvek glavni, ali izricito, ne preko skrivenog pravila.
- **Glavni na strani dodeljuje i oduzima ulogu.** Zasto: klijent ne zavisi od razvijaca kada glavni ode na odmor ili napusti posao. Rizik se time ne povecava: glavni vec moze da napravi nov nalog, a dodela trazi potvrdu sopstvenom lozinkom i ide u dnevnik.
- **Glavni moze da deaktivira drugog glavnog.** Uloga se pri deaktivaciji oduzima, a pri ponovnoj aktivaciji se ne vraca sama. Zasto: glavni su ravnopravni, inace zloupotrebljen nalog glavnog ne bi mogao da se zaustavi bez razvijaca. Pravilo 1 cuva bar jednog.
- **Potvrda sopstvenom lozinkom (potvrdjeno).** Trazi se za sve radnje glavnog nad tudjim nalozima i za oduzimanje sopstvene uloge. Neuspeh potvrde ulazi u brojac prijave.
- **Obavezna promena pocetne lozinke (potvrdjeno):** `NalogModeratora.mora_promeniti`.
- **Dnevnik pokazuje na korisnika preko FK `PROTECT`.** Korisnik se nikad ne brise ni ne preimenuje.
- Prijava i odjava se ne upisuju u dnevnik.

**Komande razvijaca, rezerva.** Sve idu kroz `nalozi.py` sa `ko=None`. Lozinka se unosi dvaput kroz `getpass`, nikad kao argument. Prvog moderatora pravi korisnik u terminalu; agent ne izmislja lozinku.

| Komanda | Ponasanje |
|---|---|
| `moderator_dodaj IME [--glavni]` | Kao `dodaj`. Bez aktivnog glavnog trazi `--glavni`. |
| `moderator_lozinka IME` | Kao `postavi_lozinku`. Neaktivan nalog se pri tom aktivira (otkljucavanje). |
| `moderator_glavni IME [--oduzmi]` | Kao `dodeli_ulogu` ili `oduzmi_ulogu`. Pravilo 1 vazi. |
| `moderator_deaktiviraj IME` | Kao `deaktiviraj`. Pravilo 1 vazi. Ispisuje broj preostalih aktivnih i glavnih. |
| `moderatori` | Ime, aktivan, glavni, `mora_promeniti`, poslednja prijava. Superuser se oznacava upozorenjem. |
| `dnevnik_ocisti [--dana 365]` | Brise zapise starije od N dana i ispisuje broj. |

Otkljucavanje kada niko nema pristup: `moderator_lozinka IME`, pa po potrebi `moderator_glavni IME`.

### 14.6 Modeli i migracije

```
class ZapisDnevnika(models.Model):
    id      = BigAutoField(primary_key=True)
    kada    = DateTimeField(default=timezone.now, editable=False)
    radnja  = CharField(max_length=24, choices=RADNJE)   # rezultat_obrisan, link_obrisan, moderator_dodat, moderator_deaktiviran,
                                                         # moderator_aktiviran, lozinka_postavljena, lozinka_promenjena, uloga_dodeljena, uloga_oduzeta
    ko      = ForeignKey(AUTH_USER_MODEL, null=True, on_delete=PROTECT, related_name="+")   # null = komanda razvijaca
    nad     = ForeignKey(AUTH_USER_MODEL, null=True, on_delete=PROTECT, related_name="+")
    red     = PositiveBigIntegerField(null=True)    # id obrisanog reda; bez FK
    partija = CharField(max_length=64, null=True)   # samo za garanciju 14.4; nikad u odgovoru
    snimak  = JSONField(default=dict)               # {ime, poeni, ocena, datum} za brisanja; {"glavni": bool} za dodat/deaktiviran; {} inace
    objects = ZapisQuerySet.as_manager()            # obrisana(radnja, partija) -> bool; najnoviji()
    Meta: permissions = [("moderira", ...), ("upravlja_nalozima", ...)]
          indexes = [Index(fields=["-kada"]), Index(fields=["radnja", "partija"])]
          constraints: CHECK radnja (nabrajanje sa OR, kao igra_pravila_poznata);
                       brisanje <=> red i partija nisu null; radnja nad nalogom <=> nad nije null
    save(): ako nije _state.adding -> ValueError("dnevnik se ne menja")

class NalogModeratora(models.Model):
    korisnik       = OneToOneField(AUTH_USER_MODEL, primary_key=True, on_delete=PROTECT, related_name="nalog_moderatora")
    mora_promeniti = BooleanField(default=True)
```
- `0009_moderator.py`: pravi ga `makemigrations`, bez rucnih izmena.
- `0010_dnevnik_okidac.py`: pise se rucno, `RunSQL` sa `CREATE TRIGGER igra_zapis_bez_izmene BEFORE UPDATE ON igra_zapisdnevnika BEGIN SELECT RAISE(ABORT, 'dnevnik se ne menja'); END;`; unazad `DROP TRIGGER IF EXISTS`.
- Okidac na DELETE ne postoji, jer bi blokirao `flush` u `test_tok` i komandu `dnevnik_ocisti`.

### 14.7 Ekran

| URL | Ime rute | Uloga | Metoda | Sablon |
|---|---|---|---|---|
| `moderator/prijava/` | `moderator_prijava` | - | GET, POST | `prijava.html` |
| `moderator/odjava/` | `moderator_odjava` | moderator | POST | - |
| `moderator/` | `moderator` | moderator | GET; POST samo za pretragu linka | `pregled.html` |
| `moderator/rezultat/<int:broj>/` | `moderator_rezultat` | moderator | GET potvrda, POST brisanje | `potvrda.html` |
| `moderator/link/<int:broj>/` | `moderator_link` | moderator | GET potvrda, POST brisanje | `potvrda.html` |
| `moderator/dnevnik/` | `moderator_dnevnik` | moderator | GET | `dnevnik.html` |
| `moderator/lozinka/` | `moderator_lozinka` | moderator | GET, POST | `lozinka.html` |
| `moderator/nalozi/` | `moderator_nalozi` | glavni | GET lista, POST dodavanje | `nalozi.html` |
| `moderator/nalozi/<int:broj>/` | `moderator_nalozi_nalog` | glavni | GET, POST `radnja` = `deaktiviraj`, `aktiviraj`, `lozinka`, `dodeli_ulogu` ili `oduzmi_ulogu` | `nalog.html` |

**Zajednicko svim stranama:**
- Sabloni su u `templates/igra/moderator/` i nasledjuju `osnova.html`.
- Meni: Преглед, Дневник, Лозинка, Одјави се; stavka „Модератори“ samo za glavnog (kontekst `glavni`).
- `zabranjeno.html` je telo 403 iz 14.3.
- Svi prikazi su `@never_cache`.
- `<head>` se izdvaja u `templates/igra/_glava.html` (treca upotreba).
- Zajednicko polje forme je u `templates/igra/_polje.html`.
- Na 375 px: `list-group` i `overflow-wrap: anywhere`; samo postojeci tokeni.
- Jezik: sr i en kroz `{% translate %}`. Greske Django formi dolaze iz Django kataloga.

**Strane:**
- `pregled`: 50 rezultata redom rang liste (prvih 10 oznaceno „јавно“) i 50 najnovijih vazecih linkova, bez tokena. Polje „nalepi link“ salje POST.
- `nalozi`: za svakog ime, aktivan, glavni, poslednja prijava i „мора да промени лозинку“. Forma za dodavanje ima ime, lozinku dvaput, polje „главни“ i vasu lozinku.
- `nalog`: forme samo za radnje dozvoljene u tom stanju. Za sopstveni nalog nema deaktivacije. „Одузми улогу“ se ne prikazuje kada je ovaj nalog poslednji glavni; server to i dalje proverava.
- `dnevnik`: 100 najnovijih zapisa; kolone kada (`10.11.2026 14:05`, kroz `tekstovi.datum_vreme`), ko, radnja, nad kim, snimak. Nikad `partija` ni `red`.

**Tekstovi (msgid):**

| Mesto | Tekst |
|---|---|
| prijava | Пријава модератора; Корисничко име; Лозинка; Пријави се; Одјави се; Погрешно корисничко име или лозинка. |
| blokada | Превише неуспешних покушаја. Покушајте поново за %(n)s минута. (`blocktranslate count`) |
| pregled | Резултати на ранг листи; Подељени линкови; Пронађи линк; Тај линк не постоји или више није доступан. |
| potvrda | Обрисати овај резултат? / Обрисати овај линк?; Брисање се уписује у дневник.; Потврди брисање; Одустани; Обрисано.; Ово је већ обрисано. |
| nalozi | Модератори; Додај модератора; Главни модератор; Ваша лозинка; Деактивирај; Активирај; Постави лозинку; Додели улогу главног; Одузми улогу главног; Морате да промените лозинку пре наставка. |
| odbijeno | `ne_sebe`: Не можете деактивирати свој налог.; `poslednji_glavni`: Мора остати бар један активан главни модератор.; 403: Ову страну види само главни модератор. |
| dnevnik | Дневник брисања и налога; Када; Ко; Шта; развијалац (команда); обрисан резултат; обрисан линк; додат модератор; деактивиран модератор; активиран модератор; постављена лозинка; промењена лозинка; додељена улога главног; одузета улога главног; Дневник је празан. |
| zavrsni ekran | `deljenje_isteklo`: Линк за ову партију више није доступан. |

### 14.8 Testovi

Samo postojece datoteke; `test_motor` ostaje kakav je.
Pomocne funkcije: `napravi_moderatora(ime, glavni=False, mora_promeniti=False)` i `napravi_korisnika_bez_dozvole(ime)`.
Osnovni skup u svakoj klasi: **neprijavljen**, **moderator**, **glavni**. Gde treba, jos drugi glavni i deaktiviran.

| Pravilo | Testovi (`test_prikazi`, osim gde pise `test_tok`) |
|---|---|
| matrica uloga | `test_matrica_ruta` nabraja sve rute `moderator*` osim prijave, za GET i POST. Neprijavljen, igrac sa partijom, korisnik bez dozvole, superuser i deaktiviran posle prijave dobijaju 302 na prijavu. Moderator na `nalozi*` dobija 403 i isto telo za svaki id (i nepostojeci), a na ostalim rutama 200 ili 302. Glavni dobija 200 ili 302 svuda. Nijedan odbijen zahtev ne menja bazu ni dnevnik. |
| mora promeniti | `test_mora_promeniti_pre_403` (moderator sa `mora_promeniti` na `nalozi`: 302 na lozinku, ne 403); propustene su samo lozinka i odjava |
| prijava | `test_prijava_cuva_igru`, `test_isti_odgovor_za_sve_neuspehe`, `test_next_van_sajta_ignorisan`, `test_lozinka_nije_na_tehnickoj_strani` (prijava, dodavanje, aktiviranje, postavljanje i promena lozinke) |
| ogranicenje | `test_peti_neuspeh_blokira_i_ispravnu`, `test_blokada_i_za_nepostojece_ime`, `test_blokada_istice`, `test_uspeh_brise_brojac`, `test_pogresna_potvrda_lozinkom_broji` |
| odjava, CSRF | `test_odjava_samo_post`, `test_odjava_cuva_igru_i_brise_prijavu`; `Client(enforce_csrf_checks=True)`: svaki POST bez tokena daje 403 i ne menja nista |
| brisanje | `test_get_potvrde_ne_brise`, `test_brisanje_rezultata` (snimak ima tacno cetiri kljuca, bez tokena i partije), `test_brisanje_linka` (isti 404 kao za nepostojeci), `test_vec_obrisano_preusmerenje`, `test_nepostojeci_id_404`, `test_ime_nestaje_sa_deljene`, `test_moderator_i_glavni_brisu` |
| garancija | `test_obrisana_partija_409` (sa oznakom i bez nje); `test_obrisana_partija_posle_ponovne_upotrebe_id` (`UPDATE sqlite_sequence`, druga partija dobija isti id: 409); isto za `podeli`; `test_dnevnik_dana_veci_od_sesije` |
| nalozi | `test_dodaj` (validatori, iexact, `mora_promeniti`, zapis, sa i bez `glavni`), `test_ne_sebe`, `test_poslednji_glavni` (deaktivacija, oduzimanje drugom i sebi daju `poslednji_glavni` i nula izmena; sa dva glavna oduzimanje sebi prolazi), `test_glavni_deaktivira_glavnog` (uloga oduzeta; posle aktiviranja nalog je obican), `test_uzajamna_deaktivacija_glavnih` (drugi zahtev, sa `request.user` ucitanim pre prvog, dobija `Odbijeno`; ostaje jedan aktivan glavni), `test_deaktiviran_odjavljen_igra_ostaje`, `test_postavi_lozinku_gasi_sesije`, `test_promeni_svoju_cuva_sesiju_i_igru` (i za obicnog moderatora), `test_aktiviraj_trazi_novu_lozinku`, `test_potvrda_sopstvenom_lozinkom`, `test_glavni_uvek_moderator`, `test_nalog_id_van_opsega_404` (glavni) |
| dnevnik | `test_save_odbija_izmenu`, `test_update_okidac`, `test_okidac_postoji`, `test_komanda_upisuje_bez_ko`, `test_uloga_u_dnevniku`, `test_redosled_i_kolone`, `test_partija_ne_izlazi`, `test_moderator_vidi_ceo_dnevnik` |
| bez skrivenog, XSS | moderatorske strane bez partije, semena, tokena i sifarnika; `test_strana_ne_pravi_sesiju` i `test_nijedan_odgovor_ne_sadrzi_skriveno` bez izmene; imena `</script><b>x` i `<svg onload=a()>` escape-ovana na pregledu, potvrdi, nalozima i u dnevniku |
| komande | `moderator_dodaj` (bez glavnog trazi `--glavni`), `moderator_lozinka` (otkljucava), `moderator_glavni` (i `--oduzmi` poslednjeg: `CommandError`), `moderator_deaktiviraj`, `moderatori`, `dnevnik_ocisti`; izmenjeni `rezultat_obrisi`, `deljeni_obrisi`, `nepodobno_dodaj --obrisi-rezultate` |
| jezik | sve moderatorske strane i 403 na sr i en, bez neprevedenog teksta |
| tok | `test_tok.ModeratorTokTests`: glavni se prijavljuje, menja pocetnu lozinku, dodaje moderatora, brise rezultat uz potvrdu, cita dnevnik i odjavljuje se; moderator nema „Модератори“ u meniju, a direktan URL daje 403 strane; `test_prijava_ne_prekida_igru`; `JS_PRELIVANJE` na 320 i 375 px za svaku stranu |

### 14.9 Talasi, agenti, dokazi, ugovor

| Talas | Datoteka | Agent |
|---|---|---|
| T1 | `orkestrator/settings.py`, `orkestrator/urls.py`, `igra/models.py`, `igra/migrations/0009_moderator.py` (`makemigrations`), `0010_dnevnik_okidac.py` (rucno), `igra/brisanje.py`, `igra/nalozi.py`, `igra/forme.py`, `igra/moderacija.py` (nove: `uloga`, `moderatori`, oba dekoratora, prikazi), `igra/views.py` (`sacuvaj` i `podeli`, 14.4), `igra/tekstovi.py` (`datum_vreme`, tekst `deljenje_isteklo`), komande `rezultat_obrisi`, `deljeni_obrisi`, `nepodobno_dodaj` i nove `moderator_dodaj`, `moderator_lozinka`, `moderator_glavni`, `moderator_deaktiviraj`, `moderatori`, `dnevnik_ocisti` | backend-senior |
| T1 | `templates/igra/_glava.html` i `_polje.html` (nove), `igra.html` i `deljeno.html` (samo include), `templates/igra/moderator/{osnova,prijava,pregled,potvrda,dnevnik,lozinka,nalozi,nalog,zabranjeno}.html` (nove), `static/igra/igra.css` | frontend-medior |
| T2 | `locale/{en,sr}/LC_MESSAGES/django.po` (`makemessages`, posle oba dela T1) | backend-senior |
| T3 | isti `.po` (engleski), `.mo` (`compilemessages`) | translate |
| T4 | `igra/tests/test_prikazi.py` i `test_tok.py` (qa); samo citanje (security). Oba u jednoj poruci. | qa, security |

Redosled backend-a: `settings`, `models`, `0009`, `0010`, `brisanje`, `nalozi`, `views`, `forme`, `moderacija`, `urls`, `tekstovi`, komande.

**Dokazi po fazama:**

*T1, backend:*
- `manage.py check` bez upozorenja.
- `makemigrations --check --dry-run` vraca „No changes detected“.
- `seq` za `igra_rezultat` i `igra_deljenirezultat` isti pre i posle `migrate` na lokalnoj bazi.
- `migrate igra 0008`, pa ponovo `migrate`.
- Postojeci testovi `EXIT=0`, ukljucujuci `MigracijaTekstaTests` i `MigracijaPravilaTests` (test_prikazi.py:3527, 3972).
- Skripta u scratchpad-u, na privremenoj bazi, kroz Django klijent. Ocekuje se:
  - prijava i odjava cuvaju igru;
  - sesti pokusaj prijave je blokiran;
  - matrica ruta daje 302, 403 ili 200 za neprijavljenog, moderatora i glavnog;
  - brisanje upisuje jedan zapis u dnevnik;
  - obrisana partija sa vracenim brojacem daje 409;
  - `UPDATE` dnevnika pada;
  - poslednji glavni ne moze biti deaktiviran;
  - dva glavna, jedan za drugim, ne mogu biti oba deaktivirana.
- Svaka komanda pokrenuta jednom na privremenoj bazi, sa zamenjenim `getpass`; ispis ide u izvestaj.

*T1, frontend:*
- Snimak HTML-a GET `/` (sr, seme 42, zavrsena partija) i deljene strane pre izmene; posle izmene isti bajtovi.
- Pregledac se ne pokrece do T4, i izvestaj to navodi.

*T3:*
- `msgattrib --untranslated --no-obsolete` za `en` je prazan.

*T4:*
- qa: `test_summary.py` `EXIT=0`; snimci svake strane na 320, 375 i 1440 px.
- security proverava:
  - oba dekoratora na svakoj ruti i redosled 302 / 302 / 403;
  - ponovnu proveru uloge pod bravom u svakom servisu;
  - pravila 1-3 iz 14.5 u servisu, ne u prikazu;
  - `sensitive_post_parameters`;
  - istu poruku za sve neuspehe prijave;
  - `next`;
  - belu listu snimka;
  - da `partija` ne izlazi;
  - okidac;
  - proveru dnevnika u `sacuvaj` i `podeli`.

**Ugovor** (menja ga samo glavna sesija):
- Rute: iz 14.7.
- Polja formi: `username`, `password`, `next`, `token`, `ime`, `lozinka1`, `lozinka2`, `glavni`, `moja_lozinka`, `radnja`; za `PasswordChangeForm` Django imena.
- Kontekst svih strana: `glavni` (bool) i `ja` (ime).
- `pregled`: `rezultati` (`id`, `mesto`, `ime`, `poeni`, `ocena` tekst, `datum`, `javno`), `deljeni` (`id`, `ime`, `poeni`, `ocena`, `nastao`, `istice`), `pronadjen`, `poruka`.
- `potvrda`: `vrsta`, `red`, `akcija`.
- `dnevnik`: `zapisi` (`kada`, `ko` ili `None`, `radnja`, `nad` ili `None`, `snimak` ili `None`).
- `nalozi`: `nalozi` (`id`, `ime`, `aktivan`, `glavni`, `poslednja_prijava`, `mora_promeniti`, `ja`), `forma`, `odbijeno` (kod ili `None`).
- `nalog`: `nalog`, `radnje` (spisak dozvoljenih), `forme`, `odbijeno`.
- `prijava`: `form`, `next`, `blokirano`.
- `lozinka`: `form`, `obavezna`.
- Datume formatira prikaz.

### 14.10 Rizici i tacke bez povratka

| Rizik | Mera |
|---|---|
| Prepravka tabele vrati brojac, pa se obrisana partija ponovo sacuva ili podeli (plan.md:466, views.py:100-113, 333-339) | provera `partija` u dnevniku pod bravom; test sa vracenim brojacem |
| Ne ostane nijedan aktivan glavni (uzajamna deaktivacija, oduzimanje sebi, komanda) | pravilo 1 u servisu, pod IMMEDIATE bravom, uz ponovnu proveru onoga ko radi; testovi; rezerva `moderator_lozinka` i `moderator_glavni` |
| Ruta `nalozi*` bez `glavni_potreban` | `test_matrica_ruta` nabraja rute; security |
| Stari `_perm_cache` na `request.user` posle oduzimanja uloge u istom zahtevu | servis cita svez objekat; sledeci zahtev ionako ucitava novog korisnika |
| Superuser napravljen iz ljuske zaobilazi uloge kroz `has_perm` | `uloga()` zahteva `not is_superuser`; `moderatori` upozorava |
| Lozinka na tehnickoj strani (settings.py:13, greske.py:6-8) | `sensitive_post_parameters`; test |
| `logout()`, postavljanje lozinke drugom ili prelazak na drugi nalog brisu partiju | `odjava` prenosi `igra`; ostalo prihvaceno |
| Komanda brise mimo dnevnika (rezultat_obrisi.py:27, deljeni_obrisi.py:31, nepodobno_dodaj.py:59) | servis `brisanje.py`; security grep `.delete()` |
| Kasnija migracija prepravi `igra_zapisdnevnika` i izgubi okidac | `test_okidac_postoji` |
| Blokada prijave po imenu (15 min); LocMem radi po procesu | lokalno prihvaceno; pri isporuci NE `DatabaseCache` (vidi pasus „Revizija T4“ ispod), nego brojac sa atomicnim `incr` (plan-isporuka.md 15.x) |
| Podrazumevani `SECRET_KEY` (settings.py:8-11) | lokalno prihvaceno; pri isporuci se cita iz okruzenja, uz `DEBUG = False` i `*_COOKIE_SECURE = True` |

**Ispravke posle T4 (2026-11-11):** pokusaj prijave i potvrde lozinkom se rezervise atomicno pre provere (`cache.add` pa `incr`, `igra.forme.rezervisi_pokusaj`), u posebnom kes aliasu `prijava` (LocMem, `MAX_ENTRIES` 100.000); `next` samo kao lokalna putanja kroz `HttpResponseRedirect`; hes lozinke se racuna van SQLite brave, a pod bravom se proverava da se lozinka nije promenila (`lozinka_promenjena`); nova lozinka ne sme biti jednaka staroj; migracija `0011_dnevnik_bez_zamene` (okidac protiv zamene zapisa); potvrda lozinkom kroz `hashers.check_password`, bez upisa novog hesa.

**Revizija T4 (2026-11-11), prihvaceno uz napomenu:**
- `sensitive_post_parameters` sam ne deluje dok je `DEBUG = True` (`SafeExceptionReporterFilter.is_active` vraca `not DEBUG`); zato `FilterBezPromenljivih.is_active` uvek vraca True (ispravka posle T4).
- Promena sopstvene lozinke odjavljuje druge sesije istog naloga i brise partiju u njima.
- Blokada po imenu: ko zna ime glavnog (vidi ga svaki moderator u dnevniku) moze sa 5 zahteva na 15 min da ga drzi van prijave i bez potvrde lozinkom. Tada kompromitovan nalog gasi razvijalac komandom `moderator_deaktiviraj`.
- Dok je `DEBUG = True`, tehnicka 404 strana nabraja moderatorske rute; nestaje sa `DEBUG = False`.
- Pri isporuci brojac prijave NE ide u `DatabaseCache` ni `FileBasedCache` (njihov `incr` je `get` pa `set` sa podrazumevanim rokom: vraca trku i jednim zahtevom skracuje ili produzava blokadu; dokaz `scratchpad\sec\r2\p5_dbkes_ponovi.py`). Potreban je kes sa atomicnim `incr` koji cuva rok (Memcached) ili brojac u bazi (`UPDATE ... SET broj = broj + 1` pod IMMEDIATE bravom); Redis tek posle provere (`RedisCache.incr` je `exists` pa `INCR`). Posle izbora ponoviti probu p5.
- Pretraga linka na pregledu nema `sensitive_post_parameters("token")`: token koji je moderator nalepio vidi se na DEBUG strani pri 500, samo njemu.
- Red dnevnika sa id = -1 (samo sirovim SQL-om) blokira svaki upis u dnevnik zbog okidaca 0011; brisanje tog reda vraca rad.
- Zavisnosti (pip-audit 2026-11-11): Django 6.0 ima ispravke do 6.0.8 (relevantan CVE-2026-33033, DoS kroz multipart na svakom POST-u, i na prijavi); sqlparse 0.5.4 → 0.6.0. Nadogradnju odobrava korisnik.

**Tacke bez povratka:**
- `migrate` na lokalnoj bazi: auth, `0009`, `0010`. `migrate igra 0008` brise dnevnik i naloge moderatora; korisnici ostaju.
- Svako brisanje rezultata ili linka je trajno.
- `dnevnik_ocisti` je trajan.
- Prvog stvarnog glavnog moderatora pravi korisnik, u terminalu: `moderator_dodaj IME --glavni`.

Odobrava korisnik potvrdom plana; `migrate` pokrece backend-senior. Isporuke nema.

### 14.11 Odluke

| # | Odluka korisnika 2026-11-11 |
|---|---|
| M1 | A: `django.contrib.auth`, dozvola `igra.moderira`, bez admina i grupa |
| M2 | B: nalozima se upravlja na strani; prvog pravi razvijalac komandom |
| M3 | B: tvrdo brisanje; snimak `{ime, poeni, ocena, datum}` u dnevniku |
| M4 | B: 365 dana, `dnevnik_ocisti` |
| N1 | B: nalozima upravlja samo glavni (`igra.upravlja_nalozima`); obican moderator brise, cita dnevnik i menja sopstvenu lozinku |
| zastite | potvrdjene: obavezna promena pocetne lozinke (`NalogModeratora.mora_promeniti`) i potvrda sopstvenom lozinkom za radnje nad tudjim nalozima |

**Odluke plana** (nisu pitanja; obrazlozene u 14.3-14.5):
- `partija` se cuva u dnevniku, a token se ne cuva.
- Prvi glavni nastaje izricito, preko `--glavni`.
- Glavni dodeljuje i oduzima ulogu na strani.
- Glavni moze da deaktivira drugog glavnog; uloga se pri deaktivaciji oduzima.
- Uvek ostaje bar jedan aktivan glavni, i za komande.
- Obican moderator na `nalozi*` dobija 403.
- Prijava i odjava se ne upisuju u dnevnik.

Otvorenih pitanja nema.

### 14.12 Dokumentacija posle izmene (predlog; planer je ne menja)

1. **`projekat-odluke`:**
   ```
   ## 2026-11-11 · Moderator
   - Sukob: zahtev klijenta (moderator se prijavljuje imenom i lozinkom, brise rezultat i deljeni link i vidi ko je sta obrisao i kada) protivreci `projekat-standardi` pravilu 3 („Tri modela, bez naloga ... bez admina“); MVP drzi naloge van opsega.
   - Odluka: nalozi samo za moderatore, kroz `django.contrib.auth` (dozvole `igra.moderira` i `igra.upravlja_nalozima`, dodeljene direktno; bez admina, grupa i `createsuperuser`). Dve uloge: moderator brise rezultate i linkove, cita dnevnik i menja sopstvenu lozinku; glavni moderator jos dodaje, deaktivira i aktivira moderatore, postavlja im lozinke i dodeljuje i oduzima ulogu glavnog, uz potvrdu sopstvenom lozinkom. Uvek ostaje bar jedan aktivan glavni; niko ne deaktivira sebe. Pocetnu lozinku vlasnik menja pri prvoj prijavi. Prvog glavnog pravi razvijalac komandom `moderator_dodaj IME --glavni`; komande ostaju kao rezerva. Brisanje je tvrdo, i kroz komande; svako brisanje i svaka radnja nad nalogom ide u nepromenljiv dnevnik (`ZapisDnevnika`) sa snimkom {ime, poeni, ocena, datum}, bez tokena; dnevnik cuva i hes partije, da se obrisana partija ne sacuva ni ne podeli ponovo; cuva se 365 dana. Igraci nemaju naloge.
   - Odlucio: korisnik, 2026-11-11 (M1 A, M2 B, M3 B, M4 B, N1 B; obe zastite potvrdjene).
   ```
2. **`projekat-standardi`, pravilo 3:** „**Pet modela; nalozi samo za moderatore.** Aplikacija `igra` ima modele `Rezultat`, `NepodobnoIme`, `DeljeniRezultat`, `ZapisDnevnika` (nepromenljiv, 365 dana) i `NalogModeratora` i njihove migracije; stanje partije je samo u sesiji. Moderator je `django.contrib.auth` korisnik sa dozvolom `igra.moderira`, glavni ima i `igra.upravlja_nalozima`; igraci nemaju naloge. Brisanje ide samo kroz `igra/brisanje.py`, radnje nad nalozima samo kroz `igra/nalozi.py`; oba ponovo proveravaju ulogu pod bravom i upisuju dnevnik u istoj transakciji. Bez admina. Bez Docker-a, Nginx-a i MySQL-a. *Poreklo: odluke 2026-11-10 i 2026-11-11 u `projekat-odluke`.*“
3. **`projekat-standardi`, tabela:**
   - Red o prikazima: „moderatorski prikazi su u `igra/moderacija.py`, pod `moderator_potreban`, a `nalozi*` pod `glavni_potreban` (403); obicne forme sa POST i preusmerenjem, bez skripte; `sacuvaj` i `podeli` proveravaju dnevnik“.
   - Red o sablonima: „`_glava.html` i `_polje.html` su zajednicki; moderatorske strane u `templates/igra/moderator/` nasledjuju `osnova.html`“.
   - Red o komandama, dodaje se: `moderator_dodaj`, `moderator_lozinka`, `moderator_glavni`, `moderator_deaktiviraj`, `moderatori`, `dnevnik_ocisti`. Uz to: brisanja kroz komande pisu dnevnik.
4. **`projekat-domen`:**
   - Pravilo 1, dodatak: „Dnevnik vide samo moderatori; ne nosi token linka, a hes partije cuva samo za proveru i nikad ga ne prikazuje. Obrisan link daje isti odgovor kao istekao.“
   - Tok igre, tacka 9: „Moderator, prijavljen imenom i lozinkom, brise rezultat sa rang liste ili deljeni link uz potvrdu; brisanje je trajno i upisano u dnevnik (ko, sta, kada, snimak). Partija obrisanog rezultata se ne cuva ponovo; partija obrisanog linka ne dobija nov. Glavni moderator upravlja nalozima i ulogom glavnog; uvek ostaje bar jedan aktivan glavni.“
   - Recnik: „moderator | nalog koji brise rezultate i linkove“; „glavni moderator | moderator koji upravlja nalozima“; „dnevnik | ko je sta obrisao ili promenio i kada, 365 dana“.
5. **`projekat-domen/references/parametri.md`**, odeljak „Moderator“: „Sesija 8 h neaktivnosti; 5 neuspeha za isto ime, pa 15 minuta blokade; lozinka najmanje 12 znakova; dnevnik 365 dana (duze od 14 dana sesije igre). Poreklo: odluke 2026-11-11; nisu parametri igre, zive u `settings.py`.“
6. **`MVP.md`** (menja korisnik):
   - Odeljak 2: u MVP-u „moderator i glavni moderator: prijava, brisanje rezultata i linka, dnevnik, upravljanje nalozima (dodato 2026-11-11)“; van MVP-a „nalozi igraca“.
   - Odeljak 3: pododeljak „Moderator“.
   - Uslov 12: „Samo prijavljen moderator brise rezultat ili link, uz potvrdu; nalozima upravlja samo glavni moderator i uvek ostaje bar jedan aktivan glavni; svako brisanje i svaka radnja nad nalogom je u dnevniku; obrisana partija se ne cuva ni ne deli ponovo; prijava i odjava ne prekidaju partiju.“
7. **`CLAUDE.md`, raspored:** `backend-senior` „motor, parametri, modeli, migracije, komande, prikazi i izdvajanje tekstova“; red „prevod | `translate` | engleski u `.po`“.
