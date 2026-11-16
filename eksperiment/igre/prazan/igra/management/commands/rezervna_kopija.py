"""Rezervna kopija baze: python manage.py rezervna_kopija <folder> [--zadrzi 14]

Koristi SQLite backup, pa je kopija ispravna i dok server radi i igraci igraju.
Pravi datoteku orkestrator-GGGGMMDD-SSMMSS.sqlite3 i brise starije kopije preko broja --zadrzi.
"""

import sqlite3
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone

OBRAZAC = "orkestrator-*.sqlite3"


class Command(BaseCommand):
    help = "Pravi rezervnu kopiju SQLite baze i brise najstarije kopije."

    def add_arguments(self, parser):
        parser.add_argument("folder", help="Folder za kopije.")
        parser.add_argument("--zadrzi", type=int, default=14, help="Koliko poslednjih kopija ostaje (podrazumevano 14).")

    def handle(self, *args, folder, zadrzi, **options):
        if zadrzi < 1:
            raise CommandError("--zadrzi mora biti bar 1.")
        if connection.vendor != "sqlite":
            raise CommandError("Komanda radi samo sa SQLite bazom.")
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)

        trenutak = timezone.localtime().strftime("%Y%m%d-%H%M%S")
        cilj = folder / f"orkestrator-{trenutak}.sqlite3"
        privremena = cilj.with_suffix(".delimicno")
        # Posebna veza samo za citanje: u WAL rezimu ne ceka upise igraca i ne zadrzava ih.
        izvor = sqlite3.connect(f"file:{Path(connection.settings_dict['NAME']).as_posix()}?mode=ro", uri=True, timeout=20)
        odrediste = sqlite3.connect(privremena)
        try:
            izvor.backup(odrediste)
            provera = odrediste.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            odrediste.close()
            izvor.close()
        if provera != "ok":
            privremena.unlink(missing_ok=True)
            raise CommandError(f"Kopija nije ispravna: {provera}")
        # Kopija dobija pravo ime tek kada je cela zapisana, pa se nedovrsena nikad ne vraca.
        privremena.replace(cilj)

        kopije = sorted(folder.glob(OBRAZAC))
        for stara in kopije[:-zadrzi]:
            stara.unlink()
        self.stdout.write(f"Kopija: {cilj} ({cilj.stat().st_size} bajtova).")
