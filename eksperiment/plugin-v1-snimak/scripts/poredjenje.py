# -*- coding: utf-8 -*-
"""Poredjenje praznog Claude Code-a i plugina, posle izrade.

    python scripts/poredjenje.py provera <koren>    dokaz pre prvog upita, u provera.json
    python scripts/poredjenje.py slepo <koren>      anonimne kopije X i Y i obrazac za ocenu coveka
    python scripts/poredjenje.py izvestaj <koren>   rezultati/poredjenje.md i .json

Tokeni, trajanje i podpitanja dolaze iz izvestaj_faza.py nad transkriptima obe strane. Testove
pokrece ova skripta, pa "svi testovi prolaze" ne zavisi od tvrdnje modela.
"provera" pokrece svaku stranu kroz njen pokreni.cmd i cita sta sesija stvarno ima; posle prijave
to je jedan kratak poziv modela Haiku, bez cuvanja sesije. Ostalo ne poziva model.
"""
import glob, hashlib, json, os, random, re, shutil, subprocess, sys

sys.stdout.reconfigure(encoding='utf-8')
OVDE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, OVDE)
import izvestaj_faza as izv
from priprema_poredjenja import STRANE, UPIT_IZRADA

KORENSKI_PLUGIN = os.path.dirname(OVDE)
OZNAKE = ('X', 'Y')
ALATI_DELEGIRANJA = {'Agent', 'Task', 'Skill', 'Workflow', 'SendMessage', 'ListAgents'}
UGRADJENI_AGENTI = {'claude', 'claude-code-guide', 'Explore', 'general-purpose', 'Plan', 'statusline-setup'}
OCEKIVANI_SKILLOVI = {'craft-code', 'craft-delegiranje', 'projekat-domen', 'projekat-standardi', 'projekat-odluke'}
SADRZAJ_PODESAVANJA = ['skills', 'agents', 'commands', 'hooks', 'plugins', 'CLAUDE.md', 'settings.json', 'settings.local.json']
PRECI_ZABRANJENO = ['CLAUDE.md', '.mcp.json', os.path.join('.claude', 'settings.json'), os.path.join('.claude', 'settings.local.json'),
                    os.path.join('.claude', 'skills'), os.path.join('.claude', 'agents'), os.path.join('.claude', 'CLAUDE.md')]
# sve sto bi otkrilo stranu: podesavanja, plan i izvestaj agenata, zapisi izrade
OCENA_BEZ = shutil.ignore_patterns('.claude', 'CLAUDE.md', 'plan.md', 'handoff.md', '__pycache__', '*.pyc', 'db.sqlite3', 'test-results')
KRITERIJUMI = [
    'igra radi od pocetka do kraja: 8 krugova, kontrolni skup, zavrsni ekran',
    'tacnost pravila i racuna: cena, minuti, kazne, poeni, ocena, lekcije',
    'skriveno ostaje na serveru: sansa, oznaka tiha, ishod tihog zadatka i seme nisu u HTML, JSON ni kolacicu',
    'potez: dupli klik, pogresan krug 409, nepoznat izbor 400, klijent ne salje cenu ni poene',
    'struktura koda: logika igre odvojena od veb sloja, svi brojevi na jednom mestu, tanki prikazi',
    'kvalitet testova: motor, prikazi, tok, balans, tvrdnje koje ne prolaze prazne',
    'izgled i upotrebljivost: cirilica, telefon, sva stanja ekrana',
    'citljivost i odrzavanje koda',
]


def putanje(koren, strana):
    return os.path.join(koren, strana, 'projekat'), os.path.join(koren, strana, 'config')


