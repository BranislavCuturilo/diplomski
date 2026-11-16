"""Ispis naloga moderatora (plan 14.5) i pomocnici komandi moderator_*.

Komande su rezerva razvijaca; sve idu kroz igra/nalozi.py sa ko=None, pa pravila 1-3 i dnevnik vaze i ovde.
"""

import getpass

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone, translation

from igra import nalozi

from .rezultati import FORMAT_TRENUTKA

User = get_user_model()

ODBIJANJA = {
    "poslednji_glavni": "Mora ostati bar jedan aktivan glavni moderator.",
    "nije_moderator": "Nalog nije moderator.",
    "nije_aktivan": "Nalog nije aktivan.",
    "vec_aktivan": "Nalog je vec aktivan.",
    "vec_glavni": "Nalog je vec glavni moderator.",
    "nije_glavni": "Nalog nije glavni moderator.",
    "glavni_bez_moderira": "Nalog bi imao ulogu glavnog bez dozvole moderira.",
    "lozinka_promenjena": "Lozinka naloga je promenjena u medjuvremenu; pokreni komandu ponovo.",
}


def greska_odbijanja(greska):
    """CommandError za nalozi.Odbijeno."""
    return CommandError(f"{ODBIJANJA.get(greska.kod, greska.kod)} Nista nije upisano.")


def greska_validacije(greska):
    """CommandError za ValidationError (validatori imena i lozinke); poruke Django-a na engleskom izvoru."""
    with translation.override(None):
        poruke = " ".join(greska.messages)
    return CommandError(f"{poruke} Nista nije upisano.")


def nalog_po_imenu(ime):
    nalog = nalozi.moderator_po_imenu(ime)
    if nalog is None:
        raise CommandError(f"Nema moderatora sa imenom {ime!r}. Spisak: python manage.py moderatori")
    return nalog


def unesi_lozinku():
    """Lozinka dvaput kroz getpass, nikad kao argument: ne ostaje u istoriji ljuske ni u spisku procesa."""
    prva = getpass.getpass("Lozinka: ")
    druga = getpass.getpass("Lozinka (ponovo): ")
    if prva != druga:
        raise CommandError("Lozinke se ne poklapaju. Nista nije upisano.")
    if not prva:
        raise CommandError("Lozinka je prazna. Nista nije upisano.")
    return prva


def brojevi():
    """Aktivni moderatori i aktivni glavni, istim uslovima kao uloga()."""
    aktivnih = sum(1 for korisnik in nalozi.moderatori() if nalozi.uloga(korisnik) is not None)
    return f"Aktivnih moderatora: {aktivnih}, aktivnih glavnih: {nalozi.aktivni_glavni().count()}."


def _da(vrednost):
    return "da" if vrednost else "ne"


class Command(BaseCommand):
    help = (
        "Ispisuje naloge moderatora: ime, aktivan, glavni, mora da promeni lozinku, poslednja prijava. "
        "Upozorava na svaki superuser nalog."
    )

    def handle(self, *args, **options):
        glavni_ids = nalozi.id_glavnih()
        redovi = list(nalozi.moderatori())
        if not redovi:
            self.stdout.write("Nema moderatora. Prvi: python manage.py moderator_dodaj IME --glavni")
        for korisnik in redovi:
            prijava = (
                "-"
                if korisnik.last_login is None
                else timezone.localtime(korisnik.last_login).strftime(FORMAT_TRENUTKA)
            )
            self.stdout.write(
                f"ime={korisnik.get_username()!r} aktivan={_da(korisnik.is_active)} "
                f"glavni={_da(korisnik.pk in glavni_ids)} "
                f"mora_promeniti={_da(korisnik.nalog_moderatora.mora_promeniti)} poslednja_prijava={prijava}"
            )
        if redovi:
            self.stdout.write(brojevi())
        # Superuser nastaje samo mimo komandi (createsuperuser, ljuska): has_perm mu daje sve, uloga() nista.
        for ime in User.objects.filter(is_superuser=True).order_by("username").values_list("username", flat=True):
            self.stdout.write(
                f"UPOZORENJE: {ime!r} je superuser; nije moderator na strani, a ima sve dozvole. "
                "Napravljen je mimo komandi."
            )
