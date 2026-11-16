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
