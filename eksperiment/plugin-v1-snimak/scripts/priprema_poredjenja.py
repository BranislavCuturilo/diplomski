# -*- coding: utf-8 -*-
"""Priprema poredjenje: isti MVP i isti upiti, prazan Claude Code prema pluginu.

    python scripts/priprema_poredjenja.py <prazan folder> [--bez-venv]

<folder>/
  UPIT.txt, UPIT-izrada.txt, POKRETANJE.md, manifest.json
  prazan/projekat/MVP.md   prazan/config/                    bez plugina, skillova i agenata
  plugin/projekat/...      plugin/config/skills/diplomski/   snimak plugina, bez .git
  <strana>/pokreni.cmd, prijava.cmd, venv/

Svaka strana se pokrece SAMO kroz svoj pokreni.cmd: on brise nasledjeno okruzenje, postavlja
CLAUDE_CONFIG_DIR, venv strane i zastavice, pa rezultat ne zavisi od toga odakle je pokrenut.
Prvi upit trazi detaljan plan, drugi izradu, pa se planiranje meri odvojeno i na strani koja nema
upis faza. Odbija neprazan folder i folder unutar git repozitorijuma: sync.py u snimku ne sme da
nadje tudji repo. --bez-venv je samo za testove.
"""
import argparse, datetime, hashlib, importlib.metadata, json, os, shutil, subprocess, sys

sys.stdout.reconfigure(encoding='utf-8')
PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MVP_IZVOR = os.path.join(PLUGIN, 'MVP-orkestrator.md')
STRANE = ('prazan', 'plugin')
OSNOVA_KOMANDE = '--model opus --effort high --permission-mode acceptEdits --strict-mcp-config'
KOMANDE = {'prazan': OSNOVA_KOMANDE + ' --disable-slash-commands --disallowedTools "Agent,Task,Skill,Workflow,SendMessage,ListAgents"', 'plugin': OSNOVA_KOMANDE}
LAUNCHER = """@echo off
setlocal
for /f "delims==" %%v in ('set CLAUDE 2^>nul') do set "%%v="
for /f "delims==" %%v in ('set ANTHROPIC 2^>nul') do set "%%v="
set "CLAUDE_CONFIG_DIR={config}"
set "CLAUDE_CODE_AUTO_CONNECT_IDE=false"
set "ENABLE_CLAUDEAI_MCP_SERVERS=false"
set "DISABLE_AUTOUPDATER=1"
set "VIRTUAL_ENV={venv}"
set "PATH={venv}\\Scripts;%PATH%"
cd /d "{projekat}"
call claude {komanda} %*
"""
UPIT = ('Procitaj MVP.md i napravi detaljan plan izrade igre Orkestrator u plan.md. '
        'Ako nesto u MVP.md nije jasno, pitaj. Ne pisi kod dok ne potvrdim plan.')
