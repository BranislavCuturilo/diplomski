"""Izmena klijenta: moderator preuzima glavnu i dnevnu rang listu kao CSV za Excel."""

import csv
import io
from datetime import date, datetime, timezone

from django.test import Client

from igra import pravila
from igra.models import Partija, Rezultat

from .test_moderator import OsnovaTest


def dodaj(ime, poeni, dan=None):
    partija = Partija.objects.create(seme="x", dan=dan)
    rezultat = Rezultat.objects.create(partija=partija, ime=ime, poeni=poeni, ocena=pravila.ocena_za_poene(poeni))
    Rezultat.objects.filter(pk=rezultat.pk).update(sacuvan=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc))
    return rezultat


def procitaj(odgovor):
    tekst = odgovor.content.decode("utf-8")
    assert tekst.startswith("﻿")
    return list(csv.reader(io.StringIO(tekst[1:]), delimiter=";"))


class IzvozTest(OsnovaTest):
    def test_glavna_lista_cela_sa_deljenim_mestima(self):
        dodaj("Ана", 50)
        dodaj("Бора", 70)
        dodaj("Ceca", 50)
        dodaj("Дневни", 99, dan=date(2026, 3, 1))
        odgovor = self.mod.get("/moderator/izvoz/?lista=glavna")
        self.assertEqual(odgovor.status_code, 200)
        self.assertEqual(odgovor["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn('attachment; filename="rang-lista.csv"', odgovor["Content-Disposition"])
        redovi = procitaj(odgovor)
        self.assertEqual(redovi[0], ["Место", "Име", "Поени", "Оцена", "Сачувано"])
        self.assertEqual([(r[0], r[1], r[2]) for r in redovi[1:]], [("1", "Бора", "70"), ("2", "Ана", "50"), ("2", "Ceca", "50")])
        self.assertEqual(redovi[1][4], "2026-03-01 13:00")

    def test_dnevna_lista_samo_tog_dana(self):
        dodaj("Обичан", 80)
        dodaj("Јуче", 60, dan=date(2026, 2, 28))
        dodaj("Данас", 40, dan=date(2026, 3, 1))
        odgovor = self.mod.get("/moderator/izvoz/?lista=dnevna&dan=2026-03-01")
        self.assertIn("rang-lista-dana-2026-03-01.csv", odgovor["Content-Disposition"])
        self.assertEqual([r[1] for r in procitaj(odgovor)[1:]], ["Данас"])

    def test_pogresan_dan_i_lista(self):
        self.assertEqual(self.mod.get("/moderator/izvoz/?lista=dnevna&dan=juce").status_code, 400)
        self.assertEqual(self.mod.get("/moderator/izvoz/?lista=sve").status_code, 400)

    def test_ime_ne_postaje_formula(self):
        dodaj("=HYPERLINK(1)", 10)
        self.assertEqual(procitaj(self.mod.get("/moderator/izvoz/"))[1][1], "'=HYPERLINK(1)")

    def test_samo_za_moderatora(self):
        self.assertRedirects(Client().get("/moderator/izvoz/"), "/moderator/prijava/")

    def test_dugmad_na_stranici_rezultata(self):
        odgovor = self.mod.get("/moderator/")
        self.assertContains(odgovor, 'id="izvoz-glavna"')
        self.assertContains(odgovor, 'id="izvoz-dnevna"')
