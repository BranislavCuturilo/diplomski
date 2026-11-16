# Plan izrade: igra Orkestrator

Izvor zahteva je `MVP.md`. Ovaj plan popunjava ono sto MVP u odeljku 8 namerno ostavlja otvoreno.
Ako se plan i MVP razlikuju, vazi MVP.

Okruzenje (provereno): Python 3.14.0, Django 6.0, Playwright 1.60.0, SQLite 3.50.4.

## 1. Odluke

### Potvrdjeno pitanjima

| Pitanje | Odluka | Posledica |
|---|---|---|
| Da li igrac vidi tezinu? | Ne, vidi samo naziv zadatka | Tezina se tretira kao skriven podatak iz pravila 1 i ne izlazi sa servera dok igra traje. |
| Sta se vidi pre poteza? | Mnozioci uz opcije | Model: cena $/M i mnozilac vremena. Nivo i podela: mnozilac tokena i vremena. Kontekst: mnozilac tokena. Bonusi i sansa se nikad ne salju. |

Ogranicenje koje ne moze da se ukloni: MVP trazi da igrac posle poteza vidi cenu i minute, a iz njih
i poznatih mnozilaca moze da se izracuna tezina odigranog zadatka. Tezina unapred ostaje skrivena.

### Tumacenja MVP-a

| # | Tema | Tumacenje | Razlog |
|---|---|---|---|
| 1 | Redosled na kraju | Prvo se dodaju troskovi tihih gresaka, pa se proverava prekoracenje. | Jedini redosled koji prolazi test balansa, videti odeljak 8. |
| 2 | Prekoracenje | Strogo vece: tacno 24 $ ili tacno 150 min nije prekoracenje. Svaka kazna se primenjuje najvise jednom. | Opus sa jednom doradom daje tacno 150 min. |
| 3 | Tihi neuspeh | Igrac je cenu vec platio jednom, kontrolni skup dodaje jos 3 puta (ukupno 4 puta). Minuti ukupno 2 puta. | Tekst kaze „dodaje se“. |
| 4 | Dorada | Vidljivi neuspeh ne ponavlja krug. Cena i minuti se dupliraju i igra ide na sledeci krug. | Igra uvek ima 8 krugova. |
| 5 | Poeni tokom igre | Ne prikazuju se, ni kazna -5. | Korak 3 toka igre nabraja sta igrac vidi. |
| 6 | Strategija „po tezini“ | Tezine 1 i 3 igraju sa „sam“. | MVP navodi 3 agenta samo za tezinu 2. |
| 7 | Stanje budzeta i roka | Moze da bude negativno i tada se prikazuje crveno. | Prekoracenje ne prekida igru. |
| 8 | Dupli klik | Dugme se zakljucava tokom zahteva. Ako drugi zahtev ipak stigne, dobija 409. | Spaja uslove 4 i 5 iz MVP-a. |
| 9 | Nova igra | Moguca samo kada nema partije u toku. U suprotnom se igrac vraca u postojecu partiju. | MVP: „nova igra posle zavrsene“. Sprecava i ponovno bacanje semena. |
| 10 | Tekst | Nazivi zadataka idu cirilicom (videti odeljak 6). CSS i CRUD ostaju latinicom kao tehnicki nazivi. | MVP, odeljak 6. |

### Napomena za tebe

MVP trazi trajnu recenicu „Цене и нивои размишљања су стварни подаци“, a tabela modela ima kolonu
„Cena igre $/M“. Recenicu prenosim doslovno i cene ne menjam. Nisam proveravao da li se te cene
poklapaju sa stvarnim cenovnikom, pa je vredi pogledati pre nego sto igru neko koristi kao nastavno
sredstvo.

## 2. Raspored datoteka

```
projekat/
  manage.py
  orkestrator/              podesavanja projekta
    settings.py
    urls.py
    wsgi.py
  igra/
    parametri.py            svi brojevi i tekstovi igre, jedino mesto
    pravila.py              ciste funkcije, bez Django-a
    models.py               Partija, Potez
    servis.py               partija iz sesije, odigravanje poteza, javni oblik stanja
    views.py
    urls.py
    migrations/
    templates/igra/         osnova.html, pocetak.html, igra.html, kraj.html
    static/igra/            igra.js, igra.css, bootstrap.min.css
    tests/
      test_pravila.py
      test_balans.py
      test_http.py
      test_tajne.py
      test_pregledac.py
```

