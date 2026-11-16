# -*- coding: utf-8 -*-
"""PostToolUse (Agent|Task|Skill): belezi jedan red po pozivu agenta ili skilla.

Izlaz: .claude/usage/usage.jsonl  (jedan JSON po redu, samo brojevi i imena, bez sadrzaja upita).
Cita ga scripts/usage_report.py.
"""
import datetime, json, os, sys


def main():
    try:
        ulaz = json.load(sys.stdin)
    except ValueError:
        return 0
    alat = ulaz.get('tool_name', '')
    unos = ulaz.get('tool_input') or {}
    if alat == 'Skill':
        vrsta, ime = 'skill', unos.get('skill', '?')
    else:
        vrsta, ime = 'agent', unos.get('subagent_type') or 'general-purpose'
    odgovor = ulaz.get('tool_response') or {}
    zapis = {
        'at': datetime.datetime.now().isoformat(timespec='seconds'),
        'session': ulaz.get('session_id'),
        'vrsta': vrsta,
        'ime': ime,
        'model': unos.get('model'),
        # pravo polje je totalTokens; agent pokrenut u pozadini ga nema i ostaje None
        'tokeni': odgovor.get('totalTokens') if isinstance(odgovor, dict) else None,
    }
    folder = os.path.join(os.environ.get('DIPLOMSKI_PROJEKAT', '.'), '.claude', 'usage')
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, 'usage.jsonl'), 'a', encoding='utf-8') as f:
        f.write(json.dumps(zapis, ensure_ascii=False) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