def problemi_sesije(strana, z):
    """Sta u prvom zapisu sesije ne odgovara strani; prazan spisak znaci da je strana cista."""
    alati, skillovi, agenti = set(z.get('tools') or []), set(z.get('skills') or []), set(z.get('agents') or [])
    izvori = [p.get('source', '') for p in z.get('plugins') or []]
    p = []
    if z.get('permissionMode') != 'acceptEdits':
        p.append('rezim dozvola je %s' % z.get('permissionMode'))
    if z.get('mcp_servers'):
        p.append('MCP serveri: %s' % z.get('mcp_servers'))
    if any('brain' in s for s in list(skillovi) + list(agenti) + izvori):
        p.append('procurio je brain')
    if strana == 'prazan':
        if alati & ALATI_DELEGIRANJA:
            p.append('dostupni alati: %s' % sorted(alati & ALATI_DELEGIRANJA))
        if skillovi or z.get('slash_commands'):
            p.append('ima skillove: %s' % sorted(skillovi))
        if agenti - UGRADJENI_AGENTI:
            p.append('dodatni agenti: %s' % sorted(agenti - UGRADJENI_AGENTI))
        if [s for s in izvori if not s.endswith('@builtin')]:
            p.append('dodatni pluginovi: %s' % izvori)
    else:
        if 'diplomski@skills-dir' not in izvori:
            p.append('plugin diplomski nije ucitan: %s' % izvori)
        kratka = {s.split(':')[-1] for s in skillovi}
        for ime in OCEKIVANI_SKILLOVI - kratka:
            p.append('nedostaje skill %s' % ime)
        if not {'diplomski:planer', 'planer'} & agenti:
            p.append('nedostaje agent planer')
        if not {'Task', 'Skill'} <= alati:
            p.append('nedostaju alati Task i Skill')
    return p


def problemi_foldera(koren, strana):
    projekat_, config = putanje(koren, strana)
    p = []
    if strana == 'prazan' and os.listdir(projekat_) != ['MVP.md']:
        p.append('projekat nije samo MVP.md: %s' % os.listdir(projekat_))
    if strana == 'plugin' and not os.path.isfile(os.path.join(projekat_, '.claude', 'diplomski-projekat')):
        p.append('nema markera projekta')
    zabranjeno = SADRZAJ_PODESAVANJA if strana == 'prazan' else [s for s in SADRZAJ_PODESAVANJA if s not in ('skills', 'plugins')]
    p += ['config ima %s' % s for s in zabranjeno if os.path.exists(os.path.join(config, s))]
    if strana == 'plugin':
        if os.listdir(os.path.join(config, 'skills')) != ['diplomski']:
            p.append('config/skills nije samo diplomski')
        instalirani = os.path.join(config, 'plugins', 'installed_plugins.json')      # alat ga pravi sam; mora da bude prazan
        if os.path.exists(instalirani):
            with open(instalirani, encoding='utf-8') as f:
                if json.load(f).get('plugins'):
                    p.append('instalirani su dodatni pluginovi')
    if glob.glob(os.path.join(config, 'projects', '**', '*.jsonl'), recursive=True):
        p.append('vec postoji transkript: strana nije nekoriscena')
    folder = os.path.dirname(os.path.abspath(projekat_))
    while True:
        p += ['roditelj ima %s' % os.path.join(folder, s) for s in PRECI_ZABRANJENO if os.path.exists(os.path.join(folder, s))]
        if os.path.dirname(folder) == folder:
            break
        folder = os.path.dirname(folder)
    return p


def problemi_manifesta(koren):
    with open(os.path.join(koren, 'manifest.json'), encoding='utf-8') as f:
        m = json.load(f)
    p = []
    if m['plugin']['neposlate_izmene']:
        p.append('snimak plugina sadrzi necommitovane izmene')
    for s in STRANE:
        with open(os.path.join(putanje(koren, s)[0], 'MVP.md'), encoding='utf-8', newline='') as f:
            if hashlib.sha256(f.read().encode('utf-8')).hexdigest() != m['mvp_sha256']:
                p.append('MVP.md na strani %s nije isti kao u manifestu' % s)
    return p, m


def problemi_pythona(koren, strana):
    python = os.path.join(koren, strana, 'venv', 'Scripts', 'python.exe')
    kod = ('import django, sys\nfrom playwright.sync_api import sync_playwright as s\n'
           'p = s().start(); b = p.chromium.launch(); b.close(); p.stop()\nprint(sys.prefix)')
    r = subprocess.run([python, '-c', kod], capture_output=True, text=True, encoding='utf-8', errors='replace', env=okruzenje())
    if r.returncode != 0:
        return ['venv ne moze da pokrene Django i Chromium: %s' % r.stderr.strip()[-200:]]
    return [] if os.path.normcase(r.stdout.strip()) == os.path.normcase(os.path.join(koren, strana, 'venv')) else ['python nije iz venv-a strane: %s' % r.stdout.strip()]


