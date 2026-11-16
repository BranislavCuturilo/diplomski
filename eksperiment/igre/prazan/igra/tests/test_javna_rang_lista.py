"""Izmena klijenta: javna adresa sa koje partneri preuzimaju rang listu u JSON obliku."""

import json
from datetime import timedelta

from django.test import Client, TestCase
from django.utils import timezone

from igra import parametri as p
from igra import servis
from igra.models import Partija, Rezultat

from .test_http import posalji, telo, zapocni
from .test_jezik import na_engleskom
from .test_rang_lista import dodaj

URL = "/api/rang-lista/"
POLJA_REDA = {"mesto", "ime", "poeni", "ocena", "sacuvan"}


def dodaj_dnevni(ime, poeni, dan):
    partija = Partija.objects.create(seme="tajno-dnevno-seme", dan=dan)
    return Rezultat.objects.create(partija=partija, ime=ime, poeni=poeni, ocena="солидан")


class JavnaRangListaTest(TestCase):
    def preuzmi(self, klijent=None):
        odgovor = (klijent or self.client).get(URL)
        self.assertEqual(odgovor.status_code, 200)
        return odgovor

    def test_oblik_odgovora(self):
        sada = timezone.now()
        dodaj("Ана", 70, sada)
        dodaj("Бора", 90, sada)
        dodaj("Ceca", 70, sada + timedelta(seconds=1))
        dodaj_dnevni("Данас", 55, servis.danas())
        dodaj_dnevni("Јуче", 99, servis.danas() - timedelta(days=1))
        podaci = self.preuzmi().json()

        self.assertEqual(set(podaci), {"verzija", "vreme", "rang_lista", "dnevna_lista"})
        self.assertEqual(podaci["verzija"], 1)
        self.assertEqual([(r["mesto"], r["ime"], r["poeni"]) for r in podaci["rang_lista"]],
                         [(1, "Бора", 90), (2, "Ана", 70), (2, "Ceca", 70)])
        for red in podaci["rang_lista"]:
            self.assertEqual(set(red), POLJA_REDA)
        self.assertEqual(podaci["rang_lista"][0]["ocena"], {"sr": "одличан оркестратор", "en": "excellent orchestrator"})
        self.assertEqual(podaci["dnevna_lista"]["dan"], servis.danas().isoformat())
        self.assertEqual([r["ime"] for r in podaci["dnevna_lista"]["rang_lista"]], ["Данас"])

    def test_vreme_je_iso_sa_zonom(self):
        dodaj("Ана", 70, timezone.now())
        podaci = self.preuzmi().json()
        for vreme in (podaci["vreme"], podaci["rang_lista"][0]["sacuvan"]):
            self.assertRegex(vreme, r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d$")

    def test_najvise_deset_kao_na_pocetnom_ekranu(self):
        for i in range(12):
            dodaj(f"Играч {i}", 50 + i, timezone.now())
        podaci = self.preuzmi().json()
        self.assertEqual(len(podaci["rang_lista"]), p.BROJ_NA_RANG_LISTI)
        self.assertEqual([r["ime"] for r in podaci["rang_lista"]],
                         [r["ime"] for r in Client().get("/").context["rang_lista"]])

    def test_prazna_lista(self):
        podaci = self.preuzmi().json()
        self.assertEqual(podaci["rang_lista"], [])
        self.assertEqual(podaci["dnevna_lista"]["rang_lista"], [])

    def test_zaglavlja_za_partnere(self):
        odgovor = self.preuzmi()
        self.assertEqual(odgovor["Content-Type"], "application/json")
        self.assertEqual(odgovor["Access-Control-Allow-Origin"], "*")
        self.assertEqual(odgovor["Cache-Control"], "public, max-age=60")

    def test_bez_kolacica_i_sesije(self):
        zapocni(self.client)
        posalji(self.client, telo(1))
        sesija = dict(self.client.session)
        odgovor = self.preuzmi()
        self.assertEqual(odgovor.cookies, {})
        self.assertEqual(dict(self.client.session), sesija)

    def test_bez_skrivenih_podataka(self):
        rezultat = dodaj_dnevni("Данас", 55, servis.danas())
        Partija.objects.filter(pk=rezultat.partija_id).update(kod="kod-linka-partije")
        sadrzaj = self.preuzmi().content.decode()
        for tajna in ("tajno-dnevno-seme", "kod-linka-partije", '"pk"', '"partija'):
            self.assertNotIn(tajna, sadrzaj)

    def test_ime_kako_je_upisano(self):
        dodaj("<b>Ана</b>", 70, timezone.now())
        odgovor = self.preuzmi()
        self.assertIn("<b>Ана</b>".encode(), odgovor.content)
        self.assertEqual(json.loads(odgovor.content)["rang_lista"][0]["ime"], "<b>Ана</b>")

    def test_isto_na_oba_jezika(self):
        dodaj("Ана", 70, timezone.now())
        srpski, engleski = self.preuzmi().json(), self.preuzmi(na_engleskom()).json()
        srpski.pop("vreme")
        engleski.pop("vreme")
        self.assertEqual(srpski, engleski)

    def test_samo_citanje(self):
        self.assertEqual(self.client.post(URL).status_code, 405)
        self.assertEqual(self.client.head(URL).status_code, 200)
