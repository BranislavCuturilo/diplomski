"""Ispis sacuvanih rezultata redom rang liste (plan 10.4): glavna lista, ili lista jednog dana dnevnog izazova."""

from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from igra.models import Rezultat

# Razvijalcu treba i vreme: kod jednakih poena ranije sacuvan je iznad.
FORMAT_TRENUTKA = "%d.%m.%Y %H:%M:%S"


def opis_reda(rezultat):
    """Red rezultata za ispis komandi; trenutak u TIME_ZONE; dan dnevnog izazova ISO, None za glavnu listu."""
    trenutak = timezone.localtime(rezultat.sacuvan).strftime(FORMAT_TRENUTKA)
    dan = None if rezultat.dan is None else rezultat.dan.isoformat()
    return (
        f"id={rezultat.id} ime={rezultat.ime!r} poeni={rezultat.poeni} "
        f"ocena={rezultat.ocena!r} pravila={rezultat.pravila} datum={trenutak} dan={dan}"
    )


def _dan(vrednost):
    try:
        return date.fromisoformat(vrednost)
    except ValueError as greska:
        raise CommandError(f"--dan mora biti YYYY-MM-DD, ne {vrednost!r}") from greska


class Command(BaseCommand):
    help = (
        "Ispisuje sacuvane rezultate glavne liste redom rang liste: mesto, id, ime, poeni, ocena, "
        "verzija pravila bodovanja, datum. Sa --dan YYYY-MM-DD ispisuje listu tog dana dnevnog izazova."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dan", help="dan dnevnog izazova, YYYY-MM-DD (Europe/Belgrade)")

    def handle(self, *args, **options):
        if options["dan"] is None:
            redovi = list(Rezultat.objects.glavna().po_rangu())
        else:
            redovi = list(Rezultat.objects.dana(_dan(options["dan"])).po_rangu())
        if not redovi:
            self.stdout.write("Nema sacuvanih rezultata.")
            return
        for mesto, rezultat in enumerate(redovi, start=1):
            self.stdout.write(f"{mesto}. {opis_reda(rezultat)}")
