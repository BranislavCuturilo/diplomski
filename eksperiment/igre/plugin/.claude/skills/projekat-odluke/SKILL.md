---
name: projekat-odluke
nivo: 3
preovladjuje: [projekat-standardi, projekat-domen]
description: >
  Odluke korisnika za slucajeve u kojima se dva projektna skilla suprotstavljaju:
  kada agent naidje na sukob, stane i pita, a odgovor se upisuje ovde sa datumom i
  razlogom, pa sledeca sesija ne pita ponovo. Ucitaj zajedno sa projekat-standardi.
  Preovladjuje nad nivoom 2. Okidaci: "dva skilla kazu razlicito", "sukob pravila".
---

# projekat-odluke (nivo 3)

Svaka odluka nastaje kada agent naidje na sukob, stane i pita. Format:
datum, sukob, odluka, ko je odlucio. Odluka se ne menja bez novog pitanja.

## 2026-11-10 · Rang lista trazi model
- Sukob: zahtev klijenta (rang lista, MVP.md odeljak 2 vise je ne stavlja van opsega) trazi trajno cuvanje rezultata; `projekat-standardi` pravilo 3 kaze "bez modela i bez naloga, aplikacija `igra` nema svoje migracije".
- Odluka: aplikacija `igra` dobija jedan model za sacuvane rezultate i njegove migracije, u istoj SQLite bazi. Stanje partije ostaje u sesiji, kako pravilo 2 standarda kaze; nalozi i dalje ne postoje. Bez JSON datoteke kao skladista.
- Odlucio: korisnik, uz preporuku glavne sesije (bezbedno pri istovremenim upisima, proverljivo testom).

## 2026-11-10 · Sifarnik nepodobnih imena
- Sukob: odluka "Rang lista trazi model" dozvoljava jedan model; moderacija imena koju je korisnik izabrao (sifarnik nepodobnih imena uz rucno dodavanje i uklanjanje) trazi drugi.
- Odluka: `igra` dobija i model `NepodobnoIme` (normalizovan kljuc, jedinstven) sa migracijom sa podacima; pocetnu listu pripremamo mi, a klijent je pregleda. Odbija se samo ime koje je posle normalizacije jednako stavci. Izmene samo kroz management komande, bez admina i naloga.
- Odlucio: korisnik, 2026-11-10 (odgovori na pitanja o moderaciji).

## 2026-11-10 · Deljenje rezultata trazi treci model
- Sukob: zahtev klijenta (link sa rezultatom partije) trazi trajno cuvanje zavrsne slike partije; `projekat-standardi` pravilo 3 dozvoljava samo modele `Rezultat` i `NepodobnoIme`.
- Odluka: `igra` dobija treci model za deljeni rezultat, nezavisan od rang liste (deljenje radi i bez upisa imena). Zapis nastaje tek na klik „Подели резултат“, jednom po partiji; link istice 30 dana posle nastanka, a stari zapisi se brisu komandom. Nalozi i admin i dalje ne postoje.
- Odlucio: korisnik, 2026-11-10.

## 2026-11-11 · Engleska verzija
- Sukob: zahtev klijenta (srpski i engleski, ceo tekst na oba jezika) protivreci `projekat-standardi` ("Tekst na ekranu cirilicom") i `projekat-domen` ("Ceo tekst na ekranu je cirilicom"); MVP je "vise jezika" drzao van opsega.
- Odluka: srpski (cirilica) i engleski, standardni Django i18n sa `.po` katalozima i GNU gettext-om (instaliran sistemski 2026-11-11, `C:\Users\Bane\AppData\Local\Programs\gettext-iconv\bin`, verzija 1.0). Izbor se pamti u kolacicu jezika; novi posetilac dobija jezik pregledaca (engleski ako ga pregledac trazi, inace srpski). Baza cuva kljuceve, ne tekst (ocena, zavrsni ekran), pa rang lista i deljena strana idu na jeziku onoga ko gleda; postojeci zapisi se prevode jednom migracijom podataka. Ime igraca se ne prevodi. Engleski tekst pravimo mi; ocene, lekcije i trajnu napomenu klijent pregleda pre isporuke.
- Odlucio: korisnik, 2026-11-11.

