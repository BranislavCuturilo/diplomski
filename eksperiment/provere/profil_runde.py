"""Profil jedne runde: trajanje glavne sesije i podagenata, alati, pozivi faza.py, skillovi, pokretanja testova i njihovo trajanje.

Pokretanje: python profil_runde.py <id glavne sesije prazne> <id glavne sesije plugina>
"""
import collections, datetime as dt, glob, json, os, re, sys

KOREN = r'C:\poredjenje-orkestrator'
TEST = re.compile(r'test_summary|manage\.py test')


def t(s):
    return dt.datetime.fromisoformat(s.replace('Z', '+00:00'))


for strana, glavni in (('prazan', sys.argv[1]), ('plugin', sys.argv[2])):
    osnova = glob.glob(os.path.join(KOREN, strana, 'config', 'projects', '*', glavni + '.jsonl'))[0]
    for f in [osnova] + sorted(glob.glob(os.path.join(os.path.splitext(osnova)[0], 'subagents', '*.jsonl'))):
        L = [json.loads(red) for red in open(f, encoding='utf-8')]
        ts = [z['timestamp'] for z in L if z.get('timestamp')]
        alati, testovi, skillovi, faza, pozivi, trajanja = collections.Counter(), [], [], 0, {}, []
        for z in L:
            if z.get('type') == 'assistant':
                for p in z['message']['content']:
                    if p.get('type') != 'tool_use':
                        continue
                    alati[p['name']] += 1
                    pozivi[p['id']] = (z['timestamp'], p)
                    komanda = str(p['input'].get('command', ''))
                    if TEST.search(komanda):
                        testovi.append(z['timestamp'][11:19])
                    if 'faza.py' in komanda:
                        faza += 1
                    if p['name'] == 'Skill':
                        skillovi.append(p['input'].get('skill'))
            if z.get('type') == 'user' and isinstance(z['message'].get('content'), list):
                for d in z['message']['content']:
                    if d.get('type') == 'tool_result' and d.get('tool_use_id') in pozivi:
                        t0, p = pozivi[d['tool_use_id']]
                        if TEST.search(str(p['input'].get('command', ''))):
                            trajanja.append(round((t(z['timestamp']) - t(t0)).total_seconds()))
        meta = os.path.splitext(f)[0] + '.meta.json'
        ime = json.load(open(meta, encoding='utf-8'))['agentType'] if os.path.exists(meta) else 'glavna'
        print('== %s %s: %s-%s (%.1f min)' % (strana, ime, min(ts)[11:19], max(ts)[11:19], (t(max(ts)) - t(min(ts))).total_seconds() / 60))
        print('   alati', dict(alati.most_common(8)), '| faza.py', faza, '| skillovi', skillovi)
        print('   testovi pokrenuti', testovi, '| trajanje (s)', trajanja)
