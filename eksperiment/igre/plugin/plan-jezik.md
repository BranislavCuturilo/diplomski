# 12. Srpski i engleski (2026-11-11)

Status: **odluke J1-J3 donete 2026-11-11 (12.12), izrada pocinje.** J2 odstupa od preporuke: engleski datum je ISO `2026-11-10` (`Y-m-d`).
Izvori: MVP 2, 6 i uslov 11; `projekat-odluke` 2026-11-11 „Engleska verzija“; `craft-i18n`; postojeci kod (279 testova prolazi, prema nalogu; ovde nije pokrenuto).

**Odgovoreno (ne pita se ponovo):** Django i18n sa `.po`, `makemessages`, `compilemessages` (GNU gettext 1.0); `sr` (cirilica) i `en`; izbor u kolacicu jezika, novi posetilac dobija jezik pregledaca (engleski ako ga trazi, inace srpski); baza cuva kljuceve, rang lista i deljena strana na jeziku posmatraca, postojeci zapisi jednom migracijom sa povratkom; ime igraca se ne prevodi; engleski pise agent `translate`, ocene, lekcije i napomenu klijent pregleda pre isporuke.

### 12.1 Sta u odeljcima 1-11 vise ne vazi

| Odeljak | Bilo | Sada |
|---|---|---|
| 2, 6 „Tekst na ekranu“ | tekst samo cirilicom | srpski izvor (msgid) cirilicom, engleski u `.po`; tabele teksta u 6, 10.6, 11.6 vaze kao srpski izvor |
| 4 | `OCENE`, `STATUS_*`, `LEKCIJE` nose tekst | nose kljuceve; tekst je oznacen za prevod (12.3) |
| 6 JavniPrikaz, 10.5, 11.4 | `zadatak`, `status`, `ocena`, `lekcije[].tekst`, `napomena` su tekst | kljucevi; `napomena` izlazi iz JSON-a (12.3) |
| 10.5 R1 | datum uvek 10.11.2026 | tako za `sr`; za `en` J2 |
| 11.1, 11.4 | `settings.py` se ne menja; deljena strana bez `Vary: Cookie` | `settings.py` dobija i18n (12.2); deljena strana dobija `Vary: Cookie`, jer jezik zavisi od kolacica |
| 10.7 | `test_latinica_samo_u_nazivima` se ne menja | vezan za `sr`, plus „English“ (12.9) |

### 12.2 Podesavanja i URL

| Podesavanje | Vrednost | Zasto |
|---|---|---|
| `LANGUAGE_CODE` | `'sr'` (ostaje) | rezervni jezik |
| `LANGUAGES` | `[('sr', 'Српски'), ('en', 'English')]`, bez `gettext_lazy` | nazivi na svom jeziku, ne prevode se |
| `LOCALE_PATHS` | `[BASE_DIR / 'locale']` | katalozi projekta |
| `MIDDLEWARE` | `LocaleMiddleware` posle `SessionMiddleware`, pre `CommonMiddleware` | redosled iz Django dokumentacije |
| `LANGUAGE_COOKIE_NAME` | podrazumevano `django_language` | test ga cita iz `settings` |
| `LANGUAGE_COOKIE_AGE` | `365 * 24 * 60 * 60` | podrazumevano `None` je kolacic do zatvaranja pregledaca: izbor se ne bi pamtio |
| `LANGUAGE_COOKIE_SAMESITE`, `_HTTPONLY`, `_SECURE` | `'Lax'`, `True`, `False` (lokalni http; pri isporuci `True`) | skripta kolacic ne cita |
| `USE_L10N` | ne dodaje se (uklonjen u Django 5.0, lokalizacija je uvek ukljucena) | backend proverava `python -m django --version` |
| `USE_THOUSAND_SEPARATOR`, `TIME_ZONE` | bez izmene | brojevi bez grupisanja kao danas; datum je dan u Beogradu na oba jezika |

**Izbor jezika:** Django `set_language`, bez sopstvenog prikaza: `path('jezik/', require_POST(set_language), name='jezik')`. `require_POST`, jer `set_language` na GET samo preusmerava, bez efekta. Polja `language` i `next`; `next` proverava sam Django (`url_has_allowed_host_and_scheme`). Od Django 4.0 ne dira sesiju.
**Prefiks jezika u URL-u: ne** (`i18n_patterns` se ne koristi). Zasto: link za deljenje mora biti jedan URL koji svako vidi na svom jeziku (MVP 6), a prefiks bi ugradio jezik posiljaoca; `fetch` adrese, ugovor i 279 testova ostaju; strana je lokalna i `noindex`, pa SEO ne trazi prefiks; nema LocaleMiddleware preusmerenja koje bi menjalo „isti 404“ (11.4).
**Vary i kes:** `LocaleMiddleware` sam dodaje `Vary: Accept-Language` i `Content-Language`. `pocetna` ima `Vary: Cookie` od sesije. `deljeno` dodaje `Vary: Cookie` izricito (`patch_vary_headers`); `never_cache` (`no-store, private`) ostaje na obe strane.
**Brojevi:** `json_script` (DjangoJSONEncoder) ne lokalizuje, pa brojevi u JSON-u ostaju brojevi na oba jezika. Broj u tekstu sablona ide samo kroz `{% blocktranslate count %}`; kao podatak, kao do sada, nikad kroz `{{ }}`.
**Formati po jeziku** zive u kodu (`tekstovi.FORMATI`), ne u `.po` (`craft-i18n`: kodovi formata se ne prevode): `sr` datum `d.m.Y`, zarez `,`, novac `%(iznos)s` + NBSP + `$`, minuti `%(iznos)s` + NBSP + `мин`; `en` datum `Y-m-d` (2026-11-10, odluka J2), tacka `.`, novac `$%(iznos)s`, minuti `%(iznos)s` + NBSP + `min`. Datum formatira `django.utils.dateformat` (nazivi meseci iz Django kataloga, ne iz C lokala Windows-a).

