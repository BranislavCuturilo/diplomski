# Plan izrade: igra Orkestrator

Status: **ceka potvrdu korisnika.** Izrada ne pocinje pre potvrde.
Nista iz ovog plana nije pokrenuto; brojevi oznaceni kao rucni proracun nisu izlaz simulacije.
Oznake [P1] do [P8] u ugovoru upucuju na odluke iz odeljka 1.

## 1. Odluke korisnika (2026-11-09)

| # | Pitanje | Odluka | Posledica |
|---|---|---|---|
| P1 | Da li igrac pre izbora vidi tezinu zadatka? | **Tezina se ne ispisuje i ne salje kao polje**, ni tokom igre ni na zavrsnom ekranu. | Igrac tezinu zakljucuje iz naziva i iz procene (odnos 1:3:6); to je namerno i deo je ucenja. Tezina ostaje u `parametri.py`. |
| P2 | Da li igrac pre potvrde vidi procenu cene i minuta? | **Da**: server salje gotovu mapu od 81 kombinacije za tekuci zadatak (`procene`). | Igrac moze da planira budzet; formula ostaje na serveru, sansa se ne salje. |
| P3 | `nova` usred igre? | **Dozvoljeno, uz potvrdu** (`window.confirm`, jer Bootstrap JS nije ucitan). | Tekuca partija se brise i pravi se novo seme. Igrac moze da ponavlja partiju; to je prihvaceno. |
| P4 | Sta GET `pocetna` radi bez igre, i koji status daje `potez` bez igre? | **GET sam pravi igru** (bez uvodnog ekrana). `potez` bez igre: **409** `nema_igre`. | Jedan ekran manje; svaka poseta pravi red u tabeli sesija, sto lokalno nije problem. |
| P5 | Istovremeno pogresan krug i nepoznat izbor: 400 ili 409? | **400 ima prednost**: zahtev se proverava pre citanja stanja. | Razliku vidi samo rucno sastavljen zahtev; pregledac nikad ne salje nepoznat izbor. |
| P6 | Granica prekoracenja i zaokruzivanje? | **Strogo vece od 24 $ i 150 min, nad nezaokruzenim**, uz uklanjanje suma racuna u pokretnom zarezu (`round(x, 9)`, tacne vrednosti imaju najvise 7 decimala). | Tabela iz `parametri.md` to potvrdjuje: „sve Opus, high“ pogadja tacno 150 min u oko 8,25 % partija; sa „vece ili jednako“ srednji poeni bi bili oko 66,5, a u tabeli je 68,0. |
| P7 | Zahtev sa dodatnim kljucem (npr. `cena`, `poeni`)? | **Odbiti sa 400** (tacan skup kljuceva). | Pravilo „klijent nikad ne salje cenu“ postaje proverljivo testom. |
| P8 | Bootstrap: CDN ili lokalna kopija? | **Lokalna kopija** 5.3.8 u `static/igra/`, kroz jedan `<link>`. | Igra i testovi rade bez mreze; jedna datoteka vise u projektu. |

## 2. Odluke plana (nisu pitanja, MVP ih odredjuje ili nemaju posledicu po igru)

- Poeni se ne prikazuju dok igra traje (MVP 3.3: igrac vidi *samo* cenu, minute, budzet, rok i status).
- `cena` i `minuti` u rezultatu kruga su stvarno placen iznos: kod dorade vec puta 2.
- Odgovor kruga pored rezultata nosi i sledeci ekran (krug, zadatak, zavrsni podaci); bez toga klijent ne bi imao sta da prikaze.
- Seme se ne salje nikad, ni na kraju. Sansa se ne cuva u stanju ni salje.
- Zavrsena igra ostaje vidljiva na `/` dok se ne pokrene nova.
- Prikaz: cena kruga 3 decimale, budzet 2, minuti 1, zarez kao separator; budzet i rok kao potroseno i preostalo (preostalo moze biti negativno).
- Nazivi zadataka idu cirilicom (MVP 6): tabela u odeljku 6. Skracenice CSS i CRUD ostaju latinicom.
- Sablon i skripta su u korenu projekta (`templates/...`, `static/...`), doslovno po standardu.
- Rucni proracun ocekivane vrednosti uz potvrdjeno tumacenje daje 73,0 / 68,1 / 20,75 (tabela: 72,8 / 68,0 / 20,8; standardna greska oko 0,4). Simulacija nije pokrenuta.

## 3. Raspored datoteka i ko pise

Koren: `C:\poredjenje-orkestrator\plugin\projekat\`

| Datoteka | Agent | Talas | Napomena |
|---|---|---|---|
| `manage.py`, `orkestrator/{__init__,settings,urls,wsgi,asgi}.py` | backend-senior | T1 | `startproject orkestrator .` |
| `igra/{__init__,apps}.py` | backend-senior | T1 | posle `startapp` obrisati `models.py`, `admin.py`, `migrations/` i obavezno `tests.py` (sudara se sa paketom `tests/`) |
| `igra/parametri.py` | backend-senior | T1 | svi brojevi i tekstovi igre |
| `igra/motor.py` | backend-senior | T1 | bez uvoza Django-a |
| `igra/views.py` | backend-senior | T1 | tri funkcije; ime `views.py` jer na njega reaguje hook `require_skill.py` |
| `templates/igra/igra.html` | frontend-medior | T1 | jedan sablon |
| `static/igra/igra.js` | frontend-medior | T1 | bez biblioteka |
| `static/igra/bootstrap-5.3.8.min.css` | frontend-medior | T1 | preuzeti jednom (odeljak 6) i proveriti SHA-384 [P8] |
| `igra/tests/{__init__,test_motor,test_prikazi,test_tok}.py` | qa | T2 | |
| (samo citanje) | security | T2 | revizija, bez pisanja |

`settings.py`: `INSTALLED_APPS` = `sessions`, `staticfiles`, `igra` (bez admin, auth, contenttypes, messages); `SESSION_ENGINE = "django.contrib.sessions.backends.db"` izricito; `TEMPLATES.DIRS = [BASE_DIR/"templates"]`; `STATICFILES_DIRS = [BASE_DIR/"static"]`; `LANGUAGE_CODE = "sr"`; `CSRF_COOKIE_HTTPONLY` ostaje False; SQLite `db.sqlite3`; `ALLOWED_HOSTS` localhost i 127.0.0.1; `SECRET_KEY` iz okruzenja, sa `django-insecure-` rezervom za lokalni rad.
`orkestrator/urls.py` drzi sve tri rute: `""` `pocetna`, `"potez/"` `potez`, `"nova/"` `nova`.

## 4. `igra/parametri.py`: struktura

Samo konstante; kljucevi su latinicom, tekst za ekran cirilicom.

| Ime | Oblik |
|---|---|
| `KRUGOVA`, `BUDZET`, `ROK`, `POCETNI_POENI`, `MIN_POENI` | 8, 24, 150, 100, 0 |
| `KAZNA_DORADA`, `KAZNA_TIHA`, `KAZNA_BUDZET`, `KAZNA_ROK` | 5, 25, 30, 20 |
| `MNOZILAC_DORADE`, `DODATAK_TIHA_CENA`, `DODATAK_TIHA_MINUTI` | 2, 3, 1 |
| `SANSA_MIN`, `SANSA_MAX`, `KOCKA_MIN`, `KOCKA_MAX`, `TOKENA_PO_MILION` | 5, 99, 1, 100, 1000000 |
| `DECIMALA_POREDJENJA`, `DECIMALA_JAVNIH` | 9, 4 |
| `ZADACI` | lista od 8 `{naziv, tezina, tih}`, redom iz tabele |
| `BAZA` | `{tezina: {tokeni, minuti}}` |
| `MODELI` | `{haiku\|sonnet\|opus: {naziv, opis, cena, brzina, sansa: {1,2,3}}}` |
| `NIVOI` | `{low\|high\|max: {naziv, opis, tokeni, brzina, bonus: {1,2,3}}}` |
| `KONTEKSTI` | `{malo\|taman\|sve: {naziv, opis, tokeni, bonus: {1,2,3}}}` |
| `PODELE` | `{sam\|tri\|pedeset: {naziv, opis, tokeni, brzina, bonus}}` |
| `OCENE` | `[(85, tekst), (65, tekst), (40, tekst), (0, tekst)]` |
| `STATUS_GOTOVO`, `STATUS_DORADA`, `NAPOMENA` | doslovni tekst, odeljak 6 |
| `LEKCIJE` | `{tiha\|opus_lako\|max\|sve\|pedeset: {tekst, odeljak}}`, redosled kao u MVP tabeli |

`opis` je kvalitativan (bez procenata i bez reci „тих“): npr. Haiku „најјефтинији и најбржи“.

## 5. `igra/motor.py`: stanje i potpisi

### Oblik stanja (`request.session["igra"]`, samo JSON tipovi)

```
{ "seme": "<token>", "krug": 1, "zavrsena": false,
  "potroseno": 0.0, "minuti": 0.0,
  "istorija": [ { "krug": 1, "izbori": {model, nivo, kontekst, podela},
                  "cena": 0.018, "minuti": 2.5, "ishod": "uspeh|dorada|tih_neuspeh" } ],
  "rezultat": null }
```

`rezultat` popunjava kontrolni skup: `{poeni, ocena, ukupna_cena, ukupni_minuti, budzet_prekoracen, rok_prekoracen, tihe_greske, lekcije}`. Tekuci poeni se ne vode dok igra traje; racunaju se jednom, iz istorije.

### Granica skriveno / javno

| Polje stanja | Dok igra traje | Posle kraja |
|---|---|---|
| `seme`, sansa (ne cuva se), `tih` (samo `parametri`), `istorija[].izbori` | skriveno | skriveno |
| `istorija[].ishod` | skriveno; u javni `status` prevodi se tako da `uspeh` i `tih_neuspeh` daju isti tekst | isto, plus spisak tihih gresaka |
| `krug`, `zavrsena`, `potroseno`, `minuti`, cena i minuti poslednjeg kruga | javno | javno |
| `rezultat` | ne postoji | javno, kroz `zavrsni` |

### Potpisi

```
class NepoznatIzbor(ValueError); class PogresanKrug(Exception); class IgraZavrsena(Exception)

nova_igra(seme: str) -> dict
proveri_izbore(izbori: dict) -> None                     # NepoznatIzbor; samo str vrednosti
racun(tezina: int, izbori: dict) -> dict                 # {cena, minuti, sansa}; interno
uspeh_kruga(seme: str, krug: int, sansa: int) -> bool    # random.Random(f"{seme}:{krug}")
odigraj_potez(stanje: dict, krug: int, izbori: dict) -> dict     # novo stanje, ulaz netaknut
kontrolni_skup(stanje: dict) -> dict
oceni(poeni: int) -> str
lekcije(stanje: dict) -> list[dict]                      # {tekst, odeljak}
procene(tezina: int) -> dict                             # 81 kljuc, samo {cena, minuti}  [P2]
javne_opcije() -> dict                                   # kljuc, naziv, opis; bez brojeva
javni_prikaz(stanje: dict) -> dict                       # JEDINI izlaz ka klijentu
```

`javni_prikaz` gradi novi recnik polje po polje, nikad kopiranjem stanja i brisanjem kljuceva. Prikazi ne salju nista sto nije proslo kroz `javni_prikaz` ili `javne_opcije`.

```
odigraj_potez:
  proveri_izbore -> ako zavrsena: IgraZavrsena -> ako krug != tekuci: PogresanKrug   [P5]
  novo = duboka kopija; r = racun(zadatak.tezina, izbori)
  uspeh -> "uspeh"; inace tih -> "tih_neuspeh"; inace "dorada", cena i minuti * MNOZILAC_DORADE
  dodaj u istoriju, saberi potroseno i minuti
  ako krug == KRUGOVA: kontrolni_skup(novo) inace krug + 1

kontrolni_skup:
  cena  = potroseno + zbir(r.cena * DODATAK_TIHA_CENA za tihe)      # ukupno 4x
  minuti = minuti + zbir(r.minuti * DODATAK_TIHA_MINUTI za tihe)    # ukupno 2x
  poeni = POCETNI - KAZNA_DORADA*dorade - KAZNA_TIHA*tihe
  ako round(cena, DECIMALA_POREDJENJA) > BUDZET: - KAZNA_BUDZET     # POSLE dodataka  [P6]
  ako round(minuti, DECIMALA_POREDJENJA) > ROK:  - KAZNA_ROK
  poeni = max(poeni, MIN_POENI); zavrsena = true
```

Seme pravi `views.nova` i `pocetna`: `secrets.token_hex(16)`. Motor ostaje cist; simulacija koristi `nova_igra(str(i))`.

## 6. HTTP ugovor i ekrani

### `potez`: POST `/potez/`

Zaglavlja: `Content-Type: application/json`, `X-CSRFToken` iz kolacica `csrftoken` (`pocetna` ima `@ensure_csrf_cookie`, jer forma nije uvek na strani).

```json
{"krug": 3, "izbori": {"model": "sonnet", "nivo": "high", "kontekst": "taman", "podela": "sam"}}
```

| Status | Telo | Kada |
|---|---|---|
| 200 | JavniPrikaz | prihvacen potez; **tih neuspeh i uspeh daju identicno telo** |
| 400 | `{"greska": "neispravan_zahtev"}` | nije JSON, nije objekat, telo > 2 KB, pogresan skup kljuceva [P7], `krug` nije int (`true` i `"3"` su 400), vrednost izbora nije string ili nije poznata |
| 409 | `{"greska": "pogresan_krug" \| "igra_zavrsena", "stanje": JavniPrikaz}` | ceo broj koji nije tekuci krug; zavrsena igra |
| 409 | `{"greska": "nema_igre", "stanje": null}` | sesija bez igre [P4] |
| 403 | HTML Django strane | nema CSRF |
| 405 | prazno | nije POST |

Redosled: parsiranje i oblik (400), `proveri_izbore` (400), citanje sesije (409), `odigraj_potez` (409), `session["igra"] = novo`, 200. Provera string tipa ide pre `in` jer `[] in dict` baca `TypeError`. `ValueError` hvata i neispravan UTF-8. Ogranicenje velicine sprecava `RecursionError` na duboko ugnezdenom JSON-u.

### JavniPrikaz (isti skup kljuceva u svim odgovorima)

```json
{
  "faza": "igra",
  "krug": 4,
  "ukupno_krugova": 8,
  "zadatak": {"naziv": "CRUD прикази"},
  "budzet": {"limit": 24, "potroseno": 3.42, "preostalo": 20.58},
  "rok": {"limit": 150, "potroseno": 21.5, "preostalo": 128.5},
  "poslednji": {"krug": 3, "zadatak": "CSS и прилагођавање телефону", "cena": 0.018, "minuti": 2.5, "status": "готово"},
  "procene": {"haiku|low|malo|sam": {"cena": 0.0, "minuti": 0.0}},
  "zavrsni": null
}
```

Na kraju: `"faza": "zavrsena"`, `zadatak` i `procene` su `null`, `poslednji` je 8. krug, a `zavrsni` je:

```json
{"poeni": 45, "ocena": "скуп учитељ", "ukupna_cena": 28.78, "ukupni_minuti": 139.5,
 "budzet_prekoracen": true, "rok_prekoracen": false,
 "tihe_greske": [{"krug": 5, "zadatak": "Модел података и миграција", "dodatak_cena": 12.96, "dodatak_minuti": 30}],
 "lekcije": [{"tekst": "Ако је грешка тиха, задатак остаје највишем разреду.", "odeljak": "4.2"}],
 "napomena": "Цене и нивои размишљања су стварни подаци; вероватноће, казне и поени су измишљени параметри игре."}
