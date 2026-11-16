import re

from django.test import Client, TestCase

from igra import pravila, servis
from igra.models import Partija

from .pomocno import SVE_OPUS
from .test_http import posalji, telo, zapocni
from .test_rang_lista import zavrsi

SEME = "tajnoseme0123456789"
LINK = re.compile(r'id="link-deljenja"[^>]*value="(http://testserver/partija/([A-Za-z0-9_-]+)/)"')


def link_sa_kraja(klijent):
    pogodak = LINK.search(klijent.get("/kraj/").content.decode())
    return pogodak.group(1), pogodak.group(2)


class LinkNaKrajuTest(TestCase):
    def test_zavrsni_ekran_ima_link_sa_nasumicnim_kodom(self):
        partija = zavrsi(self.client, SEME)
        adresa, kod = link_sa_kraja(self.client)
        partija.refresh_from_db()
        self.assertEqual(partija.kod, kod)
        self.assertGreaterEqual(len(kod), 20)
        self.assertNotIn(SEME, kod)
        self.assertNotEqual(kod, str(partija.pk))

    def test_kod_se_ne_menja_pri_ponovnom_otvaranju(self):
        zavrsi(self.client)
        self.assertEqual(link_sa_kraja(self.client), link_sa_kraja(self.client))

    def test_svaka_partija_ima_svoj_kod(self):
        zavrsi(self.client)
        _, prvi = link_sa_kraja(self.client)
        zavrsi(self.client)
        _, drugi = link_sa_kraja(self.client)
        self.assertNotEqual(prvi, drugi)

    def test_partija_u_toku_nema_kod(self):
        partija = zapocni(self.client)
        for krug in range(1, 8):
            posalji(self.client, telo(krug))
            self.assertNotContains(self.client.get("/"), "/partija/")
        partija.refresh_from_db()
        self.assertIsNone(partija.kod)
        with self.assertRaises(servis.SukobStanja):
            servis.kod_deljenja(partija)

    def test_link_ostaje_i_posle_greske_pri_cuvanju(self):
        zavrsi(self.client)
        odgovor = self.client.post("/rezultat/", {"ime": ""})
        self.assertEqual(odgovor.status_code, 400)
        self.assertContains(odgovor, 'id="link-deljenja"', status_code=400)


class PodeljenaStranicaTest(TestCase):
    def setUp(self):
        self.vlasnik = Client()
        zavrsi(self.vlasnik, SEME)
        self.adresa, self.kod = link_sa_kraja(self.vlasnik)
        self.putanja = f"/partija/{self.kod}/"

    def test_prikazuje_rezultat_te_partije(self):
        odgovor = Client().get(self.putanja)
        self.assertEqual(odgovor.status_code, 200)
        self.assertTemplateUsed(odgovor, "igra/podeljeno.html")

        ocekivano = pravila.konacni_rezultat(SEME, SVE_OPUS)
        self.assertContains(odgovor, f'<p id="poeni" class="poeni">{ocekivano.poeni}</p>', html=False)
        self.assertContains(odgovor, f'<p id="ocena" class="ocena">{ocekivano.ocena}</p>')
        for zadatak in ocekivano.tihe_greske:
            self.assertContains(odgovor, f"Круг {zadatak.krug}: {zadatak.naziv}")
        if not ocekivano.tihe_greske:
            self.assertContains(odgovor, "Нема тихих грешака.")
        for lekcija in ocekivano.lekcije:
            self.assertContains(odgovor, lekcija.tekst)
        self.assertContains(odgovor, "Цене и нивои размишљања су стварни подаци")

    def test_isti_sadrzaj_kao_zavrsni_ekran(self):
        kraj = self.vlasnik.get("/kraj/").context
        podeljeno = Client().get(self.putanja).context
        for kljuc in ("poeni", "ocena", "ukupna_cena", "ukupni_minuti", "tihe_greske", "lekcije"):
            self.assertEqual(podeljeno[kljuc], kraj[kljuc], kljuc)

    def test_nema_nastavka_igre_ni_formi(self):
        odgovor = Client().get(self.putanja)
        sadrzaj = odgovor.content.decode()
        self.assertNotIn("<form", sadrzaj)
        self.assertNotIn("csrfmiddlewaretoken", sadrzaj)
        self.assertNotIn('id="link-deljenja"', sadrzaj)
        self.assertContains(odgovor, 'id="igraj-i-ti"')
        self.assertContains(odgovor, '<meta name="robots" content="noindex">')

    def test_ne_dira_sesiju_posetioca(self):
        posetilac = Client()
        odgovor = posetilac.get(self.putanja)
        self.assertEqual(dict(odgovor.cookies), {})
        self.assertNotIn("sessionid", posetilac.cookies)
        # Posetilac bez svoje partije ne moze da odigra potez ni da sacuva rezultat.
        self.assertEqual(posalji(posetilac, telo(1)).status_code, 409)
        self.assertEqual(posetilac.post("/rezultat/", {"ime": "Уљез"}).status_code, 409)
        self.assertTemplateUsed(posetilac.get("/"), "igra/pocetak.html")

    def test_posetilac_u_toku_igre_ostaje_u_svojoj_partiji(self):
        posetilac = Client()
        njegova = zapocni(posetilac)
        posalji(posetilac, telo(1))
        posetilac.get(self.putanja)
        self.assertEqual(posetilac.session["partija_id"], njegova.pk)
        self.assertEqual(posetilac.get("/").context["krug"], 2)

    def test_nema_semena(self):
        self.assertNotContains(Client().get(self.putanja), SEME)

    def test_ime_se_prikazuje_posle_cuvanja_i_escapuje(self):
        self.assertNotContains(Client().get(self.putanja), 'id="ime-igraca"')
        self.vlasnik.post("/rezultat/", {"ime": "<b>Ана</b>"})
        odgovor = Client().get(self.putanja)
        self.assertContains(odgovor, "&lt;b&gt;Ана&lt;/b&gt;")
        self.assertNotContains(odgovor, "<b>Ана")

    def test_link_radi_i_posle_nove_igre_vlasnika(self):
        self.vlasnik.post("/nova/")
        posalji(self.vlasnik, telo(1))
        self.assertEqual(Client().get(self.putanja).status_code, 200)

    def test_nepoznat_kod_je_404(self):
        for putanja in ("/partija/nepostoji/", "/partija/" + self.kod[:-1] + "/", "/partija/%20/"):
            self.assertEqual(Client().get(putanja).status_code, 404, putanja)

    def test_partija_u_toku_se_ne_prikazuje_ni_sa_kodom(self):
        u_toku = zapocni(Client())
        Partija.objects.filter(pk=u_toku.pk).update(kod="rucnopostavljenkod")
        self.assertEqual(Client().get("/partija/rucnopostavljenkod/").status_code, 404)

    def test_post_nije_dozvoljen(self):
        self.assertEqual(Client().post(self.putanja).status_code, 405)
