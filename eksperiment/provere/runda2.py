"""Jednokratno: priprema runde 2 u postojecem poredjenju.

Upisuje tri nova upita, prenosi u snimak plugina pravila o obimu kontrolnog skupa (qa, security,
craft-delegiranje), osvezava CLAUDE.md projekta plugina i belezi sve u manifest.
"""
import hashlib, json, os, shutil, sys

sys.path.insert(0, r'C:\posao\diplomski\scripts')
import priprema_poredjenja as p
import novi_projekat as n

KOREN = r'C:\poredjenje-orkestrator'
SNIMAK = os.path.join(KOREN, 'plugin', 'config', 'skills', 'diplomski')
DELOVI = [os.path.join('agents', 'qa.md'), os.path.join('agents', 'security.md'),
          os.path.join('skills', 'opsti-sloj', 'craft-delegiranje', 'SKILL.md'), os.path.join('scripts', 'novi_projekat.py')]
otisci = {}
for deo in DELOVI:
    shutil.copyfile(os.path.join(p.PLUGIN, deo), os.path.join(SNIMAK, deo))
    with open(os.path.join(SNIMAK, deo), 'rb') as f:
        otisci[deo.replace(os.sep, '/')] = hashlib.sha256(f.read()).hexdigest()

claude_md = os.path.join(KOREN, 'plugin', 'projekat', 'CLAUDE.md')
p.upisi(claude_md, n.CLAUDE_MD.replace('<plugin>', SNIMAK.replace('\\', '/')))

for ime, tekst in p.UPITI_FAJLOVI:
    p.upisi(os.path.join(KOREN, ime), tekst + '\n')

put = os.path.join(KOREN, 'manifest.json')
with open(put, encoding='utf-8') as f:
    m = json.load(f)
m['upiti'] = dict(p.UPITI_FAJLOVI)
m['dopuna_pre_runde_2'] = {'datum': '2026-11-10', 'fajlovi': otisci, 'claude_md_projekta': 'dodat red o obimu kontrolnog skupa',
                           'razlog': 'odluka coveka: qa i security posle izmene proveravaju samo ono sto je izmenom pogodjeno'}
p.upisi(put, json.dumps(m, ensure_ascii=False, indent=1) + '\n')
print('snimak azuriran:', ', '.join(otisci))
print(open(claude_md, encoding='utf-8').read().split('## Raspored')[1][-260:])
