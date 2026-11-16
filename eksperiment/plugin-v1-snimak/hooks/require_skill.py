# -*- coding: utf-8 -*-
"""PreToolUse (Edit|Write): odbija izmenu dok skill za tu vrstu fajla nije ucitan.

Ulaz (stdin, JSON od Claude Code): tool_name, tool_input.file_path, transcript_path,
a u podagentu jos agent_id i agent_type.

Skill se smatra ucitanim ako transkript to stvarno belezi: poziv alata Skill, ili red
<command-name>skill</command-name> (tako se u transkriptu podagenta vide skillovi iz
zaglavlja agenta, a u glavnom toku /skill komanda). Podagent nema alat Skill, pa za njega
vazi i Read datoteke SKILL.md.

U podagentu je transcript_path transkript RODITELJA; podagentov je
<sesija>/subagents/agent-<id>.jsonl.
"""
import fnmatch, glob, json, os, re, sys

# vrsta fajla -> skill koji mora biti ucitan (prvo poklapanje pobedjuje)
PRAVILA = [
    ('*/migrations/*.py', 'stack-django'),
    ('*/tests/*.py', 'craft-testing'),
    ('*test_*.py', 'craft-testing'),
    ('*models.py', 'stack-django'),
    ('*views.py', 'stack-django'),
    ('*forms.py', 'stack-django'),
    ('*motor.py', 'projekat-domen'),
    ('*parametri.py', 'projekat-domen'),
    ('*/static/*.js', 'django-ssr-bootstrap'),
    ('*/templates/*.html', 'ui-bootstrap'),
    ('*.css', 'ui-bootstrap'),
    ('*Dockerfile*', 'django-nginx-docker'),
    ('*nginx*.conf', 'django-nginx-docker'),
    ('*/.github/workflows/*', 'craft-git'),
    ('*.po', 'craft-i18n'),
    ('*.py', 'craft-code'),
]
KOMANDA = re.compile(r'<command-name>/?(?:[\w-]+:)?([\w-]+)</command-name>')


def potreban_skill(putanja):
    p = putanja.replace('\\', '/')
    for obrazac, skill in PRAVILA:
        if fnmatch.fnmatch(p, obrazac):
            return skill
    return None


def ucitani_skillovi(transcript_path, podagent=False):
    """Skup ucitanih skillova; None ako transkript ne moze da se procita."""
    if not transcript_path or not os.path.exists(transcript_path):
        return None
    imena = set()
    with open(transcript_path, encoding='utf-8', errors='replace') as f:
        for red in f:
            if '"Skill"' not in red and 'command-name' not in red and 'SKILL.md' not in red:
                continue
            try:
                zapis = json.loads(red)
            except ValueError:
                continue
            sadrzaj = (zapis.get('message') or {}).get('content') or []
            if zapis.get('type') == 'user':
                tekstovi = [sadrzaj] if isinstance(sadrzaj, str) else [
                    d.get('text', '') for d in sadrzaj if isinstance(d, dict) and d.get('type') == 'text']
                for tekst in tekstovi:
                    imena.update(KOMANDA.findall(tekst))
            for deo in sadrzaj if isinstance(sadrzaj, list) else []:
                if not isinstance(deo, dict) or deo.get('type') != 'tool_use':
                    continue
                unos = deo.get('input') or {}
                if deo.get('name') == 'Skill':
                    imena.add(str(unos.get('skill', '')).split(':')[-1])
                elif podagent and deo.get('name') == 'Read' and str(unos.get('file_path', '')).endswith('SKILL.md'):
                    imena.add(os.path.basename(os.path.dirname(unos['file_path'].replace('\\', '/'))))
    return imena


def putanja_skilla(skill):
    projektni = os.path.join(os.environ.get('DIPLOMSKI_PROJEKAT', ''), '.claude', 'skills', skill, 'SKILL.md')
    if os.path.exists(projektni):
        return projektni.replace('\\', '/')
    koren = os.environ.get('CLAUDE_PLUGIN_ROOT') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    nadjeni = glob.glob(os.path.join(koren, 'skills', '*', skill, 'SKILL.md'))
    return nadjeni[0].replace('\\', '/') if nadjeni else skill + '/SKILL.md'


def main():
    try:
        ulaz = json.load(sys.stdin)
    except ValueError:
        return 0                                  # neispravan ulaz: ne blokiraj rad, ali ni ne pretvaraj se
    putanja = (ulaz.get('tool_input') or {}).get('file_path', '')
    skill = potreban_skill(putanja)
    if not skill:
        return 0
    agent_id = ulaz.get('agent_id')
    transkript = ulaz.get('transcript_path') or ''
    if agent_id:
        transkript = (ulaz.get('agent_transcript_path')
                      or os.path.join(os.path.splitext(transkript)[0], 'subagents', 'agent-%s.jsonl' % agent_id))
    imena = ucitani_skillovi(transkript, podagent=bool(agent_id))
    if imena is None or skill in imena:           # transkript nije citljiv: ne blokiraj rad
        return 0
    if agent_id:
        uputstvo = 'Procitaj %s alatom Read pa ponovi izmenu.' % putanja_skilla(skill)
    else:
        uputstvo = 'Ucitaj ga (alat Skill) pa ponovi izmenu.'
    print(json.dumps({'hookSpecificOutput': {
        'hookEventName': 'PreToolUse',
        'permissionDecision': 'deny',
        'permissionDecisionReason': 'Izmena %s trazi skill "%s". %s' % (os.path.basename(putanja), skill, uputstvo),
    }}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
