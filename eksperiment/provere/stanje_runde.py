"""Stanje runde: model, nivo, pitanja, agenti, agenti u toku po hooku, kraj i zavrsna poruka.

Pokretanje: python stanje_runde.py <id glavne sesije prazne> <id glavne sesije plugina>
"""
import collections, glob, importlib.util, json, os, re, sys

sp = importlib.util.spec_from_file_location('v', r'C:\posao\diplomski\hooks\verify_before_stop.py')
v = importlib.util.module_from_spec(sp); sp.loader.exec_module(v)
KOREN = r'C:\poredjenje-orkestrator'
for strana, glavni in (('prazan', sys.argv[1]), ('plugin', sys.argv[2])):
    f = glob.glob(os.path.join(KOREN, strana, 'config', 'projects', '*', glavni + '.jsonl'))[0]
    L = [json.loads(red) for red in open(f, encoding='utf-8')]
    modeli = collections.Counter(z['message'].get('model') for z in L if z.get('type') == 'assistant')
    nivo = collections.Counter(m for z in L for m in re.findall(r'"effort[A-Za-z_]*":\s*"(\w+)"', json.dumps(z)))
    pitanja, agenti, ljudski = 0, [], []
    for z in L:
        sadrzaj = (z.get('message') or {}).get('content')
        if z.get('type') == 'assistant':
            for p in sadrzaj:
                if p.get('type') == 'tool_use' and p['name'] == 'AskUserQuestion':
                    pitanja += len(p['input'].get('questions', []))
                if p.get('type') == 'tool_use' and p['name'] in ('Agent', 'Task'):
                    agenti.append((p['input'].get('subagent_type'), p['input'].get('description')))
        if z.get('type') == 'user' and isinstance(sadrzaj, str) and not sadrzaj.startswith(('<', 'Another Claude', 'Stop hook', 'This session')):
            ljudski.append((z['timestamp'][11:19], sadrzaj[:80]))
    pod = collections.Counter()
    for g in glob.glob(os.path.join(os.path.splitext(f)[0], 'subagents', '*.jsonl')):
        for red in open(g, encoding='utf-8'):
            z = json.loads(red)
            if z.get('type') == 'assistant':
                pod[z['message'].get('model')] += 1
    a = [z for z in L if z.get('type') == 'assistant']
    print('== %s | model %s | nivo %s | podagenti %s | pitanja %d' % (strana, dict(modeli), dict(nivo), dict(pod), pitanja))
    print('   agenti:', agenti)
    print('   poruke coveka:', ljudski)
    print('   u toku po hooku:', v.agenti_u_toku(f))
    print('   kraj', a[-1]['timestamp'], a[-1]['message'].get('stop_reason'))
    print('   ' + '\n   '.join(p.get('text', '') for p in a[-1]['message']['content'] if p.get('type') == 'text')[:3000])
