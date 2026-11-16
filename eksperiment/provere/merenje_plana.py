"""Racuna tokene i cenu iz transkripata obe strane u trenutku merenja. Nista ne menja u okruzenju strana."""
import json, os, re, subprocess, sys

sys.stdout.reconfigure(encoding='utf-8')
KOREN = r'C:\poredjenje-orkestrator'
IZLAZ = r'C:\Users\Bane\AppData\Local\Temp\claude\33eca44072f7cf40\768d5202-03fd-4f4e-b69e-7374a535513f\scratchpad\plan-merenje'
SKRIPTA = r'C:\posao\diplomski\scripts\izvestaj_faza.py'
env = {k: v for k, v in os.environ.items() if k != 'CLAUDE_PROJECT_DIR'}
for s in ('prazan', 'plugin'):
    projekat = os.path.join(KOREN, s, 'projekat')
    folder = os.path.join(KOREN, s, 'config', 'projects', re.sub(r'[^a-zA-Z0-9]', '-', projekat))
    r = subprocess.run([sys.executable, '-B', SKRIPTA, '--projekat', projekat, '--transkripti', folder, '--izlaz', os.path.join(IZLAZ, s)],
                       capture_output=True, text=True, encoding='utf-8', env=env)
    if r.returncode:
        print(s, 'PAO', r.stderr[-300:])
        continue
    with open(os.path.join(IZLAZ, s, 'izvestaj_faza.json'), encoding='utf-8') as f:
        d = json.load(f)
    u = d['ukupno']
    print('==', s, 'fajlova', d['statistika'].get('fajlova'))
    print({k: u[k] for k in ('zidno_s', 'rad_s', 'cekanje_coveka_s', 'aktivno_s', 'poruka', 'pokretanja', 'upita_coveka', 'dodatnih_upita', 'pitanja_alatom',
                             'podpitanja_coveku', 'ulaz', 'izlaz', 'cache_citanje', 'cache_upis_5m', 'cache_upis_1h', 'tokeni_ukupno', 'izlaz_po_minutu', 'cena_usd')})
    print('po upitu', [{**{k: r_[k] for k in ('upit', 'trajanje_s', 'cekanje_s', 'poruka', 'tokeni', 'cena_usd')}, 'tekst': r_['tekst'][:45]} for r_ in d['po_upitu']])
    print('po modelu', [{k: r_[k] for k in ('model', 'ulaz', 'izlaz', 'cache_citanje', 'cache_upis_5m', 'cache_upis_1h', 'cena_usd')} for r_ in d['po_modelu']])
    print('po agentu', [{k: r_[k] for k in ('agent', 'poruka', 'pokretanja', 'trajanje_s', 'izlaz', 'cena_usd')} for r_ in d['po_agentu']])
    print('po fazi', [{k: r_[k] for k in ('faza', 'trajanje_s', 'izlaz', 'cena_usd')} for r_ in d['po_fazi']], d.get('zidno_s_po_fazi'))
    print('prvi upit zaglavlje:', d['po_upitu'][0]['tekst'][:90] if d['po_upitu'] else None)
