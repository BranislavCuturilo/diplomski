import json, sys

sys.stdout.reconfigure(encoding='utf-8')
d = json.load(open(r'C:\poredjenje-orkestrator\rezultati\plugin\izvestaj_faza.json', encoding='utf-8'))
print('po agentu')
for r in sorted(d['po_agentu'], key=lambda x: -(x['cena_usd'] or 0)):
    print('%-18s pokretanja %2d poruka %3d aktivno %6.0f s izlaz %7d cena %.2f' % (r['agent'], r['pokretanja'], r['poruka'], r['trajanje_s'], r['izlaz'], r['cena_usd']))
print('po fazi')
for r in d['po_fazi']:
    print('%-16s aktivno %6.0f s izlaz %7d cena %.2f zidno %s' % (r['faza'], r['trajanje_s'], r['izlaz'], r['cena_usd'], d['zidno_s_po_fazi'].get(r['faza'])))
print('vracanja', d['vracanja_na_doradu'], 'tudje izmene', d['tudje_izmene_po_fazi'])
p = json.load(open(r'C:\poredjenje-orkestrator\rezultati\poredjenje.json', encoding='utf-8'))['strane']
for s in ('prazan', 'plugin'):
    u = p[s]['ukupno']
    print(s, {k: u[k] for k in ('zidno_s', 'rad_s', 'cekanje_coveka_s', 'tokeni_ukupno', 'izlaz', 'cena_usd', 'poruka')}, p[s]['planiranje'], p[s]['izrada'], p[s]['cistoca'])
a, b = p['prazan']['ukupno'], p['plugin']['ukupno']
print('odnosi: zidno %.1f rad %.1f tokeni %.1f izlaz %.1f cena %.1f poruke %.1f' % (b['zidno_s'] / a['zidno_s'], b['rad_s'] / a['rad_s'], b['tokeni_ukupno'] / a['tokeni_ukupno'], b['izlaz'] / a['izlaz'], b['cena_usd'] / a['cena_usd'], b['poruka'] / a['poruka']))
x, y = p['prazan']['izrada'], p['plugin']['izrada']
print('izrada: rad %.1f cena %.1f' % (y['trajanje_s'] / x['trajanje_s'], y['cena_usd'] / x['cena_usd']))
