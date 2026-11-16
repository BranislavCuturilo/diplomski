# -*- coding: utf-8 -*-
"""UserPromptSubmit: pre prvog koraka predlaze modelu skillove i agente po recima upita.

Predlog NIJE obavezan (to radi require_skill.py). Reci su napisane recnikom
korisnika koji problem jos nije razvrstao: "da li korisnik A vidi ...", ne samo "IDOR".
Svaki promasaj rutera postaje slucaj u scripts/evals.json.
"""
import json, re, sys

TEME = [
    (r'model|migraci|views?\.py|prikaz|forma|queryset|django', ['stack-django']),
    (r'da li .*(vidi|vide|pristup)|tudj|dozvol|pristup|login|lozink|bezbed|security|idor', ['craft-security']),
    (r'test|pada|flaky|qa\b|proveri da radi', ['craft-testing']),
    (r'deploy|isporu|docker|nginx|ssl|tls|server|actions', ['craft-git', 'django-nginx-docker']),
    (r'mysql|mariadb|duplikat', ['django-mysql']),
    (r'sablon|template|css|bootstrap|responsive|telefon|izgled|ekran', ['ui-bootstrap', 'django-ssr-bootstrap']),
    (r'prevod|prevedi|engleski|jezik|\.po\b', ['craft-i18n']),
    (r'motor|potez|budzet|kontrolni skup|tih\w* gresk|pravila igre|\bseme\b|\bkrug|\brok\b|sansa|poen|balans', ['projekat-domen']),
    (r'orkestrator|napravi igru', ['projekat-domen', 'projekat-standardi']),
    (r'delegir|podagent|paraleln|talas|podeli posao|pokreni agent', ['craft-delegiranje']),
]
AGENTI = [
    (r'nova aplikacija|od nule|plan|specifikacij|napravi igru', 'planer'),
    (r'bezbed|security|penetrac|da li .* vidi', 'security'),
    (r'test|qa\b', 'qa'),
    (r'deploy|isporu|vps|github actions', 'devops'),
    (r'prevod|prevedi', 'translate'),
    (r'migraci|nov model|transakcij', 'backend-senior'),
    (r'landing|pocetna strana', 'frontend-senior'),
    (r'motor igre|pravila igre', 'backend-senior'),
]


def main():
    try:
        upit = (json.load(sys.stdin).get('prompt') or '').lower()
    except ValueError:
        return 0
    skillovi = []
    for obrazac, imena in TEME:
        if re.search(obrazac, upit):
            skillovi += [s for s in imena if s not in skillovi]
    agenti = [a for obrazac, a in AGENTI if re.search(obrazac, upit)]
    if not skillovi and not agenti:
        return 0
    delovi = []
    if skillovi:
        delovi.append('Skillovi za ovaj zadatak: ' + ', '.join(skillovi[:6]) + '.')
    if agenti:
        delovi.append('Agenti koji odgovaraju: ' + ', '.join(agenti[:5]) + '. Nezavisne pokreni u JEDNOJ poruci.')
    print(json.dumps({'hookSpecificOutput': {'hookEventName': 'UserPromptSubmit',
                                             'additionalContext': ' '.join(delovi)}}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
