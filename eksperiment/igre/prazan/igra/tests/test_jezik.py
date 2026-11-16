import re
from datetime import datetime, timezone as dt_timezone

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import Client, TestCase

from igra import parametri as p
from igra import prevodi
from igra.models import Partija, Rezultat
from igra.pravila import Izbori

from .pomocno import neuspesni_krugovi
from .test_http import URL_POTEZA, posalji, telo, zapocni
from .test_rang_lista import dodaj

CIRILICA = re.compile(r"[Ѐ-ӿ]")
GODINA = 365 * 24 * 60 * 60
# Svaka lekcija ima svoj uslov: Opus na lakom zadatku, max, sve, 50 agenata i tihi neuspeh (krug 5).
SVE_LEKCIJE = Izbori("opus", "max", "sve", "50_agenata")


def na_engleskom(klijent=None):
    klijent = klijent or Client()
    klijent.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
    return klijent


class IzborJezikaTest(TestCase):
    def test_podrazumevano_je_srpski(self):
        odgovor = self.client.get("/")
        self.assertContains(odgovor, '<html lang="sr-Cyrl"')
        self.assertContains(odgovor, "Нова игра")
        self.assertEqual(odgovor["Content-Language"], "sr")

    def test_jezik_pregledaca_se_ne_koristi(self):
        odgovor = self.client.get("/", HTTP_ACCEPT_LANGUAGE="en-US,en;q=0.9")
        self.assertContains(odgovor, "Нова игра")

    def test_izbor_engleskog_se_pamti_godinu_dana(self):
        odgovor = self.client.get("/jezik/en/", {"dalje": "/kraj/"})
        self.assertRedirects(odgovor, "/kraj/", fetch_redirect_response=False)
        kolacic = odgovor.cookies[settings.LANGUAGE_COOKIE_NAME]
        self.assertEqual(kolacic.value, "en")
        self.assertEqual(kolacic["max-age"], GODINA)
        self.assertTrue(kolacic["httponly"])
        self.assertEqual(kolacic["samesite"], "Lax")

        stranica = self.client.get("/")
        self.assertContains(stranica, '<html lang="en"')
        self.assertContains(stranica, "New game")
        self.assertEqual(stranica["Content-Language"], "en")

    def test_povratak_na_srpski(self):
        self.client.get("/jezik/en/")
        self.client.get("/jezik/sr/")
        self.assertContains(self.client.get("/"), "Нова игра")

    def test_nepoznat_jezik_je_404(self):
        for kod in ("de", "EN", "sr-latn", "x"):
            odgovor = self.client.get(f"/jezik/{kod}/")
            self.assertEqual(odgovor.status_code, 404, kod)
            self.assertNotIn(settings.LANGUAGE_COOKIE_NAME, odgovor.cookies)

    def test_neispravan_kolacic_daje_srpski(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "de"
        self.assertContains(self.client.get("/"), "Нова игра")

    def test_povratak_samo_na_isti_sajt(self):
        for dalje in ("https://zlo.example/", "//zlo.example/", "javascript:alert(1)", ""):
            odgovor = self.client.get("/jezik/en/", {"dalje": dalje})
            self.assertRedirects(odgovor, "/", fetch_redirect_response=False, msg_prefix=dalje)

    def test_post_nije_dozvoljen(self):
        self.assertEqual(self.client.post("/jezik/en/").status_code, 405)

    def test_promena_tokom_igre_cuva_partiju(self):
        partija = zapocni(self.client)
        posalji(self.client, telo(1))
        posalji(self.client, telo(2))
        self.client.get("/jezik/en/", {"dalje": "/"})
        odgovor = self.client.get("/")
        self.assertEqual(odgovor.context["krug"], 3)
        self.assertEqual(self.client.session["partija_id"], partija.pk)
        self.assertEqual(set(self.client.session.keys()), {"partija_id"})
        self.assertEqual(posalji(self.client, telo(3)).status_code, 200)

    def test_linkovi_jezika_vracaju_na_istu_stranicu(self):
        zapocni(self.client)
        for krug in range(1, 9):
            posalji(self.client, telo(krug))
        self.assertContains(self.client.get("/kraj/"), 'href="/jezik/en/?dalje=%2Fkraj%2F"')
        # Posle neuspelog cuvanja (POST) link vodi na zavrsni ekran, ne na /rezultat/.
        greska = self.client.post("/rezultat/", {"ime": ""})
        self.assertContains(greska, 'href="/jezik/en/?dalje=%2Fkraj%2F"', status_code=400)

    def test_podeljena_stranica_i_dalje_nema_formi(self):
        zapocni(self.client)
        for krug in range(1, 9):
            posalji(self.client, telo(krug))
        self.client.get("/kraj/")
        kod = Partija.objects.get().kod
        odgovor = Client().get(f"/partija/{kod}/")
        self.assertNotContains(odgovor, "<form")
        self.assertContains(odgovor, f'href="/jezik/en/?dalje=%2Fpartija%2F{kod}%2F"')


class EngleskiTekstTest(TestCase):
    """Na engleskom nijedan ekran ni odgovor nema cirilicu, osim imena koja su igraci upisali."""

    def setUp(self):
        self.klijent = na_engleskom()

    def bez_cirilice(self, odgovor):
        sadrzaj = odgovor.content.decode()
        pogodak = CIRILICA.search(sadrzaj)
        self.assertIsNone(pogodak, sadrzaj[max(0, pogodak.start() - 80) : pogodak.end() + 80] if pogodak else "")

    def test_pocetni_ekran_i_rang_lista(self):
        dodaj("Ana", 70, datetime(2026, 11, 9, 23, 30, tzinfo=dt_timezone.utc))
        odgovor = self.klijent.get("/")
        self.bez_cirilice(odgovor)
        for tekst in ("Orchestrator", "New game", "Leaderboard", "solid", "Nov 10, 2026", "24 $", "150 min"):
            self.assertContains(odgovor, tekst)

    def test_prazna_rang_lista(self):
        self.assertContains(self.klijent.get("/"), "No saved results yet.")

    def test_svaki_krug_potez_i_greska(self):
        zapocni(self.klijent)
        with neuspesni_krugovi(1, 5):
            for krug in range(1, 9):
                stranica = self.klijent.get("/")
                self.bez_cirilice(stranica)
                self.bez_cirilice(posalji(self.klijent, {**telo(krug), "model": "x"}))
                self.bez_cirilice(posalji(self.klijent, telo(krug + 1)))
                self.bez_cirilice(self.klijent.post(URL_POTEZA, b"nije json", content_type="application/json"))
                odgovor = posalji(self.klijent, telo(krug))
                self.assertEqual(odgovor.status_code, 200)
                self.bez_cirilice(odgovor)
                if krug == 1:
                    self.assertEqual(odgovor.json()["status"], "sent back for rework")
                elif krug == 2:
                    self.assertEqual(odgovor.json()["status"], "done")
        self.bez_cirilice(posalji(self.klijent, telo(9)))

    def test_ekran_igre_ima_prevedene_opcije_i_brojeve(self):
        zapocni(self.klijent)
        with neuspesni_krugovi():
            posalji(self.klijent, telo(1, Izbori("haiku", "high", "taman", "sam")))
            odgovor = self.klijent.get("/")
        for tekst in ("0.18 $/M", "7.20 $/M", "time ×0.5", "tokens ×3.6", "just right", "3 agents",
                      "Reasoning level", "Round", "Budget left", "List and form template", "0.018", "done"):
            self.assertContains(odgovor, tekst)
        self.assertContains(odgovor, 'data-status-gotovo="done"')

    def test_zavrsni_ekran_sa_svim_lekcijama(self):
        zapocni(self.klijent)
        with neuspesni_krugovi(1, 5):
            for krug in range(1, 9):
                posalji(self.klijent, telo(krug, SVE_LEKCIJE))
            odgovor = self.klijent.get("/kraj/")
        self.assertEqual(len(odgovor.context["lekcije"]), len(p.LEKCIJE))
        self.assertEqual(len(odgovor.context["tihe_greske"]), 1)
        self.bez_cirilice(odgovor)
        for tekst in ("Final check", "Silent errors", "Round 5: Data model and migration", "Lessons",
                      "Section 4.2 of the thesis.", "house on fire", "made-up game parameters",
                      "Share the result", "Enter your name and save the result"):
            self.assertContains(odgovor, tekst)

    def test_greska_pri_cuvanju_imena(self):
        zapocni(self.klijent)
        for krug in range(1, 9):
            posalji(self.klijent, telo(krug))
        odgovor = self.klijent.post("/rezultat/", {"ime": "a" * 31})
        self.assertContains(odgovor, "The name must have 1 to 30 characters.", status_code=400)
        self.bez_cirilice(odgovor)
        self.klijent.post("/rezultat/", {"ime": "Ana"})
        sacuvano = self.klijent.get("/kraj/")
        self.assertContains(sacuvano, "Result saved as “Ana”.")
        self.bez_cirilice(sacuvano)
        self.bez_cirilice(self.klijent.post("/rezultat/", {"ime": "Ana"}))

    def test_podeljena_stranica(self):
        vlasnik = Client()
        zapocni(vlasnik)
        for krug in range(1, 9):
            posalji(vlasnik, telo(krug))
        vlasnik.get("/kraj/")
        vlasnik.post("/rezultat/", {"ime": "Ana"})
        odgovor = self.klijent.get(f"/partija/{Partija.objects.get().kod}/")
        self.bez_cirilice(odgovor)
        self.assertContains(odgovor, "Shared result")
        self.assertContains(odgovor, "Play it yourself")

    def test_ime_igraca_ostaje_kako_je_upisano(self):
        dodaj("Ана", 50, datetime(2026, 5, 1, tzinfo=dt_timezone.utc))
        self.assertContains(self.klijent.get("/"), "Ана")

    def test_ocena_na_rang_listi_se_prevodi(self):
        for poeni, ocena in ((90, "excellent orchestrator"), (70, "solid"), (50, "costly lesson"), (10, "house on fire")):
            Rezultat.objects.all().delete()
            dodaj("Ana", poeni, datetime(2026, 5, 1, tzinfo=dt_timezone.utc))
            self.assertContains(self.klijent.get("/"), ocena)


class KatalogTest(TestCase):
    def test_katalog_je_potpun_i_mo_azuran(self):
        po = prevodi.ucitaj_po()
        self.assertEqual(prevodi.problemi(po, prevodi.izvuci_poruke()), [])
        self.assertTrue(prevodi.mo_je_azuran(po), "pokreni `python manage.py prevodi`")

    def test_prevodi_nemaju_cirilicu(self):
        for unos in prevodi.ucitaj_po():
            for prevod in [unos.msgstr, *unos.msgstr_plural.values()]:
                self.assertIsNone(CIRILICA.search(prevod), unos.msgid)

    def test_svi_tekstovi_iz_parametara_su_u_katalogu(self):
        poruke = prevodi.izvuci_poruke()
        tekstovi = [
            p.STATUS_GOTOVO, p.STATUS_DORADA, p.NAPOMENA_O_PARAMETRIMA,
            *(z.naziv for z in p.ZADACI), *(o for _, o in p.OCENE), *(l.tekst for l in p.LEKCIJE),
            *(k.naziv for k in p.KONTEKSTI.values()), *(d.naziv for d in p.PODELE.values()),
        ]
        for tekst in tekstovi:
            self.assertIn(tekst, poruke)

    def test_skripta_nema_svoj_tekst(self):
        with open(finders.find("igra/igra.js"), encoding="utf-8") as datoteka:
            self.assertIsNone(CIRILICA.search(datoteka.read()))