### 12.3 Gde zivi tekst; motor vraca kljuceve

| Tekst | msgid (srpski izvor) | Prevodi |
|---|---|---|
| zadaci, opisi i srpski nazivi opcija, ocene, statusi, lekcije, napomena | `parametri.py`, oznaceno lokalnom `gettext_noop(tekst) -> tekst` (ime je kljucna rec koju `makemessages` vec trazi; bez uvoza Django-a) | `igra/tekstovi.py` kroz `gettext` |
| poruke skripte, obrasci recenica, pitanje nove igre, tekst deljenja | `igra/tekstovi.py` (`gettext_noop`, `ngettext`) | `tekstovi.za_skriptu()` |
| naslovi, oznake, dugmad, `aria-label`, `<title>`, pomoc | sabloni, `{% translate %}` / `{% blocktranslate %}` | Django sablon |
| Haiku, Sonnet, Opus, low, high, max, CSS, CRUD, Српски/English | nisu oznaceni | ne prevode se (MVP 6) |
| ime igraca; komande; `ValidationError` modela; log | nikad kroz gettext | ne prevode se |

**Srpski kao msgid (preporuka).** Odobren srpski tekst ostaje izvor i ne seli se u katalog; engleska izmena posle pregleda klijenta menja samo `msgstr`, ne `msgid`; nedostajuci prevod pada na srpski, sto test „engleska strana bez cirilice“ odmah vidi. Cena: gettext pada na `msgid`/`msgid_plural`, sto je tacno za engleski, a ne za srpske tri mnozine, pa `sr` katalog postoji samo za mnozinu (12.8).

**`parametri.py`:** `ZADACI` dobija `kljuc` (`prevod`, `sablon`, `css`, `crud`, `model`, `prava`, `testovi`, `revizija`); `OCENE = [(85, "odlican"), (65, "solidan"), (40, "skup"), (0, "pozar")]` i `NAZIVI_OCENA {kljuc: tekst}`; `STATUS_GOTOVO = "gotovo"`, `STATUS_DORADA = "dorada"` i `NAZIVI_STATUSA`; `LEKCIJE` zadrzava kljuceve (`tiha`, `opus_lako`, `max`, `sve`, `pedeset`). Kratke reci dobijaju `# Translators:` komentar (npr. „сам: jedan agent“, „таман: koliko treba“).

**Motor** (bez novih uvoza; `test_motor_cist` i `test_nema_brojeva_u_motoru` bez izmene):

```
oceni(poeni) -> str                        # kljuc ocene
lekcije(stanje) -> list[dict]              # [{"oznaka": "tiha", "odeljak": "4.2"}]
_javni_poslednji: "status": p.STATUS_DORADA if ishod == DORADA else p.STATUS_GOTOVO   # pravilo 1: jedan izraz
nadogradi(stanje | None) -> dict | None    # stara zavrsena sesija sa tekstom -> kljucevi (12.4); ulaz netaknut
javne_opcije()                             # bez izmene: kljuc, naziv, opis (izvorni tekst); prevodi prikaz
```

**Pravilo 1:** uspeh i tih neuspeh daju isti kljuc `gotovo`, a skripta ga prevodi iz iste mape `tekstovi.status`, pa su JSON i tekst isti bajt po bajt na oba jezika. JSON odgovora vise ne zavisi od jezika; zavisi samo datum (`rang.lista[].datum`, `podeli.istice`, `deljeno.datum`).

**JSON (izmene ugovora).** Ime polja `kljuc` se ne koristi: test ga trazi kao kljuc sifarnika (`ZABRANJENI_KLJUCEVI`).

```
JavniPrikaz:  "zadatak": "crud" | null                    # bilo {"naziv": ...}
              "poslednji": {..., "zadatak": "css", "status": "gotovo" | "dorada"}
              "zavrsni": {..., "ocena": "skup",
                          "tihe_greske": [{"krug": 5, "zadatak": "model", "dodatak_cena": .., "dodatak_minuti": ..}],
                          "lekcije": [{"oznaka": "tiha", "odeljak": "4.2"}]}     # bez "napomena"
Rang red:     {"ime", "poeni", "ocena": "odlican", "datum"}
Deljeni:      {"zavrsni": isti oblik, "ime", "datum"}
```

