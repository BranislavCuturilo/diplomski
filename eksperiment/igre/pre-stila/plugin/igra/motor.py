"""Motor igre: prima stanje i izbore, vraca novo stanje. Bez Django-a; brojevi su u parametri.py."""

import copy
import itertools
import random

from . import parametri as p

USPEH = "uspeh"
DORADA = "dorada"
TIHI_NEUSPEH = "tih_neuspeh"

GRUPE_IZBORA = {
    "model": p.MODELI,
    "nivo": p.NIVOI,
    "kontekst": p.KONTEKSTI,
    "podela": p.PODELE,
}


class NepoznatIzbor(ValueError):
    pass


class PogresanKrug(Exception):
    pass


class IgraZavrsena(Exception):
    pass


def nova_igra(seme):
    return {
        "seme": seme,
        "krug": 1,
        "zavrsena": False,
        "potroseno": 0.0,
        "minuti": 0.0,
        "istorija": [],
        "rezultat": None,
    }


def proveri_izbore(izbori):
    if not isinstance(izbori, dict) or set(izbori) != set(GRUPE_IZBORA):
        raise NepoznatIzbor("pogresan skup izbora")
    for grupa, opcije in GRUPE_IZBORA.items():
        vrednost = izbori[grupa]
        # Tip pre `in`: `[] in dict` baca TypeError.
        if not isinstance(vrednost, str) or vrednost not in opcije:
            raise NepoznatIzbor(grupa)


def racun(tezina, izbori):
    baza = p.BAZA[tezina]
    model = p.MODELI[izbori["model"]]
    nivo = p.NIVOI[izbori["nivo"]]
    kontekst = p.KONTEKSTI[izbori["kontekst"]]
    podela = p.PODELE[izbori["podela"]]

    tokeni = baza["tokeni"] * nivo["tokeni"] * kontekst["tokeni"] * podela["tokeni"]
    sansa = (
        model["sansa"][tezina]
        + nivo["bonus"][tezina]
        + kontekst["bonus"][tezina]
        + podela["bonus"]
    )
    return {
        "cena": tokeni / p.TOKENA_PO_MILION * model["cena"],
        "minuti": baza["minuti"] * model["brzina"] * nivo["brzina"] * podela["brzina"],
        "sansa": min(max(sansa, p.SANSA_MIN), p.SANSA_MAX),
    }


def uspeh_kruga(seme, krug, sansa):
    return random.Random(f"{seme}:{krug}").randint(p.KOCKA_MIN, p.KOCKA_MAX) <= sansa


def _zadatak(krug):
    return p.ZADACI[krug - 1]


def odigraj_potez(stanje, krug, izbori):
    proveri_izbore(izbori)
    if stanje["zavrsena"]:
        raise IgraZavrsena()
    if krug != stanje["krug"]:
        raise PogresanKrug()

    zadatak = _zadatak(krug)
    r = racun(zadatak["tezina"], izbori)
    cena, minuti = r["cena"], r["minuti"]
    if uspeh_kruga(stanje["seme"], krug, r["sansa"]):
        ishod = USPEH
    elif zadatak["tih"]:
        ishod = TIHI_NEUSPEH
    else:
        ishod = DORADA
        cena *= p.MNOZILAC_DORADE
        minuti *= p.MNOZILAC_DORADE

    novo = copy.deepcopy(stanje)
    novo["istorija"].append(
        {"krug": krug, "izbori": dict(izbori), "cena": cena, "minuti": minuti, "ishod": ishod}
    )
    novo["potroseno"] += cena
    novo["minuti"] += minuti
    if krug == p.KRUGOVA:
        return kontrolni_skup(novo)
    novo["krug"] = krug + 1
    return novo


def kontrolni_skup(stanje):
    novo = copy.deepcopy(stanje)
    istorija = novo["istorija"]
    tihi = [r for r in istorija if r["ishod"] == TIHI_NEUSPEH]
    dorada = sum(1 for r in istorija if r["ishod"] == DORADA)
    tihe_greske = [
        {
            "krug": r["krug"],
            "zadatak": _zadatak(r["krug"])["naziv"],
            "dodatak_cena": r["cena"] * p.DODATAK_TIHA_CENA,
            "dodatak_minuti": r["minuti"] * p.DODATAK_TIHA_MINUTI,
        }
        for r in tihi
    ]

    # Kazna se racuna posle dodataka; round uklanja sum sabiranja, poredjenje je strogo.
    cena = novo["potroseno"] + sum(g["dodatak_cena"] for g in tihe_greske)
    minuti = novo["minuti"] + sum(g["dodatak_minuti"] for g in tihe_greske)
    budzet_prekoracen = round(cena, p.DECIMALA_POREDJENJA) > p.BUDZET
    rok_prekoracen = round(minuti, p.DECIMALA_POREDJENJA) > p.ROK

    poeni = p.POCETNI_POENI - p.KAZNA_DORADA * dorada - p.KAZNA_TIHA * len(tihi)
    if budzet_prekoracen:
        poeni -= p.KAZNA_BUDZET
    if rok_prekoracen:
        poeni -= p.KAZNA_ROK
    poeni = max(poeni, p.MIN_POENI)

    # Dodaci ulaze u potroseno da se budzet na zavrsnom ekranu slaze sa ukupnom cenom.
    novo["potroseno"] = cena
    novo["minuti"] = minuti
    novo["zavrsena"] = True
    novo["rezultat"] = {
        "poeni": poeni,
        "ocena": oceni(poeni),
        "ukupna_cena": cena,
        "ukupni_minuti": minuti,
        "budzet_prekoracen": budzet_prekoracen,
        "rok_prekoracen": rok_prekoracen,
        "tihe_greske": tihe_greske,
        "lekcije": lekcije(novo),
    }
    return novo


