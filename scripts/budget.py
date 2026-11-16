# -*- coding: utf-8 -*-
"""Buzet konteksta, tri velicine iz odeljka 6.4: stalni trosak, trosak pri ucitavanju, trosak poziva agenta.

    python scripts/budget.py [--strict]

Opis skilla i agenta stoji u kontekstu stalno; telo skilla tek kada se pozove;
reference tek kada se otvore. Poziv agenta placa njegovo telo i pun SKILL.md svakog
skilla iz zaglavlja. Procena: 4 znaka = 1 token.
--strict: izlazni kod 1 ako je neka granica predjena (za CI).
"""
import glob, os, re, sys

sys.stdout.reconfigure(encoding='utf-8')
KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_OPIS = 600          # znakova po opisu agenta
OPIS_SKILLA = (300, 450)  # znakova, tabela 7 rada
MAX_TELO = 12000        # znakova u SKILL.md
MAX_UVEK = 6000         # tokena: zbir svih opisa, placa se u svakoj sesiji


def opis(tekst):
    """Vrednost description iz zaglavlja: ili u istom redu, ili uvuceni redovi posle 'description: >'."""
    redovi = tekst.split('\n')
    for i, r in enumerate(redovi):
        if r.startswith('description:'):
            deo = [r[len('description:'):].strip(' >')]
            for s in redovi[i + 1:]:
                if not s.startswith((' ', '\t')):
                    break
                deo.append(s.strip())
            return ' '.join(x for x in deo if x)
    return ''


def skillovi_agenta(tekst):
    red = next((r for r in tekst.split('\n') if r.startswith('skills:')), 'skills:')
    return [s.strip() for s in red[len('skills:'):].split(',') if s.strip()]


def trosak_poziva(put, velicina_skilla):
    t = open(put, encoding='utf-8').read()
    return len(t) + sum(velicina_skilla[s] for s in skillovi_agenta(t))


def main():
    prekoracenja, uvek = [], 0
    print('%-40s %6s %7s' % ('fajl', 'opis', 'telo'))
    for put in sorted(glob.glob(os.path.join(KOREN, 'skills', '*', '*', 'SKILL.md')) +
                      glob.glob(os.path.join(KOREN, 'agents', '*.md'))):
        t = open(put, encoding='utf-8').read()
        o = len(opis(t))
        uvek += o
        ime = os.path.relpath(put, KOREN).replace('\\', '/')
        print('%-40s %6d %7d' % (ime[-40:], o, len(t)))
        if put.endswith('SKILL.md'):
            if not OPIS_SKILLA[0] <= o <= OPIS_SKILLA[1]:
                prekoracenja.append('%s: opis %d znakova, a treba %d-%d' % (ime, o, OPIS_SKILLA[0], OPIS_SKILLA[1]))
            if len(t) > MAX_TELO:
                prekoracenja.append('%s: telo %d > %d znakova, podeli u references/' % (ime, len(t), MAX_TELO))
        elif o > MAX_OPIS:
            prekoracenja.append('%s: opis %d > %d znakova' % (ime, o, MAX_OPIS))
    velicina_skilla = {os.path.basename(os.path.dirname(p)): len(open(p, encoding='utf-8').read())
                       for p in glob.glob(os.path.join(KOREN, 'skills', '*', '*', 'SKILL.md'))}
    print('\nTrosak poziva agenta (telo + skillovi iz zaglavlja):')
    for put in sorted(glob.glob(os.path.join(KOREN, 'agents', '*.md'))):
        n = trosak_poziva(put, velicina_skilla)
        print('%-40s %7d znakova  ~%d tokena' % (os.path.basename(put)[:-3], n, n // 4))
    tok = uvek // 4
    print('\nUvek u kontekstu: ~%d tokena (granica %d)' % (tok, MAX_UVEK))
    if tok > MAX_UVEK:
        prekoracenja.append('zbir opisa ~%d tokena > %d' % (tok, MAX_UVEK))
    for p in prekoracenja:
        print('PREKORACENO:', p)
    return 1 if prekoracenja and '--strict' in sys.argv else 0


if __name__ == '__main__':
    sys.exit(main())
