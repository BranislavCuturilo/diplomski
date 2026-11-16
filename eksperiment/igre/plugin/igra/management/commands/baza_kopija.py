"""Dosledna kopija baze dok aplikacija radi (plan 15.6): VACUUM INTO, pa PRAGMA integrity_check nad kopijom."""

import os
import sqlite3
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, connection


class Command(BaseCommand):
    help = (
        "Pravi doslednu kopiju baze u PUTANJA (VACUUM INTO) i proverava je (PRAGMA integrity_check). Postojeca "
        "PUTANJA je greska. Kopija nosi sesije i heseve lozinki: datoteka je samo za vlasnika (0600)."
    )

    def add_arguments(self, parser):
        parser.add_argument("putanja", metavar="PUTANJA")

    def handle(self, *args, putanja, **options):
        cilj = Path(putanja).absolute()
        # Kopiranje datoteke dok aplikacija radi nije dosledno bez -wal; VACUUM INTO cita bazu kroz SQLite.
        try:
            # O_EXCL: postojeca putanja (i prazna datoteka, i direktorijum) se ne prepisuje, ni u trci sa drugim
            # pokretanjem. Prazna datoteka 0600 je dozvoljen cilj za VACUUM INTO i cuva prava pristupa kopije.
            os.close(os.open(cilj, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
        except FileExistsError:
            raise CommandError(f"{cilj} vec postoji; nista nije upisano.") from None
        except OSError as greska:
            raise CommandError(f"{cilj} ne moze da se napravi: {greska}. Nista nije upisano.") from greska

        try:
            with connection.cursor() as kursor:
                kursor.execute("VACUUM INTO %s", [str(cilj)])
            nalazi = self._provera(cilj)
        except (DatabaseError, sqlite3.Error) as greska:
            self._ukloni(cilj)
            raise CommandError(f"kopija nije napravljena: {greska}") from greska
        if nalazi != ["ok"]:
            self._ukloni(cilj)
            raise CommandError(f"kopija {cilj} nije ispravna i obrisana je; integrity_check: {nalazi[:10]}")
        self.stdout.write(f"kopija: {cilj} (integrity_check: ok)")

    @staticmethod
    def _provera(cilj):
        # Posebna veza samo za citanje, van Django-a: proverava se datoteka na disku, ne baza aplikacije.
        veza = sqlite3.connect(f"{cilj.as_uri()}?mode=ro", uri=True)
        try:
            return [red[0] for red in veza.execute("PRAGMA integrity_check")]
        finally:
            veza.close()

    @staticmethod
    def _ukloni(cilj):
        # Nepotpuna ili neispravna kopija ne sme da ostane pod imenom kopije (rotacija bi je cuvala kao dobru).
        try:
            cilj.unlink()
        except FileNotFoundError:
            pass  # vec je nema: cilj ovog koraka je ispunjen
