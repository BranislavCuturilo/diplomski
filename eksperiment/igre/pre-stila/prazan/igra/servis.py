"""Veza izmedju sesije, baze i pravila.

Samo recnici koje prave funkcije iz ovog modula smeju do sablona i API-ja. Svako polje je
navedeno izricito, da seme, sansa, tezina i oznaka tihog zadatka ne bi izasli sa servera.
"""

import json
import secrets
from decimal import ROUND_HALF_UP, Decimal

from django.db import IntegrityError, transaction

from igra import parametri as p
from igra import pravila
from igra.models import Partija, Potez
from igra.pravila import Izbori

KLJUC_SESIJE = "partija_id"
POLJA_IZBORA = {
    "model": p.MODELI,
    "nivo": p.NIVOI,
    "kontekst": p.KONTEKSTI,
    "podela": p.PODELE,
}
POLJA_ZAHTEVA = {"krug", *POLJA_IZBORA}


class NeispravanZahtev(Exception):
    """Odgovara kodu 400."""


class SukobStanja(Exception):
    """Odgovara kodu 409."""


def _sa_zarezom(tekst):
    return tekst.replace(".", ",")


def _bez_negativne_nule(vrednost):
    return abs(vrednost) if vrednost == 0 else vrednost


def format_cene(vrednost):
    return _sa_zarezom(
        f"{_bez_negativne_nule(vrednost.quantize(Decimal('0.001'), ROUND_HALF_UP)):f}"
    )


def format_minuta(vrednost):
    tekst = f"{_bez_negativne_nule(vrednost.quantize(Decimal('0.01'), ROUND_HALF_UP)):f}"
    return _sa_zarezom(tekst.rstrip("0").rstrip("."))


def format_mnozioca(vrednost):
    tekst = f"{vrednost:f}"
    if "." in tekst:
        tekst = tekst.rstrip("0").rstrip(".")
    return _sa_zarezom(tekst)


def _ucitaj_poteze(partija):
    return [
        Izbori(potez.model, potez.nivo, potez.kontekst, potez.podela)
        for potez in partija.potezi.all()
    ]


def nadji_partiju(sesija):
    return Partija.objects.filter(pk=sesija.get(KLJUC_SESIJE)).first()


def je_zavrsena(partija):
    return partija.potezi.count() >= p.BROJ_KRUGOVA


def nova_partija(sesija):
    """Pravi partiju samo ako nijedna nije u toku."""
    postojeca = nadji_partiju(sesija)
    if postojeca is not None and not je_zavrsena(postojeca):
        return postojeca
    partija = Partija.objects.create(seme=secrets.token_hex(16))
    sesija[KLJUC_SESIJE] = partija.pk
    return partija


def procitaj_zahtev(telo):
    try:
        podaci = json.loads(telo)
    except (ValueError, RecursionError):
        raise NeispravanZahtev("Захтев није исправан JSON.") from None

    if not isinstance(podaci, dict) or set(podaci) != POLJA_ZAHTEVA:
        raise NeispravanZahtev("Захтев нема тражена поља.")

    krug = podaci["krug"]
    if not isinstance(krug, int) or isinstance(krug, bool):
        raise NeispravanZahtev("Број круга није исправан.")

    for polje, dozvoljeno in POLJA_IZBORA.items():
        vrednost = podaci[polje]
        if not isinstance(vrednost, str) or vrednost not in dozvoljeno:
            raise NeispravanZahtev("Непознат избор.")

    return krug, Izbori(podaci["model"], podaci["nivo"], podaci["kontekst"], podaci["podela"])


def odigraj_potez(sesija, krug, izbori):
    partija = nadji_partiju(sesija)
    if partija is None:
        raise SukobStanja("Нема партије у току.")

    try:
        with transaction.atomic():
            tekuci = partija.potezi.count() + 1
            if tekuci > p.BROJ_KRUGOVA:
                raise SukobStanja("Игра је завршена.")
            if krug != tekuci:
                raise SukobStanja("Потез не важи за текући круг.")
            Potez.objects.create(partija=partija, krug=krug, **izbori._asdict())
    except IntegrityError:
        raise SukobStanja("Потез за овај круг је већ одигран.") from None

    return _odgovor_na_potez(partija)


def _javni_zadatak(krug):
    return {"krug": krug, "naziv": pravila.zadatak_kruga(krug).naziv}


