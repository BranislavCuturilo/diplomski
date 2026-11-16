---
name: craft-delegiranje
description: >
  Kada se posao predaje podagentu a kada se radi sam, kako se pise zadatak i sta
  se radi sa izvestajem. Ucitaj PRE prvog pokretanja agenta i kada posao izgleda
  dovoljno sirok za paralelni rad. Okidaci: "podeli posao", "pokreni agente",
  "paralelno", "talas", "podagent", "delegiraj", "agent je vratio los rezultat".
---

# craft-delegiranje

Delegiranje nije besplatno: podagent krece od praznog konteksta, ponovo istrazuje
i vraca izvestaj koji neko mora da procita.

## Tri pravila koja se nikad ne preskacu

1. **Nezavisni poslovi idu u JEDNU poruku.** Pozivi u istoj poruci rade istovremeno,
   a u zasebnim porukama jedan za drugim, iako izgledaju isto. Prvo nabroji sve
   nezavisne delove, pa ih pokreni zajedno, najvise 3 po talasu. Redom ide samo
   stvarna zavisnost: B treba izlaz A.
   *Poreklo: merenje u sistemu brain, 172 od 235 pokretanja bila su pojedinacna, oko 1.264 s zidnog vremena.*

2. **Zadatak je jedino sto podagent zna.** Navedi cilj, tacne datoteke, dogovorena
   imena (URL, polja, sabloni) da se delovi slazu, sta je vec utvrdjeno i oblik
   izvestaja. Podagent nema alat Skill: za skill van njegovog zaglavlja navedi
   putanju datoteke da je procita.

3. **Izvestaj se prihvata, ili se posao ponavlja razred vise.** Ne radi isti posao
   ponovo u glavnoj sesiji. Rezultat kome se ne moze verovati znaci los zadatak ili
   preslab razred. Prenesi i sta podagent NIJE mogao da utvrdi.

## Laki put i pun aparat

**Laki put** je podrazumevan za svaku izmenu postojece aplikacije do oko 15 datoteka, bez obzira na
rizik: glavna sesija napise kratak plan sama (bez `planer`-a), uradi backend, sablone, skriptu i prevod
sama (bez talasa i bez `translate`), napise testove za nove rizike i pokrene ceo paket, pa pokrene
kontrolni skup.

**Pun aparat** (`planer`, talasi, `translate`) samo za novu aplikaciju, ceo novi jezik ili izmenu preko
oko 15 datoteka sa stvarno nezavisnim celinama.

## Paralelni rezim: 3 ili vise nezavisnih zadataka u jednom upitu

Nezavisan je zadatak kome ne treba izlaz drugog. Tada:

1. **Glavna sesija ne cita projekat.** Pokrene `python "<plugin>/tools/mapa.py" . --izlaz .claude/mapa.md`
   i cita mapu; datoteku otvara samo kada joj treba za ugovor.
2. **Osnova u git-u.** Radnik radi u worktree-u od poslednjeg commit-a, pa pre pokretanja: `git status`,
   `git add -- <putanje>` (ne `.` ni `-A`), `git commit -m "osnova pre paralelnog rada"`; bez repozitorijuma
   prvo `git init`.
3. **Jedan radnik po zadatku, svi u JEDNOJ poruci**, svaki sa `isolation: "worktree"` i modelom po
   zadatku: `sonnet` za uobicajen rad, `opus` samo za prijavu, prava, novac ili poene koji se cuvaju.
   Radnik je `backend-medior` (ceo zadatak: model, prikaz, sablon, skripta, prevod, testovi), ili
   `frontend-medior` kada zadatak ne dira server.
4. **Zadatak radnika:** cilj; odlomak mape koji mu treba; ugovor (imena ruta, polja i sablona koje
   koriste drugi zadaci); koje datoteke su samo njegove. Zajednicke (`urls.py`, katalog prevoda,
   `igra.css`, `igra.js`, osnovni sablon) dopisuje na KRAJ odgovarajuceg dela, ne prepravlja tudje.
   Migraciju pravi u svom worktree-u. Na kraju `test_summary.py --brzo` i commit svog rada u svojoj
   grani (`git add -- <putanje>`). Radnik ne zove druge agente.
5. **Spajanje radi glavna sesija**, granu po granu: `git merge --no-edit <grana>`. Dve migracije sa istim
   brojem: `makemigrations --merge`. Sukob u katalogu prevoda: zadrzi oba bloka, pa `makemessages` i
   `compilemessages`. Sukob u `urls.py`: zadrzi obe rute. Necommitovan rad radnika: commit u njegovom
   worktree-u (`git -C <putanja>`), pa spajanje.
