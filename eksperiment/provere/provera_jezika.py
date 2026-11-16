"""Nezavisna provera engleske verzije, ista za obe strane: cela partija kroz interfejs pregledaca, na KOPIJI.

Pokretanje: <venv strane>\\python provera_jezika.py <projekat> <prazan|plugin> <port>
Glavna mera: na engleskom ne sme ostati nijedan cirilicni znak u vidljivom tekstu, atributima,
naslovu kartice i dijalozima (osim izbora jezika "Српски" i imena koje je igrac upisao).
"""
import glob, json, os, random, re, shutil, subprocess, sys, tempfile, time, urllib.request

IZVOR, STRANA, PORT = sys.argv[1], sys.argv[2], int(sys.argv[3])
KOPIJA = os.path.join(tempfile.mkdtemp(), 'projekat')
shutil.copytree(IZVOR, KOPIJA, ignore=shutil.ignore_patterns('*.sqlite3', '__pycache__', '.claude', 'venv'))
env = dict(os.environ, DJANGO_SETTINGS_MODULE='orkestrator.settings', PYTHONIOENCODING='utf-8')
subprocess.run([sys.executable, 'manage.py', 'migrate', '--noinput', '-v', '0'], cwd=KOPIJA, env=env, check=True)
A = f'http://127.0.0.1:{PORT}'
CIRILICA = re.compile(r'[Ѐ-ӿ]')
rng = random.Random(5)
rezultati, ostaci = [], {}


def proveri(oznaka, uslov, detalj=''):
    rezultati.append({'provera': oznaka, 'ok': bool(uslov), 'detalj': str(detalj)[:400]})


SAKUPI = '''() => {
  const out = [];
  const vidljiv = e => e && e.checkVisibility ? e.checkVisibility() : !!(e && e.offsetParent);
  const izuzet = e => { const z = e.closest('[lang="sr"], [lang="sr-Cyrl"], .jezik, #jezik-forma, [data-ime-igraca]');
                        return z && z !== document.documentElement && z !== document.body; };
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = w.nextNode())) {
    const p = n.parentElement;
    if (!p || !n.textContent.trim() || ['SCRIPT', 'STYLE', 'TEMPLATE'].includes(p.tagName) || p.closest('template, script')) continue;
    if (!vidljiv(p) || izuzet(p)) continue;
    out.push(n.textContent.trim());
  }
  for (const e of document.querySelectorAll('[title], [alt], [aria-label], [placeholder], input[type=submit], input[type=button]')) {
    if (izuzet(e)) continue;
    for (const a of ['title', 'alt', 'aria-label', 'placeholder', 'value']) {
      const v = e.getAttribute(a);
      if (v && (a !== 'value' || e.type === 'submit' || e.type === 'button')) out.push(`@${a}: ${v}`);
    }
  }
  out.push('@title-kartice: ' + document.title);
  return out;
}'''

