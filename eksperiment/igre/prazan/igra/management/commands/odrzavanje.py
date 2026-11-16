"""Dnevno odrzavanje baze: python manage.py odrzavanje

Na serveru ga jednom dnevno pokrece systemd tajmer (deploy/systemd/orkestrator-odrzavanje.timer).
- brise istekle sesije;
- brise napustene partije: nezavrsene, starije od trajanja sesije. Takvu partiju niko vise ne moze
  da nastavi, jer je kolacic sesije koji je na nju pokazivao istekao (sesija se ne produzava potezima).

Zavrsene partije se nikad ne brisu: na njima stoje podeljeni linkovi, rang lista i dnevnik moderacije.
"""

from datetime import timedelta

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from igra import parametri as p
from igra.models import Partija

# Brise se u manjim delovima, da upis u bazu ne zadrzava igrace koji upravo igraju.
DEO = 2000
# Dan rezerve preko trajanja sesije, za igraca koji je igru zapoceo pred istek kolacica.
REZERVA = timedelta(days=1)


def napustene_partije(sada=None):
    granica = (sada or timezone.now()) - timedelta(seconds=settings.SESSION_COOKIE_AGE) - REZERVA
    return (
        Partija.objects.filter(napravljena__lt=granica, kod__isnull=True, rezultat__isnull=True)
        .exclude(dogadjaji__isnull=False)
        .annotate(broj_poteza=Count("potezi"))
        .filter(broj_poteza__lt=p.BROJ_KRUGOVA)
    )


def obrisi_napustene(sada=None):
    ukupno = 0
    while True:
        with transaction.atomic():
            kljucevi = list(napustene_partije(sada).values_list("pk", flat=True)[:DEO])
            if not kljucevi:
                return ukupno
            Partija.objects.filter(pk__in=kljucevi).delete()
        ukupno += len(kljucevi)


class Command(BaseCommand):
    help = "Brise istekle sesije i napustene nezavrsene partije."

    def handle(self, *args, **options):
        call_command("clearsessions")
        obrisano = obrisi_napustene()
        self.stdout.write(f"Obrisano napustenih partija: {obrisano}.")