**`igra/tekstovi.py`** (nova, Django strana; jedino mesto koje zove `gettext` van sablona):

```
FORMATI = {"sr": {...}, "en": {...}}       # 12.2
datum(trenutak) -> str                     # localtime + dateformat u aktivnom jeziku; zamenjuje tri strftime u views
opcije(javne) -> dict                      # isti oblik kao javne_opcije, naziv i opis kroz gettext
za_skriptu() -> dict                       # u aktivnom jeziku:
  {"zadaci": {kljuc: tekst}, "status": {...}, "ocene": {...}, "lekcije": {...}, "napomena": str,
   "poruke": {osvezeno, nemaIgre, neispravno, server, stanje, rangSacuvano, rangVanListe, neispravnoIme,
              nepodobnoIme, vecSacuvano, nijeZavrsena, deljenjeIsteklo, kopirano, kopiranjeRezerva,
              nijeProcitano, izaberite},
   "pitanjeNova": str, "deljenje": {"naslov", "tekst"},
   "obrasci": {"krug": "Круг %(krug)s од %(ukupno)s", "zavrsena", "rezultatKruga": "Круг %(krug)s: %(zadatak)s",
               "procena": "Процена: цена %(cena)s, %(minuti)s.", "tiha": "Круг %(krug)s: %(zadatak)s (додатак: %(cena)s, %(minuti)s)",
               "odeljak": "(одељак %(odeljak)s)", "rok": "Линк важи до %(datum)s."},
   "format": {"zarez", "novac", "minuti"}}
```

`rangVanListe` i `neispravnoIme` server sklapa kroz `ngettext(..., n) % {"n": p.RANG_MESTA | p.IME_MAKS}`, pa skripti mnozina ne treba. Mapa ne zavisi od stanja (sve zadatke, ocene i lekcije nosi uvek), pa ne otkriva nista o partiji.

**`views.py`:** `_stanje(request)` = `motor.nadogradi(session.get("igra"))` u `pocetna`, `potez`, `sacuvaj`, `podeli`; kontekst plus `tekstovi` i `brojevi` (`rang_mesta`, `ime_maks`); `opcije` kroz `tekstovi.opcije`; datum kroz `tekstovi.datum`. `deljeno`: `?jezik=` (12.5, J1) iz `LANGUAGES`, inace se zanemaruje i ne ispisuje; kontekst i render unutar `translation.override`, `Content-Language` izricito; `Vary: Cookie`.

### 12.4 Model, migracija, stare sesije

- `0004_tekst_u_kljuceve.py` (rucna, `RunPython` sa povratkom). Preslikavanja su literali u datoteci (kao `0002`), da kasnija izmena `parametri` ne promeni istoriju. Napred: `Rezultat.ocena` tekst u kljuc; `DeljeniRezultat.zavrsni`: `ocena` i `tihe_greske[].zadatak` u kljuc, `lekcije[].tekst` u `oznaka`, `napomena` se brise (citanje je ionako uzima iz `parametri`). Nazad: tacno obrnuto, `napomena` se vraca kao literal. Vrednost koja je vec kljuc (napred) ili vec tekst (nazad) se preskace.
- **Neprepoznat tekst:** migracija baca izuzetak sa spiskom `model:id:vrednost` i ne menja nista (SQLite migracija je jedna transakcija). Bez nagadjanja iz poena: snimak cuva ono sto je igrac video. Razvijalac odlucuje: `rezultat_obrisi`/`deljeni_obrisi` ili rucna ispravka, pa ponovo `migrate`.
- `0005` (`makemigrations`): `CheckConstraint igra_ocena_kljuc` (`ocena__in` kljucevi). **Alternativa, sigurnija:** tekst ne moze kasnije da udje kroz gresku ili komandu, a `0005` pada ako je `0004` nesto preskocila. Komentar o „19 znakova“ u modelu se ispravlja.
- **Stare sesije** (nalaz, odluka ih ne pominje): zavrsena partija u sesiji nosi srpski tekst ocene, zadatka i lekcija. `motor.nadogradi` ga ne preslikava nego racuna iz postojanih podataka: `oceni(poeni)`, zadatak iz `krug`, `lekcije(stanje)` iz istorije; ista pravila daju isti rezultat. Nezavrsena partija teksta nema. Upis samo tamo gde prikaz vec pise sesiju.

### 12.5 Sabloni i izbor jezika

