# -*- coding: utf-8 -*-
"""Sinhronizacija repozitorijuma pravila sa git-om (poziva je SessionEnd hook, ili rucno).

    python scripts/sync.py [--tiho]

Redosled: commit SAMO putanja pravila (po grupi) -> pull --ff-only -> push.
Nikad `git add -A`: u folderu mogu biti i drugi fajlovi (npr. .docx rada).
Ako se istorije razilaze (oba racunara su commitovala), STAJE i kaze sta da se uradi:
spajanje bez coveka je ono sto craft-git zabranjuje.
"""
import os, subprocess, sys, tempfile

sys.stdout.reconfigure(encoding='utf-8')
KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GRUPE = [('skills', 'pravila: skillovi'), ('agents', 'pravila: agenti'),
         ('hooks', 'pravila: hookovi'), ('scripts', 'merenje'), ('tools', 'alati'), ('tests', 'testovi'),
         ('.claude-plugin', 'plugin manifest'), ('README.md', 'opis')]
TIHO = '--tiho' in sys.argv


def git(*a):
    return subprocess.run(['git', '-C', KOREN, *a], capture_output=True, text=True, encoding='utf-8')


def reci(t):
    if not TIHO:
        print(t)


def samo_pull():
    """Pocetak sesije: bez remote-a nema sta da se povuce, i to nije greska."""
    if git('rev-parse', '--is-inside-work-tree').returncode != 0 or not git('remote').stdout.strip():
        return 0
    if git('pull', '--ff-only', '-q').returncode != 0:
        print('[diplomski] pull nije uspeo: lokalne izmene ili nema mreze; pokreni scripts/sync.py')
    return 0


def main():
    if '--pull' in sys.argv:
        return samo_pull()
    if git('rev-parse', '--is-inside-work-tree').returncode != 0:
        reci('[sync] nije git repozitorijum: ' + KOREN)
        return 0
    for putanja, naslov in GRUPE:
        if not git('status', '--porcelain', '--', putanja).stdout.strip():
            continue
        git('add', '--', putanja)
        with tempfile.NamedTemporaryFile('w', delete=False, encoding='utf-8', suffix='.txt') as f:
            f.write('sync(%s): %s\n\nAutomatski commit na kraju sesije.\n' % (putanja, naslov))
        r = git('commit', '-F', f.name)
        os.unlink(f.name)
        reci('[sync] commit %s: %s' % (putanja, 'ok' if r.returncode == 0 else r.stderr.strip()[:120]))
    if git('remote').stdout.strip() == '':
        reci('[sync] nema remote-a; commit je lokalan')
        return 0
    p = git('pull', '--ff-only', '-q')
    if p.returncode != 0:
        print('[sync] ISTORIJE SE RAZILAZE: drugi racunar je poslao izmene koje nisu ovde. '
              'Pokreni rucno: git -C "%s" pull --rebase, proveri sukobe, pa ponovo sync.' % KOREN)
        return 1
    s = git('push', '-q')
    reci('[sync] push: ' + ('ok' if s.returncode == 0 else s.stderr.strip()[:120]))
    return s.returncode


if __name__ == '__main__':
    sys.exit(main())
