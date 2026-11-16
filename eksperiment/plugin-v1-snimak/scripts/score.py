# -*- coding: utf-8 -*-
"""Belezenje i citanje ucinka agenata i skillova.

    python scripts/score.py record agent backend-junior hindered "zaboravio opseg u formi"
    python scripts/score.py show

Pravila:
  - ne belezi se svaka upotreba, samo jasno pomogao (helped) ili jasno smetao (hindered);
  - ocena se racuna tek posle MIN_USES zapisa;
  - povlacenje zbog zabelezenog gubitka, NIKAD zbog retke upotrebe.
"""
import datetime, json, os, sys

sys.stdout.reconfigure(encoding='utf-8')
KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG = os.path.join(KOREN, 'scripts', 'registry.json')
MIN_USES = 5


def ucitaj():
    return json.load(open(REG, encoding='utf-8')) if os.path.exists(REG) else {}


def pojas(z):
    n = z['helped'] + z['hindered'] + z['neutral']
    if n < MIN_USES:
        return 'nedokazan (%d/%d zapisa)' % (n, MIN_USES)
    udeo = z['helped'] / n
    if z['hindered'] > z['helped']:
        return 'za povlacenje'
    return 'dokazan' if udeo >= 0.8 else 'ispravan' if udeo >= 0.5 else 'slab'


def main(a):
    reg = ucitaj()
    if len(a) >= 4 and a[0] == 'record':
        _, vrsta, ime, ishod = a[:4]
        if ishod not in ('helped', 'hindered', 'neutral'):
            sys.exit('ishod: helped | hindered | neutral')
        z = reg.setdefault(vrsta + ':' + ime, {'helped': 0, 'hindered': 0, 'neutral': 0, 'notes': []})
        z[ishod] += 1
        z['notes'].append({'at': datetime.date.today().isoformat(), 'ishod': ishod, 'beleska': ' '.join(a[4:])})
        json.dump(reg, open(REG, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print('zabelezeno:', vrsta, ime, ishod)
    elif a[:1] == ['show']:
        for k, z in sorted(reg.items()):
            print('%-30s +%d -%d =%d  %s' % (k, z['helped'], z['hindered'], z['neutral'], pojas(z)))
    else:
        print(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
