"""Jednokratno: prenosi plugin v2 u snimak strane plugin, upisuje upit runde 4 i belezi sve u manifest."""
import hashlib, json, os, shutil, subprocess, sys

sys.path.insert(0, r'C:\posao\diplomski\scripts')
import priprema_poredjenja as p

KOREN = r'C:\poredjenje-orkestrator'
SNIMAK = os.path.join(KOREN, 'plugin', 'config', 'skills', 'diplomski')
promene = subprocess.run(['git', 'diff', '--name-only', 'plugin-v1'], cwd=p.PLUGIN, capture_output=True, text=True, check=True).stdout.split()
deo_plugina = [d for d in promene if d.split('/')[0] in ('agents', 'hooks', 'skills') or d == 'scripts/novi_projekat.py']
otisci = {}
for deo in deo_plugina:
    izvor = os.path.join(p.PLUGIN, *deo.split('/'))
    cilj = os.path.join(SNIMAK, *deo.split('/'))
    shutil.copyfile(izvor, cilj)
    with open(cilj, 'rb') as f, open(izvor, 'rb') as g:
        assert f.read() == g.read(), deo
    with open(cilj, 'rb') as f:
        otisci[deo] = hashlib.sha256(f.read()).hexdigest()

for ime, tekst in p.UPITI_FAJLOVI:
    if ime == 'UPIT-10-izazov.txt':
        p.upisi(os.path.join(KOREN, ime), tekst + '\n')

put = os.path.join(KOREN, 'manifest.json')
with open(put, encoding='utf-8') as f:
    m = json.load(f)
m['upiti'] = dict(p.UPITI_FAJLOVI)
m['plugin_v2'] = {
    'datum': '2026-11-12', 'rezervna_kopija': 'git oznaka plugin-v1; snimak C:\\poredjenje-orkestrator\\plugin-v1-snimak',
    'fajlovi': otisci,
    'projekat': 'CLAUDE.md (raspored, prag, pitanja) i .claude/skills/projekat-standardi (pravilo 0) dopunjeni rukom',
    'izmene': ['security max->high; qa opus->sonnet; backend-senior xhigh->high',
               'na doradu samo visoki i srednji nalazi; najvise jedna ponovna provera',
               'prag delegiranja: do 5 datoteka bez prijave, novca, seme sa podacima i isporuke radi glavna sesija',
               'pravila unapred: brojac prijava u bazi, stanje u bazi, DEBUG, nevidljivi znakovi, srpska mnozina',
               'standard je podrazumevana vrednost; zahtev klijenta ga menja bez pitanja',
               'najvise jedan dijalog sa 4 pitanja; ostalo kao odluke za potvrdu',
               'hook: poruka coveku dok podagenti rade; ispravljen .py u verify_before_stop i agent-message u log_prompt'],
    'runda_4': 'nove sesije bez konteksta na obe strane; model i nivo bira covek u panelu (Sonnet 5.5, medium), isto na obe strane',
}
p.upisi(put, json.dumps(m, ensure_ascii=False, indent=1) + '\n')
print('snimak azuriran:', len(otisci), 'fajlova')
print('\n'.join(sorted(otisci)))
