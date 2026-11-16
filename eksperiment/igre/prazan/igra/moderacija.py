"""Moderacija: brisanje rezultata i linkova, prijavljena imena, nalozi moderatora i dnevnik.

Igraci nemaju naloge. Moderator je korisnik sa dozvolom igra.moderira; prvog pravi razvijalac
komandom `python manage.py moderator <ime>`, a ostale dodaje moderator na sajtu.
Svaka radnja se upisuje u Dogadjaj u istoj transakciji u kojoj se izvrsava.
"""

import csv
import io
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone, translation
from django.utils.translation import gettext as _
from django.utils.translation import gettext_noop as N_

from igra import parametri as p
from igra.models import Dogadjaj, Partija, PrijavaImena, Rezultat
from igra.servis import NeispravanZahtev, danas, format_dana, format_datuma, format_vremena

DOZVOLA = "igra.moderira"
NA_STRANI = 25
DUZINA_NALOGA_MAX = 30

# Posle 5 promasenih prijava za isto ime, prijava je zakljucana 15 minuta.
PRIJAVA_POKUSAJA = 5
PRIJAVA_ZAKLJUCANO_SEKUNDI = 15 * 60

RADNJE = {
    Dogadjaj.OBRISAN_REZULTAT: N_("обрисао резултат"),
    Dogadjaj.OBRISAN_LINK: N_("обрисао линк"),
    Dogadjaj.ZADRZAN_REZULTAT: N_("задржао пријављени резултат"),
    Dogadjaj.DODAT_MODERATOR: N_("додао модератора"),
    Dogadjaj.ISKLJUCEN_MODERATOR: N_("искључио модератора"),
    Dogadjaj.UKLJUCEN_MODERATOR: N_("укључио модератора"),
}


class NijePronadjeno(Exception):
    """Odgovara kodu 404: nema sta da se obrise ili je vec obrisano."""


def je_moderator(korisnik):
    # has_perm vraca False za iskljucen nalog, pa iskljucen moderator gubi pristup odmah,
    # i u sesiji koja je vec otvorena.
    return korisnik.is_authenticated and korisnik.is_active and korisnik.has_perm(DOZVOLA)


# Prijava


def _kljuc_prijave(ime):
    return "prijava:" + (ime or "").strip().casefold()


def prijava_zakljucana(ime):
    return cache.get(_kljuc_prijave(ime), 0) >= PRIJAVA_POKUSAJA


def zabelezi_promasaj(ime):
    kljuc = _kljuc_prijave(ime)
    if not cache.add(kljuc, 1, PRIJAVA_ZAKLJUCANO_SEKUNDI):
        try:
            cache.incr(kljuc)
        except ValueError:
            cache.set(kljuc, 1, PRIJAVA_ZAKLJUCANO_SEKUNDI)


def ponisti_promasaje(ime):
    cache.delete(_kljuc_prijave(ime))


# Brisanje (servis.py proverava dnevnik, pa obrisano ne moze ponovo da nastane)


def rezultat_za_brisanje(pk):
    rezultat = Rezultat.objects.filter(pk=pk).first()
    if rezultat is None:
        raise NijePronadjeno
    return rezultat


def partija_za_brisanje_linka(kod):
    partija = Partija.objects.filter(kod=kod).first() if kod else None
    if partija is None:
        raise NijePronadjeno
    return partija


def obrisi_rezultat(moderator, pk):
    """Brise rezultat sa rang liste. Konacno: ista partija ne moze ponovo da se sacuva."""
    with transaction.atomic():
        rezultat = rezultat_za_brisanje(pk)
        dogadjaj = Dogadjaj.objects.create(
            moderator=moderator,
            vrsta=Dogadjaj.OBRISAN_REZULTAT,
            partija_id=rezultat.partija_id,
            ime_igraca=rezultat.ime,
            poeni=rezultat.poeni,
        )
        rezultat.delete()
    return dogadjaj


def obrisi_link(moderator, kod):
    """Gasi deljeni link. Konacno: zavrsni ekran te partije ne pravi novi link."""
    with transaction.atomic():
        partija = partija_za_brisanje_linka(kod)
        dogadjaj = Dogadjaj.objects.create(
            moderator=moderator,
            vrsta=Dogadjaj.OBRISAN_LINK,
            partija=partija,
            ime_igraca=Rezultat.objects.filter(partija=partija).values_list("ime", flat=True).first() or "",
            kod=partija.kod,
        )
        Partija.objects.filter(pk=partija.pk).update(kod=None)
    return dogadjaj


# Prijavljena imena (igrac prijavljuje kroz servis.py; ovde moderator odlucuje)


def otvorene_prijave():
    """Prijave o kojima moderator jos nije odlucio; najstarija je prva."""
    return PrijavaImena.objects.filter(resena=False).select_related("rezultat")


