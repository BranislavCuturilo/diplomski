# -*- coding: utf-8 -*-
"""Snimci igre za prezentaciju: simulirana upotreba jedne strane poredjenja u pravom pregledacu.

Radi na KOPIJI projekta sa svezom bazom: upisuje probne partije i moderatora, pa kroz interfejs prolazi
pocetak, krug, zavrsni ekran, deljenu stranu, pravila, engleski, moderatora i telefon.

    <venv strane>\\python scripts/snimci_igre.py <projekat> <prazan|plugin> <izlazni folder> [port]
"""
import json, os, random, shutil, subprocess, sys, tempfile, time, urllib.request

IZVOR, STRANA, IZLAZ = sys.argv[1], sys.argv[2], os.path.abspath(sys.argv[3])
PORT = int(sys.argv[4]) if len(sys.argv) > 4 else 8950
A = 'http://127.0.0.1:%d' % PORT
LOZ = 'Prezentacija-Lozinka-2026'
# Manje od 10 drugih igraca, da i ime sacuvano na snimku 05 bude na rang listi bez obzira na poene.
IMENA = ['Ана', 'Марко', 'Јелена', 'Stefan', 'Милица', 'Nikola']

os.makedirs(IZLAZ, exist_ok=True)
KOPIJA = os.path.join(tempfile.mkdtemp(), 'projekat')
shutil.copytree(IZVOR, KOPIJA, ignore=shutil.ignore_patterns('*.sqlite3', '*.sqlite3.*', '__pycache__', '.claude', 'venv', '.git', 'staticfiles'))
env = dict(os.environ, DJANGO_SETTINGS_MODULE='orkestrator.settings', PYTHONIOENCODING='utf-8')
subprocess.run([sys.executable, 'manage.py', 'migrate', '--noinput', '-v', '0'], cwd=KOPIJA, env=env, check=True)
MODERATOR = '''
import sys; sys.path.insert(0, "."); import django; django.setup()
from django.contrib.auth import get_user_model
if %r == "prazan":
    from igra import moderacija; moderacija.dodaj_moderatora(None, "moderator", %r, %r)
else:
    from igra import nalozi; nalozi.dodaj(None, "moderator", %r, glavni=True)
    u = get_user_model().objects.get(username="moderator"); u.nalog_moderatora.mora_promeniti = False; u.nalog_moderatora.save()
''' % (STRANA, LOZ, LOZ, LOZ)
subprocess.run([sys.executable, '-c', MODERATOR], cwd=KOPIJA, env=env, check=True)
server = subprocess.Popen([sys.executable, 'manage.py', 'runserver', '127.0.0.1:%d' % PORT, '--noreload', '--insecure'],
                          cwd=KOPIJA, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
rng = random.Random(2026)
snimljeno = []


def cekaj_server():
    for _ in range(80):
        try:
            urllib.request.urlopen(A + '/', timeout=1)
            return
        except Exception:
            time.sleep(0.5)


def snimi(s, ime, cela=False):
    s.wait_for_load_state('networkidle'); s.wait_for_timeout(400)
    if cela:
        s.evaluate('window.scrollTo(0, 0)')   # posle klika strana ostaje skrolovana do dugmeta
    put = os.path.join(IZLAZ, ime + '.png')
    s.screenshot(path=put, full_page=cela)
    snimljeno.append(ime)


def snimi_kod(s, ime, lokator, iznad=120):
    """Jedan ekran, skrolovan tako da je lokator pri vrhu: za telefon, gde je cela strana preduga za slajd."""
    s.wait_for_load_state('networkidle'); s.wait_for_timeout(400)
    el = s.locator(lokator).first
    el.scroll_into_view_if_needed()
    s.evaluate('(y) => window.scrollTo(0, Math.max(0, y))', el.evaluate('e => e.getBoundingClientRect().top + window.scrollY') - iznad)
    s.wait_for_timeout(200)
    s.screenshot(path=os.path.join(IZLAZ, ime + '.png'))
    snimljeno.append(ime)


# Razumni izbori (kljucevi iz MVP-a, isti na obe strane), da poeni variraju umesto da svi zavrse na 0.
RAZUMNO = {'model': ('sonnet', 'opus'), 'nivo': ('high',), 'kontekst': ('taman',), 'podela': ('sam',)}
REZULTAT_KRUGA = '#rezultat-poteza' if STRANA == 'prazan' else '#rezultat'   # ceo blok: naslov, cena, minuti, status
RANG_LISTA = '#rang-lista' if STRANA == 'prazan' else '#rang-tabela'


def izaberi_i_potvrdi(s):
    for grupa in ('model', 'nivo', 'kontekst', 'podela'):
        kljuc = rng.choice(RAZUMNO[grupa])
        if s.query_selector('label[for="%s-%s"]' % (grupa, kljuc)) is None:
            kljuc = rng.choice(s.query_selector_all('input[type=radio][name="%s"]' % grupa)).get_attribute('id').split('-', 1)[1]
        s.click('label[for="%s-%s"]' % (grupa, kljuc))


def granice(s, lokator):
    el = s.locator(lokator).first
    return el.evaluate('e => { const r = e.getBoundingClientRect(); return [r.top + window.scrollY, r.bottom + window.scrollY] }')


def snimi_isecak(s, ime, od_vrha=True, do=(), oko=None, pre=80, posle=40):
    """Deo strane: od vrha do najnizeg od lokatora `do`, ili oko jednog lokatora; bez visine cele strane."""
    s.wait_for_load_state('networkidle'); s.wait_for_timeout(400)
    if oko:
        gore, dole = granice(s, oko)
        y = max(0, gore - pre)
    else:
        y, dole = 0, max(granice(s, l)[1] for l in do)
    sirina = s.viewport_size['width']
    s.screenshot(path=os.path.join(IZLAZ, ime + '.png'), full_page=True,
                 clip={'x': 0, 'y': y, 'width': sirina, 'height': dole + posle - y})
    snimljeno.append(ime)


def nova_partija(s):
    s.goto(A + '/'); s.wait_for_load_state('networkidle')
    if STRANA == 'prazan':
        s.click('form[action$="/nova/"] button[type=submit]'); s.wait_for_load_state('networkidle')


def odigraj_do_kraja(s):
    for _ in range(8):
        izaberi_i_potvrdi(s)
        s.click('#potvrdi'); s.wait_for_load_state('networkidle'); s.wait_for_timeout(250)
    if STRANA == 'prazan' and '/kraj/' not in s.url:
        s.goto(A + '/kraj/')


def sacuvaj(s, ime):
    polje, dugme = ('#ime', '#sacuvaj') if STRANA == 'prazan' else ('#rang-ime', '#rang-sacuvaj')
    s.fill(polje, ime); s.click(dugme); s.wait_for_load_state('networkidle'); s.wait_for_timeout(300)


try:
    cekaj_server()
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        # probne partije drugih igraca, da rang lista i statistika nisu prazne
        for ime in IMENA:
            k = b.new_context(); s = k.new_page()
            nova_partija(s); odigraj_do_kraja(s); sacuvaj(s, ime); k.close()

        k = b.new_context(viewport={'width': 1280, 'height': 800}); s = k.new_page()
        s.goto(A + '/'); snimi(s, '01-pocetna', cela=True)
        nova_partija(s); izaberi_i_potvrdi(s); snimi_isecak(s, '02-krug-izbor', do=('#potvrdi',), posle=16)
        s.click('#potvrdi'); s.wait_for_timeout(400); snimi_isecak(s, '03-posle-kruga', do=('#potvrdi', REZULTAT_KRUGA))
        for _ in range(7):
            izaberi_i_potvrdi(s); s.click('#potvrdi'); s.wait_for_load_state('networkidle'); s.wait_for_timeout(250)
        if STRANA == 'prazan' and '/kraj/' not in s.url:
            s.goto(A + '/kraj/')
        snimi(s, '04-zavrsni-ekran', cela=True)
        sacuvaj(s, 'Бранислав'); snimi_isecak(s, '05-rang-lista-posle-cuvanja', oko=RANG_LISTA, posle=8)
        if STRANA == 'prazan':
            s.goto(A + '/kraj/'); url = s.get_attribute('#link-deljenja', 'value')
        else:
            s.click('#deli-dugme'); s.wait_for_timeout(800)
            url = s.evaluate('() => { const e = [...document.querySelectorAll("input, a")].find(x => /\\/r\\//.test(x.value || x.href || "")); return e ? (e.value || e.href) : null }')
        if url:
            d = b.new_context(viewport={'width': 1280, 'height': 800}).new_page(); d.goto(url); snimi(d, '06-deljeni-rezultat', cela=True)
        s.goto(A + '/kako-se-igra/'); snimi(s, '07-kako-se-igra', cela=True)
        e = b.new_context(viewport={'width': 1280, 'height': 800}).new_page()
        e.goto(A + '/'); e.wait_for_load_state('networkidle')
        e.click('#jezik-en' if STRANA == 'prazan' else '#jezik-dugme[value="en"]'); snimi(e, '08-engleski')

        m = b.new_context(viewport={'width': 1280, 'height': 800}).new_page()
        m.goto(A + '/moderator/prijava/'); m.wait_for_load_state('networkidle')
        m.fill('#ime' if STRANA == 'prazan' else 'input[name="username"]', 'moderator')
        polje = '#lozinka' if STRANA == 'prazan' else 'input[name="password"]'
        m.fill(polje, LOZ); m.press(polje, 'Enter'); m.wait_for_load_state('networkidle')
        snimi(m, '09-moderator-pregled', cela=True)
        m.goto(A + '/moderator/statistika/'); snimi(m, '10-moderator-statistika')
        # Jedno brisanje kroz interfejs, da dnevnik ima sta da pokaze: prvo "Obrisi" na pregledu, pa potvrda.
        try:
            m.goto(A + '/moderator/'); m.wait_for_load_state('networkidle')
            m.locator('a:has-text("Обриши"), button:has-text("Обриши")').first.click(); m.wait_for_load_state('networkidle')
            m.locator('form button[type=submit]:has-text("Обриши"), form button[type=submit]:has-text("брисање")').last.click()
            m.wait_for_load_state('networkidle')
        except Exception as greska:
            print('brisanje za dnevnik nije uspelo:', type(greska).__name__, file=sys.stderr)
        m.goto(A + '/moderator/dnevnik/'); snimi(m, '11-moderator-dnevnik')

        t = b.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=2, is_mobile=True, has_touch=True).new_page()
        nova_partija(t); izaberi_i_potvrdi(t); t.evaluate('window.scrollTo(0, 0)'); snimi(t, '12-telefon-krug')
        t.click('#potvrdi'); t.wait_for_timeout(400)
        # Isecak oko rezultata: na praznoj strani je rezultat na dnu strane, pa ga skrol ne dovodi gore.
        snimi_isecak(t, '13-telefon-posle-kruga', oko=REZULTAT_KRUGA, pre=160, posle=24)
        b.close()
finally:
    server.terminate()
print(json.dumps({'strana': STRANA, 'izlaz': IZLAZ, 'snimaka': len(snimljeno), 'snimci': snimljeno}, ensure_ascii=False))
