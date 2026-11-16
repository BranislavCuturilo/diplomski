"""Veza izmedju sesije, baze i pravila.

Samo recnici koje prave funkcije iz ovog modula smeju do sablona i API-ja. Svako polje je
navedeno izricito, da seme, sansa, tezina i oznaka tihog zadatka ne bi izasli sa servera.
"""

import hashlib
import hmac
import json
import secrets
import unicodedata
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import dateformat, timezone, translation
from django.utils.translation import gettext as _
from django.utils.translation import gettext_noop as N_

from igra import parametri as p
from igra import pravila
from igra.models import Dogadjaj, Partija, Potez, PrijavaImena, Rezultat
from igra.pravila import Izbori

KLJUC_SESIJE = "partija_id"
KLJUC_DNEVNOG = "dnevni_izazov_dan"
# Anonimni igrac: nasumican kljuc u kolacicu, godinu dana. Po njemu igrac vidi svoje partije i kada
# sesija istekne. Sesija i dalje nosi samo partiju u toku.
KOLACIC_IGRACA = "igrac"
TRAJANJE_KOLACICA_IGRACA = 365 * 24 * 60 * 60
DUZINA_KLJUCA_IGRACA = 32
ZNACI_KLJUCA_IGRACA = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
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
    """Decimalni zarez na srpskom, tacka na engleskom."""
    return tekst if translation.get_language() == "en" else tekst.replace(".", ",")


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


def novi_kljuc_igraca():
    return secrets.token_urlsafe(24)


def ispravan_kljuc_igraca(kljuc):
    return (
        isinstance(kljuc, str)
        and len(kljuc) == DUZINA_KLJUCA_IGRACA
        and set(kljuc) <= ZNACI_KLJUCA_IGRACA
    )


def hes_igraca(kljuc):
    """Baza cuva samo hes kljuca, pa se iz nje ne moze napraviti kolacic tudjeg igraca."""
    if not ispravan_kljuc_igraca(kljuc):
        return ""
    return hashlib.sha256(kljuc.encode()).hexdigest()


def nova_partija(sesija, igrac=""):
    """Pravi partiju samo ako nijedna nije u toku. igrac je hes_igraca kljuca iz kolacica."""
    postojeca = nadji_partiju(sesija)
    if postojeca is not None and not je_zavrsena(postojeca):
        return postojeca
    partija = Partija.objects.create(seme=secrets.token_hex(16), bodovanje=p.BODOVANJE_TEKUCE, igrac=igrac)
    sesija[KLJUC_SESIJE] = partija.pk
    return partija


def danas():
    return timezone.localdate()


def dnevno_seme(dan):
    """Seme dnevnog izazova: isto za sve igrace tog dana, a ne moze se izracunati bez tajnog kljuca."""
    poruka = f"dnevni-izazov:{dan.isoformat()}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), poruka, hashlib.sha256).hexdigest()[:32]


def dnevni_izazov_dostupan(sesija):
    return sesija.get(KLJUC_DNEVNOG) != danas().isoformat()


def nova_dnevna_partija(sesija, igrac=""):
    """Dnevni izazov se igra jednom dnevno po sesiji; partija u toku se nastavlja."""
    postojeca = nadji_partiju(sesija)
    if postojeca is not None and not je_zavrsena(postojeca):
        return postojeca
    if not dnevni_izazov_dostupan(sesija):
        raise SukobStanja(_("Данашњи изазов је већ одигран."))
    dan = danas()
    partija = Partija.objects.create(
        seme=dnevno_seme(dan), bodovanje=p.BODOVANJE_TEKUCE, dan=dan, igrac=igrac
    )
    sesija[KLJUC_SESIJE] = partija.pk
    sesija[KLJUC_DNEVNOG] = dan.isoformat()
    return partija


def _konacni_rezultat(partija):
    """Rezultat po bodovanju sa kojim je partija pocela, ne po onom koje vazi danas."""
    return pravila.konacni_rezultat(partija.seme, _ucitaj_poteze(partija), partija.bodovanje)


