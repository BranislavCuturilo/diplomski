"""Izmena klijenta u bodovanju: vazi samo za nove partije, stari rezultati se ne menjaju."""

import re

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase, TransactionTestCase

from igra import parametri as p
from igra.models import Partija, Rezultat

from .pomocno import neuspesni_krugovi
from .test_http import posalji, telo, zapocni

# Svi krugovi Opus/high, a tihi neuspeh u 5. krugu: budzet je 35 % preko, rok takodje.
STARI_POENI = 100 - 25 - 30 - 20
NOVI_POENI = 100 - 35 - 40 - 20
POENI = re.compile(r'id="poeni" class="poeni">(\d+)<')


def odigraj(klijent, bodovanje=None):
    """Igra celu partiju; bodovanje=1 glumi partiju zapocetu pre izmene."""
    partija = zapocni(klijent)
    if bodovanje is not None:
        Partija.objects.filter(pk=partija.pk).update(bodovanje=bodovanje)
    with neuspesni_krugovi(5):
        for krug in range(1, 9):
            posalji(klijent, telo(krug))
    return partija


def poeni_na(odgovor):
    return int(POENI.search(odgovor.content.decode()).group(1))


class BodovanjePartijeTest(TestCase):
    def test_nova_partija_dobija_tekuce_bodovanje(self):
        partija = zapocni(self.client)
        partija.refresh_from_db()
        self.assertEqual(partija.bodovanje, p.BODOVANJE_TEKUCE)

    def test_nova_partija_se_boduje_po_novom(self):
        odigraj(self.client)
        with neuspesni_krugovi(5):
            self.assertEqual(poeni_na(self.client.get("/kraj/")), NOVI_POENI)

    def test_stara_partija_zadrzava_stare_poene_svuda(self):
        odigraj(self.client, bodovanje=1)
        with neuspesni_krugovi(5):
            kraj = self.client.get("/kraj/")
            self.assertEqual(poeni_na(kraj), STARI_POENI)
            kod = Partija.objects.latest("pk").kod
            self.assertEqual(poeni_na(Client().get(f"/partija/{kod}/")), STARI_POENI)
            self.client.post("/rezultat/", {"ime": "Ana"})
        self.assertEqual(Rezultat.objects.get().poeni, STARI_POENI)
        self.assertEqual(Rezultat.objects.get().ocena, "пожар")

    def test_stara_partija_u_toku_zavrsava_se_po_starom(self):
        """Pravila se ne menjaju usred partije: zapoceta pre izmene, zavrsava se po prvom bodovanju."""
        partija = zapocni(self.client)
        Partija.objects.filter(pk=partija.pk).update(bodovanje=1)
        with neuspesni_krugovi(5):
            for krug in range(1, 9):
                posalji(self.client, telo(krug))
            self.assertEqual(poeni_na(self.client.get("/kraj/")), STARI_POENI)

    def test_sledeca_partija_istog_igraca_je_po_novom(self):
        odigraj(self.client, bodovanje=1)
        odigraj(self.client)
        self.assertEqual(Partija.objects.latest("pk").bodovanje, 2)
        with neuspesni_krugovi(5):
            self.assertEqual(poeni_na(self.client.get("/kraj/")), NOVI_POENI)

    def test_rang_lista_prikazuje_sacuvane_poene(self):
        odigraj(self.client, bodovanje=1)
        with neuspesni_krugovi(5):
            self.client.post("/rezultat/", {"ime": "Ana"})
        odgovor = Client().get("/")
        self.assertEqual(odgovor.context["rang_lista"][0]["poeni"], STARI_POENI)
        self.assertContains(odgovor, f"<strong>{STARI_POENI}</strong>")

    def test_bodovanje_se_ne_vidi_igracu(self):
        zapocni(self.client)
        for odgovor in (self.client.get("/"), posalji(self.client, telo(1))):
            self.assertNotIn("bodovanje", odgovor.content.decode())


class MigracijaBodovanjaTest(TransactionTestCase):
    """Partije koje postoje pre migracije (i njihovi linkovi i rezultati) dobijaju prvo bodovanje."""

    pre = [("igra", "0003_kod_deljenja")]
    posle = [("igra", "0004_bodovanje")]

    def vrati_na_poslednju(self):
        # Ostali testovi ocekuju bazu sa svim migracijama, i onim koje dolaze posle 0004.
        izvrsilac = MigrationExecutor(connection)
        izvrsilac.loader.build_graph()
        izvrsilac.migrate(izvrsilac.loader.graph.leaf_nodes())

    def test_postojece_partije_dobijaju_prvo_bodovanje(self):
        self.addCleanup(self.vrati_na_poslednju)
        izvrsilac = MigrationExecutor(connection)
        izvrsilac.migrate(self.pre)
        stara = izvrsilac.loader.project_state(self.pre).apps.get_model("igra", "Partija")
        pk = stara.objects.create(seme="staro", kod="podeljen-link").pk

        izvrsilac = MigrationExecutor(connection)
        izvrsilac.loader.build_graph()
        izvrsilac.migrate(self.posle)
        nova = izvrsilac.loader.project_state(self.posle).apps.get_model("igra", "Partija")
        self.assertEqual(nova.objects.get(pk=pk).bodovanje, 1)
        self.assertEqual(nova.objects.create(seme="novo").bodovanje, 2)
