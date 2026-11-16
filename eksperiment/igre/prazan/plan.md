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
3. Svaki tihi neuspeh: cena + 3 x cena zadatka, minuti + minuti zadatka, -35 poena
   (pre izmene iz odeljka 14: -25).
4. Ukupna cena > 24: -10 za svakih zapocetih 10 % prekoracenja, najvise -50 (pre izmene: -30).
   Ukupni minuti > 150: -20.
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

Posle izmene bodovanja (odeljak 14) test daje: po tezini 71,64, sve Opus 61,15, sve Haiku 3,38.
Poredak vazi, a razlika izmedju prve dve strategije je narasla sa 5 na 10 poena.

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

Sve iz kolone „Van MVP-a“: nalozi igraca, jezici osim srpskog i engleskog, Docker, druga baza,
vise servera, nivoi tezine, animacije i zvuk.

## 11. Izmena: rang lista

Klijent je trazio cuvanje rezultata i rang listu. MVP.md je dopunjen (tok igre, korak 6, i uslov 9).

| Tema | Odluka |
|---|---|
| Model | `Rezultat`: `partija` (jedan-na-jedan, zato najvise jednom po partiji), `ime`, `poeni`, `ocena`, `sacuvan`. Poeni i ocena su snimak u trenutku cuvanja. |
| Zahtev | `POST /rezultat/` iz obicne forme, sa poljem `ime` i CSRF tokenom. Ostala polja se ignorisu, a poeni se uvek racunaju na serveru. |
| Ime | Uklanjaju se razmaci na krajevima, a niz razmaka postaje jedan. Mora imati od 1 do 30 znakova, bez kontrolnih znakova. Prikaz ide kroz automatsko escape-ovanje u Django-u. |
| Odgovori | Uspeh: preusmerenje na `/`, gde je red igraca istaknut. Neispravno ime: 400, zavrsni ekran sa porukom. Ponovno cuvanje: 409. Partija nije zavrsena ili ne postoji: 409. Stanje ostaje netaknuto. |
| Redosled | Poeni opadajuce. Pri istim poenima ide raniji rezultat. Ista mesta za iste poene (1, 2, 2, 4). Prikazuje se 10 redova. |
| Datum | Datum cuvanja, `dd.mm.gggg.`, po vremenu Europe/Belgrade. |
| Pocetni ekran | Prikazuje se i kada je partija u sesiji zavrsena, ne samo kada je nema. Do sada je `/` tada vodio na `/kraj/`, pa igrac nikad ne bi video rang listu. `/kraj/` i dalje radi dok igrac ne pokrene novu igru. |
| Tajne | Rang lista sadrzi samo zavrsene partije i nikad seme. Partija u toku nema red na listi. |
| Testovi | `test_rang_lista.py` (cuvanje, validacija, 400 i 409, redosled, 10 redova, ista mesta, datum) i provere kroz pregledac (cuvanje, dvoklik, 375 px). |

## 12. Izmena: deljenje rezultata

| Tema | Odluka |
|---|---|
| Model | `Partija.kod`: jedinstven, prazan dok partija traje. Pravi se pri prvom otvaranju zavrsnog ekrana kao `secrets.token_urlsafe(16)`. Upis ide uz uslov `kod IS NULL`, pa dva istovremena zahteva dobijaju isti kod. |
| Putanja | `GET /partija/<kod>/`. Nepoznat kod ili partija koja nije zavrsena: 404. Ostale metode: 405. |
| Zavrsni ekran | Odeljak „Подели резултат“: puna adresa u polju samo za citanje i dugme „Копирај“. Dugme se prikazuje samo uz JavaScript; bez njega se adresa oznacava i kopira rucno. |
| Podeljena stranica | Isti blok rezultata kao na zavrsnom ekranu (`_rezultat.html`): poeni, ocena, ukupna cena i minuti, tihe greske, lekcije i recenica o parametrima. Ime igraca se prikazuje ako je rezultat sacuvan. Jedino dugme je link „Играј и ти“ na `/`. |
| Bez nastavka igre | Stranica nema nijednu formu i ne cita ni ne menja sesiju posetioca. Posetilac sa svojom partijom u toku ostaje u njoj. |
| Tajne | Kod je nezavisan od semena i broja partije. Partija u toku nema kod, pa nijedan odgovor tokom igre ne sadrzi link. Stranica ima `noindex`. |
| Testovi | `test_deljenje.py` (kod, isti sadrzaj kao zavrsni ekran, bez formi i kolacica, 404 i 405, escape imena, partija u toku) i provera kroz pregledac (kopiranje, drugi posetilac, 375 px). |

