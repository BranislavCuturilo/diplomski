"""Dodavanje stavki u sifarnik nepodobnih imena (plan 10.4)."""

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from igra import brisanje
from igra.imena import kljuc_imena
from igra.models import NepodobnoIme, Rezultat

from .rezultati import opis_reda


class Command(BaseCommand):
    help = (
        "Dodaje stavke u sifarnik (rec se normalizuje kao ime) i ispisuje sacuvane rezultate "
        "sa tim imenom; brise ih samo uz --obrisi-rezultate."
    )

    def add_arguments(self, parser):
        parser.add_argument("reci", nargs="+", metavar="REC")
        parser.add_argument(
            "--obrisi-rezultate",
            action="store_true",
            help="brise pronadjene sacuvane rezultate u istoj transakciji (trajno)",
        )

    def handle(self, *args, reci, obrisi_rezultate, **options):
        parovi = [(rec, kljuc_imena(rec)) for rec in reci]
        prazni = [repr(rec) for rec, kljuc in parovi if not kljuc]
        if prazni:
            raise CommandError(f"Prazan kljuc za: {', '.join(prazni)}. Nista nije upisano.")

        trazeni = {kljuc for _, kljuc in parovi}
        with transaction.atomic():
            for rec, kljuc in parovi:
                if NepodobnoIme.objects.filter(kljuc=kljuc).exists():
                    self.stdout.write(f"{rec!r} -> {kljuc}: vec postoji")
                    continue
                stavka = NepodobnoIme(kljuc=kljuc)
                try:
                    stavka.full_clean()
                except ValidationError as greska:
                    # Izlazak iz atomic ponistava i ranije dodate stavke ovog poziva.
                    raise CommandError(
                        f"{rec!r} -> {kljuc}: {'; '.join(greska.messages)} Nista nije upisano."
                    ) from greska
                stavka.save()
                self.stdout.write(f"{rec!r} -> {kljuc}: dodato")

            # kljuc_imena je Python, pa poredjenje ide red po red; tabela je mala (plan 10.9).
            pogodjeni = [r for r in Rezultat.objects.order_by("id") if kljuc_imena(r.ime) in trazeni]
            if not pogodjeni:
                self.stdout.write("Nema sacuvanih rezultata sa tim imenom.")
                return
            self.stdout.write("Sacuvani rezultati sa tim imenom:")
            for rezultat in pogodjeni:
                self.stdout.write(f"  {opis_reda(rezultat)}")
            if obrisi_rezultate:
                # Kroz servis: svaki red ide u dnevnik moderatora, u istoj transakciji (plan 14.4).
                zapisi = brisanje.obrisi_rezultate([r.id for r in pogodjeni], ko=None)
                self.stdout.write(f"Obrisano rezultata: {len(zapisi)}")
            else:
                ids = " ".join(str(r.id) for r in pogodjeni)
                self.stdout.write(
                    "Nisu obrisani. Brisanje: python manage.py rezultat_obrisi "
                    f"{ids}, ili ponovite komandu sa --obrisi-rezultate."
                )
