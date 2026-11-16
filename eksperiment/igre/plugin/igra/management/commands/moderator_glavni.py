"""Dodela ili oduzimanje uloge glavnog moderatora (plan 14.5). Uvek ostaje bar jedan aktivan glavni."""

from django.core.management.base import BaseCommand

from igra import nalozi

from .moderatori import brojevi, greska_odbijanja, nalog_po_imenu


class Command(BaseCommand):
    help = (
        "Dodeljuje aktivnom moderatoru ulogu glavnog; uz --oduzmi je oduzima. Poslednjem aktivnom glavnom "
        "uloga se ne oduzima."
    )

    def add_arguments(self, parser):
        parser.add_argument("ime")
        parser.add_argument("--oduzmi", action="store_true", help="oduzima ulogu glavnog")

    def handle(self, *args, ime, oduzmi, **options):
        nad = nalog_po_imenu(ime)
        try:
            if oduzmi:
                nalozi.oduzmi_ulogu(None, nad)
            else:
                nalozi.dodeli_ulogu(None, nad)
        except nalozi.Odbijeno as greska:
            raise greska_odbijanja(greska) from greska
        ishod = "Uloga glavnog oduzeta" if oduzmi else "Uloga glavnog dodeljena"
        self.stdout.write(f"{ishod}: {nad.get_username()!r}. {brojevi()}")
