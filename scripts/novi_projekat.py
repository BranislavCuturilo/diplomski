# -*- coding: utf-8 -*-
"""Priprema PRAZAN folder za aplikaciju koja se radi ovim pluginom.

    python scripts/novi_projekat.py <putanja>

Pravi marker, kopira skills/sloj-projekta/* u .claude/skills/, pise .claude/settings.json
(diplomski ukljucen, brain iskljucen) i kratak CLAUDE.md. Odbija neprazan folder i folder
unutar ovog repozitorijuma. Putanje u podesavanjima i CLAUDE.md su stvarna lokacija ove kopije plugina.
"""
import argparse, json, os, re, shutil, sys

sys.stdout.reconfigure(encoding='utf-8')
PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PLUGIN, 'hooks'))
import projekat

PODESAVANJA = {'enabledPlugins': {'diplomski@skills-dir': True, 'brain@skills-dir': False}}
CLAUDE_MD = """# Igra Orkestrator

Edukativna igra u browseru. Pravila igre: skill `projekat-domen`; standard koda: `projekat-standardi`.
`MVP.md`, ako postoji, opisuje proizvod; pravila i brojevi u njemu isti su kao u `projekat-domen`.
Radi se pluginom diplomski: agenti `diplomski:*`, slojevi 1-3 iz plugina, sloj projekta u `.claude/skills/`.
Stek: Django, SQLite, cist JavaScript, Bootstrap 5. Skillovi `django-mysql` i `django-nginx-docker` se ovde ne koriste.

## Raspored

Svaka faza pocinje upisom: `python "<plugin>/scripts/faza.py" <ime faze>`.
Pre prvog pokretanja agenta ucitaj skill `craft-delegiranje`.

| Faza | Ko | Sta |
|---|---|---|
| planiranje | glavna sesija; `planer` samo za pun aparat | kratak plan i najvise jedan dijalog pitanja |
| implementacija | glavna sesija; talasi agenata samo za pun aparat | kod, sabloni, skripta, prevod i testovi |
| kontrolni skup | `qa` kada izmena menja tok kroz pregledac; `security` kada dira rizik; u istoj poruci | testovi i jedan tok kroz pregledac; bezbednosna revizija |
| poruka klijentu | glavna sesija | kratak izvestaj, odluke za potvrdu, niski nalazi |

Laki put je podrazumevan za izmenu postojece aplikacije do oko 15 datoteka; pun aparat (`planer`,
talasi, `translate`) samo za novu aplikaciju, ceo novi jezik ili vecu izmenu (skill `craft-delegiranje`).
Upit sa 3 ili vise nezavisnih zadataka ide u paralelni rezim: mapa projekta, radnici u worktree-ovima,
spajanje u glavnoj sesiji i jedna kontrola nad celinom.
Na doradu vracaju samo visoki i srednji nalazi; najvise jedna ponovna provera po upitu.

Merenje pise u `.claude/usage/`, koje git ignorise (upiti su pun tekst).
"""


def pravilo_citanja():
    """Podagent nema alat Skill, pa skill van svog zaglavlja cita kao datoteku van projekta."""
    p = re.sub(r'^([A-Za-z]):', lambda m: '/' + m.group(1).lower(), PLUGIN.replace('\\', '/'))
    return 'Read(/%s/**)' % p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('putanja')
    a = ap.parse_args()
    cilj = os.path.abspath(a.putanja)
    if os.path.normcase(cilj + os.sep).startswith(os.path.normcase(PLUGIN + os.sep)):
        print('Odbijeno: aplikacija se ne pravi unutar repozitorijuma plugina: %s' % cilj, file=sys.stderr)
        return 2
    if os.path.exists(cilj) and (not os.path.isdir(cilj) or os.listdir(cilj)):
        print('Odbijeno: %s postoji i nije prazan folder.' % cilj, file=sys.stderr)
        return 2
    claude = os.path.join(cilj, '.claude')
    skills = os.path.join(claude, 'skills')
    usage = projekat.usage_folder(cilj)
    os.makedirs(skills)
    os.makedirs(usage)
    sablon = os.path.join(PLUGIN, 'skills', 'sloj-projekta')
    for ime in sorted(os.listdir(sablon)):
        izvor = os.path.join(sablon, ime)
        if os.path.isdir(izvor):
            shutil.copytree(izvor, os.path.join(skills, ime))
        else:
            shutil.copy2(izvor, skills)
    with open(os.path.join(cilj, projekat.MARKER), 'w', encoding='utf-8') as f:
        f.write('Marker: hookovi plugina diplomski rade samo u projektu koji ima ovaj fajl.\n')
    with open(os.path.join(claude, 'settings.json'), 'w', encoding='utf-8') as f:
        json.dump(dict(PODESAVANJA, permissions={'allow': [pravilo_citanja()]}), f, indent=2)
        f.write('\n')
    with open(os.path.join(usage, '.gitignore'), 'w', encoding='utf-8') as f:
        f.write('*\n')
    with open(os.path.join(cilj, 'CLAUDE.md'), 'w', encoding='utf-8') as f:
        f.write(CLAUDE_MD.replace('<plugin>', PLUGIN.replace('\\', '/')))
    print('[novi_projekat] spreman: %s' % cilj)
    return 0


if __name__ == '__main__':
    sys.exit(main())