def prvi_zapis_sesije(koren, strana):
    log_hooka = os.path.join(putanje(koren, strana)[0], '.claude', 'usage', 'prompts.jsonl')
    postojao = os.path.exists(log_hooka)
    r = subprocess.run(['cmd', '/c', os.path.join(koren, strana, 'pokreni.cmd'), '-p', 'x', '--output-format', 'stream-json', '--verbose',
                        '--no-session-persistence', '--model', 'haiku'], stdin=subprocess.DEVNULL, capture_output=True, text=True,
                       encoding='utf-8', errors='replace', timeout=180, env=okruzenje())
    if not postojao and os.path.exists(log_hooka):
        os.remove(log_hooka)                       # upis probe ne sme da ostane u merenju
    for red in r.stdout.splitlines():
        try:
            z = json.loads(red)
        except ValueError:
            continue
        if z.get('subtype') == 'init':
            return z
    raise SystemExit('Sesija strane "%s" nije dala pocetni zapis: %s' % (strana, (r.stdout + r.stderr)[-400:]))


def provera(koren):
    problemi, m = problemi_manifesta(koren)
    izvestaj_ = {'manifest': m, 'strane': {}}
    verzije = set()
    for s in STRANE:
        z = prvi_zapis_sesije(koren, s)
        verzije.add(z.get('claude_code_version'))
        spisak = problemi_foldera(koren, s) + problemi_pythona(koren, s) + problemi_sesije(s, z)
        if os.path.exists(os.path.join(os.path.expanduser('~'), '.claude', 'projects', izv.slug(putanje(koren, s)[0]))):
            spisak.append('postoji transkript u maticnom ~/.claude: rad je tekao van strane')
        problemi += ['%s: %s' % (s, x) for x in spisak]
        izvestaj_['strane'][s] = {k: z.get(k) for k in ('claude_code_version', 'cwd', 'permissionMode', 'tools', 'skills', 'slash_commands', 'agents', 'plugins', 'mcp_servers')}
        print('%-7s alata %d, skillova %d, agenata %d, pluginova %d, problema %d'
              % (s, len(z.get('tools') or []), len(z.get('skills') or []), len(z.get('agents') or []), len(z.get('plugins') or []), len(spisak)))
    if len(verzije) != 1:
        problemi.append('strane nemaju istu verziju alata: %s' % verzije)
    izvestaj_['problemi'] = problemi
    with open(os.path.join(koren, 'provera.json'), 'w', encoding='utf-8') as f:
        json.dump(izvestaj_, f, ensure_ascii=False, indent=1)
    for x in problemi:
        print('PROBLEM:', x)
    print('SVE PROVERE PROSLE' if not problemi else 'PROVERA NIJE PROSLA: %d' % len(problemi))
    return 0 if not problemi else 1


def cistoca(koren, strana):
    """Dokaz posle izrade: pozivi agenata i skillova, zapisi hooka i curenje u maticni folder."""
    projekat_, config = putanje(koren, strana)
    pozivi = 0
    for put in glob.glob(os.path.join(config, 'projects', izv.slug(projekat_), '**', '*.jsonl'), recursive=True):
        for z in izv.citaj_jsonl(put):
            sadrzaj = (z.get('message') or {}).get('content') if z.get('type') == 'assistant' else None
            pozivi += sum(1 for d in sadrzaj or [] if isinstance(d, dict) and d.get('type') == 'tool_use' and d.get('name') in ALATI_DELEGIRANJA)
    log_hooka = os.path.join(projekat_, '.claude', 'usage', 'prompts.jsonl')
    upisa = sum(1 for _ in izv.citaj_jsonl(log_hooka)) if os.path.exists(log_hooka) else 0
    maticni = os.path.exists(os.path.join(os.path.expanduser('~'), '.claude', 'projects', izv.slug(projekat_)))
    return {'pozivi_agenata_i_skillova': pozivi, 'upisa_hooka': upisa, 'rad_u_maticnom_folderu': maticni}