```

### `nova`: POST `/nova/`

Obicna HTML forma sa `{% csrf_token %}`, bez JSON-a; ostala polja se ignorisu (klijent ne moze da zada seme). Uvek pravi novu igru sa novim semenom i vraca **302** na `/`, i usred igre [P3]. Potvrdu trazi skripta, samo dok je `faza` `igra`; server je ne proverava. Dupli klik na dugme samo jos jednom pravi igru na 1. krugu. 403 bez CSRF, 405 za GET.

### `pocetna`: GET `/`

`@require_GET`, `@ensure_csrf_cookie`, `@never_cache`. Bez igre sama pravi igru [P4]. Kontekst: `stanje` i `opcije`, Python objekti. U sablonu `{{ stanje|json_script:"stanje-igre" }}`, nikad `json.dumps` i nikad broj kroz `{{ }}` (srpska lokalizacija daje zarez).

### Ekran (jedna kolona, sirina 375 px)

Zaglavlje: naslov, „Круг 4 од 8“, Буџет i Рок (potroseno, preostalo, `.progress`). Karta zadatka: samo naziv, bez tezine [P1]. Cetiri grupe `btn-check` + `btn-group w-100`, svaka u svom redu; `<input>` iscrtava Django iz `opcije`; bez podrazumevanog izbora, izbori se brisu tek kad se promeni krug. Procena ispod grupa [P2]. Dugme „Потврди избор“ aktivno tek sa cetiri izbora. Alert „Резултат круга“: cena, minuti, status (zeleno `готово`, zuto `враћено на дораду`). Zavrsni ekran menja kontrole: rezultat 8. kruga, poeni, ocena, ukupna cena i minuti, tihe greske (ili „Нема тихих грешака.“), lekcije sa „одељак 4.2“, trajna napomena. Forma „Нова игра“ (`#nova-forma`) je na ekranu u obe faze, van bloka koji se prikazuje samo u jednoj [P3]. Bootstrap JS nije ucitan, pa bez modala i `data-bs-*`. U `<head>` i `<link rel="icon" href="data:,">`, da 404 za favicon ne prljava konzolu.

```html
<link href="{% static 'igra/bootstrap-5.3.8.min.css' %}" rel="stylesheet">
```

Datoteka se preuzima jednom sa `https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/css/bootstrap.min.css`. Njen SHA-384, u base64, mora biti `sRIl4kxILFvY47J16cr9ZwB07vP4J8+LH7qKQnuqkuIAvNWLzeN8tE5YBujZqJLB` (vrednost sa getbootstrap.com, 2026-11-09). Ako se ne slaze, posao staje i javlja se glavnoj sesiji. [P8]

### Skripta `igra.js`

Jedna funkcija `prikazi(stanje)` crta sve tri grane (GET, 200, 409), samo kroz `textContent`.

```
posalji: ako uToku -> kraj; uToku = true; dugme disabled
  r = fetch(POST); tekst = await r.text(); pokusaj JSON.parse (nikad r.json())
  200 -> prikazi(telo)
  409 sa stanjem -> prikazi(telo.stanje), „Стање је освежено.“
  409 nema_igre -> „Партија више не постоји. Освежите страну за нову игру.“
  400 -> „Захтев није исправан. Освежите страну.“, izbori ostaju
  ostalo (403, 500, mreza, nije JSON) -> „Сервер није одговорио како треба. Покушајте поново.“
  uvek: uToku = false; azuriraj dugme
```

`#nova-forma`, dogadjaj `submit`: dok je `faza` `igra`, `window.confirm("Започети нову игру? Текућа партија се губи.")`; na odustajanje `preventDefault` [P3]. Na zavrsnom ekranu bez pitanja.

Dupli klik: `uToku` i `disabled` sprecavaju drugi POST. Ako ipak prodje, 409 nosi tekuce stanje, a `poslednji` u njemu cuva prikaz rezultata.

### Tekst na ekranu

| Vrsta | Tekst |
|---|---|
| Status (doslovno) | готово; враћено на дораду |
| Ocena (doslovno) | одличан оркестратор; солидан; скуп учитељ; пожар |
| Lekcije (doslovno, odeljak) | Ако је грешка тиха, задатак остаје највишем разреду. (4.2); Најскупљи модел није увек најбољи избор. (3.2); Изнад нивоа high цена расте, а квалитет не. (3.3); Превише контекста квари резултат исто као премало. (3.1); Више агената не значи јефтиније. (5.3) |
| Napomena (doslovno) | Цене и нивои размишљања су стварни подаци; вероватноће, казне и поени су измишљени параметри игре. |
| Zadaci | Превод почетне стране; Шаблон листе и форме; CSS и прилагођавање телефону; CRUD прикази; Модел података и миграција; Провера права приступа; Аутоматски тестови; Безбедносна ревизија |
| Opcije | Haiku, Sonnet, Opus; low, high, max; мало, таман, све; сам, 3 агента, 50 агената |
| Oznake | Оркестратор, Круг, Буџет, Рок, Потрошено, Преостало, Модел, Ниво размишљања, Контекст, Подела посла, Цена, Минути, Статус, Поени, Оцена, Укупна цена, Укупно минута, Тихе грешке, Лекције, Контролни скуп |

## 7. Testovi

Pokretanje iz korena projekta (skripta poziva `manage.py`): `python "C:/poredjenje-orkestrator/plugin/config/skills/diplomski/tools/test_summary.py"`.

| MVP 7 | Uslov | Testovi |
|---|---|---|
| 1 | Cela igra u pregledacu | `test_tok.test_cela_igra_do_zavrsnog_ekrana` |
| 2 | Isto seme, isti rezultat | `test_motor.test_isto_seme_isti_izbori_isti_rezultat`, `test_formula_uspeha_doslovno`, `test_globalni_random_ne_utice`; `test_prikazi.test_isto_seme_isti_odgovori` |
| 3 | Bez skrivenih podataka | `test_prikazi.test_nijedan_odgovor_ne_sadrzi_skriveno`, `test_tacan_skup_kljuceva_javnog_prikaza`, `test_tih_neuspeh_bajt_identican_uspehu`, `test_kolacici_bez_stanja`, `test_session_engine_baza`; `test_tok.test_mreza_i_dom_bez_skrivenog` |
| 4 | 409, 400, stanje netaknuto | `test_prikazi.test_pogresan_krug_409`, `test_zavrsena_igra_409`, `test_nepoznat_izbor_400` (po polju), `test_neispravan_zahtev_400` (subTest za svaki red tabele 400), `test_stanje_netaknuto_posle_greske`, `test_prednost_400_nad_409` [P5], `test_nema_igre_409` [P4], `test_dodatni_kljuc_400` [P7], `test_bez_csrf_403` (`Client(enforce_csrf_checks=True)`), `test_potez_get_405` |
| 5 | Dupli klik | `test_prikazi.test_dupli_potez_drugi_409_stanje_isto`; `test_motor.test_odigraj_ne_menja_ulaz`; `test_tok.test_dupli_klik_jedan_post` |
| 6 | 375 px, cista konzola | `test_tok.test_375_bez_horizontalnog_skrola` (igra i zavrsni ekran), `test_tok.test_konzola_cista` |
| 7 | Pokrivenost | `test_motor`: racun po redu svake tabele, sansa 5 i 99, dorada 2x, tih 4x i 2x, `test_kazna_posle_dodataka`, `test_tacno_150_bez_kazne` [P6], `test_najmanje_nula`, ocene na 85/84/65/64/40/39, svaka lekcija ukljuceno i iskljuceno, napomena doslovno, redosled zadataka, `test_motor_cist` i `test_nema_brojeva_u_motoru` (`ast`: bez uvoza Django-a, bez literala osim 0 i 1); `test_prikazi.test_json_script_daje_recnik`, `test_nova_302_i_novo_seme`, `test_nova_usred_igre_pravi_novu` [P3], `test_nova_ignorise_seme`; `test_tok.test_nova_usred_igre_potvrda` (prihvatanje vraca na 1. krug, odustajanje ne menja krug; `page.on("dialog", ...)`); ceo paket `EXIT=0` |
| 8 | Balans | `test_motor.test_balans_poredak_5000_semena` (semena 0 do 4999), `test_balans_srednje_vrednosti` (+-1,5 oko 72,8 / 68,0 / 20,8, cuva tumacenje racuna) |

**`test_nijedan_odgovor_ne_sadrzi_skriveno`:** vise semena, puna igra; posle svakog koraka GET `/`, 200, 400 i 409. U telu nema vrednosti semena, a rekurzivno nema kljuceva `seme`, `sansa`, `tih*`, `tezina` [P1], `ishod`, `uspeh`, `neuspeh`, `bonus`. HTML se proverava kroz parsiran `json_script` i reci sa granicom (`\bsansa\b`).
**`test_tih_neuspeh_bajt_identican_uspehu`:** bez lazne funkcije; petlja nalazi dva semena sa istim ishodima krugova 1 do 4, a u krugu 5 jedno uspeh i drugo tih neuspeh. Isti izbori; status i `content` moraju biti jednaki bajt po bajt.

### Zamke Playwright sync API-ja uz Django live server

1. **Async-unsafe.** `sync_playwright` drzi petlju u test niti, pa ORM i `flush` u toj niti bacaju `SynchronousOnlyOperation`. `DJANGO_ALLOW_ASYNC_UNSAFE=true` se postavlja u `setUpClass`, pre `super()`, i vraca u cleanup; samo u `test_tok`.
2. **Slobodan port.** Port ostaje podrazumevani 0, koristi se samo `self.live_server_url` (MVP 9: moze da radi i druga izrada).
3. **Klasa.** `StaticLiveServerTestCase`, ne `LiveServerTestCase`, inace `igra.js` daje 404.
4. **Deljena baza.** SQLite u memoriji deli vezu izmedju niti: test nit dira bazu samo pre `goto` ili posle zavrsenog cekanja odgovora. Svaki test se zavrsava `flush`-om. Bez `--parallel`.
5. **Poznato seme.** `SessionStore()`, `store["igra"] = motor.nova_igra("42")`, `store.create()`, pa `context.add_cookies` sa `sessionid` i `url` pre prvog `goto`.
6. **`btn-check` je vizuelno sakriven:** klik na `label[for=...]`, ne `check()` na inputu.
7. **Konzola.** Chromium svaki odgovor 4xx belezi kao `Failed to load resource`. Normalan tok zato ne sme imati 409. Sluzaju se i `console` i `pageerror`; samo poseban test sa `page.route` dozvoljava tu jednu poruku.
8. **Cekanje** kroz `expect_response` i `expect`, nikad `sleep`. Novi `context` po testu; pregledac po klasi; gasi se pre `super().tearDownClass()`.

## 8. Faze, talasi, dokazi

Najvise 3 agenta po talasu. Faza se upisuje kroz `faza.py` pre pocetka.

| Faza | Ko | Dokaz da je gotova |
|---|---|---|
| planiranje | planer | korisnik potvrdio plan |
| delegiranje | glavna sesija, **preporuka: nova sesija** | talasi izvedeni iz ovog plana |
| implementacija, T1 | backend-senior + frontend-medior, zajedno | backend: `python -m django --version`, `manage.py check`, `migrate`, `makemigrations --check --dry-run`, simulacija tri strategije (ispisani srednji poeni), `potez` i `nova` kroz Django klijent. Frontend: proveren SHA-384 lokalnog Bootstrap-a; pise prema ugovoru; rad u pregledacu dokazuje T2 i izvestaj to mora da navede kao nepokrenuto |
| kontrolni skup, T2 | qa + security, u jednoj poruci | qa: `test_summary.py` `EXIT=0`, snimci na 375/768/1440 px. security: izvestaj bez nalaza koji traze ispravku, ukljucujuci proveru `javni_prikaz` kao jedinog izlaza |
| poruka klijentu | glavna sesija | kratak izvestaj sa stvarnim rezultatima testova |

Nalaz koji trazi ispravku vraca fazu na `implementacija`, pa ponovo `kontrolni skup`.

**Zavisnosti.** Backend i frontend su nezavisni po datotekama jer je ugovor zamrznut u odeljku 6; frontend zavisi od ugovora, ne od koda. Testovi zavise od oba. Cena paralelnog T1 je da se prvi spoj vidi tek u T2; ako glavna sesija zeli snimke frontenda pre qa, frontend ide posle backenda, uz jedan talas vise.

**Ugovor imena (backend i frontend)**

| Sta | Ime |
|---|---|
| JSON | kljucevi iz odeljka 6, bez izmena; `greska`: `neispravan_zahtev`, `pogresan_krug`, `igra_zavrsena`, `nema_igre`; `faza`: `igra`, `zavrsena` |
| Kontekst sablona | `stanje`, `opcije` (`{model, nivo, kontekst, podela: [{kljuc, naziv, opis}]}`) |
| Vrednosti izbora | `haiku`, `sonnet`, `opus`; `low`, `high`, `max`; `malo`, `taman`, `sve`; `sam`, `tri`, `pedeset` |
| Kljuc procene | `model\|nivo\|kontekst\|podela` |
| Radio | `name` = `model`, `nivo`, `kontekst`, `podela`; `id` = `<name>-<vrednost>` |
| DOM | `#stanje-igre`, `#kontrole` (`data-url-potez` iz `{% url 'potez' %}`), `#potvrdi`, `#procena`, `#rezultat`, `#poruka`, `#krug`, `#zadatak`, `#budzet`, `#rok`, `#zavrsni`, `#nova-forma` |
| URL imena | `pocetna`, `potez`, `nova` |

