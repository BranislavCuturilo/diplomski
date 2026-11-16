"""Razvijalac pravi moderatora: python manage.py moderator <ime>

Lozinka se unosi dva puta i ne prikazuje se. Ostale moderatore moze da doda i moderator na sajtu.
"""

import getpass

from django.core.management.base import BaseCommand, CommandError
from django.utils import translation

from igra import moderacija
from igra.servis import NeispravanZahtev


class Command(BaseCommand):
    help = "Pravi nalog moderatora (prvog moderatora pravi razvijalac)."

    def add_arguments(self, parser):
        parser.add_argument("ime", help="Ime naloga moderatora.")

    def handle(self, *args, ime, **options):
        lozinka = getpass.getpass("Lozinka: ")
        ponovo = getpass.getpass("Lozinka ponovo: ")
        # Poruke o greskama na engleskom, jer se konzola ne bira kroz kolacic.
        with translation.override("en"):
            try:
                nalog = moderacija.dodaj_moderatora(None, ime, lozinka, ponovo)
            except NeispravanZahtev as greska:
                raise CommandError("\n".join(str(g) for g in greska.args[0])) from None
        self.stdout.write(self.style.SUCCESS(f"Moderator '{nalog.username}' je napravljen."))
