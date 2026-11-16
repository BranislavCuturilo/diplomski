"""Nova pocetna lozinka moderatora (plan 14.5); neaktivan nalog se pri tom aktivira (otkljucavanje).

Kada niko nema pristup: moderator_lozinka IME, pa po potrebi moderator_glavni IME.
"""

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand

from igra import nalozi

from .moderatori import greska_odbijanja, greska_validacije, nalog_po_imenu, unesi_lozinku


class Command(BaseCommand):
    help = (
        "Postavlja novu lozinku moderatora (unosi se dvaput); vlasnik je menja pri prvoj prijavi, a njegove "
        "sesije se gase. Neaktivan nalog se aktivira kao obican moderator."
    )

    def add_arguments(self, parser):
        parser.add_argument("ime")

    def handle(self, *args, ime, **options):
        nad = nalog_po_imenu(ime)
        lozinka = unesi_lozinku()
        try:
            if nad.is_active:
                nalozi.postavi_lozinku(None, nad, lozinka)
                ishod = "Lozinka postavljena"
            else:
                nalozi.aktiviraj(None, nad, lozinka)
                ishod = "Lozinka postavljena i nalog aktiviran kao obican moderator"
        except ValidationError as greska:
            raise greska_validacije(greska) from greska
        except nalozi.Odbijeno as greska:
            raise greska_odbijanja(greska) from greska
        self.stdout.write(f"{ishod}: {nad.get_username()!r}; vlasnik je menja pri prvoj prijavi.")
