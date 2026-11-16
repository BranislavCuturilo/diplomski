"""Izmena klijenta: igrac na pocetnom ekranu vidi svojih poslednjih 10 zavrsenih partija."""

import hashlib
from datetime import timedelta

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase, TransactionTestCase
from django.utils import timezone

from igra import moderacija, pravila, servis
from igra.models import Partija, Potez

from .pomocno import SVE_OPUS
from .test_http import posalji, telo, zapocni
from .test_jezik import CIRILICA, na_engleskom

GODINA = 365 * 24 * 60 * 60


def zavrsi(klijent, seme="seme-istorije"):
    partija = zapocni(klijent, seme)
    for krug in range(1, 9):
        posalji(klijent, telo(krug))
    partija.refresh_from_db()
    return partija


def kljuc(klijent):
    return klijent.cookies[servis.KOLACIC_IGRACA].value


class KolacicIgracaTest(TestCase):
    def test_nova_igra_daje_kolacic_a_baza_cuva_samo_hes(self):
        odgovor = self.client.post("/nova/")
        kolacic = odgovor.cookies[servis.KOLACIC_IGRACA]
        self.assertEqual(len(kolacic.value), 32)
        self.assertEqual(kolacic["max-age"], GODINA)
        self.assertTrue(kolacic["httponly"])
        self.assertEqual(kolacic["samesite"], "Lax")
        partija = Partija.objects.get()
        self.assertEqual(partija.igrac, hashlib.sha256(kolacic.value.encode()).hexdigest())
        self.assertNotIn(kolacic.value, str(Partija.objects.values().get()))

    def test_isti_igrac_u_sledecoj_partiji(self):
        prva = zavrsi(self.client)
        stari = kljuc(self.client)
        druga = zapocni(self.client)
        self.assertEqual(kljuc(self.client), stari)
        self.assertEqual(prva.igrac, Partija.objects.get(pk=druga.pk).igrac)

    def test_neispravan_kolacic_se_zamenjuje(self):
        for los in ("kratak", "x" * 31 + "!", "x" * 33):
            klijent = Client()
            klijent.cookies[servis.KOLACIC_IGRACA] = los
            klijent.post("/nova/")
            self.assertNotEqual(kljuc(klijent), los)
            self.assertTrue(servis.ispravan_kljuc_igraca(kljuc(klijent)))

    def test_dnevni_izazov_takodje_pamti_igraca(self):
        self.client.post("/dnevna/")
        self.assertEqual(Partija.objects.get().igrac, servis.hes_igraca(kljuc(self.client)))

    def test_sesija_i_dalje_nosi_samo_partiju(self):
        partija = zavrsi(self.client)
        self.assertEqual(dict(self.client.session), {"partija_id": partija.pk})


class ZavrsetakTest(TestCase):
    def test_poslednji_potez_upisuje_vreme_i_poene(self):
        partija = zapocni(self.client, "seme-istorije")
        for krug in range(1, 8):
            posalji(self.client, telo(krug))
        partija.refresh_from_db()
        self.assertIsNone(partija.zavrsena)
        self.assertIsNone(partija.poeni)

        pre = timezone.now()
        posalji(self.client, telo(8))
        partija.refresh_from_db()
        self.assertGreaterEqual(partija.zavrsena, pre)
        self.assertEqual(partija.poeni, pravila.konacni_rezultat("seme-istorije", SVE_OPUS).poeni)

    def test_poeni_po_bodovanju_partije(self):
        partija = zapocni(self.client, "seme-istorije")
        Partija.objects.filter(pk=partija.pk).update(bodovanje=1)
        for krug in range(1, 9):
            posalji(self.client, telo(krug))
        partija.refresh_from_db()
        self.assertEqual(partija.poeni, pravila.konacni_rezultat("seme-istorije", SVE_OPUS, 1).poeni)
        self.assertEqual(partija.poeni, self.client.get("/kraj/").context["poeni"])