Promena bilo cega iz ove tabele ide kroz glavnu sesiju, nikad jednostrano.

## 9. Rizici i opseg

| Rizik | Mera |
|---|---|
| Curenje skrivenog kroz novo polje | `javni_prikaz` po beloj listi; test tacnog skupa kljuceva; security |
| Greska u tumacenju racuna | `test_balans_srednje_vrednosti` hvata pomeraj koji sam poredak ne bi |
| Promena parametra da bi test prosao | zabranjena bez odobrenja korisnika; `parametri.md` je izvor |
| Sum u pokretnom zarezu na granici 150 | `DECIMALA_POREDJENJA` i `test_tacno_150_bez_kazne` |
| Izmena sesije koja se ne upise | samo `request.session["igra"] = novo`, motor vraca novi recnik |
| Istovremena dva POST-a pre upisa | isti ulaz daje isti ishod, poslednji upis je isti; `uToku` u skripti |
| Izmenjena lokalna kopija Bootstrap-a | SHA-384 se proverava pri preuzimanju [P8] |
| Tezina procuri kao polje | `test_nijedan_odgovor_ne_sadrzi_skriveno` i bela lista `javni_prikaz` [P1] |

**Tacke bez povratka.** Nema migracije na punoj bazi ni isporuke. Odobrava korisnik: ovaj plan; svaku promenu broja igre.

**Namerno van opsega (MVP 2).** Nalozi i prijava; cuvanje rezultata i rang lista; vise jezika; isporuka na server, Docker, Nginx, MySQL; nivoi tezine, animacije, zvuk.

## 10. Rang lista (2026-11-10)

Status: **ceka potvrdu korisnika.** Pitanja R1 do R4 su odlucena (10.10). **Pocetni sadrzaj sifarnika nepodobnih imena ceka pregled klijenta** (10.4). Nista iz ovog odeljka nije pokrenuto.
Izvori: MVP 3 „Rang lista“, pravilo 3, uslov 9; `projekat-odluke` 2026-11-10 (model dozvoljen, preovladjuje nad `projekat-standardi` pravilom 3); odgovori korisnika na R1-R4 i odluka o sifarniku, preneti preko glavne sesije 2026-11-10.

**Odgovoreno (ne pita se ponovo):** model u aplikaciji `igra` i migracija u istoj SQLite bazi, stanje partije ostaje u sesiji; lista je odeljak iste strane, vidljiv od prvog ucitavanja; GET `/` i dalje pravi igru; „Нова игра“ usred partije ostaje [P3]; jedan upis po zavrsenoj partiji, klijent salje samo ime, poeni i ocena iz stanja; ime 1-20 znakova bez praznog na pocetku i kraju, ista imena dozvoljena; redosled vise poena, pa ranije sacuvan; datum kao 10.11.2026; R1-R4 i sifarnik (10.10).

### 10.1 Sta u odeljcima 1-9 vise ne vazi

| Odeljak | Bilo | Sada |
|---|---|---|
| 1 P3, 6 skripta | Na zavrsnom ekranu „Нова игра“ bez pitanja | Isti `window.confirm` i na zavrsnom ekranu dok rezultat nije sacuvan; posle cuvanja bez pitanja; usred igre kao do sada (R4). Server se ne menja. |
| 2 | Poeni se ne prikazuju dok igra traje | Vazi za tekucu partiju. Lista, vidljiva i dok igra traje, prikazuje poene ranije sacuvanih partija. |
| 3 | `startapp` bez `models.py` i `migrations/`; tri rute | Postoje `igra/models.py` (dva modela), `igra/migrations/`, `igra/imena.py` i `igra/management/commands/`; cetvrta ruta `"sacuvaj/"` `sacuvaj`. `INSTALLED_APPS` se ne menja (modeli nemaju FK, ne treba `contenttypes` ni `auth`). |
| 3 | `TIME_ZONE` nije naveden; u kodu `'UTC'` | `TIME_ZONE = 'Europe/Belgrade'` (10.5). |
| 5 | Stanje bez oznake cuvanja; `javni_prikaz` JEDINI izlaz | Stanje dobija opcioni kljuc `sacuvan`. Izlaza ka klijentu su dva, oba po beloj listi: `javni_prikaz` (nepromenjen) i `views._javni_rang`. Sifarnik nema izlaz. |
| 6 `pocetna` | Kontekst `stanje`, `opcije` | Plus `rang` (10.5). |
| 6 skripta | Posle odgovora skrol na vrh | Samo posle odgovora poteza; cuvanje ne skroluje (10.6). |
| 7 | Uslovi MVP 7 od 1 do 8 | Plus uslov 9 (10.7); `test_nova_posle_kraja_bez_potvrde` se zamenjuje (R4). |
| 8 ugovor | Tri rute, DOM bez liste | Prosiren u 10.8. |
| 9 | „Nema migracije“; rang lista van opsega | Migracije na lokalnoj `db.sqlite3` (10.9); rang lista je u opsegu. |

### 10.2 Modeli, migracije, motor

`igra/parametri.py` dobija `IME_MAKS = 20` i `RANG_MESTA = 10` (MVP 5: brojevi na jednom mestu).

`igra/models.py` (nova):

```
class RezultatQuerySet(models.QuerySet):
    def najboljih(self):          # vise poena iznad; kod jednakih raniji; id razresava isti trenutak
        return self.order_by("-poeni", "sacuvan", "id")[:p.RANG_MESTA]

def proveri_ime(vrednost) -> None                     # ValidationError(code="neispravno_ime") ako not imena.ime_ispravno(vrednost)

class Rezultat(models.Model):
    id      = models.BigAutoField(primary_key=True)   # izricito: bez DEFAULT_AUTO_FIELD check daje W042
    ime     = models.CharField(max_length=p.IME_MAKS, validators=[proveri_ime])
    poeni   = models.PositiveSmallIntegerField()
    ocena   = models.CharField(max_length=32)         # tekst iz stanja; najduza ocena ima 19 znakova
    sacuvan = models.DateTimeField(default=timezone.now, editable=False)   # UTC; default, ne auto_now_add, da test zada trenutak
    partija = models.CharField(max_length=64, unique=True, editable=False) # sha256 semena; nikad u odgovoru
    objects = RezultatQuerySet.as_manager()
    class Meta:
        indexes = [models.Index(fields=["-poeni", "sacuvan", "id"], name="igra_rang_idx")]
        constraints = [
            models.CheckConstraint(condition=Q(poeni__gte=p.MIN_POENI) & Q(poeni__lte=p.POCETNI_POENI), name="igra_poeni_opseg"),
            models.CheckConstraint(condition=~Q(ime=""), name="igra_ime_nije_prazno"),
        ]

class NepodobnoImeQuerySet(models.QuerySet):
    def sadrzi(self, ime) -> bool: return self.filter(kljuc=imena.kljuc_imena(ime)).exists()

class NepodobnoIme(models.Model):                     # sifarnik; nikad ne ide klijentu
    id    = models.BigAutoField(primary_key=True)
    kljuc = models.CharField(max_length=100, unique=True)   # vec normalizovano (10.4)
    objects = NepodobnoImeQuerySet.as_manager()
    class Meta:
        constraints = [models.CheckConstraint(condition=~Q(kljuc=""), name="igra_nepodobno_nije_prazno")]
```

Indeks prati tacan redosled upita za 10 najboljih. Ocena se cuva kao tekst iz `stanje["rezultat"]`, ne racuna se ponovo pri prikazu.

**Migracije:** `0001_initial.py` (oba modela) pravi `python manage.py makemigrations igra`, bez rucnih izmena. `0002_nepodobna_imena.py` je migracija sa podacima: `RunPython` upisuje listu `KLJUCEVI` (vec normalizovane vrednosti, literali u datoteci, da kasnija izmena `kljuc_imena` ne promeni istoriju), a obrnuti korak brise iste kljuceve. Brojevi iz `parametri` se u `0001` zamrzavaju kao literali; promena `IME_MAKS` trazi novu migraciju, sto `makemigrations --check --dry-run` (dokaz T1, ostaje) odmah pokazuje.

**Motor** (cist, bez Django-a):

```
class IgraNijeZavrsena(Exception); class VecSacuvano(Exception)
za_cuvanje(stanje) -> {"poeni": int, "ocena": str}   # iz stanje["rezultat"]; IgraNijeZavrsena; VecSacuvano ako stanje.get("sacuvan") nije None
oznaci_sacuvano(stanje, broj: int) -> dict            # kopija sa "sacuvan": broj; ulaz netaknut
sacuvani_red(stanje) -> int | None
oznaka_partije(stanje) -> str                         # hashlib.sha256(seme).hexdigest()
```

`nova_igra` se ne menja: `sacuvan` nastaje tek pri cuvanju, citanje ide kroz `.get`, pa rade i postojece sesije. `nova` pravi novo stanje, oznaka nestaje i nova partija sme jedan upis. `test_motor_cist` ostaje bez izmene i prolazi: motor uvozi samo `hashlib` vise, a test zabranjuje `django`, `time`, `datetime`, `secrets`, `uuid`. `test_nema_brojeva_u_motoru`: nove funkcije nemaju literal.

**Alternativa, sigurnija od trazenog minimuma:** `partija` sa `unique=True`. Zasto: „tacno jednom“ vazi i kad brava sesije ne uspe (npr. neko kasnije ukloni `IMMEDIATE`), i proverljivo je bez niti. Cena je jedno polje; vrednost je hes nasumicnog semena od 128 bita, pa iz nje seme ne moze da se izvede.

### 10.3 `sacuvaj`: POST `/sacuvaj/`

Zaglavlja kao `potez`. Telo: `{"ime": "Пера"}`, tacno taj jedan kljuc.

| Status | Telo | Kada |
|---|---|---|
| 200 | `{"rang": Rang}` | upisano |
| 400 | `{"greska": "neispravan_zahtev"}` | nije JSON, nije objekat, telo > 2 KB, neispravan UTF-8, skup kljuceva nije `{ime}` (`poeni` ili `ocena` u zahtevu: 400, kao [P7]), `ime` nije string |
| 400 | `{"greska": "neispravno_ime"}` | string ne prolazi pravila 10.4; odgovor ne ponavlja ime |
| 400 | `{"greska": "nepodobno_ime"}` | kljuc imena je u sifarniku; telo je uvek tacno ovo, bez imena i bez stavke |
| 409 | `{"greska": "nema_igre", "rang": Rang}` | sesija bez igre |
| 409 | `{"greska": "igra_nije_zavrsena", "rang": Rang}` | partija traje (i kada je druga kartica pokrenula novu) |
| 409 | `{"greska": "vec_sacuvano", "rang": Rang}` | oznaka u stanju, ili red sa istom `partija` vec postoji |
| 403 | HTML Django strane | nema CSRF |
| 405 | prazno | nije POST (`@require_POST`) |

```
sacuvaj:
  ime = _procitaj_ime(request)            # _json_telo + oblik; NFC; proveri_ime -> 400 (pre sesije, kao [P5])
  ako NepodobnoIme.objects.sadrzi(ime): 400 nepodobno_ime   # citanje sifarnika, sesija netaknuta
  with transaction.atomic():               # BEGIN IMMEDIATE: brava pre prvog citanja sesije
    stanje = session.get("igra")           -> None: 409 nema_igre
    podaci = motor.za_cuvanje(stanje)      -> 409 igra_nije_zavrsena | vec_sacuvano
    r = Rezultat(ime=ime, **podaci, partija=motor.oznaka_partije(stanje))
    r.full_clean(validate_unique=False)    # stack-django pravilo 1; jedinstvenost proverava baza
    try: with transaction.atomic(): r.save()
    except IntegrityError: ako red sa tom partijom postoji -> 409 vec_sacuvano, inace raise
    novo = motor.oznaci_sacuvano(stanje, r.id)
    session["igra"] = novo; session.save(); session.modified = False   # isto kao potez
    telo = {"rang": _javni_rang(novo)}
  return JsonResponse(telo)
```

Red i oznaka se upisuju u istoj transakciji: ako upis sesije padne, nestaje i red. Odbijen zahtev ne upisuje ni red ni sesiju. Drugi istovremeni zahtev iste sesije ceka bravu, cita vec oznaceno stanje i dobija 409. Citanje tela: iz `_procitaj_zahtev` se izdvaja `_json_telo(request)` (isti izuzeci, `MAKS_VELICINA_TELA`), pa ga koriste oba prikaza; ponasanje poteza se ne menja i cuvaju ga postojeci testovi 400.

### 10.4 Ime i sifarnik nepodobnih imena

**`igra/imena.py`** (nova, cist Python: bez Django-a, uvozi samo `unicodedata` i `parametri`):

```
ime_ispravno(ime: str) -> bool     # pravila 3-5 ispod; ime je vec NFC
kljuc_imena(ime: str) -> str       # normalizacija za poredjenje sa sifarnikom
```

**Pravila imena.** Server ne skida razmake i ne menja vidljiv tekst; jedina izmena je NFC.