def procitaj_zahtev(telo):
    try:
        podaci = json.loads(telo)
    except (ValueError, RecursionError):
        raise NeispravanZahtev(_("Захтев није исправан JSON.")) from None

    if not isinstance(podaci, dict) or set(podaci) != POLJA_ZAHTEVA:
        raise NeispravanZahtev(_("Захтев нема тражена поља."))

    krug = podaci["krug"]
    if not isinstance(krug, int) or isinstance(krug, bool):
        raise NeispravanZahtev(_("Број круга није исправан."))

    for polje, dozvoljeno in POLJA_IZBORA.items():
        vrednost = podaci[polje]
        if not isinstance(vrednost, str) or vrednost not in dozvoljeno:
            raise NeispravanZahtev(_("Непознат избор."))

    return krug, Izbori(podaci["model"], podaci["nivo"], podaci["kontekst"], podaci["podela"])


def odigraj_potez(sesija, krug, izbori):
    partija = nadji_partiju(sesija)
    if partija is None:
        raise SukobStanja(_("Нема партије у току."))

    try:
        with transaction.atomic():
            tekuci = partija.potezi.count() + 1
            if tekuci > p.BROJ_KRUGOVA:
                raise SukobStanja(_("Игра је завршена."))
            if krug != tekuci:
                raise SukobStanja(_("Потез не важи за текући круг."))
            Potez.objects.create(partija=partija, krug=krug, **izbori._asdict())
            if krug == p.BROJ_KRUGOVA:
                # Snimak za istoriju igraca i statistiku; isti racun kao zavrsni ekran.
                Partija.objects.filter(pk=partija.pk).update(
                    zavrsena=timezone.now(), poeni=_konacni_rezultat(partija).poeni
                )
    except IntegrityError:
        raise SukobStanja(_("Потез за овај круг је већ одигран.")) from None

    return _odgovor_na_potez(partija)


def _javni_zadatak(krug):
    return {"krug": krug, "naziv": _(pravila.zadatak_kruga(krug).naziv)}


def _javni_red_istorije(ishod):
    return {
        "krug": ishod.krug,
        "naziv": _(pravila.zadatak_kruga(ishod.krug).naziv),
        "status": _(ishod.status),
        "gotovo": ishod.status == p.STATUS_GOTOVO,
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
        "status": _(poslednji.status),
        "cena": format_cene(poslednji.cena),
        "minuti": format_minuta(poslednji.minuti),
        **_javno_stanje_budzeta(stanje),
        "sledeci": None if zavrsena else _javni_zadatak(poslednji.krug + 1),
        "zavrsena": zavrsena,
    }


def _javna_grupa(polje, naslov, opcije):
    return {
        "polje": polje,
        "naslov": _(naslov),
        "opcije": [
            {"kljuc": kljuc, "naziv": _(naziv), "detalji": detalji}
            for kljuc, naziv, detalji in opcije
        ],
    }


def _oznaka_tokena(mnozilac):
    return _("токени ×%(mnozilac)s") % {"mnozilac": format_mnozioca(mnozilac)}


def _oznaka_vremena(mnozilac):
    return _("време ×%(mnozilac)s") % {"mnozilac": format_mnozioca(mnozilac)}


def javne_opcije():
    return [
        _javna_grupa(
            "model",
            N_("Модел"),
            [
                (k, m.naziv, [_sa_zarezom(f"{m.cena:.2f} $/M"), _oznaka_vremena(m.brzina)])
                for k, m in p.MODELI.items()
            ],
        ),
        _javna_grupa(
            "nivo",
            N_("Ниво размишљања"),
            [
                (k, n.naziv, [_oznaka_tokena(n.tokeni), _oznaka_vremena(n.brzina)])
                for k, n in p.NIVOI.items()
            ],
        ),
        _javna_grupa(
            "kontekst",
            N_("Контекст"),
            [(k, c.naziv, [_oznaka_tokena(c.tokeni)]) for k, c in p.KONTEKSTI.items()],
        ),
        _javna_grupa(
            "podela",
            N_("Подела посла"),
            [
                (k, d.naziv, [_oznaka_tokena(d.tokeni), _oznaka_vremena(d.brzina)])
                for k, d in p.PODELE.items()
            ],
        ),
    ]


def format_datuma(trenutak):
    lokalno = timezone.localtime(trenutak)
    if translation.get_language() == "en":
        return dateformat.format(lokalno, "M j, Y")
    return lokalno.strftime("%d.%m.%Y.")


