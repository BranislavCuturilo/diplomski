"""Dodavanje moderatora (plan 14.5). Prvog, glavnog, pravi razvijalac: moderator_dodaj IME --glavni."""

from django.contrib.auth import get_user_model
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from igra import nalozi

from .moderatori import greska_odbijanja, greska_validacije, unesi_lozinku

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Dodaje moderatora. Lozinka se unosi dvaput (nikad kao argument); vlasnik je menja pri prvoj prijavi. "
        "Dok aktivnog glavnog moderatora nema, trazi --glavni."
    )

    def add_arguments(self, parser):
        parser.add_argument("ime")
        parser.add_argument("--glavni", action="store_true", help="glavni moderator: upravlja nalozima")

    def handle(self, *args, ime, glavni, **options):
        if not glavni and not nalozi.ima_aktivnog_glavnog():
            raise CommandError(
                "Nema aktivnog glavnog moderatora, pa prvi mora biti glavni: "
                f"python manage.py moderator_dodaj {ime} --glavni. Nista nije upisano."
            )
        # Ime pre lozinke, da se lozinka ne kuca uzalud; servis sve proverava ponovo, pod bravom.
        ime = User.normalize_username(ime)
        try:
            UnicodeUsernameValidator()(ime)
        except ValidationError as greska:
            raise greska_validacije(greska) from greska
        if nalozi.ime_zauzeto(ime):
            raise CommandError(f"Ime {ime!r} je zauzeto (velika i mala slova se ne razlikuju). Nista nije upisano.")
        lozinka = unesi_lozinku()
        try:
            korisnik = nalozi.dodaj(None, ime, lozinka, glavni=glavni)
        except ValidationError as greska:
            raise greska_validacije(greska) from greska
        except nalozi.Odbijeno as greska:
            raise greska_odbijanja(greska) from greska
        uloga = "glavni moderator" if glavni else "moderator"
        self.stdout.write(
            f"Dodat {uloga} {korisnik.get_username()!r}; pocetnu lozinku menja pri prvoj prijavi."
        )