class MojePartijeTest(TestCase):
    def moje(self, klijent=None):
        return (klijent or self.client).get("/").context["moje_partije"]

    def test_bez_kolacica_nema_odeljka(self):
        odgovor = self.client.get("/")
        self.assertEqual(odgovor.context["moje_partije"], [])
        self.assertNotContains(odgovor, 'id="moje-partije"')

    def test_zavrsene_partije_najnovija_prva(self):
        prva = zavrsi(self.client, "prvo")
        druga = zavrsi(self.client, "drugo")
        Partija.objects.filter(pk=prva.pk).update(zavrsena=druga.zavrsena - timedelta(minutes=5))
        odgovor = self.client.get("/")
        redovi = odgovor.context["moje_partije"]
        self.assertEqual([r["poeni"] for r in redovi], [druga.poeni, prva.poeni])
        druga.refresh_from_db()
        self.assertEqual(redovi[0]["kod"], druga.kod)
        self.assertContains(odgovor, f'href="/partija/{druga.kod}/"')
        self.assertEqual(redovi[0]["ocena"], pravila.ocena_za_poene(druga.poeni))
        self.assertFalse(redovi[0]["dnevna"])

    def test_partija_u_toku_se_ne_vidi(self):
        zavrsi(self.client)
        zapocni(self.client)
        posalji(self.client, telo(1))
        # Tokom partije / je ekran igre; istorija se racuna samo od zavrsenih partija.
        igrac = servis.hes_igraca(kljuc(self.client))
        self.assertEqual(len(servis.moje_partije(igrac)), 1)

    def test_najvise_deset(self):
        zavrsi(self.client)
        igrac = servis.hes_igraca(kljuc(self.client))
        sada = timezone.now()
        for i in range(12):
            partija = Partija.objects.create(seme="x", igrac=igrac, zavrsena=sada - timedelta(days=i + 1), poeni=i)
            Potez.objects.bulk_create(
                Potez(partija=partija, krug=krug, **izbori._asdict()) for krug, izbori in enumerate(SVE_OPUS, start=1)
            )
        redovi = self.moje()
        self.assertEqual(len(redovi), 10)
        self.assertEqual([r["poeni"] for r in redovi[1:]], list(range(9)))

    def test_tudje_partije_se_ne_vide(self):
        zavrsi(self.client)
        drugi = Client()
        zavrsi(drugi, "drugo")
        self.assertEqual(len(self.moje()), 1)
        self.assertEqual(len(self.moje(drugi)), 1)
        self.assertEqual(self.moje(Client()), [])

    def test_dnevna_partija_i_sacuvano_ime(self):
        self.client.post("/dnevna/")
        for krug in range(1, 9):
            posalji(self.client, telo(krug))
        self.client.post("/rezultat/", {"ime": "<b>Ана</b>"})
        odgovor = self.client.get("/")
        red = odgovor.context["moje_partije"][0]
        self.assertTrue(red["dnevna"])
        self.assertEqual(red["ime"], "<b>Ана</b>")
        self.assertContains(odgovor, "дневни изазов")
        self.assertContains(odgovor, "„&lt;b&gt;Ана&lt;/b&gt;“")

    def test_obrisan_link_nije_link(self):
        partija = zavrsi(self.client)
        self.client.get("/kraj/")
        partija.refresh_from_db()
        moderacija.obrisi_link(None, partija.kod)
        odgovor = self.client.get("/")
        red = odgovor.context["moje_partije"][0]
        self.assertIsNone(red["kod"])
        self.assertEqual(red["poeni"], partija.poeni)
        self.assertNotContains(odgovor, "/partija/")

    def test_na_engleskom(self):
        klijent = na_engleskom()
        klijent.post("/dnevna/")
        for krug in range(1, 9):
            posalji(klijent, telo(krug))
        odgovor = klijent.get("/")
        self.assertContains(odgovor, "My games")
        self.assertContains(odgovor, "daily challenge")
        self.assertIsNone(CIRILICA.search(odgovor.content.decode()))


class MigracijaIstorijeTest(TransactionTestCase):
    """Postojece zavrsene partije dobijaju poene po svom bodovanju i vreme zavrsetka."""

    pre = [("igra", "0007_prijava_imena")]
    posle = [("igra", "0008_istorija_i_statistika")]

    def vrati_na_poslednju(self):
        izvrsilac = MigrationExecutor(connection)
        izvrsilac.loader.build_graph()
        izvrsilac.migrate(izvrsilac.loader.graph.leaf_nodes())

    def test_zavrsene_partije_dobijaju_poene(self):
        self.addCleanup(self.vrati_na_poslednju)
        izvrsilac = MigrationExecutor(connection)
        izvrsilac.migrate(self.pre)
        stari = izvrsilac.loader.project_state(self.pre).apps
        Partija0, Potez0 = stari.get_model("igra", "Partija"), stari.get_model("igra", "Potez")
        zavrsena = Partija0.objects.create(seme="staro", bodovanje=1)
        nezavrsena = Partija0.objects.create(seme="pola")
        for krug, izbori in enumerate(SVE_OPUS, start=1):
            Potez0.objects.create(partija=zavrsena, krug=krug, **izbori._asdict())
            if krug <= 4:
                Potez0.objects.create(partija=nezavrsena, krug=krug, **izbori._asdict())

        izvrsilac = MigrationExecutor(connection)
        izvrsilac.loader.build_graph()
        izvrsilac.migrate(self.posle)
        Partija1 = izvrsilac.loader.project_state(self.posle).apps.get_model("igra", "Partija")
        posle = Partija1.objects.get(pk=zavrsena.pk)
        self.assertEqual(posle.poeni, pravila.konacni_rezultat("staro", SVE_OPUS, 1).poeni)
        self.assertEqual(posle.zavrsena, posle.napravljena)
        self.assertEqual(posle.igrac, "")
        pola = Partija1.objects.get(pk=nezavrsena.pk)
        self.assertEqual((pola.zavrsena, pola.poeni), (None, None))
