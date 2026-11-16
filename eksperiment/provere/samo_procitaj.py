"""Samo cita procese Cursor-a: koji profil koristi koji proces i koje okruzenje ima. Nista ne otvara."""
import collections, re, sys
import psutil

sys.stdout.reconfigure(encoding='utf-8')
zbir = collections.Counter()
for p in psutil.process_iter(['name', 'cmdline']):
    if (p.info['name'] or '').lower() != 'cursor.exe':
        continue
    cmd = ' '.join(p.info['cmdline'] or [])
    if 'utility-sub-type=node.mojom.NodeService' not in cmd:
        continue
    try:
        e = p.environ()
    except psutil.Error:
        continue
    m = re.search(r'--user-data-dir=("[^"]+"|\S+)', cmd)
    profil = m.group(1).strip('"') if m else 'obican profil'
    profil = 'POSEBAN PROFIL' if 'poredjenje' in profil.lower() else 'obican prijavljeni profil'
    zbir[(profil, e.get('CLAUDE_CONFIG_DIR') or 'bez strane')] += 1
for (profil, config), n in sorted(zbir.items()):
    print('%-26s | %-45s | procesa %d' % (profil, config, n))
