"""Izmena klijenta: igrac prijavljuje neprikladno ime sa rang liste, a moderator odlucuje da li brise rezultat."""

from datetime import timedelta

from django.conf import settings
from django.test import Client, TestCase
from django.utils import timezone

from igra import moderacija, pravila, servis
from igra.models import Dogadjaj, Partija, PrijavaImena, Rezultat

from .test_moderator import CIRILICA, OsnovaTest
from .test_rang_lista import dodaj

SPISAK = "/moderator/prijavljena-imena/"


def adresa_prijave(rezultat):
    return f"/rezultat/{rezultat.pk}/prijavi/"


def adresa_zadrzavanja(rezultat):
    return f"/moderator/rezultat/{rezultat.pk}/zadrzi/"


def dodaj_dnevni(ime, poeni, dan):
    partija = Partija.objects.create(seme="x", dan=dan)
    return Rezultat.objects.create(partija=partija, ime=ime, poeni=poeni, ocena=pravila.ocena_za_poene(poeni))


class PrijavaSaRangListeTest(TestCase):
    """Igrac: bez naloga, sa rang liste, uz potvrdu."""

    def setUp(self):
        self.sada = timezone.now()
        self.rezultat = dodaj("Ружно име", 70, self.sada)
        self.adresa = adresa_prijave(self.rezultat)

    def test_svaki_red_obe_liste_ima_link_za_prijavu(self):
        dnevni = dodaj_dnevni("Дневни", 60, servis.danas())
        odgovor = self.client.get("/")
        for rezultat in (self.rezultat, dnevni):
            self.assertContains(odgovor, f'class="rang-prijava" href="{adresa_prijave(rezultat)}" rel="nofollow"')
        self.assertContains(odgovor, 'aria-label="Пријави име „Ружно име“"')
        self.assertNotContains(odgovor, "/moderator/")

    def test_get_samo_pita_za_potvrdu(self):
        odgovor = self.client.get(self.adresa)
        self.assertTemplateUsed(odgovor, "igra/prijava_imena.html")
        self.assertContains(odgovor, '<p id="prijavljeno-ime" class="rang-ime fs-5 mb-1">Ружно име</p>')
        self.assertContains(odgovor, 'id="forma-prijave-imena"')
        self.assertContains(odgovor, 'href="/#rang-lista"')
        self.assertContains(odgovor, 'name="robots" content="noindex, nofollow"')
        self.assertFalse(PrijavaImena.objects.exists())

    def test_post_prijavljuje_a_ime_ostaje_na_listi(self):
        self.assertRedirects(self.client.post(self.adresa), self.adresa)
        prijava = PrijavaImena.objects.get()
        self.assertEqual((prijava.rezultat, prijava.resena), (self.rezultat, False))

        stranica = self.client.get(self.adresa)
        self.assertContains(stranica, 'id="ime-prijavljeno"')
        self.assertNotContains(stranica, "<form")
        # O rezultatu odlucuje moderator; sama prijava ne menja rang listu.
        self.assertContains(Client().get("/"), "Ружно име")

    def test_ponovljena_prijava_ostaje_jedna(self):
        self.client.post(self.adresa)
        prva = PrijavaImena.objects.get()
        for klijent in (self.client, Client()):
            self.assertRedirects(klijent.post(self.adresa), self.adresa)
        self.assertEqual(list(PrijavaImena.objects.values_list("pk", "podneta")), [(prva.pk, prva.podneta)])

    def test_prijava_ne_trazi_nalog_i_ne_dira_sesiju(self):
        klijent = Client()
        klijent.get("/")
        klijent.get(self.adresa)
        klijent.post(self.adresa)
        self.assertEqual(set(klijent.cookies), {"csrftoken"})
        self.assertTrue(PrijavaImena.objects.exists())

    def test_igrac_u_toku_partije_ostaje_u_njoj(self):
        self.client.post("/nova/")
        partija_id = self.client.session["partija_id"]
        self.client.post(self.adresa)
        self.assertEqual(dict(self.client.session), {"partija_id": partija_id})

    def test_prijava_trazi_csrf(self):
        klijent = Client(enforce_csrf_checks=True)
        self.assertEqual(klijent.post(self.adresa).status_code, 403)
        self.assertFalse(PrijavaImena.objects.exists())

    def test_ostale_metode_nisu_dozvoljene(self):
        for metoda in (self.client.put, self.client.delete, self.client.patch):
            self.assertEqual(metoda(self.adresa).status_code, 405)
        self.assertFalse(PrijavaImena.objects.exists())

    def test_ime_se_escapuje(self):
        opasno = dodaj('<b>"Ана"</b>', 90, self.sada)
        ocekivano = "&lt;b&gt;&quot;Ана&quot;&lt;/b&gt;"
        pocetna = self.client.get("/")
        self.assertContains(pocetna, f'aria-label="Пријави име „{ocekivano}“"')
        self.assertContains(self.client.get(adresa_prijave(opasno)), f'fs-5 mb-1">{ocekivano}</p>')
        for odgovor in (pocetna, self.client.get(adresa_prijave(opasno))):
            self.assertNotContains(odgovor, "<b>")
            self.assertNotContains(odgovor, "&amp;lt;")

    def test_nepostojeci_rezultat_je_404(self):
        for broj in (self.rezultat.pk + 1000, 0, 10**30):
            adresa = f"/rezultat/{broj}/prijavi/"
            self.assertEqual(self.client.get(adresa).status_code, 404, adresa)
            self.assertEqual(self.client.post(adresa).status_code, 404, adresa)
        for adresa in ("/rezultat/-1/prijavi/", "/rezultat/abc/prijavi/"):
            self.assertEqual(self.client.get(adresa).status_code, 404, adresa)
        self.assertFalse(PrijavaImena.objects.exists())

    def test_prijavljuje_se_samo_ime_koje_je_na_rang_listi(self):
        bolji = [dodaj(f"Играч {i}", 80 + i, self.sada) for i in range(10)]
        # Deset boljih rezultata: „Ружно име“ je jedanaesto i igrac ga ne vidi.
        self.assertNotContains(self.client.get("/"), "Ружно име")
        self.assertEqual(self.client.get(self.adresa).status_code, 404)
        self.assertEqual(self.client.post(self.adresa).status_code, 404)
        self.assertFalse(PrijavaImena.objects.exists())

        bolji[0].delete()
        self.assertContains(self.client.get("/"), "Ружно име")
        self.assertRedirects(self.client.post(self.adresa), self.adresa)
        self.assertEqual(PrijavaImena.objects.get().rezultat, self.rezultat)

    def test_dnevna_lista_samo_danasnja(self):
        danas = servis.danas()
        danasnji = dodaj_dnevni("Данашњи", 50, danas)
        jucerasnji = dodaj_dnevni("Јучерашњи", 50, danas - timedelta(days=1))

        self.assertContains(self.client.get(adresa_prijave(danasnji)), 'href="/#dnevna-lista"')
        self.assertRedirects(self.client.post(adresa_prijave(danasnji)), adresa_prijave(danasnji))
        self.assertEqual(self.client.get(adresa_prijave(jucerasnji)).status_code, 404)
        self.assertEqual(self.client.post(adresa_prijave(jucerasnji)).status_code, 404)
        self.assertEqual([p.rezultat for p in PrijavaImena.objects.all()], [danasnji])

    def test_deset_najboljih_dnevnih_ne_zavisi_od_glavne_liste(self):
        danas = servis.danas()
        for i in range(10):
            dodaj_dnevni(f"Дневни {i}", 60 + i, danas)
        jedanaesti = dodaj_dnevni("Једанаести", 10, danas)
        self.assertEqual(self.client.get(adresa_prijave(jedanaesti)).status_code, 404)
        # Glavna lista ima samo jedan rezultat, i on se i dalje moze prijaviti.
        self.assertEqual(self.client.get(self.adresa).status_code, 200)

    def test_na_engleskom_nema_cirilice(self):
        latinica = dodaj("Ana", 90, self.sada)
        adresa = adresa_prijave(latinica)
        klijent = Client()
        klijent.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"

        pocetna = klijent.get("/")
        self.assertContains(pocetna, 'aria-label="Report the name “Ana”"')
        self.assertContains(pocetna, 'title="Report an inappropriate name"')
        potvrda = klijent.get(adresa)
        self.assertContains(potvrda, "If this name is inappropriate, report it.")
        self.assertIsNone(CIRILICA.search(potvrda.content.decode()))

        klijent.post(adresa)
        prijavljeno = klijent.get(adresa)
        self.assertContains(prijavljeno, "The name has been reported.")
        self.assertIsNone(CIRILICA.search(prijavljeno.content.decode()))

        PrijavaImena.objects.update(resena=True)
        pregledano = klijent.get(adresa)
        self.assertContains(pregledano, "A moderator has reviewed this name")
        self.assertIsNone(CIRILICA.search(pregledano.content.decode()))


