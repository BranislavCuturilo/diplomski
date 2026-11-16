## 13. Novo bodovanje (2026-11-11)

Status: **B1-B4 i N1 odgovoreni (N1-A: oznaka samo na redovima ranije verzije, korisnik 2026-11-11).** Brojevi u 13.5 su procena racunom.
Zahtev klijenta: tiha greska -35 (bilo -25); budzet -10 za svakih zapocetih 10% prekoracenja, najvise -50 (bilo -30 za svako); vazi od sada; igraci vec na rang listi ili sa podeljenim linkom ne smeju da se osete prevareno.
**Odgovoreno (ne pita se ponovo):** B1-B oznaka pravila na redu liste; B2-B partija se boduje po pravilima sa svog pocetka, motor nosi oba skupa; B3-A tacno 10% = 10 poena, granica 9 decimala; B4-B procenat i kazna budzeta na zavrsnom ekranu, stari snimci zadrzavaju stari tekst.
Ne menja se: dorada -5, rok -20, pocetnih 100, najmanje 0, pragovi ocena, budzet 24 $, rok 150 min. Sacuvani poeni i snimci se **nikad** ne preracunavaju.

### 13.1 Verzija pravila: ime i mesto

| Mesto | Oblik | Bez kljuca (staro) |
|---|---|---|
| `parametri.py` | `PRAVILA_STARA = 1`, `PRAVILA_TEKUCA = 2`, `KAZNE = {1: {...}, 2: {...}}` (ispod); brisu se `KAZNA_DORADA/TIHA/BUDZET/ROK` | - |
| stanje sesije | `stanje["pravila"]`: int; `nova_igra` upisuje `p.PRAVILA_TEKUCA` | `motor.pravila(stanje)` = `stanje.get("pravila", p.PRAVILA_STARA)`; jedino mesto koje cita kljuc |
| `motor.nadogradi` | stanje bez kljuca (zavrseno **i** nezavrseno) dobija kopiju sa `"pravila": 1`; idempotentno, ulaz netaknut; `None` ostaje `None` | zavrsenom starom stanju **ne** dodaje `kazna_budzet`/`budzet_procenat` |
| `stanje["rezultat"]` | novi kljucevi `budzet_procenat` (int, 0 bez prekoracenja) i `kazna_budzet` (int) | nema ih; javno `null` |
| `Rezultat.pravila` | `PositiveSmallIntegerField()` **bez** default-a (zaboravljen upis = greska, ne tiha pogresna oznaka); `CheckConstraint(reduce(or_, (Q(pravila=v) for v in range(p.PRAVILA_STARA, p.PRAVILA_TEKUCA + 1))), name="igra_pravila_poznata")`, SQL `"pravila" = 1 OR "pravila" = 2`; ne `__in` (rusi introspekciju, 0006) ni opseg (propusta 1.5, 0007) | migracija `0006_rezultat_pravila`: postojeci redovi 1; `0007_pravila_opseg`; `0008_pravila_nabrajanje` |
| `motor.za_cuvanje` | vraca i `"pravila": pravila(stanje)`; `views.sacuvaj` je vec prosledjuje kroz `**podaci` | stara zavrsena sesija sacuvana posle isporuke: red 1 |
| `DeljeniRezultat.zavrsni` | verzija **ne ide** u snimak: snimak ostaje tacno bela lista (`test_motor.py:1011-1056`), deljena strana oznaku ne prikazuje (13.3), a tekst kazne zavisi samo od prisustva `kazna_budzet` | `.get` u `_javni_zavrsni` |

```
KAZNE = {
    1: {"dorada": 5, "tiha": 25, "rok": 20, "budzet_po_koraku": 30, "budzet_korak_procenata": 10, "budzet_maks": 30},   # do 2026-11-11
    2: {"dorada": 5, "tiha": 35, "rok": 20, "budzet_po_koraku": 10, "budzet_korak_procenata": 10, "budzet_maks": 50},   # zahtev klijenta 2026-11-11
}
PROCENAT = 100
JEDINICA_POREDJENJA = 10 ** DECIMALA_POREDJENJA      # nano-dolar
```

