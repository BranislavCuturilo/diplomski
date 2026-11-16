"""Brisanje rezultata i deljenih linkova (plan 14.4): jedini put brisanja, i za prikaze i za komande.

Tvrdo brisanje. U istoj transakciji dnevnik dobija po zapis za svaki red: snimak {ime, poeni, ocena, datum} i
partiju (sha256 semena), da se obrisana partija ne sacuva ni ne podeli ponovo i kada se brojac id-a vrati.
Token linka se ne cuva, ni kao hes: to je tajna pristupa, a dnevnik citaju svi moderatori.
`ko=None` je komanda razvijaca.

Ovde je i druga odluka moderatora o prijavljenom imenu (odluka 2026-11-12): ime ostaje, prijave se brisu
(odbaci_prijave). Brisanje rezultata odnosi njegove prijave sa sobom (PrijavaImena.rezultat je CASCADE).
"""

from django.db import transaction

from . import nalozi
from .models import (
    LINK_OBRISAN,
    PRIJAVA_ODBACENA,
    REZULTAT_OBRISAN,
    DeljeniRezultat,
    PrijavaImena,
    Rezultat,
    ZapisDnevnika,
)


class NemaReda(Exception):
    """Bar jedan id ne postoji; nista nije obrisano."""

    def __init__(self, ids):
        self.ids = sorted(ids)
        super().__init__(", ".join(str(broj) for broj in self.ids))


class NemaPrijava(Exception):
    """Bar jedan rezultat nema nijednu prijavu imena (vec je reseno); nista nije upisano ni obrisano."""


def _redovi(queryset, ids):
    redovi = list(queryset.filter(id__in=ids).order_by("id"))
    nema = set(ids) - {red.id for red in redovi}
    if nema:
        raise NemaReda(nema)
    return redovi


def _snimak(ime, poeni, ocena, trenutak, dan=None):
    # Bela lista: tacno ova cetiri kljuca, i "dan" (ISO) samo za red dnevnog izazova. ocena je kljuc
    # (parametri.OCENE), datum ISO 8601 u UTC.
    snimak = {"ime": ime, "poeni": poeni, "ocena": ocena, "datum": trenutak.isoformat()}
    if dan is not None:
        snimak["dan"] = dan.isoformat()
    return snimak


def obrisi_rezultate(ids, ko=None):
    """Brise rezultate sa rang liste; vraca zapise dnevnika. NemaReda ako ijedan id ne postoji."""
    with transaction.atomic():
        if ko is not None:
            ko = nalozi.proveri_ulogu(ko, nalozi.MODERATOR)
        redovi = _redovi(Rezultat.objects, ids)
        zapisi = [
            ZapisDnevnika.objects.upisi(
                radnja=REZULTAT_OBRISAN,
                ko=ko,
                red=red.id,
                partija=red.partija,
                snimak=_snimak(red.ime, red.poeni, red.ocena, red.sacuvan, red.dan),
            )
            for red in redovi
        ]
        # Model nema delete() ni signale, pa QuerySet.delete() nista ne preskace (stack-django pravilo 2).
        # Prijave imena ovih redova odlaze sa njima (PrijavaImena.rezultat je CASCADE).
        Rezultat.objects.filter(id__in=[red.id for red in redovi]).delete()
    return zapisi


def obrisi_deljene(ids, ko=None):
    """Brise deljene linkove (i istekle); link odmah daje isti 404 kao istekao. NemaReda ako ijedan id ne postoji."""
    with transaction.atomic():
        if ko is not None:
            ko = nalozi.proveri_ulogu(ko, nalozi.MODERATOR)
        redovi = _redovi(DeljeniRezultat.objects, ids)
        # Ime sa rang liste u trenutku brisanja, ili None ako partija nije sacuvana.
        imena = Rezultat.objects.imena_po_partiji([red.partija for red in redovi])
        zapisi = [
            ZapisDnevnika.objects.upisi(
                radnja=LINK_OBRISAN,
                ko=ko,
                red=red.id,
                partija=red.partija,
                snimak=_snimak(imena.get(red.partija), red.zavrsni["poeni"], red.zavrsni["ocena"], red.nastao),
            )
            for red in redovi
        ]
        # Model nema delete() ni signale, pa QuerySet.delete() nista ne preskace (stack-django pravilo 2).
        DeljeniRezultat.objects.filter(id__in=[red.id for red in redovi]).delete()
    return zapisi


def odbaci_prijave(ids, ko):
    """Moderator ostavlja prijavljeno ime: brise prijave tih rezultata i upisuje odluku u dnevnik; vraca zapise.

    Rezultat ostaje na listi. Zapis nosi partiju, pa se kasnije prijave istog rezultata vise ne beleze
    (views.prijavi cita ZapisDnevnika.objects.prijava_odbacena). NemaReda ako ijedan id ne postoji, NemaPrijava
    ako ijedan rezultat nema prijavu; u oba slucaja nista nije upisano. Samo moderator: komande za ovo nema.
    """
    with transaction.atomic():
        ko = nalozi.proveri_ulogu(ko, nalozi.MODERATOR)
        redovi = _redovi(Rezultat.objects, ids)
        prijave = PrijavaImena.objects.filter(rezultat__in=redovi)
        prijavljeni = set(prijave.values_list("rezultat_id", flat=True))
        if any(red.id not in prijavljeni for red in redovi):
            raise NemaPrijava()
        zapisi = [
            ZapisDnevnika.objects.upisi(
                radnja=PRIJAVA_ODBACENA,
                ko=ko,
                red=red.id,
                partija=red.partija,
                snimak=_snimak(red.ime, red.poeni, red.ocena, red.sacuvan, red.dan),
            )
            for red in redovi
        ]
        # Model nema delete() ni signale, pa QuerySet.delete() nista ne preskace (stack-django pravilo 2).
        prijave.delete()
    return zapisi