1. `type(ime) is str`, inace `neispravan_zahtev`.
2. `ime = unicodedata.normalize("NFC", ime)`; cuva se NFC oblik (Đorđe iz NFD i iz NFC je isto ime iste duzine).
3. Znak je Unicode kodna tacka posle NFC: `1 <= len(ime) <= IME_MAKS`. Emoji 😀 je jedan znak.
4. Prvi i poslednji znak nisu razmak (`str.isspace()`: obuhvata i NBSP, U+3000, tab i novi red); prvi znak nije kombinujuci (kategorija `M*`).
5. Nijedan znak nije iz kategorija `Cc` (kontrolni: `\n`, `\r`, `\t`), `Cf` (nevidljivi: U+200B, ZWJ U+200D, U+00AD, U+FEFF, smer teksta U+202A-202E i U+2066-2069), `Cs` (usamljen surogat: `json.loads('"\ud800"')` ga propusta, a SQLite ne moze da ga upise), `Co`, `Cn`, `Zl`, `Zp`. Od `Zs` je dozvoljen samo obican razmak U+0020. Emoji sastavljen ZWJ-om se zato odbija (R2).
6. Ista imena i dva razmaka u sredini su dozvoljeni.
7. (dopuna posle revizije 2026-11-10) Nijedan znak iz `NEVIDLJIVI` u `imena.py`: Default_Ignorable i prazni znakovi koje kategorije iz pravila 5 ne hvataju (Hangul popunjivaci U+115F, U+1160, U+3164, U+FFA0; prazan Braille U+2800; U+034F; selektori varijante U+FE00-FE0F i U+E0100-E01EF; U+17B4-17B5; U+180B-180F). Izuzetak: U+FE0F je dozvoljen samo odmah posle znaka kategorije `S*`, `N*` ili `P*` (❤️, 1️⃣, ™️); posle slova, razmaka, kombinujuceg znaka, na pocetku ili dvaput zaredom se odbija. Posledica: ℹ️ se odbija, jer je U+2139 slovo; prihvaceno.
8. Najvise `IME_MAKS_KOMBINUJUCIH` (2) uzastopna znaka kategorije `M*` posle NFC.

**`kljuc_imena`**, tacno ovim redom:

1. `s = NFKD(casefold(NFKD(ime)))`: velika i mala slova; NFKD rastavlja dijakritike i svodi oblike kao sto su ＰＥＲＡ i ligature na osnovna slova.
2. Izbaciti znakove kategorije `Mn` (dijakritici posle rastavljanja: š → s, č i ć → c, ž → z, й → и) i sve znakove iz `NEVIDLJIVI`, nezavisno od `ime_ispravno`.
3. Preslovljavanje po tabeli (`str.translate`): а a, б b, в v, г g, д d, ђ dj, е e, ж z, з z, и i, ј j, к k, л l, љ lj, м m, н n, њ nj, о o, п p, р r, с s, т t, ћ c, у u, ф f, х h, ц c, ч c, џ dz, ш s; latinicno đ → dj (nema rastavljanje). Dz i dž se tako slazu sa џ (dž → dz), lj i nj sa љ i њ (i jednoznakovni ǉ, ǌ, ǆ preko NFKD).
4. Zadrzati samo znakove kategorija `L*` i `N*`: nestaju svi razmaci (i unutrasnji), interpunkcija, simboli i emoji („П е-р.а“ → „pera“).
5. Rezultat moze biti prazan (ime samo od simbola); prazan kljuc nikad nije u sifarniku (ogranicenje modela).

„Ш“, „ш“, „Š“, „š“, „S“ i „s“ daju „s“. Zamena cifara za slova (0 → o, 4 → a) i ruska slova van srpske azbuke nisu u opsegu: siru mrezu prati vise laznih pogodaka.

**Poklapanje.** Odbija se samo ime ciji je kljuc JEDNAK nekoj stavci, celo ime: stavka „pera“ odbija „Пера“ i „P E R A“, ali ne i „Пера Перић“ („peraperic“). Sacuvani redovi se ne filtriraju pri prikazu; za njih postoje komande ispod.

**Poruka igracu:** jedna recenica, ista za svaku stavku (10.6). Sifarnik ne izlazi ni u jednom odgovoru, kontekstu ni sablonu.

**Pocetni sadrzaj** (`0002_nepodobna_imena.py`): nekoliko desetina najcescih psovki i uvreda, srpski i engleski, kao vec normalizovani kljucevi, jedan po redu, abecednim redom. Pise backend-senior u T1. **Ceka pregled klijenta**: klijent pregleda datoteku pre prihvatanja; izmene pre prihvatanja idu u `0002`, posle prihvatanja samo kroz komande ili novu migraciju.

**Komande** (`igra/management/commands/`, bez admina i naloga; sve izmene u `transaction.atomic()`, ispis kroz `self.stdout`, greska kroz `CommandError` sa izlaznim kodom 1):

| Komanda | Ponasanje |
|---|---|
| `nepodobno_dodaj REC [REC ...] [--obrisi-rezultate]` | Za svaku rec ispisuje kljuc. Prazan kljuc: `CommandError`, nista se ne upisuje. Postojeci kljuc: „vec postoji“, nastavlja. Zatim ispisuje sacuvane rezultate ciji je `kljuc_imena(ime)` jednak nekom od datih kljuceva (id, ime, poeni, datum). Bez opcije ih ne brise i ispisuje kako se brisu; sa `--obrisi-rezultate` brise ih u istoj transakciji i ispisuje broj. |
| `nepodobno_ukloni REC [REC ...]` | Brise stavke po kljucu; ako ijedna ne postoji, `CommandError` i nista nije obrisano. |
| `rezultati` | Svi sacuvani rezultati redom rang liste: mesto, id, ime, poeni, ocena, datum. |
| `rezultat_obrisi ID [ID ...]` | Brise po id-u i ispisuje obrisane redove; ako ijedan id ne postoji, `CommandError` i nista nije obrisano. Partija obrisanog reda se ne moze ponovo sacuvati (oznaka ostaje u njenoj sesiji). Izuzetak (revizija 2026-11-11, nisko, prihvaceno uz napomenu): migracija koja prepravlja `igra_rezultat` na SQLite-u (npr. 0006-0008) vraca brojac id-a na najveci postojeci id; ako je obrisan red sa najvecim id-om, novi red moze da dobije isti id, pa oznaka u sesiji obrisane partije vise ne pokazuje na nepostojeci red i partija moze ponovo da se sacuva. Pre takve migracije zapamti brojac (`SELECT seq FROM sqlite_sequence WHERE name = 'igra_rezultat'`), a posle nje ga vrati: `UPDATE sqlite_sequence SET seq = max(seq, <zapamceno>) WHERE name = 'igra_rezultat'`. |

Ime je tudji unos koji vide drugi: na strani samo kroz `{{ rang|json_script:"rang-lista" }}` (nikad `{{ }}` u HTML-u ni `|safe`); u skripti samo `textContent`, nikad `innerHTML` ni `insertAdjacentHTML`. Ime stoji u `<bdi>`, da desno-levi tekst ne premesti susedne kolone. MVP 6 (cirilica) vazi za tekst aplikacije; ime ostaje kako ga je igrac upisao.

Klijent pre slanja radi `ime.normalize("NFC").trim()`; dugme je onemoguceno dok je to prazno, pa „prazno posle skidanja razmaka“ ne stize do servera (server ga i dalje odbija). `maxlength="20"` broji UTF-16 jedinice, pa je za emoji strozi od servera; prihvatljivo. Ostala pravila i sifarnik proverava samo server.

### 10.5 Lista na strani i datum

`views._javni_rang(stanje | None) -> Rang`:

```json
{"lista": [{"ime": "Пера", "poeni": 85, "ocena": "одличан оркестратор", "datum": "10.11.2026"}],
 "sacuvano": true,
 "moj": 0}
```

- `lista`: najvise 10, redom iz `najboljih()`; svaki red tacno 4 kljuca, gradi se polje po polje (bez `id`, `partija`, `sacuvan`). Mesto 1-10 skripta racuna iz pozicije.
- `sacuvano`: tekuca partija je sacuvana (`motor.sacuvani_red(stanje) is not None`).
- `moj`: indeks sopstvenog reda u `lista`, ili `null` (nije sacuvano, ispod 10. mesta, posle nove igre). Server poredi `id` iz sesije sa redovima; `id` ne izlazi, pa igrac saznaje samo koji je red njegov. Nema novog skrivenog podatka.
- `Rang` dolazi na dva mesta: GET `/` (kontekst `rang`, `json_script` id `rang-lista`) i odgovori `sacuvaj` 200 i 409. `javni_prikaz` i odgovor `potez` se ne menjaju, pa `test_tacan_skup_kljuceva_javnog_prikaza` ostaje isti. Posle `nova` strana se ionako ponovo ucitava (302).

**Datum (R1):** `USE_TZ = True` ostaje (baza cuva UTC). `TIME_ZONE` postaje `'Europe/Belgrade'`: rezultat sacuvan 9.11. u 23:30 UTC nosi datum 10.11.2026. Formatira ga prikaz, u `_javni_rang`: `timezone.localtime(r.sacuvan).strftime("%d.%m.%Y")`, sa vodecom nulom (01.02.2026). Skripta ga samo ispisuje, bez `Date` u pregledacu, cija zona zavisi od racunara. Na Windows-u `zoneinfo` trazi paket `tzdata` (Django ga tamo povlaci kao zavisnost); proverava se u T1.

### 10.6 Ekran

Forma `#rang-forma` je u `#zavrsni`, posle `.zbir`, pa postoji samo na zavrsnom ekranu. Odeljak `#rang` je na kraju strane, posle `#nova-forma`, vidljiv u obe faze.

| Stanje | Forma | Poruka (`#rang-poruka`, `role="status"`, ili `#rang-greska`) | Lista |
|---|---|---|---|
| igra traje | nema je (u skrivenom `#zavrsni`) | - | bez isticanja |
| zavrsena, nije sacuvano | prazno polje; dugme onemoguceno dok je ime prazno | - | bez isticanja |
| cuvanje u toku | dugme `disabled`; `uCuvanju` sprecava drugi klik i Enter | - | - |
| 400 `neispravno_ime` ili `nepodobno_ime` | polje `.is-invalid`, vrednost ostaje, dugme ponovo aktivno | `#rang-greska`: odgovarajuci tekst | nepromenjena |
| 400 ostalo, 403, 500, mreza, nije JSON | ostaje | `#rang-greska`: postojece „Захтев није исправан…“ ili „Сервер није одговорио…“ | nepromenjena |
| 200 | skriva se | sacuvano, ili sacuvano van liste ako je `moj` `null` | iz odgovora, istaknut `moj` |
| 409 `vec_sacuvano` / `igra_nije_zavrsena` / `nema_igre` | skriva se | odgovarajuci tekst ispod | iz odgovora |
| osvezavanje posle cuvanja | nema je (`rang.sacuvano`) | kao posle 200 | istaknut red |
| posle „Нова игра“ | nema je (faza `igra`) | - | bez isticanja |
| prazna lista | - | - | tekst umesto tabele |

**„Нова игра“ (R4):** `#nova-forma` trazi postojeci `window.confirm(PITANJE_NOVA)` kada je `faza` `igra`, ili `zavrsena` dok `rang.sacuvano` nije `true`; posle cuvanja (i posle osvezavanja sacuvane partije) bez pitanja. Ako se `#rang-lista` ne procita, skripta pita (bolje pitanje vise nego izgubljen rezultat). Server se ne menja.

Cuvanje ne skroluje na vrh: poruka je tamo gde je igrac kliknuo. Gornji `#poruka` se za cuvanje ne koristi. Odgovor se cita kao tekst pa JSON, kao u `posalji`.

| Mesto | Tekst (doslovno) |
|---|---|
| naslov odeljka | Ранг листа |
| podnaslov | 10 најбољих сачуваних резултата |
| kolone | Место; Име; Поени; Оцена; Датум |
| prazna lista | Још нема сачуваних резултата. |
| oznaka polja | Име за ранг листу |
| pomoc ispod polja | Од 1 до 20 знакова. |
| dugme | Сачувај резултат |
| sacuvano | Резултат је сачуван. |
| sacuvano van liste | Резултат је сачуван, али није међу 10 најбољих. |
| `neispravno_ime` | Име мора имати од 1 до 20 знакова, без размака на почетку и крају и без невидљивих знакова. |
| `nepodobno_ime` (ista za svaku stavku) | Ово име није дозвољено. Изаберите друго име. |
| `vec_sacuvano` | Ова партија је већ сачувана. |
| `igra_nije_zavrsena` | Партија још није завршена. Освежите страну. |
| `nema_igre`, 400, ostalo | postojeci tekstovi iz odeljka 6 |
| potvrda nove igre | postojeca: Започети нову игру? Текућа партија се губи. |
| sopstveni red (`aria-current="true"`, skriven tekst za citac) | ваш резултат |
| lista nije procitana | Ранг листа није могла да се прочита. |

**Izgled**, samo postojeci tokeni: kartica kao `.zavrsni` (`--c-papir`, `--linija` u `--c-tinta`, `--rad-l`, `--senka`), ikonica postojeca `#ik-pehar`; sopstveni red `--c-primarna-svetla` sa levom ivicom `--c-primarna`; greska kroz Bootstrap `.is-invalid` i `.invalid-feedback` (vec vezani za `--bs-danger-rgb`); poruka sacuvano `--c-uspeh` na `--c-uspeh-svetla`; fokus `--fokus`. Tabela `.table .table-sm`, bez `.table-responsive`; ime `overflow-wrap: anywhere`, ocena se prelama, datum `white-space: nowrap`, poeni i datum `font-variant-numeric: tabular-nums`. Nova boja, ako ustreba, ide u odeljak 1 tokena uz izmeren kontrast. ID-jevi i klase u HTML-u ne smeju sadrzati reci iz `ZABRANJENE_RECI` (`tih`, `uspeh`, `ishod`...), jer ih test trazi u celom HTML-u.

### 10.7 Testovi (uslov 9, pravila upisa, sifarnik)

Samo postojece datoteke. Dva sacuvana rezultata u istom testu traze razlicita semena (`partija` je jedinstvena). Testovi ne zavise od pojedinacnih reci iz `0002`, osim `test_pocetni_sifarnik_normalizovan`; `TransactionTestCase` u `test_tok` posle prvog testa brise i podatke iz migracije, pa `test_tok` stavke upisuje sam, pre `goto`.

