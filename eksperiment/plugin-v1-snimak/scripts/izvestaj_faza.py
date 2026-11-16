# -*- coding: utf-8 -*-
"""Izvestaj za odeljak 7.6: tokeni, trajanje, pokretanja i upiti po fazi, agentu i modelu.

    python scripts/izvestaj_faza.py [--projekat <putanja>] [--transkripti <folder>] [--izlaz <folder>]

Bez poziva modela, samo stdlib. Izvor brojki su stvarni transkripti Claude Code-a
(~/.claude/projects/<slug>/<sesija>.jsonl i <sesija>/subagents/agent-*.jsonl), ne procene.
Faze dolaze iz .claude/usage/faze.jsonl. Izlaz: izvestaj_faza.md i izvestaj_faza.json.

Definicije (iste se ispisuju u izvestaju):
- Tokeni: jedna API poruka se broji jednom. Isti message id se u transkriptu javlja u vise
  redova, a nastavljena sesija kopira istoriju; uzima se red sa najvecim output_tokens.
- Zidno trajanje faze: od njenog upisa do sledeceg upisa (poslednja faza: do poslednje poruke).
- Aktivno trajanje: zbir razmaka izmedju uzastopnih poruka istog pokretanja, bez cekanja na
  novi upit i bez razmaka duzih od --prag sekundi. Paralelni agenti se sabiraju, pa zbir
  moze biti veci od zidnog trajanja.
- Pokretanje: jedan agent id, odnosno jedna sesija za glavni tok.
- Upit: stvaran upit korisnika u glavnom toku (bez tool_result, meta i sazetih poruka).
- Vracanje na doradu: upis faze "implementacija" koji sledi posle ranijeg upisa "kontrolni skup",
  a prethodni upis nije bio "implementacija".
- Tudja izmena (sira mera): uspesna Edit/Write izmena fajla koji je poslednji menjalo DRUGO
  pokretanje. Broji i planirano nadogradjivanje, pa je to gornja granica, ne broj gresaka.
- Rad bez cekanja coveka: zbir trajanja po upitu (od upita do poslednje poruke pre sledeceg upita),
  umanjen za vreme u kome AskUserQuestion ceka odgovor.
- Podpitanja coveku: pitanja iz AskUserQuestion plus svaki upit coveka posle prvog. Dozvole se ne vide
  u transkriptu, pa se poredjenje radi sa istim rezimom dozvola.

Sa --transkripti marker nije obavezan: tako se meri i prazan Claude Code.
"""
import argparse, bisect, collections, datetime, glob, json, os, re, sys

sys.stdout.reconfigure(encoding='utf-8')
PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PLUGIN, 'hooks'))
import projekat

GLAVNI = 'glavna sesija'
BEZ_FAZE = '(bez faze)'
ALATI_IZMENE = {'Edit', 'Write', 'MultiEdit', 'NotebookEdit'}
ALAT_PITANJA = 'AskUserQuestion'
CENA_NIJE = 'cena nije podesena'
TOKENI = ('ulaz', 'izlaz', 'cache_citanje', 'cache_upis_5m', 'cache_upis_1h')


def vreme(s):
    return datetime.datetime.fromisoformat(s.replace('Z', '+00:00'))


def slug(koren):
    return re.sub(r'[^a-zA-Z0-9]', '-', os.path.abspath(koren))


def folder_transkripata(koren):
    osnova = os.environ.get('CLAUDE_CONFIG_DIR') or os.path.join(os.path.expanduser('~'), '.claude')
    return os.path.join(osnova, 'projects', slug(koren))


def citaj_jsonl(put):
    with open(put, encoding='utf-8', errors='replace') as f:
        for red in f:
            try:
                yield json.loads(red)
            except ValueError:
                continue


def tekst_upita(zapis):
    """Tekst stvarnog upita korisnika, ili None ako ovaj red to nije."""
    if zapis.get('type') != 'user' or zapis.get('isMeta') or zapis.get('isCompactSummary'):
        return None
    sadrzaj = (zapis.get('message') or {}).get('content')
    if isinstance(sadrzaj, list):
        if any(isinstance(d, dict) and d.get('type') == 'tool_result' for d in sadrzaj):
            return None
        sadrzaj = ' '.join(d.get('text', '') for d in sadrzaj if isinstance(d, dict))
    if not isinstance(sadrzaj, str) or not sadrzaj.strip() or sadrzaj.lstrip().startswith(projekat.NIJE_UPIT):
        return None
    return sadrzaj


