"""Brisanje isteklih deljenih rezultata (plan 11.8); vazeci linkovi ostaju."""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from igra.models import DeljeniRezultat


class Command(BaseCommand):
    help = "Brise deljene rezultate kojima je istekao rok; vazeci linkovi ostaju. Bez argumenata."

    def handle(self, *args, **options):
        with transaction.atomic():
            # Model nema delete() ni signale, pa QuerySet.delete() nista ne preskace (stack-django pravilo 2).
            broj, _ = DeljeniRezultat.objects.istekli(timezone.now()).delete()
        self.stdout.write(f"obrisano isteklih: {broj}")