def ocisti_ime(tekst):
    if not isinstance(tekst, str):
        raise NeispravanZahtev(_("Упиши име."))
    ime = " ".join(unicodedata.normalize("NFC", tekst).split())
    if not ime or len(ime) > p.DUZINA_IMENA_MAX:
        raise NeispravanZahtev(
            _("Име мора имати од 1 до %(najvise)s знакова.") % {"najvise": p.DUZINA_IMENA_MAX}
        )
    if any(unicodedata.category(znak).startswith("C") for znak in ime):
        raise NeispravanZahtev(_("Име садржи недозвољене знакове."))
    return ime


def sacuvaj_rezultat(sesija, sirovo_ime):
    """Cuva rezultat zavrsene partije. Poeni i ocena se uvek racunaju ovde, nikad ne dolaze od klijenta."""
    ime = ocisti_ime(sirovo_ime)
    partija = nadji_partiju(sesija)
    if partija is None or not je_zavrsena(partija):
        raise SukobStanja(_("Нема завршене партије."))

    rezultat = _konacni_rezultat(partija)
    try:
        with transaction.atomic():
            # U istoj transakciji kao i brisanje moderatora, pa se obrisan rezultat ne vraca.
            if _uklonjeno(partija, Dogadjaj.OBRISAN_REZULTAT):
                raise SukobStanja(_("Модератор је уклонио резултат ове партије."))
            if Rezultat.objects.filter(partija=partija).exists():
                raise SukobStanja(_("Резултат ове партије је већ сачуван."))
            return Rezultat.objects.create(
                partija=partija, ime=ime, poeni=rezultat.poeni, ocena=rezultat.ocena
            )
    except IntegrityError:
        raise SukobStanja(_("Резултат ове партије је већ сачуван.")) from None


def _rezultati_liste(dan=None):
    """Bez dana su to obicne partije; sa danom samo partije dnevnog izazova tog dana."""
    if dan:
        return Rezultat.objects.filter(partija__dan=dan)
    return Rezultat.objects.filter(partija__dan__isnull=True)


def _sa_mestima(rezultati):
    """(mesto, rezultat) redom liste. Isti poeni dele mesto (1, 2, 2, 4)."""
    mesto, prethodni_poeni = 0, None
    for redni_broj, rezultat in enumerate(rezultati, start=1):
        if rezultat.poeni != prethodni_poeni:
            mesto, prethodni_poeni = redni_broj, rezultat.poeni
        yield mesto, rezultat


def rang_lista(istaknuta_partija_id=None, dan=None):
    """Najboljih N rezultata jedne liste."""
    return [
        {
            # Broj rezultata, za link kojim se ime prijavljuje (prijavi_ime).
            "pk": rezultat.pk,
            "mesto": mesto,
            "ime": rezultat.ime,
            "poeni": rezultat.poeni,
            # Ocena je sacuvana kao srpski tekst iz OCENE i prevodi se pri prikazu.
            "ocena": _(rezultat.ocena),
            "datum": format_datuma(rezultat.sacuvan),
            "istaknut": rezultat.partija_id == istaknuta_partija_id,
        }
        for mesto, rezultat in _sa_mestima(_rezultati_liste(dan)[: p.BROJ_NA_RANG_LISTI])
    ]


# Javna rang lista za partnere (JSON). Oblik je ugovor sa partnerima: polja se ne uklanjaju i ne
# menjaju znacenje; za takvu izmenu raste VERZIJA_JSON.
VERZIJA_JSON = 1


def _na_svim_jezicima(tekst):
    prevodi = {}
    for kod, _naziv in settings.LANGUAGES:
        with translation.override(kod):
            prevodi[kod] = _(tekst)
    return prevodi


def _javni_redovi(dan=None):
    # Samo ono sto stoji i na pocetnom ekranu: bez broja rezultata, partije, koda linka i semena.
    return [
        {
            "mesto": mesto,
            "ime": rezultat.ime,
            "poeni": rezultat.poeni,
            "ocena": _na_svim_jezicima(rezultat.ocena),
            "sacuvan": timezone.localtime(rezultat.sacuvan).isoformat(timespec="seconds"),
        }
        for mesto, rezultat in _sa_mestima(_rezultati_liste(dan)[: p.BROJ_NA_RANG_LISTI])
    ]


def javna_rang_lista():
    dan = danas()
    return {
        "verzija": VERZIJA_JSON,
        "vreme": timezone.localtime().isoformat(timespec="seconds"),
        "rang_lista": _javni_redovi(),
        "dnevna_lista": {"dan": dan.isoformat(), "rang_lista": _javni_redovi(dan)},
    }


