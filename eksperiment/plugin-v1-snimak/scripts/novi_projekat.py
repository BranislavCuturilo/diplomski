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
| planiranje | `planer` | plan i pitanja |
| delegiranje | glavna sesija | deli plan na talase |
| implementacija | `backend-senior`; `frontend-medior` | motor, parametri i prikazi; sablon i skripta |
| kontrolni skup | `qa`; `security`, u jednoj poruci | testovi i pregledac; bezbednosna revizija |
| poruka klijentu | glavna sesija | kratak izvestaj |

Kontrolni skup rade podagenti, svaki u svom kontekstu, pa nova sesija nije potrebna.
Nalaz koji trazi ispravku vraca fazu na `implementacija`, pa ponovo `kontrolni skup`.
Posle prve izrade kontrolni skup ide u obimu izmene (skill `craft-delegiranje`).

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