def slepo(koren):
    ocena = os.path.join(koren, 'ocena')
    if os.path.exists(ocena):
        print('Odbijeno: %s vec postoji; ocene se ne prepisuju.' % ocena, file=sys.stderr)
        return 2
    strane = list(STRANE)
    random.SystemRandom().shuffle(strane)
    kljuc = dict(zip(OZNAKE, strane))
    for oznaka, strana in kljuc.items():
        shutil.copytree(putanje(koren, strana)[0], os.path.join(ocena, oznaka), ignore=OCENA_BEZ)
    with open(os.path.join(ocena, 'kljuc.json'), 'w', encoding='utf-8') as f:
        json.dump(kljuc, f, indent=1)
    obrazac = {'uputstvo': 'Svaki kriterijum 1 do 5. Oceni gledajuci samo foldere X i Y.',
               'ocene': {k: {o: None for o in OZNAKE} for k in KRITERIJUMI}, 'napomena': {o: '' for o in OZNAKE}}
    with open(os.path.join(ocena, 'ocena.json'), 'w', encoding='utf-8') as f:
        json.dump(obrazac, f, ensure_ascii=False, indent=1)
    print('[slepo] popuni %s' % os.path.join(ocena, 'ocena.json'))
    return 0


def ocene_coveka(koren):
    """{strana: {'kriterijumi': {...}, 'prosek': x, 'napomena': s}}; None dok obrazac nije popunjen."""
    folder = os.path.join(koren, 'ocena')
    try:
        with open(os.path.join(folder, 'ocena.json'), encoding='utf-8') as f:
            obrazac = json.load(f)
        with open(os.path.join(folder, 'kljuc.json'), encoding='utf-8') as f:
            kljuc = json.load(f)
    except FileNotFoundError:
        return None
    for vrednosti in obrazac['ocene'].values():
        for v in vrednosti.values():
            if v is None:
                return None
            if v not in (1, 2, 3, 4, 5):
                raise ValueError('ocena mora biti ceo broj 1 do 5, a ne %r' % (v,))
    izlaz = {}
    for oznaka, strana in kljuc.items():
        po_kriterijumu = {k: v[oznaka] for k, v in obrazac['ocene'].items()}
        izlaz[strana] = {'oznaka': oznaka, 'kriterijumi': po_kriterijumu, 'napomena': obrazac['napomena'][oznaka],
                         'prosek': round(sum(po_kriterijumu.values()) / len(po_kriterijumu), 2)}
    return izlaz


def okruzenje():
    return {k: v for k, v in os.environ.items() if k != 'CLAUDE_PROJECT_DIR'}


def izvestaj_strane(koren, strana):
    projekat_, config = putanje(koren, strana)
    folder = os.path.join(config, 'projects', izv.slug(projekat_))
    if not os.path.isdir(folder):
        raise SystemExit('Nema transkripata za stranu "%s": %s' % (strana, folder))
    izlaz = os.path.join(koren, 'rezultati', strana)
    r = subprocess.run([sys.executable, os.path.join(OVDE, 'izvestaj_faza.py'), '--projekat', projekat_, '--transkripti', folder, '--izlaz', izlaz],
                       capture_output=True, text=True, encoding='utf-8', env=okruzenje())
    if r.returncode != 0:
        raise SystemExit('izvestaj_faza.py pao za "%s": %s' % (strana, r.stderr))
    with open(os.path.join(izlaz, 'izvestaj_faza.json'), encoding='utf-8') as f:
        return json.load(f)


def pokreni_testove(koren, strana):
    projekat_ = putanje(koren, strana)[0]
    if not os.path.exists(os.path.join(projekat_, 'manage.py')):
        return {'exit': None, 'izlaz': 'nema manage.py', 'pokrenuto': None, 'palo': None}
    venv = os.path.join(koren, strana, 'venv', 'Scripts', 'python.exe')
    try:
        r = subprocess.run([venv if os.path.exists(venv) else sys.executable, os.path.join(KORENSKI_PLUGIN, 'tools', 'test_summary.py')], cwd=projekat_, timeout=1800,
                           capture_output=True, text=True, encoding='utf-8', errors='replace', env=okruzenje())
    except subprocess.TimeoutExpired:
        return {'exit': None, 'izlaz': 'isteklo 30 minuta', 'pokrenuto': None, 'palo': None}
    m = re.search(r'(\d+) pokrenuto, (\d+) palo', r.stdout)
    return {'exit': r.returncode, 'izlaz': r.stdout.strip(), 'pokrenuto': int(m.group(1)) if m else None, 'palo': int(m.group(2)) if m else None}


