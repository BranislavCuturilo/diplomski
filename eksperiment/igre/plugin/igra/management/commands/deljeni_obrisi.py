"""Brisanje deljenih rezultata po id-u (plan 11.8, 14.4). Trajno; pokrece ga razvijalac po nalogu korisnika.

Brise kroz servis brisanje.py, pa svaki red ide u dnevnik moderatora kao "razvijalac (komanda)".
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from igra import brisanje
from igra.models import DeljeniRezultat

from .deljeni import imena_sa_rang_liste, opis_deljenog


class Command(BaseCommand):
    help = (
        "Brise deljene rezultate po id-u (id ispisuje komanda deljeni) i upisuje ih u dnevnik; link odmah "
        "daje 404. Ako ijedan id ne postoji, nista se ne brise. Partija obrisanog reda novi link ne dobija."
    )

    def add_arguments(self, parser):
        parser.add_argument("ids", nargs="+", type=int, metavar="ID")

    def handle(self, *args, ids, **options):
        sada = timezone.now()
        # Spoljna transakcija: redovi i imena za ispis i brisanje pod istom bravom.
        with transaction.atomic():
            redovi = list(DeljeniRezultat.objects.filter(id__in=ids).order_by("id"))
            # Ime se cita pre brisanja, za ispis obrisanih.
            imena = imena_sa_rang_liste(redovi)
            try:
                brisanje.obrisi_deljene(ids, ko=None)
            except brisanje.NemaReda as greska:
                spisak = ", ".join(str(broj) for broj in greska.ids)
                raise CommandError(f"Nema deljenog rezultata sa id: {spisak}. Nista nije obrisano.") from greska
        for red in redovi:
            self.stdout.write(f"obrisano: {opis_deljenog(red, sada, imena)}")