class Faze:
    def __init__(self, koren):
        self.upisi = []
        put = os.path.join(projekat.usage_folder(koren), 'faze.jsonl')
        if os.path.exists(put):
            self.upisi = sorted((vreme(z['vreme']), z['faza']) for z in citaj_jsonl(put))
        self.pocetci = [t for t, _ in self.upisi]

    def u_trenutku(self, t):
        i = bisect.bisect_right(self.pocetci, t) - 1
        return self.upisi[i][1] if i >= 0 else BEZ_FAZE

    def zidno(self, kraj):
        po_fazi = collections.Counter()
        for i, (t, ime) in enumerate(self.upisi):
            sledeci = self.upisi[i + 1][0] if i + 1 < len(self.upisi) else kraj
            if sledeci and sledeci > t:
                po_fazi[ime] += (sledeci - t).total_seconds()
        return po_fazi

    def vracanja(self):
        n, bio_kontrolni, prethodna = 0, False, None
        for _, ime in self.upisi:
            if ime == 'implementacija' and bio_kontrolni and prethodna != 'implementacija':
                n += 1
            bio_kontrolni = bio_kontrolni or ime == 'kontrolni skup'
            prethodna = ime
        return n


def tokeni_iz(u):
    pisano = u.get('cache_creation_input_tokens') or 0
    detalj = u.get('cache_creation') or {}
    jedan_sat = detalj.get('ephemeral_1h_input_tokens') or 0
    return {'ulaz': u.get('input_tokens') or 0, 'izlaz': u.get('output_tokens') or 0,
            'cache_citanje': u.get('cache_read_input_tokens') or 0,
            'cache_upis_5m': pisano - jedan_sat, 'cache_upis_1h': jedan_sat}


def ime_agenta(put):
    meta = put[:-len('.jsonl')] + '.meta.json'
    try:
        with open(meta, encoding='utf-8') as f:
            return json.load(f).get('agentType', '?').split(':')[-1]
    except (OSError, ValueError):
        return '?'


def prikupi(folder, prag):
    """Cita transkripte: poruke (po message id), upite i uspesne izmene fajlova."""
    glavni = sorted(glob.glob(os.path.join(folder, '*.jsonl')))
    pod = sorted(glob.glob(os.path.join(folder, '*', 'subagents', '**', '*.jsonl'), recursive=True))
    poruke, upiti, izmene, greske, pitanja = {}, [], [], set(), {}
    uuidi, stat = set(), collections.Counter()
    for put in glavni + pod:                       # glavni prvi: kopija istorije pripada glavnom toku
        je_glavni = put in glavni
        ime = os.path.basename(put)[:-len('.jsonl')]
        pokretanje = ime if je_glavni else ime.replace('agent-', '', 1)
        agent = GLAVNI if je_glavni else ime_agenta(put)
        stat['fajlova'] += 1
        prethodno, cekaju = None, []
        for z in citaj_jsonl(put):
            t = vreme(z['timestamp']) if z.get('timestamp') else None
            if z.get('type') == 'user':
                for d in (z.get('message') or {}).get('content') or []:
                    if not isinstance(d, dict) or d.get('type') != 'tool_result':
                        continue
                    if d.get('is_error'):
                        greske.add(d.get('tool_use_id'))
                    pitanje = pitanja.get(d.get('tool_use_id'))
                    if pitanje and t and pitanje['odgovor'] is None:
                        pitanje['odgovor'] = t
                tekst = tekst_upita(z)
                if tekst is not None and t:
                    prethodno = t
                    if je_glavni and z.get('uuid') not in uuidi:
                        uuidi.add(z.get('uuid'))
                        cekaju.append((t, tekst))
                elif prethodno is None and t:
                    prethodno = t
            if z.get('type') != 'assistant' or not t:
                continue
            m = z.get('message') or {}
            mid, model, u = m.get('id'), m.get('model'), m.get('usage')
            if not mid or not u or model == '<synthetic>':
                continue
            for d in m.get('content') or []:
                if isinstance(d, dict) and d.get('type') == 'tool_use' and d.get('name') == ALAT_PITANJA:
                    pitanja.setdefault(d.get('id'), {'t': t, 'odgovor': None,
                                                     'broj': len((d.get('input') or {}).get('questions') or []) or 1})
                if isinstance(d, dict) and d.get('type') == 'tool_use' and d.get('name') in ALATI_IZMENE:
                    fajl = (d.get('input') or {}).get('file_path')
                    if fajl:
                        izmene.append((t, d.get('id'), os.path.normcase(os.path.normpath(fajl)), pokretanje))
            tok = tokeni_iz(u)
            if mid in poruke:
                stat['duplikata'] += 1
                if tok['izlaz'] >= poruke[mid]['tok']['izlaz']:
                    poruke[mid]['tok'] = tok
                prethodno = max(prethodno or t, t)
                continue
            razmak = (t - prethodno).total_seconds() if prethodno else 0
            if razmak > prag:
                stat['preskocenih_razmaka'] += 1
                razmak = 0
            poruke[mid] = {'t': t, 'model': re.sub(r'\[.*\]$', '', model or '?'), 'agent': agent, 'pokretanje': pokretanje,
                           'trajanje': max(razmak, 0), 'tok': tok, 'brzo': u.get('speed') not in (None, 'standard')}
            prethodno = t
            for tu, tekst in cekaju:
                upiti.append((tu, agent, poruke[mid]['model'], tekst))
            cekaju = []
        for tu, tekst in cekaju:                   # upit bez odgovora modela
            upiti.append((tu, agent, '?', tekst))
    stat['poruka'] = len(poruke)
    uspesne = sorted(i for i in izmene if i[1] not in greske)
    return poruke, upiti, uspesne, stat, pitanja


