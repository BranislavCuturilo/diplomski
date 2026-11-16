# -*- coding: utf-8 -*-
"""Priprema poredjenje: isti MVP i isti upiti, prazan Claude Code prema pluginu, kroz ekstenziju u Cursor-u.

    python scripts/priprema_poredjenja.py <prazan folder> [--bez-venv]

<folder>/
  UPIT.txt, UPIT-izrada.txt, POKRETANJE.md, manifest.json
  prazan/projekat/MVP.md   prazan/config/                    bez plugina, skillova i agenata
  plugin/projekat/...      plugin/config/skills/diplomski/   snimak plugina, bez .git
  <strana>/otvori.cmd, prijava.cmd, venv/

Svaka strana se otvara SAMO kroz svoj otvori.cmd: novi prozor prijavljenog Cursor-a sa CLAUDE_CONFIG_DIR
i venv-om strane. Ekstenzija ne prima zastavice, pa ogranicenja stoje u config/settings.json strane.
Prvi upit trazi detaljan plan, drugi izradu, pa se planiranje meri odvojeno i na strani koja nema
upis faza. Odbija neprazan folder i folder unutar git repozitorijuma: sync.py u snimku ne sme da
nadje tudji repo. --bez-venv je samo za testove.
"""
import argparse, datetime, glob, hashlib, importlib.metadata, json, os, shutil, subprocess, sys

sys.stdout.reconfigure(encoding='utf-8')
PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MVP_IZVOR = os.path.join(PLUGIN, 'MVP-orkestrator.md')
STRANE = ('prazan', 'plugin')
ZABRANJENI_ALATI = ['Agent', 'Task', 'Skill', 'Workflow', 'SendMessage', 'ListAgents']
ZAJEDNICKA_PODESAVANJA = {'syncClaudeAiSkills': False, 'model': 'opus', 'effortLevel': 'high'}     # sync: prijava bi povukla skillove naloga
PODESAVANJA_STRANE = {
    'prazan': dict(ZAJEDNICKA_PODESAVANJA, disableBundledSkills=True, skillOverrides={'doctor': 'off', 'design': 'off', 'plugin-authoring': 'off'},
                   permissions={'defaultMode': 'acceptEdits', 'deny': ZABRANJENI_ALATI}),
    'plugin': dict(ZAJEDNICKA_PODESAVANJA, permissions={'defaultMode': 'acceptEdits'}),
}
ZAGLAVLJE_CMD = """@echo off
setlocal
for /f "delims==" %%v in ('set CLAUDE 2^>nul') do set "%%v="
for /f "delims==" %%v in ('set ANTHROPIC 2^>nul') do set "%%v="
set "PWD="
set "OLDPWD="
"""
UPIT = ('Procitaj MVP.md i napravi detaljan plan izrade igre Orkestrator u plan.md. '
        'Ako nesto u MVP.md nije jasno, pitaj. Ne pisi kod dok ne potvrdim plan.')
UPIT_IZRADA = 'Potvrdjeno. Izradi igru Orkestrator. Zavrseno je kada su ispunjeni svi uslovi iz odeljka "Kada je gotovo" u MVP.md.'
# Upit kaze STA se dodaje. Provere kvaliteta (telefon, konzola, testovi) su namerno izostavljene:
# one su u skillu ui-bootstrap, pa poredjenje pokazuje da li ih skill donosi.
UPIT_STIL = ('Doradi izgled igre Orkestrator, tako da izgleda kao igra, a ne kao obrazac: jedinstvena tema (boje, slova, razmaci), '
             'slike i ikonice koje prate zadatke, izbore i ishode, jasno istaknut izabran izbor, pregledan budzet i rok, '
             'i zavrsni ekran koji izgleda kao rezultat igre. Ne menjaj pravila, tekst ni ponasanje igre.')
# Runda 2: nove funkcionalnosti kao zahtev klijenta, svaka u novoj sesiji na obe strane. Kazu STA klijent
# trazi; bezbednost, testovi i prevod po pravilima su namerno izostavljeni, jer su posao skillova.
UPIT_RANG = ('Klijent trazi rang listu: posle zavrsene partije igrac moze da upise ime i sacuva rezultat, a pocetni '
             'ekran prikazuje 10 najboljih rezultata (ime, poeni, ocena, datum). Ovo menja MVP: cuvanje rezultata '
             'i rang lista vise nisu van opsega.')