Verzija 1 je ista formula: svako prekoracenje daje bar jedan korak, a `min(30 * koraci, 30)` = 30. Motor (`kontrolni_skup`, bez literala):

```
k        = p.KAZNE[pravila(stanje)]
preko_j  = round(cena * p.JEDINICA_POREDJENJA) - p.BUDZET * p.JEDINICA_POREDJENJA     # celi brojevi
budzet_prekoracen = preko_j > 0                                                        # jedan izvor
procenat = -(-preko_j * p.PROCENAT // (p.BUDZET * p.JEDINICA_POREDJENJA)) if preko_j > 0 else 0   # navise, ceo
kazna    = min(-(-procenat // k["budzet_korak_procenata"]) * k["budzet_po_koraku"], k["budzet_maks"])
poeni    = 100 - k["dorada"]*dorada - k["tiha"]*tihih - kazna - (k["rok"] if rok_prekoracen else 0), najmanje 0
```

Procenat na ekranu je isti ceo broj zaokruzen navise, pa se uvek slaze sa kaznom (prikazani 10 % uvek daje -10, 11 % daje -20). Proveravano racunom: 24,000000001 → 1 % / 10; 24,0024 (0,01%) → 1 % / 10; 26,40 → 10 % / 10; 26,4024 (10,01%) → 11 % / 20; 28,80 → 20 % / 20; 33,84 (41%) → 41 % / 50; 72 (200%) → 200 % / 50. Partija „po tezini“ sa jednom tihom greskom i jednom doradom na tezini 1 kosta tacno 28,80 $ (oko 6% takvih partija), pa je racun u celim brojevima obavezan.

### 13.2 Gde se kazne i poeni citaju pri prikazu (nalaz, nepromenjen)

Danas nijedno mesto ne prikazuje iznos kazne i nijedno ne preracunava poene. Kljucna mesta: `motor.py:142-153` (jedino citanje kazni), `motor.py:176-191` (`nadogradi` ne dira poene; tako i ostaje), `motor.py:199-206` + `views.py:285-291` (cuvanje iz sesije), `motor.py:310-329` (`_javni_zavrsni` indeksira direktno: novi kljucevi **samo** kroz `.get`, inace 500 za stare linkove `views.py:152-160` i stare sesije `motor.py:346`), `views.py:116-132` (rang iz baze), `_zavrsni.html:41`, `igra.js:295-304`. Iznos na ekranu dolazi samo iz snimka/stanja, nikad iz `parametri` pri prikazu.

### 13.3 Oznaka na rang listi

- **Javni oblik reda:** `{"ime", "poeni", "ocena", "datum", "stara_pravila"}`; `stara_pravila = red.pravila != p.PRAVILA_TEKUCA` (`views._javni_rang`). Bool, ne broj verzije: skripti ne treba znanje o verzijama.
- **Koji redovi:** samo redovi ranije verzije (preporuka N1-A). Novi redovi bez oznake.
- **Tekst (predlog, klijent pregleda):** oznaka sr „старо бодовање“, en "old scoring". Objasnjenje ispod tabele, vidljivo samo kad bar jedan red ima oznaku: sr „Старо бодовање: резултат је бодован по ранијим правилима, са другачијим казнама за тиху грешку и буџет.“, en "Old scoring: this result was scored under the earlier rules, with different penalties for silent errors and the budget."
- **Mesto:** u celiji „Оцена“, ispod teksta ocene, kao zaseban `<span class="rang-pravila" data-mesto="pravila" hidden>` (ocena prelazi u `<span data-mesto="ocena">`, jer `textContent` na celiji bi obrisao oznaku). Na 375 px celija je red 2, kolona `1fr` (`igra.css:1160-1163`, oko 215 px): oznaka u svom redu (`display: block`), `0.75rem`, boja `--c-tiho`; kolona poena (5rem) je preuska. Bez preloma reci i bez horizontalnog skrola (postojeca provera `test_tok.py:69`).
- **Pristupacnost:** znacenje nosi tekst, ne boja; citac cita „пожар старо бодовање“ u istoj celiji; objasnjenje je obican `<p id="rang-legenda">` posle tabele. Oznaka i objasnjenje su u sablonu (`{% translate %}`, kao „ваш резултат“), skripta samo menja `hidden`.
- **Deljena strana:** bez oznake. Pokazuje ono sto je igrac video; poredjenje sa drugima postoji samo na listi.

