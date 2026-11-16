"""Izmena klijenta: moderator brise rezultate i deljene linkove i vidi dnevnik. Igraci su bez naloga."""

import io
import re
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import CommandError, call_command
from django.test import Client, TestCase, override_settings

from igra import moderacija, servis
from igra.models import Dogadjaj, Partija, Rezultat

from .test_http import posalji, telo, zapocni
from .test_rang_lista import zavrsi

LOZINKA = "Dirigent-palica-42"
CIRILICA = re.compile(r"[\u0400-\u04FF]")
# Pravi hes (PBKDF2) je namerno spor; proverava ga samo PrijavaTest.
BRZ_HES = override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])


def napravi_moderatora(ime="mira", ko=None):
    return moderacija.dodaj_moderatora(ko, ime, LOZINKA, LOZINKA)


def prijavi(klijent, ime="mira", lozinka=LOZINKA):
    return klijent.post("/moderator/prijava/", {"ime": ime, "lozinka": lozinka})


def sacuvana_partija(ime="Ана"):
    """Igrac zavrsi partiju, sacuva rezultat i otvori zavrsni ekran (time nastaje link)."""
    igrac = Client()
    partija = zavrsi(igrac)
    igrac.get("/kraj/")
    igrac.post("/rezultat/", {"ime": ime})
    partija.refresh_from_db()
    return igrac, partija


@BRZ_HES
class OsnovaTest(TestCase):
    def setUp(self):
        cache.clear()
        self.mira = napravi_moderatora()
        self.mod = Client()
        self.mod.force_login(self.mira)


class PrijavaTest(TestCase):
    def setUp(self):
        cache.clear()
        self.mira = napravi_moderatora()

    def test_ispravna_prijava_vodi_na_moderaciju(self):
        odgovor = prijavi(self.client)
        self.assertRedirects(odgovor, "/moderator/")
        self.assertContains(self.client.get("/moderator/"), 'id="prijavljen" class="moderator-ime">mira<')

    def test_pogresna_lozinka_i_nepostojece_ime_daju_istu_poruku(self):
        pogresna = prijavi(self.client, lozinka="nije-ta-lozinka")
        nepostojeci = prijavi(self.client, ime="niko")
        for odgovor in (pogresna, nepostojeci):
            self.assertEqual(odgovor.status_code, 400)
            self.assertContains(odgovor, "Погрешно име или лозинка.", status_code=400)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_korisnik_bez_dozvole_ne_moze_da_se_prijavi(self):
        get_user_model().objects.create_user("obican", password=LOZINKA)
        self.assertEqual(prijavi(self.client, ime="obican").status_code, 400)

    def test_lozinka_se_cuva_samo_kao_hes(self):
        self.assertNotIn(LOZINKA, self.mira.password)
        self.assertTrue(self.mira.password.startswith("pbkdf2_sha256$"))

    def test_posle_pet_promasaja_prijava_je_zakljucana(self):
        for _ in range(moderacija.PRIJAVA_POKUSAJA):
            self.assertEqual(prijavi(self.client, lozinka="pogresno").status_code, 400)
        # Zakljucano je i za tacnu lozinku, i za isto ime napisano drugacijim slovima.
        self.assertEqual(prijavi(self.client).status_code, 429)
        self.assertEqual(prijavi(self.client, ime=" MIRA ").status_code, 429)
        cache.clear()
        self.assertEqual(prijavi(self.client).status_code, 302)

    def test_uspesna_prijava_brise_promasaje(self):
        for _ in range(moderacija.PRIJAVA_POKUSAJA - 1):
            prijavi(self.client, lozinka="pogresno")
        prijavi(self.client)
        self.assertFalse(moderacija.prijava_zakljucana("mira"))

    def test_prijava_i_odjava_cuvaju_partiju_koja_se_igra(self):
        partija = zapocni(self.client)
        posalji(self.client, telo(1))
        prijavi(self.client)
        self.assertEqual(self.client.session["partija_id"], partija.pk)
        self.client.post("/moderator/odjava/")
        self.assertEqual(self.client.session["partija_id"], partija.pk)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertRedirects(self.client.get("/moderator/"), "/moderator/prijava/")
        # Igra se nastavlja od drugog kruga.
        self.assertEqual(posalji(self.client, telo(2)).status_code, 200)

    def test_prijava_nije_za_pretrazivace(self):
        self.assertContains(self.client.get("/moderator/prijava/"), 'name="robots" content="noindex, nofollow"')