## 2026-11-11 · Verzije pravila bodovanja
- Sukob: zahtev klijenta (novo bodovanje: tiha -35, budzet -10 po zapocetih 10%, najvise -50; stari rezultati ne smeju izgledati prevareno) trazi oznaku pravila na redu liste, a `projekat-domen` pravilo 1 kaze „Rang lista nosi samo ime, poene, ocenu i datum“.
- Odluka: `Rezultat.pravila` (1 do promene, 2 od 2026-11-11; postojeci redovi 1); samo red ranije verzije nosi vidljivu oznaku i objasnjenje ispod liste; partija se boduje po pravilima sa svog pocetka; tacno 10% = -10, racun u celim brojevima na 9 decimala; zavrsni ekran novih partija pokazuje procenat i kaznu budzeta, stari snimci ne; poeni i snimci se ne preracunavaju. Novi balans prihvacen: u pravilima 2 „Opus samo za tihe“ (72,7) je iznad „po tezini“ (71,6), obavezni poredak vazi.
- Odlucio: korisnik, 2026-11-11.

## 2026-11-11 · Moderator
- Sukob: zahtev klijenta (moderator se prijavljuje imenom i lozinkom, brise rezultat i deljeni link i vidi ko je sta obrisao i kada) protivreci `projekat-standardi` pravilu 3 („Tri modela, bez naloga ... bez admina“); MVP drzi naloge van opsega.
- Odluka: nalozi samo za moderatore, kroz `django.contrib.auth` (dozvole `igra.moderira` i `igra.upravlja_nalozima`, dodeljene direktno; bez admina, grupa i `createsuperuser`). Dve uloge: moderator brise rezultate i linkove, cita dnevnik i menja sopstvenu lozinku; glavni moderator jos dodaje, deaktivira i aktivira moderatore, postavlja im lozinke i dodeljuje i oduzima ulogu glavnog, uz potvrdu sopstvenom lozinkom. Uvek ostaje bar jedan aktivan glavni; niko ne deaktivira sebe. Pocetnu lozinku vlasnik menja pri prvoj prijavi. Prvog glavnog pravi razvijalac komandom `moderator_dodaj IME --glavni`; komande ostaju kao rezerva. Brisanje je tvrdo, i kroz komande; svako brisanje i svaka radnja nad nalogom ide u nepromenljiv dnevnik (`ZapisDnevnika`) sa snimkom {ime, poeni, ocena, datum}, bez tokena; dnevnik cuva i hes partije, da se obrisana partija ne sacuva ni ne podeli ponovo; cuva se 365 dana. Igraci nemaju naloge.
- Odlucio: korisnik, 2026-11-11 (M1 A, M2 B, M3 B, M4 B, N1 B; obe zastite potvrdjene).

