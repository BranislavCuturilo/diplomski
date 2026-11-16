"""Jednokratno: prenosi plugin v2.2 u snimak strane plugin, upisuje upit runde 5 i belezi sve u manifest."""
import hashlib, json, os, shutil, subprocess, sys

sys.path.insert(0, r'C:\posao\diplomski\scripts')
import priprema_poredjenja as p

KOREN = r'C:\poredjenje-orkestrator'
SNIMAK = os.path.join(KOREN, 'plugin', 'config', 'skills', 'diplomski')
promene = subprocess.run(['git', 'diff', '--name-only', 'plugin-v2.1'], cwd=p.PLUGIN, capture_output=True, text=True, check=True).stdout.split()
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
    if ime == 'UPIT-11-csv.txt':
        p.upisi(os.path.join(KOREN, ime), tekst + '\n')

put = os.path.join(KOREN, 'manifest.json')
with open(put, encoding='utf-8') as f:
    m = json.load(f)
m['upiti'] = dict(p.UPITI_FAJLOVI)
m['plugin_v2_2'] = {
    'datum': '2026-11-12', 'rezervna_kopija': 'git oznaka plugin-v2.1 (c28c463)', 'fajlovi': otisci,
    'projekat': 'CLAUDE.md (raspored: laki put i pun aparat) dopunjen rukom',
    'izmene': ['laki put do oko 15 datoteka: plan, kod, prevod i testovi u glavnoj sesiji, bez planera i talasa',
               'pun aparat samo za novu aplikaciju, ceo novi jezik ili vecu izmenu',
               'qa uzi: ceo paket, testovi za nove rizike, jedan tok u pregledacu; snimci samo kad se menja izgled',
               'agenti nasledjuju model i nivo glavne sesije (model: inherit), osim security (Opus, high)',
               'translate samo za ceo novi jezik',
               'hook ne trazi testove dok podagenti rade'],
    'runda_5': 'nove sesije bez konteksta; Opus 5.5 na najnizem nivou izabranom u panelu, isto na obe strane',
}
p.upisi(put, json.dumps(m, ensure_ascii=False, indent=1) + '\n')
print('snimak azuriran:', len(otisci), 'fajlova')
print('\n'.join(sorted(otisci)))
