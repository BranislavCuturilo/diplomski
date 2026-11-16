"""Ispis deljenih rezultata (plan 11.8). Token se ne ispisuje: ispis zavrsava u terminalu i logovima."""

from django.core.management.base import BaseCommand
from django.utils import timezone

from igra.models import DeljeniRezultat, Rezultat

from .rezultati import FORMAT_TRENUTKA


def imena_sa_rang_liste(redovi):
    """partija -> ime, samo za partije koje su sacuvane na rang listi."""
    partije = [red.partija for red in redovi]
    return dict(Rezultat.objects.filter(partija__in=partije).values_list("partija", "ime"))


def opis_deljenog(red, sada, imena):
    """Red deljenog rezultata za ispis komandi; trenuci u TIME_ZONE, bez tokena i partije."""
    nastao = timezone.localtime(red.nastao).strftime(FORMAT_TRENUTKA)
    istice = timezone.localtime(red.istice).strftime(FORMAT_TRENUTKA)
    vazenje = "istekao" if red.istekao(sada) else "vazi"
    ime = imena.get(red.partija)
    return (
        f"id={red.id} nastao={nastao} istice={istice} {vazenje} "
        f"poeni={red.zavrsni['poeni']} ocena={red.zavrsni['ocena']!r} "
        f"ime={'-' if ime is None else repr(ime)}"
    )


class Command(BaseCommand):
    help = (
        "Ispisuje deljene rezultate: id, nastao, istice, vazi ili istekao, poeni, ocena, ime sa rang "
        "liste ili -. Token se ne ispisuje; --token nalazi red po prijavljenom linku."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--token",
            help="samo red sa ovim tokenom (deo linka posle /r/)",
        )

    def handle(self, *args, token, **options):
        redovi = DeljeniRezultat.objects.order_by("id")
        if token is not None:
            redovi = redovi.filter(token=token)
        redovi = list(redovi)
        if not redovi:
            if token is None:
                self.stdout.write("Nema deljenih rezultata.")
            else:
                self.stdout.write("Nema deljenog rezultata sa tim tokenom.")  # bez ponavljanja tokena
            return
        sada = timezone.now()
        imena = imena_sa_rang_liste(redovi)
        for red in redovi:
            self.stdout.write(opis_deljenog(red, sada, imena))