def nadji_za_prijavu(pk):
    """Rezultat koji je sada na javnoj rang listi (glavnoj ili danasnjoj), ili None.

    Igrac moze da prijavi samo ime koje vidi. Zato ni skripta ne moze da zatrpa moderatora
    prijavama rezultata kojih na listi nema.
    """
    rezultat = Rezultat.objects.select_related("partija").filter(pk=pk).first()
    if rezultat is None:
        return None
    dan = rezultat.partija.dan
    if dan is not None and dan != danas():
        return None
    na_listi = _rezultati_liste(dan).values_list("pk", flat=True)[: p.BROJ_NA_RANG_LISTI]
    return rezultat if rezultat.pk in list(na_listi) else None


def prijavi_ime(pk):
    """Belezi da je ime prijavljeno i vraca rezultat, ili None ako rezultata nema na rang listi.

    Ne pamti se ko prijavljuje, pa je prijava jedna po rezultatu: ponovljena ne menja nista, a
    rezultat koji je moderator vec pregledao i zadrzao ne dolazi ponovo na pregled.
    """
    with transaction.atomic():
        # U istoj transakciji kao i brisanje moderatora, pa se ne prijavljuje rezultat kojeg vise nema.
        rezultat = nadji_za_prijavu(pk)
        if rezultat is not None:
            PrijavaImena.objects.get_or_create(rezultat=rezultat)
    return rezultat


def kontekst_prijave_imena(rezultat):
    """Stranica prijave prikazuje samo ono sto je vec na rang listi, i dokle je prijava stigla."""
    prijava = PrijavaImena.objects.filter(rezultat=rezultat).first()
    if prijava is None:
        stanje = "slobodno"
    elif prijava.resena:
        stanje = "pregledano"
    else:
        stanje = "prijavljeno"
    return {
        "pk": rezultat.pk,
        "ime": rezultat.ime,
        "poeni": rezultat.poeni,
        "ocena": _(rezultat.ocena),
        # Deo pocetnog ekrana na koji se igrac vraca.
        "lista": "dnevna-lista" if rezultat.partija.dan else "rang-lista",
        "stanje": stanje,
    }


def format_dana(dan):
    if translation.get_language() == "en":
        return dateformat.format(dan, "M j, Y")
    return dan.strftime("%d.%m.%Y.")


def format_vremena(trenutak):
    """Datum i vreme, po vremenu Europe/Belgrade."""
    lokalno = timezone.localtime(trenutak)
    if translation.get_language() == "en":
        return dateformat.format(lokalno, "M j, Y, H:i")
    return dateformat.format(lokalno, "d.m.Y. H:i")


def moje_partije(igrac):
    """Poslednje zavrsene partije igraca (hes_igraca), najnovija prva. Partija u toku se ne prikazuje."""
    if not igrac:
        return []
    partije = (
        Partija.objects.filter(igrac=igrac, zavrsena__isnull=False)
        .select_related("rezultat")
        .order_by("-zavrsena", "-pk")[: p.BROJ_U_ISTORIJI]
    )
    redovi = []
    for partija in partije:
        # Partija bez sacuvanog rezultata baca RelatedObjectDoesNotExist, sto je AttributeError.
        rezultat = getattr(partija, "rezultat", None)
        redovi.append(
            {
                "vreme": format_vremena(partija.zavrsena),
                "poeni": partija.poeni,
                "ocena": _(pravila.ocena_za_poene(partija.poeni)),
                "dnevna": partija.dan is not None,
                "ime": rezultat.ime if rezultat else None,
                # None kada je moderator obrisao link; tada red nije link.
                "kod": _kod_za_istoriju(partija),
            }
        )
    return redovi


def _kod_za_istoriju(partija):
    """Postojeci kod, ili nov za partiju ciji zavrsni ekran igrac nije otvorio."""
    if partija.kod:
        return partija.kod
    try:
        return kod_deljenja(partija)
    except SukobStanja:
        return None  # Ne bi trebalo da se desi; pocetni ekran zbog jednog reda ne sme da padne.


