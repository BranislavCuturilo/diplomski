"""Snimci obe igre na 1280, 768 i 375 px i objektivne mere izgleda iz pregledaca.

    python snimci.py <oznaka> <folder prazne igre> <folder igre sa pluginom> <izlaz>

Igre se pokrecu iz KOPIJA (runserver --insecure), pa njihove baze ostaju netaknute.
Mere: greske u konzoli, neuspeli zahtevi, zahtevi van lokalnog servera, slike koje se nisu ucitale,
sirina sadrzaja prema sirini prozora.
"""
import json, os, shutil, socket, subprocess, sys, time
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')
oznaka, izvor_prazan, izvor_plugin, IZLAZ = sys.argv[1:5]
RADNI = os.path.join(IZLAZ, 'radni-' + oznaka)
os.makedirs(IZLAZ, exist_ok=True)
SIRINE = (1280, 768, 375)


def slobodan_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def pokreni(izvor, ime):
    cilj = os.path.join(RADNI, ime)
    if os.path.exists(cilj):
        shutil.rmtree(cilj)
    shutil.copytree(izvor, cilj, ignore=shutil.ignore_patterns('__pycache__'))
    port = slobodan_port()
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith('CLAUDE')}
    p = subprocess.Popen([sys.executable, 'manage.py', 'runserver', '--insecure', '--noreload', '127.0.0.1:%d' % port],
                         cwd=cilj, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            socket.create_connection(('127.0.0.1', port), timeout=0.5).close()
            return p, 'http://127.0.0.1:%d/' % port
        except OSError:
            time.sleep(0.5)
    raise SystemExit('server za %s nije krenuo' % ime)


def izaberi(page):
    for ime in ('model', 'nivo', 'kontekst', 'podela'):
        radio = page.locator('input[name="%s"]' % ime).nth(1 if ime == 'model' else 0)
        page.locator('label[for="%s"]' % radio.get_attribute('id')).click()


def slomljene_slike(page):
    return page.evaluate("""() => [...document.images].filter(i => i.complete && i.naturalWidth === 0).map(i => i.currentSrc || i.src)""")


def igraj(page, url, strana, sirina, mere):
    page.set_viewport_size({'width': sirina, 'height': 900})
    m = {'konzola': [], 'neuspeli': [], 'spoljni': set(), 'slomljene': set(), 'siri_od_prozora': [], 'koraci': 0}
    domacin = urlparse(url).netloc
    page.on('console', lambda p: m['konzola'].append(p.text) if p.type == 'error' else None)
    page.on('pageerror', lambda e: m['konzola'].append(str(e)))
    page.on('requestfailed', lambda r: m['neuspeli'].append(r.url))
    page.on('response', lambda r: m['neuspeli'].append('%d %s' % (r.status, r.url)) if r.status >= 400 and '/potez/' not in r.url else None)
    page.on('request', lambda r: m['spoljni'].add(urlparse(r.url).netloc) if urlparse(r.url).netloc not in (domacin, '') and not r.url.startswith('data:') else None)

    def proveri(ime):
        page.wait_for_timeout(500)
        m['slomljene'].update(slomljene_slike(page))
        if page.evaluate('document.documentElement.scrollWidth') > sirina:
            m['siri_od_prozora'].append(ime)
        page.screenshot(path=os.path.join(IZLAZ, '%s-%s-%d-%s.png' % (oznaka, strana, sirina, ime)), full_page=True)

    page.goto(url)
    page.wait_for_load_state('networkidle')
    nova = page.locator('form[action$="/nova/"] button')
    if not page.locator('#potvrdi').count() and nova.count():
        proveri('pocetak')
        nova.first.click()
        page.wait_for_load_state('networkidle')
    for krug in range(8):
        izaberi(page)
        if krug == 0:
            page.mouse.move(2, 2)
            proveri('izbor')
        with page.expect_response(lambda r: '/potez/' in r.url):
            page.locator('#potvrdi').click()
        m['koraci'] += 1
        if krug == 0:
            page.evaluate('window.scrollTo(0, 0)')
            proveri('posle-poteza')
    rezultat = page.locator('#pogledaj-rezultat')
    if rezultat.count() and rezultat.is_visible():
        rezultat.click()
        page.wait_for_load_state('networkidle')
    proveri('kraj')
    mere['%s-%d' % (strana, sirina)] = {'konzola': len(m['konzola']), 'neuspeli': sorted(set(m['neuspeli'])), 'spoljni': sorted(m['spoljni']),
                                        'slomljene_slike': sorted(m['slomljene']), 'siri_od_prozora': m['siri_od_prozora'], 'odigrano': m['koraci'],
                                        'prve_greske': m['konzola'][:3]}


procesi, mere = [], {}
try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        for strana, izvor in (('prazan', izvor_prazan), ('plugin', izvor_plugin)):
            p, url = pokreni(izvor, strana)
            procesi.append(p)
            for sirina in SIRINE:
                ctx = b.new_context()
                try:
                    igraj(ctx.new_page(), url, strana, sirina, mere)
                except Exception as g:
                    mere['%s-%d' % (strana, sirina)] = {'greska_skripte': str(g)[:300]}
                ctx.close()
        b.close()
finally:
    for p in procesi:
        p.terminate()
with open(os.path.join(IZLAZ, 'mere-%s.json' % oznaka), 'w', encoding='utf-8') as f:
    json.dump(mere, f, ensure_ascii=False, indent=1)
for k, v in mere.items():
    print(k, json.dumps(v, ensure_ascii=False)[:400])