- `{% load i18n %}`, `{% get_current_language as JEZIK %}`, `<html lang="{{ JEZIK }}">` u `igra.html` i `deljeno.html`; sav tekst, `aria-label`, `<title>` i „ваш резултат“ kroz `{% translate %}`. Brojevi iz `parametri`: `{% blocktranslate count n=brojevi.rang_mesta trimmed %}` za podnaslov liste, isto za „Од 1 до 20 знакова.“ (`ime_maks`) i „важи 30 дана“ (`dana`). `maxlength="20"` se ne dira.
- **Igra:** forma `#jezik-forma` (POST na `{% url 'jezik' %}`, `{% csrf_token %}`, skriveno `next` = `{% url 'pocetna' %}`), u `.vrh`, desno od naslova, sa `flex-wrap` na uskom ekranu. Jedno dugme `#jezik-dugme`, `name="language"`, za drugi jezik: na srpskoj „English“ (`lang="en"`), na engleskoj „Српски“ (`lang="sr"`); forma ima `aria-label` „Језик“ / „Language“. Nazivi su doslovni u sablonu: `get_available_languages` ih prevodi kroz Django katalog („енглески“). Radi bez skripte; promena usred partije ne dira stanje, gube se samo neposlati izbori i upisano ime (prihvatljivo). Bez potvrde.
- **Deljena strana** (preporuka J1): nema CSRF kolacica, a `{% csrf_token %}` bi ga napravio, pa POST forma ne dolazi u obzir. Link `#jezik-link` `href="?jezik=en"` (ili `sr`) menja jezik samo te strane, bez kolacica i bez upisa; i na 404. Inace vazi kolacic, pa jezik pregledaca.
- `#tekstovi` (`{{ tekstovi|json_script:"tekstovi" }}`) na obe strane, pre `igra.js`; `#tekstovi-greska` je skriven prevedeni tekst „Стање игре није могло да се прочита...“ za slucaj da se mapa ne procita.
- 320 i 375 px: engleski tekst je duzi (ocena, dugmad, zaglavlje sa dugmetom jezika); provera `JS_PRELIVANJE` na oba jezika (12.9).

### 12.6 Skripta

**Preporuka: tekst kroz `json_script`, bez `JavaScriptCatalog`.** Zasto: jedan katalog (`django`), bez domena `djangojs`; bez dodatnog zahteva i bez rizika da pregledac zadrzi katalog starog jezika (isti URL za oba); deljena strana dobija tekst u istom odgovoru, bez kolacica; mnozinu skripta ne treba jer su svi brojevi u porukama konstante koje server ubaci.

- `T` = parsiran `#tekstovi` na pocetku `pokreni`; neuspeh: prikazati `#tekstovi-greska`, dalje nista. U `igra.js` ne ostaje nijedno cirilicno slovo.
- `zameni(obrazac, vrednosti)`: menja `%(ime)s`; nepoznato mesto ostaje vidljivo (test ga hvata).
- `IZGLED_OCENE` po kljucu ocene; dorada je `status === "dorada"`; zadatak, ocena, status, lekcija i napomena iz `T`; nepoznat kljuc daje sam kljuc (vidljivo, hvata test latinice/cirilice). `jeZavrsni` i `jeRed` proveravaju kljuceve iz `T` i vise ne traze `napomena`.
- `broj(v, d)`: `toFixed`, pa `T.format.zarez`; `dolari`: predznak ispred obrasca (`-$1.20`, `-1,20 $`). Bez `Intl` i `toLocaleString`: jezik pregledaca nije jezik strane, a `Intl` za `sr` grupise hiljade, pa bi se srpski prikaz promenio.

### 12.7 Komande

Ostaju srpski latinicom i ne prevode se: alat razvijaoca, ispis se pretrazuje (`craft-i18n`: log na jednom jeziku), testovi koriste `StringIO`. Jedina izmena je da `rezultati` i `deljeni` ispisuju kljuc ocene (`ocena='odlican'`), isto kao u bazi.

### 12.8 Prevod

```
$env:Path += ";C:\Users\Bane\AppData\Local\Programs\gettext-iconv\bin"     # samo stara ljuska
python manage.py makemessages -l en -l sr --ignore "igra/tests/*" --add-location file
  (translate) en: svi msgstr; sr: samo stavke sa msgid_plural (tri oblika); zaglavlja Plural-Forms
python manage.py compilemessages
msgfmt --check --statistics -o NUL locale/en/LC_MESSAGES/django.po     # i za sr
msgattrib --untranslated --no-obsolete locale/en/LC_MESSAGES/django.po   # prazno
msgattrib --only-fuzzy locale/en/LC_MESSAGES/django.po                   # prazno, i za sr
msgattrib --untranslated locale/sr/LC_MESSAGES/django.po | findstr msgid_plural   # prazno
```