def zbir_upita(redovi):
    cene = [r['cena_usd'] for r in redovi]
    return {'trajanje_s': round(sum(r['trajanje_s'] - r['cekanje_s'] for r in redovi), 1), 'tokeni': sum(r['tokeni'] for r in redovi),
            'cena_usd': None if None in cene else round(sum(cene), 6)}


def podela_rada(po_upitu):
    """(planiranje, izrada) po propisanom upitu za izradu; izrada je None ako taj upit nije poslat."""
    granica = next((i for i, r in enumerate(po_upitu) if UPIT_IZRADA[:40] in r['tekst']), None)
    if granica is None:
        return zbir_upita(po_upitu), None
    return zbir_upita(po_upitu[:granica]), zbir_upita(po_upitu[granica:])


def podpitanja(izvestaj_):
    """Bez jednog propisanog upita kojim se plan potvrdjuje."""
    n = izvestaj_['ukupno']['podpitanja_coveku']
    return n - 1 if podela_rada(izvestaj_['po_upitu'])[1] is not None else n


def deo_rada(s, indeks, polje, oblik):
    deo = podela_rada(s['izvestaj']['po_upitu'])[indeks]
    return '-' if deo is None else oblik(deo[polje])


def tekst_testova(t):
    if t['pokrenuto'] is None:
        return t['izlaz']
    return '%d pokrenuto, %d palo (izlazni kod %s)' % (t['pokrenuto'], t['palo'], t['exit'])


def redovi_poredjenja(strane):
    """(naslov, funkcija nad jednom stranom) redom kojim stoje u tabeli."""
    u = lambda s: s['izvestaj']['ukupno']
    return [
        ('zidno trajanje', lambda s: izv.trajanje(u(s)['zidno_s'])),
        ('rad bez cekanja coveka', lambda s: izv.trajanje(u(s)['rad_s'])),
        ('cekanje coveka', lambda s: izv.trajanje(u(s)['cekanje_coveka_s'])),
        ('aktivno, zbir svih agenata', lambda s: izv.trajanje(u(s)['aktivno_s'])),
        ('planiranje: rad', lambda s: deo_rada(s, 0, 'trajanje_s', izv.trajanje)),
        ('planiranje: tokena', lambda s: deo_rada(s, 0, 'tokeni', izv.broj)),
        ('planiranje: cena', lambda s: deo_rada(s, 0, 'cena_usd', izv.cena)),
        ('izrada: rad', lambda s: deo_rada(s, 1, 'trajanje_s', izv.trajanje)),
        ('izrada: tokena', lambda s: deo_rada(s, 1, 'tokeni', izv.broj)),
        ('izrada: cena', lambda s: deo_rada(s, 1, 'cena_usd', izv.cena)),
        ('upita coveka', lambda s: u(s)['upita_coveka']),
        ('podpitanja coveku, bez propisane potvrde plana', lambda s: podpitanja(s['izvestaj'])),
        ('  pitanja alatom', lambda s: u(s)['pitanja_alatom']),
        ('  poruke posle prvog upita, sa potvrdom plana', lambda s: u(s)['dodatnih_upita']),
        ('API poruka', lambda s: izv.broj(u(s)['poruka'])),
        ('pokretanja (sesije i agenti)', lambda s: u(s)['pokretanja']),
        ('ulazni tokeni', lambda s: izv.broj(u(s)['ulaz'])),
        ('izlazni tokeni', lambda s: izv.broj(u(s)['izlaz'])),
        ('citanje iz kesa', lambda s: izv.broj(u(s)['cache_citanje'])),
        ('upis u kes', lambda s: izv.broj(u(s)['cache_upis_5m'] + u(s)['cache_upis_1h'])),
        ('tokena ukupno', lambda s: izv.broj(u(s)['tokeni_ukupno'])),
        ('izlaznih tokena u minuti', lambda s: u(s)['izlaz_po_minutu']),
        ('cena', lambda s: izv.cena(u(s)['cena_usd'])),
        ('vracanja na doradu', lambda s: s['izvestaj']['vracanja_na_doradu']),
        ('testovi, nezavisno pokretanje', lambda s: tekst_testova(s['testovi'])),
        ('pozivi agenata i skillova', lambda s: s['cistoca']['pozivi_agenata_i_skillova']),
        ('upisa hooka plugina', lambda s: s['cistoca']['upisa_hooka']),
        ('ocena coveka, prosek od 5', lambda s: s['ocena']['prosek'] if s['ocena'] else 'nije ocenjeno'),
    ]


