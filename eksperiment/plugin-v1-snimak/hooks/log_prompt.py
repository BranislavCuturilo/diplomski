# -*- coding: utf-8 -*-
"""UserPromptSubmit: belezi jedan JSON red po upitu u .claude/usage/prompts.jsonl.

Polja: vreme, sesija, faza, duzina, tekst (ceo upit).
Nikad ne blokira upit: svaka greska se guta, izlaz je uvek 0 i nista se ne ispisuje.
"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    try:
        import projekat
        ulaz = json.load(sys.stdin)
        tekst = ulaz.get('prompt') or ''
        if tekst.lstrip().startswith(projekat.NIJE_UPIT):
            return 0
        koren = os.environ.get('DIPLOMSKI_PROJEKAT') or projekat.koren(ulaz.get('cwd'))
        zapis = {
            'vreme': projekat.sada(),
            'sesija': ulaz.get('session_id'),
            'faza': projekat.tekuca_faza(koren),
            'duzina': len(tekst),
            'tekst': tekst,
        }
        folder = projekat.usage_folder(koren)
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, 'prompts.jsonl'), 'a', encoding='utf-8', errors='backslashreplace') as f:
            f.write(json.dumps(zapis, ensure_ascii=False) + '\n')
    except Exception:
        pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