Instalirane aplikacije su samo `sessions`, `contenttypes`, `staticfiles` i `igra`. Django admin se ne
ukljucuje jer bi bio jos jedan put do semena.

## 3. Pravila igre (`parametri.py`, `pravila.py`)

`pravila.py` ne zna za bazu, HTTP ni sesiju. Server i test balansa koriste iste funkcije.

| Funkcija | Ulaz | Izlaz |
|---|---|---|
| `racun_poteza` | krug, izbori | cena, minuti, sansa |
| `uspeh_kruga` | seme, krug, sansa | da ili ne, po formuli iz pravila 2 |
| `odigraj_krug` | seme, krug, izbori | status, vidljiva cena i minuti, vrsta ishoda |
| `vidljivo_stanje` | seme, lista poteza | stanje koje igrac sme da vidi |
| `konacni_rezultat` | seme, lista poteza | poeni, ocena, ukupna cena i minuti, tihe greske, lekcije |

Racun koristi `Decimal` napravljen iz stringova. Sa `float` vrednostima bi granica od 150 min mogla
da se predje zbog greske zaokruzivanja. Poredjenje sa budzetom i rokom ide nad tacnom vrednoscu, a
zaokruzuje se samo prikaz: cena na 3 decimale, minuti na najvise 2, sa decimalnim zarezom.

`konacni_rezultat` radi ovim redom:

1. Pocetak: 100 poena, cena i minuti iz svih krugova, sa dupliranim doradama.
2. Svaka dorada: -5 poena.
3. Svaki tihi neuspeh: cena + 3 x cena zadatka, minuti + minuti zadatka, -25 poena.
4. Ukupna cena > 24: -30. Ukupni minuti > 150: -20.
5. Poeni najmanje 0, zatim ocena i lekcije cije je uslov ispunjen (svaka najvise jednom).

## 4. Stanje partije

Partija se ne cuva kao gotov rezultat, nego kao seme i odluke. Sve ostalo se racuna iz njih, pa
nema dva izvora istine i pravilo 2 vazi po konstrukciji.

| Model | Polja | Napomena |
|---|---|---|
| `Partija` | `seme`, `napravljena` | Seme je `secrets.token_hex(16)`. |
| `Potez` | `partija`, `krug`, `model`, `nivo`, `kontekst`, `podela` | Ogranicenje jedinstvenosti nad (`partija`, `krug`). |

- Tekuci krug je broj poteza + 1. Partija je zavrsena kada ima 8 poteza.
- Sesija je u bazi (`django.contrib.sessions.backends.db`). Kolacic nosi samo ID sesije, a u sesiji je
  samo ID partije. Potpisane sesije u kolacicu se ne koriste jer bi to prekrsilo pravilo 1.
- Potez se upisuje u `transaction.atomic()`, a SQLite radi sa `transaction_mode: IMMEDIATE`, da
  istovremeni zahtevi ne dobiju „database is locked“. `select_for_update` na SQLite-u nema efekta, pa
  zastitu od duplog upisa daje ogranicenje jedinstvenosti: `IntegrityError` postaje 409.

## 5. URL-ovi i odgovori

| Metoda i putanja | Sta radi |
|---|---|
| `GET /` | Bez partije: pocetni ekran. Partija u toku: ekran igre. Zavrsena: preusmerava na `/kraj/`. |
| `POST /nova/` | Pravi partiju ako nema nijedne u toku, zatim preusmerava na `/`. |
| `POST /api/potez/` | Odigrava potez. |
| `GET /kraj/` | Zavrsni ekran. Dok igra traje, preusmerava na `/`. |

Zahtev za potez:

```json
{"krug": 3, "model": "haiku", "nivo": "high", "kontekst": "taman", "podela": "sam"}
```

Odgovor 200 ima ista polja i iste vrednosti za uspeh i za tihi neuspeh:

