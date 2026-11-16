"""Brisanje starih zapisa dnevnika moderatora (plan 14.4, odluka M4: 365 dana). Trajno."""

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from igra.models import ZapisDnevnika

SEKUNDI_DANA = 24 * 60 * 60


class Command(BaseCommand):
    help = (
        "Brise zapise dnevnika moderatora starije od N dana (podrazumevano DNEVNIK_DANA) i ispisuje broj. "
        "N mora biti duze od trajanja sesije igre (SESSION_COOKIE_AGE)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dana", type=int, default=settings.DNEVNIK_DANA, metavar="N")

    def handle(self, *args, dana, **options):
        # Zapis cuva hes partije da se obrisan rezultat ili link ne vrati; dok sesija zavrsene partije moze da
        # postoji, zapis mora da ostane (plan 14.4).
        if dana * SEKUNDI_DANA <= settings.SESSION_COOKIE_AGE:
            raise CommandError(
                f"--dana mora biti vece od trajanja sesije igre ({settings.SESSION_COOKIE_AGE // SEKUNDI_DANA} "
                "dana), inace obrisana partija moze ponovo da se sacuva ili podeli. Nista nije obrisano."
            )
        granica = timezone.now() - timedelta(days=dana)
        with transaction.atomic():
            # Model nema delete() ni signale, a okidac 0010 vazi samo za UPDATE (stack-django pravilo 2).
            broj, _ = ZapisDnevnika.objects.filter(kada__lt=granica).delete()
        self.stdout.write(f"obrisano zapisa: {broj}")