- Zaglavlja: `en` `nplurals=2; plural=(n != 1);`; `sr` isti izraz kao Django `sr` katalog (`nplurals=3; plural=(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2);`).
- **`.po` i `.mo` su u projektu** (`locale/{en,sr}/LC_MESSAGES/`): server i testovi rade bez gettext-a u PATH-u i bez koraka gradnje. Zastareo `.mo` hvataju testovi ponasanja (12.9).
- **Pravila za `translate`:** menja samo `msgstr`; `%(ime)s` doslovno; bez HTML-a u `msgstr` (`blocktranslate` ga ne escape-uje); bez reci chance, odds, difficulty, seed i bez nagovestaja tezine ili tihog zadatka u opisima (pravilo 1, P1); nazivi iz 12.3 neprevedeni; NBSP nije u katalogu (u `FORMATI`); `fuzzy` se ne ostavlja; ocene, lekcije, napomena i naziv igre doslovno iz tabele ispod do odluke klijenta.
- **Recnik** (jedan engleski izraz po pojmu): krug round; kontrolni skup final check; tiha greska silent error; vraceno na doradu sent back for rework; budzet budget; rok deadline; nivo razmisljanja thinking level; kontekst context; podela posla work split; rang lista leaderboard; deljeni rezultat shared result.

**Za pregled klijenta** (predlog; menja se samo `msgstr`):

| Vrsta | Srpski | Engleski (predlog) |
|---|---|---|
| ocena | одличан оркестратор | excellent orchestrator |
| ocena | солидан | solid |
| ocena | скуп учитељ | costly lesson (doslovno: expensive teacher) |
| ocena | пожар | disaster (ili: on fire) |
| lekcija 4.2 | Ако је грешка тиха, задатак остаје највишем разреду. | If an error is silent, the task stays with the top tier. |
| lekcija 3.2 | Најскупљи модел није увек најбољи избор. | The most expensive model is not always the best choice. |
| lekcija 3.3 | Изнад нивоа high цена расте, а квалитет не. | Above the high level, cost goes up but quality does not. |
| lekcija 3.1 | Превише контекста квари резултат исто као премало. | Too much context spoils the result just as much as too little. |
| lekcija 5.3 | Више агената не значи јефтиније. | More agents does not mean cheaper. |
| napomena | Цене и нивои размишљања су стварни подаци; вероватноће, казне и поени су измишљени параметри игре. | Prices and thinking levels are real data; probabilities, penalties and points are made-up game parameters. |
| status (uz pregled) | готово / враћено на дораду | done / sent back for rework |
| naziv igre (J3) | Оркестратор | Orchestrator |

### 12.9 Testovi (samo postojece datoteke)

**Vezivanje za `sr`.** Django klijent bez `Accept-Language` dobija `sr`; novi `test_podrazumevano_sr` to dokazuje (`Content-Language`, `<html lang="sr">`) pre nego sto se ostali oslone na srpski tekst. **Playwright Chromium salje `en-US`**: `novi_kontekst` dobija `locale="sr-RS"` kao podrazumevano, inace bi ceo `test_tok` presao na engleski; engleski testovi zadaju `locale="en-US"`.