```json
{
  "krug": 3,
  "status": "готово",
  "cena": "0,018",
  "minuti": "2,5",
  "budzet_preostalo": "23,946",
  "rok_preostalo": "142,5",
  "budzet_prekoracen": false,
  "rok_prekoracen": false,
  "sledeci": {"krug": 4, "naziv": "CRUD прикази"},
  "zavrsena": false
}
```

Po zavrsetku 8. kruga `sledeci` je `null`, a `zavrsena` je `true`. Sve vrednosti formatira server, pa
JavaScript nista ne racuna.

Greske vracaju samo `{"greska": "<kratak tekst>"}`:

| Slucaj | Kod | Stanje |
|---|---|---|
| Telo nije JSON objekat, nedostaje polje, postoji visak polja (npr. `cena`) | 400 | netaknuto |
| `krug` nije ceo broj (string i bool se odbijaju) | 400 | netaknuto |
| Nepoznat izbor | 400 | netaknuto |
| Drugi broj kruga, zavrsena igra, nema partije u sesiji | 409 | netaknuto |

Prvo se proverava oblik zahteva (400), pa stanje (409). CSRF zastita ostaje ukljucena, a JavaScript
salje token u zaglavlju `X-CSRFToken`.

**Tajne (pravilo 1, prosireno tezinom):** seme, sansa, bonusi, oznaka tihog zadatka, ishod tihog
zadatka i tezina ne ulaze u HTML, JSON ni kolacic. Sablon i API dobijaju samo recnike koje pravi
`servis.py` po spisku dozvoljenih polja, nikad objekte iz `parametri.py`. Seme se ne salje ni posle
zavrsetka igre.

## 6. Ekrani

Bootstrap 5 CSS je lokalna kopija u `static/igra/`, preuzeta jednom, jer igra radi lokalno i bez
interneta. Bootstrap JS nije potreban. Sopstveni `igra.js` je obican JavaScript.

| Ekran | Sadrzaj |
|---|---|
| Pocetni | Kratko objasnjenje, budzet 24 $, rok 150 min, 8 krugova, dugme „Нова игра“. |
| Igra | Vrh: krug N/8, preostali budzet i rok. Sredina: naziv zadatka i cetiri grupe izbora sa mnoziocima. Dugme „Потврди“ je aktivno kada su izabrane sve cetiri grupe, bez podrazumevanog izbora. Ispod: rezultat poslednjeg poteza i istorija krugova. |
| Posle 8. kruga | Forma nestaje, ostaje rezultat poslednjeg kruga i dugme „Погледај резултат“. Provera je vec izvrsena na serveru, bez akcije igraca. |
| Zavrsni | Poeni, ocena, ukupna cena i minuti, spisak tihih gresaka, lekcije sa odeljkom rada, trajna recenica o parametrima, dugme „Нова игра“. |

Na uzanom ekranu grupe izbora idu jedna ispod druge, a dugmad ostaju dovoljno velika za dodir.
Izbori su radio dugmad sa natpisima, pa rade i tastaturom.

Nazivi zadataka: Превод почетне стране; Шаблон листе и форме; CSS и прилагођавање телефону;
CRUD прикази; Модел података и миграција; Провера права приступа; Аутоматски тестови;
Безбедносна ревизија.

Nazivi opcija: Haiku, Sonnet, Opus; low, high, max; мало, таман, све; сам, 3 агента, 50 агената.

Brzina je u MVP-u mnozilac minuta (manje je brze), pa ce na ekranu pisati „време ×0,5“.

## 7. Testovi

Sve se pokrece sa `python manage.py test`. Pretpostavlja se da je Playwright Chromium vec instaliran
(MVP, odeljak 9).

| Datoteka | Pokriva |
|---|---|
| `test_pravila.py` | Primeri racuna, ogranicenje sanse 5..99, ishodi, redosled kraja, granice 24 $ i 150 min, granice ocena, pod 0 poena, svaka lekcija sa uslovom i bez njega. |
| `test_balans.py` | 5.000 semena (`str(i)`), tri strategije, zahtevani poredak. |
| `test_http.py` | 200, 400 i 409 iz tabele, stanje netaknuto posle svake greske, dupli POST, isto seme i isti izbori daju isti zavrsni rezultat. |
| `test_tajne.py` | Posle svakog koraka partije HTML, JSON i kolacici ne sadrze seme ni zabranjena polja. Odgovor za tihi neuspeh je bajt po bajt jednak odgovoru za uspeh. `igra.js` nema parametre. |
| `test_pregledac.py` | Cela partija do zavrsnog ekrana i nova igra, dvoklik na „Потврди“, sirina 375 px bez horizontalnog klizanja, bez gresaka u konzoli. |