@BRZ_HES
class PristupTest(TestCase):
    STRANE = ("/moderator/", "/moderator/linkovi/", "/moderator/dnevnik/", "/moderator/nalozi/")

    def setUp(self):
        cache.clear()

    def test_bez_prijave_get_vodi_na_prijavu(self):
        rezultat = Rezultat.objects.create(partija=Partija.objects.create(seme="x", kod="k"), ime="A", poeni=5, ocena="пожар")
        for adresa in (*self.STRANE, f"/moderator/rezultat/{rezultat.pk}/obrisi/", "/moderator/link/k/obrisi/"):
            self.assertRedirects(self.client.get(adresa), "/moderator/prijava/", msg_prefix=adresa)

    def test_bez_prijave_post_je_zabranjen_i_nista_se_ne_menja(self):
        partija = Partija.objects.create(seme="x", kod="k")
        rezultat = Rezultat.objects.create(partija=partija, ime="A", poeni=5, ocena="пожар")
        mira = napravi_moderatora()
        for adresa in (
            f"/moderator/rezultat/{rezultat.pk}/obrisi/",
            "/moderator/link/k/obrisi/",
            "/moderator/nalozi/",
            f"/moderator/nalozi/{mira.pk}/iskljuci/",
        ):
            self.assertEqual(self.client.post(adresa, {"ime": "uljez", "lozinka": LOZINKA, "lozinka_ponovo": LOZINKA}).status_code, 403)
        self.assertTrue(Rezultat.objects.exists())
        self.assertEqual(Partija.objects.get(pk=partija.pk).kod, "k")
        self.assertFalse(get_user_model().objects.filter(username="uljez").exists())
        self.assertEqual(Dogadjaj.objects.exclude(vrsta=Dogadjaj.DODAT_MODERATOR).count(), 0)

    def test_brisanje_trazi_csrf(self):
        _, partija = sacuvana_partija()
        mod = Client(enforce_csrf_checks=True)
        mod.force_login(napravi_moderatora())
        self.assertEqual(mod.post(f"/moderator/rezultat/{partija.rezultat.pk}/obrisi/").status_code, 403)
        self.assertTrue(Rezultat.objects.exists())

    def test_igraci_i_dalje_bez_naloga(self):
        igrac, _ = sacuvana_partija()
        self.assertEqual(set(igrac.session.keys()), {"partija_id"})
        self.assertEqual(get_user_model().objects.count(), 0)
        # Kolacic igrac je anonimni kljuc za istoriju partija, ne nalog: nema korisnika ni prijave.
        for naziv in igrac.cookies:
            self.assertIn(naziv, ("sessionid", "csrftoken", settings.LANGUAGE_COOKIE_NAME, servis.KOLACIC_IGRACA))

    def test_pocetna_ne_pominje_moderaciju(self):
        self.assertNotContains(self.client.get("/"), "/moderator/")


