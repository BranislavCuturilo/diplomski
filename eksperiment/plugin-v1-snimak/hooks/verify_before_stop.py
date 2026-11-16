# -*- coding: utf-8 -*-
"""Stop: ne dozvoljava kraj rada ako je u ovoj sesiji menjan .py kod, a testovi nisu pokrenuti.

Cita i transkripte podagenata iste sesije: kod i testove u izradi sa agentima pisu i pokrecu oni.
Odbija JEDNOM (stop_hook_active sprecava petlju), sa razlogom koji agent cita.
"""
import glob, json, os, re, sys

TEST_KOMANDA = re.compile(r'(pytest|manage\.py test|python -m unittest|playwright test|tools/test_summary\.py)')
SHELL = re.compile(r'"name":\s*"(Bash|PowerShell)"')


def transkripti(put):
    return [put] + sorted(glob.glob(os.path.join(os.path.splitext(put)[0], 'subagents', '**', '*.jsonl'), recursive=True))


def main():
    try:
        ulaz = json.load(sys.stdin)
    except ValueError:
        return 0
    if ulaz.get('stop_hook_active'):
        return 0                                   # vec smo jednom odbili; ne vrti u krug
    put = ulaz.get('transcript_path')
    if not put or not os.path.exists(put):
        return 0
    menjan_kod = pokrenuti_testovi = False
    for fajl in transkripti(put):
        with open(fajl, encoding='utf-8', errors='replace') as f:
            for red in f:
                if '"tool_use"' not in red:
                    continue
                if re.search(r'"name":\s*"(Edit|Write)"', red) and '.py' in red:
                    menjan_kod = True
                if SHELL.search(red) and TEST_KOMANDA.search(red):
                    pokrenuti_testovi = True
    if menjan_kod and not pokrenuti_testovi:
        # hook dobija CLAUDE_PLUGIN_ROOT u okruzenju; Bash alat agenta ga NEMA, pa saljemo punu putanju
        alat = os.path.join(os.environ.get('CLAUDE_PLUGIN_ROOT', '<plugin>'), 'tools', 'test_summary.py')
        print(json.dumps({'decision': 'block',
                          'reason': 'Menjan je Python kod, a testovi nisu pokrenuti. Pokreni '
                                    'python "%s" i navedi ishod u izvestaju.' % alat.replace('\\', '/')},
                         ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
