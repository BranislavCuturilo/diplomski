"""Koje je provere izgleda svaka strana sama uradila u fazi stila, iz transkripata. Nista ne menja."""
import glob, json, os, re, sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'C:\posao\diplomski\scripts')
import priprema_poredjenja as p

KOREN = r'C:\poredjenje-orkestrator'
OBRASCI = {
    'sirina 375': r'\b375\b', 'sirina 768': r'\b768\b', 'sirina 1280': r'\b1280\b',
    'snimak ekrana': r'screenshot', 'scrollWidth': r'scrollWidth', 'konzola': r'console|pageerror',
    'naturalWidth / slike': r'naturalWidth', 'pokretanje testova': r'manage\.py test|test_summary',
}
for strana in p.STRANE:
    projekat = os.path.join(KOREN, strana, 'projekat')
    folder = os.path.join(KOREN, strana, 'config', 'projects', re.sub(r'[^a-zA-Z0-9]', '-', projekat))
    fajlovi = sorted(glob.glob(os.path.join(folder, '**', '*.jsonl'), recursive=True))
    pocetak = None
    for put in fajlovi:
        for red in open(put, encoding='utf-8', errors='replace'):
            if p.UPIT_STIL[:40] in red and '"type":"user"' in red.replace(' ', ''):
                z = json.loads(red)
                pocetak = min(pocetak or z['timestamp'], z['timestamp'])
    brojac = {k: 0 for k in OBRASCI}
    alati, agenti, skillovi = 0, [], []
    for put in fajlovi:
        for red in open(put, encoding='utf-8', errors='replace'):
            try:
                z = json.loads(red)
            except ValueError:
                continue
            if z.get('type') != 'assistant' or not pocetak or (z.get('timestamp') or '') < pocetak:
                continue
            for d in (z.get('message') or {}).get('content') or []:
                if not isinstance(d, dict) or d.get('type') != 'tool_use':
                    continue
                alati += 1
                ulaz = json.dumps(d.get('input') or {}, ensure_ascii=False)
                if d.get('name') in ('Task', 'Agent'):
                    agenti.append((d.get('input') or {}).get('subagent_type'))
                if d.get('name') == 'Skill':
                    skillovi.append((d.get('input') or {}).get('skill'))
                for k, o in OBRASCI.items():
                    if re.search(o, ulaz, re.I):
                        brojac[k] += 1
    print('==', strana, 'pocetak faze stila', pocetak, 'poziva alata', alati)
    print('   agenti:', agenti, 'skillovi:', skillovi)
    print('   pozivi alata koji pominju:', brojac)