| Pravilo | Testovi |
|---|---|
| uslov 11: oba jezika, jezik pregledaca | `test_prikazi.JezikTests`: `test_podrazumevano_sr`; `test_accept_language` (subTest: `en-US`, `en-GB` -> en; `de` -> sr; `sr-Latn` -> sr; `de, en;q=0.5` -> en; `sr, en` -> sr); `test_kolacic_jaci_od_zaglavlja`; `test_nepodrzan_kolacic` (`de` -> zaglavlje ili sr) |
| pamcenje | `test_jezik_post_kolacic` (302 na `/`, ime iz `settings`, `max-age` 31536000, `SameSite=Lax`, `HttpOnly`, vrednost `en`); `test_jezik_get_405`; `test_jezik_bez_csrf_403`; `test_jezik_next_spolja` (Location nije tudji domen); `test_jezik_ne_dira_sesiju` (`session_data` isti); `test_tok.JezikTokTests.test_izbor_se_pamti` (klik, osvezavanje, nova kartica; atributi kolacica) |
| nijedan neprevedeni tekst | `test_prikazi.PrevodTests`: `test_engleska_bez_cirilice` (sirov HTML pod `en`: igra u toku, zavrsni ekran sa pet lekcija i tri tihe greske, rang sa latinicnim imenima, deljena 200 i 404; jedini izuzetak „Српски“ u `[lang=sr]`); `test_tekstovi_en_bez_cirilice`; `test_tekstovi_sr_latinica` (posle uklanjanja `%(...)s` samo `DOZVOLJENA_LATINICA`); `test_parametri_prevedeni` (svaki oznacen tekst: pod `en` drugaciji i bez cirilice, pod `sr` jednak sebi); `test_mesta_za_vrednosti_ista` (skup `%(ime)s` isti na oba jezika); `test_mnozina_sr` (n = 1, 2, 5, 21) i `test_mnozina_en` (1, 2); `test_formati_svi_jezici`; `test_tok`: `test_engleska_igra_bez_cirilice` (vidljivi tekst bez `bdi` i `[lang]` drugog jezika, svaki ekran kao u `test_latinica_samo_u_nazivima`), `confirm` i `navigator.share` na engleskom |
| promena jezika ne menja tok | `test_prikazi.test_promena_jezika_usred_partije` (isto seme: krugovi 1-4 sr, POST jezik, 5-8 en; tela poteza i zavrsno stanje jednaki partiji samo na sr); `test_json_ne_zavisi_od_jezika`; `test_tok.test_promena_jezika_usred_partije` (krug, budzet, rok isti) |
| pravilo 1 na oba jezika | `test_tih_neuspeh_bajt_identican_uspehu` i `test_status_tihog_neuspeha_je_gotovo` sa `subTest(jezik)`; `test_tekstovi_ne_zavise_od_stanja` (dva stanja, isti bajtovi); `test_nijedan_odgovor_ne_sadrzi_skriveno` i pod `en`, uz `ZABRANJENE_RECI_EN` (reci chance, chances, odds, difficulty, seed sa granicom reci, bez obzira na velika slova) |
| rang i deljena na jeziku posmatraca | `test_rang_na_jeziku_posmatraca` (isti red: kljuc u JSON-u, `T.ocene` i datum po jeziku; 2026-11-09 23:30 UTC daje `10.11.2026`, a na engleskom oblik iz J2); `test_deljena_na_jeziku_posmatraca` (isti token, kolacic sr i en: `lang`, `<title>`, JSON isti osim `datum`); `test_deljena_parametar_jezika` (`?jezik=en` bez `Set-Cookie`; `?jezik=xx` isto kao bez njega, vrednost se ne ispisuje); `test_zaglavlja` prosiren: `Vary` sadrzi `Accept-Language` i `Cookie`, `no-store`, `private` |
| deljena ne dira sesiju | `test_strana_ne_pravi_sesiju`: provera „Cookie nije u Vary“ se **zamenjuje** dokazom koji ne zavisi od zaglavlja: klijent sa postojecom sesijom, `CaptureQueriesContext` bez `CITANJE_SESIJE`, bez `Set-Cookie` |
| migracija | `test_prikazi.MigracijaTekstaTests` (`TransactionTestCase`, `MigrationExecutor`; na kraju vraca na poslednju): napred (ocena, zadatak, lekcije, napomena), nazad do istog JSON-a, neprepoznat tekst baca i ne menja nista, vec kljuc se preskace, posle `0005` tekst u `ocena` daje `IntegrityError` |
| motor | `test_motor`: `test_redosled_zadataka` (kljuc, naziv, tezina, tih), `test_ocene_na_granicama` (kljucevi), `LekcijeTests` (oznaka, odeljak), `test_statusi_kljucevi`, `test_napomena_doslovno` (izvor ostaje srpski), `test_parametri_cist` (`ast`: bez uvoza Django-a), `NadogradnjaTests` (staro zavrseno stanje daje isto sto i novo; idempotentno; ulaz netaknut; nezavrseno nepromenjeno) |
| postojeci tekst i kljucevi | `test_status_dorade` (`dorada`), `test_tacan_skup_kljuceva_javnog_prikaza` (`zadatak` string, lekcija `{oznaka, odeljak}`, `KLJUCEVI_ZAVRSNOG` bez `napomena`), `KLJUCEVI_LEKCIJE`, komande (`ocena='...'` kljuc), `test_tok.OCENE` i `seme_za_ocenu` po kljucu; `test_latinica_samo_u_nazivima`: prvo `<html lang="sr">`, `DOZVOLJENA_LATINICA` plus „English“ |
| ekran | `test_375_rang_bez_prelivanja`, `test_deljena_bez_prelivanja`, `JS_OCENA_U_KARTICI` sa `subTest(jezik)` na 320 i 375 px (najduza engleska ocena; zaglavlje sa dugmetom jezika); `test_konzola_cista` i na engleskom |
| bez izmene | `BalansTests`, `DeterminizamTests`, `test_motor_cist`, `test_nema_brojeva_u_motoru`, `DeterminizamHttpTests` |

### 12.10 Raspored, talasi, dokazi, ugovor

| Talas | Datoteke | Agent |
|---|---|---|
| T1 | `igra/parametri.py`, `igra/motor.py`, `igra/tekstovi.py` (nova), `igra/models.py`, `igra/migrations/0004_tekst_u_kljuceve.py` (rucna), `0005_...` (`makemigrations`), `igra/views.py`, `orkestrator/urls.py`, `orkestrator/settings.py`; komande `rezultati.py`, `deljeni.py` samo ako ispis trazi izmenu | backend-senior |
| T1 | `templates/igra/{igra,deljeno,_zavrsni}.html`, `static/igra/igra.js`, `static/igra/igra.css` | frontend-medior |
| T2 | `locale/{en,sr}/LC_MESSAGES/django.po` (`makemessages`, posle oba iz T1: cita i Python i sablone) | backend-senior |
| T3 | isti `.po` (prevod), `.mo` (`compilemessages`) | translate |
| T4 | `igra/tests/test_motor.py`, `test_prikazi.py`, `test_tok.py`; (samo citanje) | qa; security, u jednoj poruci |