UPIT_DELJENJE = ('Klijent trazi deljenje rezultata: na zavrsnom ekranu igrac dobija link koji moze da posalje drugome, '
                 'a taj link otvara stranicu sa rezultatom te partije (poeni, ocena, tihe greske, lekcije), bez '
                 'mogucnosti da se igra nastavi.')
UPIT_JEZIK = ('Klijent trazi englesku verziju igre: igrac bira srpski ili engleski, izbor se pamti, a ceo tekst na '
              'ekranu, ukljucujuci lekcije i napomenu, postoji na oba jezika.')
# Runda 3: namerno izabrani zahtevi u kojima greska skupo kosta (podaci, autorizacija, javni rad).
UPIT_BODOVANJE = ('Klijent menja bodovanje: tiha greska sada kosta 35 poena umesto 25, a kazna za prekoracen budzet vise '
                  'nije ista za svako prekoracenje, vec iznosi 10 poena za svakih zapocetih 10% prekoracenja, najvise 50. '
                  'Promena vazi od sada; igraci koji su vec na rang listi ili su vec podelili link ne smeju da se osete prevareno.')
UPIT_MODERATOR = ('Klijent trazi moderatora: moderator se prijavljuje imenom i lozinkom i moze da obrise rezultat sa rang '
                  'liste ili deljeni link, a vidi i ko je sta obrisao i kada. Igraci i dalje igraju bez naloga. Prvog '
                  'moderatora pravi razvijalac.')
UPIT_JAVNO = ('Klijent pusta igru javno na internetu, na adresi https://orkestrator.example, i ocekuje nekoliko hiljada '
              'igraca dnevno. Pripremi projekat za to; samo postavljanje na server radi klijentov administrator po tvom uputstvu.')
# Runda 4: plugin v2 (podesen na osnovu rundi 1-3), nove sesije bez konteksta, model izabran u panelu.
UPIT_IZAZOV = ('Klijent trazi dnevni izazov: svakog dana svi igraci igraju istu partiju (isti zadaci i isti ishodi), a '
               'pocetni ekran pored glavne prikazuje i rang listu dana. Obicna igra ostaje kakva je.')
# Runda 5: plugin v2.2 (laki put, agenti nasledjuju model), Opus 5.5 na najnizem nivou izabranom u panelu.
UPIT_CSV = 'Klijent trazi da moderator moze da preuzme rang listu (glavnu i dnevnu) kao CSV datoteku koju otvara u Excel-u.'
# Runda 6: plugin v2.3 (brzi paket testova, qa samo za tok kroz pregledac), Fable 5.2 na najvisem nivou.
UPIT_PRIJAVA = ('Klijent trazi da igrac moze da prijavi neprikladno ime sa rang liste, a moderator vidi prijavljena '
                'imena i odlucuje da li brise rezultat.')
# Runda 7: plugin v2.4 (paralelni rezim: mapa, radnici u worktree-ovima), Opus 5.5 high na obe strane.
UPIT_PET = ('Klijent trazi pet novih stvari: (1) stranicu "Kako se igra" sa pravilima i primerom jednog kruga, dostupnu '
            'sa pocetnog ekrana; (2) zvucne efekte za ishod kruga koje igrac moze da ukljuci ili iskljuci, a izbor se '
            'pamti; (3) da igrac vidi svojih poslednjih 10 zavrsenih partija; (4) da moderator vidi statistiku: broj '
            'odigranih partija i prosecne poene po danu za poslednjih 7 dana; (5) javnu adresu sa koje partneri '
            'preuzimaju rang listu u JSON obliku.')
