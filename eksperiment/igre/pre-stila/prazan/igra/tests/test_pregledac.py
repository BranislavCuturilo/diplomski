import os

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from playwright.sync_api import expect, sync_playwright

from igra import parametri as p
from igra import pravila
from igra.models import Partija, Potez
from igra.pravila import Izbori

SIROK_EKRAN = {"width": 1280, "height": 800}
TELEFON = {"width": 375, "height": 667}
SEME = "seme-za-pregledac"

STRATEGIJA = {
    1: Izbori("haiku", "high", "taman", "sam"),
    2: Izbori("sonnet", "high", "taman", "3_agenta"),
    3: Izbori("opus", "high", "taman", "sam"),
}
POTEZI = [STRATEGIJA[z.tezina] for z in p.ZADACI]


class PregledacTestCase(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        # Sinhroni Playwright drzi asyncio petlju, a testovi iz iste niti citaju bazu.
        os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.pregledac = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.pregledac.close()
        cls.playwright.stop()
        super().tearDownClass()
        os.environ.pop("DJANGO_ALLOW_ASYNC_UNSAFE", None)

    def otvori(self, ekran=SIROK_EKRAN):
        kontekst = self.pregledac.new_context(viewport=ekran)
        self.addCleanup(kontekst.close)
        stranica = kontekst.new_page()
        self.greske = []
        self.zahtevi_poteza = []
        stranica.on(
            "console",
            lambda poruka: self.greske.append(poruka.text) if poruka.type == "error" else None,
        )
        stranica.on("pageerror", lambda greska: self.greske.append(str(greska)))
        stranica.on(
            "response",
            lambda odgovor: self.greske.append(f"{odgovor.status} {odgovor.url}")
            if odgovor.status >= 400
            else None,
        )
        stranica.on(
            "request",
            lambda zahtev: self.zahtevi_poteza.append(zahtev)
            if zahtev.url.endswith("/api/potez/")
            else None,
        )
        return stranica

    def zapocni(self, stranica):
        stranica.goto(self.live_server_url)
        stranica.get_by_role("button", name="Нова игра").click()
        expect(stranica.locator("#broj-kruga")).to_have_text("1")
        partija = Partija.objects.latest("pk")
        partija.seme = SEME
        partija.save()

    def izaberi(self, stranica, izbori):
        for polje, vrednost in izbori._asdict().items():
            stranica.locator(f'label[for="{polje}-{vrednost}"]').click()

    def odigraj(self, stranica, krug, izbori):
        self.izaberi(stranica, izbori)
        stranica.locator("#potvrdi").click()
        if krug < p.BROJ_KRUGOVA:
            expect(stranica.locator("#broj-kruga")).to_have_text(str(krug + 1))
        else:
            expect(stranica.locator("#pogledaj-rezultat")).to_be_visible()

    def proveri_sirinu(self, stranica, sirina):
        self.assertLessEqual(
            stranica.evaluate("document.documentElement.scrollWidth"), sirina, stranica.url
        )

    def test_cela_igra_i_nova_igra(self):
        stranica = self.otvori()
        self.zapocni(stranica)
        expect(stranica.locator("#potvrdi")).to_be_disabled()

        stanje = pravila.vidljivo_stanje(SEME, POTEZI)
        for krug, izbori in enumerate(POTEZI, start=1):
            expect(stranica.locator("#naziv-zadatka")).to_have_text(p.ZADACI[krug - 1].naziv)
            self.odigraj(stranica, krug, izbori)
            expect(stranica.locator("#poslednji-status")).to_have_text(
                stanje.krugovi[krug - 1].status
            )
            if krug < p.BROJ_KRUGOVA:
                expect(stranica.locator("#potvrdi")).to_be_disabled()

        expect(stranica.locator("#forma-poteza")).to_be_hidden()
        expect(stranica.locator("#istorija li")).to_have_count(p.BROJ_KRUGOVA)
        stranica.locator("#pogledaj-rezultat").click()

        rezultat = pravila.konacni_rezultat(SEME, POTEZI)
        expect(stranica.locator("#poeni")).to_have_text(str(rezultat.poeni))
        expect(stranica.locator("#ocena")).to_have_text(rezultat.ocena)
        expect(stranica.locator("#napomena")).to_have_text(p.NAPOMENA_O_PARAMETRIMA)
        if rezultat.tihe_greske:
            expect(stranica.locator("#tihe-greske li")).to_have_count(len(rezultat.tihe_greske))
        else:
            expect(stranica.locator("#tihe-greske")).to_have_text("Нема тихих грешака.")

        stranica.locator("#nova-igra").click()
        expect(stranica.locator("#broj-kruga")).to_have_text("1")
        expect(stranica.locator("#istorija li")).to_have_count(0)
        self.assertEqual(self.greske, [])

    def test_osvezavanje_cuva_stanje(self):
        stranica = self.otvori()
        self.zapocni(stranica)
        self.odigraj(stranica, 1, POTEZI[0])
        ocekivani_budzet = stranica.locator("#budzet").inner_text()
        stranica.reload()
        expect(stranica.locator("#broj-kruga")).to_have_text("2")
        expect(stranica.locator("#budzet")).to_have_text(ocekivani_budzet)
        expect(stranica.locator("#istorija li")).to_have_count(1)
        self.assertEqual(self.greske, [])

    def test_dvoklik_salje_jedan_potez(self):
        stranica = self.otvori()
        self.zapocni(stranica)
        self.izaberi(stranica, POTEZI[0])
        stranica.locator("#potvrdi").dblclick()
        expect(stranica.locator("#broj-kruga")).to_have_text("2")
        expect(stranica.locator("#istorija li")).to_have_count(1)
        self.assertEqual(len(self.zahtevi_poteza), 1)
        self.assertEqual(Potez.objects.count(), 1)
        self.assertEqual(self.greske, [])

    def test_istovremeni_zahtevi_upisuju_jedan_potez(self):
        stranica = self.otvori()
        self.zapocni(stranica)
        statusi = stranica.evaluate(
            """() => {
              const token = document.querySelector("input[name=csrfmiddlewaretoken]").value;
              const posalji = () => fetch("/api/potez/", {
                method: "POST",
                headers: {"Content-Type": "application/json", "X-CSRFToken": token},
                body: JSON.stringify({krug: 1, model: "opus", nivo: "high",
                                      kontekst: "taman", podela: "sam"}),
              }).then(odgovor => odgovor.status);
              return Promise.all([posalji(), posalji(), posalji(), posalji()]);
            }"""
        )
        self.assertEqual(sorted(statusi), [200, 409, 409, 409])
        self.assertEqual(Potez.objects.count(), 1)

    def test_sukob_stanja_ucitava_tekuci_krug(self):
        stranica = self.otvori()
        self.zapocni(stranica)
        partija = Partija.objects.latest("pk")
        izbori = POTEZI[0]
        Potez.objects.create(partija=partija, krug=1, **izbori._asdict())
        self.izaberi(stranica, izbori)
        stranica.locator("#potvrdi").click()
        expect(stranica.locator("#broj-kruga")).to_have_text("2")
        expect(stranica.locator("#istorija li")).to_have_count(1)

    def test_telefon_375(self):
        stranica = self.otvori(TELEFON)
        stranica.goto(self.live_server_url)
        self.proveri_sirinu(stranica, TELEFON["width"])
        self.zapocni(stranica)

        for krug, izbori in enumerate(POTEZI, start=1):
            self.proveri_sirinu(stranica, TELEFON["width"])
            for oznaka in stranica.locator("label.izbor").all():
                okvir = oznaka.bounding_box()
                self.assertGreaterEqual(okvir["height"], 44)
                self.assertGreaterEqual(okvir["x"], 0)
                self.assertLessEqual(okvir["x"] + okvir["width"], TELEFON["width"])
            self.odigraj(stranica, krug, izbori)

        self.proveri_sirinu(stranica, TELEFON["width"])
        stranica.locator("#pogledaj-rezultat").click()
        expect(stranica.locator("#poeni")).to_be_visible()
        self.proveri_sirinu(stranica, TELEFON["width"])
        self.assertEqual(self.greske, [])