def ucitaj_cene(put):
    """{model: cene}; modeli bez svih cena, ili fajl bez izvora, ne ulaze."""
    try:
        with open(put, encoding='utf-8') as f:
            sve = json.load(f)
    except (OSError, ValueError):
        return {}, None
    if not sve.get('izvor'):
        return {}, None
    return ({m: c for m, c in (sve.get('modeli') or {}).items() if all(c.get(k) is not None for k in TOKENI)},
            sve.get('izvor'))


def nov_red():
    return {'trajanje': 0.0, 'poruka': 0, 'pokretanja': set(), 'upiti': 0, 'cena': 0.0, **{k: 0 for k in TOKENI}}


def dodaj(red, p, cene):
    red['trajanje'] += p['trajanje']
    red['poruka'] += 1
    red['pokretanja'].add(p['pokretanje'])
    for k in TOKENI:
        red[k] += p['tok'][k]
    v = cena_poruke(p['tok'], cene.get(p['model']))
    red['cena'] = None if v is None or red['cena'] is None else red['cena'] + v


def cena_poruke(tok, c):
    """Dolari za jednu API poruku; None ako model nema cenu. Prag vazi po zahtevu, za ceo prompt."""
    if c is None:
        return None
    prag = c.get('prag_prompta')
    if prag and tok['ulaz'] + tok['cache_citanje'] + tok['cache_upis_5m'] + tok['cache_upis_1h'] > prag:
        c = c['iznad_praga']
    return sum(tok[k] * c[k] for k in TOKENI) / 1e6


def po_upitima(poruke, upiti, cene, pitanja):
    """Jedan red po upitu coveka: od upita do poslednje poruke pre sledeceg upita, sa svim agentima."""
    redom = sorted((t, tekst) for t, _, _, tekst in upiti)
    pocetci = [t for t, _ in redom]
    redovi = [{'upit': i + 1, 't': t, 'tekst': tekst[:120], 'kraj': t, 'poruka': 0, 'tokeni': 0, 'cena': 0.0, 'cekanje': 0.0}
              for i, (t, tekst) in enumerate(redom)]
    for q in pitanja.values():
        i = bisect.bisect_right(pocetci, q['t']) - 1
        if q['odgovor'] and i >= 0:
            redovi[i]['cekanje'] += (q['odgovor'] - q['t']).total_seconds()
    for p in poruke.values():
        i = bisect.bisect_right(pocetci, p['t']) - 1
        if i < 0:
            continue
        r = redovi[i]
        r['kraj'], r['poruka'], r['tokeni'] = max(r['kraj'], p['t']), r['poruka'] + 1, r['tokeni'] + sum(p['tok'].values())
        v = cena_poruke(p['tok'], cene.get(p['model']))
        r['cena'] = None if v is None or r['cena'] is None else r['cena'] + v
    return redovi