def kontekst_pocetka(sesija, igrac=""):
    partija = nadji_partiju(sesija)
    istaknuta = partija.pk if partija else None
    dan = danas()
    return {
        "moje_partije": moje_partije(igrac),
        "broj_krugova": p.BROJ_KRUGOVA,
        "budzet": format_mnozioca(p.BUDZET),
        "rok": format_mnozioca(p.ROK),
        "rang_lista": rang_lista(istaknuta),
        "dnevni_dostupan": dnevni_izazov_dostupan(sesija),
        "dnevni_datum": format_dana(dan),
        "dnevna_lista": rang_lista(istaknuta, dan=dan),
        "kraj_dostupan": partija is not None
        and je_zavrsena(partija)
        and not Rezultat.objects.filter(partija=partija).exists()
        and not _uklonjeno(partija, Dogadjaj.OBRISAN_REZULTAT),
    }


def _uklonjeno(partija, vrsta):
    """Da li je moderator obrisao rezultat ili link ove partije (vidi moderacija.py)."""
    return Dogadjaj.objects.filter(partija=partija, vrsta=vrsta).exists()


def _udeo(preostalo, ukupno):
    """Procenat preostalog za merac na ekranu, ogranicen na 0..100."""
    return int(max(Decimal(0), min(Decimal(100), preostalo * 100 / ukupno)))


def kontekst_igre(partija):
    potezi = _ucitaj_poteze(partija)
    stanje = pravila.vidljivo_stanje(partija.seme, potezi)
    istorija = [_javni_red_istorije(ishod) for ishod in stanje.krugovi]
    krug = len(potezi) + 1
    return {
        "broj_krugova": p.BROJ_KRUGOVA,
        "krug": krug,
        "naziv": _(pravila.zadatak_kruga(krug).naziv),
        "segmenti": [
            {
                "odigran": i < len(istorija),
                "gotovo": i < len(istorija) and istorija[i]["gotovo"],
                "tekuci": i + 1 == krug,
            }
            for i in range(p.BROJ_KRUGOVA)
        ],
        "budzet": format_mnozioca(p.BUDZET),
        "rok": format_mnozioca(p.ROK),
        "budzet_udeo": _udeo(stanje.budzet_preostalo, p.BUDZET),
        "rok_udeo": _udeo(stanje.rok_preostalo, p.ROK),
        "opcije": javne_opcije(),
        "istorija": istorija,
        "poslednji": istorija[-1] if istorija else None,
        **_javno_stanje_budzeta(stanje),
    }


def kod_deljenja(partija):
    """Vraca kod javnog linka zavrsene partije i pravi ga pri prvom pozivu.

    Kod je nasumican i nezavisan od semena i broja partije, pa se iz njega nista ne moze izvesti.
    """
    if not je_zavrsena(partija):
        raise SukobStanja(_("Партија није завршена."))
    if partija.kod is None:
        with transaction.atomic():
            # Link koji je moderator obrisao se ne pravi ponovo. Provera je u istoj transakciji.
            if _uklonjeno(partija, Dogadjaj.OBRISAN_LINK):
                return None
            # Uslov kod__isnull cini upis jednokratnim i kada dva zahteva stignu istovremeno.
            Partija.objects.filter(pk=partija.pk, kod__isnull=True).update(kod=secrets.token_urlsafe(16))
        partija.refresh_from_db(fields=["kod"])
    return partija.kod


def nadji_podeljenu(kod):
    """Zavrsena partija sa datim kodom ili None. Partija u toku se nikad ne prikazuje."""
    partija = Partija.objects.filter(kod=kod).first() if kod else None
    if partija is None or not je_zavrsena(partija):
        return None
    return partija


def kontekst_podeljenog(partija):
    """Samo rezultat partije, bez ikakve veze sa sesijom onoga ko gleda."""
    return {
        **_kontekst_rezultata(partija),
        "ime_igraca": Rezultat.objects.filter(partija=partija).values_list("ime", flat=True).first(),
    }


def _kontekst_rezultata(partija):
    rezultat = _konacni_rezultat(partija)
    ocene = [ocena for _, ocena in p.OCENE]
    return {
        "poeni": rezultat.poeni,
        "ocena": _(rezultat.ocena),
        # Najbolja ocena ima 3 zvezdice, najlosija nijednu.
        "zvezdice": len(ocene) - 1 - ocene.index(rezultat.ocena),
        "cena_prekoracena": rezultat.ukupna_cena > p.BUDZET,
        "minuti_prekoraceni": rezultat.ukupni_minuti > p.ROK,
        "ukupna_cena": format_cene(rezultat.ukupna_cena),
        "ukupni_minuti": format_minuta(rezultat.ukupni_minuti),
        "budzet": format_mnozioca(p.BUDZET),
        "rok": format_mnozioca(p.ROK),
        "tihe_greske": [_javni_zadatak(z.krug) for z in rezultat.tihe_greske],
        "lekcije": [{"tekst": _(l.tekst), "odeljak": l.odeljak} for l in rezultat.lekcije],
        "napomena": _(p.NAPOMENA_O_PARAMETRIMA),
    }


