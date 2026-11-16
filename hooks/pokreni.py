# -*- coding: utf-8 -*-
"""Jedina ulazna tacka svih hookova: bez markera projekta tih no-op, sa markerom pokrece hook.

    python hooks/pokreni.py <ime>

Ulaz se ovde cita kao UTF-8 i tako prosledjuje hooku. Na Windows-u je sys.stdin cp1252,
pa bi slovo "c" sa kvacicom u upitu srusilo json.load, a hookovi taj izuzetak namerno gutaju:
hook bi cutke prestao da radi.
"""
import io, json, os, runpy, sys

OVDE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(OVDE)
sys.path.insert(0, OVDE)

CILJEVI = {
    'pull': ('scripts/sync.py', ['--pull', '--tiho']),
    'ruter': ('hooks/prompt_router.py', []),
    'upit': ('hooks/log_prompt.py', []),
    'skill': ('hooks/require_skill.py', []),
    'git': ('hooks/git_guard.py', []),
    'upotreba': ('hooks/log_usage.py', []),
    'stop': ('hooks/verify_before_stop.py', []),
    'sync': ('scripts/sync.py', ['--tiho']),
}


def main():
    try:
        import projekat
        tekst = sys.stdin.buffer.read().decode('utf-8', 'replace')
        try:
            ulaz = json.loads(tekst)
        except ValueError:
            ulaz = {}
        koren = projekat.koren(ulaz.get('cwd') if isinstance(ulaz, dict) else None)
        cilj = CILJEVI.get(sys.argv[1] if len(sys.argv) > 1 else '')
    except Exception:
        return 0                                  # kapija nikad ne sme da smeta sesiji
    if koren is None or cilj is None:
        return 0
    putanja = os.path.join(PLUGIN, *cilj[0].split('/'))
    os.environ['DIPLOMSKI_PROJEKAT'] = koren
    sys.stdin = io.StringIO(tekst)
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    sys.argv = [putanja] + cilj[1]
    runpy.run_path(putanja, run_name='__main__')
    return 0


if __name__ == '__main__':
    sys.exit(main())