6. **Jedna kontrola nad spojenim kodom:** ceo paket jednom, pa `security` (ako bilo koji zadatak dira
   rizik) i `qa` (ako se menja tok kroz pregledac) u jednoj poruci, sa spiskom svih izmenjenih datoteka:
   veze izmedju zadataka vidi samo kontrola nad celinom.

*Poreklo: poredjenje 2026-11-12, tri agenta u istom folderu dala su tri neslaganja; mapa projekta ima
oko 2.400 tokena, a projekat oko 13.000 redova.*

Rizik ne bira put, nego kontrolni skup: `security` ide kada izmena dira prijavu, prava, ulaz, novac ili
poene koji se cuvaju, semu sa podacima ili isporuku; `qa` ide uvek, u uzem obimu.

*Poreklo: poredjenje 2026-11-12, dnevni izazov: planer 5,6 min, talas 16,9 min uz 3 neslaganja
izmedju agenata, prevod 9 poruka 9,5 min; prazna sesija isto za 2,5 min, isti ishod provere.*

## Kontrolni skup posle izmene

- Agenti za proveru dobijaju spisak izmenjenih datoteka i proveravaju samo njih i ono sto od njih zavisi.
- Bezbednosnu reviziju pokreni samo ako izmena dira ulaz, sesiju, stanje, URL-ove, cuvanje podataka ili
  ono sto se salje klijentu. Izmena samo izgleda to ne dira.
- Ceo paket testova se pokrece uvek; on je jeftin, a pregled nije.
- `qa` se zove samo kada izmena dodaje ili menja tok kroz pregledac (nov ekran, forma, ponasanje
  skripte). Tada: ceo paket, testovi samo za nove rizike i JEDAN tok kroz pregledac; snimci na vise
  sirina samo kada se menja izgled. Za dugme, link ili izvoz `qa` se ne zove: glavna sesija pise
  testove i jednom pokrece ceo paket. *Poreklo: CSV izvoz, `qa` 7 min uz `security` 2 min.*
- Modeli: agenti nasledjuju model i nivo glavne sesije, osim `security`, koji ostaje jak jer je jedini
  nasao srednji nalaz u celom poredjenju.
- **Na doradu vracaju samo visoki i srednji nalazi.** Niski idu u izvestaj klijentu kao spisak.
- **Najvise jedna ponovna provera po upitu**, i ona gleda samo ispravljene nalaze. Ako i posle nje
  ostane visok ili srednji nalaz, stani i pitaj coveka; ne pokreci treci krug.

*Poreklo: poredjenje 2026-11-10 i 2026-11-12: provera je bila 49-66 % cene, a javni rad je posle
"gotovo" imao jos 6 krugova ispravki, vecinom zbog niskih nalaza.*

## Pitanja coveku

- Pitaj samo ono sto je nepovratno (brisanje, migracija na podacima, isporuka) ili se kosi sa tekstom
  klijenta. Sve ostalo odluci po svojoj preporuci i navedi u zavrsnoj poruci kao "Odluke za potvrdu".
- Najvise JEDAN dijalog pitanja po upitu, sa najvise 4 pitanja, pre izrade.
- Standard projekta nije razlog za pitanje: zahtev klijenta ga menja, a odluka se upisuje u
  `projekat-odluke`.

*Poreklo: poredjenje, 46 pitanja prema 4; oko 6 je postojalo samo zbog sukoba sa standardom projekta.*

## Kraj reda dok agenti rade

Dok bilo koji podagent radi, red se ne zavrsava porukom koja lici na kraj. Ako mora, prvi red
poruke je `RADI JOS: <agenti>`; sesija se sama nastavlja kada stigne izvestaj, i to pise u poruci.

*Poreklo: poredjenje 2026-11-12, covek je pitao "jel gotovo?" dok su agenti jos 75 min radili.*

## Ne delegiraj

- posao od nekoliko poziva alata;
- ponovno citanje sopstvene izmene (nezavisan pregled je nesto drugo);
- ono sto trazi istoriju razgovora;
- jedan mali posao iseckan da bi izgledao paralelno.

## Oblik izvestaja

Trazi zakljucak i mesto u kodu, nikad sadrzaj datoteka: izvestaj ostaje u kontekstu
glavne sesije do kraja rada.
