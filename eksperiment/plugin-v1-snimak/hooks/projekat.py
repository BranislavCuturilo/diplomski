# -*- coding: utf-8 -*-
"""Zajednicki deo hookova i skripti: da li je ovo projekat diplomskog i koja je tekuca faza.

Plugin u maticnom folderu vazi za SVE projekte, a meri i odbija samo tamo gde postoji
marker .claude/diplomski-projekat. Ovo je jedino mesto koje to odlucuje.
"""
import datetime, json, os

MARKER = os.path.join('.claude', 'diplomski-projekat')
FAZE = ['planiranje', 'delegiranje', 'implementacija', 'kontrolni skup', 'poruka klijentu']
# poruke koje alat salje kao da su upit, a korisnik ih nije napisao
NIJE_UPIT = ('<local-command', '<task-notification', '[Request interrupted')


def koren(polazna=None):
    """Najblizi folder sa markerom, od polazne putanje navise; None ako ga nema."""
    tekuci = os.path.abspath(os.environ.get('CLAUDE_PROJECT_DIR') or polazna or os.getcwd())
    while True:
        if os.path.isfile(os.path.join(tekuci, MARKER)):
            return tekuci
        roditelj = os.path.dirname(tekuci)
        if roditelj == tekuci:
            return None
        tekuci = roditelj


def usage_folder(projekat):
    return os.path.join(projekat, '.claude', 'usage')


def sada():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')


def tekuca_faza(projekat):
    """Poslednja faza upisana kroz scripts/faza.py; None dok nijedna nije upisana."""
    put = os.path.join(usage_folder(projekat), 'faze.jsonl')
    faza = None
    if os.path.exists(put):
        with open(put, encoding='utf-8') as f:
            for red in f:
                if red.strip():
                    faza = json.loads(red).get('faza')
    return faza