### 13.4 Tekst kazne na zavrsnom ekranu (B4-B)

- Prikazuje se samo kad je `budzet_prekoracen` i snimak nosi broj u `budzet_procenat` i `kazna_budzet`; inace ostaje postojece „Буџет је прекорачен.“ (stari linkovi, stare zavrsene sesije). Partija verzije 1 zavrsena posle isporuke dobija tacan iznos (-30).
- `msgid` (ngettext, broj je kazna): sr jednina „Буџет је прекорачен за %(procenat)s (−%(kazna)s поен).“, mnozina „Буџет је прекорачен за %(procenat)s (−%(kazna)s поена).“; en "Budget exceeded by %(procenat)s (−%(kazna)s point)." / "Budget exceeded by %(procenat)s (−%(kazna)s points)."
- `tekstovi.py`: `FORMATI[...]["procenat"]` = sr `"%(iznos)s" + NBSP + "%"`, en `"%(iznos)s%"`; `za_skriptu()["budzetKazne"]` = mapa `"kazna" → tekst` za svaku mogucu kaznu iz `p.KAZNE` (danas 10, 20, 30, 40, 50), oblik izabran na serveru kroz `ngettext`, `%(procenat)s` ostaje za skriptu. Kazna van mape: postojeca recenica.
- `_zavrsni.html:41`: dva `span`-a, `data-mesto="budzet-osnovno"` (postojeci tekst) i `data-mesto="budzet-iznos"` (prazan, `hidden`); skripta pri svakom crtanju bira jedan.

### 13.5 Balans (procena racunom; simulaciju radi talas 1)

Verzija 2: po tezini ~71,8; Opus samo za tihe ~73; sve Opus ~61,5; sve Sonnet ~48; sve Haiku low malo ~3. Obavezni poredak se cuva. Verzija 1 mora i dalje dati 72,8 / 68,0 / 20,8. **Stop uslov:** ako simulacija potvrdi „Opus samo za tihe“ iznad „po tezini“, glavna sesija pita korisnika pre talasa 2.
Test: `odigraj_celu(seme, strategija, pravila=None)` (posle `nova_igra` upisuje zadatu verziju); `BalansTests` racuna obe verzije, poredak za obe, srednje vrednosti v1 stare, v2 iz simulacije (delta 1,5). Semena se ne smanjuju; ako trajanje testa smeta, qa prijavljuje.

### 13.6 Dokumentacija (predlog; menja glavna sesija, MVP korisnik)

1. `projekat-domen` pravilo 1, nova recenica: „Rang lista nosi samo ime, poene, ocenu, datum i oznaku da je red bodovan po ranijim pravilima; sifarnik nepodobnih imena nikad ne ide klijentu.“ Tok igre 4: „-35 poena (pravila 1: -25)“; 5: „budzet -10 za svaki zapocet 10% prekoracenja, najvise -50 (pravila 1: -30 za svako); rok -20“; 6: „... ukupna cena i minuti, prekoracenje budzeta u procentima i njegova kazna, ...“. Nov odeljak „Verzije pravila“: „Partija se boduje po pravilima sa kojima je pocela (`pravila` u stanju; bez kljuca 1). Sacuvan red nosi verziju; red ranije verzije ima oznaku „старо бодовање“. Sacuvani poeni i snimci se ne preracunavaju.“
2. `projekat-odluke`, nova stavka:
   `## 2026-11-11 · Verzije pravila bodovanja` / Sukob: zahtev klijenta (novo bodovanje; stari rezultati ne smeju izgledati prevareno; B1-B) trazi oznaku pravila na redu liste, a `projekat-domen` pravilo 1 kaze „Rang lista nosi samo ime, poene, ocenu i datum“. / Odluka: `Rezultat.pravila` (1 do promene, 2 od 2026-11-11; postojeci redovi 1); red ranije verzije nosi vidljivu oznaku i objasnjenje ispod liste; partija se boduje po pravilima sa pocetka (B2-B); tacno 10% = 10, 9 decimala (B3-A); zavrsni ekran novih partija pokazuje procenat i kaznu budzeta, stari snimci ne (B4-B); poeni i snimci se ne preracunavaju. / Odlucio: korisnik, 2026-11-11.