def kontekst_kraja(partija):
    return {
        **_kontekst_rezultata(partija),
        "sacuvano_ime": Rezultat.objects.filter(partija=partija).values_list("ime", flat=True).first(),
        "duzina_imena": p.DUZINA_IMENA_MAX,
        # None kada je moderator obrisao link; tada se umesto linka prikazuje poruka.
        "kod": kod_deljenja(partija),
        "rezultat_uklonjen": _uklonjeno(partija, Dogadjaj.OBRISAN_REZULTAT),
    }


def _granice_ocena():
    """Raspon poena za svaku ocenu, od najbolje: 85–100, 65–84, 40–64, 0–39."""
    raspon, gornja = [], p.POCETNI_POENI
    for granica, ocena in p.OCENE:
        raspon.append({"od": granica, "do": gornja, "ocena": _(ocena)})
        gornja = granica - 1
    return raspon


def kontekst_pravila():
    """Stranica „Kako se igra“: pravila iz parametara i jedan izmisljen krug kao primer.

    Prikazuje samo ono sto igrac vidi i u igri (mnozioce opcija, cenu i minute posle poteza) i
    kazne iz tekuceg bodovanja. Sansa, bonusi, tezina i oznaka tihog zadatka ostaju na serveru.
    """
    bodovanje = p.BODOVANJA[p.BODOVANJE_TEKUCE]
    izbori = Izbori(*p.PRIMER_IZBORI)
    racun = pravila.racun_za_tezinu(p.PRIMER_TEZINA, izbori)
    cena_dorade, minuti_dorade = racun.cena * p.DORADA_PUTA, racun.minuti * p.DORADA_PUTA
    korak = bodovanje.korak_budzeta_procenata
    return {
        "broj_krugova": p.BROJ_KRUGOVA,
        "budzet": format_mnozioca(p.BUDZET),
        "rok": format_mnozioca(p.ROK),
        "opcije": javne_opcije(),
        "pocetni_poeni": p.POCETNI_POENI,
        "najmanje_poena": p.MIN_POENI,
        "dorada_puta": p.DORADA_PUTA,
        "dorada_poeni": p.DORADA_POENI,
        "tihi_cena_puta": p.TIHI_DODATAK_CENE_PUTA,
        "tihi_minuti_puta": p.TIHI_DODATAK_MINUTA_PUTA,
        "tihi_poeni": bodovanje.tihi_poeni,
        "kazna_budzet": bodovanje.kazna_budzet,
        "korak_budzeta": korak,
        "korak_budzeta_iznos": _sa_zarezom(f"{p.BUDZET * korak / 100:.2f}") if korak else None,
        "kazna_budzet_max": bodovanje.kazna_budzet_max,
        "kazna_rok": p.KAZNA_ROK,
        "ocene": _granice_ocena(),
        "broj_u_istoriji": p.BROJ_U_ISTORIJI,
        "napomena": _(p.NAPOMENA_O_PARAMETRIMA),
        "status_gotovo": _(p.STATUS_GOTOVO),
        "status_dorada": _(p.STATUS_DORADA),
        "primer": {
            "zadatak": _(p.PRIMER_ZADATAK),
            "izbori": [
                _(p.MODELI[izbori.model].naziv),
                _(p.NIVOI[izbori.nivo].naziv),
                _(p.KONTEKSTI[izbori.kontekst].naziv),
                _(p.PODELE[izbori.podela].naziv),
            ],
            "cena": format_cene(racun.cena),
            "minuti": format_minuta(racun.minuti),
            "budzet_posle": format_cene(p.BUDZET - racun.cena),
            "rok_posle": format_minuta(p.ROK - racun.minuti),
            "cena_dorade": format_cene(cena_dorade),
            "minuti_dorade": format_minuta(minuti_dorade),
            "budzet_posle_dorade": format_cene(p.BUDZET - cena_dorade),
            "rok_posle_dorade": format_minuta(p.ROK - minuti_dorade),
        },
    }
