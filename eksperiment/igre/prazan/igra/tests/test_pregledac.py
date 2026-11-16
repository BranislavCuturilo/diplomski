import os
import re

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.utils import timezone, translation
from playwright.sync_api import expect, sync_playwright

from igra import parametri as p
from igra import pravila
from igra.models import Partija, Potez, Rezultat
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
# Broji tonove koje stranica pusti kroz Web Audio; zvuk se ne snima, samo se broje pozivi.
BROJAC_TONOVA = """
window.__tonovi = 0;
const pokreni = OscillatorNode.prototype.start;
OscillatorNode.prototype.start = function () {
  window.__tonovi += 1;
  return pokreni.apply(this, arguments);
};
"""
TONOVA_GOTOVO = 3
TONOVA_DORADA = 2


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

    def zavrsi_u_bazi(self, stranica):
        self.zapocni(stranica)
        partija = Partija.objects.latest("pk")
        for krug, izbori in enumerate(POTEZI, start=1):
            Potez.objects.create(partija=partija, krug=krug, **izbori._asdict())
        stranica.goto(self.live_server_url + "/kraj/")

    def test_cuvanje_rezultata_i_rang_lista(self):
        stranica = self.otvori()
        self.zavrsi_u_bazi(stranica)
        stranica.locator("#ime").fill("Тест играч")
        stranica.locator("#sacuvaj").dblclick()

        istaknut = stranica.locator(".rang-istaknut")
        expect(istaknut.locator(".rang-ime")).to_have_text("Тест играч")
        poeni = pravila.konacni_rezultat(SEME, POTEZI).poeni
        expect(istaknut.locator(".rang-poeni strong")).to_have_text(str(poeni))
        self.assertEqual(Rezultat.objects.count(), 1)
        self.assertEqual(self.greske, [])

    def test_rang_lista_na_telefonu(self):
        sada = timezone.now()
        for i in range(12):
            partija = Partija.objects.create(seme="x")
            ime = "Ш" * 30 if i % 2 else f"Играч {i}"
            Rezultat.objects.create(partija=partija, ime=ime, poeni=100 - i * 7, ocena="солидан", sacuvan=sada)

        stranica = self.otvori(TELEFON)
        stranica.goto(self.live_server_url)
        expect(stranica.locator(".rang-red")).to_have_count(10)
        self.proveri_sirinu(stranica, TELEFON["width"])

        self.zavrsi_u_bazi(stranica)
        expect(stranica.locator("#ime")).to_be_visible()
        self.proveri_sirinu(stranica, TELEFON["width"])
        stranica.locator("#ime").fill("Ж" * 30)
        stranica.locator("#sacuvaj").click()
        expect(stranica.locator(".rang-istaknut")).to_be_visible()
        self.proveri_sirinu(stranica, TELEFON["width"])
        self.assertEqual(self.greske, [])

    def test_deljenje_rezultata(self):
        stranica = self.otvori(TELEFON)
        self.zavrsi_u_bazi(stranica)
        self.proveri_sirinu(stranica, TELEFON["width"])
        adresa = stranica.locator("#link-deljenja").input_value()
        self.assertRegex(adresa, r"^http://[^/]+/partija/[A-Za-z0-9_-]{20,}/$")

        stranica.locator("#kopiraj-link").click()
        expect(stranica.locator("#poruka-kopiranja")).not_to_be_empty()

        # Drugi igrac, sa svojim kolacicima, otvara link na telefonu.
        drugi = self.otvori(TELEFON)
        drugi.goto(adresa)
        rezultat = pravila.konacni_rezultat(SEME, POTEZI)
        expect(drugi.locator("#poeni")).to_have_text(str(rezultat.poeni))
        expect(drugi.locator("#ocena")).to_have_text(rezultat.ocena)
        expect(drugi.locator("form")).to_have_count(0)
        self.proveri_sirinu(drugi, TELEFON["width"])

        drugi.locator("#igraj-i-ti").click()
        expect(drugi.get_by_role("button", name="Нова игра")).to_be_visible()
        self.assertEqual(self.greske, [])

    def snimi(self, stranica, naziv):
        # Snimci samo na zahtev (SNIMCI_DIR), za pregled izgleda; test ih ne proverava.
        if os.environ.get("SNIMCI_DIR"):
            stranica.screenshot(path=os.path.join(os.environ["SNIMCI_DIR"], naziv), full_page=True)

    def test_moderator_brise_rezultat_i_link_na_telefonu(self):
        from igra import moderacija

        moderacija.dodaj_moderatora(None, "mira", "Dirigent-palica-42", "Dirigent-palica-42")
        igrac = self.otvori(TELEFON)
        self.zavrsi_u_bazi(igrac)
        igrac.locator("#ime").fill("Ж" * 30)
        igrac.locator("#sacuvaj").click()
        expect(igrac.locator(".rang-istaknut")).to_be_visible()

        mod = self.otvori(TELEFON)
        mod.goto(self.live_server_url + "/moderator/")
        expect(mod.locator("#forma-prijave")).to_be_visible()
        self.snimi(mod, "moderator-1-prijava.png")
        mod.locator("#ime").fill("mira")
        mod.locator("#lozinka").fill("Dirigent-palica-42")
        mod.locator("#prijavi-se").click()
        expect(mod.locator("#prijavljen")).to_have_text("mira")
        expect(mod.locator("#rezultati .rang-red")).to_have_count(1)
        self.proveri_sirinu(mod, TELEFON["width"])
        self.snimi(mod, "moderator-2-rezultati.png")

        mod.get_by_role("link", name="Обриши резултат").click()
        expect(mod.locator("#potvrda")).to_contain_text("Ж" * 30)
        self.proveri_sirinu(mod, TELEFON["width"])
        self.snimi(mod, "moderator-3-potvrda.png")
        mod.locator("#obrisi").click()
        expect(mod.locator("#poruka")).to_be_visible()
        expect(mod.locator("#rezultati .rang-red")).to_have_count(0)

        mod.get_by_role("link", name="Линкови").click()
        mod.get_by_role("link", name="Обриши линк").click()
        mod.locator("#obrisi").click()
        expect(mod.locator("#poruka")).to_be_visible()
        self.snimi(mod, "moderator-4-linkovi.png")

        mod.get_by_role("link", name="Дневник").click()
        expect(mod.locator(".dnevnik-red")).to_have_count(3)
        expect(mod.locator(".dnevnik-red").first).to_contain_text("mira")
        self.proveri_sirinu(mod, TELEFON["width"])
        self.snimi(mod, "moderator-5-dnevnik.png")

        mod.get_by_role("link", name="Модератори").click()
        self.proveri_sirinu(mod, TELEFON["width"])
        self.snimi(mod, "moderator-6-nalozi.png")
        mod.locator("#odjava").click()
        expect(mod.get_by_role("button", name="Нова игра")).to_be_visible()

        igrac.goto(self.live_server_url + "/kraj/")
        expect(igrac.locator("#rezultat-uklonjen")).to_be_visible()
        expect(igrac.locator("#link-uklonjen")).to_be_visible()
        self.proveri_sirinu(igrac, TELEFON["width"])
        self.snimi(igrac, "moderator-7-igrac.png")
        self.assertEqual(self.greske, [])

    def test_igrac_prijavljuje_ime_a_moderator_odlucuje_na_telefonu(self):
        from igra import moderacija

        moderacija.dodaj_moderatora(None, "mira", "Dirigent-palica-42", "Dirigent-palica-42")
        sada = timezone.now()
        for ime, poeni in (("Ж" * 30, 90), ("Пристојно име", 80)):
            partija = Partija.objects.create(seme="x")
            Rezultat.objects.create(partija=partija, ime=ime, poeni=poeni, ocena="солидан", sacuvan=sada)

        igrac = self.otvori(TELEFON)
        igrac.goto(self.live_server_url)
        expect(igrac.locator(".rang-prijava")).to_have_count(2)
        for zastavica in igrac.locator(".rang-prijava").all():
            okvir = zastavica.bounding_box()
            self.assertGreaterEqual(okvir["width"], 44)
            self.assertGreaterEqual(okvir["height"], 44)
            self.assertLessEqual(okvir["x"] + okvir["width"], TELEFON["width"])
        self.proveri_sirinu(igrac, TELEFON["width"])
        self.snimi(igrac, "prijava-1-rang-lista.png")

        # Igrac prijavljuje oba imena, svako uz potvrdu; do odluke moderatora oba ostaju na listi.
        for redni_broj in (0, 1):
            igrac.locator(".rang-prijava").nth(redni_broj).click()
            expect(igrac.locator("#prijavi")).to_be_visible()
            self.proveri_sirinu(igrac, TELEFON["width"])
            if redni_broj == 0:
                expect(igrac.locator("#prijavljeno-ime")).to_have_text("Ж" * 30)
                self.snimi(igrac, "prijava-2-potvrda.png")
            igrac.locator("#prijavi").click()
            expect(igrac.locator("#ime-prijavljeno")).to_be_visible()
            self.proveri_sirinu(igrac, TELEFON["width"])
            if redni_broj == 0:
                self.snimi(igrac, "prijava-3-prijavljeno.png")
            igrac.locator("#nazad-na-listu").click()
            expect(igrac.locator(".rang-red")).to_have_count(2)

        mod = self.otvori(TELEFON)
        mod.goto(self.live_server_url + "/moderator/")
        mod.locator("#ime").fill("mira")
        mod.locator("#lozinka").fill("Dirigent-palica-42")
        mod.locator("#prijavi-se").click()
        expect(mod.locator("#broj-prijava")).to_have_text("2")
        self.proveri_sirinu(mod, TELEFON["width"])
        mod.get_by_role("link", name="Пријаве").click()
        redovi = mod.locator("#prijavljena-imena .rang-red")
        expect(redovi).to_have_count(2)
        self.proveri_sirinu(mod, TELEFON["width"])
        self.snimi(mod, "prijava-4-spisak.png")

        # Prvo ime moderator brise (uz potvrdu), drugo zadrzava.
        expect(redovi.first).to_contain_text("Ж" * 30)
        redovi.first.get_by_role("link", name="Обриши резултат").click()
        expect(mod.locator("#potvrda")).to_contain_text("Ж" * 30)
        self.proveri_sirinu(mod, TELEFON["width"])
        mod.locator("#obrisi").click()
        expect(mod.locator("#poruka")).to_have_text("Резултат је обрисан.")
        expect(redovi).to_have_count(1)
        mod.get_by_role("button", name="Задржи").click()
        expect(mod.locator("#poruka")).to_have_text("Резултат је задржан.")
        expect(redovi).to_have_count(0)
        expect(mod.locator("#broj-prijava")).to_have_count(0)
        self.snimi(mod, "prijava-5-prazan-spisak.png")

        igrac.reload()
        expect(igrac.locator(".rang-ime")).to_have_text(["Пристојно име"])
        igrac.locator(".rang-prijava").click()
        expect(igrac.locator("#ime-pregledano")).to_be_visible()
        expect(igrac.locator("form")).to_have_count(0)
        self.proveri_sirinu(igrac, TELEFON["width"])
        self.snimi(igrac, "prijava-6-pregledano.png")
        self.assertEqual(self.greske, [])

    def test_cela_igra_na_engleskom(self):
        stranica = self.otvori(TELEFON)
        stranica.goto(self.live_server_url)
        stranica.locator("#jezik-en").click()
        expect(stranica.locator("html")).to_have_attribute("lang", "en")
        stranica.get_by_role("button", name="New game").click()
        expect(stranica.locator("#broj-kruga")).to_have_text("1")
        partija = Partija.objects.latest("pk")
        partija.seme = SEME
        partija.save()

        stanje = pravila.vidljivo_stanje(SEME, POTEZI)
        with translation.override("en"):
            ocekivani_statusi = [translation.gettext(k.status) for k in stanje.krugovi]
        for krug, izbori in enumerate(POTEZI, start=1):
            self.proveri_sirinu(stranica, TELEFON["width"])
            self.odigraj(stranica, krug, izbori)
            expect(stranica.locator("#poslednji-status")).to_have_text(ocekivani_statusi[krug - 1])
        expect(stranica.locator("#istorija li").first).to_contain_text(" min")
        expect(stranica.locator("#istorija li.ishod-gotovo")).to_have_count(ocekivani_statusi.count("done"))

        # Promena jezika usred zavrsnog ekrana ne menja partiju.
        stranica.locator("#pogledaj-rezultat").click()
        expect(stranica.locator(".naslov-kraja")).to_have_text("Final check")
        stranica.locator("#jezik-sr").click()
        expect(stranica.locator(".naslov-kraja")).to_have_text("Завршна провера")
        stranica.locator("#jezik-en").click()
        expect(stranica.locator("#poeni")).to_have_text(str(pravila.konacni_rezultat(SEME, POTEZI).poeni))
        stranica.locator("#kopiraj-link").click()
        expect(stranica.locator("#poruka-kopiranja")).to_have_text(re.compile(r"^Link (copied|selected, copy it)\.$"))
        self.proveri_sirinu(stranica, TELEFON["width"])
        self.assertNotRegex(stranica.locator("body").inner_text(), r"[Ѐ-ӿ]")
        self.assertEqual(self.greske, [])

    def test_zvuk_ishoda_kruga(self):
        stranica = self.otvori()
        stranica.context.add_init_script(BROJAC_TONOVA)
        self.zapocni(stranica)
        zvuk = stranica.locator("#zvuk")
        expect(zvuk).to_be_visible()
        expect(zvuk).to_have_attribute("aria-pressed", "false")
        self.odigraj(stranica, 1, POTEZI[0])
        self.assertEqual(stranica.evaluate("window.__tonovi"), 0, "zvuk je podrazumevano iskljucen")

        zvuk.click()
        expect(zvuk).to_have_attribute("aria-pressed", "true")
        self.assertEqual(stranica.evaluate("window.__tonovi"), TONOVA_GOTOVO, "potvrda pri ukljucivanju")

        # Melodija zavisi samo od vidljivog statusa: tiha greska zvuci kao uspeh.
        stanje = pravila.vidljivo_stanje(SEME, POTEZI)
        for krug in range(2, 5):
            stranica.evaluate("window.__tonovi = 0")
            self.odigraj(stranica, krug, POTEZI[krug - 1])
            gotovo = stanje.krugovi[krug - 1].status == p.STATUS_GOTOVO
            self.assertEqual(stranica.evaluate("window.__tonovi"), TONOVA_GOTOVO if gotovo else TONOVA_DORADA, krug)

        stranica.reload()
        expect(zvuk).to_have_attribute("aria-pressed", "true")
        zvuk.click()
        expect(zvuk).to_have_attribute("aria-pressed", "false")
        stranica.reload()
        expect(zvuk).to_have_attribute("aria-pressed", "false")
        stranica.evaluate("window.__tonovi = 0")
        self.odigraj(stranica, 5, POTEZI[4])
        self.assertEqual(stranica.evaluate("window.__tonovi"), 0)
        self.assertEqual(self.greske, [])

    def test_kako_se_igra_i_moje_partije_na_telefonu(self):
        stranica = self.otvori(TELEFON)
        stranica.goto(self.live_server_url)
        expect(stranica.locator("#moje-partije")).to_have_count(0)
        stranica.locator("#kako-se-igra").click()
        expect(stranica.locator("h1")).to_have_text("Како се игра")
        expect(stranica.locator("#primer-gotovo")).to_contain_text("1,404 $ · 6 мин")
        self.proveri_sirinu(stranica, TELEFON["width"])
        self.snimi(stranica, "pravila.png")
        stranica.locator("#nazad").click()
        expect(stranica.get_by_role("button", name="Нова игра")).to_be_visible()

        self.zapocni(stranica)
        for krug, izbori in enumerate(POTEZI, start=1):
            self.odigraj(stranica, krug, izbori)
        stranica.goto(self.live_server_url)
        red = stranica.locator("#moje-partije .rang-red")
        expect(red).to_have_count(1)
        poeni = pravila.konacni_rezultat(SEME, POTEZI).poeni
        expect(red.locator(".rang-poeni strong")).to_have_text(str(poeni))
        self.proveri_sirinu(stranica, TELEFON["width"])
        self.snimi(stranica, "moje-partije.png")
        red.click()
        expect(stranica.locator("#podeljeno")).to_be_visible()
        expect(stranica.locator("#poeni")).to_have_text(str(poeni))
        self.assertEqual(self.greske, [])

    def test_statistika_na_telefonu(self):
        from igra import moderacija

        moderacija.dodaj_moderatora(None, "mira", "Dirigent-palica-42", "Dirigent-palica-42")
        Partija.objects.create(seme="x", zavrsena=timezone.now(), poeni=77)
        mod = self.otvori(TELEFON)
        mod.goto(self.live_server_url + "/moderator/")
        mod.locator("#ime").fill("mira")
        mod.locator("#lozinka").fill("Dirigent-palica-42")
        mod.locator("#prijavi-se").click()
        mod.get_by_role("link", name="Статистика").click()
        redovi = mod.locator(".dan-statistike")
        expect(redovi).to_have_count(p.DANA_STATISTIKE)
        expect(redovi.first).to_contain_text("77,0")
        expect(mod.locator("#ukupno-statistike")).to_contain_text("1")
        self.proveri_sirinu(mod, TELEFON["width"])
        self.snimi(mod, "statistika.png")
        self.assertEqual(self.greske, [])

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
