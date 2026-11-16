"""Belezi ispravku hooka posle runde 4 (v2.1) u manifest."""
import hashlib, json, os, sys

sys.path.insert(0, r'C:\posao\diplomski\scripts')
import priprema_poredjenja as p

put = r'C:\poredjenje-orkestrator\manifest.json'
with open(put, encoding='utf-8') as f:
    m = json.load(f)
with open(r'C:\poredjenje-orkestrator\plugin\config\skills\diplomski\hooks\verify_before_stop.py', 'rb') as f:
    otisak = hashlib.sha256(f.read()).hexdigest()
m['plugin_v2_1'] = {'datum': '2026-11-12', 'posle': 'runde 4', 'fajlovi': {'hooks/verify_before_stop.py': otisak},
                    'razlog': 'hook je javljao "RADI JOS" i za agenta koji je vec predao izvestaj, a obavestenje o zadatku jos nije stiglo'}
p.upisi(put, json.dumps(m, ensure_ascii=False, indent=1) + '\n')
print('upisano', otisak[:12])
