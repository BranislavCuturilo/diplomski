from django.core.management.base import BaseCommand, CommandError

from igra import prevodi


class Command(BaseCommand):
    help = "Dopunjuje engleski katalog (django.po) porukama iz koda i pravi django.mo."

    def add_arguments(self, parser):
        parser.add_argument(
            "--provera", action="store_true", help="Samo proveri katalog, bez izmena datoteka."
        )

    def handle(self, *args, provera=False, **opcije):
        poruke = prevodi.izvuci_poruke()
        po = prevodi.ucitaj_po()
        if not provera:
            prevodi.osvezi(po, poruke)
        nadjeno = prevodi.problemi(po, poruke)
        if not prevodi.mo_je_azuran(po):
            nadjeno.append("django.mo nije azuran: pokreni `python manage.py prevodi`")
        for problem in nadjeno:
            self.stderr.write(problem)
        if nadjeno:
            raise CommandError(f"Katalog nije potpun ({len(nadjeno)} problema).")
        self.stdout.write(f"Katalog je potpun: {len(poruke)} poruka.")