def _javni_red_istorije(ishod):
    return {
        "krug": ishod.krug,
        "naziv": pravila.zadatak_kruga(ishod.krug).naziv,
        "status": ishod.status,
        "cena": format_cene(ishod.cena),
        "minuti": format_minuta(ishod.minuti),
    }


def _javno_stanje_budzeta(stanje):
    return {
        "budzet_preostalo": format_cene(stanje.budzet_preostalo),
        "rok_preostalo": format_minuta(stanje.rok_preostalo),
        "budzet_prekoracen": stanje.budzet_prekoracen,
        "rok_prekoracen": stanje.rok_prekoracen,
    }


def _odgovor_na_potez(partija):
    stanje = pravila.vidljivo_stanje(partija.seme, _ucitaj_poteze(partija))
    poslednji = stanje.krugovi[-1]
    zavrsena = len(stanje.krugovi) >= p.BROJ_KRUGOVA
    return {
        "krug": poslednji.krug,
        "status": poslednji.status,
        "cena": format_cene(poslednji.cena),
        "minuti": format_minuta(poslednji.minuti),
        **_javno_stanje_budzeta(stanje),
        "sledeci": None if zavrsena else _javni_zadatak(poslednji.krug + 1),
        "zavrsena": zavrsena,
    }


def _javna_grupa(polje, naslov, opcije):
    return {
        "polje": polje,
        "naslov": naslov,
        "opcije": [
            {"kljuc": kljuc, "naziv": naziv, "detalji": detalji}
            for kljuc, naziv, detalji in opcije
        ],
    }


def _oznaka_tokena(mnozilac):
    return f"токени ×{format_mnozioca(mnozilac)}"


def _oznaka_vremena(mnozilac):
    return f"време ×{format_mnozioca(mnozilac)}"


def javne_opcije():
    return [
        _javna_grupa(
            "model",
            "Модел",
            [
                (k, m.naziv, [f"{m.cena:.2f} $/M".replace(".", ","), _oznaka_vremena(m.brzina)])
                for k, m in p.MODELI.items()
            ],
        ),
        _javna_grupa(
            "nivo",
            "Ниво размишљања",
            [
                (k, n.naziv, [_oznaka_tokena(n.tokeni), _oznaka_vremena(n.brzina)])
                for k, n in p.NIVOI.items()
            ],
        ),
        _javna_grupa(
            "kontekst",
            "Контекст",
            [(k, c.naziv, [_oznaka_tokena(c.tokeni)]) for k, c in p.KONTEKSTI.items()],
        ),
        _javna_grupa(
            "podela",
            "Подела посла",
            [
                (k, d.naziv, [_oznaka_tokena(d.tokeni), _oznaka_vremena(d.brzina)])
                for k, d in p.PODELE.items()
            ],
        ),
    ]


def kontekst_pocetka():
    return {
        "broj_krugova": p.BROJ_KRUGOVA,
        "budzet": format_mnozioca(p.BUDZET),
        "rok": format_mnozioca(p.ROK),
    }


def kontekst_igre(partija):
    potezi = _ucitaj_poteze(partija)
    stanje = pravila.vidljivo_stanje(partija.seme, potezi)
    istorija = [_javni_red_istorije(ishod) for ishod in stanje.krugovi]
    krug = len(potezi) + 1
    return {
        "broj_krugova": p.BROJ_KRUGOVA,
        "krug": krug,
        "naziv": pravila.zadatak_kruga(krug).naziv,
        "segmenti": [i < len(potezi) for i in range(p.BROJ_KRUGOVA)],
        "opcije": javne_opcije(),
        "istorija": istorija,
        "poslednji": istorija[-1] if istorija else None,
        **_javno_stanje_budzeta(stanje),
    }


def kontekst_kraja(partija):
    rezultat = pravila.konacni_rezultat(partija.seme, _ucitaj_poteze(partija))
    return {
        "poeni": rezultat.poeni,
        "ocena": rezultat.ocena,
        "ukupna_cena": format_cene(rezultat.ukupna_cena),
        "ukupni_minuti": format_minuta(rezultat.ukupni_minuti),
        "budzet": format_mnozioca(p.BUDZET),
        "rok": format_mnozioca(p.ROK),
        "tihe_greske": [_javni_zadatak(z.krug) for z in rezultat.tihe_greske],
        "lekcije": [{"tekst": l.tekst, "odeljak": l.odeljak} for l in rezultat.lekcije],
        "napomena": p.NAPOMENA_O_PARAMETRIMA,
    }
