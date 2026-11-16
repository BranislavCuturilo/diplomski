# -*- coding: utf-8 -*-
"""Upisuje pocetak faze izrade u .claude/usage/faze.jsonl tekuceg projekta.

    python scripts/faza.py <ime>     (planiranje, delegiranje, implementacija, kontrolni skup, poruka klijentu)

Faza traje do sledeceg upisa. Pokrece se iz foldera projekta (mora imati marker).
Cita ga hooks/log_prompt.py i scripts/izvestaj_faza.py.
"""
import json, os, sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'hooks'))
import projekat


def main():
    ime = ' '.join(sys.argv[1:]).replace('-', ' ').replace('_', ' ').strip().lower()
    if ime not in projekat.FAZE:
        print('Nepoznata faza "%s". Faze: %s' % (ime, ', '.join(projekat.FAZE)), file=sys.stderr)
        return 2
    koren = projekat.koren(os.getcwd())
    if koren is None:
        print('Ovde nema markera %s; pokreni iz foldera projekta.' % projekat.MARKER, file=sys.stderr)
        return 2
    folder = projekat.usage_folder(koren)
    os.makedirs(folder, exist_ok=True)
    zapis = {'vreme': projekat.sada(), 'faza': ime}
    with open(os.path.join(folder, 'faze.jsonl'), 'a', encoding='utf-8') as f:
        f.write(json.dumps(zapis, ensure_ascii=False) + '\n')
    print('[faza] %s od %s' % (ime, zapis['vreme']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