3. `parametri.md`: odeljak „Kazne“ (tabela obe verzije, poreklo: izmisljeno; verzija 2 zahtev klijenta 2026-11-11) i nova tabela balansa za verziju 2 (stara ostaje uz oznaku „pravila 1“).
4. `MVP.md` 3: „Rang lista“ (+ oznaka), „Kontrolni skup i poeni“ (nove kazne, verzije); 7 uslov 9 (+ oznaka).

### 13.7 Talasi, agent po datoteci, dokaz

| Talas | Agent | Datoteke | Dokaz |
|---|---|---|---|
| 1 | backend-senior | `igra/parametri.py`, `igra/motor.py`, `igra/models.py`, `igra/migrations/0006_rezultat_pravila.py` (`AddField` sa `default=1, preserve_default=False`, `AddConstraint` sa literalom `[1, 2]`, kao `0005`), `igra/views.py` (`_javni_rang`), `igra/tekstovi.py` (13.4), `igra/management/commands/rezultati.py` (`pravila=` u `opis_reda`); `igra/tests/test_motor.py` (testovi T-M ispod); mehanicki u `test_prikazi.py` i `test_tok.py`: `pravila=` u svakom `Rezultat(...)`/`create` (oko 20), `KLJUCEVI_REDA`, `KLJUCEVI_ZAVRSNOG`, brojevi `:1014`, `:1176`, `:1884`, `:2075` (25 → 5) | ceo `test_summary.py` zelen; `makemigrations --check --dry-run`; ispis simulacije |
| 2 | frontend-medior | `templates/igra/igra.html` (sablon reda, `#rang-legenda`), `templates/igra/_zavrsni.html` (13.4), `static/igra/igra.js` (`jeRed`: `stara_pravila` bool ili odsutno = false; `nacrtajRang`; `nacrtajZavrsni`), `static/igra/igra.css` (`.rang-pravila`, legenda) | snimci 375 px i 1280 px, sr i en: lista sa starim redom, zavrsni sa prekoracenjem |
| 2 | translate | `locale/{sr,en}/LC_MESSAGES/django.po` i `.mo` (oznaka, objasnjenje, 13.4 sa 3 oblika za sr) | `makemessages` bez novih praznih `msgstr`; `compilemessages` |
| 3 | qa i security, jedna poruka | qa: testovi T-P i T-T; security: rang i zavrsni po beloj listi, nista novo pre kraja partije, `pravila` iz sesije ne moze da zada klijent | sazetak testova; nalazi |
| 4 | glavna sesija | 13.6 | razlika dokumenata |

Talas 2 posle talasa 1 (ugovor: `stara_pravila`, `budzet_procenat`, `kazna_budzet`, `budzetKazne`, `FORMATI.procenat`); frontend-medior i translate su isti talas.