## 13. Izmena: srpski i engleski

| Tema | Odluka |
|---|---|
| Nacin | Django i18n. Izvorni tekst ostaje srpski i on je `msgid`; engleski je u `igra/locale/en/LC_MESSAGES/django.po`. Tekst u `parametri.py` je oznacen sa `gettext_noop` i prevodi se tek pri prikazu u `servis.py`, pa cista pravila i test balansa ostaju netaknuti. |
| Alat | GNU gettext nije instaliran, pa `python manage.py prevodi` skuplja poruke iz sablona (Django `templatize`) i koda, dopunjuje `.po` i pravi `.mo` preko biblioteke polib. `--provera` samo proverava. |
| Pamcenje izbora | Kolacic `jezik`, godinu dana, HttpOnly, SameSite=Lax. Sesija i dalje cuva samo `partija_id`. Jezik pregledaca (Accept-Language) se ne koristi: podrazumevano je srpski. |
| Birac | Linkovi „SR“ i „EN“ na vrhu svakog ekrana: `GET /jezik/<sr|en>/?dalje=<putanja>`. Povratak samo na isti sajt, inace `/`. Obican link, pa podeljena stranica i dalje nema nijednu formu. Nepoznat jezik: 404. |
| Sta se prevodi | Sav tekst sablona, nazivi zadataka, statusi, opcije, ocene, lekcije, napomena, poruke gresaka (400 i 409) i tekst iz `igra.js` (sada dolazi iz `data-` atributa). Ocena na rang listi je sacuvana na srpskom i prevodi se pri prikazu. Ime igraca se ne prevodi. |
| Brojevi i datum | Srpski: decimalni zarez i `dd.mm.gggg.`. Engleski: decimalna tacka i `Nov 10, 2026`. Polja API-ja su ista na oba jezika. |
| Tajne | Provera skrivenih podataka i jednakosti odgovora za tihi neuspeh i uspeh radi na oba jezika; dodate su engleske reci (chance, probab, difficult, seed, silent). |
| Testovi | `test_jezik.py`: izbor i pamcenje, 404 i 405, povratak samo na isti sajt, promena usred partije, nijedan ekran ni odgovor na engleskom nema cirilicu (svi krugovi, sve lekcije, greske, podeljena stranica), katalog potpun i `.mo` azuran. U pregledacu: cela partija na engleskom na 375 px. |

## 14. Izmena: bodovanje

| Tema | Odluka |
|---|---|
| Nova pravila | Tihi neuspeh -35. Budzet: -10 za svaki zapoceti korak od 10 % prekoracenja (korak je 2,40 $), najvise -50. Tacno 10 % preko je jedan korak, 10,01 % su dva. Dorada, rok, ocene i sve ostalo ostaju isti. |
| Zasto verzija | Zavrsni ekran i podeljeni link racunaju poene iz semena i poteza svaki put. Bez verzije bi stari linkovi posle izmene pokazali nove, nize poene, a rang lista (koja cuva poene) bi se razisla sa linkom iste partije. |
| Verzija | `parametri.BODOVANJA` ima verziju 1 (staro) i 2 (novo); `BODOVANJE_TEKUCE = 2`. `Partija.bodovanje` se upisuje pri pravljenju partije i vise se ne menja. `pravila.konacni_rezultat` prima verziju, a `servis` uvek prosledjuje verziju partije. |
| Migracija | `0004_bodovanje`: postojece partije dobijaju 1, nove 2. Time stare zavrsene, sacuvane i podeljene partije zadrzavaju poene, a partija zapoceta pre izmene zavrsava se po starom, jer se pravila ne menjaju usred partije. |
| Rang lista | Cuva poene i ocenu iz trenutka cuvanja, pa se stari redovi ne menjaju. Stari i novi rezultati stoje na istoj listi. |
| Tajne | Verzija bodovanja se ne salje klijentu i nije skriven podatak iz pravila 1. Iznosi kazni se nigde ne prikazuju, pa nema novog teksta za prevod. |
| Testovi | `test_pravila.py`: novi iznosi i granice koraka (0, 0,0001 %, 10 %, 10,0001 %, 40 %, 40,04 %, 100 %), staro bodovanje daje stare poene, ostala pravila su ista u obe verzije. `test_bodovanje.py`: nova partija dobija verziju 2, stara partija ima iste poene na zavrsnom ekranu, linku i rang listi, stara partija u toku zavrsava po starom, migracija daje 1 postojecim partijama. |

