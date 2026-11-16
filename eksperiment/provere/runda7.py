"""Jednokratno: prenosi plugin v2.4 u snimak strane plugin, upisuje upit runde 7 i belezi sve u manifest."""
import hashlib, json, os, shutil, subprocess, sys

sys.path.insert(0, r'C:\posao\diplomski\scripts')
import priprema_poredjenja as p

KOREN = r'C:\poredjenje-orkestrator'
SNIMAK = os.path.join(KOREN, 'plugin', 'config', 'skills', 'diplomski')
promene = subprocess.run(['git', 'diff', '--name-only', 'plugin-v2.3'], cwd=p.PLUGIN, capture_output=True, text=True, check=True).stdout.split()
novi = subprocess.run(['git', 'ls-files', '--others', '--exclude-standard', 'tools'], cwd=p.PLUGIN, capture_output=True, text=True, check=True).stdout.split()
deo_plugina = [d for d in promene + novi if d.split('/')[0] in ('agents', 'hooks', 'skills', 'tools') or d == 'scripts/novi_projekat.py']
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
    if ime == 'UPIT-13-pet.txt':
        p.upisi(os.path.join(KOREN, ime), tekst + '\n')

put = os.path.join(KOREN, 'manifest.json')
with open(put, encoding='utf-8') as f:
    m = json.load(f)
m['upiti'] = dict(p.UPITI_FAJLOVI)
m['plugin_v2_4'] = {
    'datum': '2026-11-12', 'rezervna_kopija': 'git oznaka plugin-v2.3 (4ef56a0)', 'fajlovi': otisci,
    'projekat': 'CLAUDE.md (red o paralelnom rezimu) dopunjen rukom',
    'izmene': ['tools/mapa.py: mapa projekta iz koda (rute, modeli i polja, moduli, sabloni, testovi, migracije, prevodi)',
               'paralelni rezim za 3 ili vise nezavisnih zadataka: glavna sesija cita mapu, commit osnove, radnici u '
               'worktree-ovima u jednoj poruci, model po zadatku (sonnet; opus za prijavu, prava, novac, poene), '
               'spajanje grana u glavnoj sesiji, jedna kontrola nad spojenim kodom'],
    'okruzenje': 'ekstenzija Claude Code se sama azurirala sa 2.1.319 na 2.1.322 (2026-11-12 12:42), isto na obe strane',
    'runda_7': 'nove sesije bez konteksta; Opus 5.5 high izabran u panelu, isto na obe strane; brzina se meri i bez vremena automatskih testova',
}
p.upisi(put, json.dumps(m, ensure_ascii=False, indent=1) + '\n')
print('snimak azuriran:', len(otisci), 'fajlova')
print('\n'.join(sorted(otisci)))
