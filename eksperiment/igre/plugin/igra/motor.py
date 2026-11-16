"""Motor igre: prima stanje i izbore, vraca novo stanje. Bez Django-a; brojevi su u parametri.py.

Vraca kljuceve (zadatak, ocena, status, lekcija), nikad tekst: prevodi igra/tekstovi.py (plan 12.3).
"""

import copy
import hashlib
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


class IgraNijeZavrsena(Exception):
    pass


class VecSacuvano(Exception):
    pass


def nova_igra(seme, dan=None, oznaka=None):
    """Nova partija. Dnevni izazov zadaje i `dan` (ISO, dan pocetka) i `oznaku` (nasumicna, jedinstvena po partiji).

    Kljucevi `dan` i `oznaka` postoje samo kada nisu None, pa je obicna partija ista kao pre dnevnog izazova.
    """
    stanje = {
        "seme": seme,
        "krug": 1,
        "zavrsena": False,
        "potroseno": 0.0,
        "minuti": 0.0,
        "istorija": [],
        "rezultat": None,
        "pravila": p.PRAVILA_TEKUCA,
    }
    if dan is not None:
        stanje["dan"] = dan
    if oznaka is not None:
        stanje["oznaka"] = oznaka
    return stanje


def dan_partije(stanje):
    """Dan dnevnog izazova (ISO) ili None za obicnu partiju; jedino mesto koje cita kljuc."""
    return stanje.get("dan")