## 15. Izmena: moderator

| Tema | Odluka |
|---|---|
| Nalozi | Django `auth`, samo za moderatore. Moderator je korisnik sa dozvolom `igra.moderira` i aktivnim nalogom; iskljucen nalog gubi pristup i u vec otvorenoj sesiji. Lozinka: PBKDF2 hes, najmanje 10 znakova, ne cesta, ne samo cifre, ne slicna imenu. |
| Prvi moderator | `python manage.py moderator <ime>`: lozinka se unosi dvaput kroz `getpass`. Ostale dodaje moderator na `/moderator/nalozi/`. Ime je jedinstveno bez obzira na velika i mala slova. |
| Prijava | `/moderator/prijava/`. Ista poruka za pogresno ime, pogresnu lozinku i nalog bez dozvole (400). Posle 5 promasaja za isto ime: 429 na 15 minuta (Django kes, u memoriji procesa). Prijava i odjava cuvaju `partija_id`, pa moderator moze i da igra. |
| Stranice | Rezultati (svi, po 25, sa mestom), Linkovi (svi deljeni linkovi, i bez sacuvanog rezultata), Dnevnik, Moderatori. Sve `never_cache` i `noindex`, na oba jezika. GET bez prijave vodi na prijavu, POST bez prijave je 403. CSRF na svakom POST-u. |
| Brisanje | GET prikazuje potvrdu, tek POST brise. Rezultat: red se brise iz `Rezultat`. Link: `Partija.kod` postaje prazan, pa `/partija/<kod>/` daje 404. Upis u dnevnik je u istoj transakciji. Ponovno brisanje: 404. |
| Konacnost | `servis` pre cuvanja rezultata i pre pravljenja koda proverava dnevnik u istoj (IMMEDIATE) transakciji, pa obrisano ne moze ponovo da nastane. Zavrsni ekran tada pokazuje poruku umesto forme ili linka. Brisanje rezultata ne gasi link (link tada vise ne pokazuje ime), a brisanje linka ne dira rang listu. |
| Dnevnik | Model `Dogadjaj`: vreme, moderator (prazno = razvijalac komandom), vrsta, partija, i snimak obrisanog (ime igraca, poeni, kod) ili ime naloga. Strani kljucevi su `PROTECT`, a sajt nema nijednu radnju koja menja ili brise upis. |
| Testovi | `test_moderator.py` (41): prijava, zakljucavanje, hes, pristup bez prijave, CSRF, brisanje i dnevnik, konacnost, nalozi, iskljucivanje, komanda, engleski bez cirilice. U pregledacu: ceo tok moderatora na 375 px. |

## 16. Izmena: javni server

Igra se pusta na https://orkestrator.example, za nekoliko hiljada igraca dnevno. Server postavlja
klijentov administrator po `deploy/UPUTSTVO.md`.