def zadrzi_rezultat(moderator, pk):
    """Moderator je pregledao prijavljeno ime i rezultat ostaje. Konacno: vise se ne moze prijaviti.

    Druga odluka je obrisi_rezultat: prijava tada nestaje zajedno sa rezultatom.
    """
    with transaction.atomic():
        prijava = otvorene_prijave().filter(rezultat_id=pk).first()
        if prijava is None:
            raise NijePronadjeno
        dogadjaj = Dogadjaj.objects.create(
            moderator=moderator,
            vrsta=Dogadjaj.ZADRZAN_REZULTAT,
            partija_id=prijava.rezultat.partija_id,
            ime_igraca=prijava.rezultat.ime,
            poeni=prijava.rezultat.poeni,
        )
        prijava.resena = True
        prijava.save(update_fields=["resena"])
    return dogadjaj


# Nalozi moderatora


def _dozvola():
    return Permission.objects.get(content_type__app_label="igra", codename="moderira")


def moderatori():
    Korisnik = get_user_model()
    return (
        Korisnik.objects.filter(Q(user_permissions=_dozvola()) | Q(is_superuser=True))
        .distinct()
        .order_by("username")
    )


def proveri_novi_nalog(ime, lozinka, ponovo):
    """Vraca ocisceno ime ili baca NeispravanZahtev sa svim greskama, jednom po redu."""
    Korisnik = get_user_model()
    ime = (ime or "").strip()
    greske = []
    if not ime:
        greske.append(_("Име налога је обавезно."))
    elif len(ime) > DUZINA_NALOGA_MAX:
        greske.append(_("Име налога може имати највише %(broj)s знакова.") % {"broj": DUZINA_NALOGA_MAX})
    else:
        try:
            Korisnik.username_validator(ime)
        except ValidationError:
            greske.append(_("Име налога сме да има само слова, цифре и знакове @ . + - _."))
        else:
            if Korisnik.objects.filter(username__iexact=ime).exists():
                greske.append(_("Налог са тим именом већ постоји."))
    if not lozinka:
        greske.append(_("Лозинка је обавезна."))
    elif lozinka != ponovo:
        greske.append(_("Лозинке се не поклапају."))
    else:
        try:
            password_validation.validate_password(lozinka, Korisnik(username=ime))
        except ValidationError as greska:
            greske.extend(greska.messages)
    if greske:
        raise NeispravanZahtev(greske)
    return ime


def dodaj_moderatora(ko, ime, lozinka, ponovo):
    """ko je moderator koji dodaje, ili None kada nalog pravi razvijalac komandom."""
    ime = proveri_novi_nalog(ime, lozinka, ponovo)
    with transaction.atomic():
        nalog = get_user_model().objects.create_user(username=ime, password=lozinka)
        nalog.user_permissions.add(_dozvola())
        Dogadjaj.objects.create(moderator=ko, vrsta=Dogadjaj.DODAT_MODERATOR, nalog=ime)
    return nalog


def promeni_aktivnost(ko, pk, aktivan):
    nalog = moderatori().filter(pk=pk).first()
    if nalog is None:
        raise NijePronadjeno
    if nalog.pk == ko.pk:
        raise NeispravanZahtev([_("Не можеш да искључиш сопствени налог.")])
    if nalog.is_active == aktivan:
        return None
    with transaction.atomic():
        nalog.is_active = aktivan
        nalog.save(update_fields=["is_active"])
        vrsta = Dogadjaj.UKLJUCEN_MODERATOR if aktivan else Dogadjaj.ISKLJUCEN_MODERATOR
        return Dogadjaj.objects.create(moderator=ko, vrsta=vrsta, nalog=nalog.username)


# Prikaz


def strana(upit, broj):
    return Paginator(upit, NA_STRANI).get_page(broj)


def red_rezultata(rezultat):
    return {
        "pk": rezultat.pk,
        "mesto": Rezultat.objects.filter(poeni__gt=rezultat.poeni).count() + 1,
        "ime": rezultat.ime,
        "poeni": rezultat.poeni,
        "ocena": _(rezultat.ocena),
        "datum": format_datuma(rezultat.sacuvan),
        "kod": rezultat.partija.kod,
    }


def red_prijave(prijava):
    # Bez mesta: spisak prijava ide po vremenu prijave, ne po poenima.
    rezultat = prijava.rezultat
    return {
        "pk": rezultat.pk,
        "ime": rezultat.ime,
        "poeni": rezultat.poeni,
        "ocena": _(rezultat.ocena),
        "datum": format_datuma(rezultat.sacuvan),
        "prijavljeno": format_vremena(prijava.podneta),
    }


def red_linka(partija):
    # Partija bez sacuvanog rezultata baca RelatedObjectDoesNotExist, sto je AttributeError.
    rezultat = getattr(partija, "rezultat", None)
    return {
        "kod": partija.kod,
        "datum": format_datuma(partija.napravljena),
        "ime": rezultat.ime if rezultat else None,
        "poeni": rezultat.poeni if rezultat else None,
    }


def red_dnevnika(dogadjaj):
    return {
        "vreme": format_vremena(dogadjaj.vreme),
        "moderator": dogadjaj.moderator.username if dogadjaj.moderator else None,
        "vrsta": dogadjaj.vrsta,
        "radnja": _(RADNJE.get(dogadjaj.vrsta, dogadjaj.vrsta)),
        "ime_igraca": dogadjaj.ime_igraca,
        "poeni": dogadjaj.poeni,
        "kod": dogadjaj.kod,
        "nalog": dogadjaj.nalog,
    }