class PrijavljenaImenaTest(OsnovaTest):
    """Moderator: vidi prijavljena imena i za svako brise rezultat ili ga zadrzava."""

    def setUp(self):
        super().setUp()
        self.rezultat = dodaj("Ружно име", 70, timezone.now())
        self.igrac = Client()
        self.igrac.post(adresa_prijave(self.rezultat))
        self.zadrzi = adresa_zadrzavanja(self.rezultat)
        self.obrisi = f"/moderator/rezultat/{self.rezultat.pk}/obrisi/?odakle=prijave"

    def test_bez_prijave_moderatora_nema_pristupa(self):
        self.assertRedirects(Client().get(SPISAK), "/moderator/prijava/")
        self.assertEqual(Client().post(self.zadrzi).status_code, 403)
        self.assertFalse(PrijavaImena.objects.get().resena)
        self.assertFalse(Dogadjaj.objects.filter(vrsta=Dogadjaj.ZADRZAN_REZULTAT).exists())

    def test_spisak_prikazuje_prijavljeno_ime_i_obe_odluke(self):
        dodaj("Обично име", 60, timezone.now())
        odgovor = self.mod.get(SPISAK)
        self.assertEqual([r["ime"] for r in odgovor.context["redovi"]], ["Ружно име"])
        self.assertContains(odgovor, f'action="{self.zadrzi}"')
        self.assertContains(odgovor, f'href="{self.obrisi}"')
        self.assertRegex(odgovor.content.decode(), r"пријављено \d\d\.\d\d\.\d{4}\. \d\d:\d\d<")
        self.assertNotContains(odgovor, "Обично име")

    def test_prazan_spisak(self):
        PrijavaImena.objects.all().delete()
        self.assertContains(self.mod.get(SPISAK), "Нема пријављених имена.")

    def test_meni_pokazuje_broj_prijava_na_svakoj_stranici(self):
        for adresa in ("/moderator/", "/moderator/dnevnik/", SPISAK):
            self.assertContains(self.mod.get(adresa), '<span id="broj-prijava" class="moderator-broj">1</span>')
        self.mod.post(self.zadrzi)
        self.assertNotContains(self.mod.get("/moderator/"), 'id="broj-prijava"')

    def test_najstarija_prijava_je_prva_i_spisak_ima_strane(self):
        PrijavaImena.objects.all().delete()
        sada = timezone.now()
        for i in range(moderacija.NA_STRANI + 3):
            prijava = PrijavaImena.objects.create(rezultat=dodaj(f"Име {i}", 50, sada))
            PrijavaImena.objects.filter(pk=prijava.pk).update(podneta=sada - timedelta(minutes=i))
        prva = self.mod.get(SPISAK)
        self.assertEqual(len(prva.context["redovi"]), moderacija.NA_STRANI)
        self.assertEqual(prva.context["redovi"][0]["ime"], f"Име {moderacija.NA_STRANI + 2}")
        self.assertContains(prva, "?strana=2")
        self.assertEqual(len(self.mod.get(SPISAK + "?strana=2").context["redovi"]), 3)

    def test_zadrzavanje_ostavlja_rezultat_i_belezi_ko_sta_i_kada(self):
        self.assertRedirects(self.mod.post(self.zadrzi), SPISAK + "?poruka=zadrzan")
        self.assertTrue(PrijavaImena.objects.get().resena)
        dogadjaj = Dogadjaj.objects.get(vrsta=Dogadjaj.ZADRZAN_REZULTAT)
        self.assertEqual(
            (dogadjaj.moderator, dogadjaj.partija_id, dogadjaj.ime_igraca, dogadjaj.poeni),
            (self.mira, self.rezultat.partija_id, "Ружно име", 70),
        )
        self.assertIsNotNone(dogadjaj.vreme)

        spisak = self.mod.get(SPISAK + "?poruka=zadrzan")
        self.assertContains(spisak, "Резултат је задржан.")
        self.assertEqual(spisak.context["redovi"], [])
        self.assertContains(Client().get("/"), "Ружно име")
        self.assertContains(self.mod.get("/moderator/"), "Ружно име")

    def test_zadrzan_rezultat_se_vise_ne_moze_prijaviti(self):
        self.mod.post(self.zadrzi)
        adresa = adresa_prijave(self.rezultat)
        stranica = self.igrac.get(adresa)
        self.assertContains(stranica, 'id="ime-pregledano"')
        self.assertNotContains(stranica, "<form")

        self.assertRedirects(self.igrac.post(adresa), adresa)
        self.assertTrue(PrijavaImena.objects.get().resena)
        self.assertEqual(self.mod.get(SPISAK).context["redovi"], [])
        self.assertNotContains(self.mod.get(SPISAK), 'id="broj-prijava"')

    def test_zadrzavanje_bez_otvorene_prijave_je_404(self):
        neprijavljen = dodaj("Обично име", 60, timezone.now())
        self.assertEqual(self.mod.post(adresa_zadrzavanja(neprijavljen)).status_code, 404)
        self.mod.post(self.zadrzi)
        self.assertEqual(self.mod.post(self.zadrzi).status_code, 404)
        self.assertEqual(self.mod.post("/moderator/rezultat/999999/zadrzi/").status_code, 404)
        self.assertEqual(Dogadjaj.objects.filter(vrsta=Dogadjaj.ZADRZAN_REZULTAT).count(), 1)

    def test_zadrzavanje_trazi_post_i_csrf(self):
        self.assertEqual(self.mod.get(self.zadrzi).status_code, 405)
        strogi = Client(enforce_csrf_checks=True)
        strogi.force_login(self.mira)
        self.assertEqual(strogi.post(self.zadrzi).status_code, 403)
        self.assertFalse(PrijavaImena.objects.get().resena)

    def test_brisanje_sa_spiska_prijava_vraca_na_spisak(self):
        potvrda = self.mod.get(self.obrisi)
        self.assertContains(potvrda, "Обрисати резултат?")
        self.assertContains(potvrda, "Ружно име")
        self.assertContains(potvrda, f'action="{self.obrisi}"')
        self.assertContains(potvrda, f'id="odustani" class="btn dugme-sporedno" href="{SPISAK}"')
        self.assertTrue(Rezultat.objects.filter(pk=self.rezultat.pk).exists())

        self.assertRedirects(self.mod.post(self.obrisi), SPISAK + "?poruka=rezultat")
        self.assertFalse(Rezultat.objects.filter(pk=self.rezultat.pk).exists())
        self.assertFalse(PrijavaImena.objects.exists())
        dogadjaj = Dogadjaj.objects.get(vrsta=Dogadjaj.OBRISAN_REZULTAT)
        self.assertEqual((dogadjaj.moderator, dogadjaj.ime_igraca, dogadjaj.poeni), (self.mira, "Ружно име", 70))

        spisak = self.mod.get(SPISAK + "?poruka=rezultat")
        self.assertContains(spisak, "Резултат је обрисан.")
        self.assertContains(spisak, "Нема пријављених имена.")
        self.assertNotContains(Client().get("/"), "Ружно име")
        self.assertEqual(self.igrac.get(adresa_prijave(self.rezultat)).status_code, 404)

    def test_brisanje_sa_spiska_rezultata_uklanja_i_prijavu(self):
        adresa = f"/moderator/rezultat/{self.rezultat.pk}/obrisi/"
        self.assertContains(self.mod.get(adresa), 'id="odustani" class="btn dugme-sporedno" href="/moderator/"')
        self.assertRedirects(self.mod.post(adresa), "/moderator/?poruka=rezultat")
        self.assertFalse(PrijavaImena.objects.exists())
        self.assertEqual(self.mod.get(SPISAK).context["redovi"], [])

    def test_dnevnik_prikazuje_zadrzavanje(self):
        self.mod.post(self.zadrzi)
        odgovor = self.mod.get("/moderator/dnevnik/")
        red = odgovor.context["redovi"][0]
        self.assertEqual((red["moderator"], red["vrsta"]), ("mira", "zadrzan"))
        self.assertContains(odgovor, "задржао пријављени резултат")
        self.assertContains(odgovor, "„Ружно име“")

    def test_strane_moderatora_na_engleskom_nemaju_cirilicu(self):
        Rezultat.objects.filter(pk=self.rezultat.pk).update(ime="Ana")
        drugi = dodaj("Bora", 60, timezone.now())
        PrijavaImena.objects.create(rezultat=drugi)
        self.mod.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
        self.mod.post(adresa_zadrzavanja(drugi))
        for adresa in (SPISAK + "?poruka=zadrzan", self.obrisi, "/moderator/dnevnik/"):
            odgovor = self.mod.get(adresa)
            self.assertEqual(odgovor.status_code, 200, adresa)
            self.assertIsNone(CIRILICA.search(odgovor.content.decode()), adresa)
        self.assertContains(self.mod.get(SPISAK), '<button type="submit" class="btn dugme-sporedno">Keep</button>')
        self.assertContains(self.mod.get("/moderator/dnevnik/"), "kept a reported result")
        PrijavaImena.objects.all().delete()
        self.assertContains(self.mod.get(SPISAK), "No reported names.")