## 2026-11-11 · Javna isporuka
- Sukob: zahtev klijenta (javno na https://orkestrator.example, nekoliko hiljada igraca dnevno; postavlja klijentov administrator po nasem uputstvu) protivreci CLAUDE.md (`django-nginx-docker` se ne koristi), `projekat-standardi` pravilu 3 (bez Docker-a i Nginx-a) i MVP 2 (isporuka van opsega).
- Odluka: Linux server sa Docker Compose (Nginx za TLS, staticke fajlove i ogranicenje brzine; gunicorn sa 4 radnika); SQLite u WAL modu ostaje; `settings_prod.py` uz `settings.py` za lokalni rad i testove; brojac neuspesnih prijava moderatora u bazi (sesti model `PokusajPrijave`, atomican upis), zajednicki svim procesima; Django 6.0.8 i sqlparse 0.6.0 pre isporuke; kod stize kao `git archive` iz lokalnog git repozitorijuma, pa kopije baze i zapisi upita ne ulaze u isporuku.
- Odlucio: korisnik, 2026-11-11 (P1 A, P2 A, P3 A, P4 A).

## 2026-11-12 · Dnevni izazov
- Sukob: zahtev klijenta (svakog dana svi igraju istu partiju; pocetni ekran pokazuje i rang listu dana) protivreci `projekat-standardi` pravilu 2 (stanje samo u `request.session["igra"]`), `projekat-domen` pravilu 2 (seme pravi server nasumicno; hes partije je sha256 semena, pa bi svi dnevni igraci imali isti hes i `Rezultat.partija` bi pustila samo prvog) i tok 7 (jedna rang lista).
- Odluka: dnevna partija je u drugom kljucu sesije `dnevna`; seme dana je `salted_hmac("igra.dnevni_izazov", dan.isoformat(), sha256)` (dan po Europe/Belgrade, nikad u HTML/JSON/kolacic); dnevno stanje nosi nasumicnu `oznaka`, a hes partije se racuna iz nje; `Rezultat.dan` (null = obicna igra), i dalje sest modela; lista dana je 10 najboljih sa `dan` = danas; jedna dnevna partija po sesiji i danu. Detalji i ostalih osam odluka: `PLAN-dnevni-izazov.md`.
- Odlucio: zahtev klijenta, 2026-11-12 (standard se menja bez pitanja, `projekat-standardi` pravilo 0). Odluke 1-8 iz plana cekaju potvrdu korisnika.

## 2026-11-12 · Prijava neprikladnog imena
- Sukob: zahtev klijenta (igrac prijavljuje neprikladno ime sa rang liste; moderator vidi prijavljena imena i odlucuje da li brise rezultat) protivreci `projekat-standardi` pravilu 3 (sest modela) i `projekat-domen` pravilu 1 (red rang liste nosi samo ime, poene, ocenu, datum i oznaku starih pravila: klijent nije imao cime da imenuje red).
- Odluka: sedmi model `PrijavaImena` (rezultat, HMAC kljuca sesije, trenutak; jedna po rezultatu i sesiji), migracija `0014`. Red liste dobija javnu oznaku `red` = HMAC partije (32 heks. cifre), nikad id. `POST prijavi/` sa `{"red": oznaka}`: 200 `{"primljeno": true}`, 400 `neispravan_zahtev`, 409 `nema_igre` ili `nije_na_listi`; prijaviti se moze samo red sa ekrana (10 najboljih glavne liste ili liste danas), iz sesije koja ima partiju; najvise 100 zabelezenih prijava po rezultatu. Prijava nista ne sakriva: odlucuje moderator, na strani „Преглед“ (odeljak „Пријављена имена“), brisanjem kroz postojecu potvrdu ili sa „Остави“ (`moderator/rezultat/<id>/ostavi/`, samo POST). „Остави“ ide kroz `brisanje.odbaci_prijave`: brise prijave i upisuje u dnevnik novu radnju `prijava_odbacena` sa partijom, pa se kasnije prijave istog rezultata ne beleze dok je zapis u dnevniku (365 dana); odgovor igracu je isti. Prijave liste ranijeg dana se brisu uz sledecu prijavu. Bez razloga prijave, bez obavestenja moderatoru, bez prijave sa deljene strane i bez upisa u sifarnik: to klijent nije trazio.
- Odlucio: zahtev klijenta, 2026-11-12 (standard se menja bez pitanja, `projekat-standardi` pravilo 0). Odluke po preporuci glavne sesije cekaju potvrdu korisnika: izbor imena ispod liste umesto dugmeta u svakom redu, isti odgovor za svaku primljenu prijavu, trajnost odluke „Остави“, granica 100, dnevnik za odbacenu prijavu.

## 2026-11-12 · Pravila igre, zvuk, istorija, statistika, javna lista
- Sukob: zahtev klijenta (strana „Kako se igra“, zvuk ishoda kruga, poslednjih 10 partija igraca, statistika za moderatora, javna adresa sa rang listom u JSON-u) protivreci MVP 2 (zvuk van opsega; igraci bez naloga), `projekat-standardi` pravilu 3 (sedam modela) i standardu „dva sablona“; danas se zavrsena partija koja nije sacuvana nigde ne belezi.
- Odluka: (1) treci sablon `kako.html` na `kako-se-igra/`, bez sanse, oznake `tiha` i spiska tihih zadataka; primer kruga racuna motor. (2) Zvuk iz Web Audio API-ja, bez datoteka, podrazumevano iskljucen, izbor u `localStorage` pregledaca; zvuk zavisi samo od javnog statusa, pa uspeh i tih neuspeh zvuce isto. (3) „Svojih“ = ovaj pregledac: najvise 10 zavrsenih partija u kljucu sesije `istorija`, bez modela; nestaje sa sesijom (14 dana bez igre) i brisanjem kolacica. (4) Osmi model `ZavrsenaPartija` (dan, vrsta, poeni; bez imena i sesije) belezi svaku partiju koja stigne do zavrsnog ekrana; strana `moderator/statistika/` pokazuje 7 dana; brojanje pocinje od isporuke. (5) `api/rang-lista/`: glavna i danasnja lista, ista polja kao na strani (kljuc ocene, ISO datum), bez id-a i oznake reda; bez kljuca, CORS `*`, kes 60 s, posebna zona brzine u Nginx-u.
- Odlucio: korisnik, 2026-11-12 (istorija: ovaj pregledac; statistika: svaka zavrsena partija); ostalo po preporuci glavne sesije, ceka potvrdu.

## Sablon za novu odluku

```
## <datum> · <kratak naziv>
- Sukob: <skill A> kaze ..., <skill B> kaze ...
- Odluka: ...
- Odlucio: ...
```