def ukupno(poruke, redovi, pitanja, grupe):
    """Zbirne brojke cele izrade; iz njih pise poredjenje.py."""
    cekanje_pitanja = sum((q['odgovor'] - q['t']).total_seconds() for q in pitanja.values() if q['odgovor'])
    rad_upita = sum((r['kraj'] - r['t']).total_seconds() for r in redovi)
    zidno = (redovi[-1]['kraj'] - redovi[0]['t']).total_seconds() if redovi else 0.0
    rad = max(rad_upita - cekanje_pitanja, 0.0)
    modeli = list(grupe['model'].values())
    tokeni = {k: sum(r[k] for r in modeli) for k in TOKENI}
    dodatni, ask = max(len(redovi) - 1, 0), sum(q['broj'] for q in pitanja.values())
    return dict(tokeni, zidno_s=round(zidno, 1), rad_s=round(rad, 1), cekanje_coveka_s=round(zidno - rad, 1),
                aktivno_s=round(sum(p['trajanje'] for p in poruke.values()), 1), poruka=len(poruke),
                pokretanja=len({p['pokretanje'] for p in poruke.values()}), upita_coveka=len(redovi),
                dodatnih_upita=dodatni, pitanja_alatom=ask, podpitanja_coveku=dodatni + ask,
                tokeni_ukupno=sum(tokeni.values()), izlaz_po_minutu=round(tokeni['izlaz'] / (rad / 60), 1) if rad else None,
                cena_usd=None if any(r['cena'] is None for r in modeli) or not modeli else round(sum(r['cena'] for r in modeli), 6))


def sazmi(poruke, upiti, faze, cene):
    grupe = {'detalj': collections.defaultdict(nov_red), 'faza': collections.defaultdict(nov_red),
             'agent': collections.defaultdict(nov_red), 'model': collections.defaultdict(nov_red)}
    for p in poruke.values():
        f = faze.u_trenutku(p['t'])
        for ime, kljuc in (('detalj', (f, p['agent'], p['model'])), ('faza', (f,)), ('agent', (p['agent'],)), ('model', (p['model'],))):
            dodaj(grupe[ime][kljuc], p, cene)
    for t, agent, model, _ in upiti:
        f = faze.u_trenutku(t)
        for ime, kljuc in (('detalj', (f, agent, model)), ('faza', (f,)), ('agent', (agent,)), ('model', (model,))):
            grupe[ime][kljuc]['upiti'] += 1
    return grupe


def tudje_izmene(izmene, faze):
    po_fazi, po_agentu_run, poslednji = collections.Counter(), collections.Counter(), {}
    for t, _, fajl, run in izmene:
        if fajl in poslednji and poslednji[fajl] != run:
            po_fazi[faze.u_trenutku(t)] += 1
            po_agentu_run[run] += 1
        poslednji[fajl] = run
    return po_fazi, po_agentu_run


def upiti_iz_hooka(koren):
    n = collections.Counter()
    put = os.path.join(projekat.usage_folder(koren), 'prompts.jsonl')
    if os.path.exists(put):
        for z in citaj_jsonl(put):
            n[z.get('faza') or BEZ_FAZE] += 1
    return n