| Pravilo | Testovi |
|---|---|
| poeni i ocena sa servera; klijent salje samo ime | `test_prikazi.test_sacuvaj_200_poeni_i_ocena_iz_stanja`, `test_poeni_u_zahtevu_400` (i `ocena`; 0 redova) |
| oblik zahteva | `test_prikazi.test_sacuvaj_neispravan_zahtev_400` (subTest po redu tabele 10.3), `test_sacuvaj_prednost_400_nad_409` (i za `nepodobno_ime` bez igre) |
| ime | `test_prikazi.test_ime_pravila` (subTest. Prihvaceno: `А`, 20 cirilicnih, `Пера Перић`, 😀, 20 kodnih tacaka sa emoji, NFD Đorđe sacuvan kao NFC. Odbijeno: prazno, razmak, razmak na pocetku, razmak na kraju, 21 znak, `\n`, `\t`, U+200B, ZWJ U+200D i emoji 👩‍💻, U+00A0, U+202E, U+2028, `"\ud800"` kao sirov JSON, pocetni U+0301), `test_ista_imena_dozvoljena`, `test_full_clean_odbija_lose_ime`, `test_maxlength_jednak_ime_maks`; `test_motor.ImenaTests.test_ime_ispravno_tabela` (iste vrednosti, bez servera) |
| normalizacija | `test_motor.ImenaTests`: `test_s_iz_svih_pisama` (Ш, ш, Š, š, S, s → s), `test_digrafi` (Љ/Lj/ǉ → lj, Њ/Nj → nj, Џ/Dž/DŽ/ǆ → dz, Ђ/Đ/đ → dj), `test_c_i_z` (Ћ, Ч, Ц, ć, č → c; Ж, ž, З → z), `test_razmaci_i_interpunkcija` („П е-р.а“ → pera), `test_nfkd_oblici` (ＰＥＲＡ → pera, ß → ss), `test_samo_simboli_prazan_kljuc`, `test_idempotentno`, `test_imena_cist` (`ast`: bez uvoza Django-a, kao `test_motor_cist`) |
| poklapanje i odbijanje | `test_prikazi.SifarnikTests`: `test_nepodobno_ime_400` (stavka upisana kroz ORM; „Забрањено“, „ZABRANJENO“, „za branjeno“ → 400, 0 redova, bez upisa sesije), `test_rec_u_imenu_nije_odbijena` (200), `test_nepodobno_telo_bez_sadrzaja` (telo tacno `{"greska": "nepodobno_ime"}`), `test_sifarnik_ne_izlazi` (kljuc stavke nije ni u jednom odgovoru ni u HTML-u), `test_pocetni_sifarnik_normalizovan` (posle migracija bar 30 stavki; svaka neprazna i jednaka `kljuc_imena` same sebe) |
| komande | `test_prikazi.KomandeTests` (`call_command`, `stdout=StringIO`): `test_dodaj_upisuje_kljuc`, `test_dodaj_postojece_bez_greske`, `test_dodaj_prazan_kljuc_greska`, `test_dodaj_ispisuje_a_ne_brise_rezultate`, `test_dodaj_obrisi_rezultate`, `test_ukloni`, `test_ukloni_nepostojece_nista_ne_brise`, `test_rezultati_ispis_sa_id`, `test_rezultat_obrisi`, `test_rezultat_obrisi_nepostojeci_nista_ne_brise` |
| tacno jednom, i pod trkom | `test_prikazi.test_drugo_cuvanje_409_jedan_red`, `test_nova_posle_cuvanja_novi_upis`, `test_igra_nije_zavrsena_409` (stanje netaknuto), `test_sacuvaj_nema_igre_409`, `test_izgubljena_oznaka_409_jedan_red` (red sa istom `partija` upisan unapred, stanje bez oznake: tacno ono sto bi video drugi zahtev da je sesiju procitao pre upisa prvog), `test_sacuvaj_cita_i_upisuje_u_istoj_transakciji` (SAVEPOINT < citanje sesije < `INSERT INTO "igra_rezultat"` < upis sesije < RELEASE), `test_sacuvaj_200_tacno_jedan_upis_sesije`, `test_odbijeno_cuvanje_bez_upisa` (400 i 409); postojeci `test_rezim_transakcije_je_immediate`; `test_tok.test_dupli_klik_cuvanja_jedan_post` |
| redosled i 10 | `test_prikazi.test_redosled_poeni_pa_ranije` (ORM sa zadatim `sacuvan`), `test_isti_trenutak_po_redu_upisa`, `test_najvise_10` (11 redova) |
| datum | `test_prikazi.test_datum_beogradsko_vreme` (2026-11-09 23:30 UTC daje 10.11.2026; 2026-07-01 22:30 UTC daje 02.07.2026, letnje vreme i vodeca nula) |
| bez skrivenog | `test_nijedan_odgovor_ne_sadrzi_skriveno` prosiren odgovorima `sacuvaj` (200, 400, 409) i GET-om posle cuvanja; `test_rang_tacan_skup_kljuceva`; `test_rang_json_script_daje_recnik`; `test_partija_ne_izlazi` |
| isticanje | `test_prikazi.test_moj_posle_cuvanja_i_osvezavanja`, `test_moj_null_posle_nove`, `test_sacuvano_van_prvih_10` |
| CSRF, metoda | `test_prikazi.test_sacuvaj_bez_csrf_403`, `test_sacuvaj_get_405` |
| XSS | `test_prikazi.test_ime_xss_u_json_script` (ime `</script><b>x`: sirov HTML ga nema, parsiran `json_script` ga vraca doslovno); `test_tok.test_xss_kroz_ime` (redovi `<svg onload=a()>` i `<b>x</b>` upisani pre `goto`: tekst doslovan, `#rang [onload]` i `#rang b` nula, bez dijaloga i `pageerror`) |
| tok i ekran | `test_tok.test_cuvanje_i_lista` (prazna lista na prvom ucitavanju; cuvanje; istaknut red; osvezavanje; „Нова игра“ bez dijaloga: forme nema, red bez isticanja), `test_neispravno_ime_poruka` i `test_nepodobno_ime_poruka` (svaki dozvoljava tacno jedan 4xx u konzoli, zamka 7), `test_cuvanje_ne_skroluje` (375 px, `#rang-poruka` u vidnom polju) |
| R4, nova igra | **`test_tok.test_nova_posle_kraja_bez_potvrde` se zamenjuje**, jer posle R4 njegov rukovalac odbija dijalog, pa `expect_navigation` istekne. Umesto njega: `test_nova_posle_kraja_potvrda_dok_nije_sacuvano` (zavrsena partija bez cuvanja: odustajanje daje poruku `PITANJE_NOVA`, `#zavrsni` ostaje vidljiv, bez navigacije; prihvatanje vodi na „Круг 1 од 8“) i `test_nova_posle_cuvanja_bez_potvrde` (telo starog testa, uz cuvanje pre klika; `dijalozi == []`). `test_nova_usred_igre_potvrda` ostaje isti. |
| 375 px | `test_tok.test_375_rang_bez_prelivanja` (10 redova sa 20 × Ш i ocenom „одличан оркестратор“, plus forma; `JS_PRELIVANJE` na 320 i 375 px) |
| motor | `test_motor.RangMotorTests`: `test_za_cuvanje_iz_rezultata`, `test_za_cuvanje_nezavrsena`, `test_za_cuvanje_vec_sacuvano`, `test_oznaci_sacuvano_ne_menja_ulaz`, `test_oznaka_partije_stabilna_bez_semena`; `ParametriTests.test_konstante_rang` (20, 10) |

Pomocno u `test_tok`: `Zapis` dobija `zahtevi_cuvanja`; `otvori_zavrseno(seme)` upisuje zavrseno stanje (`odigraj_celu`) pre `goto`, bez 8 klikova; redove liste i stavke sifarnika test nit upisuje samo pre `goto` (zamka 4). `test_latinica_samo_u_nazivima` se ne menja: baza je u `test_tok` prazna, a novi tekst je cirilicom.
Prava trka dve niti nije stalni test: test baza je SQLite u memoriji sa deljenom vezom, gde cekanje na bravu ne radi kao na datoteci, pa bi test bio nepouzdan. Dokaz trke je u T1 (10.8).

### 10.8 Raspored, talasi, ugovor

| Datoteka | Agent | Talas |
|---|---|---|
| `igra/parametri.py`, `igra/motor.py`, `igra/imena.py` (nova), `igra/models.py` (nova), `igra/migrations/{__init__,0001_initial}.py` (`makemigrations`), `igra/migrations/0002_nepodobna_imena.py` (podaci; sadrzaj ceka pregled klijenta), `igra/management/{__init__,commands/__init__}.py`, `igra/management/commands/{nepodobno_dodaj,nepodobno_ukloni,rezultati,rezultat_obrisi}.py`, `igra/views.py`, `orkestrator/urls.py`, `orkestrator/settings.py` (samo `TIME_ZONE`) | backend-senior | T1 |
| `templates/igra/igra.html`, `static/igra/igra.js`, `static/igra/igra.css` | frontend-medior | T1 |
| `igra/tests/test_motor.py`, `test_prikazi.py`, `test_tok.py` | qa | T2 |
| (samo citanje) | security | T2 |

Redosled unutar backend-senior: `parametri`, `imena`, `models`, `0001`, `0002`, `motor`, `views`, `urls`, `settings`, komande.

| Faza | Dokaz da je gotova |
|---|---|
| implementacija, T1 | backend: `manage.py check` bez upozorenja; `makemigrations --check --dry-run` „No changes detected“ posle upisanih migracija; `migrate` na lokalnoj bazi i broj stavki sifarnika posle njega; `migrate igra 0001` pa ponovo `migrate` (obrnuti korak `0002` radi); `python -c "import zoneinfo; zoneinfo.ZoneInfo('Europe/Belgrade')"`; postojecih 125 testova prolazi (`test_summary.py` `EXIT=0`); svaka od cetiri komande pokrenuta jednom, sa ispisom u izvestaju; trka: skripta u scratchpad-u sa podesavanjima koja menjaju samo putanju baze na privremenu datoteku, `migrate`, `runserver` na slobodnom portu, 20 sesija sa zavrsenom partijom, po dva istovremena POST-a iza `threading.Barrier`; ocekivano uvek jedan 200 i jedan 409 `vec_sacuvano`, ukupno 20 redova; statusi ispisani u izvestaju. Frontend: pise prema ugovoru; rad u pregledacu dokazuje T2, a izvestaj to navodi kao nepokrenuto. |
| kontrolni skup, T2 | qa: `test_summary.py` `EXIT=0` (postojeci i novi); snimci na 375/768/1440 px zavrsnog ekrana sa formom i liste sa 10 redova. security: bela lista `_javni_rang`, `partija`, `id` i sifarnik ne izlaze, put imena do DOM-a (`json_script`, `textContent`, `<bdi>`), 400 pre citanja sesije, `IntegrityError` se ne guta. Sadrzaj sifarnika ne ocenjuju qa ni security; to radi klijent. |
| poruka klijentu | glavna sesija; uz izvestaj ide zahtev za pregled liste iz `0002`. |

Backend i frontend su nezavisni po datotekama jer je ugovor ispod zamrznut.

| Sta | Ime |
|---|---|
| URL | `"sacuvaj/"`, ime rute `sacuvaj` |
| Zahtev | `{"ime": str}` |
| JSON | `rang`: `lista`, `sacuvano`, `moj`; red: `ime`, `poeni`, `ocena`, `datum`; `greska`: `neispravan_zahtev`, `neispravno_ime`, `nepodobno_ime`, `nema_igre`, `igra_nije_zavrsena`, `vec_sacuvano` |
| Kontekst sablona | plus `rang`; `json_script` id `rang-lista` |
| DOM | `#rang-forma` (`novalidate`, `data-url-sacuvaj` iz `{% url 'sacuvaj' %}`, bez `method` i `action`: salje je samo skripta), `#rang-ime` (`name="ime"`, `maxlength="20"`, `autocomplete="nickname"`), `#rang-sacuvaj`, `#rang-greska`, `#rang-poruka`, `#rang`, `#rang-tabela`, `#rang-redovi`, `#rang-prazno`, `<template id="sablon-rang-red">`, sopstveni red `.rang-moj` + `aria-current="true"` |
| Skripta | zastita `uCuvanju`, odvojena od `uToku`; potvrda nove igre po 10.6 |
| Komande | `nepodobno_dodaj`, `nepodobno_ukloni`, `rezultati`, `rezultat_obrisi`; opcija `--obrisi-rezultate` |
| Ciste funkcije | `imena.ime_ispravno`, `imena.kljuc_imena` |

Promena iz ove tabele ide kroz glavnu sesiju.

### 10.9 Rizici i tacke bez povratka

| Rizik | Mera |
|---|---|
| `migrate` nije pokrenut na lokalnoj bazi: GET `/` daje 500 (nema tabele) | `migrate` je deo dokaza T1 |
| Tudji unos izvrsen u pregledacu | `json_script`, `textContent`, `<bdi>`; testovi XSS; security |
| `partija`, `id` ili sifarnik iscure | bela lista; `test_rang_tacan_skup_kljuceva`, `test_partija_ne_izlazi`, `test_sifarnik_ne_izlazi` |
| Lazni pogodak sifarnika (obicno ime jednako stavci posle normalizacije) | samo celo ime; klijent pregleda listu; stavka se uklanja komandom |
| Zaobilazenje sifarnika (cifre umesto slova, rec u duzem imenu) | prihvaceno: odluka je poklapanje celog imena; uklanja se `rezultat_obrisi` |
| Zaobilazenje sifarnika homoglifima (npr. cirilicno с umesto latinicnog c u `fuck`, ili р, х, у, в, н), jer se preslovljava po glasu, a ne po izgledu | prihvaceno (revizija 2026-11-10): uklanja se `rezultat_obrisi` |
| Nevidljivi i prazni znakovi (Hangul popunjivaci, prazan Braille, selektori varijante) i nagomilani kombinujuci znakovi | odbijaju se u `imena.py` (ispravka posle revizije 2026-11-10, R2) |
| Povratak migracije `0002` pa ponovni `migrate` vraca pocetne stavke koje je klijent uklonio | posle takvog povratka ponovo pokrenuti `nepodobno_ukloni` za uklonjene stavke |
| Lista nagradjuje srecu (nova igra usred partije) | prihvaceno u MVP 3 |
| Tabela raste bez granice | lokalno zanemarljivo; indeks pokriva upit za 10 najboljih |
| Cirilica u ispisu komande preusmerenom u datoteku na Windows-u | pokretati uz `PYTHONIOENCODING=utf-8`; testovi koriste `StringIO` |

**Tacke bez povratka:** `migrate` na lokalnoj `db.sqlite3` (u njoj su samo sesije; vraca se sa `migrate igra zero`, sto brise sacuvane rezultate i sifarnik). `nepodobno_dodaj --obrisi-rezultate` i `rezultat_obrisi` brisu sacuvane rezultate trajno; pokrece ih samo razvijalac, po nalogu korisnika. Odobrava korisnik potvrdom ovog plana; `migrate` pokrece backend-senior. Pocetni sifarnik odobrava klijent. Isporuke nema.

