"""Rang lista u pravom pregledacu, na KOPIJI projekta: XSS ime, ocena i broj redova kako ih korisnik vidi.

Pokretanje: <venv strane>\\python provera_ranga_pregledac.py <projekat> <prazan|plugin> <port>
"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request

IZVOR, STRANA, PORT = sys.argv[1], sys.argv[2], int(sys.argv[3])
KOPIJA = os.path.join(tempfile.mkdtemp(), 'projekat')
shutil.copytree(IZVOR, KOPIJA, ignore=shutil.ignore_patterns('*.sqlite3', '__pycache__', '.claude', 'venv'))
env = dict(os.environ, DJANGO_SETTINGS_MODULE='orkestrator.settings', PYTHONIOENCODING='utf-8')
subprocess.run([sys.executable, 'manage.py', 'migrate', '--noinput', '-v', '0'], cwd=KOPIJA, env=env, check=True)

ZLO = '<img src=x onerror=window.__x=1>'
UNOS = r'''
import datetime, sys
sys.path.insert(0, '.')
import django; django.setup()
from django.utils import timezone
from igra.models import Rezultat
STRANA = %r; ZLO = %r
imena = [ZLO[:20] if STRANA == 'plugin' else ZLO] + ['Igrac%%02d' %% i for i in range(1, 12)]
for i, ime in enumerate(imena):
    poeni = 90 - i * 5
    if STRANA == 'prazan':
        from igra.models import Partija
        Rezultat.objects.create(partija=Partija.objects.create(seme='s%%d' %% i), ime=ime, poeni=poeni, ocena='Проба оцене')
    else:
        Rezultat.objects.create(ime=ime, poeni=poeni, ocena='Проба оцене', partija='h%%d' %% i)
print(Rezultat.objects.count())
''' % (STRANA, ZLO)
subprocess.run([sys.executable, '-c', UNOS], cwd=KOPIJA, env=env, check=True)

server = subprocess.Popen([sys.executable, 'manage.py', 'runserver', f'127.0.0.1:{PORT}', '--noreload'], cwd=KOPIJA, env=env,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{PORT}/', timeout=1); break
        except Exception:
            time.sleep(0.5)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        s = b.new_page()
        greske = []
        s.on('pageerror', lambda e: greske.append(str(e)))
        s.goto(f'http://127.0.0.1:{PORT}/'); s.wait_for_load_state('networkidle')
        tekst = s.inner_text('body')
        ime_prikazano = ZLO[:20] if STRANA == 'plugin' else ZLO
        rezultat = {
            'strana': STRANA,
            'xss_izvrsen': s.evaluate('window.__x === 1'),
            'img_src_x_u_dom': s.evaluate('document.querySelectorAll("img[src=\\"x\\"]").length'),
            'zlo_ime_vidljivo_kao_tekst': ime_prikazano in tekst,
            'ocena_vidljiva': 'Проба оцене' in tekst,
            'vidljivih_igraca': sorted({n for n in __import__('re').findall(r'Igrac\d\d', tekst)}),
            'js_greske': greske,
        }
        b.close()
finally:
    server.terminate()
rezultat['ok'] = (not rezultat['xss_izvrsen'] and rezultat['img_src_x_u_dom'] == 0 and rezultat['zlo_ime_vidljivo_kao_tekst']
                  and rezultat['ocena_vidljiva'] and len(rezultat['vidljivih_igraca']) == 9 and not rezultat['js_greske'])
print(json.dumps(rezultat, ensure_ascii=False))