def trajanje(s):
    s = int(round(s))
    return '%d h %02d min' % (s // 3600, s % 3600 // 60) if s >= 3600 else '%d min %02d s' % (s // 60, s % 60)


def broj(n):
    return '{:,}'.format(n).replace(',', '.')


def cena(v):
    return CENA_NIJE if v is None else '%.4f $' % v


def u_recnik(kolone, kljuc, red):
    izlaz = dict(zip(kolone, kljuc))
    izlaz.update({k: red[k] for k in TOKENI})
    izlaz.update(trajanje_s=round(red['trajanje'], 1), poruka=red['poruka'], pokretanja=len(red['pokretanja']),
                 upita=red['upiti'], cena_usd=None if red['cena'] is None else round(red['cena'], 6))
    return izlaz


REDOSLED = {ime: i for i, ime in enumerate([BEZ_FAZE] + projekat.FAZE)}


def tabela(naslovi, redovi):
    izlaz = ['| ' + ' | '.join(naslovi) + ' |', '|' + '---|' * len(naslovi)]
    izlaz += ['| ' + ' | '.join(str(c) for c in r) + ' |' for r in redovi]
    return izlaz


def celije(red):
    return [trajanje(red['trajanje']), broj(red['ulaz']), broj(red['izlaz']), broj(red['cache_citanje']),
            broj(red['cache_upis_5m'] + red['cache_upis_1h']), len(red['pokretanja']), red['upiti'], cena(red['cena'])]


def markdown(ctx):
    g, fz = ctx['grupe'], ctx['faze']
    zaj = ['aktivno', 'ulaz', 'izlaz', 'cache citanje', 'cache upis', 'pokretanja', 'upita', 'cena']
    L = ['# Izvestaj po fazama', '',
         '- Projekat: `%s`' % ctx['koren'], '- Transkripti: `%s`' % ctx['folder'],
         '- Napravljen: %s' % projekat.sada(),
         '- Fajlova: %(fajlova)d; jedinstvenih API poruka: %(poruka)d; duplih redova preskoceno: %(duplikata)d; razmaka preko praga: %(preskocenih_razmaka)d' % ctx['stat'],
         '- Cene: ' + ('izvor ' + ctx['izvor_cena'] if ctx['izvor_cena'] else CENA_NIJE + ' (`scripts/cene.json`)'), '']
    if not fz.upisi:
        L += ['**Nijedna faza nije upisana** (`scripts/faza.py`), pa je sve u "%s".' % BEZ_FAZE, '']
    u = ctx['ukupno']
    L += ['## Ukupno', '']
    L += tabela(['zidno', 'rad bez cekanja coveka', 'cekanje coveka', 'upita coveka', 'podpitanja coveku', 'tokena', 'izlaz/min', 'cena'],
                [[trajanje(u['zidno_s']), trajanje(u['rad_s']), trajanje(u['cekanje_coveka_s']), u['upita_coveka'], u['podpitanja_coveku'],
                  broj(u['tokeni_ukupno']), u['izlaz_po_minutu'], cena(u['cena_usd'])]]) + ['']
    L += ['## Po upitu coveka', '']
    L += tabela(['upit', 'trajanje', 'poruka', 'tokena', 'cena'],
                [[r['upit'], trajanje((r['kraj'] - r['t']).total_seconds()), r['poruka'], broj(r['tokeni']), cena(r['cena'])] for r in ctx['po_upitu']]) + ['']
    L += ['## Po fazi', '']
    redovi = []
    for k, red in sorted(g['faza'].items(), key=lambda x: REDOSLED.get(x[0][0], 99)):
        zid = ctx['zidno'].get(k[0])
        redovi.append([k[0], trajanje(zid) if zid is not None else '-'] + celije(red) + [ctx['hook'].get(k[0], 0)])
    L += tabela(['faza', 'zidno'] + zaj + ['upita (hook)'], redovi) + ['']
    for naslov, ime in (('Po agentu', 'agent'), ('Po modelu', 'model')):
        L += ['## ' + naslov, '']
        L += tabela([ime] + zaj, [[k[0]] + celije(r) for k, r in sorted(g[ime].items(), key=lambda x: -x[1]['izlaz'])]) + ['']
    L += ['## Faza, agent i model', '']
    red_det = sorted(g['detalj'].items(), key=lambda x: (REDOSLED.get(x[0][0], 99), x[0][1], x[0][2]))
    L += tabela(['faza', 'agent', 'model'] + zaj, [list(k) + celije(r) for k, r in red_det]) + ['']
    L += ['## Vracanja na doradu', '', '- **Vracanja na doradu: %d**' % ctx['vracanja'],
          '- Tudje izmene (sira mera, gornja granica): %d' % sum(ctx['tudje'].values())]
    L += ['  - %s: %d' % (f, n) for f, n in sorted(ctx['tudje'].items(), key=lambda x: REDOSLED.get(x[0], 99))]
    L += ['', '## Definicije', '',
          '- **Vracanje na doradu**: upis faze "implementacija" posle ranijeg upisa "kontrolni skup", kada prethodni upis nije bio "implementacija".',
          '- **Tudja izmena**: uspesna Edit/Write izmena fajla koji je poslednji menjalo drugo pokretanje; broji i planirano nadogradjivanje.',
          '- **Tokeni**: jedna API poruka jednom (message id, red sa najvecim output_tokens). Izlaz ukljucuje razmisljanje.',
          '- **Zidno**: od upisa faze do sledeceg upisa. **Aktivno**: zbir razmaka izmedju poruka istog pokretanja, bez cekanja na upit i bez razmaka preko %d s; paralelni agenti se sabiraju.' % ctx['prag'],
          '- **Upit**: stvaran upit u glavnom toku iz transkripta; "upita (hook)" je kontrolni broj iz `prompts.jsonl`.',
          '- **Cena** ne ukljucuje web pretrage i racuna standardnu brzinu; poruka u brzom rezimu: %d.' % ctx['brzih'],
          '- **Van izvestaja**: CLI u probama prijavljuje 1.190 do 1.411 ulaznih i 177 do 356 izlaznih tokena po sesiji vise nego transkript; cache tokeni se poklapaju tacno. Verovatno pozadinski pozivi alata, uzrok nije utvrdjen.', '']
    return '\n'.join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--projekat', default=os.getcwd())
    ap.add_argument('--transkripti')
    ap.add_argument('--izlaz')
    ap.add_argument('--prag', type=int, default=1800, help='najduzi razmak koji se racuna kao rad, u sekundama')
    ap.add_argument('--cene', default=os.path.join(PLUGIN, 'scripts', 'cene.json'))
    a = ap.parse_args()
    koren = projekat.koren(a.projekat) or (os.path.abspath(a.projekat) if a.transkripti else None)
    if koren is None:
        print('Nema markera %s u %s' % (projekat.MARKER, a.projekat), file=sys.stderr)
        return 2
    folder = a.transkripti or folder_transkripata(koren)
    if not os.path.isdir(folder):
        print('Nema foldera transkripata: %s (zadaj --transkripti)' % folder, file=sys.stderr)
        return 2
    poruke, upiti, izmene, stat, pitanja = prikupi(folder, a.prag)
    for k in ('duplikata', 'preskocenih_razmaka'):
        stat[k] += 0
    faze = Faze(koren)
    cene, izvor = ucitaj_cene(a.cene)
    grupe = sazmi(poruke, upiti, faze, cene)
    kraj = max((p['t'] for p in poruke.values()), default=None)
    zidno = faze.zidno(kraj)
    tudje, tudje_run = tudje_izmene(izmene, faze)
    redovi_upita = po_upitima(poruke, upiti, cene, pitanja)
    zbir = ukupno(poruke, redovi_upita, pitanja, grupe)
    ctx = {'koren': koren, 'folder': folder, 'stat': stat, 'izvor_cena': izvor, 'grupe': grupe, 'faze': faze,
           'ukupno': zbir, 'po_upitu': redovi_upita,
           'zidno': zidno, 'hook': upiti_iz_hooka(koren), 'vracanja': faze.vracanja(), 'tudje': tudje, 'prag': a.prag,
           'brzih': sum(1 for p in poruke.values() if p['brzo'])}
    izlaz = a.izlaz or projekat.usage_folder(koren)
    os.makedirs(izlaz, exist_ok=True)
    tekst = markdown(ctx)
    with open(os.path.join(izlaz, 'izvestaj_faza.md'), 'w', encoding='utf-8') as f:
        f.write(tekst)
    podaci = {
        'projekat': koren, 'transkripti': folder, 'statistika': dict(stat), 'izvor_cena': izvor, 'ukupno': zbir,
        'po_upitu': [{'upit': r['upit'], 'tekst': r['tekst'], 'trajanje_s': round((r['kraj'] - r['t']).total_seconds(), 1),
                      'cekanje_s': round(r['cekanje'], 1), 'poruka': r['poruka'], 'tokeni': r['tokeni'],
                      'cena_usd': None if r['cena'] is None else round(r['cena'], 6)} for r in redovi_upita],
        'vracanja_na_doradu': ctx['vracanja'], 'tudje_izmene_po_fazi': dict(tudje), 'tudje_izmene_po_pokretanju': dict(tudje_run),
        'zidno_s_po_fazi': {k: round(v, 1) for k, v in zidno.items()}, 'upita_hook_po_fazi': dict(ctx['hook']),
        'po_fazi': [u_recnik(['faza'], k, r) for k, r in grupe['faza'].items()],
        'po_agentu': [u_recnik(['agent'], k, r) for k, r in grupe['agent'].items()],
        'po_modelu': [u_recnik(['model'], k, r) for k, r in grupe['model'].items()],
        'detalj': [u_recnik(['faza', 'agent', 'model'], k, r) for k, r in grupe['detalj'].items()],
    }
    with open(os.path.join(izlaz, 'izvestaj_faza.json'), 'w', encoding='utf-8') as f:
        json.dump(podaci, f, ensure_ascii=False, indent=1)
    print(tekst)
    return 0


if __name__ == '__main__':
    sys.exit(main())
