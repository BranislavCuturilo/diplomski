"""Pravila igre kao ciste funkcije: ishod zavisi samo od semena i odluka."""

import random
from dataclasses import dataclass
from decimal import Decimal
from typing import NamedTuple, Sequence

from igra import parametri as p

USPEH = "uspeh"
DORADA = "dorada"
TIHI_NEUSPEH = "tihi_neuspeh"


class Izbori(NamedTuple):
    model: str
    nivo: str
    kontekst: str
    podela: str


@dataclass(frozen=True)
class Racun:
    cena: Decimal
    minuti: Decimal
    sansa: int


@dataclass(frozen=True)
class IshodKruga:
    krug: int
    vrsta: str
    status: str
    cena: Decimal
    minuti: Decimal
    osnovna_cena: Decimal
    osnovni_minuti: Decimal


@dataclass(frozen=True)
class VidljivoStanje:
    krugovi: tuple
    budzet_preostalo: Decimal
    rok_preostalo: Decimal

    @property
    def budzet_prekoracen(self):
        return self.budzet_preostalo < 0

    @property
    def rok_prekoracen(self):
        return self.rok_preostalo < 0


@dataclass(frozen=True)
class KonacniRezultat:
    poeni: int
    ocena: str
    ukupna_cena: Decimal
    ukupni_minuti: Decimal
    tihe_greske: tuple
    lekcije: tuple


def zadatak_kruga(krug):
    return p.ZADACI[krug - 1]


def ogranici_sansu(sansa):
    return max(p.SANSA_MIN, min(p.SANSA_MAX, sansa))


def racun_poteza(krug, izbori):
    tezina = zadatak_kruga(krug).tezina
    model = p.MODELI[izbori.model]
    nivo = p.NIVOI[izbori.nivo]
    kontekst = p.KONTEKSTI[izbori.kontekst]
    podela = p.PODELE[izbori.podela]

    tokeni = p.BAZA_TOKENA[tezina] * nivo.tokeni * kontekst.tokeni * podela.tokeni
    cena = tokeni / p.TOKENA_PO_JEDINICI_CENE * model.cena
    minuti = p.BAZA_MINUTA[tezina] * model.brzina * nivo.brzina * podela.brzina
    sansa = ogranici_sansu(
        model.sansa[tezina] + nivo.bonus[tezina] + kontekst.bonus[tezina] + podela.bonus
    )
    return Racun(cena, minuti, sansa)


def uspeh_kruga(seme, krug, sansa):
    return random.Random(f"{seme}:{krug}").randint(1, p.KOCKA_MAX) <= sansa


def odigraj_krug(seme, krug, izbori):
    racun = racun_poteza(krug, izbori)
    cena, minuti = racun.cena, racun.minuti

    if uspeh_kruga(seme, krug, racun.sansa):
        vrsta, status = USPEH, p.STATUS_GOTOVO
    elif zadatak_kruga(krug).tih:
        vrsta, status = TIHI_NEUSPEH, p.STATUS_GOTOVO
    else:
        vrsta, status = DORADA, p.STATUS_DORADA
        cena *= p.DORADA_PUTA
        minuti *= p.DORADA_PUTA

    return IshodKruga(krug, vrsta, status, cena, minuti, racun.cena, racun.minuti)


def _odigraj_sve(seme, potezi):
    return tuple(odigraj_krug(seme, krug, izbori) for krug, izbori in enumerate(potezi, start=1))


def vidljivo_stanje(seme, potezi: Sequence[Izbori]):
    krugovi = _odigraj_sve(seme, potezi)
    return VidljivoStanje(
        krugovi=krugovi,
        budzet_preostalo=p.BUDZET - sum((k.cena for k in krugovi), Decimal(0)),
        rok_preostalo=p.ROK - sum((k.minuti for k in krugovi), Decimal(0)),
    )


def ocena_za_poene(poeni):
    for granica, ocena in p.OCENE:
        if poeni >= granica:
            return ocena
    return p.OCENE[-1][1]


def _lekcija_vazi(lekcija, potezi, tihe_greske):
    if lekcija.polje is None:
        return bool(tihe_greske)
    return any(
        getattr(izbori, lekcija.polje) == lekcija.vrednost
        and (lekcija.tezina is None or zadatak_kruga(krug).tezina == lekcija.tezina)
        for krug, izbori in enumerate(potezi, start=1)
    )


def konacni_rezultat(seme, potezi: Sequence[Izbori]):
    if len(potezi) != p.BROJ_KRUGOVA:
        raise ValueError("Konacni rezultat postoji samo za zavrsenu partiju.")

    krugovi = _odigraj_sve(seme, potezi)
    poeni = p.POCETNI_POENI
    ukupna_cena = sum((k.cena for k in krugovi), Decimal(0))
    ukupni_minuti = sum((k.minuti for k in krugovi), Decimal(0))

    poeni -= p.DORADA_POENI * sum(k.vrsta == DORADA for k in krugovi)

    tihe_greske = tuple(k for k in krugovi if k.vrsta == TIHI_NEUSPEH)
    for greska in tihe_greske:
        ukupna_cena += p.TIHI_DODATAK_CENE_PUTA * greska.osnovna_cena
        ukupni_minuti += p.TIHI_DODATAK_MINUTA_PUTA * greska.osnovni_minuti
        poeni -= p.TIHI_POENI

    # Prekoracenje se proverava tek posle troskova tihih gresaka.
    if ukupna_cena > p.BUDZET:
        poeni -= p.KAZNA_BUDZET
    if ukupni_minuti > p.ROK:
        poeni -= p.KAZNA_ROK

    poeni = max(p.MIN_POENI, poeni)
    return KonacniRezultat(
        poeni=poeni,
        ocena=ocena_za_poene(poeni),
        ukupna_cena=ukupna_cena,
        ukupni_minuti=ukupni_minuti,
        tihe_greske=tuple(zadatak_kruga(g.krug) for g in tihe_greske),
        lekcije=tuple(l for l in p.LEKCIJE if _lekcija_vazi(l, potezi, tihe_greske)),
    )