PROPISANI_UPITI = (('izrada', UPIT_IZRADA), ('stil', UPIT_STIL),
                   ('rang', UPIT_RANG), ('deljenje', UPIT_DELJENJE), ('jezik', UPIT_JEZIK),
                   ('bodovanje', UPIT_BODOVANJE), ('moderator', UPIT_MODERATOR), ('javno', UPIT_JAVNO),
                   ('izazov', UPIT_IZAZOV), ('csv', UPIT_CSV), ('prijava', UPIT_PRIJAVA),
                   ('pet', UPIT_PET))   # posle prvog upita; ne broje se kao podpitanje
UPITI_FAJLOVI = (('UPIT.txt', UPIT), ('UPIT-izrada.txt', UPIT_IZRADA), ('UPIT-stil.txt', UPIT_STIL),
                 ('UPIT-4-rang.txt', UPIT_RANG), ('UPIT-5-deljenje.txt', UPIT_DELJENJE), ('UPIT-6-jezik.txt', UPIT_JEZIK),
                 ('UPIT-7-bodovanje.txt', UPIT_BODOVANJE), ('UPIT-8-moderator.txt', UPIT_MODERATOR), ('UPIT-9-javno.txt', UPIT_JAVNO),
                 ('UPIT-10-izazov.txt', UPIT_IZAZOV), ('UPIT-11-csv.txt', UPIT_CSV), ('UPIT-12-prijava.txt', UPIT_PRIJAVA),
                 ('UPIT-13-pet.txt', UPIT_PET))
SNIMAK_BEZ = shutil.ignore_patterns('.git', '.claude', '__pycache__', '*.pyc', '*.docx', '*.pdf', '~$*', 'poglavlje-7-nacrt.md', 'MVP-orkestrator.md')
USLOVI = """
## 9. Uslovi izrade

- Python, Django i Playwright sa pregledacem su vec instalirani.
- Ako pokreces server, izaberi slobodan port: na istom racunaru moze da radi i druga izrada.
"""
POKRETANJE = """# Pokretanje poredjenja

Isti rezim dozvola i isti model na obe strane. Radi se kroz Claude ekstenziju u Cursor-u.

## 1. Prijava, jednom po strani

```
& "{koren}\\prazan\\prijava.cmd"
& "{koren}\\plugin\\prijava.cmd"
```

## 2. Dokaz da su strane ciste, pre prvog upita

```
python "{skripta}" provera "{koren}"
```

Mora da se zavrsi sa `SVE PROVERE PROSLE`. Dokaz ostaje u `provera.json`.

## 3. Cursor

Svaku stranu otvori SAMO njenim launcherom, da bi prozor dobio okruzenje strane:

```
& "{koren}\\prazan\\otvori.cmd"
& "{koren}\\plugin\\otvori.cmd"
```

Koristi Claude ekstenziju u tim prozorima. Cursor AI ne koristi.

## 4. Start, u oba prozora u isto vreme

Jedna sesija po strani.

1. Nalepi tacno tekst iz `UPIT.txt`: agent pravi `plan.md`.
2. Odmah proveri da rad ide u pravi folder: `python "{skripta}" trag "{koren}"`. Svaka strana mora da ima transkript, a maticni folder 0.
3. Kada je plan gotov, nalepi tacno tekst iz `UPIT-izrada.txt`: agent gradi igru.
4. Kada je izrada gotova, u istoj sesiji nalepi tacno tekst iz `UPIT-stil.txt`: agent doradjuje izgled.

## 5. Runda 2: nove funkcionalnosti

Svaki od upita `UPIT-4-rang.txt`, `UPIT-5-deljenje.txt` i `UPIT-6-jezik.txt` ide redom, u NOVOJ sesiji
(novi razgovor u panelu istog prozora), na obe strane u isto vreme. Sledeci upit tek kada obe strane zavrse.
Odmah posle svakog upita pokreni `trag`. Ako agent trazi potvrdu plana, odgovori "Potvrdjeno."

## 6. Runda 3: zahtevi u kojima greska skupo kosta

Isto kao runda 2, redom: `UPIT-7-bodovanje.txt`, `UPIT-8-moderator.txt`, `UPIT-9-javno.txt`.
Ovi zahtevi su namerno izabrani tamo gde plugin tvrdi da vredi; u radu se navode kao takvi.

## 7. Runda 4: plugin v2

`UPIT-10-izazov.txt` u NOVOJ sesiji na obe strane (novi razgovor u panelu istog prozora), sa istim modelom
i nivoom izabranim u panelu na obe strane. Plugin je pre ove runde izmenjen (v2); to pise u `manifest.json`.

## 8. Runda 5: plugin v2.2

`UPIT-11-csv.txt` u NOVOJ sesiji na obe strane, Opus 5.5 na najnizem nivou izabranom u panelu, isto na
obe strane. Plugin v2.2: laki put do oko 15 datoteka, agenti nasledjuju model i nivo osim `security`.

## 9. Runda 6: plugin v2.3

`UPIT-12-prijava.txt` u NOVOJ sesiji na obe strane, Fable 5.2 na NAJVISEM nivou izabranom u panelu, isto
na obe strane. Plugin v2.3: brzi paket testova tokom rada, ceo jednom; `qa` samo kada se menja tok kroz pregledac.

## 10. Runda 7: plugin v2.4

`UPIT-13-pet.txt` (pet nezavisnih zadataka) u NOVOJ sesiji na obe strane, Opus 5.5 high izabran u panelu,
isto na obe strane. Plugin v2.4: paralelni rezim (mapa projekta, radnici u worktree-ovima, jedna kontrola).

## Pravila za coveka tokom izrade

- Odgovaraj samo kada agent pita; isto pitanje dobija isti odgovor na obe strane.
- Dozvole za komande odobravaj podjednako brzo na obe strane.
- Plan ne doradjuj sam. Ne pomazi, ne ispravljaj i ne pozuruj. Svaka poruka osim dva propisana upita broji se kao podpitanje.
- Kada agent kaze da je gotovo, ne doradjuj posle toga.

## Posle izrade

```
python "{skripta}" slepo "{koren}"
```

Popuni `ocena/ocena.json` gledajuci samo foldere `ocena/X` i `ocena/Y`; `ocena/kljuc.json` ne otvaraj.

```
python "{skripta}" izvestaj "{koren}"
```

Rezultat: `rezultati/poredjenje.md` i `.json`.
"""


