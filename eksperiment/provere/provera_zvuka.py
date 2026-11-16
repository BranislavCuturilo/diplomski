"""Zvuk u pravom pregledacu, na kopiji projekta: podrazumevano iskljucen, ukljucuje se, izbor prezivi ucitavanje.

Pokretanje: <venv strane>\\python provera_zvuka.py <projekat> <prazan|plugin> <port>
"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request

IZVOR, STRANA, PORT = sys.argv[1], sys.argv[2], int(sys.argv[3])
KOPIJA = os.path.join(tempfile.mkdtemp(), 'projekat')
shutil.copytree(IZVOR, KOPIJA, ignore=shutil.ignore_patterns('*.sqlite3', '*.sqlite3.*', '__pycache__', '.claude', 'venv', '.git', 'staticfiles'))
env = dict(os.environ, DJANGO_SETTINGS_MODULE='orkestrator.settings', PYTHONIOENCODING='utf-8')
subprocess.run([sys.executable, 'manage.py', 'migrate', '--noinput', '-v', '0'], cwd=KOPIJA, env=env, check=True)
A = f'http://127.0.0.1:{PORT}'
server = subprocess.Popen([sys.executable, 'manage.py', 'runserver', f'127.0.0.1:{PORT}', '--noreload', '--insecure'], cwd=KOPIJA, env=env,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
rezultat = {'strana': STRANA}
try:
    for _ in range(60):
        try:
            urllib.request.urlopen(A + '/', timeout=1); break
        except Exception:
            time.sleep(0.5)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch(); s = b.new_page(); greske = []
        s.on('pageerror', lambda e: greske.append(str(e)))
        s.goto(A + '/'); s.wait_for_load_state('networkidle')
        if STRANA == 'prazan':
            s.click('form[action$="/nova/"] button[type=submit]'); s.wait_for_load_state('networkidle')
        dugme = '#zvuk' if STRANA == 'prazan' else '#zvuk-dugme'
        s.wait_for_selector(dugme, state='visible', timeout=10000)
        pre = s.get_attribute(dugme, 'aria-pressed')
        s.click(dugme); s.wait_for_timeout(300)
        posle = s.get_attribute(dugme, 'aria-pressed')
        s.reload(); s.wait_for_load_state('networkidle'); s.wait_for_selector(dugme, state='visible', timeout=10000)
        posle_ucitavanja = s.get_attribute(dugme, 'aria-pressed')
        rezultat.update({'podrazumevano': pre, 'posle_klika': posle, 'posle_ucitavanja': posle_ucitavanja, 'js_greske': greske})
        rezultat['ok'] = pre == 'false' and posle == 'true' and posle_ucitavanja == 'true' and not greske
        b.close()
finally:
    server.terminate()
print(json.dumps(rezultat, ensure_ascii=False))