Redosled unutar backend-senior: `parametri`, `motor`, `tekstovi`, `models`, `0004`, `0005`, `views`, `urls`, `settings`. Prevod ide tek posle izdvajanja; testovi posle `.mo`, jer engleski testovi traze preveden katalog.

| Faza | Dokaz |
|---|---|
| T1 backend | `manage.py check` bez upozorenja; `makemigrations --check --dry-run` „No changes detected“; kopija `db.sqlite3` pre `migrate`; `migrate`, `migrate igra 0003`, `migrate` (broj redova po oceni ispisan pre i posle); skripta u scratchpad-u kroz Django klijent: GET `/` sa `Accept-Language` en i sr (`Content-Language`, `lang`), POST `/jezik/` (zaglavlje `Set-Cookie`), deljena sa `?jezik=en` (`Vary`); `BalansTests` i `DeterminizamTests` prolaze; ceo paket pokrenut, a spisak palih testova u izvestaju (ocekivano samo oni iz 12.9 „postojeci tekst i kljucevi“; ispravlja qa) |
| T1 frontend | pre izmene snimak HTML-a GET `/` (sr, seme 42, zavrsena); posle: nijedno cirilicno slovo u `igra.js`; u sablonima cirilica samo unutar `translate`/`blocktranslate` i u „Српски“ (skripta u scratchpad-u); rad u pregledacu je nepokrenut do T4 i izvestaj to navodi |
| T2 | `makemessages` ispis; broj stavki i spisak stavki sa `msgid_plural` |
| T3 | komande provere iz 12.8 sa praznim izlazom; `msgfmt --statistics` bez neprevedenih i `fuzzy` za `en`; `compilemessages` bez greske. Ako agent nema ljusku, komande pokrece glavna sesija pre T4 |
| T4 | qa: `test_summary.py` `EXIT=0`; snimci 320/375/1440 na oba jezika (igra, zavrsni sa blokom deljenja, rang sa 10 redova, deljena 200 i 404). security: kolacic jezika (atributi, vrednost samo `sr`/`en`), `next` i `?jezik` (bela lista, bez odraza), `msgstr` bez HTML-a, `T` samo kroz `textContent`, deljena strana bez sesije i CSRF kolacica, pravilo 1 na oba jezika |
| poruka klijentu | glavna sesija: tabela 12.8 na pregled; isporuka tek posle odobrenja |

| Ugovor | Ime |
|---|---|
| URL | `"jezik/"`, ime `jezik`; POST `language`, `next` |
| Kljucevi | zadaci `prevod`, `sablon`, `css`, `crud`, `model`, `prava`, `testovi`, `revizija`; ocene `odlican`, `solidan`, `skup`, `pozar`; status `gotovo`, `dorada`; lekcije `tiha`, `opus_lako`, `max`, `sve`, `pedeset` |
| JSON | 12.3; polje lekcije `oznaka`; bez `napomena` |
| Kontekst | plus `tekstovi` (obe strane), `brojevi` (`rang_mesta`, `ime_maks`); `JEZIK` iz `get_current_language` |
| `tekstovi` | kljucevi iz 12.3, `json_script` id `tekstovi` |
| DOM | `#tekstovi`, `#tekstovi-greska`, `#jezik-forma`, `#jezik-dugme` (igra); `#jezik-link` (deljena i 404) |
| Upit | `?jezik=sr` ili `?jezik=en`, samo na `deljeno` |
| Motor | `nadogradi`; `oceni`, `lekcije` vracaju kljuceve |
| Funkcije prikaza | `tekstovi.datum`, `tekstovi.opcije`, `tekstovi.za_skriptu`, `tekstovi.FORMATI` |

Promena iz ove tabele ide kroz glavnu sesiju. **Preporuka: delegiranje u novoj sesiji**; kontekst planiranja implementaciji ne treba.

### 12.11 Rizici i tacke bez povratka

| Rizik | Mera |
|---|---|
| Playwright na `en-US` prevede `test_tok` na engleski | `locale="sr-RS"` podrazumevano u `novi_kontekst` |
| Nedostajuci ili zastareo prevod tiho pada na srpski | testovi bez cirilice pod `en`; `msgattrib` provere |
| `msgid` se promeni (izmena srpskog teksta), engleski postane `fuzzy` | `fuzzy` se ne ostavlja; T3 provera |
| HTML u `msgstr` kroz `blocktranslate` | pravilo za `translate`; security |
| Skriveno procuri kroz prevod (tezina, tih zadatak u opisu) | pravila za `translate`; `ZABRANJENE_RECI_EN` |
| Duzi engleski tekst preliva 320 px | `JS_PRELIVANJE` na oba jezika |
| Stara sesija sa tekstom | `motor.nadogradi` i `NadogradnjaTests` |
| Povratak koda posle `0004`: sesije sa kljucevima stari kod ne razume | uz `migrate igra 0003` obrisati sesije (lokalno, igrac gubi tekucu partiju) |
| Neprepoznat tekst u bazi | migracija staje i ne menja nista; razvijalac odlucuje |