server = subprocess.Popen([sys.executable, 'manage.py', 'runserver', f'127.0.0.1:{PORT}', '--noreload'], cwd=KOPIJA, env=env,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        try:
            urllib.request.urlopen(A + '/', timeout=1); break
        except Exception:
            time.sleep(0.5)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        k = b.new_context(locale='sr-RS', extra_http_headers={'Accept-Language': 'sr'})
        s = k.new_page()
        dijalozi, js_greske = [], []
        s.on('dialog', lambda d: (dijalozi.append(d.message), d.accept()))
        s.on('pageerror', lambda e: js_greske.append(str(e)))

        def sakupi(ekran, ime_igraca=None):
            s.wait_for_load_state('networkidle')
            nadjeno = [t for t in s.evaluate(SAKUPI) if CIRILICA.search(t) and (not ime_igraca or ime_igraca not in t)]
            if nadjeno:
                ostaci[ekran] = sorted(set(nadjeno))
            return s.evaluate('document.documentElement.lang')

        def na_engleski():
            if STRANA == 'prazan':
                s.click('#jezik-en')
            else:
                s.click('#jezik-dugme[value="en"]')
            s.wait_for_load_state('networkidle')

        def na_srpski():
            if STRANA == 'prazan':
                s.click('#jezik-sr')
            else:
                s.click('#jezik-dugme[value="sr"]')
            s.wait_for_load_state('networkidle')

        def odigraj_krug():
            for grupa in ('model', 'nivo', 'kontekst', 'podela'):
                radija = s.query_selector_all(f'input[type=radio][name="{grupa}"]')
                izbor = rng.choice(radija)
                s.click(f'label[for="{izbor.get_attribute("id")}"]')
            s.click('#potvrdi')
            s.wait_for_load_state('networkidle'); s.wait_for_timeout(300)

        # 1. pocetak: srpski po podrazumevanju, prelaz na engleski kroz interfejs
        s.goto(A + '/')
        lang0 = sakupi('_srpski_pocetak_ne_broji_se')
        kontrola = len(ostaci.pop('_srpski_pocetak_ne_broji_se', []))
        proveri('kontrola: isti sakupljac na srpskom ekranu nalazi cirilicu', kontrola > 5, f'{kontrola} tekstova')
        proveri('bez izbora (Accept-Language: sr) igra je na srpskom', lang0.startswith('sr'), lang0)
        na_engleski()
        lang = sakupi('pocetna')
        proveri('posle izbora engleskog <html lang> je en', lang.startswith('en'), lang)
        if STRANA == 'prazan':
            s.click('form[action$="/nova/"] button[type=submit]'); s.wait_for_load_state('networkidle')
        sakupi('igra, 1. krug')

        # 2. cela partija na engleskom, sa promenom jezika usred partije
        for krug in range(1, 9):
            odigraj_krug()
            if krug < 8:
                sakupi(f'igra posle {krug}. kruga')
            if krug == 3:
                na_srpski(); na_engleski()
        if STRANA == 'prazan' and '/kraj/' not in s.url:
            s.goto(A + '/kraj/')
        tekst_kraja = s.inner_text('body')
        proveri('promena jezika usred partije ne prekida igru (kraj posle 8 krugova)',
                re.search(r'lesson|score|points|rating', tekst_kraja, re.I) is not None, s.url)
        sakupi('zavrsni ekran (lekcije, napomena)')

        # 3. cuvanje: prazno ime pa pravo ime; rang lista
        polje = '#ime' if STRANA == 'prazan' else '#rang-ime'
        dugme = '#sacuvaj' if STRANA == 'prazan' else '#rang-sacuvaj'
        s.fill(polje, '   ')
        if s.is_enabled(dugme):
            s.click(dugme); s.wait_for_load_state('networkidle'); s.wait_for_timeout(300)
        sakupi('greska pri cuvanju praznog imena')
        if STRANA == 'prazan' and '/kraj/' not in s.url and s.query_selector(polje) is None:
            s.goto(A + '/kraj/')
        s.fill(polje, 'Ana Test')
        s.click(dugme); s.wait_for_load_state('networkidle'); s.wait_for_timeout(500)
        sakupi('rang lista posle cuvanja', 'Ana Test')

        # 4. link za deljenje, na engleskom
        if STRANA == 'prazan':
            s.goto(A + '/kraj/'); url = s.get_attribute('#link-deljenja', 'value')
        else:
            s.click('#deli-dugme'); s.wait_for_timeout(800)
            url = s.input_value('#deli-link') if s.query_selector('#deli-link') else None
            if not url:
                url = s.evaluate('() => { const e = [...document.querySelectorAll("input, a")].find(x => /\\/r\\//.test(x.value || x.href || "")); return e ? (e.value || e.href) : null }')
        sakupi('zavrsni ekran sa linkom')
        proveri('link za deljenje dobijen na engleskom', bool(url), url)

        # 5. pamcenje: nov prozor pregledaca sa istim kolacicima
        kolacici = k.cookies()
        jezicki = [c for c in kolacici if 'jezik' in c['name'] or 'language' in c['name']]
        trajanje = (jezicki[0]['expires'] - time.time()) / 86400 if jezicki and jezicki[0]['expires'] > 0 else 0
        proveri('izbor se pamti u trajnom kolacicu (> 300 dana)', trajanje > 300, f'{[c["name"] for c in jezicki]}, {trajanje:.0f} dana')
        k2 = b.new_context(locale='sr-RS', extra_http_headers={'Accept-Language': 'sr'})
        k2.add_cookies([c for c in jezicki])
        s2 = k2.new_page(); s2.goto(A + '/'); s2.wait_for_load_state('networkidle')
        proveri('nov prozor sa kolacicem jezika otvara engleski', s2.evaluate('document.documentElement.lang').startswith('en'))

        # 6. deljena strana i 404 na jeziku posmatraca
        if url:
            s.goto(url); sakupi('deljena strana (posmatrac na engleskom)', 'Ana Test')
            k3 = b.new_context(locale='sr-RS', extra_http_headers={'Accept-Language': 'sr'})
            s3 = k3.new_page(); s3.goto(url); s3.wait_for_load_state('networkidle')
            proveri('ista deljena strana je srpski posmatracu bez izbora', s3.evaluate('document.documentElement.lang').startswith('sr'))
            s.goto(url.rstrip('/')[:-3] + 'zzz/'); sakupi('deljena strana koja ne postoji (404)')

        # 7. sacuvan srpski zapis gledan na engleskom (ocena je podatak u bazi)
        ks = b.new_context(locale='sr-RS', extra_http_headers={'Accept-Language': 'sr'})
        ss = ks.new_page(); ss.on('dialog', lambda d: d.accept()); ss.goto(A + '/')
        if STRANA == 'prazan':
            ss.click('form[action$="/nova/"] button[type=submit]'); ss.wait_for_load_state('networkidle')
        for _ in range(8):
            for grupa in ('model', 'nivo', 'kontekst', 'podela'):
                izbor = rng.choice(ss.query_selector_all(f'input[type=radio][name="{grupa}"]'))
                ss.click(f'label[for="{izbor.get_attribute("id")}"]')
            ss.click('#potvrdi'); ss.wait_for_load_state('networkidle'); ss.wait_for_timeout(300)
        if STRANA == 'prazan' and '/kraj/' not in ss.url:
            ss.goto(A + '/kraj/')
        ss.fill(polje, 'Sara Srpski'); ss.click(dugme); ss.wait_for_load_state('networkidle'); ss.wait_for_timeout(500)
        if STRANA == 'prazan':
            s.goto(A + '/')
        else:
            s.goto(A + '/')
        sakupi('rang lista sa zapisom sacuvanim na srpskom', 'Sara Srpski')

        # 8. bezbednost izbora jezika: preusmeravanje van sajta i nepostojeci jezik
        if STRANA == 'prazan':
            r = s.request.get(A + '/jezik/en/?dalje=https://zlo.example/', max_redirects=0)
            r2 = s.request.get(A + '/jezik/de/', max_redirects=0)
        else:
            s.goto(A + '/')
            tok = next(c['value'] for c in k.cookies() if c['name'] == 'csrftoken')
            h = {'X-CSRFToken': tok, 'Referer': A + '/', 'Origin': A}
            r = s.request.post(A + '/jezik/', form={'language': 'en', 'next': 'https://zlo.example/'}, headers=h, max_redirects=0)
            r2 = s.request.post(A + '/jezik/', form={'language': 'de', 'next': '/'}, headers=h, max_redirects=0)
        proveri('izbor jezika ne preusmerava van sajta', 'zlo.example' not in (r.headers.get('location') or ''), (r.status, r.headers.get('location')))
        proveri('nepostojeci jezik (de) odbijen ili zanemaren', r2.status in (400, 404) or 'de' not in str(r2.headers.get('set-cookie', '')), r2.status)

        # 9. srpski ekran bez engleskih ostataka: engleski prevodi iz kataloga strane ne smeju na srpski ekran
        po = glob.glob(os.path.join(KOPIJA, '**', 'locale', 'en', 'LC_MESSAGES', 'django.po'), recursive=True)
        try:
            import polib
            en = {e.msgstr for f in po for e in polib.pofile(f) if e.msgstr and len(e.msgstr) >= 14}
        except ImportError:
            en = set()
        s.goto(A + '/'); na_srpski()
        s.goto(A + ('/kraj/' if STRANA == 'prazan' else '/'))
        srpski = s.inner_text('body')
        proveri('srpski zavrsni ekran nema engleskih recenica iz kataloga', not [x for x in en if x in srpski],
                [x for x in en if x in srpski][:5])

        proveri('dijalozi pregledaca bez cirilice na engleskom', not [d for d in dijalozi if CIRILICA.search(d)], dijalozi)
        proveri('bez JS gresaka tokom cele partije', not js_greske, js_greske)
        b.close()
finally:
    server.terminate()

for ekran, tekstovi in ostaci.items():
    proveri(f'bez cirilice na engleskom: {ekran}', False, tekstovi)
ekrani = ['pocetna', 'igra, 1. krug', 'zavrsni ekran (lekcije, napomena)', 'greska pri cuvanju praznog imena', 'rang lista posle cuvanja',
          'zavrsni ekran sa linkom', 'deljena strana (posmatrac na engleskom)', 'deljena strana koja ne postoji (404)',
          'rang lista sa zapisom sacuvanim na srpskom'] + [f'igra posle {i}. kruga' for i in range(1, 8)]
for ekran in ekrani:
    if ekran not in ostaci:
        proveri(f'bez cirilice na engleskom: {ekran}', True)
print(json.dumps({'strana': STRANA, 'prolazi': sum(x['ok'] for x in rezultati), 'ukupno': len(rezultati), 'provere': rezultati},
                 ensure_ascii=False, indent=1))