class BrisanjeRezultataTest(OsnovaTest):
    def setUp(self):
        super().setUp()
        self.igrac, self.partija = sacuvana_partija("Увредљиво име")
        self.rezultat = self.partija.rezultat
        self.adresa = f"/moderator/rezultat/{self.rezultat.pk}/obrisi/"

    def test_spisak_prikazuje_rezultat_sa_dugmetom(self):
        odgovor = self.mod.get("/moderator/")
        self.assertContains(odgovor, "Увредљиво име")
        self.assertContains(odgovor, f'href="{self.adresa}"')

    def test_get_samo_pita_za_potvrdu(self):
        odgovor = self.mod.get(self.adresa)
        self.assertContains(odgovor, "Обрисати резултат?")
        self.assertContains(odgovor, "Увредљиво име")
        self.assertTrue(Rezultat.objects.filter(pk=self.rezultat.pk).exists())

    def test_post_brise_i_belezi_ko_sta_i_kada(self):
        odgovor = self.mod.post(self.adresa)
        self.assertRedirects(odgovor, "/moderator/?poruka=rezultat")
        self.assertFalse(Rezultat.objects.exists())
        dogadjaj = Dogadjaj.objects.get(vrsta=Dogadjaj.OBRISAN_REZULTAT)
        self.assertEqual(
            (dogadjaj.moderator, dogadjaj.partija_id, dogadjaj.ime_igraca, dogadjaj.poeni),
            (self.mira, self.partija.pk, "Увредљиво име", self.rezultat.poeni),
        )
        self.assertIsNotNone(dogadjaj.vreme)
        self.assertContains(self.mod.get("/moderator/?poruka=rezultat"), "Резултат је обрисан.")

    def test_rang_lista_vise_ne_prikazuje_rezultat(self):
        self.mod.post(self.adresa)
        self.assertNotContains(Client().get("/"), "Увредљиво име")

    def test_igrac_ne_moze_ponovo_da_sacuva(self):
        self.mod.post(self.adresa)
        kraj = self.igrac.get("/kraj/")
        self.assertContains(kraj, 'id="rezultat-uklonjen"')
        self.assertNotContains(kraj, 'id="forma-imena"')
        odgovor = self.igrac.post("/rezultat/", {"ime": "Novo ime"})
        self.assertContains(odgovor, 'id="rezultat-uklonjen"', status_code=409)
        self.assertNotContains(odgovor, 'id="forma-imena"', status_code=409)
        self.assertFalse(Rezultat.objects.exists())
        self.assertNotContains(self.igrac.get("/"), 'id="nazad-na-rezultat"')

    def test_link_ostaje_posle_brisanja_rezultata_ali_bez_imena(self):
        self.mod.post(self.adresa)
        odgovor = Client().get(f"/partija/{self.partija.kod}/")
        self.assertEqual(odgovor.status_code, 200)
        self.assertNotContains(odgovor, "Увредљиво име")

    def test_drugo_brisanje_istog_je_404(self):
        self.mod.post(self.adresa)
        self.assertEqual(self.mod.post(self.adresa).status_code, 404)
        self.assertEqual(self.mod.get(self.adresa).status_code, 404)
        self.assertEqual(Dogadjaj.objects.filter(vrsta=Dogadjaj.OBRISAN_REZULTAT).count(), 1)

    def test_ostali_rezultati_ostaju_i_mesta_se_pomeraju(self):
        _, druga = sacuvana_partija("Друга")
        self.mod.post(self.adresa)
        lista = Client().get("/").context["rang_lista"]
        self.assertEqual([(r["mesto"], r["ime"]) for r in lista], [(1, "Друга")])


class BrisanjeLinkaTest(OsnovaTest):
    def setUp(self):
        super().setUp()
        self.igrac, self.partija = sacuvana_partija("Ана")
        self.kod = self.partija.kod
        self.adresa = f"/moderator/link/{self.kod}/obrisi/"

    def test_spisak_linkova(self):
        odgovor = self.mod.get("/moderator/linkovi/")
        self.assertContains(odgovor, f"/partija/{self.kod}/")
        self.assertContains(odgovor, "Ана")

    def test_link_bez_rezultata_je_na_spisku(self):
        drugi = Client()
        zavrsi(drugi)
        drugi.get("/kraj/")
        self.assertContains(self.mod.get("/moderator/linkovi/"), "без сачуваног резултата")

    def test_post_gasi_link_i_belezi(self):
        self.assertContains(self.mod.get(self.adresa), "Обрисати линк?")
        self.assertRedirects(self.mod.post(self.adresa), "/moderator/linkovi/?poruka=link")
        self.assertEqual(Client().get(f"/partija/{self.kod}/").status_code, 404)
        dogadjaj = Dogadjaj.objects.get(vrsta=Dogadjaj.OBRISAN_LINK)
        self.assertEqual(
            (dogadjaj.moderator, dogadjaj.partija_id, dogadjaj.kod, dogadjaj.ime_igraca),
            (self.mira, self.partija.pk, self.kod, "Ана"),
        )

    def test_zavrsni_ekran_ne_pravi_novi_link(self):
        self.mod.post(self.adresa)
        kraj = self.igrac.get("/kraj/")
        self.assertContains(kraj, 'id="link-uklonjen"')
        self.assertNotContains(kraj, "/partija/")
        self.partija.refresh_from_db()
        self.assertIsNone(self.partija.kod)

    def test_rezultat_na_rang_listi_ostaje(self):
        self.mod.post(self.adresa)
        self.assertContains(Client().get("/"), "Ана")

    def test_nepostojeci_link_je_404(self):
        self.mod.post(self.adresa)
        self.assertEqual(self.mod.post(self.adresa).status_code, 404)
        self.assertEqual(self.mod.get("/moderator/link/nepostoji/obrisi/").status_code, 404)