### 10.10 Odluke korisnika (bivsa pitanja R1-R4)

| # | Pitanje | Odluka | Posledica |
|---|---|---|---|
| R1 | Datum sa vodecom nulom ili bez? | Sa nulom, `%d.%m.%Y` (01.02.2026) | Jedan format u `_javni_rang`; test sa 02.07.2026 |
| R2 | Ime sa ZWJ i drugim nevidljivim znakovima? | Odbija se | Pravilo 5 u 10.4; 👩‍💻 u tabeli odbijenih |
| R3 | Brisanje neprikladnog imena? | Zamenjeno: sifarnik nepodobnih imena (poklapanje celog imena posle normalizacije) i rucne izmene kroz cetiri komande, bez admina i naloga | Drugi model, `igra/imena.py`, migracija sa podacima koja ceka pregled klijenta, komande i testovi (10.2, 10.4, 10.7) |
| R4 | „Нова игра“ na zavrsnom ekranu pre cuvanja: pitati? | Da, isti `window.confirm` dok rezultat nije sacuvan; posle cuvanja bez pitanja | `test_nova_posle_kraja_bez_potvrde` se zamenjuje sa dva testa (10.7) |

### 10.11 Dokumentacija posle izmene (predlog; planer je ne menja)

1. `projekat-odluke`, nova odluka (prva odluka od 2026-11-10 kaze „jedan model“): „## 2026-11-10 · Sifarnik nepodobnih imena / - Sukob: odluka ‚Rang lista trazi model‘ dozvoljava jedan model; moderacija imena trazi drugi. / - Odluka: `igra` dobija i model `NepodobnoIme` (normalizovan kljuc, jedinstven) sa migracijom sa podacima; izmene samo kroz management komande, bez admina i naloga. / - Odlucio: korisnik, 2026-11-10.“
2. `projekat-standardi`, pravilo 3, novi tekst: „**Dva modela, bez naloga.** Aplikacija `igra` ima modele `Rezultat` (rang lista) i `NepodobnoIme` (sifarnik) i njihove migracije; stanje partije je samo u sesiji. Rucne izmene idu kroz management komande, bez admina. Bez Docker-a, Nginx-a i MySQL-a. *Poreklo: odluke 2026-11-10 u `projekat-odluke`.*“
3. `projekat-standardi`, red tabele o prikazima: „Prikazi su funkcije: `pocetna` (GET), `potez` (POST, JSON), `nova` (POST), `sacuvaj` (POST, JSON) | cetiri tanka prikaza; motor racuna, `sacuvaj` jos upisuje `Rezultat` u istoj transakciji sa sesijom | stack-django: primeri u `views.md` su klase“.
4. `projekat-standardi`, novi redovi: „`igra/imena.py` je cist Python kao motor: pravila imena i `kljuc_imena` | testira se bez servera | nijedno“; „Datum za prikaz formatira prikaz, `%d.%m.%Y` u `TIME_ZONE = 'Europe/Belgrade'`; skripta ga samo ispisuje | isti datum u svakom pregledacu | nijedno“; „Rucne izmene podataka: komande `nepodobno_dodaj`, `nepodobno_ukloni`, `rezultati`, `rezultat_obrisi` | nema admina ni naloga | nijedno“. Red o testovima: `test_motor` pokriva i `imena`, `test_prikazi` i komande.
5. `projekat-domen`, pravilo 1, dodatak: „Rang lista nosi samo ime, poene, ocenu i datum; sifarnik nepodobnih imena nikad ne ide klijentu.“ Pravilo 3, dodatak: „Cuvanje rezultata nosi samo ime; poeni i ocena dolaze iz stanja; jednom po zavrsenoj partiji, drugi pokusaj je 409.“
6. `projekat-domen`, Tok igre, nova tacka 7: „Posle zavrsene partije igrac moze jednom da sacuva rezultat pod imenom od 1 do 20 znakova. Ime jednako stavci sifarnika posle normalizacije (velika i mala slova, cirilica i latinica, dijakritici, razmaci) se odbija jednom opstom porukom. Rang lista: 10 najboljih, vise poena iznad, kod jednakih ranije sacuvan iznad; ime, poeni, ocena, datum (10.11.2026). ‚Нова игра‘ pita za potvrdu usred partije i na zavrsnom ekranu dok rezultat nije sacuvan.“ Recnik: „rang lista | 10 najboljih sacuvanih rezultata“; „sifarnik | spisak nepodobnih imena, samo na serveru“.
7. `projekat-domen/references/parametri.md`, novi odeljak „Rang lista“: „Ime 1 do 20 znakova; prikazuje se 10 najboljih. Poreklo: zahtev klijenta, MVP 3 (2026-11-10).“
8. `MVP.md`, odeljak 3 „Rang lista“ (menja korisnik): sifarnik i potvrda nove igre na zavrsnom ekranu, jer `CLAUDE.md` trazi da su pravila u MVP-u i `projekat-domen` ista.
9. `CLAUDE.md`, raspored: `backend-senior` „motor, parametri, modeli, migracije, komande i prikazi“.

## 11. Deljenje rezultata (2026-11-10)

Status: **odluke D1 i D2 donete (11.10), izrada pocinje.**
Izvori: MVP 3 „Deljenje rezultata“, uslov 10; `projekat-odluke` 2026-11-10 „Deljenje rezultata trazi treci model“; postojeci kod (`views.sacuvaj`, `motor._javni_zavrsni`, `Rezultat.partija`).

**Odgovoreno (ne pita se ponovo):** treci model, nezavisan od rang liste, deljenje radi i bez imena; zapis nastaje na klik „Подели резултат“, jednom po partiji, ponovni klik (i posle osvezavanja) daje isti link; istek 30 dana posle nastanka, zatim poruka da rezultat vise nije dostupan; stari zapisi se brisu komandom; sadrzaj stranice (11.5); otvaranje linka ne pravi igru ni sesiju i ne menja igru posetioca.

### 11.1 Sta u odeljcima 1-10 vise ne vazi

| Odeljak | Bilo | Sada |
|---|---|---|
| 3, 10.1 | cetiri rute | sest: plus `"podeli/"` `podeli` i `"r/<str:token>/"` `deljeno` |
| 3, 6 | jedan sablon `igra.html` | dva sablona (`igra.html`, `deljeno.html`) i dva dela kroz `{% include %}` (`_ikone.html`, `_zavrsni.html`); izmena standarda u 11.12 |
| 5, 10.1 | dva izlaza ka klijentu | tri: plus `views._javni_deljeni`; njegov `zavrsni` prolazi belu listu `motor.deljeni_prikaz` |
| 5, 10.2 | stanje sa opcionim `sacuvan` | plus opcioni `podeljeno` (id reda `DeljeniRezultat`); `nova` ga brise jer pravi novo stanje |
| 6 skripta | `prikazi(stanje)` crta sve | plus grana `pokreniDeljeno` (deljena strana) i deljenje na zavrsnom ekranu (11.6) |
| 10.2, 10.8 | dva modela, migracije `0001`, `0002` | tri modela, plus `0003_deljenirezultat.py` |
| 10.4 | cetiri komande | sedam (11.8) |
| 10.6 | na zavrsnom ekranu samo forma rang liste | plus blok deljenja; potvrda „Нова игра“ (R4) se ne menja, jer deljenje nije cuvanje |
| 10.8 ugovor | | prosiren u 11.9 |
| 10.9 | „Tabela raste bez granice“ | vazi za `Rezultat`; `DeljeniRezultat` cisti `deljeni_ocisti` |

`pocetna`, `potez`, `nova`, `sacuvaj`, `javni_prikaz`, `_javni_rang` i `settings.py` se ne menjaju.

### 11.2 Model i motor

`parametri.py`: `DELJENJE_DANA = 30`, `DELJENJE_TOKEN_BAJTOVA = 16`, `DELJENJE_TOKEN_DUZINA = 22` (duzina `secrets.token_urlsafe(16)`; test to proverava).

```
class DeljeniRezultatQuerySet(models.QuerySet):
    def vazeci(self, sada):  return self.filter(istice__gt=sada)
    def istekli(self, sada): return self.filter(istice__lte=sada)

class DeljeniRezultat(models.Model):
    id      = models.BigAutoField(primary_key=True)
    token   = models.CharField(max_length=p.DELJENJE_TOKEN_DUZINA, unique=True, editable=False)  # jedino sto ide u URL
    partija = models.CharField(max_length=64, unique=True, editable=False)  # sha256 semena, isto kao Rezultat.partija; nikad u odgovoru
    zavrsni = models.JSONField()                                           # snimak motor.za_deljenje
    nastao  = models.DateTimeField(default=timezone.now, editable=False)  # UTC
    istice  = models.DateTimeField(editable=False)                        # nastao + DELJENJE_DANA; racuna prikaz
    objects = DeljeniRezultatQuerySet.as_manager()
    def istekao(self, sada) -> bool: return sada >= self.istice
    class Meta:
        indexes = [models.Index(fields=["istice"], name="igra_deljeno_istice_idx")]
        constraints = [CheckConstraint(condition=Q(istice__gt=F("nastao")), name="igra_deljeno_istice_posle"),
                       CheckConstraint(condition=~Q(token=""), name="igra_deljeno_token_nije_prazan")]
```

- **JSON, a ne posebna polja:** zavrsni ekran ima dve ugnezdene liste (tihe greske, lekcije); posebna polja traze dve tabele i spajanje za podatke po kojima se nikad ne filtrira. Snimak cuva tacno ono sto je igrac video. Kolone su samo ono po cemu se trazi: `token`, `partija`, `istice`.
- **Indeksi:** `token` i `partija` su jedinstveni, pa imaju svoje; `istice` za brisanje isteklih.
- **Token:** `secrets.token_urlsafe(p.DELJENJE_TOKEN_BAJTOVA)` u `views` (motor ne sme da uveze `secrets`): 128 bita iz OS izvora, 22 znaka `[A-Za-z0-9_-]`. Seme, `partija` i id nisu ulaz, pa iz tokena ne mogu da se izvedu i obrnuto. Jedinstvenost cuva `unique=True`; sudar je zanemarljiv (oko 2^-64 i pri 2^32 zapisa), pa bez petlje ponavljanja: `IntegrityError` koji nije zbog `partija` se ne guta.
- **Veza sa `Rezultat` za ime, bez FK (alternativa, jeftinija):** ime se cita pri GET-u, `Rezultat.objects.filter(partija=red.partija).values_list("ime", flat=True).first()`. Zasto: `sacuvaj` ostaje netaknut, ime se pojavljuje i kad je partija sacuvana posle deljenja, a nestaje kad ga `rezultat_obrisi` ili `nepodobno_dodaj --obrisi-rezultate` uklone. Obe kolone imaju jedinstven indeks.
- **Migracija** `0003_deljenirezultat.py` pravi `makemigrations igra`, bez rucnih izmena. `JSONField` na SQLite trazi JSON1; `manage.py check` bez `fields.E180` je dokaz u T1.

**Motor** (cist; bez novih uvoza):

```
za_deljenje(stanje) -> dict               # IgraNijeZavrsena; _javni_zavrsni(stanje["rezultat"])
deljeni_prikaz(snimak) -> dict            # _javni_zavrsni(snimak): ista bela lista i pri citanju; napomena iz parametri
podeljeni_red(stanje) -> int | None       # stanje.get("podeljeno"); stare sesije rade
oznaci_podeljeno(stanje, broj) -> dict    # kopija; ulaz netaknut
```

`_javni_zavrsni` radi i nad snimkom jer su kljucevi isti, a `_javno` nad vec zaokruzenim brojem ne menja vrednost; test to dokazuje (11.9).

### 11.3 `podeli`: POST `/podeli/`

Zaglavlje `X-CSRFToken` kao `sacuvaj`. Telo se ne cita (kao `nova`), pa klijent nista ne zadaje i nema 400.

| Status | Telo | Kada |
|---|---|---|
| 200 | `{"url": "http://127.0.0.1:8000/r/<token>/", "istice": "10.12.2026"}` | nov link, ili postojeci link iste partije |
| 409 | `{"greska": "nema_igre"}` | sesija bez igre |
| 409 | `{"greska": "igra_nije_zavrsena"}` | partija traje; stanje i tabela netaknuti |
| 409 | `{"greska": "deljenje_isteklo"}` | oznaka postoji, a red je istekao ili obrisan; novi link se ne pravi (jednom po partiji) |
| 403 | HTML Django strane | nema CSRF |
| 405 | prazno | nije POST (`@require_POST`) |

```
podeli:
  sada = timezone.now()
  with transaction.atomic():                          # BEGIN IMMEDIATE, kao sacuvaj
    stanje = session.get("igra")                      -> None: 409 nema_igre
    snimak = motor.za_deljenje(stanje)                -> IgraNijeZavrsena: 409 igra_nije_zavrsena
    broj = motor.podeljeni_red(stanje)
    ako broj nije None:
      red = DeljeniRezultat.objects.filter(id=broj).first()
      ako red je None ili red.istekao(sada): 409 deljenje_isteklo
      return 200 _odgovor_deljenja(request, red)      # bez upisa sesije
    partija = motor.oznaka_partije(stanje)
    red = filter(partija=partija).first()             # izgubljena oznaka: isti link; istekao -> 409 deljenje_isteklo
    ako red je None:
      red = DeljeniRezultat(token=secrets.token_urlsafe(...), partija=partija, zavrsni=snimak,
                            nastao=sada, istice=sada + timedelta(days=p.DELJENJE_DANA))
      red.full_clean(validate_unique=False)
      try: with transaction.atomic(): red.save()
      except IntegrityError: red = filter(partija=partija).first(); ako None: raise
    session["igra"] = motor.oznaci_podeljeno(stanje, red.id); session.save(); session.modified = False
    telo = _odgovor_deljenja(request, red)
  return JsonResponse(telo)
```

`_odgovor_deljenja`: `url` iz `request.build_absolute_uri(reverse("deljeno", args=[red.token]))`, `istice` kao `timezone.localtime(red.istice).strftime(FORMAT_DATUMA)`. Red i oznaka su u istoj transakciji; drugi istovremeni klik ceka bravu, cita oznaku i dobija isti link bez upisa. `deljenje_isteklo` je uz podrazumevani `SESSION_COOKIE_AGE` (14 dana od poslednjeg upisa sesije) prakticno nedostizan; test ga pravi kroz ORM.

