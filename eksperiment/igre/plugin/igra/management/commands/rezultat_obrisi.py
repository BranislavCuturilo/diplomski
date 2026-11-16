"""Brisanje sacuvanih rezultata po id-u (plan 10.4, 14.4). Trajno; pokrece ga razvijalac po nalogu korisnika.

Brise kroz servis brisanje.py, pa svaki red ide u dnevnik moderatora kao "razvijalac (komanda)".
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from igra import brisanje
from igra.models import Rezultat

from .rezultati import opis_reda


class Command(BaseCommand):
    help = (
        "Brise sacuvane rezultate po id-u (id ispisuje komanda rezultati) i upisuje ih u dnevnik. Ako ijedan "
        "id ne postoji, nista se ne brise. Partija obrisanog reda se ne moze ponovo sacuvati."
    )

    def add_arguments(self, parser):
        parser.add_argument("ids", nargs="+", type=int, metavar="ID")

    def handle(self, *args, ids, **options):
        # Spoljna transakcija: redovi za ispis i brisanje pod istom bravom.
        with transaction.atomic():
            redovi = list(Rezultat.objects.filter(id__in=ids).order_by("id"))
            try:
                brisanje.obrisi_rezultate(ids, ko=None)
            except brisanje.NemaReda as greska:
                spisak = ", ".join(str(broj) for broj in greska.ids)
                raise CommandError(f"Nema rezultata sa id: {spisak}. Nista nije obrisano.") from greska
        for rezultat in redovi:
            self.stdout.write(f"obrisano: {opis_reda(rezultat)}")