**T-M (test_motor, backend):** tabela granica za obe verzije (24,0; 24,000000001; 0,01%; 10%; 10,01%; 20%; 40%; 41%; 200%: procenat i kazna; v1 uvek 0 ili 30); 28,80 sabrano u dva redosleda daje 20; prava partija „po tezini“ tacno 28,80 $ kroz `nadji_seme`; tiha po verziji (2 tihe: v1 50, v2 30); `nova_igra` nosi `PRAVILA_TEKUCA`; `kontrolni_skup` bira skup po stanju (isto seme, v1 25 i v2 5 za sve Opus sa jednom tihom); `nadogradi` (nezavrseno i zavrseno bez kljuca → 1, idempotentno, ulaz netaknut, bez novih kljuceva rezultata); `za_cuvanje` vraca verziju; `_javni_zavrsni` stari rezultat → `null`; `za_deljenje` i dalje jednak javnom; balans obe verzije; `test_nema_brojeva_u_motoru` i `test_motor_cist` bez izmene. Postojeci `PoeniTests` sa `sirovo_stanje` bez kljuca ostaju kao provera verzije 1.
**T-P (test_prikazi, qa):** red liste ima tacno 5 kljuceva; nov red `stara_pravila` false, red sa `pravila=1` true; `sacuvaj` nove partije upisuje 2; stara zavrsena sesija bez kljuca sacuvana posle isporuke → 1; stara nezavrsena sesija odigrana kroz `potez` do kraja → poeni verzije 1 i tekst -30; stari snimak bez novih kljuceva → `deljeno` 200, `null` u JSON-u; `budzetKazne` sr i en sa ispravnim oblikom; komanda `rezultati` ispisuje verziju; migracija `0006` napred (postojeci redovi 1, CHECK odbija 3 i NULL), nazad (kolona nestaje, poeni i ocena netaknuti), pa ponovo napred (svi 1, ocekivano, 13.9); `0004` nazad radi sa snimkom koji nosi nove kljuceve.
**T-T (test_tok, qa):** 375 px: stari red sa oznakom i objasnjenjem bez preliva; zavrsni ekran sa prekoracenjem sr i en; deljena strana starog snimka pokazuje samo „Буџет је прекорачен.“

### 13.8 Pitanja

B1-B4 odgovoreni (zaglavlje). Novo:

**N1. Koji redovi liste nose oznaku pravila** (odgovor B1 kaze „na svakom redu“, sto moze da znaci i oznaku na svim redovima)
- A. Samo redovi ranije verzije, „старо бодовање“ (**preporuka**): na 375 px manje teksta; oznaka nestaje sama kad stari redovi ispadnu iz prvih 10.
- B. Svi redovi: „старо бодовање“ / „ново бодовање“; trajno jedan red teksta vise po redu, i posle nestanka starih redova.

Talas 1 ne zavisi od N1 (server salje bool za svaki red); talas 2 ceka odgovor.

### 13.9 Rizici i tacke bez povratka

- **Tacke bez povratka:** (1) isporuka: od tada nove partije dobijaju verziju 2; (2) `migrate` za `0006` na pravoj `db.sqlite3`. Pre toga kopija `db.sqlite3` i ispis `rezultati`. Povratak (`migrate igra 0005`) brise kolonu, pa ponovni `migrate` oznacava **sve** redove kao 1, i redove verzije 2. Ispravka je rucna, iz sacuvanog ispisa. Odobrava korisnik, `migrate` pokrece backend-senior.
- `KAZNE[1]` ostaje dok postoji sesija bez kljuca ili verzije 1. Rok nije 14 dana: svaki potez produzava sesiju, pa nezavrsena partija verzije 1 moze da traje do oko 112 dana. Brisanje je posebna odluka, tek posle upita nad neisteklim sesijama. Revizija 2026-11-11 (nisko): CHECK je bio `sorted(p.KAZNE)` kao `IN (1, 2)`, sto je uz to rusilo SQLite introspekciju Django-a (nalaz qa). Ispravljeno migracijom `0007_pravila_opseg`: isti naziv `igra_pravila_poznata`, opseg `PRAVILA_STARA..PRAVILA_TEKUCA`, nezavisan od `KAZNE`. Opseg je na SQLite-u (tabela nije STRICT) propustao REAL 1.5, pa ga `0008_pravila_nabrajanje` zamenjuje sa `pravila = 1 OR pravila = 2` (granice i dalje iz `PRAVILA_STARA..PRAVILA_TEKUCA`).
- Novi kljuc citan bez `.get` obara stare linkove i sesije: test starog snimka i stare sesije (T-P).
- Ukupna cena na 2 decimale (`igra.js:301`): 24,004 $ pise „24,00 $“, a uz to „прекорачен за 1 % (−10 поена)“. Ostaje tako (B3-A).

Posle odgovora na N1: nova sesija za implementaciju.