class DnevnikTest(OsnovaTest):
    def test_dnevnik_prikazuje_ko_je_sta_obrisao_i_kada(self):
        _, partija = sacuvana_partija("Ана")
        self.mod.post(f"/moderator/rezultat/{partija.rezultat.pk}/obrisi/")
        self.mod.post(f"/moderator/link/{partija.kod}/obrisi/")
        redovi = self.mod.get("/moderator/dnevnik/").context["redovi"]
        self.assertEqual([(r["moderator"], r["vrsta"]) for r in redovi[:2]], [("mira", "link"), ("mira", "rezultat")])
        odgovor = self.mod.get("/moderator/dnevnik/")
        self.assertContains(odgovor, "обрисао резултат")
        self.assertContains(odgovor, "„Ана“")
        self.assertRegex(odgovor.content.decode(), r"<time>\d\d\.\d\d\.\d{4}\. \d\d:\d\d</time>")

    def test_moderator_koga_je_napravio_razvijalac(self):
        self.assertContains(self.mod.get("/moderator/dnevnik/"), "развијалац")

    def test_dnevnik_se_ne_moze_menjati_kroz_sajt(self):
        broj = Dogadjaj.objects.count()
        self.assertEqual(self.mod.post("/moderator/dnevnik/").status_code, 405)
        self.assertEqual(Dogadjaj.objects.count(), broj)

    def test_dnevnik_ima_strane(self):
        for i in range(moderacija.NA_STRANI + 3):
            Dogadjaj.objects.create(moderator=self.mira, vrsta=Dogadjaj.DODAT_MODERATOR, nalog=f"n{i}")
        prva = self.mod.get("/moderator/dnevnik/")
        self.assertEqual(len(prva.context["redovi"]), moderacija.NA_STRANI)
        self.assertContains(prva, "?strana=2")
        self.assertEqual(len(self.mod.get("/moderator/dnevnik/?strana=2").context["redovi"]), 4)


class NaloziTest(OsnovaTest):
    def dodaj(self, ime="vuk", lozinka=LOZINKA, ponovo=None):
        return self.mod.post(
            "/moderator/nalozi/", {"ime": ime, "lozinka": lozinka, "lozinka_ponovo": ponovo or lozinka}
        )

    def test_moderator_dodaje_moderatora(self):
        self.assertRedirects(self.dodaj(), "/moderator/nalozi/?poruka=dodat")
        dogadjaj = Dogadjaj.objects.get(vrsta=Dogadjaj.DODAT_MODERATOR, nalog="vuk")
        self.assertEqual(dogadjaj.moderator, self.mira)
        self.assertEqual(prijavi(Client(), ime="vuk").status_code, 302)

    def test_neispravni_nalozi(self):
        slucajevi = {
            ("", LOZINKA, LOZINKA): "Име налога је обавезно.",
            ("MIRA", LOZINKA, LOZINKA): "Налог са тим именом већ постоји.",
            ("ime sa razmakom", LOZINKA, LOZINKA): "Име налога сме да има само слова",
            ("x" * 31, LOZINKA, LOZINKA): "највише 30 знакова",
            ("vuk", LOZINKA, LOZINKA + "x"): "Лозинке се не поклапају.",
            ("vuk", "kratka", "kratka"): "lozinka",  # Django: prekratka lozinka
            ("vuk", "1234567890123", "1234567890123"): "lozinka",
            ("vuk", "", ""): "Лозинка је обавезна.",
        }
        for (ime, lozinka, ponovo), poruka in slucajevi.items():
            with self.subTest(ime=ime, lozinka=lozinka):
                odgovor = self.dodaj(ime, lozinka, ponovo)
                self.assertEqual(odgovor.status_code, 400)
                self.assertIn(poruka.casefold(), odgovor.content.decode().casefold())
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_iskljucen_moderator_gubi_pristup_odmah(self):
        vuk = napravi_moderatora("vuk", self.mira)
        vukov = Client()
        vukov.force_login(vuk)
        self.assertEqual(vukov.get("/moderator/").status_code, 200)

        self.assertRedirects(self.mod.post(f"/moderator/nalozi/{vuk.pk}/iskljuci/"), "/moderator/nalozi/?poruka=iskljucen")
        self.assertRedirects(vukov.get("/moderator/"), "/moderator/prijava/")
        self.assertEqual(prijavi(Client(), ime="vuk").status_code, 400)
        self.assertTrue(Dogadjaj.objects.filter(vrsta=Dogadjaj.ISKLJUCEN_MODERATOR, nalog="vuk", moderator=self.mira).exists())

        self.mod.post(f"/moderator/nalozi/{vuk.pk}/ukljuci/")
        self.assertEqual(prijavi(Client(), ime="vuk").status_code, 302)
        self.assertTrue(Dogadjaj.objects.filter(vrsta=Dogadjaj.UKLJUCEN_MODERATOR, nalog="vuk").exists())

    def test_ne_moze_da_iskljuci_sebe(self):
        odgovor = self.mod.post(f"/moderator/nalozi/{self.mira.pk}/iskljuci/")
        self.assertContains(odgovor, "Не можеш да искључиш сопствени налог.", status_code=400)
        self.mira.refresh_from_db()
        self.assertTrue(self.mira.is_active)

    def test_ne_dira_naloge_koji_nisu_moderatori(self):
        obican = get_user_model().objects.create_user("obican", password=LOZINKA)
        self.assertEqual(self.mod.post(f"/moderator/nalozi/{obican.pk}/iskljuci/").status_code, 404)

    def test_ista_radnja_dvaput_se_belezi_jednom(self):
        vuk = napravi_moderatora("vuk", self.mira)
        self.mod.post(f"/moderator/nalozi/{vuk.pk}/iskljuci/")
        self.mod.post(f"/moderator/nalozi/{vuk.pk}/iskljuci/")
        self.assertEqual(Dogadjaj.objects.filter(vrsta=Dogadjaj.ISKLJUCEN_MODERATOR).count(), 1)