**Tacke bez povratka:** `migrate` za `0004` i `0005` na lokalnoj `db.sqlite3` (pre toga kopija baze; povratak `migrate igra 0003`); pokrece backend-senior, odobrava korisnik potvrdom plana. Engleske ocene, lekcije, napomenu i naziv igre odobrava klijent pre isporuke. Isporuke na server nema.

### 12.12 Odluke korisnika (2026-11-11)

| # | Pitanje | Odluka | Posledica |
|---|---|---|---|
| J1 | Da li deljena strana ima izbor jezika? | Da, link `?jezik=` koji vazi samo za tu stranu, bez kolacica | Jedna grana u `deljeno` i tri testa |
| J2 | Format datuma na engleskom? | ISO `2026-11-10` (`Y-m-d`), ne preporuceni `10 Nov 2026` | MVP 3 „10.11.2026“ vazi za srpski; engleski bez naziva meseca, pa ne zavisi od Django kataloga meseci; kolona datuma iste sirine kao srpska |
| J3 | Naziv igre na engleskom? | „Orchestrator“ | Naslov, `<title>`, tekst deljenja; ide u tabelu za klijenta |

### 12.13 Dokumentacija posle izmene (predlog; planer je ne menja)

1. `projekat-standardi`, red „Tekst na ekranu cirilicom, kod latinicom bez dijakritika“ postaje: „Tekst na ekranu na srpskom (cirilica) i engleskom, kroz Django i18n; izvor (msgid) je odobren srpski tekst; kod latinicom bez dijakritika | srpski ostaje izvor, engleski se menja samo u `.po` | nijedno“.
2. `projekat-standardi`, novi redovi: „Motor i `parametri.py` vracaju kljuceve, nikad prevedeni tekst; tekst u `parametri.py` oznacen lokalnom `gettext_noop`, bez uvoza Django-a; prevode samo `igra/tekstovi.py` i sabloni | motor ostaje cist, JSON ne zavisi od jezika | nijedno“; „Tekst skripte stize kroz `json_script` `tekstovi`, bez `JavaScriptCatalog`; skripta samo popunjava `%(ime)s` | jedan katalog, bez dodatnog zahteva | nijedno“; „Formati po jeziku (datum, zarez, novac, minuti) u `tekstovi.FORMATI`, nikad u `.po` | craft-i18n: kodovi formata se ne prevode | nijedno“; „Katalozi `locale/{en,sr}/LC_MESSAGES/django.po` i `.mo` su u projektu; `sr` nosi samo mnozinu | server i testovi bez gettext-a u PATH-u | nijedno“; „Komande i log ostaju srpski latinicom | jedan jezik za pretragu | nijedno“; „Jezik: `set_language` na `jezik/` (samo POST), kolacic 365 dana, bez prefiksa u URL-u | link za deljenje je isti za sve jezike | nijedno“. Red o prikazima: plus „`jezik` (POST, Django `set_language`)“.
3. `projekat-domen`, „Ceo tekst na ekranu je cirilicom.“ postaje: „Tekst na ekranu postoji na srpskom (cirilicom) i engleskom; Haiku, Sonnet, Opus, low, high, max, CSS i CRUD su isti na oba jezika. Jezik bira igrac i pamti se u kolacicu; novi posetilac dobija jezik pregledaca (engleski ako ga trazi, inace srpski). Rang lista i deljena strana su na jeziku onoga ko gleda; ime igraca se ne prevodi.“ Pravilo 1, dodatak: „Uspeh i tih neuspeh nose isti kljuc statusa `gotovo` na oba jezika; baza i JSON cuvaju kljuceve, ne tekst.“ Tabela ishoda i ocena: engleski u zagradi posle odobrenja klijenta. „Sta mora da pise na ekranu“: dodati engleski tekst napomene (posle odobrenja). Recnik: kolona „engleski“ iz 12.8.
4. `projekat-domen/references/parametri.md`: tabela zadataka dobija kolonu „kljuc“; novi odeljak „Jezik“: „Kolacic jezika vazi 365 dana (u `settings.py`, nije parametar igre). Poreklo: odluka plana 2026-11-11; Django podrazumevano brise kolacic pri zatvaranju pregledaca, a MVP 6 trazi da se izbor pamti.“
5. `CLAUDE.md` (samo predlog): u tabeli rasporeda nova faza posle implementacije: „prevod | `translate` | engleski i srpska mnozina u `.po`, posle izdvajanja tekstova“; `backend-senior` „motor, parametri, modeli, migracije, komande, prikazi i izdvajanje tekstova“; red: „Za svaki tekst na ekranu ucitaj `craft-i18n`. Stara ljuska dodaje gettext u PATH: `C:\Users\Bane\AppData\Local\Programs\gettext-iconv\bin`.“
6. `MVP.md` (menja korisnik): posle J2, odeljak 3 „Datum se prikazuje kao 10.11.2026“ dobija engleski oblik.
