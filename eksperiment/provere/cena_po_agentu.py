"""Cena strane sa pluginom po agentu, ukupno i po fazi (plan, izrada, stil). Cita transkripte, nista ne menja."""
import bisect, collections, json, os, re, sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'C:\posao\diplomski\scripts')
import izvestaj_faza as izv
import priprema_poredjenja as p

projekat = r'C:\poredjenje-orkestrator\plugin\projekat'
folder = os.path.join(r'C:\poredjenje-orkestrator\plugin\config\projects', izv.slug(projekat))
poruke, upiti, _, _, _ = izv.prikupi(folder, 1800)
cene, _ = izv.ucitaj_cene(os.path.join(p.PLUGIN, 'scripts', 'cene.json'))

granice = [('planiranje', min(t for t, _, _, _ in upiti))]
for ime, upit in p.PROPISANI_UPITI:
    t = min((t for t, _, _, tekst in upiti if upit[:40] in tekst), default=None)
    if t:
        granice.append((ime, t))
granice.sort(key=lambda x: x[1])
pocetci = [t for _, t in granice]

zbir = collections.defaultdict(lambda: {'cena': 0.0, 'izlaz': 0, 'tokeni': 0, 'poruka': 0, 'pokretanja': set(), 'modeli': set()})
for por in poruke.values():
    i = bisect.bisect_right(pocetci, por['t']) - 1
    faza = granice[max(i, 0)][0]
    for kljuc in ((por['agent'], faza), (por['agent'], 'ukupno')):
        z = zbir[kljuc]
        z['cena'] += izv.cena_poruke(por['tok'], cene.get(por['model'])) or 0.0
        z['izlaz'] += por['tok']['izlaz']
        z['tokeni'] += sum(por['tok'].values())
        z['poruka'] += 1
        z['pokretanja'].add(por['pokretanje'])
        z['modeli'].add(por['model'].replace('claude-', ''))

faze = [ime for ime, _ in granice]
agenti = sorted({a for a, _ in zbir}, key=lambda a: -zbir[(a, 'ukupno')]['cena'])
ukupno = sum(zbir[(a, 'ukupno')]['cena'] for a in agenti)
izlaz = {'faze': faze, 'agenti': []}
for a in agenti:
    u = zbir[(a, 'ukupno')]
    red = {'agent': a, 'modeli': sorted(u['modeli']), 'pokretanja': len(u['pokretanja']), 'poruka': u['poruka'], 'izlaz': u['izlaz'],
           'cena': round(u['cena'], 2), 'udeo': round(100 * u['cena'] / ukupno, 1),
           'po_fazi': {f: round(zbir[(a, f)]['cena'], 2) if (a, f) in zbir else 0.0 for f in faze},
           'pokretanja_po_fazi': {f: len(zbir[(a, f)]['pokretanja']) if (a, f) in zbir else 0 for f in faze}}
    izlaz['agenti'].append(red)
izlaz['ukupno'] = round(ukupno, 2)
izlaz['po_fazi'] = {f: round(sum(zbir[(a, f)]['cena'] for a in agenti if (a, f) in zbir), 2) for f in faze}
print(json.dumps(izlaz, ensure_ascii=False, indent=1))