def pravila(stanje):
    """Verzija pravila bodovanja partije (plan 13.1); jedino mesto koje cita kljuc.

    Stanje iz sesije pre verzija kljuc nema: ta partija je pocela po verziji PRAVILA_STARA (B2-B).
    """
    return stanje.get("pravila", p.PRAVILA_STARA)


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
            "zadatak": _zadatak(r["krug"])["kljuc"],
            "dodatak_cena": r["cena"] * p.DODATAK_TIHA_CENA,
            "dodatak_minuti": r["minuti"] * p.DODATAK_TIHA_MINUTI,
        }
        for r in tihi
    ]

    # Kazna se racuna posle dodataka; round uklanja sum sabiranja, poredjenje je strogo.
    cena = novo["potroseno"] + sum(g["dodatak_cena"] for g in tihe_greske)
    minuti = novo["minuti"] + sum(g["dodatak_minuti"] for g in tihe_greske)
    rok_prekoracen = round(minuti, p.DECIMALA_POREDJENJA) > p.ROK

    # Budzet u celim brojevima (B3-A): 28,80 sabrano u bilo kom redosledu je tacno 20 %, ne 20,0000001.
    budzet_j = p.BUDZET * p.JEDINICA_POREDJENJA
    preko_j = round(cena * p.JEDINICA_POREDJENJA) - budzet_j
    budzet_prekoracen = preko_j > 0
    # Procenat i broj koraka zaokruzeni navise (-(-a // b)); ekran pokazuje isti procenat, pa se
    # uvek slaze sa kaznom.
    procenat = -(-preko_j * p.PROCENAT // budzet_j) if budzet_prekoracen else 0
    kazne = p.KAZNE[pravila(novo)]
    koraci = -(-procenat // kazne["budzet_korak_procenata"])
    kazna_budzet = min(koraci * kazne["budzet_po_koraku"], kazne["budzet_maks"])

    poeni = (
        p.POCETNI_POENI
        - kazne["dorada"] * dorada
        - kazne["tiha"] * len(tihi)
        - kazna_budzet
    )
    if rok_prekoracen:
        poeni -= kazne["rok"]
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
        # Ceo procenat prekoracenja (0 bez prekoracenja) i njegova kazna u poenima (B4-B).
        "budzet_procenat": procenat,
        "kazna_budzet": kazna_budzet,
        "rok_prekoracen": rok_prekoracen,
        "tihe_greske": tihe_greske,
        "lekcije": lekcije(novo),
    }
    return novo


def oceni(poeni):
    return next(kljuc for prag, kljuc in p.OCENE if poeni >= prag)


def nadogradi(stanje):
    """Stanje iz sesije pre kljuceva i verzija pravila (plan 12.4, 13.1).

    Stanje bez kljuca "pravila", zavrseno ili ne, dobija verziju PRAVILA_STARA: po njoj je pocelo.
    Zavrsena partija pre kljuceva nosi srpski tekst ocene, zadatka i lekcija; kljucevi se ne
    preslikavaju iz teksta nego racunaju istim pravilima kao kontrolni_skup: ocena iz poena, zadatak
    iz kruga, lekcije iz istorije. Poeni se ne preracunavaju, pa stari rezultat ne dobija ni
    budzet_procenat ni kazna_budzet. Idempotentno; ulaz ostaje netaknut; nezavrsena partija sa
    verzijom vraca se ista.
    """
    if stanje is None:
        return None
    if not stanje["zavrsena"] and "pravila" in stanje:
        return stanje
    novo = copy.deepcopy(stanje)
    novo["pravila"] = pravila(stanje)
    if not novo["zavrsena"]:
        return novo
    rezultat = novo["rezultat"]
    rezultat["ocena"] = oceni(rezultat["poeni"])
    for greska in rezultat["tihe_greske"]:
        greska["zadatak"] = _zadatak(greska["krug"])["kljuc"]
    rezultat["lekcije"] = lekcije(novo)
    return novo


def sacuvani_red(stanje):
    # .get: kljuc nastaje tek pri cuvanju, pa i stanje bez njega (stare sesije) radi.
    return stanje.get("sacuvan")


def za_cuvanje(stanje):
    """Poeni, ocena i verzija pravila za rang listu, samo iz stanja; klijent ih nikad ne salje.

    Dnevna partija dodaje i "dan" (ISO): red ide na listu dana pocetka partije, i posle ponoci. Obicna ga nema
    (ne None), pa je njen recnik isti kao pre dnevnog izazova; prikaz cita `.get("dan")`.
    """
    if not stanje["zavrsena"]:
        raise IgraNijeZavrsena()
    if sacuvani_red(stanje) is not None:
        raise VecSacuvano()
    rezultat = stanje["rezultat"]
    podaci = {"poeni": rezultat["poeni"], "ocena": rezultat["ocena"], "pravila": pravila(stanje)}
    dan = dan_partije(stanje)
    if dan is not None:
        podaci["dan"] = dan
    return podaci


def oznaci_sacuvano(stanje, broj):
    novo = copy.deepcopy(stanje)
    novo["sacuvan"] = broj
    return novo


def za_deljenje(stanje):
    """Snimak zavrsnog ekrana za deljeni link: ista bela lista kao javni_prikaz, nikad kopija stanja."""
    if not stanje["zavrsena"]:
        raise IgraNijeZavrsena()
    return _javni_zavrsni(stanje["rezultat"])


def deljeni_prikaz(snimak):
    # Bela lista i pri citanju: polje koje bi kasnije dospelo u snimak ne izlazi.
    return _javni_zavrsni(snimak)


def podeljeni_red(stanje):
    # .get: kljuc nastaje tek pri deljenju, pa i stanje bez njega (stare sesije) radi.
    return stanje.get("podeljeno")


def oznaci_podeljeno(stanje, broj):
    novo = copy.deepcopy(stanje)
    novo["podeljeno"] = broj
    return novo


def oznaka_partije(stanje):
    # Hes nasumicne vrednosti od 128 bita: jedinstven po partiji, a ona se iz njega ne izvodi. Obicna partija
    # hesira seme. Dnevna hesira svoju `oznaku`: seme dana je isto za sve igrace, pa bi hes semena spojio sve
    # partije dana u jednu (jedinstven Rezultat.partija, dnevnik brisanja po partiji).
    return hashlib.sha256(stanje.get("oznaka", stanje["seme"]).encode("utf-8")).hexdigest()


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
    return [
        {"oznaka": kljuc, "odeljak": lekcija["odeljak"]}
        for kljuc, lekcija in p.LEKCIJE.items()
        if uslovi[kljuc]
    ]


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
        "zadatak": _zadatak(r["krug"])["kljuc"],
        "cena": _javno(r["cena"]),
        "minuti": _javno(r["minuti"]),
        # Pravilo 1: uspeh i tih neuspeh moraju dati isti kljuc, jednim izrazom.
        "status": p.STATUS_DORADA if r["ishod"] == DORADA else p.STATUS_GOTOVO,
    }


def _javni_zavrsni(rezultat):
    return {
        "poeni": rezultat["poeni"],
        "ocena": rezultat["ocena"],
        "ukupna_cena": _javno(rezultat["ukupna_cena"]),
        "ukupni_minuti": _javno(rezultat["ukupni_minuti"]),
        "budzet_prekoracen": rezultat["budzet_prekoracen"],
        # .get: rezultat iz sesije i snimak pre 2026-11-11 ih nemaju; javno su null (B4-B).
        "budzet_procenat": rezultat.get("budzet_procenat"),
        "kazna_budzet": rezultat.get("kazna_budzet"),
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
        # Napomena vise nije u JSON-u: skripta je cita iz tekstovi.za_skriptu (plan 12.3).
        "lekcije": [{"oznaka": l["oznaka"], "odeljak": l["odeljak"]} for l in rezultat["lekcije"]],
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
        "zadatak": None if zavrsena else zadatak["kljuc"],
        "budzet": _javni_limit(p.BUDZET, stanje["potroseno"]),
        "rok": _javni_limit(p.ROK, stanje["minuti"]),
        "poslednji": _javni_poslednji(stanje["istorija"]),
        "procene": None if zavrsena else procene(zadatak["tezina"]),
        "zavrsni": _javni_zavrsni(stanje["rezultat"]) if zavrsena else None,
    }
