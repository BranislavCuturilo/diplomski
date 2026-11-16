# -*- coding: utf-8 -*-
"""PreToolUse (Bash): odbija git komande koje su vec kostale incident.

Pravila iz skills/opsti-sloj/craft-git.
"""
import json, re, sys

ZABRANE = [
    (r'git\s+push\b.*(--force\b|-f\b|--force-with-lease)', 'force push prepisuje deljenu istoriju (craft-git pravilo 1)'),
    (r'git\s+push\b.*\s(origin\s+)?(main|master)(\s|$)', 'push na main ide kroz pull request, ne direktno'),
    (r'git\s+add\s+(-A|--all|\.)(\s|$)', 'dodaj samo putanje koje si menjao, ne sve (craft-git)'),
    (r'git\s+reset\s+--hard(?!\s+origin/)', 'reset --hard brise lokalni rad; dozvoljeno samo "reset --hard origin/<grana>" u isporuci'),
    (r'git\s+commit\b[^\n]*-m\s+"[^"]*`', 'obrnuti navodnici u -m izvrsava shell; koristi git commit -F <fajl>'),
]


def main():
    try:
        komanda = (json.load(sys.stdin).get('tool_input') or {}).get('command', '')
    except ValueError:
        return 0
    for obrazac, razlog in ZABRANE:
        if re.search(obrazac, komanda):
            print(json.dumps({'hookSpecificOutput': {
                'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
                'permissionDecisionReason': 'Odbijeno: ' + razlog}}, ensure_ascii=False))
            return 0
    return 0


if __name__ == '__main__':
    sys.exit(main())