def mvp():
    with open(MVP_IZVOR, encoding='utf-8') as f:
        return f.read().rstrip('\n') + '\n' + USLOVI


def alat_ekstenzije():
    """Alat koji pokrece Claude ekstenzija u Cursor-u; None ako ekstenzija nije instalirana."""
    kandidati = sorted(glob.glob(os.path.join(os.path.expanduser('~'), '.cursor', 'extensions', 'anthropic.claude-code-*-win32-x64',
                                              'resources', 'native-binary', 'claude.exe')))
    return kandidati[-1] if kandidati else None


def promenljive_strane(koren, strana):
    return {'CLAUDE_CONFIG_DIR': os.path.join(koren, strana, 'config'), 'CLAUDE_CODE_AUTO_CONNECT_IDE': 'false',
            'ENABLE_CLAUDEAI_MCP_SERVERS': 'false', 'DISABLE_AUTOUPDATER': '1', 'VIRTUAL_ENV': os.path.join(koren, strana, 'venv')}


def u_gitu(put):
    """Da li put, ili najblizi postojeci roditelj, pripada git repozitorijumu."""
    while not os.path.isdir(put):
        put = os.path.dirname(put)
    r = subprocess.run(['git', '-C', put, 'rev-parse', '--is-inside-work-tree'], capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip() == 'true'


def verzija_paketa(ime):
    try:
        return importlib.metadata.version(ime)
    except importlib.metadata.PackageNotFoundError:
        print('UPOZORENJE: %s nije instaliran; izrada ga trazi.' % ime, file=sys.stderr)
        return None


def verzija_alata():
    alat = alat_ekstenzije() or shutil.which('claude')
    if alat is None:
        print('UPOZORENJE: Claude alat nije nadjen.', file=sys.stderr)
        return None
    return subprocess.run([alat, '--version'], capture_output=True, text=True, encoding='utf-8').stdout.strip()


def stanje_plugina():
    git = lambda *a: subprocess.run(['git', '-C', PLUGIN, *a], capture_output=True, text=True, encoding='utf-8').stdout.strip()
    return {'commit': git('rev-parse', 'HEAD') or None, 'neposlate_izmene': bool(git('status', '--porcelain'))}


def sha(tekst):
    return hashlib.sha256(tekst.encode('utf-8')).hexdigest()


def upisi(put, tekst, kraj_reda='\n'):
    with open(put, 'w', encoding='utf-8', newline=kraj_reda) as f:
        f.write(tekst)


def upisi_okruzenje_strane(koren, strana):
    """Podesavanja strane i launcheri; sve sto strana sme da ima, iz jednog izvora."""
    projekat = os.path.join(koren, strana, 'projekat')
    prom = promenljive_strane(koren, strana)
    upisi(os.path.join(prom['CLAUDE_CONFIG_DIR'], 'settings.json'), json.dumps(PODESAVANJA_STRANE[strana], indent=1) + '\n')
    okruzenje = ZAGLAVLJE_CMD + ''.join('set "%s=%s"\n' % kv for kv in prom.items()) + 'set "PATH=%s\\Scripts;%%PATH%%"\n' % prom['VIRTUAL_ENV']
    upisi(os.path.join(koren, strana, 'prijava.cmd'), okruzenje + 'call claude auth login\n', kraj_reda='\r\n')
    upisi(os.path.join(koren, strana, 'otvori.cmd'), okruzenje + 'call cursor --new-window "%s"\n' % projekat, kraj_reda='\r\n')


def upisi_pokretanje(koren, skripta):
    upisi(os.path.join(koren, 'POKRETANJE.md'), POKRETANJE.format(koren=koren, skripta=skripta))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('koren')
    ap.add_argument('--bez-venv', action='store_true')
    a = ap.parse_args()
    koren = os.path.abspath(a.koren)
    if os.path.exists(koren) and (not os.path.isdir(koren) or os.listdir(koren)):
        print('Odbijeno: %s postoji i nije prazan folder.' % koren, file=sys.stderr)
        return 2
    if u_gitu(koren):
        print('Odbijeno: %s je unutar git repozitorijuma.' % koren, file=sys.stderr)
        return 2
    projekti = {s: os.path.join(koren, s, 'projekat') for s in STRANE}
    os.makedirs(projekti['prazan'])
    os.makedirs(os.path.join(koren, 'prazan', 'config'))
    snimak = os.path.join(koren, 'plugin', 'config', 'skills', 'diplomski')
    shutil.copytree(PLUGIN, snimak, ignore=SNIMAK_BEZ)
    r = subprocess.run([sys.executable, os.path.join(snimak, 'scripts', 'novi_projekat.py'), projekti['plugin']],
                       capture_output=True, text=True, encoding='utf-8')
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        return r.returncode
    tekst = mvp()
    for s in STRANE:
        upisi(os.path.join(projekti[s], 'MVP.md'), tekst)
        upisi_okruzenje_strane(koren, s)
        if not a.bez_venv:
            subprocess.run([sys.executable, '-m', 'venv', '--system-site-packages', os.path.join(koren, s, 'venv')], check=True)
    for ime, tekst_upita in UPITI_FAJLOVI:
        upisi(os.path.join(koren, ime), tekst_upita + '\n')
    upisi_pokretanje(koren, os.path.join(PLUGIN, 'scripts', 'poredjenje.py'))
    manifest = {'napravljen': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'), 'upiti': dict(UPITI_FAJLOVI),
                'podesavanja': PODESAVANJA_STRANE, 'mvp_sha256': sha(tekst), 'plugin': stanje_plugina(), 'claude': verzija_alata(),
                'python': sys.version.split()[0], 'django': verzija_paketa('django'), 'playwright': verzija_paketa('playwright')}
    upisi(os.path.join(koren, 'manifest.json'), json.dumps(manifest, ensure_ascii=False, indent=1) + '\n')
    print('[priprema] spremno: %s\nDalje: %s' % (koren, os.path.join(koren, 'POKRETANJE.md')))
    return 0


if __name__ == '__main__':
    sys.exit(main())