@BRZ_HES
class KomandaTest(TestCase):
    def pokreni(self, *lozinke, ime="prvi"):
        with mock.patch("getpass.getpass", side_effect=lozinke):
            call_command("moderator", ime, stdout=io.StringIO())

    def test_razvijalac_pravi_prvog_moderatora(self):
        self.pokreni(LOZINKA, LOZINKA)
        prvi = get_user_model().objects.get(username="prvi")
        self.assertTrue(moderacija.je_moderator(prvi))
        self.assertFalse(prvi.is_superuser or prvi.is_staff)
        dogadjaj = Dogadjaj.objects.get()
        self.assertEqual((dogadjaj.vrsta, dogadjaj.moderator, dogadjaj.nalog), (Dogadjaj.DODAT_MODERATOR, None, "prvi"))

    def test_lozinke_se_ne_poklapaju(self):
        with self.assertRaisesMessage(CommandError, "The passwords do not match."):
            self.pokreni(LOZINKA, LOZINKA + "x")
        self.assertFalse(get_user_model().objects.exists())

    def test_slaba_lozinka_i_postojece_ime(self):
        with self.assertRaises(CommandError):
            self.pokreni("123", "123")
        self.pokreni(LOZINKA, LOZINKA)
        with self.assertRaisesMessage(CommandError, "already exists"):
            self.pokreni(LOZINKA, LOZINKA, ime="PRVI")


class EngleskiTest(OsnovaTest):
    def test_strane_moderatora_na_engleskom_nemaju_cirilicu(self):
        _, partija = sacuvana_partija("Ana")
        self.mod.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
        self.mod.post(f"/moderator/link/{partija.kod}/obrisi/")
        adrese = [
            "/moderator/?poruka=rezultat",
            "/moderator/linkovi/",
            f"/moderator/rezultat/{partija.rezultat.pk}/obrisi/",
            "/moderator/dnevnik/",
            "/moderator/nalozi/",
        ]
        for adresa in adrese:
            odgovor = self.mod.get(adresa)
            self.assertEqual(odgovor.status_code, 200, adresa)
            self.assertIsNone(CIRILICA.search(odgovor.content.decode()), adresa)
        greska = self.mod.post("/moderator/nalozi/", {"ime": "", "lozinka": "x", "lozinka_ponovo": "y"})
        self.assertIsNone(CIRILICA.search(greska.content.decode()))
        prijava = Client()
        prijava.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
        for odgovor in (prijava.get("/moderator/prijava/"), prijavi(prijava, lozinka="pogresno")):
            self.assertIsNone(CIRILICA.search(odgovor.content.decode()))
        self.assertContains(self.mod.get("/moderator/dnevnik/"), "deleted a link")