| Odluka | Izbor | Razlog |
|---|---|---|
| Podesavanja | `orkestrator/settings_produkcija.py` nasledjuje `settings.py`; tajne i putanje iz promenljivih okruzenja | Lokalni rad i testovi ostaju isti; server bez tajnog kljuca namerno ne krece. |
| Server | nginx (HTTPS, staticke datoteke, ogranicenje zahteva) → gunicorn, 3 procesa → Django | Uobicajen sklop za jedan Linux server; administrator ga lako odrzava. |
| Baza | ostaje SQLite, u WAL rezimu, sa IMMEDIATE transakcijama | Test opterecenja: oko 550 partija u minuti sa 3 procesa, bez gresaka. Potreba je nekoliko hiljada dnevno. |
| Kes | u bazi (`createcachetable`) | Brojac promasenih prijava moderatora je zajednicki za sve procese i prezivljava restart. |
| Staticke datoteke | `ManifestStaticFilesStorage`, nginx ih kesira godinu dana | Ime nosi hes sadrzaja, pa nova verzija nikad ne dobija staru datoteku iz kesa. |
| Bezbednost | HTTPS svuda, HSTS godinu dana (bez poddomena i preload liste), bezbedni kolacici, CSP u svim okruzenjima | Testovi u pregledacu rade sa istim CSP-om, pa bi prekrsaj pao kao greska u konzoli. |
| Stranice gresaka | `400.html`, `404.html`, `500.html` u izgledu igre, bez tehnickih detalja | Pravilo 1: ni pad ne sme da prikaze seme. |
| Odrzavanje | `manage.py odrzavanje` (istekle sesije, napustene partije starije od trajanja sesije) i `manage.py rezervna_kopija`, svake noci kroz systemd tajmer | Baza ne raste bez potrebe; kopija se pravi dok igra radi. Zavrsene partije se nikad ne brisu. |

Testovi su u `igra/tests/test_produkcija.py`. Produkciona podesavanja proveravaju se u posebnom
procesu sa sopstvenom bazom: `check --deploy` bez upozorenja, preusmerenje na HTTPS, odbijen tudji
domen, bezbedni kolacici i staticke datoteke sa hesom u imenu.

## 17. Izmena: prijava imena

Klijent je trazio da igrac moze da prijavi neprikladno ime sa rang liste, a da moderator vidi
prijavljena imena i odluci da li brise rezultat. MVP.md je dopunjen (odeljak „Prijava imena“ i uslov 15).

| Tema | Odluka |
|---|---|
| Model | `PrijavaImena`: `rezultat` (jedan-na-jedan), `podneta`, `resena`. Prijava je jedna po rezultatu. Ne pamti se ko prijavljuje (nema naloga, a adresa i sesija se ne cuvaju), pa broj prijava ne bi nista znacio, a tabela ne moze da ima vise redova nego sto ima rezultata. |
| Igrac | Zastavica na kraju svakog reda obe liste vodi na `GET /rezultat/<pk>/prijavi/`: stranica sa imenom i potvrdom. Tek `POST` prijavljuje i vraca na istu adresu, koja tada kaze da ime ceka pregled. Pocetni ekran zato nema novih formi, a slucajan dodir na telefonu nista ne prijavljuje. |
| Sta se prijavljuje | Samo rezultat koji je u tom trenutku medju 10 na glavnoj listi ili na listi danasnjeg dana; sve ostalo je 404. Igrac prijavljuje ono sto vidi, a skripta ne moze da prijavi sve rezultate iz baze i zatrpa moderatora. |
| Do odluke | Prijavljeno ime ostaje na rang listi. Nema automatskog skrivanja: prijave su anonimne, pa bi skrivanje posle N prijava bilo nacin da se tudji rezultat ukloni bez moderatora. |
| Moderator | `/moderator/prijavljena-imena/`: otvorene prijave, najstarija prva, po 25. Uz „Пријаве“ u meniju stoji broj otvorenih, na svakoj stranici moderacije. Dve odluke: „Обриши резултат“ (postojece brisanje sa potvrdom; `?odakle=prijave` posle brisanja vraca na spisak) i „Задржи“ (`POST /moderator/rezultat/<pk>/zadrzi/`). |
| Konacnost | Brisanje je konacno kao i do sada, a prijava nestaje sa rezultatom. Zadrzan rezultat se vise ne moze prijaviti: stranica prijave tada kaze da ga je moderator pregledao. Moderator ga i dalje moze obrisati sa spiska rezultata. Zadrzavanje bez otvorene prijave: 404. |
| Dnevnik | Zadrzavanje je nova vrsta dogadjaja (`zadrzan`), sa imenom i poenima; brisanje se belezi kao i do sada. Prijave igraca nisu u dnevniku, jer on belezi radnje moderatora. |
| Sesija i tajne | Stranica prijave ne cita i ne menja sesiju. U adresi je broj rezultata (ne partije ni kod linka); iz njega se ne dobija nista o semenu, a rezultati van liste se preko njega ne mogu otvoriti. Stranica ima `noindex`, a link `rel="nofollow"`. |
| Testovi | `test_prijava_imena.py`: potvrda pa prijava, jedna prijava po rezultatu, bez naloga i sesije, CSRF, 404 van liste i za jucerasnji dan, escape imena, obe odluke moderatora, dnevnik, pristup bez prijave moderatora, oba jezika. U pregledacu: ceo tok na 375 px, zastavica od 44 px. |