### 11.4 `deljeno`: GET `/r/<token>/`

`@require_GET`, `@never_cache`. **Bez** `@ensure_csrf_cookie`, bez `request.session` i bez `{% csrf_token %}`: nema `sessionid`, `csrftoken`, reda u `django_session` ni `Vary: Cookie`.

```
deljeno(request, token):
  red = None
  ako re.fullmatch(r"[A-Za-z0-9_-]{22}", token):     # fullmatch: "$" bi propustio zavrsni "\n" (%0A)
    red = DeljeniRezultat.objects.vazeci(timezone.now()).filter(token=token).first()
  odgovor = render(deljeno.html, {"deljeno": None, "dana": p.DELJENJE_DANA}, status=404) ako red je None
            inace render(deljeno.html, {"deljeno": _javni_deljeni(red)})
  odgovor["Referrer-Policy"] = "no-referrer"; odgovor["X-Robots-Tag"] = "noindex, nofollow"
```

- **Istekao, nepostojeci i neispravan token daju isto:** 404 i isti bajtovi. Tako link ne odaje da li je token ikad postojao, a jedan tekst ispunjava MVP za istekao link. Ne `raise Http404`: uz `DEBUG = True` Django tada prikazuje tehnicku stranu sa spiskom ruta. Format tokena se proverava u prikazu, a ne u konverteru rute, iz istog razloga.
- **Zaglavlja:** `never_cache` daje `Cache-Control: max-age=0, no-cache, no-store, must-revalidate, private` (strana se menja kad se ime sacuva i kad link istekne). `SecurityMiddleware` vec salje `Referrer-Policy: same-origin` kroz `setdefault`, pa ga vrednost iz prikaza zamenjuje sa `no-referrer`. `X-Robots-Tag` i `<meta name="robots" content="noindex, nofollow">`. `X-Frame-Options: DENY` vec dolazi iz middleware-a.
- `_javni_deljeni(red) -> {"zavrsni": motor.deljeni_prikaz(red.zavrsni), "ime": str | None, "datum": "10.11.2026"}`, tacno tri kljuca, gradi se polje po polje; `datum` je `localtime(red.nastao)` (D1).

### 11.5 Pravilo 1 na deljenoj strani i u odgovoru

| Ulazi | Ne ulazi nikad |
|---|---|
| `zavrsni` po `KLJUCEVI_ZAVRSNOG`: poeni, ocena, ukupna cena i minuti, `budzet_prekoracen`, `rok_prekoracen`, tihe greske (krug, zadatak, dodatak cene i minuta), lekcije (tekst, odeljak), napomena; ime sa rang liste; datum | seme, `partija`, id, sansa, `tih` po zadatku, istorija, izbori i ishod po krugu, tezina, `poslednji`, `procene`, mere budzeta i roka, `nastao`/`istice` kao trenutak, oznaka `podeljeno` |

Token je samo u URL-u (strana ga ne ponavlja u telu). Odgovor `podeli` nosi samo `url` i `istice`. Tihe greske su javne posle kraja partije (odeljak 5, granica skriveno/javno), a MVP 3 ih trazi na deljenoj strani; rizik u 11.11.

### 11.6 Sabloni, skripta, izgled

| Sablon | Sadrzaj |
|---|---|
| `templates/igra/_ikone.html` (nova) | SVG sprite iz `igra.html`, premesten bez izmene |
| `templates/igra/_zavrsni.html` (nova) | `<section id="zavrsni">` i `<template>` `sablon-tiha`, `sablon-lekcija`, premesteni; forma rang liste i blok deljenja unutar `{% if not samo_citanje %}` |
| `igra.html` | `{% include %}` oba dela; blok deljenja u `#zavrsni`, posle `#rang-poruka` |
| `deljeno.html` (nova) | `<head>` kao u `igra.html` plus meta robots (dva pojavljivanja; izdvaja se tek kod treceg); `_ikone.html`; zaglavlje `.vrh` sa naslovom i podnaslovom; `#deljeno-podaci` (ime u `<bdi>`, datum); `{% include "igra/_zavrsni.html" with samo_citanje=True %}`; `#poruka`; link `#igraj-i-ti` (`href` iz `{% url 'pocetna' %}`, GET, bez forme); `{{ deljeno|json_script:"deljeni-rezultat" }}` samo na 200; `igra.js`. Na 404 samo naslov, tekst i `#igraj-i-ti`. |

**Skripta** (`igra.js`, ista datoteka, jer formatiranje broja i `nacrtajZavrsni` ne smeju da postoje dvaput):

```
pokreni(): ako postoji #deljeni-rezultat -> pokreniDeljeno(); kraj    # pre bilo kog el.nova/el.kontrole
pokreniDeljeno: JSON.parse u try; nije objekat ili zavrsni nije objekat -> poruka „Резултат није могао да се прочита.“
  inace nacrtajZavrsni(d.zavrsni); ime -> textContent u <bdi> (red sakriven ako null); datum -> textContent. Bez fetch-a i kolacica.
deli (klik #deli-dugme): ako uDeljenju -> kraj; uDeljenju = true; disabled
  fetch POST bez tela, X-CSRFToken; tekst pa JSON.parse (kao posalji)
  200 i url string -> #deli-link.value = url; #deli-rok; #deli-blok vidljiv; #deli-posalji.hidden = typeof navigator.share !== "function"
  409 po kodu -> poruka iz tabele; ostalo, mreza, nije JSON -> PORUKE.server
  finally: uDeljenju = false; dugme aktivno (ponovni klik daje isti link)
kopiraj: ako navigator.clipboard i window.isSecureContext -> await writeText(url) -> „Линк је копиран.“
  inace ili izuzetak -> rezerva: #deli-link.focus(); select(); poruka rezerve  (bez execCommand: zastarelo)
posalji: await navigator.share({title, text, url}); AbortError = igrac odustao, bez poruke (komentar u istom redu); ostalo -> rezerva
```

`http://localhost` i `http://127.0.0.1` jesu secure context; rezerva radi za `http` preko druge adrese, stariji pregledac i odbijenu dozvolu. URL ide samo u `value` polja i u `navigator.share`, nikad u `innerHTML` ni `href`.

**Izgled**, samo postojeci tokeni i komponente: deljena strana koristi istu karticu `.zavrsni` (`data-ocena` ton, `--poeni` prsten) i `.vrh`; „Подели резултат“, „Копирај линк“ i „Пошаљи“ su `.dugme .dugme-sporedno`, „Играј и ти“ `.dugme .dugme-glavno`; polje `.form-control` `readonly`; poruke koriste postojece `.rang-poruka`, `.rang-poruka-ok`, `.rang-poruka-info`; dugmad u `d-flex flex-wrap gap-2`, pa na 320 px idu jedno ispod drugog; ime `overflow-wrap: anywhere`. Nova boja nije potrebna. ID-jevi bez reci iz `ZABRANJENE_RECI`.

| Mesto | Tekst (doslovno) |
|---|---|
| dugme deljenja | Подели резултат |
| oznaka polja | Линк за дељење |
| rok | Линк важи до 10.12.2026. (datum iz `istice`) |
| dugme kopiranja / slanja | Копирај линк / Пошаљи |
| kopirano | Линк је копиран. |
| rezerva | Копирање није успело. Линк је означен; копирајте га ручно. |
| `deljenje_isteklo` | Линк за ову партију је истекао. |
| `igra_nije_zavrsena`, `nema_igre`, ostalo | postojeci `PORUKE.nijeZavrsena`, `nemaIgre`, `server` |
| `navigator.share` title / text | Оркестратор / Мој резултат у игри Оркестратор |
| deljena: `<title>` / podnaslov | Подељени резултат · Оркестратор / Подељени резултат |
| ime / datum | Играч: <ime> / Датум: 10.11.2026 |
| samo za citanje | Ово је завршена партија; овде се не може играти. |
| dugme | Играј и ти |
| 404: `<title>` / tekst / pomoc | Резултат није доступан · Оркестратор / Овај резултат више није доступан. / Линк за дељење важи 30 дана. (broj iz konteksta `dana`) |
| nije procitano | Резултат није могао да се прочита. |

### 11.7 Apsolutni URL

`request.build_absolute_uri(...)` uzima semu i host iz zahteva; `get_host()` proverava host prema `ALLOWED_HOSTS` (`localhost`, `127.0.0.1`, bez izmene), pa lazni `Host` daje 400 pre nego sto link nastane i link ne moze da pokazuje na tudji domen. Lokalno igrac dobija `http://127.0.0.1:8000/r/<22 znaka>/` ili `http://localhost:8000/...`, prema adresi kojom je otvorio igru; link radi samo na tom racunaru (D2). Testovi: Django klijent `http://testserver/r/...`, live server `http://localhost:<port>/r/...`. Pri isporuci (van MVP-a) trebaju `ALLOWED_HOSTS`, a iza proxy-ja `SECURE_PROXY_SSL_HEADER` i `USE_X_FORWARDED_HOST`, inace link nosi `http` ili unutrasnji host.

### 11.8 Komande

| Komanda | Ponasanje |
|---|---|
| `deljeni_ocisti` | Bez argumenata. U `transaction.atomic()` brise `istekli(timezone.now())` jednim `QuerySet.delete()` (model nema `delete()` ni signale, pa nista ne preskace; stack-django pravilo 2); ispisuje „obrisano isteklih: N“; ponovno pokretanje daje 0. |
| `deljeni [--token TOKEN]` | Ispis: id, nastao, istice, „vazi“ ili „istekao“, poeni, ocena, ime sa rang liste ili „-“. Token se ne ispisuje (ispis zavrsava u terminalu i logovima); `--token` nalazi red po linku koji je neko prijavio. |
| `deljeni_obrisi ID [ID ...]` | Kao `rezultat_obrisi`: ako ijedan id ne postoji, `CommandError` i nista nije obrisano; ispisuje obrisane. Link odmah daje 404; oznaka u sesiji ostaje, pa ta partija novi link ne dobija. |

Ispis i brisanje jednog reda: jedini nacin da se link povuce na zahtev bez admina, po obrascu `rezultati` i `rezultat_obrisi`. Mogu da se izostave bez uticaja na MVP (dve datoteke i cetiri testa manje). Rasporedjivaca nema: `deljeni_ocisti` se pokrece rucno; istekli, a neobrisani red se ionako ne prikazuje (`vazeci`).

### 11.9 Testovi, raspored, ugovor

Samo postojece datoteke. Vreme: queryset i model primaju `sada`; isticanje se zadaje kroz ORM (`nastao`, `istice` u proslosti); granica kroz `mock.patch("igra.views.timezone.now", return_value=T)`; bez spavanja. Pomocno u `test_prikazi`: `upisi_deljeno(stanje=None, nastao=None, istice=None)` (ORM, svaka svoja `partija`, kao `upisi_red`), `DELJENO_SCRIPT`, `deljeno_iz_html`, `PomocPrikaza.podeli(klijent=None)`, `KLJUCEVI_DELJENOG = {"zavrsni", "ime", "datum"}`, `KLJUCEVI_PODELI = {"url", "istice"}`, `OBLIK_TOKENA`. U `test_tok`: `Zapis.zahtevi_deljenja`, `OsnovaToka.podeli_i_cekaj(strana)`, `novi_kontekst(..., dozvole=None)`.

| Pravilo | Testovi |
|---|---|
| uslov 10: rezultat te partije | `test_prikazi.DeljenjeTests.test_podeli_200_url_i_istice` (`http://testserver/r/<token>/`, `istice - nastao == 30 dana`, jedan red), `DeljenaStranaTests.test_strana_iste_partije` (`zavrsni` sa strane == `javni_prikaz(stanje)["zavrsni"]`); `test_motor.DeljenjeMotorTests.test_deljeni_prikaz_jednak_javnom` (vise semena) |
| jednom po partiji | `test_ponovni_klik_isti_link` (jedan red, drugi zahtev bez upisa sesije), `test_posle_osvezavanja_isti_link`, `test_izgubljena_oznaka_isti_link`, `test_nova_posle_deljenja_nov_link`, `test_podeli_cita_i_upisuje_u_istoj_transakciji` (SAVEPOINT < citanje sesije < `INSERT INTO "igra_deljenirezultat"` < upis sesije < RELEASE) |
| odbijanje | `test_podeli_nema_igre_409`, `test_podeli_nezavrsena_409` (stanje i broj redova netaknuti), `test_podeli_isteklo_409` (subTest: istekao red, obrisan red), `test_podeli_bez_csrf_403`, `test_podeli_get_405`, `test_podeli_ne_cita_telo` (`{"poeni": 100, "token": ...}`: 200, poeni iz stanja), `test_deljenje_bez_imena` |
| istek | `DeljenaStranaTests.test_granica_isteka` (`istice` minus 1 µs: 200; tacno `istice`: 404), `test_istekao_i_nepostojeci_isti` (subTest: istekao, nepostojeci, 21 i 23 znaka, `%0A` posle vazeceg: 404 i isti `content` bajt po bajt); `DeljenjeModelTests.test_istekli_i_vazeci_granica`, `test_istice_posle_nastanka` (`IntegrityError`) |
| nepogodiv token | `test_token_nasumican` (`mock.patch("igra.views.secrets.token_urlsafe", wraps=...)` pozvan sa 16; `OBLIK_TOKENA`; nije podniz semena ni `partija`), `test_tokeni_razliciti` (20 sesija); `test_motor.ParametriTests.test_konstante_deljenje` (30, 16, 22 == `len(secrets.token_urlsafe(16))`) |
| bez skrivenog | `test_deljeno_tacan_skup_kljuceva` (`KLJUCEVI_DELJENOG`, `KLJUCEVI_ZAVRSNOG`, `KLJUCEVI_PODELI`), `test_deljeno_bez_skrivenog` (`skriveni_kljucevi(..., zavrsena=True)` prazan; u sirovom HTML-u nema semena, `partija`, id-a ni `ZABRANJENE_RECI`), `test_deljeno_json_script_daje_recnik`; `test_motor.test_deljeni_prikaz_bela_lista` (snimak sa dodatim `seme`, `izbori`, `ishod` na svakom nivou: izlaz bez njih); `test_nijedan_odgovor_ne_sadrzi_skriveno` prosiren odgovorima `podeli` i deljenom stranom |
| ime | `test_ime_posle_kasnijeg_cuvanja` (podeli, strana bez imena, `sacuvaj`, strana sa imenom), `test_ime_sacuvano_pre`, `test_ime_nestaje_posle_rezultat_obrisi` |
| sesija posetioca | `test_strana_ne_pravi_sesiju` (svez klijent: `odgovor.cookies` prazan, broj `Session` isti, „Cookie“ nije u `Vary`, nema `csrfmiddlewaretoken`), `test_strana_ne_menja_igru_posetioca` (posetilac usred igre: `session_data` i `expire_date` isti; zatim potez tekuceg kruga 200) |
| zaglavlja, metoda | `test_zaglavlja` (200 i 404: `no-store`, `private`, `no-referrer`, `noindex, nofollow`, meta robots), `test_deljeno_post_405` |
| XSS | `test_ime_xss_u_json_script` (`</script><b>x`); `test_tok.test_xss_kroz_ime_na_deljenoj` (`<svg onload=a()>`: tekst doslovan, `[onload]` nula, bez dijaloga i `pageerror`) |
| komande | `KomandeTests`: `test_ocisti_brise_samo_istekle` (minus i plus jedan dan), `test_ocisti_prazno`, `test_deljeni_ispis_bez_tokena`, `test_deljeni_po_tokenu`, `test_deljeni_obrisi`, `test_deljeni_obrisi_nepostojeci_nista_ne_brise` |
| motor | `DeljenjeMotorTests`: `test_za_deljenje_nezavrsena`, `test_oznaci_podeljeno_ne_menja_ulaz`, `test_podeljeni_red_bez_kljuca`; `test_motor_cist` i `test_nema_brojeva_u_motoru` bez izmene |
| tok (Playwright) | `test_tok.DeljenjeTokTests`: `test_podeli_kopiraj_otvori` (kontekst sa `clipboard-read`, `clipboard-write`; klik, `expect_response` 200; „Копирај линк“, poruka, `navigator.clipboard.readText()` == url; url u novom kontekstu bez kolacica: poeni i ocena isti, `context.cookies()` prazan; „Играј и ти“ vodi na „Круг 1 од 8“; `proveri_cisto`), `test_kopiranje_bez_clipboard` (init skripta uklanja `navigator.clipboard`: poruka rezerve, `document.activeElement.id == "deli-link"`, ceo tekst oznacen), `test_navigator_share` (lazni `share` belezi argumente; bez njega `#deli-posalji` skriven; `AbortError` bez poruke), `test_ponovni_klik_posle_osvezavanja_isti_link`, `test_istekao_link_poruka` (tacno jedan 404 u konzoli, zamka 7), `test_deljena_bez_prelivanja` (ime 20 × Ш, tri tihe greske, pet lekcija; `JS_PRELIVANJE` na `USKI_EKRANI`; i zavrsni ekran sa otvorenim blokom deljenja), `test_mreza_i_dom_bez_skrivenog` i `test_latinica_samo_u_nazivima` prosireni deljenom stranom |

