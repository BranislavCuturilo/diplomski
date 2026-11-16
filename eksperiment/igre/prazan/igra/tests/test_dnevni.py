from datetime import date
from unittest import mock

from django.test import Client, TestCase

from igra import servis
from igra.models import Partija, Rezultat

from .test_http import posalji, telo
from .test_rang_lista import dodaj


def igraj_dnevnu(klijent):
    klijent.post("/dnevna/")
    for krug in range(1, 9):
        posalji(klijent, telo(krug))
    return Partija.objects.latest("pk")


class DnevniIzazovTest(TestCase):
    def test_svi_igraci_dobijaju_isto_seme_istog_dana(self):
        a, b = Client(), Client()
        pa, pb = igraj_dnevnu(a), igraj_dnevnu(b)
        self.assertEqual(pa.seme, pb.seme)
        self.assertNotEqual(pa.pk, pb.pk)
        self.assertEqual(pa.dan, pb.dan)

    def test_seme_se_menja_po_danu_i_nije_otkriveno(self):
        d1, d2 = date(2026, 11, 12), date(2026, 11, 13)
        self.assertNotEqual(servis.dnevno_seme(d1), servis.dnevno_seme(d2))
        self.assertEqual(servis.dnevno_seme(d1), servis.dnevno_seme(d1))
        self.assertNotIn(servis.dnevno_seme(d1), Client().get("/").content.decode())

    def test_obicne_partije_ostaju_nasumicne(self):
        a, b = Client(), Client()
        a.post("/nova/")
        b.post("/nova/")
        semena = set(Partija.objects.values_list("seme", flat=True))
        self.assertEqual(len(semena), 2)
        self.assertEqual(set(Partija.objects.values_list("dan", flat=True)), {None})

    def test_jedan_pokusaj_dnevno_po_sesiji(self):
        klijent = Client()
        igraj_dnevnu(klijent)
        klijent.post("/dnevna/")
        self.assertEqual(Partija.objects.count(), 1)
        odgovor = klijent.get("/")
        self.assertNotContains(odgovor, 'id="dnevni-izazov"')
        self.assertContains(odgovor, 'id="dnevni-odigran"')

    def test_sutradan_je_ponovo_dostupan(self):
        klijent = Client()
        igraj_dnevnu(klijent)
        with mock.patch.object(servis, "danas", return_value=date(2999, 1, 1)):
            self.assertContains(klijent.get("/"), 'id="dnevni-izazov"')
            klijent.post("/dnevna/")
        self.assertEqual(Partija.objects.count(), 2)

    def test_partija_u_toku_se_nastavlja(self):
        klijent = Client()
        klijent.post("/dnevna/")
        posalji(klijent, telo(1))
        klijent.post("/dnevna/")
        self.assertEqual(Partija.objects.count(), 1)

    def test_rezultat_dnevne_ide_na_listu_dana_a_ne_na_glavnu(self):
        klijent = Client()
        igraj_dnevnu(klijent)
        odgovor = klijent.post("/rezultat/", {"ime": "Ана"})
        self.assertRedirects(odgovor, "/#dnevna-lista", fetch_redirect_response=False)
        dodaj("Бора", 10, servis.timezone.now())
        pocetna = Client().get("/")
        self.assertEqual([r["ime"] for r in pocetna.context["dnevna_lista"]], ["Ана"])
        self.assertEqual([r["ime"] for r in pocetna.context["rang_lista"]], ["Бора"])

    def test_lista_dana_ne_pokazuje_juce(self):
        klijent = Client()
        partija = igraj_dnevnu(klijent)
        klijent.post("/rezultat/", {"ime": "Ана"})
        Partija.objects.filter(pk=partija.pk).update(dan=date(2020, 1, 1))
        self.assertEqual(Client().get("/").context["dnevna_lista"], [])

    def test_ista_partija_isti_poeni(self):
        a, b = Client(), Client()
        igraj_dnevnu(a)
        igraj_dnevnu(b)
        a.post("/rezultat/", {"ime": "А"})
        b.post("/rezultat/", {"ime": "Б"})
        poeni = list(Rezultat.objects.values_list("poeni", flat=True))
        self.assertEqual(len(set(poeni)), 1)