## 18. Izmena: kako se igra, zvuk, moje partije, statistika, JSON

Klijent je trazio pet stvari odjednom. MVP.md je dopunjen (opseg, pet novih odeljaka, uslovi 16 do 20).

### Zajednicka osnova: partija pamti igraca, kraj i poene (migracija 0008)

| Polje `Partija` | Znacenje |
|---|---|
| `igrac` | SHA-256 hes kljuca iz kolacica `igrac`; prazno za partije pre izmene. Sam kljuc se ne cuva, pa se iz baze ne moze napraviti tudji kolacic. |
| `zavrsena` | Vreme poslednjeg poteza. Upisuje se u istoj transakciji kao 8. potez. |
| `poeni` | Konacni poeni po bodovanju partije, isti racun kao zavrsni ekran. Posle se ne menjaju (bodovanje partije je stalno), pa su snimak, ne drugi izvor istine. |

Migracija postojecim zavrsenim partijama racuna poene i za `zavrsena` uzima vreme pocetka; `igrac`
ostaje prazan, pa one ulaze u statistiku, ali ni u ciju istoriju. Indeksi: (`igrac`, `-zavrsena`) i
`zavrsena`.

### Kako se igra

| Tema | Odluka |
|---|---|
| Adresa | `GET /kako-se-igra/`, link „Како се игра“ na pocetnom ekranu. Ne cita i ne menja sesiju; ista je za svakoga, i tokom partije. |
| Sadrzaj | Cilj; jedan krug u tri koraka sa svim opcijama i mnoziocima (isti `javne_opcije` kao ekran igre); tri ishoda; poeni, kazne i raspon svake ocene; sta postoji posle igre; napomena o parametrima. |
| Kazne | Prikazuju se, iz `BODOVANJA[BODOVANJE_TEKUCE]`. Do sada se nigde nisu prikazivale, ali nisu skriven podatak iz pravila 1, a bez njih pravila nisu potpuna. |
| Primer kruga | Izmisljen zadatak „Страница „О нама““ (tezina 2, nije medju osam), izbor Sonnet, high, taman, 3 agenta: 1,404 $ i 6 min, uz dorada 2,808 $ i 12 min. Racun ide kroz `pravila.racun_za_tezinu`, isti kao u igri, pa se primer menja sa parametrima. |
| Tajne | Pravi zadaci se ne navode, pa stranica ne otkriva koji je tezak ili tih. Sansa i bonusi se ne prikazuju. Igrac iz primera saznaje osnovu jedne tezine, sto je i do sada mogao posle prvog poteza (odeljak 1). |

### Zvuk

| Tema | Odluka |
|---|---|
| Izvor | Web Audio u `igra.js`, bez zvucnih datoteka: tri rastuca tona za „готово“, dva padajuca za „враћено на дораду“. Nema licenci ni novih datoteka, a CSP ostaje isti. |
| Pravilo 1 | Melodija se bira po statusu iz odgovora, pa tihi neuspeh zvuci kao uspeh. Server ne salje nista novo. |
| Dugme | Na ekranu igre, pored broja kruga, 44 px, `aria-pressed`. Bez JavaScript-a je skriveno. |
| Pamcenje | `localStorage` (`orkestrator-zvuk`), ne kolacic: serveru izbor ne treba. Podrazumevano iskljuceno, jer javni sajt ne treba da se cuje bez pitanja; klik na dugme je i dozvola pregledaca za zvuk i pusta kratku potvrdu. |

### Moje partije

