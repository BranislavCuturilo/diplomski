"""Izmena klijenta: moderator vidi broj zavrsenih partija i prosecne poene po danu za poslednjih 7 dana."""

from datetime import date, datetime
from unittest import mock
from zoneinfo import ZoneInfo

from django.test import Client

from igra.models import Partija

from .test_istorija import zavrsi
from .test_jezik import CIRILICA, na_engleskom
from .test_moderator import OsnovaTest

BEOGRAD = ZoneInfo("Europe/Belgrade")
DANAS = date(2026, 11, 12)
URL = "/moderator/statistika/"


def zavrsena(godina, mesec, dan, sat, minut, poeni):
    kada = datetime(godina, mesec, dan, sat, minut, tzinfo=BEOGRAD)
    return Partija.objects.create(seme="x", zavrsena=kada, poeni=poeni)


class StatistikaTest(OsnovaTest):
    def statistika(self, klijent=None):
        with mock.patch("igra.moderacija.danas", return_value=DANAS):
            odgovor = (klijent or self.mod).get(URL)
        self.assertEqual(odgovor.status_code, 200)
        return odgovor

    def test_samo_za_moderatora(self):
        self.assertRedirects(Client().get(URL), "/moderator/prijava/")

    def test_meni_vodi_na_statistiku(self):
        self.assertContains(self.mod.get("/moderator/"), f'href="{URL}"')

    def test_broj_i_prosek_po_danu(self):
        # Pola sata posle ponoci po beogradskom vremenu (u UTC jos prethodni dan) je novi dan.
        zavrsena(2026, 11, 12, 0, 30, 80)
        zavrsena(2026, 11, 12, 23, 59, 61)
        zavrsena(2026, 11, 11, 23, 59, 50)
        zavrsena(2026, 11, 6, 0, 0, 40)
        zavrsena(2026, 11, 5, 23, 59, 99)  # osmi dan unazad: van statistike
        Partija.objects.create(seme="nezavrsena")
        dani = self.statistika().context["statistika"]["dani"]
        self.assertEqual(
            [(d["dan"], d["broj"], d["prosek"]) for d in dani],
            [
                ("12.11.2026.", 2, "70,5"),
                ("11.11.2026.", 1, "50,0"),
                ("10.11.2026.", 0, None),
                ("09.11.2026.", 0, None),
                ("08.11.2026.", 0, None),
                ("07.11.2026.", 0, None),
                ("06.11.2026.", 1, "40,0"),
            ],
        )
        self.assertTrue(dani[0]["danas"])
        self.assertEqual([d["udeo"] for d in dani], [100, 50, 0, 0, 0, 0, 50])

    def test_ukupno_je_prosek_svih_partija(self):
        for poeni in (80, 61, 50):
            zavrsena(2026, 11, 12, 10, 0, poeni)
        zavrsena(2026, 11, 10, 10, 0, 40)
        odgovor = self.statistika()
        ukupno = odgovor.context["statistika"]["ukupno"]
        self.assertEqual((ukupno["broj"], ukupno["prosek"]), (4, "57,8"))
        self.assertContains(odgovor, "57,8")

    def test_bez_partija(self):
        odgovor = self.statistika()
        self.assertEqual(odgovor.context["statistika"]["ukupno"]["broj"], 0)
        self.assertContains(odgovor, "—", count=8)

    def test_odigrana_partija_ulazi_u_statistiku(self):
        partija = zavrsi(Client())
        with mock.patch("igra.moderacija.danas", return_value=partija.zavrsena.astimezone(BEOGRAD).date()):
            danas = self.mod.get(URL).context["statistika"]["dani"][0]
        self.assertEqual((danas["broj"], danas["prosek"]), (1, f"{partija.poeni},0"))

    def test_na_engleskom(self):
        zavrsena(2026, 11, 12, 10, 0, 71)
        odgovor = self.statistika(na_engleskom(self.mod))
        self.assertIsNone(CIRILICA.search(odgovor.content.decode()))
        for tekst in ("Statistics for the last 7 days", "Nov 12, 2026", "71.0", "Average points"):
            self.assertContains(odgovor, tekst)
