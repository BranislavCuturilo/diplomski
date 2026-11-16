# -*- coding: utf-8 -*-
"""Stop: dve stvari pre kraja reda.

1. Ne dozvoljava kraj rada ako je u ovoj sesiji menjan .py kod, a testovi nisu pokrenuti. Cita i
   transkripte podagenata iste sesije: kod i testove u izradi sa agentima pisu i pokrecu oni.
   Odbija JEDNOM (stop_hook_active sprecava petlju), sa razlogom koji agent cita.
2. Ako podagenti pokrenuti u pozadini jos rade, coveku ispisuje da rad nije gotov i da se sesija sama
   nastavlja. Ne blokira: blokada bi naterala agenta da "ceka" pisanjem, sto je petlja.
"""
import glob, json, os, re, sys

TEST_KOMANDA = re.compile(r'(pytest|manage\.py test|python -m unittest|playwright test|tools/test_summary\.py)')
SHELL = ('Bash', 'PowerShell')
IZMENA = ('Edit', 'Write', 'MultiEdit')
POZADINA = re.compile(r'Async agent launched|working in the background', re.I)
AGENT_ID = re.compile(r'agentId:\s*(\w+)')
PREDAO = re.compile(r'<agent-message from="(\w+)">\s*\[Subagent hand-back\]')
OBAVESTENJE = re.compile(r'<tool-use-id>([^<]+)</tool-use-id>.*?<status>(completed|failed|killed|stopped|error)</status>', re.S)


def transkripti(put):
    return [put] + sorted(glob.glob(os.path.join(os.path.splitext(put)[0], 'subagents', '**', '*.jsonl'), recursive=True))


def zapisi(fajl):
    with open(fajl, encoding='utf-8', errors='replace') as f:
        for red in f:
            try:
                yield json.loads(red)
            except ValueError:
                continue


def delovi(z):
    sadrzaj = (z.get('message') or {}).get('content')
    if isinstance(sadrzaj, str):
        return [{'type': 'text', 'text': sadrzaj}]
    return [d for d in sadrzaj or [] if isinstance(d, dict)]


def tekst_dela(d):
    if d.get('type') == 'text':
        return d.get('text') or ''
    sadrzaj = d.get('content')
    if isinstance(sadrzaj, list):
        return ' '.join(x.get('text', '') for x in sadrzaj if isinstance(x, dict))
    return sadrzaj if isinstance(sadrzaj, str) else ''


def kod_i_testovi(put):
    menjan_kod = pokrenuti_testovi = False
    for fajl in transkripti(put):
        for z in zapisi(fajl):
            for d in delovi(z):
                if d.get('type') != 'tool_use':
                    continue
                ulaz = d.get('input') or {}
                if d.get('name') in IZMENA and str(ulaz.get('file_path', '')).lower().endswith('.py'):
                    menjan_kod = True
                if d.get('name') in SHELL and TEST_KOMANDA.search(str(ulaz.get('command', ''))):
                    pokrenuti_testovi = True
    return menjan_kod, pokrenuti_testovi


def agenti_u_toku(put):
    """Opisi podagenata iz glavnog transkripta koji su pokrenuti u pozadini, a nema obavestenja da su stali."""
    pokrenuti, u_pozadini, gotovi, agent_id = {}, set(), set(), {}
    for z in zapisi(put):
        for d in delovi(z):
            tekst = tekst_dela(d)
            if d.get('type') == 'tool_use' and d.get('name') in ('Agent', 'Task'):
                pokrenuti[d.get('id')] = (d.get('input') or {}).get('description') or (d.get('input') or {}).get('subagent_type') or 'agent'
            elif d.get('type') == 'tool_result' and POZADINA.search(tekst):
                u_pozadini.add(d.get('tool_use_id'))
                m = AGENT_ID.search(tekst)
                if m:
                    agent_id[m.group(1)] = d.get('tool_use_id')
            if '<task-notification>' in tekst:
                gotovi.update(m.group(1).strip() for m in OBAVESTENJE.finditer(tekst))
            # Predat izvestaj je kraj rada agenta, i kada obavestenje o zadatku stigne tek posle.
            gotovi.update(agent_id.get(m.group(1), '') for m in PREDAO.finditer(tekst))
    return [pokrenuti[i] for i in pokrenuti if i in u_pozadini and i not in gotovi]


def main():
    try:
        ulaz = json.load(sys.stdin)
    except ValueError:
        return 0
    put = ulaz.get('transcript_path')
    if not put or not os.path.exists(put):
        return 0
    izlaz = {}
    u_toku = agenti_u_toku(put)
    if u_toku:
        izlaz['systemMessage'] = ('RADI JOS: %d podagent(a): %s. Sesija se sama nastavlja kada zavrse; '
                                  'ne treba nista da pises.' % (len(u_toku), ', '.join(u_toku)))
    # Dok agenti rade, testovi bi isli nad nedovrsenim kodom (poredjenje 2026-11-12: 510 pokrenuto, 19 palo).
    # stop_hook_active: vec smo jednom odbili; ne vrti u krug.
    if not ulaz.get('stop_hook_active') and not u_toku:
        menjan_kod, pokrenuti_testovi = kod_i_testovi(put)
        if menjan_kod and not pokrenuti_testovi:
            # hook dobija CLAUDE_PLUGIN_ROOT u okruzenju; Bash alat agenta ga NEMA, pa saljemo punu putanju
            alat = os.path.join(os.environ.get('CLAUDE_PLUGIN_ROOT', '<plugin>'), 'tools', 'test_summary.py')
            izlaz.update({'decision': 'block',
                          'reason': 'Menjan je Python kod, a testovi nisu pokrenuti. Pokreni '
                                    'python "%s" i navedi ishod u izvestaju.' % alat.replace('\\', '/')})
    if izlaz:
        print(json.dumps(izlaz, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