def markdown(rezultat, koren):
    L = ['# Poredjenje: prazan Claude Code i plugin', '', '- Koren: `%s`' % koren, '']
    strane = rezultat['strane']
    if strane['prazan']['cistoca']['pozivi_agenata_i_skillova'] or any(strane[s]['cistoca']['rad_u_maticnom_folderu'] for s in STRANE):
        L += ['**MERENJE NIJE VAZECE:** prazna strana je zvala agenta ili skill, ili je deo rada tekao u maticnom `~/.claude`.', '']
    L += izv.tabela(['mera'] + list(STRANE), [[naslov] + [f(strane[s]) for s in STRANE] for naslov, f in redovi_poredjenja(strane)]) + ['']
    L += ['## Po modelu', '']
    redovi = []
    for s in STRANE:
        for r in sorted(strane[s]['izvestaj']['po_modelu'], key=lambda x: -x['izlaz']):
            redovi.append([s, r['model'], izv.broj(r['ulaz']), izv.broj(r['izlaz']), izv.broj(r['cache_citanje']),
                           izv.broj(r['cache_upis_5m'] + r['cache_upis_1h']), izv.cena(r['cena_usd'])])
    L += izv.tabela(['strana', 'model', 'ulaz', 'izlaz', 'cache citanje', 'cache upis', 'cena'], redovi) + ['']
    if all(strane[s]['ocena'] for s in STRANE):
        L += ['## Ocena coveka po kriterijumu', '']
        L += izv.tabela(['kriterijum'] + list(STRANE), [[k] + [strane[s]['ocena']['kriterijumi'][k] for s in STRANE] for k in KRITERIJUMI]) + ['']
    L += ['## Ogranicenja', '',
          '- Svaka strana je izvedena jednom: rezultat pokazuje sta se desilo u ovom slucaju, a ne statisticki pouzdanu razliku.',
          '- Cena je obracun po ceni programskog interfejsa, bez obzira na nacin placanja.',
          '- Obe strane imaju isti MVP.md; strana sa pluginom ima i gotove standarde koda, sto je deo onoga sto se poredi.',
          '- Pravila plugina dopunjena su pre merenja zamkama izabranim za tehnologije ove igre.', '']
    return '\n'.join(L)


def izvestaj(koren):
    ocene = ocene_coveka(koren)
    strane = {s: {'izvestaj': izvestaj_strane(koren, s), 'testovi': pokreni_testove(koren, s), 'ocena': ocene[s] if ocene else None, 'cistoca': cistoca(koren, s)} for s in STRANE}
    rezultat = {'strane': {s: {'ukupno': v['izvestaj']['ukupno'], 'po_modelu': v['izvestaj']['po_modelu'], 'po_upitu': v['izvestaj']['po_upitu'],
                               'planiranje': podela_rada(v['izvestaj']['po_upitu'])[0], 'izrada': podela_rada(v['izvestaj']['po_upitu'])[1],
                               'podpitanja_coveku': podpitanja(v['izvestaj']), 'cistoca': v['cistoca'],
                               'vracanja_na_doradu': v['izvestaj']['vracanja_na_doradu'], 'testovi': v['testovi'], 'ocena': v['ocena']} for s, v in strane.items()}}
    folder = os.path.join(koren, 'rezultati')
    tekst = markdown({'strane': strane}, koren)
    with open(os.path.join(folder, 'poredjenje.md'), 'w', encoding='utf-8') as f:
        f.write(tekst)
    with open(os.path.join(folder, 'poredjenje.json'), 'w', encoding='utf-8') as f:
        json.dump(rezultat, f, ensure_ascii=False, indent=1)
    print(tekst)
    return 0


def main(a):
    radnje = {'provera': provera, 'slepo': slepo, 'izvestaj': izvestaj}
    if len(a) != 2 or a[0] not in radnje:
        print(__doc__, file=sys.stderr)
        return 2
    return radnje[a[0]](os.path.abspath(a[1]))


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
