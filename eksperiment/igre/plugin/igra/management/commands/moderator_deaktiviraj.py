"""Deaktivacija moderatora (plan 14.5): nalog se ne brise (dnevnik pokazuje na njega), samo ne moze da se prijavi."""

from django.core.management.base import BaseCommand

from igra import nalozi

from .moderatori import brojevi, greska_odbijanja, nalog_po_imenu


class Command(BaseCommand):
    help = (
        "Deaktivira moderatora; njegove sesije od sledeceg zahteva su anonimne, a uloga glavnog se oduzima. "
        "Poslednji aktivni glavni se ne deaktivira. Ponovo: moderator_lozinka IME."
    )

    def add_arguments(self, parser):
        parser.add_argument("ime")

    def handle(self, *args, ime, **options):
        nad = nalog_po_imenu(ime)
        try:
            nalozi.deaktiviraj(None, nad)
        except nalozi.Odbijeno as greska:
            raise greska_odbijanja(greska) from greska
        self.stdout.write(f"Deaktiviran: {nad.get_username()!r}. {brojevi()}")