**Raspored**

| Datoteka | Agent | Talas |
|---|---|---|
| `igra/parametri.py`, `igra/motor.py`, `igra/models.py`, `igra/migrations/0003_deljenirezultat.py` (`makemigrations`), `igra/views.py`, `orkestrator/urls.py`, `igra/management/commands/{deljeni_ocisti,deljeni,deljeni_obrisi}.py` (nove) | backend-senior | T1 |
| `templates/igra/{_ikone,_zavrsni,deljeno}.html` (nove), `templates/igra/igra.html`, `static/igra/igra.js`, `static/igra/igra.css` | frontend-medior | T1 |
| `igra/tests/test_motor.py`, `test_prikazi.py`, `test_tok.py` | qa | T2 |
| (samo citanje) | security | T2 |

Redosled unutar backend-senior: `parametri`, `motor`, `models`, `0003`, `views`, `urls`, komande.

| Faza | Dokaz da je gotova |
|---|---|
| implementacija, T1 | backend: `manage.py check` bez upozorenja (i bez `fields.E180`); `makemigrations --check --dry-run` „No changes detected“; `migrate`; `migrate igra 0002` pa `migrate`; postojecih 213 testova `EXIT=0`; skripta u scratchpad-u kroz Django klijent: dva POST `/podeli/` daju isti `url`, GET 200 sa ispisanim zaglavljima, nepostojeci token 404, broj `Session` pre i posle GET-a isti; svaka komanda pokrenuta jednom, ispis u izvestaju. frontend: **pre prve izmene** snimak HTML-a GET `/` sa zavrsenom partijom (seme 42) u scratchpad; pise prema ugovoru; rad u pregledacu dokazuje T2, a izvestaj to navodi kao nepokrenuto. |
| kontrolni skup, T2 | qa: `test_summary.py` `EXIT=0`; razlika GET `/` prema snimku frontenda je samo blok deljenja; snimci na 320/375/1440 px deljene strane i zavrsnog ekrana sa otvorenim blokom. security: bela lista `_javni_deljeni` i `deljeni_prikaz`, token iz `secrets` i nezavisan, strana ne dira sesiju ni CSRF kolacic, isti 404, put imena do DOM-a, `IntegrityError` se ne guta. |
| poruka klijentu | glavna sesija; uz izvestaj ide napomena D2 (link radi samo lokalno). |

Backend i frontend su nezavisni po datotekama jer je ugovor ispod zamrznut.

| Sta | Ime |
|---|---|
| URL | `"podeli/"` ime `podeli`; `"r/<str:token>/"` ime `deljeno` |
| JSON | `url`, `istice`; `greska`: `nema_igre`, `igra_nije_zavrsena`, `deljenje_isteklo` |
| Kontekst `deljeno.html` | `deljeno` (`zavrsni`, `ime`, `datum`) ili `None`; `dana`; `json_script` id `deljeni-rezultat` |
| Include | `igra/_ikone.html`; `igra/_zavrsni.html` sa `samo_citanje` |
| DOM igra | `#deli` (`data-url-podeli` iz `{% url 'podeli' %}`), `#deli-dugme`, `#deli-blok`, `#deli-link` (`readonly`), `#deli-rok`, `#deli-kopiraj`, `#deli-posalji`, `#deli-poruka` (`role="status"`) |
| DOM deljena | `#deljeni-rezultat`, `#deljeno-podaci`, `#deljeno-ime` (`<bdi>`), `#deljeno-datum`, `#zavrsni`, `#poruka`, `#igraj-i-ti`, `#nedostupno` |
| Skripta | `pokreniDeljeno`; zastita `uDeljenju`, odvojena od `uToku` i `uCuvanju` |
| Motor | `za_deljenje`, `deljeni_prikaz`, `podeljeni_red`, `oznaci_podeljeno`; kljuc stanja `podeljeno` |
| Komande | `deljeni_ocisti`, `deljeni` (`--token`), `deljeni_obrisi` |

Promena iz ove tabele ide kroz glavnu sesiju.

### 11.10 Odluke korisnika (2026-11-10)

Oba pitanja su odlucena po preporuci: D1 dan nastanka linka, oznaka „Датум:“ (u MVP-u „datum deljenja“); D2 link radi lokalno do isporuke, bez novih podesavanja.

| # | Pitanje | Odluka | Posledica |
|---|---|---|---|
| D1 | „Datum partije“: dan nastanka linka ili dan kraja partije? Stanje ne pamti vreme kraja (motor ne sme da cita sat). | Dan nastanka linka, kao sto rang lista prikazuje dan cuvanja; oznaka „Датум:“. | Partija podeljena danima posle kraja nosi dan deljenja. Dan kraja trazi upis vremena u `potez` (novi kljuc stanja, izmena toka koji cuvaju postojeci testovi). |
| D2 | Lokalno link radi samo na racunaru igraca (`127.0.0.1`), a MVP kaze „posalje drugome“. Prihvatljivo do isporuke? | Da, bez novog podesavanja; isporuka je van MVP-a. | Drugi racunar ne otvara link dok igra nije isporucena; pri isporuci `ALLOWED_HOSTS` i podesavanja proxy-ja (11.7). |

### 11.11 Rizici i tacke bez povratka

| Rizik | Mera |
|---|---|
| Novo polje snimka procuri | bela lista pri upisu i pri citanju (`_javni_zavrsni` oba puta); test skupa kljuceva; security |
| Tihe greske tudje partije govore posetiocu koji jos igra da zadaci 5, 6 i 8 mogu biti tihi | MVP 3 ih izricito trazi; isto zna svako ko je odigrao jednu partiju; prihvaceno |
| Token u istoriji pregledaca, u ispisu `runserver`-a ili kroz Referer | `no-referrer`, strana nema spoljnih resursa; komanda `deljeni` token ne ispisuje; ispis servera lokalno prihvatljiv |
| Premestanje sprite-a i zavrsnog ekrana u include promeni igru | razlika GET `/` prema snimku (T2) i postojecih 213 testova |
| Neograniceno pravljenje zapisa | svaki trazi celu partiju; `deljeni_ocisti`; lokalno zanemarljivo |
| Poredjenje tokena kroz indeks nije u konstantnom vremenu | 128 bita i SQLite lokalno: napad merenjem vremena nije izvodljiv; prihvaceno |
| `JSONField` bez JSON1 u SQLite | `manage.py check` u T1 |
| Posle rucnog povratka migracije (`migrate igra 0002`/`zero` pa `migrate`) oznaka `sacuvan` ili `podeljeno` u sesiji moze da pokaze na tudji red, jer AUTOINCREMENT krece od 1 | oznaka na red druge partije racuna se kao izgubljena (`views._sacuvana_partija`, `podeli` trazi po `partija`): igrac dobija samo sopstveni nov link ili cuvanje, nikad tudji red. Odstupa od „partija obrisanog reda se ne cuva / ne deli ponovo“ (10.4, 11.8) samo posle takvog povratka, koji pokrece razvijalac; prihvaceno (revizija 2026-11-10) |

**Tacke bez povratka:** `migrate` za `0003` na lokalnoj `db.sqlite3` (vraca se sa `migrate igra 0002`, sto brise sve linkove). `deljeni_ocisti` brise samo istekle; `deljeni_obrisi` trajno gasi vazeci link i pokrece ga samo razvijalac, po nalogu korisnika. Odobrava korisnik potvrdom ovog plana; `migrate` pokrece backend-senior. Isporuke nema.

### 11.12 Dokumentacija posle izmene (predlog; planer je ne menja)

1. `projekat-standardi`, pravilo 3, novi tekst: „**Tri modela, bez naloga.** Aplikacija `igra` ima modele `Rezultat` (rang lista), `NepodobnoIme` (sifarnik) i `DeljeniRezultat` (link za deljenje, 30 dana) i njihove migracije; stanje partije je samo u sesiji. Rucne izmene idu kroz management komande, bez admina. Bez Docker-a, Nginx-a i MySQL-a. *Poreklo: odluke 2026-11-10 u `projekat-odluke`.*“
2. `projekat-standardi`, red o prikazima: „Prikazi su funkcije: `pocetna` (GET), `potez` (POST, JSON), `nova` (POST), `sacuvaj` (POST, JSON), `podeli` (POST, JSON), `deljeno` (GET, samo citanje) | sest tankih prikaza; motor racuna, `sacuvaj` i `podeli` jos upisuju model u istoj transakciji sa sesijom; `deljeno` ne dira sesiju ni CSRF kolacic | stack-django: primeri u `views.md` su klase“.
3. `projekat-standardi`, red o sablonu: „Dva sablona: `templates/igra/igra.html` (igra) i `deljeno.html` (deljeni rezultat, samo citanje); zajednicki delovi `_ikone.html` i `_zavrsni.html` kroz `{% include %}` | zavrsni ekran izgleda isto na obe strane, bez kopije | nijedno“. Red o skripti: „`static/igra/igra.js`, bez biblioteka i bez koraka gradnje; ista skripta na obe strane, grana po `#deljeni-rezultat` | browser samo prikazuje stanje | nijedno“.
4. `projekat-standardi`, red o komandama: „Rucne izmene podataka: komande `nepodobno_dodaj`, `nepodobno_ukloni`, `rezultati`, `rezultat_obrisi`, `deljeni`, `deljeni_obrisi`, `deljeni_ocisti` | nema admina ni naloga | nijedno“.
5. `projekat-domen`, pravilo 1, dodatak: „Deljeni rezultat nosi samo zavrsni ekran, ime sa rang liste i datum; link je nasumican token, nezavisan od semena i partije.“ Tok igre, nova tacka 8: „Posle zavrsene partije igrac moze da napravi link za deljenje, jednom po partiji (ponovni klik daje isti link), nezavisno od rang liste. Link otvara stranu samo za citanje: zavrsni ekran, datum i ime ako je partija sacuvana; vazi 30 dana, posle toga strana kaze da rezultat vise nije dostupan.“ Recnik: „deljeni rezultat | snimak zavrsnog ekrana, dostupan linkom 30 dana“.
6. `projekat-domen/references/parametri.md`, novi odeljak „Deljenje rezultata“: „Link vazi 30 dana od nastanka. Poreklo: zahtev klijenta, MVP 3 (2026-11-10). Token: 16 nasumicnih bajtova iz `secrets` (128 bita), u URL-u 22 znaka base64url. Poreklo: odluka plana 2026-11-10; dvostruko iznad najmanje entropije identifikatora sesije koju trazi OWASP Session Management Cheat Sheet (64 bita).“
7. `MVP.md`, odeljak 3 „Deljenje rezultata“ (menja korisnik), ako se D1 prihvati: „datum partije“ postaje „datum deljenja“.
8. `CLAUDE.md`, raspored: `backend-senior` „motor, parametri, modeli, migracije, komande i prikazi“; `frontend-medior` „sabloni i skripta“.

## 12. Srpski i engleski (2026-11-11)

Plan je u posebnoj datoteci `plan-jezik.md` (odeljci 12.1-12.13).

## 13. Novo bodovanje (2026-11-11)

Plan je u posebnoj datoteci `plan-bodovanje.md` (odeljci 13.1-13.9).

## 14. Moderator (2026-11-11)

Plan je u posebnoj datoteci `plan-moderator.md` (odeljci 14.1-14.12).

## 15. Javna isporuka (2026-11-11)

Plan je u posebnoj datoteci `plan-isporuka.md` (odeljci 15.1-15.14).