Playwright radi kroz `StaticLiveServerTestCase`, koji sam bira slobodan port. Sinhroni Playwright API
drzi aktivnu asyncio petlju, pa ti testovi postavljaju `DJANGO_ALLOW_ASYNC_UNSAFE=true`, inace Django
prijavljuje `SynchronousOnlyOperation`.

Veza sa uslovima iz MVP-a:

| Uslov | Test |
|---|---|
| 1. Cela igra u pregledacu | `test_pregledac` |
| 2. Isto seme, isti rezultat | `test_pravila`, `test_http` |
| 3. Bez skrivenih podataka | `test_tajne` |
| 4. Kodovi 409 i 400 | `test_http` |
| 5. Dupli klik | `test_http`, `test_pregledac` |
| 6. 375 px, konzola | `test_pregledac` |
| 7. Pokrivenost | svih pet datoteka |
| 8. Balans | `test_balans` |

## 8. Racunska provera balansa

Racunato rucno pre izrade, a test ce dati konacan broj.

| Strategija | Osnovna cena | Osnovni minuti | Jedan tihi neuspeh | Ocekivani poeni |
|---|---|---|---|---|
| po tezini | 15,82 $ | 109,5 | 28,78 $ i 139,5 min: samo kazna budzeta | oko 73 |
| sve Opus, high | 19,44 $ | 135 | 32,40 $ i 165 min: obe kazne | oko 68 |
| sve Haiku, low, malo | manje od 0,1 $ | 40,5 | nema prekoracenja | oko 21 |

Poredak iz MVP-a vazi: 73 > 68 > 21. Razlika izmedju prve dve strategije je oko 5 poena, a greska
proseka na 5.000 semena je ispod 1 poena.

Kada bi se prekoracenje proveravalo pre troskova tihih gresaka, rezultat bi bio oko 86 za „po tezini“
i oko 87 za „sve Opus“, pa bi se poredak obrnuo. Zato je tumacenje 1 obavezno.

## 9. Redosled izrade

Svaka faza se zavrsava proverom. Sledeca pocinje tek kada provera prodje.

| Faza | Posao | Provera |
|---|---|---|
| 1. Kostur | Django projekat, aplikacija `igra`, podesavanja, lokalni Bootstrap | `manage.py check` prolazi |
| 2. Pravila | `parametri.py`, `pravila.py`, `test_pravila.py`, `test_balans.py` | Testovi prolaze, poredak balansa vazi |
| 3. Model i API | Modeli, migracija, `servis.py`, pogledi, `test_http.py`, `test_tajne.py` | Testovi prolaze |
| 4. Ekrani | Sabloni, `igra.js`, `igra.css` | Rucna partija na slobodnom portu, bez gresaka u konzoli |
| 5. Pregledac | `test_pregledac.py`, popravke prikaza na 375 px | Testovi prolaze, pregled snimaka ekrana |
| 6. Zavrsna provera | Ceo `manage.py test`, prolaz kroz svih 8 uslova iz MVP-a | Svih 8 uslova ispunjeno |

Pravila idu pre svega ostalog jer je balans najveci rizik: ako ne prodje, menja se samo jedan modul.

Podela posla: sve radi jedan izvrsilac, redom. Faze su male i oslanjaju se jedna na drugu.

Lokalni server se pokrece na slobodnom portu koji se proveri pre pokretanja. Procesi koje nisam
pokrenuo se ne diraju, jer na racunaru moze da radi druga izrada. Git se ne inicijalizuje osim ako
to ne zatrazis.

## 10. Van ovog plana

Sve iz kolone „Van MVP-a“: nalozi, cuvanje rezultata, rang lista, vise jezika, isporuka na server,
nivoi tezine, animacije i zvuk.
