# Diplomski: teorijski sistem agenata za izradu Django veb aplikacija

Primer kako se AI agenti organizuju, konfigurisu i vode pravilima. Sistem je
**teorijski**: pokazuje kako nesto treba da se radi, na Django radnom okviru.

Skillovi namerno NE ponavljaju ono sto model vec zna iz obucavanja ("koristi
ORM", "pisi citljiv kod"). Svaki sadrzi samo **zamke, odluke i dogovore** koje
model sam ne bi primenio, jer ih nauci tek kad nesto pukne.

## Struktura

| Folder | Sta je | Kada radi |
|---|---|---|
| `skills/` | pravila, u 4 sloja | ucitavaju se po potrebi |
| `agents/` | 14 uloga sa modelom, effort-om, alatima, skillovima | kada ih orkestrator pozove |
| `hooks/` | provere koje **sprovode** pravila | samo u projektu sa markerom, bez odluke modela |
| `scripts/` | merenje: potrosnja, buzet konteksta, evaluacije, ucinak, izvestaj po fazama | periodicno, rucno |
| `tools/` | deterministicki alati koji stede tokene | agent ih poziva umesto da sam broji |
| `tests/` | testovi hookova, faza i izvestaja (`python -m unittest discover -s tests`) | posle svake izmene hookova ili skripti |

## Licenca

GNU General Public License v3.0 (`LICENSE`). Biblioteke ukljucene u igre iz eksperimenta (npr. Bootstrap)
zadrzavaju svoje licence.

## Ostalo u ovom repou

| Fajl ili folder | Sta je |
|---|---|
| `Diplomski rad - … .docx` i `.pdf` | zavrsni rad (MEF Beograd), konacna verzija |
| `eksperiment/` | poredjenje praznog Claude Code-a i plugina: obe igre, upiti, rezultati, skripte provera; igre se pokrecu sa `eksperiment/pokreni.sh` (vidi `eksperiment/README.md`) |
| `Zapazanja iz poredjenja.docx` | radna beleska eksperimenta: sva merenja i zapazanja, runda po runda |
| `prezentacija/slike/` | grafici i snimci ekrana za odbranu |
| `MVP-orkestrator.md` | kratak opis igre, polazni dokument za obe strane |

## Ubacivanje u maticni folder

Plugin se ubacuje u `~/.claude/skills/diplomski`, kao `brain`, i koristi UMESTO brain plugina
u projektu igre Orkestrator. Folder u `~/.claude/skills/` sa `.claude-plugin/plugin.json`
Claude Code sam pronalazi pod imenom `diplomski@skills-dir`, bez `claude plugin install`.

### Koraci (PowerShell)

```
git clone C:\posao\diplomski "$HOME\.claude\skills\diplomski"
git -C "$HOME\.claude\skills\diplomski" remote remove origin
python "$HOME\.claude\skills\diplomski\scripts\novi_projekat.py" C:\posao\orkestrator-b
cd C:\posao\orkestrator-b
claude
```

`remote remove` je obavezan: `scripts/sync.py` bi inace na kraju sesije probao push u
`C:\posao\diplomski`. Klon ne nosi `.docx`, `.pdf` ni `izmene_v3_v4.diff`, jer nisu u git-u.
Od tog trenutka postoje dve kopije; plugin se menja u onoj u maticnom folderu.

### Provera da se ucitalo

Iz foldera projekta:

```
claude plugin list --json
claude plugin details diplomski@skills-dir
```

Ocekivano: `diplomski@skills-dir` ima `enabled: true`, `brain@skills-dir` ima `enabled: false`,
11 skillova, 14 agenata, 6 dogadjaja hookova. U sesiji: `/plugin`, `/agents`, `/hooks`.
Projektni skillovi `projekat-*` se vide u `/skills`. Posle prvog upita mora da postoji
`.claude/usage/prompts.jsonl`.

### Kako je brain iskljucen

Samo u tom projektu, u `.claude/settings.json` koji pise `novi_projekat.py`:

```json
{ "enabledPlugins": { "diplomski@skills-dir": true, "brain@skills-dir": false } }
```

Projektno podesavanje preovladjuje nad korisnickim, pa u svim ostalim projektima brain radi
kao i do sada. Tu je i `permissions.allow` za citanje stvarne lokacije plugina: podagent
nema alat Skill, pa skill van svog zaglavlja cita kao datoteku, a citanje van projekta je
inace odbijeno.

**Ostaje aktivno i u tom projektu**, jer ne pripada brain pluginu nego `~/.claude/settings.json`
i maticnom folderu: hookovi `pixel-agents`, statusna linija (skripta iz brain foldera),
`~/.claude/CLAUDE.md` i ostali skillovi iz `~/.claude/skills/`. Za merenje u odeljku 7.6 to
treba uzeti u obzir.

### Sta vazi za druge projekte

Hookovi su bez markera tih no-op, ali skillovi i agenti se vide svuda: po
`claude plugin details` to je oko 1.437 tokena u svakoj sesiji. Da bi plugin radio samo u
projektu sa markerom, u `~/.claude/settings.json` dodaj
`"enabledPlugins": { "diplomski@skills-dir": false }`; projektno `true` to preovladjuje.

### Merenje tokom izrade

```
python "$HOME\.claude\skills\diplomski\scripts\faza.py" planiranje
python "$HOME\.claude\skills\diplomski\scripts\izvestaj_faza.py"
```

Faza se upisuje pre pocetka svake faze. Izvestaj napravi cim se izrada zavrsi, dok su
transkripti na disku. Detalji: `scripts/README.md`.

### Izrada: prazan Claude Code prema pluginu

Igra se pravi dvaput, paralelno i pod istim uslovima, da bi odeljak 7.6 imao stvarno poredjenje.

```
python scripts\priprema_poredjenja.py C:\poredjenje
```

Dalje uputstvo je u `C:\poredjenje\POKRETANJE.md`.

| | Prazan | Plugin |
|---|---|---|
| Ko radi | Claude Code bez plugina i podesavanja, sa iskljucenim ugradjenim skillovima i podagentima | plugin, agenti po rasporedu ispod |
| Upiti i `MVP.md` | isti, bajt za bajt | isti |
| Pravila igre i standardi | samo `MVP.md` | `MVP.md` i `projekat-*` skillovi |
| Konfiguracija | sopstveni `CLAUDE_CONFIG_DIR` | sopstveni `CLAUDE_CONFIG_DIR`, sa snimkom plugina |
| Pokretanje | Claude ekstenzija u Cursor-u otvorenom kroz `prazan\otvori.cmd`; Opus, high, `acceptEdits` | isto, kroz `plugin\otvori.cmd` |
| Dokaz cistoce | `poredjenje.py provera`, iz stvarnog pokretanja | isto |

Prvi upit (`UPIT.txt`) trazi detaljan plan, a drugi (`UPIT-izrada.txt`) izradu, pa se planiranje
meri odvojeno i na strani koja nema upis faza. Izvor je [MVP-orkestrator.md](MVP-orkestrator.md). Merenje i ocena:

| Mera | Izvor |
|---|---|
| trajanje upita i rada, brzina | transkripti, `izvestaj_faza.py` |
| tokeni i cena po modelu | transkripti i `scripts/cene.json` |
| trosak planiranja i izrade, odvojeno | deli se po upitu za izradu |
| podpitanja coveku | `AskUserQuestion` i upiti posle prvog, bez propisane potvrde plana |
| da li testovi prolaze | `poredjenje.py` ih sam pokrece |
| kvalitet | covek, 8 kriterijuma, na anonimnim kopijama X i Y |

Raspored na strani sa pluginom; stoji i u `CLAUDE.md` projekta, a svaka faza pocinje upisom `faza.py`:

| Faza | Ko | Sta |
|---|---|---|
| planiranje | `planer` | plan i pitanja |
| delegiranje | glavna sesija | deli plan na talase |
| implementacija | `backend-senior`; `frontend-medior` | motor, parametri i prikazi; sablon i skripta |
| kontrolni skup | `qa`; `security`, svaki u svom kontekstu | testovi i pregledac; bezbednosna revizija |
| poruka klijentu | glavna sesija | kratak izvestaj |

Agenti `devops` i `translate` postoje, ali se u ovom primeru ne pokrecu. Testovi koriste
Django test runner, a Playwright i Django su vec instalirani; `pytest` nije potreban.

### Ponistavanje

```
Remove-Item -Recurse -Force "$HOME\.claude\skills\diplomski"
Remove-Item C:\posao\orkestrator-b\.claude\settings.json
```

Posle toga `claude plugin list --json` iz projekta pokazuje `brain@skills-dir` kao ukljucen.
Marker i `.claude/usage/` u projektu mogu da ostanu; bez plugina ih niko ne cita.

### Sta nije moglo da se testira

Uslov je bio da se `~/.claude` ne menja, pa:

| Nije testirano | Sta jeste |
|---|---|
| sesija sa modelom dok je plugin stvarno u `~/.claude/skills/diplomski` | `plugin list` i `plugin details` nad klonom u izolovanom `CLAUDE_CONFIG_DIR`; sesija sa modelom preko `--plugin-dir` |
| puna izrada u izolovanom `CLAUDE_CONFIG_DIR` | `plugin list` i `plugin details` nad pripremljenim okruzenjem, bez sesije sa modelom |
| pravilo citanja na stvarnoj lokaciji plugina | apsolutno pravilo za plugin na drugoj putanji |
| interaktivan rad: `/plugin`, `/agents`, `/hooks`, pitanja za dozvole | samo `claude -p` |
| agenti na modelima Sonnet i Opus | svi pozivi su bili Haiku |
| racun sa stvarnim transkriptom | prave cene u `cene.json`, racun proveren testovima nad primerom transkripta |
| `git pull` i `push` sa pravim remote-om | put bez remote-a |
| dugacke sesije sa sazimanjem konteksta i workflow agenti | kratke sesije, nastavak sesije, agent u prvom planu i u pozadini |

## Slojevi skillova (najsiri ka najuzem)

| Sloj | Folder | Vazi za |
|---|---|---|
| 1. Opsti | `skills/opsti-sloj/` | svaki jezik i svaki okvir |
| 2. Tehnologija | `skills/sloj-tehnologije/` | jednu tehnologiju (Django, Bootstrap) |
| 3. Spoj tehnologija | `skills/sloj-spoja-tehnologija/` | dve tehnologije zajedno (Django + MySQL) |
| 4. Projekat | `skills/sloj-projekta/` | jednu aplikaciju; **preovladjuje** nad svim iznad |

Tri pravila rasporedjivanja:

1. Pravilo ide u **najsiri sloj u kome je jos tacno**. Provera: da li bi vazilo u drugom repozitorijumu?
2. Isto pravilo **nikad na dva mesta**.
3. Izvedeni skill (npr. `django-detail-view`) **zamenjuje** skill iz koga je izveden; ne ucitavaju se oba.

## Agenti

| Uloga | Agent | Model | Effort |
|---|---|---|---|
| Planer | `planer` | opus | high |
| Orkestrator | `orchestrator` | opus | xhigh |
| UI/UX | `ui-ux` | opus | high |
| Dizajner | `designer` | sonnet | high |
| Frontend | `frontend-junior` / `-medior` / `-senior` | haiku / sonnet / opus | medium / high / high |
| Backend | `backend-junior` / `-medior` / `-senior` | sonnet / sonnet / opus | medium / high / xhigh |
| QA | `qa` | opus | high |
| DevOps | `devops` | opus | high |
| Security | `security` | opus | max |
| Prevodilac | `translate` | haiku | low |

Pravilo razreda: **ako je greska jeftina i ocigledna, sme nizi razred; ako je tiha, ostaje najvisi.**

## Instalacija preko marketplace-a (drugi nacin, sinhrono kroz git)

Ovaj nacin opisuje rad, a za izradu igre Orkestrator vazi odeljak "Ubacivanje u maticni
folder". Automatska sinhronizacija ispod radi samo u projektu sa markerom i samo ako repo ima remote.

Ovaj folder je **plugin** (`.claude-plugin/plugin.json`) i **lokalni marketplace**
(`.claude-plugin/marketplace.json`). Plugin iz lokalnog marketplace-a Claude Code
ucitava **sa mesta**: nista se ne kopira, pa `git pull` u ovom folderu odmah menja
pravila u svakoj sledecoj sesiji, na svakom racunaru.

Jednom po racunaru:

```
git clone <url-repozitorijuma> C:\posao\diplomski
claude plugin marketplace add C:\posao\diplomski
claude plugin install diplomski@diplomski
```

Posle toga sinhronizacija je automatska:

| Kada | Sta se desi |
|---|---|
| pocetak sesije | `git pull --ff-only` (hook `SessionStart`) |
| kraj sesije | `scripts/sync.py`: commit samo putanja pravila, `pull --ff-only`, `push` |
| oba racunara menjala | sync STAJE i kaze da se uradi `git pull --rebase` rucno |

**Kopira se samo sloj projekta, i to jednom:** `skills/sloj-projekta/*` je sablon.
Kopira se u `<projekat>/.claude/skills/` i od tada pripada projektu: sinhronizuje se
kroz git TOG projekta, sa svima koji rade na njemu.

Provera: `claude plugin validate C:\posao\diplomski`, pa u sesiji `/plugin` (plugin
"diplomski" ukljucen), `/agents`, `/hooks`.

## Koje putanje se kopiraju, a koje ne

| Deo | Gde zivi | Sinhronizuje ga |
|---|---|---|
| slojevi 1-3, agenti, hookovi, merenje, alati | ovaj repozitorijum (plugin) | `git` ovog repozitorijuma |
| sloj projekta | `<projekat>/.claude/skills/` | `git` projekta |
| licna podesavanja | `~/.claude/settings.json`, `.claude/settings.local.json` | ne sinhronizuje se |