UPIT_IZRADA = 'Potvrdjeno. Izradi igru Orkestrator. Zavrseno je kada su ispunjeni svi uslovi iz odeljka "Kada je gotovo" u MVP.md.'
SNIMAK_BEZ = shutil.ignore_patterns('.git', '.claude', '__pycache__', '*.pyc', '*.docx', '*.pdf', '~$*', 'poglavlje-7-nacrt.md', 'MVP-orkestrator.md')
USLOVI = """
## 9. Uslovi izrade

- Python, Django i Playwright sa pregledacem su vec instalirani.
- Ako pokreces server, izaberi slobodan port: na istom racunaru moze da radi i druga izrada.
"""
POKRETANJE = """# Pokretanje poredjenja

## 1. Prijava, jednom po strani

```
"{koren}\\prazan\\prijava.cmd"
"{koren}\\plugin\\prijava.cmd"
```

## 2. Dokaz da su strane ciste, pre prvog upita

```
python "{skripta}" provera "{koren}"
```

Mora da se zavrsi sa `SVE PROVERE PROSLE`. Dokaz ostaje u `provera.json`.

## 3. Cursor

Dva odvojena prozora Cursor-a, svaki sa svojim folderom:

- `{projekat_prazan}`
- `{projekat_plugin}`

U svakom otvori Terminal i pokreni samo:

```
..\\pokreni.cmd
```

**Ne koristi Claude panel u Cursor-u ni Cursor AI.** Panel je druga verzija alata i radi nad pravim
`~/.claude`, pa bi merenje bilo nevazece. Izvestaj to otkriva i prijavljuje.

## 4. Start, u oba prozora u isto vreme

Jedna sesija po strani.

1. Nalepi tacno tekst iz `UPIT.txt`: agent pravi `plan.md`.
2. Kada je plan gotov, nalepi tacno tekst iz `UPIT-izrada.txt`: agent gradi igru.

## Pravila za coveka tokom izrade

- Odgovaraj samo kada agent pita; isto pitanje dobija isti odgovor na obe strane.
- Dozvole za komande odobravaj podjednako brzo na obe strane.
- Plan ne doradjuj sam. Ne pomazi, ne ispravljaj i ne pozuruj. Svaka poruka osim dva propisana upita broji se kao podpitanje.
- Kada agent kaze da je gotovo: `/exit` (ili dva puta Ctrl+C). Ne doradjuj posle toga.

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
    claude = shutil.which('claude')
    if claude is None:
        print('UPOZORENJE: claude nije na putanji.', file=sys.stderr)
        return None
    return subprocess.run([claude, '--version'], capture_output=True, text=True, encoding='utf-8').stdout.strip()


def stanje_plugina():
    git = lambda *a: subprocess.run(['git', '-C', PLUGIN, *a], capture_output=True, text=True, encoding='utf-8').stdout.strip()
    return {'commit': git('rev-parse', 'HEAD') or None, 'neposlate_izmene': bool(git('status', '--porcelain'))}


def sha(tekst):
    return hashlib.sha256(tekst.encode('utf-8')).hexdigest()


def upisi(put, tekst, kraj_reda='\n'):
    with open(put, 'w', encoding='utf-8', newline=kraj_reda) as f:
        f.write(tekst)


def upisi_launchere(koren, strana, putanje):
    venv = os.path.join(koren, strana, 'venv')
    for ime, komanda in (('pokreni.cmd', KOMANDE[strana]), ('prijava.cmd', 'auth login')):
        upisi(os.path.join(koren, strana, ime), LAUNCHER.format(komanda=komanda, venv=venv, **putanje), kraj_reda='\r\n')


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
    putanje = {s: {'projekat': os.path.join(koren, s, 'projekat'), 'config': os.path.join(koren, s, 'config')} for s in STRANE}
    os.makedirs(putanje['prazan']['projekat'])
    os.makedirs(putanje['prazan']['config'])
    snimak = os.path.join(putanje['plugin']['config'], 'skills', 'diplomski')
    shutil.copytree(PLUGIN, snimak, ignore=SNIMAK_BEZ)
    r = subprocess.run([sys.executable, os.path.join(snimak, 'scripts', 'novi_projekat.py'), putanje['plugin']['projekat']],
                       capture_output=True, text=True, encoding='utf-8')
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        return r.returncode
    tekst = mvp()
    for s in STRANE:
        upisi(os.path.join(putanje[s]['projekat'], 'MVP.md'), tekst)
        upisi_launchere(koren, s, putanje[s])
        if not a.bez_venv:
            subprocess.run([sys.executable, '-m', 'venv', '--system-site-packages', os.path.join(koren, s, 'venv')], check=True)
    upisi(os.path.join(koren, 'UPIT.txt'), UPIT + '\n')
    upisi(os.path.join(koren, 'UPIT-izrada.txt'), UPIT_IZRADA + '\n')
    upisi(os.path.join(koren, 'POKRETANJE.md'), POKRETANJE.format(
        koren=koren, skripta=os.path.join(snimak, 'scripts', 'poredjenje.py'),
        projekat_prazan=putanje['prazan']['projekat'], projekat_plugin=putanje['plugin']['projekat']))
    manifest = {'napravljen': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'), 'upit': UPIT, 'upit_izrada': UPIT_IZRADA, 'komande': KOMANDE,
                'mvp_sha256': sha(tekst), 'plugin': stanje_plugina(), 'claude': verzija_alata(), 'python': sys.version.split()[0],
                'django': verzija_paketa('django'), 'playwright': verzija_paketa('playwright')}
    upisi(os.path.join(koren, 'manifest.json'), json.dumps(manifest, ensure_ascii=False, indent=1) + '\n')
    print('[priprema] spremno: %s\nDalje: %s' % (koren, os.path.join(koren, 'POKRETANJE.md')))
    return 0


if __name__ == '__main__':
    sys.exit(main())
