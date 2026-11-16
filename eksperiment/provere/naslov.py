"""Racunati stil naslova i snimak izabranih opcija, za obe igre. Pokrece kopije, ne dira baze."""
import os, shutil, socket, subprocess, sys, time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')
OVDE = os.path.dirname(os.path.abspath(__file__))
IZLAZ = os.path.join(OVDE, 'snimci')
IGRE = {'prazan': r'C:\poredjenje-orkestrator\prazan\projekat', 'plugin': r'C:\poredjenje-orkestrator\plugin\projekat'}


def pokreni(izvor, ime):
    cilj = os.path.join(IZLAZ, 'radni-naslov', ime)
    if os.path.exists(cilj):
        shutil.rmtree(cilj)
    shutil.copytree(izvor, cilj, ignore=shutil.ignore_patterns('__pycache__'))
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith('CLAUDE')}
    p = subprocess.Popen([sys.executable, 'manage.py', 'runserver', '--insecure', '--noreload', '127.0.0.1:%d' % port],
                         cwd=cilj, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            socket.create_connection(('127.0.0.1', port), timeout=0.5).close()
            return p, 'http://127.0.0.1:%d/' % port
        except OSError:
            time.sleep(0.5)
    raise SystemExit('server nije krenuo')


procesi = []
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        for ime, izvor in IGRE.items():
            p, url = pokreni(izvor, ime)
            procesi.append(p)
            page = b.new_page(viewport={'width': 1280, 'height': 900})
            page.goto(url)
            if ime == 'prazan':
                page.locator('form[action$="/nova/"] button').first.click()
                page.wait_for_selector('#forma-poteza')
            stil = page.evaluate("""() => { const h = document.querySelector('header h1'); const s = getComputedStyle(h);
                return {klase: h.className, boja: s.color, slika: s.backgroundImage.slice(0, 60), clip: s.backgroundClip, wclip: s.webkitBackgroundClip}; }""")
            print(ime, stil)
            for polje in ('model', 'nivo', 'kontekst', 'podela'):
                radio = page.locator('input[name="%s"]' % polje).nth(1)
                page.locator('label[for="%s"]' % radio.get_attribute('id')).click()
            page.mouse.move(5, 5)
            page.wait_for_timeout(500)
            page.screenshot(path=os.path.join(IZLAZ, 'izbor-%s.png' % ime), full_page=False)
        b.close()
finally:
    for p in procesi:
        p.terminate()