# Izvoz rang liste u CSV (za Excel)

# Excel u srpskim podesavanjima ocekuje tacku-zarez; BOM mu kaze da je datoteka UTF-8 (cirilica).
CSV_ODVAJAC = ";"
CSV_BOM = "﻿"
# Excel izvrsava celiju koja pocinje ovim znakom kao formulu; ime igraca je slobodan tekst.
OPASNI_POCECI = ("=", "+", "-", "@", "\t", "\r")


def _bezbedna_celija(tekst):
    tekst = str(tekst)
    return "'" + tekst if tekst.startswith(OPASNI_POCECI) else tekst


def procitaj_dan(tekst):
    """Dan iz adrese (GGGG-MM-DD); prazno znaci danas. Pogresan unos baca NeispravanZahtev."""
    if not tekst:
        return danas()
    try:
        return date.fromisoformat(tekst)
    except ValueError:
        raise NeispravanZahtev([_("Дан мора бити у облику ГГГГ-ММ-ДД.")]) from None


def redovi_za_izvoz(dan=None):
    """Cela rang lista (ne samo prvih N): bez dana obicne partije, sa danom dnevni izazov tog dana.

    Isti poeni dele mesto (1, 2, 2, 4), kao na javnoj listi.
    """
    if dan:
        upit = Rezultat.objects.filter(partija__dan=dan)
    else:
        upit = Rezultat.objects.filter(partija__dan__isnull=True)
    mesto, prethodni = 0, None
    for redni_broj, rezultat in enumerate(upit.iterator(), start=1):
        if rezultat.poeni != prethodni:
            mesto, prethodni = redni_broj, rezultat.poeni
        yield [
            mesto,
            _bezbedna_celija(rezultat.ime),
            rezultat.poeni,
            _bezbedna_celija(_(rezultat.ocena)),
            timezone.localtime(rezultat.sacuvan).strftime("%Y-%m-%d %H:%M"),
        ]


def csv_rang_liste(dan=None):
    izlaz = io.StringIO()
    izlaz.write(CSV_BOM)
    pisac = csv.writer(izlaz, delimiter=CSV_ODVAJAC, lineterminator="\r\n")
    pisac.writerow([_("Место"), _("Име"), _("Поени"), _("Оцена"), _("Сачувано")])
    pisac.writerows(redovi_za_izvoz(dan))
    return izlaz.getvalue()


# Statistika: zavrsene partije i prosecni poeni po danu


def statistika(dana=None, do_dana=None):
    """Zavrsene partije (obicne i dnevni izazov) po danu zavrsetka, za poslednjih `dana` dana.

    Dan je po vremenu Europe/Belgrade, a najnoviji je prvi. Dan bez partija ima broj 0 i prosek None.
    Napustene (nezavrsene) partije se ne broje, jer nemaju poene.
    """
    dana = dana or p.DANA_STATISTIKE
    poslednji = do_dana or danas()
    prvi = poslednji - timedelta(days=dana - 1)
    zona = timezone.get_current_timezone()
    od = datetime.combine(prvi, time.min, tzinfo=zona)
    do = datetime.combine(poslednji + timedelta(days=1), time.min, tzinfo=zona)
    po_danu = {
        red["dan_zavrsetka"]: red
        for red in Partija.objects.filter(zavrsena__gte=od, zavrsena__lt=do)
        .annotate(dan_zavrsetka=TruncDate("zavrsena", tzinfo=zona))
        .values("dan_zavrsetka")
        .annotate(broj=Count("pk"), zbir=Sum("poeni"))
        .order_by()
    }
    redovi = []
    for pomak in range(dana):
        dan = poslednji - timedelta(days=pomak)
        red = po_danu.get(dan, {"broj": 0, "zbir": 0})
        redovi.append({"dan": dan, "broj": red["broj"], "zbir": red["zbir"] or 0})
    ukupno = {"broj": sum(r["broj"] for r in redovi), "zbir": sum(r["zbir"] for r in redovi)}
    najvise = max((r["broj"] for r in redovi), default=0)
    return {
        "dani": [_red_statistike(r, najvise) for r in redovi],
        "ukupno": _red_statistike(ukupno, najvise),
        "broj_dana": dana,
    }


def _prosek(zbir, broj):
    """Prosek na jednu decimalu (pola nagore), sa zarezom na srpskom; None kada nema partija."""
    if not broj:
        return None
    vrednost = (Decimal(zbir) / broj).quantize(Decimal("0.1"), ROUND_HALF_UP)
    return f"{vrednost}" if translation.get_language() == "en" else f"{vrednost}".replace(".", ",")


def _red_statistike(red, najvise):
    return {
        "dan": format_dana(red["dan"]) if "dan" in red else None,
        "danas": red.get("dan") == danas(),
        "broj": red["broj"],
        "prosek": _prosek(red["zbir"], red["broj"]),
        # Sirina trake u tabeli, u procentima najveceg dana.
        "udeo": round(red["broj"] * 100 / najvise) if najvise else 0,
    }
