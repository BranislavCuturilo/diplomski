"""Uklanjanje stavki iz sifarnika nepodobnih imena (plan 10.4)."""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from igra.imena import kljuc_imena
from igra.models import NepodobnoIme


class Command(BaseCommand):
    help = (
        "Uklanja stavke sifarnika po kljucu (rec se normalizuje kao ime). "
        "Ako ijedna ne postoji, nista se ne uklanja."
    )

    def add_arguments(self, parser):
        parser.add_argument("reci", nargs="+", metavar="REC")

    def handle(self, *args, reci, **options):
        parovi = [(rec, kljuc_imena(rec)) for rec in reci]
        with transaction.atomic():
            trazeni = {kljuc for _, kljuc in parovi}
            postojeci = set(
                NepodobnoIme.objects.filter(kljuc__in=trazeni).values_list("kljuc", flat=True)
            )
            nema = [f"{rec!r} -> {kljuc!r}" for rec, kljuc in parovi if kljuc not in postojeci]
            if nema:
                raise CommandError(f"Nema u sifarniku: {', '.join(nema)}. Nista nije uklonjeno.")
            NepodobnoIme.objects.filter(kljuc__in=postojeci).delete()
        for rec, kljuc in parovi:
            self.stdout.write(f"{rec!r} -> {kljuc}: uklonjeno")