| Tema | Odluka |
|---|---|
| Ko je igrac | Kolacic `igrac`: nasumican kljuc (32 znaka), HttpOnly, SameSite=Lax, Secure na serveru, godinu dana; svaka nova partija ga produzava. Sesija i dalje nosi samo `partija_id`, jer sesija istice posle 2 nedelje. Neispravan kljuc se zamenjuje novim. |
| Prikaz | Odeljak „Моје партије“ na pocetnom ekranu, samo kada ima bar jedne zavrsene: vreme zavrsetka, poeni, ocena, oznaka dnevnog izazova, sacuvano ime. Red je link na podeljen rezultat; za partiju ciji zavrsni ekran igrac nije otvorio link se pravi tada. Link koji je moderator obrisao se ne vraca, red tada nije link. |
| Granice | Najvise 10, najnovija prva. Partija u toku se ne prikazuje. Druge pregledace i obrisane kolacice igra ne moze da poveze, jer nema naloga. |

### Statistika

| Tema | Odluka |
|---|---|
| Adresa | `/moderator/statistika/`, stavka „Статистика“ u meniju moderacije; ista zastita kao ostale stranice moderatora. |
| Sta se broji | Zavrsene partije (obicne i dnevni izazov) po danu zavrsetka, po vremenu Europe/Belgrade; danas i 6 dana pre. Nezavrsene se ne broje jer nemaju poene. Dan bez partija: 0 i crtica. |
| Prosek | Iz `Partija.poeni`, jedna decimala, pola nagore. Red „Укупно“ je prosek svih partija perioda, ne prosek dnevnih proseka. Jedan upit sa `TruncDate`, bez ponovnog racuna partija. |

### Javna rang lista (JSON)

| Tema | Odluka |
|---|---|
| Adresa | `GET` ili `HEAD /api/rang-lista/`; ostale metode 405. |
| Oblik | `{"verzija": 1, "vreme": ISO 8601, "rang_lista": [...], "dnevna_lista": {"dan": "GGGG-MM-DD", "rang_lista": [...]}}`. Red: `mesto`, `ime`, `poeni`, `ocena` (`{"sr": ..., "en": ...}`), `sacuvan` (ISO 8601 sa zonom). Isti redovi kao na pocetnom ekranu (10, ista mesta). Isti odgovor na oba jezika. |
| Ugovor | Polja se ne uklanjaju i ne menjaju znacenje; za takvu izmenu raste `verzija`. |
| Tajne | Bez broja rezultata, partije, koda linka i semena. Ime je kako ga je igrac upisao; JSON ga ne menja, a partner ga escape-uje pri prikazu. |
| Zastita | Bez kolacica i sesije, `Access-Control-Allow-Origin: *`, `Cache-Control: public, max-age=60`. Nginx: 2 zahteva u sekundi po adresi, rezerva 20 (`deploy/nginx/orkestrator.conf`). |

### Testovi

| Datoteka | Pokriva |
|---|---|
| `test_kako_se_igra.py` | Link, sadrzaj, kazne i ocene iz parametara, primer jednak racunu igre, bez pravih zadataka i tajni, sesija netaknuta, 405, engleski bez cirilice. |
| `test_istorija.py` | Kolacic (hes u bazi, rok, zamena neispravnog), upis kraja i poena (i po starom bodovanju), redosled, 10 redova, tudje partije, dnevna i ime (escape), obrisan link, engleski, migracija 0008. |
| `test_statistika.py` | Pristup, meni, granica ponoci po beogradskom vremenu, 7 dana, prosek i ukupno, prazni dani, partija odigrana kroz igru, engleski. |
| `test_javna_rang_lista.py` | Oblik, mesta, samo danasnja dnevna lista, 10 redova kao pocetni ekran, zaglavlja, bez kolacica, bez tajni, ime, isti na oba jezika, GET/HEAD/405. |
| `test_pregledac.py` | Zvuk: podrazumevano iskljucen, pamti se posle osvezavanja, broj tonova prati vidljivi status. „Kako se igra“, moje partije i statistika na 375 px. |
| `test_tajne.py`, `test_produkcija.py` | Kolacic `igrac` je dozvoljen i bez semena; na serveru je Secure i HttpOnly. |
