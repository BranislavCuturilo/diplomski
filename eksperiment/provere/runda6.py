"""Jednokratno: prenosi plugin v2.3 u snimak strane plugin, upisuje upit runde 6 i belezi sve u manifest."""
import hashlib, json, os, shutil, subprocess, sys

sys.path.insert(0, r'C:\posao\diplomski\scripts')
import priprema_poredjenja as p

KOREN = r'C:\poredjenje-orkestrator'
SNIMAK = os.path.join(KOREN, 'plugin', 'config', 'skills', 'diplomski')
promene = subprocess.run(['git', 'diff', '--name-only', 'plugin-v2.2'], cwd=p.PLUGIN, capture_output=True, text=True, check=True).stdout.split()
deo_plugina = [d for d in promene if d.split('/')[0] in ('agents', 'hooks', 'skills', 'tools') or d == 'scripts/novi_projekat.py']
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
    if ime == 'UPIT-12-prijava.txt':
        p.upisi(os.path.join(KOREN, ime), tekst + '\n')

put = os.path.join(KOREN, 'manifest.json')
with open(put, encoding='utf-8') as f:
    m = json.load(f)
m['upiti'] = dict(p.UPITI_FAJLOVI)
m['plugin_v2_3'] = {
    'datum': '2026-11-12', 'rezervna_kopija': 'git oznaka plugin-v2.2 (9d8f12a)', 'fajlovi': otisci,
    'projekat': 'CLAUDE.md (kontrolni skup) i .claude/skills/projekat-standardi (red o pokretanju testova) dopunjeni rukom',
    'izmene': ['test_summary.py --brzo: bez modula sa pregledacem (388 s -> 37 s na projektu plugina)',
               'brzi paket tokom rada i posle ispravke; ceo paket jednom po upitu, nad konacnim kodom',
               'qa samo kada izmena menja tok kroz pregledac; qa nivo medium, model nasledjen'],
    'runda_6': 'nove sesije bez konteksta; Fable 5.2 na najvisem nivou izabranom u panelu, isto na obe strane',
}
p.upisi(put, json.dumps(m, ensure_ascii=False, indent=1) + '\n')
print('snimak azuriran:', len(otisci), 'fajlova')
print('\n'.join(sorted(otisci)))