def oceni(poeni):
    return next(tekst for prag, tekst in p.OCENE if poeni >= prag)


def lekcije(stanje):
    istorija = stanje["istorija"]
    uslovi = {
        "tiha": any(r["ishod"] == TIHI_NEUSPEH for r in istorija),
        "opus_lako": any(
            r["izbori"]["model"] == "opus" and _zadatak(r["krug"])["tezina"] == p.TEZINA_LAKA
            for r in istorija
        ),
        "max": any(r["izbori"]["nivo"] == "max" for r in istorija),
        "sve": any(r["izbori"]["kontekst"] == "sve" for r in istorija),
        "pedeset": any(r["izbori"]["podela"] == "pedeset" for r in istorija),
    }
    return [dict(lekcija) for kljuc, lekcija in p.LEKCIJE.items() if uslovi[kljuc]]


def _javno(vrednost):
    # + 0.0 pretvara -0.0 u 0.0: tacno pogodjen limit inace daje "-0" na ekranu.
    return round(vrednost, p.DECIMALA_JAVNIH) + 0.0


def procene(tezina):
    rezultat = {}
    for model, nivo, kontekst, podela in itertools.product(*GRUPE_IZBORA.values()):
        r = racun(tezina, {"model": model, "nivo": nivo, "kontekst": kontekst, "podela": podela})
        rezultat[f"{model}|{nivo}|{kontekst}|{podela}"] = {
            "cena": _javno(r["cena"]),
            "minuti": _javno(r["minuti"]),
        }
    return rezultat


def javne_opcije():
    return {
        grupa: [
            {"kljuc": kljuc, "naziv": opcija["naziv"], "opis": opcija["opis"]}
            for kljuc, opcija in opcije.items()
        ]
        for grupa, opcije in GRUPE_IZBORA.items()
    }


def _javni_limit(limit, potroseno):
    return {
        "limit": limit,
        "potroseno": _javno(potroseno),
        "preostalo": _javno(limit - potroseno),
    }


def _javni_poslednji(istorija):
    if not istorija:
        return None
    r = istorija[-1]
    return {
        "krug": r["krug"],
        "zadatak": _zadatak(r["krug"])["naziv"],
        "cena": _javno(r["cena"]),
        "minuti": _javno(r["minuti"]),
        # Uspeh i tih neuspeh moraju dati isti tekst.
        "status": p.STATUS_DORADA if r["ishod"] == DORADA else p.STATUS_GOTOVO,
    }


def _javni_zavrsni(rezultat):
    return {
        "poeni": rezultat["poeni"],
        "ocena": rezultat["ocena"],
        "ukupna_cena": _javno(rezultat["ukupna_cena"]),
        "ukupni_minuti": _javno(rezultat["ukupni_minuti"]),
        "budzet_prekoracen": rezultat["budzet_prekoracen"],
        "rok_prekoracen": rezultat["rok_prekoracen"],
        "tihe_greske": [
            {
                "krug": g["krug"],
                "zadatak": g["zadatak"],
                "dodatak_cena": _javno(g["dodatak_cena"]),
                "dodatak_minuti": _javno(g["dodatak_minuti"]),
            }
            for g in rezultat["tihe_greske"]
        ],
        "lekcije": [{"tekst": l["tekst"], "odeljak": l["odeljak"]} for l in rezultat["lekcije"]],
        "napomena": p.NAPOMENA,
    }


def javni_prikaz(stanje):
    """Jedini izlaz stanja ka klijentu: bela lista, polje po polje, nikad kopija stanja."""
    zavrsena = stanje["zavrsena"]
    krug = stanje["krug"]
    zadatak = None if zavrsena else _zadatak(krug)
    return {
        "faza": "zavrsena" if zavrsena else "igra",
        "krug": krug,
        "ukupno_krugova": p.KRUGOVA,
        "zadatak": None if zavrsena else {"naziv": zadatak["naziv"]},
        "budzet": _javni_limit(p.BUDZET, stanje["potroseno"]),
        "rok": _javni_limit(p.ROK, stanje["minuti"]),
        "poslednji": _javni_poslednji(stanje["istorija"]),
        "procene": None if zavrsena else procene(zadatak["tezina"]),
        "zavrsni": _javni_zavrsni(stanje["rezultat"]) if zavrsena else None,
    }
