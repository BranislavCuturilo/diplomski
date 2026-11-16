"""Tok kroz pravi pregledac. Zamke sync API-ja i live servera: plan.md, odeljak 7."""

import datetime
import itertools
import os
import re
from unittest import mock

from django.conf import settings
from django.contrib.sessions.backends.db import SessionStore
from django.core.exceptions import PermissionDenied
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from django.utils import timezone
from playwright.sync_api import expect, sync_playwright

from igra import brisanje, motor, nalozi, parametri, views
from igra.models import DeljeniRezultat, NepodobnoIme, PrijavaImena, Rezultat, ZapisDnevnika

from .test_motor import (
    NAPOMENA_SR,
    OCENE_SR,
    OPUS_HIGH,
    SEME_JEDNA_TIHA,
    ZADACI_SR,
    bez_verzije,
    izbori,
    ishodi,
    nadji_seme,
    odigraj_celu,
    po_tezini,
    sve_opus,
)
# Redove test nit upisuje samo pre goto ili posle zavrsenog cekanja odgovora.
from .test_prikazi import (
    BRZI_HES,
    ISTA_LOZINKA_EN,
    ISTA_LOZINKA_SR,
    LOZINKA,
    LOZINKA2,
    LOZINKA3,
    TEKST_403,
    istekao_red,
    napravi_moderatora,
    obrisi_brojace,
    oznaka_reda,
    seme_uspesnog_osmog,
    skriveni_kljucevi,
    stanje_pred_osmi,
    upisi_deljeno,
    upisi_prijavu,
    upisi_red,
)

ASYNC_UNSAFE = "DJANGO_ALLOW_ASYNC_UNSAFE"
ZAVRSEN_TEKST = "Игра је завршена"
PITANJE_NOVA = "Започети нову игру? Текућа партија се губи."
NAPOMENA = NAPOMENA_SR
# Plan 12.9: na srpskoj strani jos i dugme "English" (naziv drugog jezika, lang="en").
DOZVOLJENA_LATINICA = {"Haiku", "Sonnet", "Opus", "low", "high", "max", "CSS", "CRUD", "English"}
# Playwright Chromium bez locale salje en-US (plan 12.9): postojeci testovi traze srpski izricito.
SRPSKI = "sr-RS"
ENGLESKI = "en-US"
KRUG_TEKST = {"sr": "Круг {} од 8", "en": "Round {} of 8"}
ZAVRSEN = {"sr": "Игра је завршена", "en": "Game over"}
# Engleski tekst iz kataloga (plan 12.8, predlog za klijenta); prepisan, ne cita se iz .po.
OCENE_EN = {"odlican": "excellent orchestrator", "solidan": "solid", "skup": "costly lesson", "pozar": "disaster"}
OCENE_TEKST = {"sr": OCENE_SR, "en": OCENE_EN}
NAPOMENA_EN = (
    "Prices and thinking levels are real data; probabilities, penalties and points are made-up game parameters."
)
PITANJE_NOVA_EN = "Start a new game? The current game will be lost."
CIRILICA = re.compile(r"[\u0400-\u04FF]+")

TELEFON = (375, 812)
TABLET = (768, 1024)
RACUNAR = (1440, 900)

JS_PRELIVANJE = """() => {
  const sirina = document.documentElement.clientWidth;
  const van = [];
  for (const e of document.body.querySelectorAll('*')) {
    if (e.closest('template') || e.matches('.btn-check, script, style')) continue;
    const r = e.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    if (r.right > sirina + 0.5 || r.left < -0.5) van.push(e.tagName + '#' + e.id + '.' + e.className);
  }
  const odseceno = [];
  for (const e of document.querySelectorAll('label.btn, button, h1, h2, h3, dt, dd, li, p, legend')) {
    const r = e.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    if (e.scrollWidth > e.clientWidth + 1) odseceno.push(e.tagName + ':' + e.textContent.trim().slice(0, 30));
  }
  return {
    skrol: document.documentElement.scrollWidth,
    sirina: sirina,
    van: van,
    odseceno: odseceno,
  };
}"""


# Odsustvo skrola ne moze da se saceka, moze samo da se posmatra: kadrovi bez promene pozicije.
JS_SKROL_MIRAN = """() => new Promise((gotovo) => {
  let poslednji = window.scrollY;
  let mirnih = 0;
  function korak() {
    mirnih = window.scrollY === poslednji ? mirnih + 1 : 0;
    poslednji = window.scrollY;
    if (mirnih >= 30) { gotovo(poslednji); } else { requestAnimationFrame(korak); }
  }
  requestAnimationFrame(korak);
})"""


def zarez(vrednost, decimale):
    return f"{vrednost:.{decimale}f}".replace(".", ",")


def najduza_partija(krug):
    """Pali svih pet lekcija, pa zavrsni ekran ima najvise teksta."""
    return izbori("opus" if krug == 1 else "haiku", "max", "sve", "pedeset")


def seme_najduze_partije():
    return nadji_seme(najduza_partija, lambda i: i.count(motor.TIHI_NEUSPEH) == 3)


OCENE = ("odlican", "solidan", "skup", "pozar")
USKI_EKRANI = ((320, 640), TELEFON)

# Desna i leva ivica teksta ocene (ne kutije elementa: kutija se skuplja, tekst izlazi iz nje).
JS_OCENA_U_KARTICI = """() => {
  const tekst = document.querySelector('#zavrsni [data-mesto="ocena"]');
  const opseg = document.createRange();
  opseg.selectNodeContents(tekst);
  const redovi = Array.from(opseg.getClientRects());
  const kartica = document.querySelector('#zavrsni .hero').getBoundingClientRect();
  return {
    tekst: tekst.textContent,
    redova: redovi.length,
    levo: Math.min(...redovi.map((r) => r.left)),
    desno: Math.max(...redovi.map((r) => r.right)),
    kartica_levo: kartica.left,
    kartica_desno: kartica.right,
  };
}"""


def seme_za_ocenu(strategija, ocena, granica=5000):
    """Prvo seme iz niza 0, 1, 2... cija cela partija zavrsava datom ocenom."""
    for i in range(granica):
        if odigraj_celu(str(i), strategija)["rezultat"]["ocena"] == ocena:
            return str(i)
    raise AssertionError(f"nema semena za ocenu {ocena}")


class Zapis:
    """Sve sto pregledac prijavi kao gresku, i svi odgovori servera."""

    def __init__(self, strana):
        self.konzola = []
        self.izuzeci = []
        self.neuspeli = []
        self.odgovori = []
        self.zahtevi_poteza = []
        self.zahtevi_cuvanja = []
        self.zahtevi_deljenja = []
        strana.on("console", self._konzola)
        strana.on("pageerror", lambda greska: self.izuzeci.append(str(greska)))
        strana.on("requestfailed", lambda z: self.neuspeli.append(f"{z.method} {z.url}"))
        strana.on("response", lambda odgovor: self.odgovori.append(odgovor))
        strana.on("request", self._zahtev)

    def _konzola(self, poruka):
        if poruka.type in ("error", "warning"):
            self.konzola.append(f"{poruka.type}: {poruka.text}")

    def _zahtev(self, zahtev):
        if zahtev.method == "POST" and zahtev.url.endswith("/potez/"):
            self.zahtevi_poteza.append(zahtev)
        if zahtev.method == "POST" and zahtev.url.endswith("/sacuvaj/"):
            self.zahtevi_cuvanja.append(zahtev)
        if zahtev.method == "POST" and zahtev.url.endswith("/podeli/"):
            self.zahtevi_deljenja.append(zahtev)

    def losi_odgovori(self):
        return [f"{o.status} {o.url}" for o in self.odgovori if o.status >= 400]


class OsnovaToka(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        stara = os.environ.get(ASYNC_UNSAFE)
        os.environ[ASYNC_UNSAFE] = "true"

        def vrati():
            if stara is None:
                os.environ.pop(ASYNC_UNSAFE, None)
            else:
                os.environ[ASYNC_UNSAFE] = stara

        cls.addClassCleanup(vrati)
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.pregledac = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.pregledac.close()
        cls.playwright.stop()
        super().tearDownClass()

    def novi_kontekst(self, dimenzije=RACUNAR, dozvole=None, skripta=None, jezik=SRPSKI):
        sirina, visina = dimenzije
        kontekst = self.pregledac.new_context(
            viewport={"width": sirina, "height": visina}, permissions=dozvole or [], locale=jezik
        )
        self.addCleanup(kontekst.close)
        if skripta is not None:
            kontekst.add_init_script(skripta)
        return kontekst

    def otvori(self, seme, dimenzije=RACUNAR, stanje=None, dozvole=None, skripta=None, jezik=SRPSKI):
        # Test nit dira bazu samo pre prvog goto.
        sesija = SessionStore()
        sesija["igra"] = stanje if stanje is not None else motor.nova_igra(seme)
        sesija.create()
        kontekst = self.novi_kontekst(dimenzije, dozvole, skripta, jezik)
        kontekst.add_cookies(
            [
                {
                    "name": settings.SESSION_COOKIE_NAME,
                    "value": sesija.session_key,
                    "url": self.live_server_url,
                }
            ]
        )
        strana = kontekst.new_page()
        zapis = Zapis(strana)
        strana.goto(self.live_server_url + "/")
        expect(strana.locator("html")).to_have_attribute("lang", jezik[:2])
        if stanje is not None and stanje["zavrsena"]:
            expect(strana.locator("#zavrsni")).to_be_visible()
        else:
            expect(strana.locator("#krug")).to_have_text(KRUG_TEKST[jezik[:2]].format(1))
        return strana, zapis

    def otvori_zavrseno(self, seme, dimenzije=RACUNAR, strategija=sve_opus, dozvole=None, skripta=None,
                        jezik=SRPSKI):
        """Zavrsena partija upisana u sesiju pre goto, bez 8 klikova (plan 10.7)."""
        return self.otvori(
            seme, dimenzije, stanje=odigraj_celu(seme, strategija), dozvole=dozvole, skripta=skripta,
            jezik=jezik,
        )

    def jezik(self, strana):
        """Jezik strane iz <html lang>, kako ga je server izabrao."""
        return strana.evaluate("() => document.documentElement.lang")

    def podeli_i_cekaj(self, strana):
        with strana.expect_response(
            lambda o: o.url.endswith("/podeli/") and o.request.method == "POST"
        ) as informacija:
            strana.locator("#deli-dugme").click()
        return informacija.value

    def sacuvaj_i_cekaj(self, strana, ime):
        strana.locator("#rang-ime").fill(ime)
        expect(strana.locator("#rang-sacuvaj")).to_be_enabled()
        with strana.expect_response(
            lambda o: o.url.endswith("/sacuvaj/") and o.request.method == "POST"
        ) as informacija:
            strana.locator("#rang-sacuvaj").click()
        return informacija.value

    def izaberi(self, strana, izbor):
        for ime, vrednost in izbor.items():
            strana.locator(f'label[for="{ime}-{vrednost}"]').click()

    def potvrdi_i_cekaj(self, strana):
        with strana.expect_response(
            lambda o: o.url.endswith("/potez/") and o.request.method == "POST"
        ) as informacija:
            strana.locator("#potvrdi").click()
        return informacija.value

    def odigraj_krug(self, strana, krug, izbor):
        self.izaberi(strana, izbor)
        expect(strana.locator("#potvrdi")).to_be_enabled()
        odgovor = self.potvrdi_i_cekaj(strana)
        self.assertEqual(odgovor.status, 200)
        if krug < 8:
            expect(strana.locator("#krug")).to_have_text(KRUG_TEKST[self.jezik(strana)].format(krug + 1))
        else:
            expect(strana.locator("#zavrsni")).to_be_visible()
        return odgovor

    def odigraj_celu_u_pregledacu(self, strana, strategija):
        for krug in range(1, 9):
            self.odigraj_krug(strana, krug, strategija(krug))

    def proveri_cisto(self, zapis):
        self.assertEqual(zapis.konzola, [])
        self.assertEqual(zapis.izuzeci, [])
        self.assertEqual(zapis.neuspeli, [])
        self.assertEqual(zapis.losi_odgovori(), [])

    def proveri_bez_prelivanja(self, strana, oznaka):
        mere = strana.evaluate(JS_PRELIVANJE)
        with self.subTest(ekran=oznaka):
            self.assertLessEqual(mere["skrol"], mere["sirina"], mere)
            self.assertEqual(mere["van"], [])
            self.assertEqual(mere["odseceno"], [])


class TokTests(OsnovaToka):
    def test_cela_igra_do_zavrsnog_ekrana(self):
        seme = nadji_seme(
            po_tezini,
            lambda i: motor.TIHI_NEUSPEH in i and motor.DORADA in i,
        )
        referenca = odigraj_celu(seme, po_tezini)
        strana, zapis = self.otvori(seme)

        rezultat = strana.locator("#rezultat")
        expect(rezultat).to_be_hidden()
        expect(strana.locator("#zavrsni")).to_be_hidden()
        expect(strana.locator("#zadatak")).to_have_text("Превод почетне стране")

        for krug in range(1, 9):
            with self.subTest(krug=krug):
                self.odigraj_krug(strana, krug, po_tezini(krug))
                red = referenca["istorija"][krug - 1]
                expect(rezultat).to_be_visible()
                expect(rezultat.locator('[data-mesto="zadatak"]')).to_contain_text(f"Круг {krug}:")
                expect(rezultat.locator('[data-mesto="cena"]')).to_have_text(
                    zarez(red["cena"], 3) + " $"
                )
                expect(rezultat.locator('[data-mesto="minuti"]')).to_have_text(
                    zarez(red["minuti"], 1) + " мин"
                )
                ocekivan_status = (
                    "враћено на дораду" if red["ishod"] == motor.DORADA else "готово"
                )
                expect(rezultat.locator('[data-mesto="status"]')).to_have_text(ocekivan_status)
                self.assertEqual(
                    "alert-warning" in rezultat.get_attribute("class"),
                    red["ishod"] == motor.DORADA,
                )

        kraj = referenca["rezultat"]
        zavrsni = strana.locator("#zavrsni")
        expect(strana.locator("#kontrole")).to_be_hidden()
        expect(strana.locator("#krug")).to_have_text(ZAVRSEN_TEKST)
        expect(zavrsni.locator('[data-mesto="poeni"]')).to_have_text(str(kraj["poeni"]))
        expect(zavrsni.locator('[data-mesto="ocena"]')).to_have_text(OCENE_SR[kraj["ocena"]])
        expect(zavrsni.locator('[data-mesto="cena"]')).to_have_text(
            zarez(kraj["ukupna_cena"], 2) + " $"
        )
        expect(zavrsni.locator('[data-mesto="minuti"]')).to_have_text(
            zarez(kraj["ukupni_minuti"], 1) + " мин"
        )
        expect(zavrsni.locator('[data-mesto="napomena"]')).to_have_text(NAPOMENA)
        tihe = zavrsni.locator('[data-mesto="tihe"] li')
        self.assertGreaterEqual(len(kraj["tihe_greske"]), 1)
        expect(tihe).to_have_count(len(kraj["tihe_greske"]))
        expect(tihe.first).to_contain_text(ZADACI_SR[kraj["tihe_greske"][0]["zadatak"]])
        lekcije = zavrsni.locator('[data-mesto="lekcije"] li')
        expect(lekcije).to_have_count(len(kraj["lekcije"]))
        expect(lekcije.first).to_contain_text("(одељак " + kraj["lekcije"][0]["odeljak"] + ")")
        expect(strana.locator("#nova-forma button")).to_be_visible()
        self.proveri_cisto(zapis)

    def test_igra_bez_tihih_gresaka_ispisuje_poruku(self):
        seme = nadji_seme(sve_opus, lambda i: i == [motor.USPEH] * 8)
        strana, zapis = self.otvori(seme)
        self.odigraj_celu_u_pregledacu(strana, sve_opus)
        zavrsni = strana.locator("#zavrsni")
        expect(zavrsni.locator('[data-mesto="poeni"]')).to_have_text("100")
        expect(zavrsni.locator('[data-mesto="nema-tihih"]')).to_be_visible()
        expect(zavrsni.locator('[data-mesto="tihe"]')).to_be_hidden()
        expect(zavrsni.locator('[data-mesto="budzet-prekoracen"]')).to_be_hidden()
        expect(zavrsni.locator('[data-mesto="rok-prekoracen"]')).to_be_hidden()
        self.proveri_cisto(zapis)

    def test_dugme_i_procena_prate_izbor(self):
        strana, zapis = self.otvori("seme-procena")
        potvrdi = strana.locator("#potvrdi")
        procena = strana.locator("#procena")
        expect(potvrdi).to_be_disabled()
        expect(procena).to_have_text("Изаберите све четири опције да видите процену.")

        for ime, vrednost in (("model", "opus"), ("nivo", "high"), ("kontekst", "taman")):
            strana.locator(f'label[for="{ime}-{vrednost}"]').click()
            expect(potvrdi).to_be_disabled()
        strana.locator('label[for="podela-sam"]').click()
        expect(potvrdi).to_be_enabled()
        expect(procena).to_have_text("Процена: цена 0,720 $, 5,0 мин.")

        strana.locator('label[for="model-haiku"]').click()
        expect(procena).to_have_text("Процена: цена 0,018 $, 2,5 мин.")
        self.proveri_cisto(zapis)

    def test_izbori_se_brisu_kad_se_promeni_krug(self):
        strana, zapis = self.otvori("seme-brisanje")
        self.odigraj_krug(strana, 1, OPUS_HIGH)
        self.assertEqual(strana.locator("input.btn-check:checked").count(), 0)
        expect(strana.locator("#potvrdi")).to_be_disabled()
        self.proveri_cisto(zapis)

    def test_osvezavanje_cuva_partiju(self):
        strana, zapis = self.otvori("seme-osvezi")
        self.odigraj_krug(strana, 1, OPUS_HIGH)
        strana.reload()
        expect(strana.locator("#krug")).to_have_text("Круг 2 од 8")
        expect(strana.locator("#zadatak")).to_have_text("Шаблон листе и форме")
        expect(strana.locator("#rezultat")).to_be_visible()
        self.proveri_cisto(zapis)

    def test_osvezavanje_zavrsene_igre(self):
        strana, zapis = self.otvori("seme-osvezi-kraj")
        self.odigraj_celu_u_pregledacu(strana, sve_opus)
        strana.reload()
        expect(strana.locator("#zavrsni")).to_be_visible()
        expect(strana.locator("#kontrole")).to_be_hidden()
        expect(strana.locator("#krug")).to_have_text(ZAVRSEN_TEKST)
        self.proveri_cisto(zapis)

    def test_mreza_i_dom_bez_skrivenog(self):
        # Seme je dugacak prepoznatljiv niz, da pretraga ne pogodi slucajno.
        seme = next(
            kandidat
            for kandidat in (f"tajno-seme-pregledac-x9q-{i}" for i in range(1000))
            if motor.TIHI_NEUSPEH in ishodi(odigraj_celu(kandidat, sve_opus))
        )
        strana, zapis = self.otvori(seme)
        kontekst = strana.context

        for krug in range(1, 9):
            with self.subTest(krug=krug):
                odgovor = self.odigraj_krug(strana, krug, OPUS_HIGH)
                self.assertNotIn(seme, odgovor.text())
                self.assertEqual(skriveni_kljucevi(odgovor.json(), krug == 8), set())
                dom = strana.content()
                self.assertNotIn(seme, dom)
                self.assertNotRegex(dom, r"\b(sansa|tezina|ishod|bonus)\b")
                self.assertNotRegex(dom.lower(), r"шанс|тежин")
                self.assertEqual({k["name"] for k in kontekst.cookies()}, {"sessionid", "csrftoken"})
                for kolacic in kontekst.cookies():
                    self.assertNotIn(seme, kolacic["value"])
                skladiste = strana.evaluate("() => localStorage.length + sessionStorage.length")
                self.assertEqual(skladiste, 0)

        self.assertEqual(len(zapis.zahtevi_poteza), 8)
        dokument = [o for o in zapis.odgovori if o.url == self.live_server_url + "/"]
        self.assertEqual(len(dokument), 1)
        self.assertNotIn(seme, dokument[0].text())

        # Deljenje: odgovor, DOM igre i deljena strana u novom kontekstu, bez semena i partije.
        partija = motor.oznaka_partije({"seme": seme})
        odgovor = self.podeli_i_cekaj(strana)
        self.assertEqual(odgovor.status, 200)
        self.assertEqual(set(odgovor.json()), {"url", "istice"})
        url = odgovor.json()["url"]
        token = url.rstrip("/").rsplit("/", 1)[1]
        expect(strana.locator("#deli-link")).to_have_value(url)
        for tajna in (seme, partija):
            self.assertNotIn(tajna, odgovor.text())
        # Link je samo u value polja: nije u HTML-u igre ni u kolacicima.
        self.assertNotIn(token, strana.content())
        for kolacic in kontekst.cookies():
            self.assertNotIn(token, kolacic["value"])

        gost = self.novi_kontekst()
        deljena = gost.new_page()
        zapis_gosta = Zapis(deljena)
        self.assertEqual(deljena.goto(url).status, 200)
        expect(deljena.locator("#zavrsni")).to_be_visible()
        dom = deljena.content()
        for tajna in (seme, partija):
            self.assertNotIn(tajna, dom)
            self.assertNotIn(tajna, zapis_gosta.odgovori[0].text())
        self.assertNotRegex(dom, r"\b(sansa|tezina|ishod|bonus)\b")
        self.assertNotRegex(dom.lower(), r"шанс|тежин")
        self.assertEqual(gost.cookies(), [])
        self.assertEqual(deljena.evaluate("() => localStorage.length + sessionStorage.length"), 0)
        self.proveri_cisto(zapis_gosta)

    def test_tih_neuspeh_na_ekranu_izgleda_kao_uspeh(self):
        seme = nadji_seme(
            sve_opus, lambda i: i[:5] == [motor.USPEH] * 4 + [motor.TIHI_NEUSPEH]
        )
        strana, zapis = self.otvori(seme)
        for krug in range(1, 6):
            self.odigraj_krug(strana, krug, OPUS_HIGH)
        rezultat = strana.locator("#rezultat")
        expect(rezultat.locator('[data-mesto="status"]')).to_have_text("готово")
        self.assertIn("alert-success", rezultat.get_attribute("class"))
        expect(rezultat.locator('[data-mesto="cena"]')).to_have_text("4,320 $")
        self.proveri_cisto(zapis)

    def test_dupli_klik_jedan_post(self):
        strana, zapis = self.otvori("seme-dupli")
        self.izaberi(strana, OPUS_HIGH)
        with strana.expect_response(lambda o: o.url.endswith("/potez/")) as informacija:
            strana.locator("#potvrdi").dblclick()
        self.assertEqual(informacija.value.status, 200)
        expect(strana.locator("#krug")).to_have_text("Круг 2 од 8")
        expect(strana.locator('#budzet [data-mesto="potroseno"]')).to_have_text("0,72 $")
        self.assertEqual(len(zapis.zahtevi_poteza), 1)
        self.proveri_cisto(zapis)

    def test_dupli_klik_zastita_u_skripti_bez_disabled(self):
        strana, zapis = self.otvori("seme-dupli-js")
        self.izaberi(strana, OPUS_HIGH)
        # Drugi klik stize dok je prvi zahtev u toku, i to preko skinutog `disabled`.
        with strana.expect_response(lambda o: o.url.endswith("/potez/")) as informacija:
            strana.evaluate(
                """() => {
                  const dugme = document.getElementById('potvrdi');
                  dugme.click();
                  dugme.disabled = false;
                  dugme.click();
                }"""
            )
        self.assertEqual(informacija.value.status, 200)
        expect(strana.locator("#krug")).to_have_text("Круг 2 од 8")
        self.assertEqual(len(zapis.zahtevi_poteza), 1)
        self.proveri_cisto(zapis)

    def test_stara_kartica_dobija_409_i_osvezava_stanje(self):
        strana, zapis = self.otvori("seme-kartica")
        druga = strana.context.new_page()
        druga.goto(self.live_server_url + "/")
        self.odigraj_krug(druga, 1, OPUS_HIGH)

        self.izaberi(strana, izbori("haiku"))
        odgovor = self.potvrdi_i_cekaj(strana)
        self.assertEqual(odgovor.status, 409)
        expect(strana.locator("#poruka")).to_have_text("Стање је освежено.")
        expect(strana.locator("#krug")).to_have_text("Круг 2 од 8")
        expect(strana.locator('#budzet [data-mesto="potroseno"]')).to_have_text("0,72 $")
        # Jedini dozvoljeni trag u konzoli: Chromium belezi svaki 4xx.
        self.assertEqual(len(zapis.konzola), 1)
        self.assertIn("409", zapis.konzola[0])
        self.assertEqual(zapis.izuzeci, [])

    def test_greske_servera_prikazuju_poruku(self):
        strana, zapis = self.otvori("seme-ruta")
        self.izaberi(strana, OPUS_HIGH)
        slucajevi = [
            (
                "400",
                lambda ruta: ruta.fulfill(
                    status=400,
                    content_type="application/json",
                    body='{"greska": "neispravan_zahtev"}',
                ),
                "Захтев није исправан. Освежите страну.",
            ),
            (
                "409 nema_igre",
                lambda ruta: ruta.fulfill(
                    status=409,
                    content_type="application/json",
                    body='{"greska": "nema_igre", "stanje": null}',
                ),
                "Партија више не постоји. Освежите страну за нову игру.",
            ),
            (
                "403 html",
                lambda ruta: ruta.fulfill(status=403, content_type="text/html", body="<h1>CSRF</h1>"),
                "Сервер није одговорио како треба. Покушајте поново.",
            ),
            (
                "500 html",
                lambda ruta: ruta.fulfill(status=500, content_type="text/html", body="<h1>x</h1>"),
                "Сервер није одговорио како треба. Покушајте поново.",
            ),
            (
                "200 nije json",
                lambda ruta: ruta.fulfill(status=200, content_type="text/html", body="<h1>x</h1>"),
                "Сервер није одговорио како треба. Покушајте поново.",
            ),
            (
                "mreza",
                lambda ruta: ruta.abort(),
                "Сервер није одговорио како треба. Покушајте поново.",
            ),
        ]
        poruka = strana.locator("#poruka")
        for ime, rukovalac, ocekivano in slucajevi:
            with self.subTest(ime=ime):
                strana.route("**/potez/", rukovalac)
                strana.locator("#potvrdi").click()
                expect(poruka).to_have_text(ocekivano)
                expect(strana.locator("#krug")).to_have_text("Круг 1 од 8")
                expect(strana.locator("#potvrdi")).to_be_enabled()
                self.assertEqual(strana.locator("input.btn-check:checked").count(), 4)
                strana.unroute("**/potez/")
        self.assertEqual(zapis.izuzeci, [])

        # Kontrola: posle ispravnog odgovora poruka nestaje.
        self.potvrdi_i_cekaj(strana)
        expect(strana.locator("#krug")).to_have_text("Круг 2 од 8")
        expect(poruka).to_be_hidden()

    def test_nova_usred_igre_potvrda(self):
        strana, zapis = self.otvori("seme-nova")
        self.odigraj_krug(strana, 1, OPUS_HIGH)
        poruke = []

        def odustani(dijalog):
            poruke.append(dijalog.message)
            dijalog.dismiss()

        strana.once("dialog", odustani)
        strana.locator("#nova-forma button").click()
        self.assertEqual(poruke, [PITANJE_NOVA])
        expect(strana.locator("#krug")).to_have_text("Круг 2 од 8")

        def prihvati(dijalog):
            poruke.append(dijalog.message)
            dijalog.accept()

        strana.once("dialog", prihvati)
        with strana.expect_navigation():
            strana.locator("#nova-forma button").click()
        self.assertEqual(poruke, [PITANJE_NOVA, PITANJE_NOVA])
        expect(strana.locator("#krug")).to_have_text("Круг 1 од 8")
        expect(strana.locator("#zadatak")).to_have_text("Превод почетне стране")
        expect(strana.locator("#rezultat")).to_be_hidden()
        self.proveri_cisto(zapis)

    def test_nova_posle_kraja_potvrda_dok_nije_sacuvano(self):
        # R4: zamenjuje test_nova_posle_kraja_bez_potvrde.
        strana, zapis = self.otvori("seme-nova-kraj")
        self.odigraj_celu_u_pregledacu(strana, sve_opus)
        poruke = []

        def odustani(dijalog):
            poruke.append(dijalog.message)
            dijalog.dismiss()

        # Oznaka na prozoru nestaje samo ako se strana ponovo ucita.
        strana.evaluate("() => { window.oznakaBezNavigacije = 1; }")
        strana.once("dialog", odustani)
        strana.locator("#nova-forma button").click()
        self.assertEqual(poruke, [PITANJE_NOVA])
        expect(strana.locator("#zavrsni")).to_be_visible()
        expect(strana.locator("#krug")).to_have_text(ZAVRSEN_TEKST)
        expect(strana.locator("#rang-forma")).to_be_visible()
        self.assertEqual(strana.evaluate("() => window.oznakaBezNavigacije"), 1)

        def prihvati(dijalog):
            poruke.append(dijalog.message)
            dijalog.accept()

        strana.once("dialog", prihvati)
        with strana.expect_navigation():
            strana.locator("#nova-forma button").click()
        self.assertEqual(poruke, [PITANJE_NOVA, PITANJE_NOVA])
        expect(strana.locator("#krug")).to_have_text("Круг 1 од 8")
        expect(strana.locator("#zavrsni")).to_be_hidden()
        expect(strana.locator("#kontrole")).to_be_visible()
        self.proveri_cisto(zapis)

    def test_nova_posle_cuvanja_bez_potvrde(self):
        strana, zapis = self.otvori_zavrseno("seme-nova-kraj-sacuvano")
        self.assertEqual(self.sacuvaj_i_cekaj(strana, "Пера").status, 200)
        expect(strana.locator("#rang-poruka")).to_have_text("Резултат је сачуван.")
        dijalozi = []

        def zabelezi(dijalog):
            dijalozi.append(dijalog.message)
            dijalog.dismiss()

        strana.on("dialog", zabelezi)
        with strana.expect_navigation():
            strana.locator("#nova-forma button").click()
        expect(strana.locator("#krug")).to_have_text("Круг 1 од 8")
        expect(strana.locator("#zavrsni")).to_be_hidden()
        expect(strana.locator("#kontrole")).to_be_visible()
        self.assertEqual(dijalozi, [])
        self.proveri_cisto(zapis)

    def test_konzola_cista(self):
        self.proveri_konzolu(SRPSKI)

    def test_konzola_cista_en(self):
        self.proveri_konzolu(ENGLESKI)

    def proveri_konzolu(self, jezik):
        strana, zapis = self.otvori(seme_najduze_partije(), jezik=jezik)
        self.odigraj_celu_u_pregledacu(strana, najduza_partija)
        expect(strana.locator("#zavrsni")).to_be_visible()
        self.proveri_cisto(zapis)
        # Kontrola: zapis zaista vidi saobracaj koji proverava.
        self.assertEqual(len(zapis.zahtevi_poteza), 8)
        self.assertGreaterEqual(len(zapis.odgovori), 11)

    def test_latinica_samo_u_nazivima(self):
        strana, zapis = self.otvori(seme_najduze_partije())
        # Plan 12.9: provera vazi za srpsku stranu, pa prvo jezik strane.
        self.assertEqual(self.jezik(strana), "sr")
        expect(strana.locator("#jezik-dugme")).to_have_text("English")
        reci = re.compile(r"[A-Za-z]+")

        def proveri(oznaka):
            tekst = strana.evaluate("() => document.body.innerText")
            self.assertGreater(len(tekst), 100)
            with self.subTest(ekran=oznaka):
                self.assertEqual(set(reci.findall(tekst)) - DOZVOLJENA_LATINICA, set())

        proveri("pocetak")
        for krug in range(1, 9):
            self.odigraj_krug(strana, krug, najduza_partija(krug))
            proveri(f"krug {krug}")
        odgovor = self.podeli_i_cekaj(strana)
        self.assertEqual(odgovor.status, 200)
        expect(strana.locator("#deli-blok")).to_be_visible()
        proveri("zavrsni sa blokom deljenja")
        self.proveri_cisto(zapis)

        # Deljena strana posle istog teksta zavrsnog ekrana.
        strana = self.novi_kontekst().new_page()
        zapis = Zapis(strana)
        self.assertEqual(strana.goto(odgovor.json()["url"]).status, 200)
        expect(strana.locator("#deljeno-datum")).not_to_be_empty()
        self.assertEqual(self.jezik(strana), "sr")
        proveri("deljena strana")
        self.proveri_cisto(zapis)

    def proveri_sirinu(self, dimenzije, jezik=SRPSKI):
        strana, zapis = self.otvori(seme_najduze_partije(), dimenzije, jezik=jezik)
        self.assertEqual(strana.evaluate("() => document.documentElement.clientWidth"), dimenzije[0])
        self.proveri_bez_prelivanja(strana, "pocetak")
        for krug in range(1, 8):
            self.odigraj_krug(strana, krug, najduza_partija(krug))
        self.izaberi(strana, najduza_partija(8))
        self.proveri_bez_prelivanja(strana, "igra sa rezultatom i procenom")
        strana.locator("#potvrdi").scroll_into_view_if_needed()
        expect(strana.locator("#potvrdi")).to_be_in_viewport()
        self.potvrdi_i_cekaj(strana)
        expect(strana.locator("#zavrsni")).to_be_visible()
        self.proveri_bez_prelivanja(strana, "zavrsni ekran")
        expect(strana.locator('#zavrsni [data-mesto="budzet-prekoracen"]')).to_be_visible()
        expect(strana.locator('#zavrsni [data-mesto="rok-prekoracen"]')).to_be_visible()
        expect(strana.locator('#zavrsni [data-mesto="lekcije"] li')).to_have_count(5)
        self.proveri_cisto(zapis)

    def test_375_bez_horizontalnog_skrola(self):
        self.proveri_sirinu(TELEFON)

    def test_320_bez_horizontalnog_skrola_en(self):
        # Plan 12.9: duzi engleski tekst i dugme jezika u zaglavlju.
        self.proveri_sirinu(USKI_EKRANI[0], ENGLESKI)

    def test_375_bez_horizontalnog_skrola_en(self):
        self.proveri_sirinu(TELEFON, ENGLESKI)

    def test_768_bez_horizontalnog_skrola(self):
        self.proveri_sirinu(TABLET)

    def test_1440_bez_horizontalnog_skrola(self):
        self.proveri_sirinu(RACUNAR)

    def test_svaka_ocena_staje_na_uskom_ekranu(self):
        # Prava partija za svaku ocenu; ista strana se meri na 320 i na 375 px.
        provereno = []
        # Engleski (plan 12.9): duza ocena i zaglavlje sa dugmetom jezika; zavrsna partija iz sesije.
        for jezik, ocena in itertools.product((SRPSKI, ENGLESKI), OCENE):
            seme = seme_za_ocenu(po_tezini, ocena)
            tekst = OCENE_TEKST[jezik[:2]][ocena]
            if jezik == SRPSKI:
                strana, zapis = self.otvori(seme, USKI_EKRANI[0])
                self.odigraj_celu_u_pregledacu(strana, po_tezini)
            else:
                strana, zapis = self.otvori_zavrseno(seme, USKI_EKRANI[0], po_tezini, jezik=jezik)
            expect(strana.locator('#zavrsni [data-mesto="ocena"]')).to_have_text(tekst)
            for sirina, visina in USKI_EKRANI:
                strana.set_viewport_size({"width": sirina, "height": visina})
                # Ulazna animacija kartice menja velicinu dok traje.
                strana.wait_for_function("() => document.getAnimations().length === 0")
                self.assertEqual(strana.evaluate("() => document.documentElement.clientWidth"), sirina)
                mere = strana.evaluate(JS_OCENA_U_KARTICI)
                with self.subTest(jezik=jezik, ocena=ocena, sirina=sirina):
                    self.assertEqual(mere["tekst"], tekst)
                    self.assertGreaterEqual(mere["redova"], 1)
                    self.assertGreaterEqual(mere["levo"], mere["kartica_levo"], mere)
                    self.assertLessEqual(mere["desno"], mere["kartica_desno"], mere)
                self.proveri_bez_prelivanja(strana, f"{jezik} {ocena}, {sirina} px")
                provereno.append((jezik, ocena, sirina))
            self.proveri_cisto(zapis)
        self.assertEqual(len(provereno), 2 * len(OCENE) * len(USKI_EKRANI))


class SkrolTests(OsnovaToka):
    def cekaj_vrh(self, strana):
        # Bootstrap ukljucuje glatki skrol: ceka se konacna pozicija, ne trenutak poziva.
        strana.wait_for_function("() => window.scrollY === 0")

    def spusti_do_dugmeta(self, strana, izbor):
        self.izaberi(strana, izbor)
        potvrdi = strana.locator("#potvrdi")
        expect(potvrdi).to_be_enabled()
        potvrdi.scroll_into_view_if_needed()
        expect(potvrdi).to_be_in_viewport(ratio=1)
        # Bez ove kontrole povratak na vrh bi prolazio i kad skrola nema.
        strana.wait_for_function("() => window.scrollY > 0")

    def proveri_vidno(self, strana, *selektori):
        for selektor in selektori:
            with self.subTest(selektor=selektor):
                expect(strana.locator(selektor)).to_be_in_viewport(ratio=1)

    def test_375_prvo_ucitavanje_ne_skroluje(self):
        strana, zapis = self.otvori("seme-skrol-ucitavanje", TELEFON)
        # Kontrola: strana je visa od ekrana, pa bi skrol imao kuda.
        visak = strana.evaluate("() => document.documentElement.scrollHeight - window.innerHeight")
        self.assertGreater(visak, 0)
        self.assertEqual(strana.evaluate(JS_SKROL_MIRAN), 0)
        self.proveri_cisto(zapis)

    def test_375_posle_poteza_budzet_rok_rezultat_i_zadatak_u_vidnom_polju(self):
        strana, zapis = self.otvori("seme-skrol", TELEFON)
        rezultat = strana.locator("#rezultat")
        zadatak = strana.locator("#zadatak")
        for krug in range(1, 8):
            with self.subTest(krug=krug):
                self.spusti_do_dugmeta(strana, OPUS_HIGH)
                self.assertEqual(self.potvrdi_i_cekaj(strana).status, 200)
                expect(rezultat.locator('[data-mesto="zadatak"]')).to_contain_text(f"Круг {krug}:")
                expect(zadatak).to_have_text(parametri.ZADACI[krug]["naziv"])
                self.cekaj_vrh(strana)
                self.proveri_vidno(strana, "#budzet", "#rok", "#rezultat", "#zadatak")

        self.spusti_do_dugmeta(strana, OPUS_HIGH)
        self.assertEqual(self.potvrdi_i_cekaj(strana).status, 200)
        expect(rezultat.locator('[data-mesto="zadatak"]')).to_contain_text("Круг 8:")
        expect(strana.locator("#zavrsni")).to_be_visible()
        self.cekaj_vrh(strana)
        self.proveri_vidno(
            strana,
            "#budzet",
            "#rok",
            "#rezultat",
            "#zavrsni h2",
            '#zavrsni [data-mesto="poeni"]',
        )
        self.proveri_cisto(zapis)

    def test_375_posle_409_poruka_u_vidnom_polju(self):
        strana, zapis = self.otvori("seme-skrol-409", TELEFON)
        druga = strana.context.new_page()
        druga.goto(self.live_server_url + "/")
        self.odigraj_krug(druga, 1, OPUS_HIGH)
        druga.close()

        self.spusti_do_dugmeta(strana, izbori("haiku"))
        self.assertEqual(self.potvrdi_i_cekaj(strana).status, 409)
        expect(strana.locator("#poruka")).to_have_text("Стање је освежено.")
        self.cekaj_vrh(strana)
        self.proveri_vidno(strana, "#poruka", "#budzet", "#rok")
        self.assertEqual(zapis.izuzeci, [])


PORUKA_SACUVANO = "Резултат је сачуван."
PORUKA_NEISPRAVNO_IME = (
    "Име мора имати од 1 до 20 знакова, без размака на почетку и крају и без невидљивих знакова."
)
PORUKA_NEPODOBNO_IME = "Ово име није дозвољено. Изаберите друго име."

# Celije rang tabele: tekst ne sme da izadje iz celije ni da bude odsecen.
JS_RANG_CELIJE = """() => {
  const van = [];
  for (const c of document.querySelectorAll('#rang-redovi td, #rang-redovi th')) {
    const r = c.getBoundingClientRect();
    if (c.scrollWidth > c.clientWidth + 1) van.push('odseceno:' + c.textContent.slice(0, 20));
    // Tekst za citac ekrana (.visually-hidden) je isecen na 1 px; njegova geometrija nije vidljiva.
    const setac = document.createTreeWalker(c, NodeFilter.SHOW_TEXT);
    for (let cvor = setac.nextNode(); cvor; cvor = setac.nextNode()) {
      if (cvor.parentElement.closest('.visually-hidden')) continue;
      const opseg = document.createRange();
      opseg.selectNodeContents(cvor);
      for (const t of opseg.getClientRects()) {
        if (t.right > r.right + 0.5 || t.left < r.left - 0.5) {
          van.push('izlazi:' + cvor.textContent.slice(0, 20) + ' ' + JSON.stringify([t.left, t.right, r.left, r.right]));
          break;
        }
      }
    }
  }
  return van;
}"""


# Broj redova teksta svakog imena u listi: tekstualni pravougaonici grupisani po vrhu (+-3 px).
JS_REDOVI_IMENA = """() => {
  const rez = {};
  for (const b of document.querySelectorAll('#rang-redovi [data-mesto="ime"]')) {
    const o = document.createRange();
    o.selectNodeContents(b);
    const vrhovi = Array.from(o.getClientRects()).filter((r) => r.width > 0).map((r) => r.top).sort((a, c) => a - c);
    let redova = 0, poslednji = -1e9;
    for (const v of vrhovi) { if (v - poslednji > 3) { redova += 1; } poslednji = v; }
    rez[b.textContent] = redova;
  }
  return rez;
}"""

# Sopstveni red: svaka tacka unutar <tr> pogadja celiju tog reda (bez rupa izmedju dva reda mreze).
JS_MOJ_RED = """() => {
  const tr = document.querySelector('#rang-redovi tr.rang-moj');
  tr.scrollIntoView({block: 'center', behavior: 'instant'});
  const r = tr.getBoundingClientRect();
  const celije = Array.from(tr.children).map((c) => {
    const b = c.getBoundingClientRect();
    const s = getComputedStyle(c);
    return {top: b.top, bottom: b.bottom, left: b.left, right: b.right, bg: s.backgroundColor,
            levo: s.borderLeftWidth};
  });
  const tudja = document.querySelector('#rang-redovi tr:not(.rang-moj) td');
  const rupe = [];
  for (let y = r.top + 1; y < r.bottom - 1; y += 2) {
    for (let x = r.left + 1; x < r.right - 1; x += 4) {
      const e = document.elementFromPoint(x, y);
      const c = e && e.closest('td, th');
      if (!c || c.parentElement !== tr) rupe.push([Math.round(x), Math.round(y), e ? e.tagName : null]);
    }
  }
  return {tr: {top: r.top, bottom: r.bottom}, celije: celije,
          tudja_bg: getComputedStyle(tudja).backgroundColor, rupe: rupe.slice(0, 5), broj_rupa: rupe.length};
}"""

# Naslov kolone ne sme da izadje iz svoje celije (inace se crta preko susednog naslova).
JS_ZAGLAVLJE = """() => {
  const van = [];
  for (const c of document.querySelectorAll('#rang-tabela thead th')) {
    const r = c.getBoundingClientRect();
    const o = document.createRange();
    o.selectNodeContents(c);
    for (const t of o.getClientRects()) {
      if (t.right > r.right + 0.5 || t.left < r.left - 0.5) {
        van.push(c.textContent.trim() + ' ' + JSON.stringify([Math.round(t.left), Math.round(t.right), Math.round(r.left), Math.round(r.right)]));
        break;
      }
    }
  }
  return van;
}"""

JS_MERNA_OBLAST = """(e) => {
  const r = e.getBoundingClientRect();
  let o = document.getElementById('merna-oblast');
  if (!o) {
    o = document.createElement('div');
    o.id = 'merna-oblast';
    o.style.cssText = 'position:fixed;pointer-events:none;background:transparent;z-index:2147483647';
    document.body.appendChild(o);
  }
  Object.assign(o.style, {left: (r.left + 1) + 'px', top: (r.top + 1) + 'px',
                          width: (r.width - 2) + 'px', height: (r.height - 2) + 'px'});
}"""

JS_DVA_KADRA ="() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => r(true))))"


def danas():
    return timezone.localtime(timezone.now()).strftime("%d.%m.%Y")


class RangTokTests(OsnovaToka):
    def aktivni_id(self, strana):
        return strana.evaluate("() => document.activeElement && document.activeElement.id")

    def test_cuvanje_i_lista(self):
        strana, zapis = self.otvori_zavrseno("seme-rang-tok")
        poeni = odigraj_celu("seme-rang-tok", sve_opus)["rezultat"]
        rang = strana.locator("#rang")
        expect(rang.locator("#rang-naslov")).to_have_text("Ранг листа")
        expect(strana.locator("#rang-prazno")).to_have_text("Још нема сачуваних резултата.")
        expect(strana.locator("#rang-prazno")).to_be_visible()
        expect(strana.locator("#rang-tabela")).to_be_hidden()
        expect(strana.locator("#rang-forma")).to_be_visible()
        expect(strana.locator("#rang-sacuvaj")).to_be_disabled()
        strana.locator("#rang-ime").fill("   ")
        expect(strana.locator("#rang-sacuvaj")).to_be_disabled()

        pre = danas()
        odgovor = self.sacuvaj_i_cekaj(strana, "Пера")
        posle = danas()
        self.assertEqual(odgovor.status, 200)
        expect(strana.locator("#rang-poruka")).to_have_text(PORUKA_SACUVANO)
        expect(strana.locator("#rang-forma")).to_be_hidden()
        self.assertEqual(self.aktivni_id(strana), "rang-poruka")
        redovi = strana.locator("#rang-redovi tr")
        expect(redovi).to_have_count(1)
        expect(strana.locator("#rang-prazno")).to_be_hidden()
        moj = strana.locator("#rang-redovi tr.rang-moj")
        expect(moj).to_have_count(1)
        expect(moj).to_have_attribute("aria-current", "true")
        expect(moj.locator('[data-mesto="mesto"]')).to_have_text("1")
        expect(moj.locator('[data-mesto="ime"]')).to_have_text("Пера")
        expect(moj.locator('[data-mesto="poeni"]')).to_have_text(str(poeni["poeni"]))
        expect(moj.locator('[data-mesto="ocena"]')).to_have_text(OCENE_SR[poeni["ocena"]])
        self.assertIn(moj.locator('[data-mesto="datum"]').inner_text(), {pre, posle})
        expect(moj.locator('[data-mesto="moj"]')).to_have_text(" ваш резултат")

        strana.reload()
        expect(strana.locator("#zavrsni")).to_be_visible()
        expect(strana.locator("#rang-forma")).to_be_hidden()
        expect(strana.locator("#rang-poruka")).to_have_text(PORUKA_SACUVANO)
        expect(strana.locator("#rang-redovi tr.rang-moj")).to_have_count(1)

        dijalozi = []
        strana.on("dialog", lambda d: (dijalozi.append(d.message), d.dismiss()))
        with strana.expect_navigation():
            strana.locator("#nova-forma button").click()
        expect(strana.locator("#krug")).to_have_text("Круг 1 од 8")
        expect(strana.locator("#rang-forma")).to_be_hidden()
        expect(strana.locator("#rang-redovi tr")).to_have_count(1)
        expect(strana.locator("#rang-redovi tr.rang-moj")).to_have_count(0)
        expect(strana.locator("#rang-redovi [aria-current]")).to_have_count(0)
        expect(strana.locator("#rang-poruka")).to_be_hidden()
        self.assertEqual(dijalozi, [])
        self.assertEqual(len(zapis.zahtevi_cuvanja), 1)
        self.proveri_cisto(zapis)

    def test_lista_vidljiva_dok_igra_traje(self):
        upisi_red("Први", 90, timezone.now() - datetime.timedelta(days=1))
        upisi_red("Други", 40)
        strana, zapis = self.otvori("seme-rang-u-igri")
        expect(strana.locator("#rang")).to_be_visible()
        expect(strana.locator("#rang-forma")).to_be_hidden()
        expect(strana.locator("#rang-redovi tr")).to_have_count(2)
        expect(strana.locator('#rang-redovi [data-mesto="ime"]')).to_have_text(["Први", "Други"])
        expect(strana.locator('#rang-redovi [data-mesto="mesto"]')).to_have_text(["1", "2"])
        expect(strana.locator("#rang-redovi tr.rang-moj")).to_have_count(0)
        self.proveri_cisto(zapis)

    def test_neispravno_ime_poruka(self):
        strana, zapis = self.otvori_zavrseno("seme-rang-neispravno")
        polje = strana.locator("#rang-ime")
        odgovor = self.sacuvaj_i_cekaj(strana, "Пе​ра")
        self.assertEqual(odgovor.status, 400)
        greska = strana.locator("#rang-greska")
        expect(greska).to_have_text(PORUKA_NEISPRAVNO_IME)
        expect(greska).to_be_visible()
        expect(polje).to_have_class(re.compile(r"\bis-invalid\b"))
        expect(polje).to_have_attribute("aria-invalid", "true")
        expect(polje).to_have_value("Пе​ра")
        expect(strana.locator("#rang-sacuvaj")).to_be_enabled()
        self.assertEqual(self.aktivni_id(strana), "rang-ime")
        expect(strana.locator("#rang-redovi tr")).to_have_count(0)
        # Zamka 7: tacno jedan 4xx u konzoli, i to bas ovaj.
        self.assertEqual(len(zapis.konzola), 1, zapis.konzola)
        self.assertIn("400", zapis.konzola[0])
        self.assertEqual(zapis.izuzeci, [])

        # Ispravka: greska nestaje, cuvanje prolazi.
        self.assertEqual(self.sacuvaj_i_cekaj(strana, "Пера").status, 200)
        expect(greska).to_be_hidden()
        expect(strana.locator("#rang-poruka")).to_have_text(PORUKA_SACUVANO)
        self.assertEqual(len(zapis.konzola), 1)

    def test_nepodobno_ime_poruka(self):
        NepodobnoIme.objects.create(kljuc="zabranjeno")
        strana, zapis = self.otvori_zavrseno("seme-rang-nepodobno")
        odgovor = self.sacuvaj_i_cekaj(strana, "ZA BRANJENO")
        self.assertEqual(odgovor.status, 400)
        self.assertEqual(odgovor.json(), {"greska": "nepodobno_ime"})
        expect(strana.locator("#rang-greska")).to_have_text(PORUKA_NEPODOBNO_IME)
        expect(strana.locator("#rang-ime")).to_have_class(re.compile(r"\bis-invalid\b"))
        expect(strana.locator("#rang-ime")).to_have_value("ZA BRANJENO")
        expect(strana.locator("#rang-sacuvaj")).to_be_enabled()
        self.assertNotIn("zabranjeno", strana.content())
        self.assertEqual(len(zapis.konzola), 1, zapis.konzola)
        self.assertIn("400", zapis.konzola[0])
        self.assertEqual(zapis.izuzeci, [])

    def test_vec_sacuvano_u_drugoj_kartici(self):
        strana, zapis = self.otvori_zavrseno("seme-rang-kartica")
        druga = strana.context.new_page()
        druga.goto(self.live_server_url + "/")
        expect(druga.locator("#rang-forma")).to_be_visible()
        self.assertEqual(self.sacuvaj_i_cekaj(druga, "Прва").status, 200)

        odgovor = self.sacuvaj_i_cekaj(strana, "Друга")
        self.assertEqual(odgovor.status, 409)
        expect(strana.locator("#rang-poruka")).to_have_text("Ова партија је већ сачувана.")
        expect(strana.locator("#rang-forma")).to_be_hidden()
        expect(strana.locator('#rang-redovi [data-mesto="ime"]')).to_have_text(["Прва"])
        expect(strana.locator("#rang-redovi tr.rang-moj")).to_have_count(1)
        self.assertEqual(len(zapis.konzola), 1, zapis.konzola)
        self.assertIn("409", zapis.konzola[0])
        self.assertEqual(zapis.izuzeci, [])

    def test_cuvanje_ne_skroluje(self):
        strana, zapis = self.otvori_zavrseno("seme-rang-skrol", TELEFON)
        strana.locator("#rang-sacuvaj").scroll_into_view_if_needed()
        strana.wait_for_function("() => window.scrollY > 0")
        self.assertEqual(self.sacuvaj_i_cekaj(strana, "Пера").status, 200)
        expect(strana.locator("#rang-poruka")).to_have_text(PORUKA_SACUVANO)
        polozaj = strana.evaluate(JS_SKROL_MIRAN)
        self.assertGreater(polozaj, 0)
        expect(strana.locator("#rang-poruka")).to_be_in_viewport(ratio=1)
        self.proveri_cisto(zapis)

    def test_dupli_klik_cuvanja_jedan_post(self):
        strana, zapis = self.otvori_zavrseno("seme-rang-dupli")
        strana.locator("#rang-ime").fill("Пера")
        with strana.expect_response(lambda o: o.url.endswith("/sacuvaj/")) as informacija:
            strana.locator("#rang-sacuvaj").dblclick()
        self.assertEqual(informacija.value.status, 200)
        expect(strana.locator("#rang-poruka")).to_have_text(PORUKA_SACUVANO)
        self.assertEqual(len(zapis.zahtevi_cuvanja), 1)
        self.proveri_cisto(zapis)

    def test_dupli_submit_zastita_u_skripti_bez_disabled(self):
        strana, zapis = self.otvori_zavrseno("seme-rang-dupli-js")
        strana.locator("#rang-ime").fill("Пера")
        with strana.expect_response(lambda o: o.url.endswith("/sacuvaj/")) as informacija:
            strana.evaluate(
                """() => {
                  const forma = document.getElementById('rang-forma');
                  const dugme = document.getElementById('rang-sacuvaj');
                  forma.requestSubmit();
                  dugme.disabled = false;
                  forma.requestSubmit();
                  dugme.disabled = false;
                  dugme.click();
                }"""
            )
        self.assertEqual(informacija.value.status, 200)
        expect(strana.locator("#rang-poruka")).to_have_text(PORUKA_SACUVANO)
        self.assertEqual(len(zapis.zahtevi_cuvanja), 1)
        self.proveri_cisto(zapis)

    def test_xss_kroz_ime(self):
        # `a` ne postoji na strani: svako izvrsavanje daje pageerror, svaka slika zahtev.
        napadi = ["<svg onload=a()>", "<b>x</b>", "<img src onerror=a>", "</script><b>x"]
        for rb, ime in enumerate(napadi):
            upisi_red(ime, 90 - rb)
        strana, zapis = self.otvori_zavrseno("seme-rang-xss")
        dijalozi = []
        strana.on("dialog", lambda d: (dijalozi.append(d.message), d.dismiss()))
        imena_na_strani = strana.locator('#rang-redovi [data-mesto="ime"]')
        expect(imena_na_strani).to_have_text(napadi)

        nov_napad = "<img src=x onerror=a"
        self.assertEqual(self.sacuvaj_i_cekaj(strana, nov_napad).status, 200)
        expect(strana.locator("#rang-redovi tr.rang-moj [data-mesto='ime']")).to_have_text(nov_napad)
        expect(imena_na_strani).to_have_count(5)

        for selektor in (
            "#rang-redovi b", "#rang-redovi img", "#rang-redovi svg", "#rang-redovi script",
            "#rang [onload]", "#rang [onerror]", "body > b", "body img",
        ):
            with self.subTest(selektor=selektor):
                self.assertEqual(strana.locator(selektor).count(), 0)
        # Skripta je radila do kraja: stanje je procitano i prikazano.
        expect(strana.locator("#krug")).to_have_text(ZAVRSEN_TEKST)
        self.assertEqual(dijalozi, [])
        self.proveri_cisto(zapis)

    def test_375_rang_bez_prelivanja(self):
        self.proveri_usku_rang_listu(SRPSKI)

    def test_375_rang_bez_prelivanja_en(self):
        # Plan 12.9: engleska ocena je duza, datum je ISO (iste sirine kao 10.11.2026).
        self.proveri_usku_rang_listu(ENGLESKI)

    def proveri_usku_rang_listu(self, jezik):
        # Najsira imena od 20 znakova, bez mesta za prelom, uz najduzu ocenu.
        siroka = ["Ш" * 20, "Ж" * 20, "W" * 20, "Щ" * 20, "M" * 20, "😀" * 20, "Ю" * 20, "Ш" * 20, "Ж" * 20]
        pocetak = timezone.now() - datetime.timedelta(days=30)
        for rb, ime in enumerate(siroka):
            upisi_red(ime, 100, pocetak + datetime.timedelta(days=rb), "odlican")
        upisi_red("Ш" * 20, 0, pocetak)
        seme = nadji_seme(sve_opus, lambda i: i == [motor.USPEH] * 8)
        strana, zapis = self.otvori_zavrseno(seme, USKI_EKRANI[0], jezik=jezik)
        expect(strana.locator("#rang-redovi tr")).to_have_count(10)
        expect(strana.locator('#rang-redovi [data-mesto="ocena"]').first).to_have_text(
            OCENE_TEKST[jezik[:2]]["odlican"]
        )
        datum = {"sr": r"^\d{2}\.\d{2}\.\d{4}$", "en": r"^\d{4}-\d{2}-\d{2}$"}[jezik[:2]]
        self.assertRegex(strana.locator('#rang-redovi [data-mesto="datum"]').first.inner_text(), datum)

        def izmeri(oznaka):
            for sirina, visina in USKI_EKRANI:
                strana.set_viewport_size({"width": sirina, "height": visina})
                strana.wait_for_function("() => document.getAnimations().length === 0")
                self.assertEqual(strana.evaluate("() => document.documentElement.clientWidth"), sirina)
                self.proveri_bez_prelivanja(strana, f"{oznaka}, {sirina} px")
                with self.subTest(ekran=oznaka, sirina=sirina):
                    self.assertEqual(strana.evaluate(JS_RANG_CELIJE), [])

        izmeri("forma i 10 redova")
        strana.set_viewport_size({"width": USKI_EKRANI[0][0], "height": USKI_EKRANI[0][1]})
        strana.locator("#rang-ime").fill("Ш" * 20)
        izmeri("popunjena forma")
        self.assertEqual(self.sacuvaj_i_cekaj(strana, "Ш" * 20).status, 200)
        expect(strana.locator("#rang-redovi tr.rang-moj")).to_have_count(1)
        expect(strana.locator("#rang-redovi tr.rang-moj [data-mesto='mesto']")).to_have_text("10")
        izmeri("posle cuvanja, istaknut red")
        self.proveri_cisto(zapis)

    def postavi_usku(self, strana, sirina, visina):
        strana.set_viewport_size({"width": sirina, "height": visina})
        strana.wait_for_function("() => document.getAnimations().length === 0")
        self.assertEqual(strana.evaluate("() => document.documentElement.clientWidth"), sirina)

    def test_uska_tabela_imena_i_redovi(self):
        # Prelom imena na 320 i 375 px (raspored ispod 576 px, plan 10.6 posle ispravke).
        obicna = ["Александрија", "Јелена Перић", "Миловановић", "Ana Marković"]
        dugacka = "Ш" * 20
        imena_liste = obicna + ["Šćepanović", dugacka, "W" * 20, "Ж" * 20, "😀" * 10, "Мика"]
        for rb, ime in enumerate(imena_liste):
            upisi_red(ime, 100 - rb, ocena="odlican")
        strana, zapis = self.otvori("seme-uska-tabela", USKI_EKRANI[0])
        expect(strana.locator("#rang-redovi tr")).to_have_count(10)
        for sirina, visina in USKI_EKRANI:
            self.postavi_usku(strana, sirina, visina)
            redovi = strana.evaluate(JS_REDOVI_IMENA)
            with self.subTest(sirina=sirina):
                self.assertEqual(set(redovi), set(imena_liste))
                for ime in obicna:
                    self.assertLessEqual(len(ime), 12)
                    self.assertEqual(redovi[ime], 1, (ime, redovi))
                self.assertEqual(redovi["Šćepanović"], 1, redovi)
                self.assertLessEqual(redovi[dugacka], 2, redovi)
                self.assertEqual(strana.evaluate(JS_RANG_CELIJE), [])
            with self.subTest(sirina=sirina, deo="zaglavlje"):
                self.assertEqual(strana.evaluate(JS_ZAGLAVLJE), [], "naslov kolone izlazi iz celije")
            self.proveri_bez_prelivanja(strana, f"uska tabela {sirina} px")
        self.proveri_cisto(zapis)

    def test_uska_prazna_lista_bez_tabele(self):
        strana, zapis = self.otvori("seme-uska-prazna", USKI_EKRANI[0])
        for sirina, visina in USKI_EKRANI:
            self.postavi_usku(strana, sirina, visina)
            with self.subTest(sirina=sirina):
                expect(strana.locator("#rang-prazno")).to_be_visible()
                expect(strana.locator("#rang-tabela")).to_be_hidden()
                self.assertEqual(
                    strana.evaluate("() => getComputedStyle(document.getElementById('rang-tabela')).display"),
                    "none",
                )
        self.proveri_cisto(zapis)

    def test_uski_moj_red_kroz_oba_reda(self):
        seme = "seme-uski-moj"
        for rb in range(4):
            upisi_red(f"Играч {rb}", 100 - rb)
        igra = odigraj_celu(seme, sve_opus)
        # Red ove partije: oznaka "sacuvan" vazi samo za red sa istom partijom (revizija N1).
        moj = Rezultat.objects.create(
            ime="Пера Перић", poeni=90, ocena=motor.oceni(90), pravila=parametri.PRAVILA_TEKUCA,
            partija=motor.oznaka_partije(igra),
        )
        for rb in range(4):
            upisi_red(f"Слабији {rb}", 50 - rb)
        stanje = motor.oznaci_sacuvano(igra, moj.id)
        strana, zapis = self.otvori(seme, USKI_EKRANI[0], stanje=stanje)
        expect(strana.locator("#rang-redovi tr.rang-moj")).to_have_count(1)
        for sirina, visina in USKI_EKRANI:
            self.postavi_usku(strana, sirina, visina)
            m = strana.evaluate(JS_MOJ_RED)
            mesto, ime, poeni, ocena, datum = m["celije"]
            with self.subTest(sirina=sirina):
                # Ocena ispod imena, datum ispod poena, bez razmaka izmedju dva reda.
                self.assertAlmostEqual(ime["bottom"], ocena["top"], delta=1, msg=m)
                self.assertAlmostEqual(poeni["bottom"], datum["top"], delta=1, msg=m)
                # Mesto i leva ivica se protezu kroz oba reda.
                self.assertAlmostEqual(mesto["top"], m["tr"]["top"], delta=1, msg=m)
                self.assertAlmostEqual(mesto["bottom"], m["tr"]["bottom"], delta=1, msg=m)
                self.assertEqual(mesto["levo"], "4px")
                # Ista pozadina u svih pet celija, razlicita od tudjeg reda, i nijedna rupa.
                self.assertEqual({c["bg"] for c in m["celije"]}, {mesto["bg"]})
                self.assertNotEqual(mesto["bg"], m["tudja_bg"])
                self.assertNotEqual(mesto["bg"], "rgba(0, 0, 0, 0)")
                self.assertEqual(m["broj_rupa"], 0, m["rupe"])
        self.proveri_cisto(zapis)

    def test_kombinujuci_ne_crtaju_van_celije(self):
        ime = "Z͆͆a͓͓"  # po 2 iznad i ispod: najvise sto pravilo imena pusta
        upisi_red("Ана", 90)
        upisi_red(ime, 80)
        upisi_red("Ива", 70)
        strana, zapis = self.otvori("seme-kombinujuci", USKI_EKRANI[0])
        redovi = strana.locator("#rang-redovi tr")
        expect(redovi).to_have_count(3)
        meta = redovi.nth(1)
        bdi = meta.locator('[data-mesto="ime"]')
        expect(bdi).to_have_text(ime)
        susedi = [
            redovi.nth(0),
            meta.locator('[data-mesto="ocena"]'),
            meta.locator('[data-mesto="poeni"]'),
            meta.locator('[data-mesto="mesto"]'),
            redovi.nth(2),
        ]

        def okolina():
            # Snimak providnog fiksnog okvira nad susedom, uvucenog 1 px: granica dve celije deli
            # delimican red piksela, pa bi ga snimak celog suseda video i kad nista ne izlazi.
            strana.wait_for_function(JS_DVA_KADRA)
            okviri, snimci = [], []
            for s in susedi:
                okviri.append(s.bounding_box())
                s.evaluate(JS_MERNA_OBLAST)
                snimci.append(strana.locator("#merna-oblast").screenshot(animations="disabled"))
            strana.evaluate("() => document.getElementById('merna-oblast').remove()")
            return okviri, snimci

        # Bootstrap ukljucuje glatki skrol; merenje trazi miran ekran sa sva tri reda u vidnom polju.
        strana.evaluate("() => { document.documentElement.style.scrollBehavior = 'auto'; }")
        for sirina, visina in USKI_EKRANI:
            self.postavi_usku(strana, sirina, visina)
            redovi.nth(1).evaluate("(e) => e.scrollIntoView({block: 'center', behavior: 'instant'})")
            bdi.evaluate("(e, t) => { e.textContent = t; e.parentElement.style.overflow = ''; }", ime)
            okviri_sa, sa_znacima = okolina()
            bdi.evaluate("(e) => { e.textContent = 'Za'; }")
            okviri_bez, bez_znakova = okolina()
            with self.subTest(sirina=sirina):
                self.assertEqual(okviri_sa, okviri_bez)
                self.assertTrue(sa_znacima == bez_znakova, "kombinujuci znak crta preko susedne celije")
                # Kontrola: bez okvira celije isti znaci se vide u susedstvu, pa provera vidi crtez.
                bdi.evaluate("(e, t) => { e.textContent = t; e.parentElement.style.overflow = 'visible'; }", ime)
                _, vidljivo = okolina()
                self.assertFalse(vidljivo == bez_znakova, "kontrola: znaci ne izlaze ni bez okvira")
        self.proveri_cisto(zapis)

    def test_rang_tabela_za_citac_ekrana(self):
        for rb, ime in enumerate(("Пера", "Мика", "Ана")):
            upisi_red(ime, 90 - rb)
        strana, zapis = self.otvori("seme-citac", USKI_EKRANI[0])
        expect(strana.locator("#rang-redovi tr")).to_have_count(3)
        for sirina, visina in (USKI_EKRANI[0], TELEFON, TABLET, RACUNAR):
            self.postavi_usku(strana, sirina, visina)
            snimak = strana.locator("#rang").aria_snapshot()
            with self.subTest(sirina=sirina):
                self.assertRegex(snimak, r'- table "Ранг листа"')
                self.assertEqual(
                    re.findall(r'- columnheader "([^"]+)"', snimak), ["Место", "Име", "Поени", "Оцена", "Датум"]
                )
                self.assertEqual(len(re.findall(r"- row\b", snimak)), 4, snimak)
                self.assertEqual(re.findall(r'- rowheader "([^"]+)"', snimak), ["1", "2", "3"], snimak)
                self.assertIn('- cell "Пера"', snimak)
                self.assertIn('- cell "одличан оркестратор"', snimak)
        self.proveri_cisto(zapis)


# Deljenje rezultata (plan 11.6, 11.9). Tekstovi su prepisani iz plana.
PORUKA_KOPIRANO = "Линк је копиран."
PORUKA_REZERVA = "Копирање није успело. Линк је означен; копирајте га ручно."
PORUKA_REZERVA_EN = "Copying failed. The link is selected; copy it manually."
PORUKA_ISTEKLO = "Линк за ову партију више није доступан."
DOZVOLE_CLIPBOARD = ["clipboard-read", "clipboard-write"]
JS_BEZ_CLIPBOARD = "Object.defineProperty(Navigator.prototype, 'clipboard', {get() { return undefined; }, configurable: true});"
JS_CLIPBOARD_ODBIJA = (
    "Clipboard.prototype.writeText = function () {"
    " return Promise.reject(new DOMException('odbijeno', 'NotAllowedError')); };"
)
JS_NIJE_SIGURNO = "Object.defineProperty(window, 'isSecureContext', {get() { return false; }, configurable: true});"
JS_BEZ_SHARE = "delete Navigator.prototype.share; delete Navigator.prototype.canShare;"
# Lazni navigator.share: belezi argumente; ishod bira window.__ishodSlanja (ok, AbortError, NotAllowedError).
JS_LAZNI_SHARE = """
window.__poslato = [];
Object.defineProperty(Navigator.prototype, 'share', {configurable: true, writable: true, value: function (podaci) {
  window.__poslato.push({title: podaci.title, text: podaci.text, url: podaci.url});
  const ishod = window.__ishodSlanja || 'ok';
  return ishod === 'ok' ? Promise.resolve() : Promise.reject(new DOMException('x', ishod));
}});
"""
JS_IZBOR_LINKA = """() => {
  const e = document.getElementById('deli-link');
  return {aktivan: document.activeElement && document.activeElement.id,
          od: e.selectionStart, do: e.selectionEnd, duzina: e.value.length};
}"""
OBLIK_URL = r"/r/[A-Za-z0-9_-]{22}/"
# Po delu zavrsnog ekrana: sirina, visina, tekst i stil svakog vidljivog elementa u njemu, plus ton kartice.
JS_IZGLED_ZAVRSNOG = """(delovi) => {
  const svojstva = ['color', 'backgroundColor', 'backgroundImage', 'fontSize', 'fontWeight', 'fontFamily',
                    'lineHeight', 'paddingTop', 'paddingLeft', 'marginTop', 'borderTopWidth', 'borderTopColor',
                    'borderLeftWidth', 'borderLeftColor', 'borderRadius', 'display', 'boxShadow'];
  const zavrsni = document.getElementById('zavrsni');
  const rez = {};
  for (const deo of delovi) {
    const koren = zavrsni.querySelector(deo);
    const okvir = koren.getBoundingClientRect();
    const stilovi = [];
    for (const e of [koren, ...koren.querySelectorAll('*')]) {
      const r = e.getBoundingClientRect();
      if (r.width === 0 && r.height === 0) continue;
      const s = getComputedStyle(e);
      stilovi.push([e.tagName, Math.round(r.width * 10) / 10, Math.round(r.height * 10) / 10,
                    ...svojstva.map((k) => s[k])]);
    }
    rez[deo] = {sirina: Math.round(okvir.width * 10) / 10, visina: Math.round(okvir.height * 10) / 10,
                tekst: koren.innerText, elemenata: stilovi.length, stilovi: stilovi,
                ton: zavrsni.dataset.ocena, poeni: zavrsni.style.getPropertyValue('--poeni')};
  }
  return rez;
}"""


class DeljenjeTokTests(OsnovaToka):
    def seme_sa_tihom(self):
        return nadji_seme(sve_opus, lambda i: motor.TIHI_NEUSPEH in i)

    def otvori_link(self, url, dimenzije=RACUNAR, jezik=SRPSKI):
        """Link u novom kontekstu bez kolacica; vraca stranu, zapis i odgovor dokumenta."""
        kontekst = self.novi_kontekst(dimenzije, jezik=jezik)
        self.assertEqual(kontekst.cookies(), [])
        strana = kontekst.new_page()
        zapis = Zapis(strana)
        odgovor = strana.goto(url)
        return strana, zapis, odgovor

    def podeli_u_igri(self, strana):
        odgovor = self.podeli_i_cekaj(strana)
        self.assertEqual(odgovor.status, 200)
        url = odgovor.json()["url"]
        expect(strana.locator("#deli-blok")).to_be_visible()
        expect(strana.locator("#deli-link")).to_have_value(url)
        return url

    def test_podeli_kopiraj_otvori(self):
        seme = self.seme_sa_tihom()
        kraj = odigraj_celu(seme, sve_opus)["rezultat"]
        strana, zapis = self.otvori_zavrseno(seme, dozvole=DOZVOLE_CLIPBOARD)
        dugme = strana.locator("#deli-dugme")
        expect(dugme).to_be_visible()
        expect(dugme).to_have_text("Подели резултат")
        expect(strana.locator("#deli-blok")).to_be_hidden()

        pre = danas()
        odgovor = self.podeli_i_cekaj(strana)
        posle = danas()
        self.assertEqual(odgovor.status, 200)
        podaci = odgovor.json()
        url = podaci["url"]
        self.assertRegex(url, "^" + re.escape(self.live_server_url) + OBLIK_URL + "$")
        expect(strana.locator("#deli-blok")).to_be_visible()
        expect(strana.locator('label[for="deli-link"]')).to_have_text("Линк за дељење")
        expect(strana.locator("#deli-link")).to_have_value(url)
        expect(strana.locator("#deli-link")).to_have_attribute("readonly", "")
        expect(strana.locator("#deli-rok")).to_have_text(f"Линк важи до {podaci['istice']}.")
        expect(strana.locator("#deli-poruka")).to_be_hidden()

        kopiraj = strana.locator("#deli-kopiraj")
        expect(kopiraj).to_have_text("Копирај линк")
        kopiraj.click()
        expect(strana.locator("#deli-poruka")).to_have_text(PORUKA_KOPIRANO)
        self.assertEqual(strana.evaluate("() => navigator.clipboard.readText()"), url)
        self.assertEqual(len(zapis.zahtevi_deljenja), 1)
        self.proveri_cisto(zapis)
        sesija_igraca = {k["name"]: k["value"] for k in strana.context.cookies()}["sessionid"]

        # Link u novom kontekstu bez kolacica: rezultat te partije, samo za citanje.
        gost, zapis_gosta, dokument = self.otvori_link(url)
        self.assertEqual(dokument.status, 200)
        zavrsni = gost.locator("#zavrsni")
        expect(zavrsni).to_be_visible()
        expect(gost).to_have_title("Подељени резултат · Оркестратор")
        expect(gost.locator(".vrh .krug")).to_have_text("Подељени резултат")
        for mesto in ("poeni", "ocena", "cena", "minuti"):
            with self.subTest(mesto=mesto):
                expect(zavrsni.locator(f'[data-mesto="{mesto}"]')).to_have_text(
                    strana.locator(f'#zavrsni [data-mesto="{mesto}"]').inner_text()
                )
        expect(zavrsni.locator('[data-mesto="poeni"]')).to_have_text(str(kraj["poeni"]))
        expect(zavrsni.locator('[data-mesto="ocena"]')).to_have_text(OCENE_SR[kraj["ocena"]])
        expect(zavrsni.locator('[data-mesto="tihe"] li')).to_have_count(len(kraj["tihe_greske"]))
        expect(zavrsni.locator('[data-mesto="napomena"]')).to_have_text(NAPOMENA)
        self.assertIn(gost.locator("#deljeno-datum").inner_text(), {pre, posle})
        expect(gost.locator("#deljeno-podaci")).to_be_visible()
        expect(gost.locator("#deljeno-ime-red")).to_be_hidden()
        expect(gost.locator(".deljeno-napomena")).to_have_text("Ово је завршена партија; овде се не може играти.")
        for selektor in ("#kontrole", "#potvrdi", "#nova-forma", "#rang", "#rang-forma", "#deli",
                         "#staza", "form", "input", "button"):
            with self.subTest(selektor=selektor):
                self.assertEqual(gost.locator(selektor).count(), 0)
        self.assertEqual(gost.context.cookies(), [])

        # „Играј и ти“ vodi na pocetnu, gde pocinje nova igra posetioca.
        igraj = gost.locator("#igraj-i-ti")
        expect(igraj).to_have_text("Играј и ти")
        with gost.expect_navigation():
            igraj.click()
        self.assertEqual(gost.url, self.live_server_url + "/")
        expect(gost.locator("#krug")).to_have_text("Круг 1 од 8")
        expect(gost.locator("#zavrsni")).to_be_hidden()
        kolacici = {k["name"]: k["value"] for k in gost.context.cookies()}
        self.assertEqual(set(kolacici), {"sessionid", "csrftoken"})
        self.assertNotEqual(kolacici["sessionid"], sesija_igraca)
        igra_gosta = SessionStore(session_key=kolacici["sessionid"])["igra"]
        self.assertEqual((igra_gosta["krug"], igra_gosta["zavrsena"]), (1, False))
        self.assertNotEqual(igra_gosta["seme"], seme)
        self.proveri_cisto(zapis_gosta)

        # Igrac je i dalje na svom zavrsnom ekranu.
        strana.reload()
        expect(strana.locator("#krug")).to_have_text(ZAVRSEN_TEKST)
        expect(strana.locator("#zavrsni")).to_be_visible()
        self.proveri_cisto(zapis)

    def test_kopiranje_bez_clipboard(self):
        for opis, skripta in (
            ("nema clipboard", JS_BEZ_CLIPBOARD),
            ("writeText odbija", JS_CLIPBOARD_ODBIJA),
            ("nije secure context", JS_NIJE_SIGURNO),
        ):
            with self.subTest(opis=opis):
                strana, zapis = self.otvori_zavrseno(
                    f"seme-rezerva-{opis}", dozvole=DOZVOLE_CLIPBOARD, skripta=skripta
                )
                url = self.podeli_u_igri(strana)
                strana.locator("#deli-kopiraj").click()
                expect(strana.locator("#deli-poruka")).to_have_text(PORUKA_REZERVA)
                izbor = strana.evaluate(JS_IZBOR_LINKA)
                self.assertEqual(izbor, {"aktivan": "deli-link", "od": 0, "do": len(url), "duzina": len(url)})
                self.proveri_cisto(zapis)

    def test_navigator_share(self):
        strana, zapis = self.otvori_zavrseno("seme-share", skripta=JS_LAZNI_SHARE)
        url = self.podeli_u_igri(strana)
        posalji = strana.locator("#deli-posalji")
        expect(posalji).to_be_visible()
        expect(posalji).to_have_text("Пошаљи")
        posalji.click()
        strana.wait_for_function("() => window.__poslato.length === 1")
        self.assertEqual(
            strana.evaluate("() => window.__poslato"),
            [{"title": "Оркестратор", "text": "Мој резултат у игри Оркестратор", "url": url}],
        )
        expect(strana.locator("#deli-poruka")).to_be_hidden()

        # Igrac odustaje: bez poruke i bez oznacavanja polja.
        strana.evaluate("() => { window.__ishodSlanja = 'AbortError'; }")
        posalji.click()
        strana.wait_for_function("() => window.__poslato.length === 2")
        strana.wait_for_function(JS_DVA_KADRA)
        expect(strana.locator("#deli-poruka")).to_be_hidden()
        self.assertNotEqual(strana.evaluate(JS_IZBOR_LINKA)["aktivan"], "deli-link")

        # Druga greska: rezerva.
        strana.evaluate("() => { window.__ishodSlanja = 'NotAllowedError'; }")
        posalji.click()
        expect(strana.locator("#deli-poruka")).to_have_text(PORUKA_REZERVA)
        self.assertEqual(strana.evaluate(JS_IZBOR_LINKA)["aktivan"], "deli-link")
        self.proveri_cisto(zapis)

        # Bez navigator.share dugme ne postoji za igraca.
        bez, zapis_bez = self.otvori_zavrseno("seme-bez-share", skripta=JS_BEZ_SHARE)
        self.assertEqual(bez.evaluate("() => typeof navigator.share"), "undefined")
        self.podeli_u_igri(bez)
        expect(bez.locator("#deli-kopiraj")).to_be_visible()
        expect(bez.locator("#deli-posalji")).to_be_hidden()
        self.proveri_cisto(zapis_bez)

    def test_ponovni_klik_posle_osvezavanja_isti_link(self):
        strana, zapis = self.otvori_zavrseno("seme-tok-isti-link")
        prvi = self.podeli_u_igri(strana)
        drugi = self.podeli_u_igri(strana)
        self.assertEqual(drugi, prvi)
        strana.reload()
        expect(strana.locator("#zavrsni")).to_be_visible()
        expect(strana.locator("#deli-blok")).to_be_hidden()
        self.assertEqual(self.podeli_u_igri(strana), prvi)
        self.assertEqual(len(zapis.zahtevi_deljenja), 3)

        # Dupli klik preko skinutog `disabled`: zastita u skripti salje jedan zahtev.
        with strana.expect_response(lambda o: o.url.endswith("/podeli/")) as informacija:
            strana.evaluate(
                """() => {
                  const dugme = document.getElementById('deli-dugme');
                  dugme.click();
                  dugme.disabled = false;
                  dugme.click();
                }"""
            )
        self.assertEqual(informacija.value.status, 200)
        expect(strana.locator("#deli-dugme")).to_be_enabled()
        self.assertEqual(len(zapis.zahtevi_deljenja), 4)
        self.assertEqual(DeljeniRezultat.objects.count(), 1)
        self.proveri_cisto(zapis)

    def test_istekao_link_poruka(self):
        red = istekao_red()
        strana, zapis, dokument = self.otvori_link(f"{self.live_server_url}/r/{red.token}/")
        self.assertEqual(dokument.status, 404)
        expect(strana).to_have_title("Резултат није доступан · Оркестратор")
        expect(strana.locator("#nedostupno")).to_be_visible()
        expect(strana.locator("#nedostupno h2")).to_have_text("Овај резултат више није доступан.")
        expect(strana.locator("#nedostupno p")).to_have_text("Линк за дељење важи 30 дана.")
        self.assertEqual(strana.locator("#zavrsni").count(), 0)
        self.assertEqual(strana.locator("#deljeni-rezultat").count(), 0)
        # Zamka 7: tacno jedan 4xx u konzoli, i to bas ovaj dokument.
        self.assertEqual(len(zapis.konzola), 1, zapis.konzola)
        self.assertIn("404", zapis.konzola[0])
        self.assertEqual(zapis.losi_odgovori(), [f"404 {self.live_server_url}/r/{red.token}/"])
        self.assertEqual(zapis.izuzeci, [])
        self.assertEqual(zapis.neuspeli, [])
        self.assertEqual(strana.context.cookies(), [])
        with strana.expect_navigation():
            strana.locator("#igraj-i-ti").click()
        expect(strana.locator("#krug")).to_have_text("Круг 1 од 8")
        self.assertEqual(len(zapis.konzola), 1)

    def test_isteklo_deljenje_poruka_na_zavrsnom(self):
        seme = "seme-tok-isteklo-deljenje"
        stanje = odigraj_celu(seme, sve_opus)
        red = istekao_red(stanje)
        strana, zapis = self.otvori(seme, stanje=motor.oznaci_podeljeno(stanje, red.id))
        odgovor = self.podeli_i_cekaj(strana)
        self.assertEqual(odgovor.status, 409)
        expect(strana.locator("#deli-poruka")).to_have_text(PORUKA_ISTEKLO)
        expect(strana.locator("#deli-blok")).to_be_hidden()
        expect(strana.locator("#deli-dugme")).to_be_enabled()
        self.assertEqual(len(zapis.konzola), 1, zapis.konzola)
        self.assertIn("409", zapis.konzola[0])
        self.assertEqual(zapis.izuzeci, [])

    def test_link_ne_menja_igru_posetioca(self):
        red = upisi_deljeno()
        strana, zapis = self.otvori("seme-tok-posetilac")
        self.odigraj_krug(strana, 1, OPUS_HIGH)
        kolacici_pre = sorted((k["name"], k["value"]) for k in strana.context.cookies())
        druga = strana.context.new_page()
        zapis_druge = Zapis(druga)
        self.assertEqual(druga.goto(f"{self.live_server_url}/r/{red.token}/").status, 200)
        expect(druga.locator("#zavrsni")).to_be_visible()
        self.proveri_cisto(zapis_druge)
        self.assertEqual(sorted((k["name"], k["value"]) for k in strana.context.cookies()), kolacici_pre)
        strana.reload()
        expect(strana.locator("#krug")).to_have_text("Круг 2 од 8")
        self.odigraj_krug(strana, 2, OPUS_HIGH)
        self.proveri_cisto(zapis)

    def test_deljena_bez_prelivanja(self):
        self.proveri_deljenu_usko(SRPSKI)

    def test_deljena_bez_prelivanja_en(self):
        self.proveri_deljenu_usko(ENGLESKI)

    def proveri_deljenu_usko(self, jezik):
        seme = seme_najduze_partije()
        stanje = odigraj_celu(seme, najduza_partija)
        red = upisi_deljeno(stanje)
        Rezultat.objects.create(ime="Ш" * 20, poeni=stanje["rezultat"]["poeni"],
                                ocena=stanje["rezultat"]["ocena"], pravila=parametri.PRAVILA_TEKUCA,
                                partija=red.partija)
        istekao = istekao_red()

        strana, zapis, dokument = self.otvori_link(f"{self.live_server_url}/r/{red.token}/", USKI_EKRANI[0], jezik)
        self.assertEqual(dokument.status, 200)
        expect(strana.locator("html")).to_have_attribute("lang", jezik[:2])
        expect(strana.locator("#deljeno-ime")).to_have_text("Ш" * 20)
        expect(strana.locator('#zavrsni [data-mesto="tihe"] li')).to_have_count(3)
        expect(strana.locator('#zavrsni [data-mesto="lekcije"] li')).to_have_count(5)
        for sirina, visina in USKI_EKRANI:
            strana.set_viewport_size({"width": sirina, "height": visina})
            strana.wait_for_function("() => document.getAnimations().length === 0")
            self.assertEqual(strana.evaluate("() => document.documentElement.clientWidth"), sirina)
            self.proveri_bez_prelivanja(strana, f"deljena, {sirina} px")
        self.proveri_cisto(zapis)

        nedostupna, zapis_404, dokument = self.otvori_link(
            f"{self.live_server_url}/r/{istekao.token}/", USKI_EKRANI[0], jezik
        )
        expect(nedostupna.locator("html")).to_have_attribute("lang", jezik[:2])
        self.assertEqual(dokument.status, 404)
        for sirina, visina in USKI_EKRANI:
            nedostupna.set_viewport_size({"width": sirina, "height": visina})
            self.proveri_bez_prelivanja(nedostupna, f"404, {sirina} px")

        # Zavrsni ekran igre sa otvorenim blokom deljenja i porukom rezerve (najduza poruka).
        igra, zapis_igre = self.otvori(seme, USKI_EKRANI[0], stanje=stanje, skripta=JS_BEZ_CLIPBOARD, jezik=jezik)
        self.podeli_u_igri(igra)
        igra.locator("#deli-kopiraj").click()
        expect(igra.locator("#deli-poruka")).to_have_text(PORUKA_REZERVA if jezik == SRPSKI else PORUKA_REZERVA_EN)
        for sirina, visina in USKI_EKRANI:
            igra.set_viewport_size({"width": sirina, "height": visina})
            igra.wait_for_function("() => document.getAnimations().length === 0")
            self.assertEqual(igra.evaluate("() => document.documentElement.clientWidth"), sirina)
            self.proveri_bez_prelivanja(igra, f"zavrsni sa deljenjem, {sirina} px")
            # Polje sa linkom staje u blok deljenja.
            polje = igra.locator("#deli-link").bounding_box()
            blok = igra.locator("#deli").bounding_box()
            self.assertLessEqual(polje["x"] + polje["width"], blok["x"] + blok["width"] + 0.5)
        self.proveri_cisto(zapis_igre)

    def test_xss_kroz_ime_na_deljenoj(self):
        ime = "<svg onload=a()>"
        stanje = odigraj_celu("seme-tok-xss-deljeno", sve_opus)
        red = upisi_deljeno(stanje)
        Rezultat.objects.create(ime=ime, poeni=stanje["rezultat"]["poeni"],
                                ocena=stanje["rezultat"]["ocena"], pravila=parametri.PRAVILA_TEKUCA,
                                partija=red.partija)
        strana, zapis, dokument = self.otvori_link(f"{self.live_server_url}/r/{red.token}/")
        self.assertEqual(dokument.status, 200)
        dijalozi = []
        strana.on("dialog", lambda d: (dijalozi.append(d.message), d.dismiss()))
        expect(strana.locator("#deljeno-ime")).to_have_text(ime)
        expect(strana.locator("#deljeno-ime-red")).to_be_visible()
        for selektor in ("[onload]", "#deljeno-podaci svg", "#deljeno-ime *"):
            with self.subTest(selektor=selektor):
                self.assertEqual(strana.locator(selektor).count(), 0)
        # Skripta je radila do kraja: zavrsni ekran je nacrtan.
        expect(strana.locator('#zavrsni [data-mesto="poeni"]')).to_have_text(str(stanje["rezultat"]["poeni"]))
        self.assertEqual(dijalozi, [])
        self.proveri_cisto(zapis)

    def test_deljena_kartica_ista_kao_u_igri(self):
        # Isti izgled: svaki deo zavrsnog ekrana ima istu velicinu, tekst i stil na obe strane.
        # (Snimak piksel po piksel ne moze: delovi stoje na razlicitoj visini, pa se ivice zaokruzuju drugacije.)
        seme = seme_najduze_partije()
        stanje = odigraj_celu(seme, najduza_partija)
        red = upisi_deljeno(stanje)
        delovi = (".zavrsni-naslov", ".hero", ".zbir", '[data-mesto="tihe"]', '[data-mesto="lekcije"]',
                  ".napomena")
        for dimenzije in (USKI_EKRANI[0], TELEFON, RACUNAR):
            igra, zapis_igre = self.otvori(seme, dimenzije, stanje=stanje)
            deljena, zapis_deljene, _ = self.otvori_link(f"{self.live_server_url}/r/{red.token}/", dimenzije)
            mere = []
            for strana in (igra, deljena):
                strana.wait_for_function("() => document.getAnimations().length === 0")
                mere.append(strana.evaluate(JS_IZGLED_ZAVRSNOG, list(delovi)))
            with self.subTest(sirina=dimenzije[0]):
                self.assertEqual(len(mere[0]), len(delovi))
                self.assertGreater(mere[0][".hero"]["elemenata"], 5)
                self.assertEqual(mere[1], mere[0])
            self.proveri_cisto(zapis_igre)
            self.proveri_cisto(zapis_deljene)


# ---------- Srpski i engleski u pregledacu (plan 12.9, uslov 11) ----------

ZADACI_EN = {
    "prevod": "Home page translation",
    "sablon": "List and form template",
    "css": "CSS and phone adaptation",
    "crud": "CRUD screens",
    "model": "Data model and migration",
    "prava": "Access rights check",
    "testovi": "Automated tests",
    "revizija": "Security review",
}
# Vidljiv tekst strane, naslov i aria-label/title, bez imena igraca (bdi) i bez elementa drugog jezika ([lang]).
JS_VIDLJIV_TEKST = """() => {
  const delovi = [document.title];
  const setac = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let c = setac.nextNode(); c; c = setac.nextNode()) {
    const e = c.parentElement;
    if (!e || e.closest('script, style, template, bdi, [lang]:not(html)')) continue;
    if (!e.checkVisibility()) continue;
    delovi.push(c.textContent);
  }
  for (const e of document.body.querySelectorAll('[aria-label], [title], [placeholder]')) {
    if (e.closest('[lang]:not(html)') || !e.checkVisibility()) continue;
    delovi.push(e.getAttribute('aria-label') || '', e.getAttribute('title') || '', e.getAttribute('placeholder') || '');
  }
  return delovi.join(' ');
}"""


class JezikTokTests(OsnovaToka):
    def kolacic_jezika(self, kontekst):
        return {k["name"]: k for k in kontekst.cookies()}.get(settings.LANGUAGE_COOKIE_NAME)

    def promeni_jezik(self, strana, ocekivani):
        dugme = strana.locator("#jezik-dugme")
        expect(dugme).to_have_attribute("lang", ocekivani)
        with strana.expect_navigation():
            dugme.click()
        expect(strana.locator("html")).to_have_attribute("lang", ocekivani)

    def test_izbor_se_pamti(self):
        strana, zapis = self.otvori("seme-jezik-tok")
        self.odigraj_krug(strana, 1, OPUS_HIGH)
        self.assertIsNone(self.kolacic_jezika(strana.context))
        expect(strana.locator("#jezik-dugme")).to_have_text("English")
        pre = datetime.datetime.now(datetime.timezone.utc).timestamp()
        self.promeni_jezik(strana, "en")
        expect(strana).to_have_title("Orchestrator")
        expect(strana.locator("#krug")).to_have_text("Round 2 of 8")
        expect(strana.locator("#jezik-dugme")).to_have_text("Српски")
        expect(strana.locator("#jezik-forma")).to_have_attribute("aria-label", "Language")
        kolacic = self.kolacic_jezika(strana.context)
        self.assertEqual(kolacic["value"], "en")
        self.assertTrue(kolacic["httpOnly"])
        self.assertEqual(kolacic["sameSite"], "Lax")
        self.assertEqual(kolacic["path"], "/")
        # 365 dana (plan 12.2), ne kolacic do zatvaranja pregledaca.
        self.assertAlmostEqual(kolacic["expires"] - pre, 365 * 24 * 60 * 60, delta=120)

        # Osvezavanje i nova kartica: kolacic je jaci od jezika pregledaca (kontekst je sr-RS).
        strana.reload()
        expect(strana.locator("#krug")).to_have_text("Round 2 of 8")
        nova = strana.context.new_page()
        zapis_nove = Zapis(nova)
        nova.goto(self.live_server_url + "/")
        expect(nova.locator("html")).to_have_attribute("lang", "en")
        expect(nova.locator("#krug")).to_have_text("Round 2 of 8")
        self.proveri_cisto(zapis_nove)

        # Nazad na srpski istim dugmetom.
        self.promeni_jezik(strana, "sr")
        expect(strana.locator("#krug")).to_have_text("Круг 2 од 8")
        self.assertEqual(self.kolacic_jezika(strana.context)["value"], "sr")
        self.proveri_cisto(zapis)

    def test_promena_jezika_usred_partije(self):
        seme = nadji_seme(po_tezini, lambda i: motor.TIHI_NEUSPEH in i and motor.DORADA in i)
        referenca = odigraj_celu(seme, po_tezini)
        strana, zapis = self.otvori(seme)
        for krug in range(1, 5):
            self.odigraj_krug(strana, krug, po_tezini(krug))
        posle_cetiri = motor.nova_igra(seme)
        for krug in range(1, 5):
            posle_cetiri = motor.odigraj_potez(posle_cetiri, krug, po_tezini(krug))
        expect(strana.locator('#budzet [data-mesto="potroseno"]')).to_have_text(
            zarez(posle_cetiri["potroseno"], 2) + " $"
        )
        # Izabrano a neposlato se gubi pri promeni (prihvaceno u planu 12.5); stanje ostaje.
        self.izaberi(strana, po_tezini(5))
        self.promeni_jezik(strana, "en")
        expect(strana.locator("#krug")).to_have_text("Round 5 of 8")
        expect(strana.locator("#zadatak")).to_have_text(ZADACI_EN["model"])
        expect(strana.locator('#budzet [data-mesto="potroseno"]')).to_have_text(
            f"${posle_cetiri['potroseno']:.2f}"
        )
        expect(strana.locator('#rok [data-mesto="potroseno"]')).to_have_text(f"{posle_cetiri['minuti']:.1f} min")
        cetvrti = posle_cetiri["istorija"][3]
        rezultat = strana.locator("#rezultat")
        expect(rezultat.locator('[data-mesto="zadatak"]')).to_have_text("Round 4: " + ZADACI_EN["crud"])
        expect(rezultat.locator('[data-mesto="status"]')).to_have_text(
            "sent back for rework" if cetvrti["ishod"] == motor.DORADA else "done"
        )
        self.assertEqual(strana.locator("input.btn-check:checked").count(), 0)

        for krug in range(5, 9):
            self.odigraj_krug(strana, krug, po_tezini(krug))
        kraj = referenca["rezultat"]
        zavrsni = strana.locator("#zavrsni")
        expect(strana.locator("#krug")).to_have_text("Game over")
        expect(zavrsni.locator('[data-mesto="poeni"]')).to_have_text(str(kraj["poeni"]))
        expect(zavrsni.locator('[data-mesto="ocena"]')).to_have_text(OCENE_EN[kraj["ocena"]])
        expect(zavrsni.locator('[data-mesto="cena"]')).to_have_text(f"${kraj['ukupna_cena']:.2f}")
        expect(zavrsni.locator('[data-mesto="minuti"]')).to_have_text(f"{kraj['ukupni_minuti']:.1f} min")
        expect(zavrsni.locator('[data-mesto="tihe"] li')).to_have_count(len(kraj["tihe_greske"]))
        expect(zavrsni.locator('[data-mesto="tihe"] li').first).to_contain_text(
            ZADACI_EN[kraj["tihe_greske"][0]["zadatak"]]
        )
        expect(zavrsni.locator('[data-mesto="napomena"]')).to_have_text(NAPOMENA_EN)
        # Server: ista partija kao da jezik nije menjan.
        kljuc = {k["name"]: k["value"] for k in strana.context.cookies()}["sessionid"]
        self.assertEqual(SessionStore(session_key=kljuc)["igra"], referenca)
        self.proveri_cisto(zapis)

    def test_engleska_igra_bez_cirilice(self):
        upisi_red("Пера Перић", 90)
        upisi_red("Ана", 30)
        strana, zapis = self.otvori(seme_najduze_partije(), jezik=ENGLESKI)

        def proveri(s, oznaka):
            tekst = s.evaluate(JS_VIDLJIV_TEKST)
            with self.subTest(ekran=oznaka):
                self.assertGreater(len(tekst), 100)
                self.assertEqual(CIRILICA.findall(tekst), [])

        expect(strana.locator('#rang-redovi [data-mesto="ime"]')).to_have_text(["Пера Перић", "Ана"])
        proveri(strana, "pocetak")
        for krug in range(1, 9):
            self.odigraj_krug(strana, krug, najduza_partija(krug))
            proveri(strana, f"krug {krug}")
        expect(strana.locator('#zavrsni [data-mesto="lekcije"] li')).to_have_count(5)
        expect(strana.locator('#zavrsni [data-mesto="tihe"] li')).to_have_count(3)
        expect(strana.locator('#zavrsni [data-mesto="lekcije"] li').first).to_contain_text("(section 4.2)")
        odgovor = self.podeli_i_cekaj(strana)
        self.assertEqual(odgovor.status, 200)
        self.assertRegex(odgovor.json()["istice"], r"^\d{4}-\d{2}-\d{2}$")
        expect(strana.locator("#deli-rok")).to_have_text(f"Link valid until {odgovor.json()['istice']}.")
        proveri(strana, "zavrsni sa blokom deljenja")

        # Potvrda nove igre na engleskom (partija nije sacuvana).
        poruke = []
        strana.once("dialog", lambda d: (poruke.append(d.message), d.dismiss()))
        strana.locator("#nova-forma button").click()
        self.assertEqual(poruke, [PITANJE_NOVA_EN])
        strana.locator("#rang-ime").fill("Пера")
        expect(strana.locator("#rang-sacuvaj")).to_have_text("Save result")
        self.assertEqual(self.sacuvaj_i_cekaj(strana, "Пера").status, 200)
        expect(strana.locator("#rang-poruka")).to_have_text("Result saved.")
        proveri(strana, "posle cuvanja")
        self.proveri_cisto(zapis)

        # Deljena strana i 404 na engleskom, sa imenom igraca cirilicom.
        deljena = self.novi_kontekst(jezik=ENGLESKI).new_page()
        zapis_deljene = Zapis(deljena)
        self.assertEqual(deljena.goto(odgovor.json()["url"]).status, 200)
        expect(deljena.locator("html")).to_have_attribute("lang", "en")
        expect(deljena.locator("#deljeno-ime")).to_have_text("Пера")
        expect(deljena.locator("#jezik-link")).to_have_text("Српски")
        proveri(deljena, "deljena strana")
        self.proveri_cisto(zapis_deljene)
        nedostupna = self.novi_kontekst(jezik=ENGLESKI).new_page()
        self.assertEqual(nedostupna.goto(self.live_server_url + "/r/" + "x" * 22 + "/").status, 404)
        expect(nedostupna.locator("#nedostupno h2")).to_have_text("This result is no longer available.")
        proveri(nedostupna, "deljena 404")

        # Kontrola: ista provera na srpskoj strani nalazi cirilicu.
        srpska = self.novi_kontekst().new_page()
        srpska.goto(self.live_server_url + "/")
        self.assertTrue(CIRILICA.findall(srpska.evaluate(JS_VIDLJIV_TEKST)))

    def test_navigator_share_na_engleskom(self):
        strana, zapis = self.otvori_zavrseno("seme-share-en", skripta=JS_LAZNI_SHARE, jezik=ENGLESKI)
        odgovor = self.podeli_i_cekaj(strana)
        self.assertEqual(odgovor.status, 200)
        url = odgovor.json()["url"]
        posalji = strana.locator("#deli-posalji")
        expect(posalji).to_have_text("Send")
        posalji.click()
        strana.wait_for_function("() => window.__poslato.length === 1")
        self.assertEqual(
            strana.evaluate("() => window.__poslato"),
            [{"title": "Orchestrator", "text": "My result in the game Orchestrator", "url": url}],
        )
        self.proveri_cisto(zapis)

    def test_deljena_link_jezika(self):
        red = upisi_deljeno()
        strana = self.novi_kontekst().new_page()
        zapis = Zapis(strana)
        dokument = strana.goto(f"{self.live_server_url}/r/{red.token}/")
        self.assertEqual(dokument.status, 200)
        expect(strana.locator("html")).to_have_attribute("lang", "sr")
        link = strana.locator("#jezik-link")
        expect(link).to_have_text("English")
        with strana.expect_navigation():
            link.click()
        expect(strana.locator("html")).to_have_attribute("lang", "en")
        expect(strana).to_have_title("Shared result · Orchestrator")
        expect(strana.locator('#zavrsni [data-mesto="napomena"]')).to_have_text(NAPOMENA_EN)
        self.assertTrue(strana.url.endswith("?jezik=en"), strana.url)
        # Bez kolacica: ni jezika ni sesije.
        self.assertEqual(strana.context.cookies(), [])
        with strana.expect_navigation():
            strana.locator("#jezik-link").click()
        expect(strana.locator("html")).to_have_attribute("lang", "sr")
        self.proveri_cisto(zapis)


# Plan 13.7 T-T: novo bodovanje u pregledacu. Tekst je prepisan iz plana 13.3 i 13.4, ne cita se iz kataloga.
NBSP = " "
MINUS = "−"
OZNAKA_STARIH = {"sr": "старо бодовање", "en": "old scoring"}
LEGENDA_STARIH = {
    "sr": "Старо бодовање: резултат је бодован по ранијим правилима, са другачијим казнама за тиху грешку и буџет.",
    "en": "Old scoring: this result was scored under the earlier rules, with different penalties for silent errors "
          "and the budget.",
}
BUDZET_OSNOVNO = {"sr": "Буџет је прекорачен.", "en": "Budget exceeded."}
# Snimci ekrana za izvestaj qa: samo kad je zadat folder (van projekta); test ne zavisi od njih.
SNIMCI = os.environ.get("ORKESTRATOR_SNIMCI")


def tekst_kazne(jezik, procenat, kazna):
    if jezik == "sr":
        return f"Буџет је прекорачен за {procenat}{NBSP}% ({MINUS}{kazna} поена)."
    return f"Budget exceeded by {procenat}% ({MINUS}{kazna} points)."


# Za svaki red liste: ime, da li je oznaka vidljiva, njen tekst, broj redova teksta oznake i da li je ispod ocene.
JS_OZNAKE_REDOVA = """() => Array.from(document.querySelectorAll('#rang-redovi tr')).map((tr) => {
  const oznaka = tr.querySelector('[data-mesto="pravila"]');
  const ocena = tr.querySelector('[data-mesto="ocena"]');
  const vidljiva = oznaka.getClientRects().length > 0 && getComputedStyle(oznaka).display !== 'none';
  const o = document.createRange();
  o.selectNodeContents(oznaka);
  const vrhovi = new Set(Array.from(o.getClientRects()).filter((r) => r.width > 0).map((r) => Math.round(r.top)));
  const b = oznaka.getBoundingClientRect();
  const c = ocena.getBoundingClientRect();
  return {
    ime: tr.querySelector('[data-mesto="ime"]').textContent,
    vidljiva: vidljiva,
    tekst: oznaka.textContent,
    redova: vidljiva ? vrhovi.size : 0,
    ispod: vidljiva ? b.top >= c.bottom - 1 : null,
  };
})"""

JS_BUDZET = """() => {
  const blok = document.querySelector('#zavrsni [data-mesto="budzet-prekoracen"]');
  const osnovno = blok.querySelector('[data-mesto="budzet-osnovno"]');
  const iznos = blok.querySelector('[data-mesto="budzet-iznos"]');
  const vidljiv = (e) => e.getClientRects().length > 0;
  return {blok: vidljiv(blok), osnovno: vidljiv(osnovno), iznos: vidljiv(iznos),
          tekst_osnovno: osnovno.textContent, tekst_iznos: iznos.textContent};
}"""


class BodovanjeTokTests(OsnovaToka):
    """Oznaka starih redova, legenda, tekst kazne budzeta i stari snimci (plan 13.3, 13.4)."""

    def snimi(self, strana, ime):
        if SNIMCI:
            strana.wait_for_function("() => document.getAnimations().length === 0")
            strana.screenshot(path=os.path.join(SNIMCI, f"{ime}.png"), full_page=True, animations="disabled")

    def otvori_pred_osmi(self, stanje, dimenzije, jezik):
        """Kao otvori, ali partija stoji pred 8. krugom."""
        sesija = SessionStore()
        sesija["igra"] = stanje
        sesija.create()
        kontekst = self.novi_kontekst(dimenzije, jezik=jezik)
        kontekst.add_cookies([{"name": settings.SESSION_COOKIE_NAME, "value": sesija.session_key,
                               "url": self.live_server_url}])
        strana = kontekst.new_page()
        zapis = Zapis(strana)
        strana.goto(self.live_server_url + "/")
        expect(strana.locator("#krug")).to_have_text(KRUG_TEKST[jezik[:2]].format(8))
        return strana, zapis

    def budzet(self, strana):
        strana.wait_for_function("() => document.getAnimations().length === 0")
        return strana.evaluate(JS_BUDZET)

    def oznake(self, strana):
        return {r["ime"]: r for r in strana.evaluate(JS_OZNAKE_REDOVA)}

    # --- rang lista ---

    def test_375_stari_red_oznaka_i_legenda_bez_preliva(self):
        self.proveri_usku_listu_sa_starim(SRPSKI)

    def test_375_stari_red_oznaka_i_legenda_bez_preliva_en(self):
        self.proveri_usku_listu_sa_starim(ENGLESKI)

    def proveri_usku_listu_sa_starim(self, jezik):
        jez = jezik[:2]
        # Najsira imena i najduza ocena (en "excellent orchestrator"); svaki drugi red je verzije 1.
        pocetak = timezone.now() - datetime.timedelta(days=30)
        stari = set()
        for rb in range(10):
            ime = ("Ш" * 19 if rb % 2 else "W" * 19) + str(rb)
            pravila = 1 if rb % 2 == 0 else 2
            if pravila == 1:
                stari.add(ime)
            upisi_red(ime, 100 - rb, pocetak + datetime.timedelta(days=rb), "odlican", pravila=pravila)
        seme = nadji_seme(sve_opus, lambda i: i == [motor.USPEH] * 8)
        strana, zapis = self.otvori_zavrseno(seme, TELEFON, jezik=jezik)
        expect(strana.locator("#rang-redovi tr")).to_have_count(10)
        legenda = strana.locator("#rang-legenda")
        expect(legenda).to_be_visible()
        expect(legenda).to_have_text(LEGENDA_STARIH[jez])
        # Legenda je posle tabele, ne u njoj.
        self.assertTrue(strana.evaluate(
            "() => !!(document.getElementById('rang-tabela').compareDocumentPosition("
            "document.getElementById('rang-legenda')) & Node.DOCUMENT_POSITION_FOLLOWING)"
        ))
        for sirina, visina in USKI_EKRANI:
            strana.set_viewport_size({"width": sirina, "height": visina})
            strana.wait_for_function("() => document.getAnimations().length === 0")
            self.assertEqual(strana.evaluate("() => document.documentElement.clientWidth"), sirina)
            self.proveri_bez_prelivanja(strana, f"lista sa starim redovima, {sirina} px")
            with self.subTest(sirina=sirina):
                self.assertEqual(strana.evaluate(JS_RANG_CELIJE), [])
                redovi = self.oznake(strana)
                self.assertEqual(len(redovi), 10)
                self.assertEqual({ime for ime, r in redovi.items() if r["vidljiva"]}, stari)
                for ime in stari:
                    self.assertEqual(redovi[ime]["tekst"], OZNAKA_STARIH[jez])
                    # Oznaka u svom redu, ispod ocene (plan 13.3).
                    self.assertTrue(redovi[ime]["ispod"], redovi[ime])
                    if sirina >= TELEFON[0]:
                        self.assertEqual(redovi[ime]["redova"], 1, redovi[ime])
        self.snimi(strana, f"rang-stari-375-{jez}")
        for dimenzije, oznaka in ((TABLET, "768"), (RACUNAR, "1440")):
            strana.set_viewport_size({"width": dimenzije[0], "height": dimenzije[1]})
            self.proveri_bez_prelivanja(strana, f"lista sa starim redovima, {oznaka} px")
            self.assertEqual({ime for ime, r in self.oznake(strana).items() if r["vidljiva"]}, stari)
            self.snimi(strana, f"rang-stari-{oznaka}-{jez}")
        self.proveri_cisto(zapis)

    def test_bez_starih_redova_nema_oznake_ni_legende(self):
        for rb in range(3):
            upisi_red(f"Нови {rb}", 90 - rb, pravila=parametri.PRAVILA_TEKUCA)
        strana, zapis = self.otvori("seme-bez-starih", TELEFON)
        expect(strana.locator("#rang-redovi tr")).to_have_count(3)
        expect(strana.locator("#rang-legenda")).to_be_hidden()
        self.assertEqual([r["vidljiva"] for r in self.oznake(strana).values()], [False] * 3)
        self.assertNotIn(OZNAKA_STARIH["sr"], strana.locator("#rang").inner_text())
        self.proveri_cisto(zapis)

    # --- zavrsni ekran ---

    def test_zavrsni_granica_10_posto(self):
        self.proveri_granicu(SRPSKI)

    def test_zavrsni_granica_10_posto_en(self):
        self.proveri_granicu(ENGLESKI)

    def proveri_granicu(self, jezik):
        # Isti put kao igrac: poslednji krug se igra u pregledacu, tekst sastavlja skripta.
        jez = jezik[:2]
        seme = seme_uspesnog_osmog()
        for opis, cena, procenat, kazna, poeni in (
            ("10", 26.40, 10, 10, 90),
            ("10-01", 26.4024, 11, 20, 80),
        ):
            with self.subTest(opis=opis):
                strana, zapis = self.otvori_pred_osmi(stanje_pred_osmi(seme, cena), TELEFON, jezik)
                self.odigraj_krug(strana, 8, OPUS_HIGH)
                expect(strana.locator('#zavrsni [data-mesto="poeni"]')).to_have_text(str(poeni))
                b = self.budzet(strana)
                self.assertEqual((b["blok"], b["osnovno"], b["iznos"]), (True, False, True), b)
                self.assertEqual(b["tekst_iznos"], tekst_kazne(jez, procenat, kazna))
                self.proveri_bez_prelivanja(strana, f"zavrsni {opis} %, 375 px")
                self.snimi(strana, f"zavrsni-{opis}-375-{jez}")
                # Osvezavanje crta isto iz stanja.
                strana.reload()
                expect(strana.locator("#zavrsni")).to_be_visible()
                self.assertEqual(self.budzet(strana)["tekst_iznos"], tekst_kazne(jez, procenat, kazna))
                self.proveri_cisto(zapis)

    def test_stara_zavrsena_sesija_osnovni_tekst_i_oznaka(self):
        seme = nadji_seme(sve_opus, lambda i: i == SEME_JEDNA_TIHA)
        staro = bez_verzije(odigraj_celu(seme, sve_opus, pravila=1))
        strana, zapis = self.otvori(seme, TELEFON, stanje=staro)
        expect(strana.locator('#zavrsni [data-mesto="poeni"]')).to_have_text("25")
        b = self.budzet(strana)
        self.assertEqual((b["blok"], b["osnovno"], b["iznos"]), (True, True, False), b)
        self.assertEqual(b["tekst_osnovno"], BUDZET_OSNOVNO["sr"])
        self.assertEqual(b["tekst_iznos"], "")
        self.snimi(strana, "zavrsni-stara-sesija-375-sr")
        self.assertEqual(self.sacuvaj_i_cekaj(strana, "Стари").status, 200)
        self.assertEqual(Rezultat.objects.get().pravila, 1)
        self.assertEqual([r["vidljiva"] for r in self.oznake(strana).values()], [True])
        expect(strana.locator("#rang-legenda")).to_be_visible()
        self.proveri_bez_prelivanja(strana, "posle cuvanja stare partije, 375 px")
        self.proveri_cisto(zapis)

    def test_stara_nezavrsena_sesija_do_kraja_pa_nova(self):
        seme = nadji_seme(sve_opus, lambda i: i == SEME_JEDNA_TIHA)
        strana, zapis = self.otvori(seme, TELEFON, stanje=bez_verzije(motor.nova_igra(seme)))
        self.odigraj_celu_u_pregledacu(strana, sve_opus)
        # Pravila 1: 100 - 25 - 30 - 20; 32,40 $ je 35 %.
        expect(strana.locator('#zavrsni [data-mesto="poeni"]')).to_have_text("25")
        b = self.budzet(strana)
        self.assertEqual((b["osnovno"], b["iznos"]), (False, True), b)
        self.assertEqual(b["tekst_iznos"], tekst_kazne("sr", 35, 30))
        self.snimi(strana, "zavrsni-stara-nezavrsena-375-sr")
        self.assertEqual(self.sacuvaj_i_cekaj(strana, "Стари").status, 200)
        self.assertEqual(Rezultat.objects.get(ime="Стари").pravila, 1)
        self.assertEqual({i: r["vidljiva"] for i, r in self.oznake(strana).items()}, {"Стари": True})
        expect(strana.locator("#rang-legenda")).to_be_visible()

        # Nova partija (posle cuvanja bez potvrde) je verzije 2: red bez oznake, legenda ostaje zbog starog.
        with strana.expect_navigation():
            strana.locator("#nova-forma button").click()
        expect(strana.locator("#krug")).to_have_text("Круг 1 од 8")
        self.odigraj_celu_u_pregledacu(strana, sve_opus)
        # Seme nove partije bira server; bez prekoracenja blok je skriven, sa njim nosi iznos. Osnovni tekst nikad.
        b = self.budzet(strana)
        self.assertEqual((b["iznos"], b["osnovno"]), (b["blok"], False), b)
        self.assertEqual(self.sacuvaj_i_cekaj(strana, "Нови").status, 200)
        self.assertEqual(Rezultat.objects.get(ime="Нови").pravila, 2)
        oznake = {i: r["vidljiva"] for i, r in self.oznake(strana).items()}
        self.assertEqual(oznake, {"Стари": True, "Нови": False})
        expect(strana.locator("#rang-legenda")).to_be_visible()
        self.proveri_bez_prelivanja(strana, "stari i novi red, 375 px")
        self.snimi(strana, "rang-stari-i-novi-375-sr")
        self.proveri_cisto(zapis)

    # --- deljena strana ---

    def test_deljena_stari_snimak_samo_osnovni_tekst(self):
        stanje = odigraj_celu(nadji_seme(sve_opus, lambda i: i == SEME_JEDNA_TIHA), sve_opus, pravila=1)
        red = upisi_deljeno(stanje)
        snimak = dict(red.zavrsni)
        DeljeniRezultat.objects.filter(id=red.id).update(
            zavrsni={k: v for k, v in snimak.items() if k not in ("budzet_procenat", "kazna_budzet")}
        )
        Rezultat.objects.create(ime="Стари", poeni=25, ocena="pozar", pravila=1, partija=red.partija)
        novi = upisi_deljeno(odigraj_celu("seme-deljeno-novo-bodovanje", sve_opus))
        self.assertTrue(novi.zavrsni["budzet_prekoracen"])
        for jezik in (SRPSKI, ENGLESKI):
            jez = jezik[:2]
            with self.subTest(jezik=jez):
                strana = self.novi_kontekst(TELEFON, jezik=jezik).new_page()
                zapis = Zapis(strana)
                self.assertEqual(strana.goto(f"{self.live_server_url}/r/{red.token}/").status, 200)
                expect(strana.locator("#deljeno-ime")).to_have_text("Стари")
                b = self.budzet(strana)
                self.assertEqual((b["blok"], b["osnovno"], b["iznos"]), (True, True, False), b)
                self.assertEqual(b["tekst_osnovno"], BUDZET_OSNOVNO[jez])
                # Deljena strana nema oznaku verzije (plan 13.3).
                self.assertNotIn(OZNAKA_STARIH[jez], strana.locator("body").inner_text())
                self.assertEqual(strana.locator(".rang-pravila, #rang-legenda").count(), 0)
                self.proveri_bez_prelivanja(strana, f"deljena, stari snimak, {jez}")
                self.snimi(strana, f"deljena-stari-snimak-375-{jez}")
                self.proveri_cisto(zapis)

                # Kontrola: nov snimak na deljenoj strani pokazuje iznos.
                strana.goto(f"{self.live_server_url}/r/{novi.token}/")
                b = self.budzet(strana)
                self.assertEqual((b["osnovno"], b["iznos"]), (False, True), b)
                z = novi.zavrsni
                self.assertEqual(b["tekst_iznos"], tekst_kazne(jez, z["budzet_procenat"], z["kazna_budzet"]))


# Moderator u pregledacu (plan 14.8, red tok). Tekst je prepisan iz plana 14.7, ne cita se iz kataloga.
SIRINE_MODERATORA = ((320, 640), TELEFON, RACUNAR)
DUGO_IME = "Moderator_sa_veoma_dugackim_korisnickim_imenom_bez_ijednog_razmaka_2026"
SIROKO_IME = "Ш" * 20
OBAVEZNA_PROMENA = {"sr": "Морате да промените лозинку пре наставка.",
                    "en": "You must change your password before continuing."}
ISTA_LOZINKA = {"sr": ISTA_LOZINKA_SR, "en": ISTA_LOZINKA_EN}
# Kao JS_PRELIVANJE, ali bez sadrzaja .visually-hidden (Bootstrap: 1 px, clip), koji se ne vidi i ne pravi skrol;
# skrol cele strane i dalje meri scrollWidth.
JS_PRELIVANJE_MOD = JS_PRELIVANJE.replace(
    "if (e.closest('template') ||", "if (e.closest('template, .visually-hidden') ||"
).replace(
    "    const r = e.getBoundingClientRect();\n    if (r.width === 0 || r.height === 0) continue;\n    if (e.scrollWidth",
    "    if (e.closest('.visually-hidden')) continue;\n    const r = e.getBoundingClientRect();\n"
    "    if (r.width === 0 || r.height === 0) continue;\n    if (e.scrollWidth",
)
assert JS_PRELIVANJE_MOD.count(".visually-hidden") == 2, "JS_PRELIVANJE se promenio; uskladi JS_PRELIVANJE_MOD"


@override_settings(PASSWORD_HASHERS=BRZI_HES)
class ModeratorTokTests(OsnovaToka):
    def setUp(self):
        super().setUp()
        obrisi_brojace()  # brojac neuspeha prijave je u bazi, zajednickoj za test nit i live server
        self.addCleanup(obrisi_brojace)

    def adresa(self, putanja):
        return self.live_server_url + putanja

    def snimi(self, strana, ime):
        if SNIMCI:
            strana.wait_for_function("() => document.getAnimations().length === 0")
            strana.screenshot(path=os.path.join(SNIMCI, f"{ime}.png"), full_page=True, animations="disabled")

    def posalji(self, strana, forma="form.mod-forma"):
        with strana.expect_navigation():
            strana.locator(forma).locator("button[type=submit]").click()

    def prijavi(self, strana, ime, lozinka=LOZINKA):
        strana.goto(self.adresa("/moderator/prijava/"))
        strana.locator("#username").fill(ime)
        strana.locator("#password").fill(lozinka)
        self.posalji(strana)

    def proveri_bez_prelivanja_mod(self, strana, oznaka):
        mere = strana.evaluate(JS_PRELIVANJE_MOD)
        with self.subTest(ekran=oznaka):
            self.assertLessEqual(mere["skrol"], mere["sirina"], mere)
            self.assertEqual(mere["van"], [])
            self.assertEqual(mere["odseceno"], [])

    def nova_strana(self, dimenzije=RACUNAR, jezik=SRPSKI):
        strana = self.novi_kontekst(dimenzije, jezik=jezik).new_page()
        return strana, Zapis(strana)

    def meni(self, strana):
        return [t.strip() for t in strana.locator(".mod-meni li").all_inner_texts()]

    # --- tok glavnog moderatora ---

    def test_glavni_ceo_tok(self):
        nalozi.dodaj(None, "Glavni", LOZINKA, glavni=True)  # kao komanda: pocetna lozinka
        prvi = upisi_red("Први", 90)
        upisi_red("Други", 80)
        strana, zapis = self.nova_strana()
        strana.goto(self.adresa("/moderator/"))
        expect(strana).to_have_url(self.adresa("/moderator/prijava/?next=/moderator/"))
        strana.locator("#username").fill("Glavni")
        strana.locator("#password").fill(LOZINKA)
        self.posalji(strana)

        # Pocetna lozinka: samo strana lozinke i odjava.
        expect(strana).to_have_url(self.adresa("/moderator/lozinka/"))
        expect(strana.locator(".mod-poruka-info")).to_have_text(OBAVEZNA_PROMENA["sr"])
        self.assertEqual(self.meni(strana), ["Одјави се"])
        self.snimi(strana, "mod-tok-1-obavezna-promena")
        strana.locator("#old_password").fill(LOZINKA)
        strana.locator("#new_password1").fill(LOZINKA3)
        strana.locator("#new_password2").fill(LOZINKA3)
        self.posalji(strana)
        expect(strana).to_have_url(self.adresa("/moderator/"))
        self.assertEqual(self.meni(strana), ["Преглед", "Дневник", "Статистика", "Лозинка", "Модератори", "Одјави се"])

        # Dodaje moderatora.
        with strana.expect_navigation():
            strana.locator(".mod-meni a", has_text="Модератори").click()
        strana.locator("#ime").fill("Mod")
        strana.locator("#lozinka1").fill(LOZINKA2)
        strana.locator("#lozinka2").fill(LOZINKA2)
        strana.locator("#moja_lozinka").fill(LOZINKA3)
        self.posalji(strana)
        expect(strana).to_have_url(self.adresa("/moderator/nalozi/"))
        stavka = strana.locator("li.mod-stavka", has_text="Mod")
        expect(stavka).to_contain_text("мора да промени лозинку")
        self.snimi(strana, "mod-tok-2-nalozi-posle-dodavanja")

        # Brise rezultat uz potvrdu.
        with strana.expect_navigation():
            strana.locator(".mod-meni a", has_text="Преглед").click()
        with strana.expect_navigation():
            strana.locator("li.mod-stavka", has_text="Први").locator("a.mod-obrisi").click()
        expect(strana).to_have_url(self.adresa(f"/moderator/rezultat/{prvi.id}/"))
        expect(strana.locator("h1")).to_have_text("Обрисати овај резултат?")
        self.snimi(strana, "mod-tok-3-potvrda")
        self.assertTrue(Rezultat.objects.filter(pk=prvi.id).exists())  # GET ne brise
        self.posalji(strana, "form.mod-potvrda")
        expect(strana).to_have_url(self.adresa("/moderator/?poruka=obrisano"))
        expect(strana.locator(".mod-poruka-ok")).to_have_text("Обрисано.")
        expect(strana.locator("li.mod-stavka", has_text="Први")).to_have_count(0)
        expect(strana.locator("li.mod-stavka", has_text="Други")).to_have_count(1)

        # Cita dnevnik.
        with strana.expect_navigation():
            strana.locator(".mod-meni a", has_text="Дневник").click()
        zapisi = strana.locator("li.mod-zapis")
        expect(zapisi).to_have_count(4)  # dodat (komanda), promenjena, dodat, obrisan
        expect(zapisi.nth(0)).to_contain_text("обрисан резултат")
        expect(zapisi.nth(0)).to_contain_text("Први")
        expect(zapisi.nth(1)).to_contain_text("додат модератор")
        expect(zapisi.nth(2)).to_contain_text("промењена лозинка")
        expect(zapisi.nth(3)).to_contain_text("развијалац (команда)")
        self.snimi(strana, "mod-tok-4-dnevnik")

        # Odjava.
        self.posalji(strana, ".mod-meni form")
        expect(strana).to_have_url(self.adresa("/moderator/prijava/"))
        strana.goto(self.adresa("/moderator/"))
        expect(strana).to_have_url(self.adresa("/moderator/prijava/?next=/moderator/"))
        self.proveri_cisto(zapis)
        self.assertFalse(Rezultat.objects.filter(pk=prvi.id).exists())
        self.assertEqual(
            list(ZapisDnevnika.objects.order_by("id").values_list("radnja", flat=True)),
            ["moderator_dodat", "lozinka_promenjena", "moderator_dodat", "rezultat_obrisan"],
        )

    def test_moderator_nema_stavku_a_url_daje_403(self):
        napravi_moderatora("Glavni", glavni=True)
        napravi_moderatora("Mod")
        strana, zapis = self.nova_strana(TELEFON)
        self.prijavi(strana, "Mod")
        expect(strana).to_have_url(self.adresa("/moderator/"))
        self.assertEqual(self.meni(strana), ["Преглед", "Дневник", "Статистика", "Лозинка", "Одјави се"])
        self.assertEqual(strana.locator('a[href="/moderator/nalozi/"]').count(), 0)
        dokument = strana.goto(self.adresa("/moderator/nalozi/"))
        self.assertEqual(dokument.status, 403)
        expect(strana.locator("h1")).to_have_text(TEKST_403)
        self.proveri_bez_prelivanja_mod(strana, "403, 375 px")
        self.snimi(strana, "mod-tok-403-375-sr")
        # Tacno jedan 4xx, i to bas ovaj dokument.
        self.assertEqual(zapis.losi_odgovori(), [f"403 {self.adresa('/moderator/nalozi/')}"])
        self.assertEqual(len(zapis.konzola), 1, zapis.konzola)
        self.assertIn("403", zapis.konzola[0])
        self.assertEqual((zapis.izuzeci, zapis.neuspeli), ([], []))
        with strana.expect_navigation():
            strana.locator("main a", has_text="Преглед").click()
        expect(strana).to_have_url(self.adresa("/moderator/"))

    def test_prijava_ne_prekida_igru(self):
        napravi_moderatora("Mod")
        strana, zapis = self.otvori("seme-prijava-u-drugoj-kartici", RACUNAR)
        self.odigraj_krug(strana, 1, OPUS_HIGH)
        druga = strana.context.new_page()
        zapis_druge = Zapis(druga)
        self.prijavi(druga, "Mod")
        expect(druga).to_have_url(self.adresa("/moderator/"))
        # Prijava menja kljuc sesije i CSRF kolacic; kartica igre igra dalje bez osvezavanja.
        self.odigraj_krug(strana, 2, OPUS_HIGH)
        self.posalji(druga, ".mod-meni form")
        expect(druga).to_have_url(self.adresa("/moderator/prijava/"))
        self.odigraj_krug(strana, 3, OPUS_HIGH)
        strana.reload()
        expect(strana.locator("#krug")).to_have_text(KRUG_TEKST["sr"].format(4))
        self.proveri_cisto(zapis)
        self.proveri_cisto(zapis_druge)

    def test_ista_lozinka_poruka(self):
        """Obavezna promena, nova = stara: jedna poruka forme, bez polja .is-invalid, vidljiva na 320/375/1440."""
        for jezik in (SRPSKI, ENGLESKI):
            jez = jezik[:2]
            with self.subTest(jez):
                ime = f"Novajlija{jez}"
                napravi_moderatora(ime, mora_promeniti=True)
                strana, zapis = self.nova_strana(jezik=jezik)
                self.prijavi(strana, ime)
                expect(strana).to_have_url(self.adresa("/moderator/lozinka/"))
                strana.locator("#old_password").fill(LOZINKA)
                strana.locator("#new_password1").fill(LOZINKA)
                strana.locator("#new_password2").fill(LOZINKA)
                self.posalji(strana)
                expect(strana).to_have_url(self.adresa("/moderator/lozinka/"))
                greska = strana.locator(".mod-poruka-greska")
                expect(greska).to_have_count(1)
                expect(greska).to_have_text(ISTA_LOZINKA[jez])
                self.assertEqual(strana.locator(".is-invalid").count(), 0)
                self.assertNotIn(LOZINKA, strana.content())
                for sirina, visina in SIRINE_MODERATORA:
                    strana.set_viewport_size({"width": sirina, "height": visina})
                    strana.wait_for_function("() => document.getAnimations().length === 0")
                    self.proveri_bez_prelivanja_mod(strana, f"ista lozinka, {sirina} px, {jez}")
                    expect(greska).to_be_visible()
                    self.snimi(strana, f"mod-lozinka-ista-{sirina}-{jez}")
                # Lozinka nije promenjena: obavezna promena i dalje vraca na stranu lozinke.
                strana.goto(self.adresa("/moderator/dnevnik/"))
                expect(strana).to_have_url(self.adresa("/moderator/lozinka/"))
                self.proveri_cisto(zapis)

    # --- izgled svake strane: 320, 375 i 1440 px, sr i en ---

    def podaci_za_izgled(self):
        glavni = napravi_moderatora("Glavni", glavni=True)
        dug = napravi_moderatora(DUGO_IME)
        napravi_moderatora("Novajlija", mora_promeniti=True)
        neaktivan = napravi_moderatora("Neaktivan")
        type(neaktivan).objects.filter(pk=neaktivan.pk).update(is_active=False)
        rezultat = upisi_red(SIROKO_IME, 95)
        upisi_red("W" * 20, 94)
        upisi_red("</script><b>x", 50)
        link = upisi_deljeno()
        Rezultat.objects.create(ime="W" * 20 + "x", poeni=link.zavrsni["poeni"], ocena=link.zavrsni["ocena"],
                                pravila=parametri.PRAVILA_TEKUCA, partija=link.partija)
        upisi_deljeno()
        for radnja in ("moderator_dodat", "moderator_deaktiviran", "moderator_aktiviran", "lozinka_postavljena",
                       "lozinka_promenjena", "uloga_dodeljena", "uloga_oduzeta"):
            ZapisDnevnika.objects.upisi(radnja=radnja, ko=dug, nad=dug,
                                        snimak={"glavni": True} if radnja == "moderator_dodat" else {})
        brisanje.obrisi_rezultate([upisi_red(SIROKO_IME, 30).id], ko=None)
        brisanje.obrisi_deljene([upisi_deljeno().id], ko=glavni)
        return {"rezultat": rezultat, "link": link, "dug": dug, "neaktivan": neaktivan}

    def proveri_ekran(self, strana, ime, jez, greske=False):
        for sirina, visina in SIRINE_MODERATORA:
            strana.set_viewport_size({"width": sirina, "height": visina})
            strana.wait_for_function("() => document.getAnimations().length === 0")
            self.assertEqual(strana.evaluate("() => document.documentElement.clientWidth"), sirina)
            self.proveri_bez_prelivanja_mod(strana, f"{ime}, {sirina} px, {jez}")
            if greske:
                poruke = strana.locator(".invalid-feedback, .mod-poruka-greska")
                self.assertGreater(poruke.count(), 0, ime)
                for redni in range(poruke.count()):
                    expect(poruke.nth(redni)).to_be_visible()
            self.snimi(strana, f"mod-{ime}-{sirina}-{jez}")

    def test_strane_bez_prelivanja_sr(self):
        self.proveri_sve_strane(SRPSKI)

    def test_strane_bez_prelivanja_en(self):
        self.proveri_sve_strane(ENGLESKI)

    def proveri_sve_strane(self, jezik):
        jez = jezik[:2]
        podaci = self.podaci_za_izgled()
        strana, zapis = self.nova_strana(jezik=jezik)

        strana.goto(self.adresa("/moderator/prijava/"))
        expect(strana.locator("html")).to_have_attribute("lang", jez)
        self.proveri_ekran(strana, "prijava", jez)
        strana.locator("#username").fill("Glavni")
        strana.locator("#password").fill("pogresna")
        self.posalji(strana)
        self.proveri_ekran(strana, "prijava-greska", jez, greske=True)

        strana.locator("#username").fill("Glavni")
        strana.locator("#password").fill(LOZINKA)
        self.posalji(strana)
        expect(strana).to_have_url(self.adresa("/moderator/"))
        self.proveri_ekran(strana, "pregled", jez)
        strana.locator("#mod-token").fill(self.adresa(f"/r/{podaci['link'].token}/"))
        self.posalji(strana, "form.mod-forma:has(#mod-token)")
        expect(strana.locator("main li.mod-stavka").first).to_be_visible()
        self.proveri_ekran(strana, "pregled-pretraga", jez)

        strana.goto(self.adresa(f"/moderator/rezultat/{podaci['rezultat'].id}/"))
        self.proveri_ekran(strana, "potvrda-rezultata", jez)
        strana.goto(self.adresa(f"/moderator/link/{podaci['link'].id}/"))
        self.proveri_ekran(strana, "potvrda-linka", jez)
        strana.goto(self.adresa("/moderator/dnevnik/"))
        expect(strana.locator("li.mod-zapis")).to_have_count(9)
        self.proveri_ekran(strana, "dnevnik", jez)

        strana.goto(self.adresa("/moderator/lozinka/"))
        self.proveri_ekran(strana, "lozinka", jez)
        strana.locator("#old_password").fill("pogresna")
        strana.locator("#new_password1").fill("kratka")
        strana.locator("#new_password2").fill("druga")
        self.posalji(strana)
        self.proveri_ekran(strana, "lozinka-greske", jez, greske=True)

        strana.goto(self.adresa("/moderator/nalozi/"))
        self.proveri_ekran(strana, "nalozi", jez)
        strana.locator("#ime").fill(DUGO_IME.lower())
        strana.locator("#lozinka1").fill("12345")
        strana.locator("#lozinka2").fill("6789")
        strana.locator("#moja_lozinka").fill("pogresna")
        self.posalji(strana)
        self.proveri_ekran(strana, "nalozi-greske", jez, greske=True)

        strana.goto(self.adresa(f"/moderator/nalozi/{podaci['dug'].pk}/"))
        expect(strana.locator("h1")).to_have_text(DUGO_IME)
        self.proveri_ekran(strana, "nalog", jez)
        forma = 'form:has(input[name="radnja"][value="lozinka"])'
        strana.locator(forma).locator("#lozinka-lozinka1").fill("kratka")
        self.posalji(strana, forma)
        self.proveri_ekran(strana, "nalog-greske", jez, greske=True)
        strana.goto(self.adresa(f"/moderator/nalozi/{podaci['neaktivan'].pk}/"))
        self.proveri_ekran(strana, "nalog-neaktivan", jez)
        self.proveri_cisto(zapis)
        obrisi_brojace()  # tri pogresne potvrde za "Glavni"

        # Obavezna promena (drugi nalog) i 403 (obican moderator), svako u svom pregledacu.
        novajlija, zapis_novajlije = self.nova_strana(jezik=jezik)
        self.prijavi(novajlija, "Novajlija")
        expect(novajlija.locator(".mod-poruka-info")).to_have_text(OBAVEZNA_PROMENA[jez])
        self.proveri_ekran(novajlija, "lozinka-obavezna", jez)
        self.proveri_cisto(zapis_novajlije)
        moderator, zapis_moderatora = self.nova_strana(jezik=jezik)
        self.prijavi(moderator, DUGO_IME)
        self.assertEqual(moderator.goto(self.adresa("/moderator/nalozi/")).status, 403)
        self.proveri_ekran(moderator, "zabranjeno", jez)
        self.assertEqual(zapis_moderatora.losi_odgovori(), [f"403 {self.adresa('/moderator/nalozi/')}"])
        self.assertEqual((zapis_moderatora.izuzeci, zapis_moderatora.neuspeli), ([], []))


# ---------- javna isporuka u pregledacu (plan 15.4, 15.5, 15.11 T4) ----------

# Svako krsenje CSP-a u dokumentu, i pre prve skripte strane (init skripta ide pre nje).
CSP_SLUSALAC = """
window.__csp = [];
document.addEventListener("securitypolicyviolation", (e) => {
  window.__csp.push(e.violatedDirective + " " + (e.blockedURI || "-"));
});
"""
STRANI_HOST = "strani-host.example"
EKRANI_GRESAKA = ((320, 640), TELEFON, TABLET, RACUNAR)
# vrsta: status, h1 sr, h1 en (prepisano iz kataloga; plan 15.4)
STRANE_GRESAKA = {
    "400": (400, "Захтев није исправан.", "This request is not valid."),
    "403": (403, "Приступ није дозвољен.", "Access is not allowed."),
    "403_csrf": (403, "Страна је истекла.", "This page has expired."),
    "404": (404, "Ова страна не постоји.", "This page does not exist."),
    "500": (500, "Нешто је пошло по злу.", "Something went wrong."),
}
SERVER_GRESKA = {"sr": "Сервер није одговорио како треба. Покушајте поново.",
                 "en": "The server did not respond properly. Try again."}
# Telo koje Nginx salje uz limit_req (plan 15.5), sa njegovim zaglavljem.
NGINX_429 = (
    "<html>\r\n<head><title>429 Too Many Requests</title></head>\r\n<body>\r\n"
    "<center><h1>429 Too Many Requests</h1></center>\r\n<hr><center>nginx</center>\r\n</body>\r\n</html>\r\n"
)


@override_settings(PASSWORD_HASHERS=BRZI_HES)
class CspTokTests(OsnovaToka):
    """CSP iz settings.py vazi i ovde; nijedna strana ga ne krsi, ni posle radnji."""

    def setUp(self):
        super().setUp()
        obrisi_brojace()
        self.addCleanup(obrisi_brojace)

    def adresa(self, putanja):
        return self.live_server_url + putanja

    def snimi(self, strana, ime):
        if SNIMCI:
            strana.wait_for_function("() => document.getAnimations().length === 0")
            strana.screenshot(path=os.path.join(SNIMCI, f"{ime}.png"), full_page=True, animations="disabled")

    def bez_krsenja(self, strana, zapis, opis):
        with self.subTest(strana=opis):
            self.assertEqual(strana.evaluate("() => window.__csp"), [])
            self.assertEqual([red for red in zapis.konzola if "Content Security Policy" in red], [])

    def test_ceo_tok_igra_deljena_moderator(self):
        napravi_moderatora("Glavni", glavni=True)
        strana, zapis = self.otvori("seme-csp-ceo-tok", TELEFON, skripta=CSP_SLUSALAC)
        self.bez_krsenja(strana, zapis, "igra, pocetak")
        # Najduza partija: svih pet lekcija i najvise sablona na zavrsnom ekranu.
        self.odigraj_celu_u_pregledacu(strana, najduza_partija)
        self.bez_krsenja(strana, zapis, "igra, zavrsni")
        self.assertEqual(self.sacuvaj_i_cekaj(strana, "Пера").status, 200)
        expect(strana.locator("#rang-poruka")).to_be_visible()
        odgovor = self.podeli_i_cekaj(strana)
        self.assertEqual(odgovor.status, 200)
        expect(strana.locator("#deli-blok")).to_be_visible()
        self.bez_krsenja(strana, zapis, "igra, sacuvano i podeljeno")
        self.snimi(strana, "csp-igra-zavrsni-375")
        self.proveri_cisto(zapis)

        deljena = strana.context.new_page()
        zapis_deljene = Zapis(deljena)
        deljena.goto(odgovor.json()["url"])
        expect(deljena.locator("#zavrsni")).to_be_visible()
        self.bez_krsenja(deljena, zapis_deljene, "deljena")
        self.snimi(deljena, "csp-deljena-375")
        self.proveri_cisto(zapis_deljene)

        moderator = self.novi_kontekst(TELEFON, skripta=CSP_SLUSALAC).new_page()
        zapis_moderatora = Zapis(moderator)
        moderator.goto(self.adresa("/moderator/prijava/"))
        self.bez_krsenja(moderator, zapis_moderatora, "prijava")
        moderator.locator("#username").fill("Glavni")
        moderator.locator("#password").fill(LOZINKA)
        with moderator.expect_navigation():
            moderator.locator("form.mod-forma button[type=submit]").click()
        expect(moderator).to_have_url(self.adresa("/moderator/"))
        # Rezultat i deljeni link iste partije, oba sa imenom.
        expect(moderator.locator("li.mod-stavka", has_text="Пера")).to_have_count(2)
        self.bez_krsenja(moderator, zapis_moderatora, "pregled")
        for putanja in ("/moderator/dnevnik/", "/moderator/lozinka/", "/moderator/nalozi/"):
            moderator.goto(self.adresa(putanja))
            expect(moderator.locator("h1")).to_be_visible()
            self.bez_krsenja(moderator, zapis_moderatora, putanja)
        self.proveri_cisto(zapis_moderatora)

    def test_kontrola_krsenje_se_vidi(self):
        # Dokaz da provera gore nalazi krsenje: ugradjen stil i skripta su blokirani i zabelezeni oba puta.
        strana, zapis = self.otvori("seme-csp-kontrola", skripta=CSP_SLUSALAC)
        strana.evaluate(
            """() => {
              document.body.insertAdjacentHTML("beforeend", '<p style="color: red">x</p>');
              const s = document.createElement("script");
              s.textContent = "window.__ubaceno = 1";
              document.body.append(s);
            }"""
        )
        strana.wait_for_function("() => window.__csp.length >= 2")
        self.assertIsNone(strana.evaluate("() => window.__ubaceno ?? null"))
        prekrsaji = strana.evaluate("() => window.__csp")
        self.assertTrue(any(p.startswith("style-src") for p in prekrsaji), prekrsaji)
        self.assertTrue(any(p.startswith("script-src") for p in prekrsaji), prekrsaji)
        strana.wait_for_function("() => new Promise((gotovo) => requestAnimationFrame(() => gotovo(true)))")
        self.assertTrue(any("Content Security Policy" in red for red in zapis.konzola), zapis.konzola)

    def test_429_na_375_opsta_poruka(self):
        # Nginx vraca 429 HTML (plan 15.5); skripta ga prikazuje kao opstu gresku i igra ide dalje.
        strana, zapis = self.otvori("seme-429-potez", TELEFON, skripta=CSP_SLUSALAC)
        self.izaberi(strana, OPUS_HIGH)
        ograniceno = lambda ruta: ruta.fulfill(status=429, content_type="text/html", body=NGINX_429)  # noqa: E731
        strana.route("**/potez/", ograniceno)
        strana.locator("#potvrdi").click()
        poruka = strana.locator("#poruka")
        expect(poruka).to_have_text(SERVER_GRESKA["sr"])
        expect(poruka).to_be_in_viewport()
        expect(strana.locator("#krug")).to_have_text(KRUG_TEKST["sr"].format(1))
        expect(strana.locator("#potvrdi")).to_be_enabled()
        self.proveri_bez_prelivanja(strana, "429 potez 375")
        self.snimi(strana, "429-potez-375")
        strana.unroute("**/potez/")
        self.assertEqual(self.potvrdi_i_cekaj(strana).status, 200)
        expect(strana.locator("#krug")).to_have_text(KRUG_TEKST["sr"].format(2))
        expect(poruka).to_be_hidden()
        self.assertEqual((zapis.izuzeci, zapis.neuspeli), ([], []))
        self.assertEqual(strana.evaluate("() => window.__csp"), [])

        strana, zapis = self.otvori_zavrseno("seme-429-zavrsni", TELEFON, skripta=CSP_SLUSALAC)
        strana.route("**/sacuvaj/", ograniceno)
        strana.route("**/podeli/", ograniceno)
        self.assertEqual(self.sacuvaj_i_cekaj(strana, "Пера").status, 429)
        expect(strana.locator("#rang-greska")).to_have_text(SERVER_GRESKA["sr"])
        expect(strana.locator("#rang-sacuvaj")).to_be_enabled()
        self.assertEqual(self.podeli_i_cekaj(strana).status, 429)
        expect(strana.locator("#deli-poruka")).to_have_text(SERVER_GRESKA["sr"])
        expect(strana.locator("#deli-poruka")).to_be_in_viewport()
        self.proveri_bez_prelivanja(strana, "429 zavrsni 375")
        self.snimi(strana, "429-zavrsni-375")
        self.assertEqual(Rezultat.objects.count(), 0)
        self.assertEqual((zapis.izuzeci, zapis.neuspeli), ([], []))
        self.assertEqual(strana.evaluate("() => window.__csp"), [])

    # --- strane gresaka ---

    def proveri_stranu_greske(self, strana, zapis, vrsta, jez, url, zanemari=()):
        status, h1_sr, h1_en = STRANE_GRESAKA[vrsta]
        konzola = [red for red in zapis.konzola if not any(deo in red for deo in zanemari)]
        expect(strana.locator("html")).to_have_attribute("lang", jez)
        expect(strana.locator("h1")).to_have_text(h1_sr if jez == "sr" else h1_en)
        # Stil je ucitan pod CSP-om: veza-dugme vise nije "inline" kao obican link bez CSS-a.
        self.assertNotEqual(strana.evaluate("() => getComputedStyle(document.querySelector('a.btn')).display"),
                            "inline")
        self.assertEqual(strana.evaluate("() => window.__csp"), [])
        self.assertEqual((zapis.izuzeci, zapis.neuspeli), ([], []))
        # Jedini los odgovor je sam dokument; jedini red konzole je Chromium-ov za njegov status.
        self.assertEqual(zapis.losi_odgovori(), [f"{status} {url}"])
        self.assertEqual(len(konzola), 1, zapis.konzola)
        self.assertIn(f"status of {status}", konzola[0])
        for sirina, visina in EKRANI_GRESAKA:
            strana.set_viewport_size({"width": sirina, "height": visina})
            self.proveri_bez_prelivanja(strana, f"{vrsta}, {sirina} px, {jez}")
            expect(strana.locator("h1")).to_be_in_viewport()
            self.snimi(strana, f"greska-{vrsta}-{sirina}-{jez}")

    def strane_gresaka(self, jezik):
        jez = jezik[:2]

        def nova():
            strana = self.novi_kontekst(TELEFON, skripta=CSP_SLUSALAC, jezik=jezik).new_page()
            return strana, Zapis(strana)

        strana, zapis = nova()
        url = self.adresa("/nepostoji-qzx/")
        self.assertEqual(strana.goto(url).status, 404)
        self.proveri_stranu_greske(strana, zapis, "404", jez, url)

        strana, zapis = nova()
        with mock.patch("igra.views._stanje", side_effect=PermissionDenied("x")), \
                self.assertLogs("django.request", "WARNING"):
            self.assertEqual(strana.goto(self.adresa("/")).status, 403)
        self.proveri_stranu_greske(strana, zapis, "403", jez, self.adresa("/"))

        strana, zapis = nova()
        with mock.patch("igra.views._stanje", side_effect=RuntimeError("kvar-u-pregledacu")), \
                self.assertLogs("django.request", "ERROR"):
            self.assertEqual(strana.goto(self.adresa("/")).status, 500)
        self.assertNotIn("kvar-u-pregledacu", strana.content())
        self.proveri_stranu_greske(strana, zapis, "500", jez, self.adresa("/"))

        # Forma prijave posle isteka kolacica (npr. posle brisanja kolacica): 403_csrf, bez forme i skripte.
        strana, zapis = nova()
        url = self.adresa("/moderator/prijava/")
        strana.goto(url)
        strana.context.clear_cookies()
        strana.locator("#username").fill("Glavni")
        strana.locator("#password").fill(LOZINKA)
        with self.assertLogs("django.security.csrf", "WARNING"), strana.expect_navigation():
            strana.locator("form.mod-forma button[type=submit]").click()
        self.proveri_stranu_greske(strana, zapis, "403_csrf", jez, url)

    def test_strane_gresaka_sr(self):
        self.strane_gresaka(SRPSKI)

    def test_strane_gresaka_en(self):
        self.strane_gresaka(ENGLESKI)

    def test_strana_400_strani_host(self):
        # Strani Host bez izmene hosts datoteke: Chromium ime razresava na adresu live servera.
        pregledac = self.playwright.chromium.launch(args=[f"--host-resolver-rules=MAP {STRANI_HOST} 127.0.0.1"])
        self.addCleanup(pregledac.close)
        url = f"http://{STRANI_HOST}:{self.server_thread.port}/"
        for jezik in (SRPSKI, ENGLESKI):
            with self.subTest(jezik):
                kontekst = pregledac.new_context(viewport={"width": 375, "height": 812}, locale=jezik)
                self.addCleanup(kontekst.close)
                kontekst.add_init_script(CSP_SLUSALAC)
                strana = kontekst.new_page()
                zapis = Zapis(strana)
                with self.assertLogs("django.security.DisallowedHost", "ERROR"):
                    self.assertEqual(strana.goto(url).status, 400)
                self.assertNotIn(STRANI_HOST, strana.content())
                # http na imenu koje nije localhost nije "trustworthy", pa Chromium COOP zanemaruje i to kaze u
                # konzoli. Na serveru je https; ovo je posledica probe, ne strane.
                self.proveri_stranu_greske(strana, zapis, "400", jezik[:2], url,
                                           zanemari=("Cross-Origin-Opener-Policy header has been ignored",))

OZNAKE_TOKA = itertools.count(1)


# ---------- Dnevni izazov kroz pregledac (PLAN-dnevni-izazov.md, Talas 3, tacka 10) ----------

JS_DANA_CELIJE = JS_RANG_CELIJE.replace("#rang-redovi", "#rang-dana-redovi")
EKRANI_DNEVNOG = (TELEFON, TABLET, RACUNAR)
DNEVNI_IGRAC = "Дневни играч"


class DnevniTokTests(OsnovaToka):
    """Pocetna -> dnevni -> 8 krugova -> cuvanje -> pocetna pokazuje red na listi dana; izgled na 375/768/1440."""

    def snimi(self, strana, ime):
        if SNIMCI:
            strana.wait_for_function("() => document.getAnimations().length === 0")
            strana.screenshot(path=os.path.join(SNIMCI, f"{ime}.png"), full_page=True, animations="disabled")

    def otvori_pocetnu(self, dimenzije=RACUNAR, jezik=SRPSKI):
        kontekst = self.novi_kontekst(dimenzije, jezik=jezik)
        strana = kontekst.new_page()
        zapis = Zapis(strana)
        strana.goto(self.live_server_url + "/")
        expect(strana.locator("#krug")).to_have_text(KRUG_TEKST[jezik[:2]].format(1))
        return strana, zapis

    def otvori_dnevni(self, stanje, dimenzije=RACUNAR, jezik=SRPSKI):
        """Dnevna partija upisana u sesiju pre goto; strana /dnevni/ je nastavlja (dan je danasnji)."""
        sesija = SessionStore()
        sesija["dnevna"] = stanje
        sesija.create()
        kontekst = self.novi_kontekst(dimenzije, jezik=jezik)
        kontekst.add_cookies([{"name": settings.SESSION_COOKIE_NAME, "value": sesija.session_key,
                               "url": self.live_server_url}])
        strana = kontekst.new_page()
        zapis = Zapis(strana)
        strana.goto(self.live_server_url + "/dnevni/")
        if stanje["zavrsena"]:
            expect(strana.locator("#zavrsni")).to_be_visible()
        else:
            expect(strana.locator("#krug")).to_have_text(KRUG_TEKST[jezik[:2]].format(stanje["krug"]))
        return strana, zapis

    def dnevno_stanje(self, strategija=None):
        """Stanje kakvo server pravi danas; zavrseno ako je zadata strategija."""
        dan = timezone.localdate()
        stanje = motor.nova_igra(views._dnevno_seme(dan), dan=dan.isoformat(), oznaka=f"{next(OZNAKE_TOKA):032x}")
        if strategija is not None:
            for krug in range(1, 9):
                stanje = motor.odigraj_potez(stanje, krug, strategija(krug))
        return stanje

    def test_pocetna_dnevni_osam_krugova_cuvanje_pocetna_pokazuje_red(self):
        strana, zapis = self.otvori_pocetnu()
        osnova = self.live_server_url
        # Pocetna: prazna lista dana, link na dnevni izazov, glavna lista prazna.
        expect(strana.locator("#rang-dana-naslov")).to_have_text("Ранг листа дана")
        expect(strana.locator("#rang-dana-prazno")).to_be_visible()
        expect(strana.locator("#rang-dana-prazno")).to_have_text("Данас још нема сачуваних резултата.")
        expect(strana.locator("#rang-dana-tabela")).to_be_hidden()
        expect(strana.locator("#dnevni-dugme")).to_have_attribute("href", "/dnevni/")
        self.snimi(strana, "dnevni-1-pocetna-prazna")

        strana.locator("#dnevni-dugme").click()
        strana.wait_for_url(osnova + "/dnevni/")
        expect(strana.locator("#krug")).to_have_text(KRUG_TEKST["sr"].format(1))
        expect(strana.locator("#dnevni-naslov")).to_contain_text("Дневни изазов")
        expect(strana.locator("#nova-forma")).to_have_count(0)
        expect(strana.locator("#rang-dana-sekcija")).to_have_count(0)
        expect(strana.locator("#nazad-dugme")).to_have_attribute("href", "/")
        self.snimi(strana, "dnevni-2-krug-1")

        self.odigraj_celu_u_pregledacu(strana, po_tezini)
        self.assertEqual(len(zapis.zahtevi_poteza), 8)
        self.assertEqual({z.url for z in zapis.zahtevi_poteza}, {osnova + "/dnevni/potez/"})
        expect(strana.locator("#zavrsni")).to_be_visible()
        expect(strana.locator("#rang-forma")).to_be_visible()
        self.snimi(strana, "dnevni-3-zavrsni")

        odgovor = self.sacuvaj_i_cekaj(strana, DNEVNI_IGRAC)
        self.assertEqual(odgovor.status, 200)
        self.assertEqual(odgovor.url, osnova + "/dnevni/sacuvaj/")
        expect(strana.locator("#rang-poruka")).to_have_text(PORUKA_SACUVANO)
        expect(strana.locator("#rang-redovi tr")).to_have_count(1)
        expect(strana.locator("#rang-redovi tr.rang-moj [data-mesto='ime']")).to_have_text(DNEVNI_IGRAC)
        red = Rezultat.objects.get()  # posle zavrsenog odgovora, pa test nit ne ometa server
        self.assertEqual((red.ime, red.dan), (DNEVNI_IGRAC, timezone.localdate()))
        self.snimi(strana, "dnevni-4-sacuvano")

        strana.locator("#nazad-dugme").click()
        strana.wait_for_url(osnova + "/")
        expect(strana.locator("#krug")).to_have_text(KRUG_TEKST["sr"].format(1))
        # Lista dana ima red, i to kao sopstveni; glavna lista ostaje prazna.
        expect(strana.locator("#rang-dana-redovi tr")).to_have_count(1)
        expect(strana.locator("#rang-dana-tabela")).to_be_visible()
        expect(strana.locator("#rang-dana-prazno")).to_be_hidden()
        moj = strana.locator("#rang-dana-redovi tr.rang-moj")
        expect(moj).to_have_count(1)
        expect(moj.locator('[data-mesto="ime"]')).to_have_text(DNEVNI_IGRAC)
        expect(moj.locator('[data-mesto="mesto"]')).to_have_text("1")
        expect(moj.locator('[data-mesto="poeni"]')).to_have_text(str(red.poeni))
        expect(moj.locator('[data-mesto="datum"]')).to_have_text(danas())
        expect(strana.locator("#rang-redovi tr")).to_have_count(0)
        expect(strana.locator("#rang-prazno")).to_be_visible()
        self.snimi(strana, "dnevni-5-pocetna-sa-redom")

        # Povratak na dnevni: ista, zavrsena i sacuvana partija; nema druge igre istog dana.
        strana.locator("#dnevni-dugme").click()
        strana.wait_for_url(osnova + "/dnevni/")
        expect(strana.locator("#zavrsni")).to_be_visible()
        expect(strana.locator("#rang-forma")).to_be_hidden()
        expect(strana.locator("#rang-redovi tr")).to_have_count(1)
        self.assertEqual(len(zapis.zahtevi_cuvanja), 1)
        self.proveri_cisto(zapis)

    def test_jezik_na_dnevnoj_strani_ostaje_na_njoj_i_cuva_partiju(self):
        strana, zapis = self.otvori_dnevni(self.dnevno_stanje())
        for krug in (1, 2):
            self.odigraj_krug(strana, krug, po_tezini(krug))
        strana.locator("#jezik-dugme").click()
        strana.wait_for_url(self.live_server_url + "/dnevni/")
        expect(strana.locator("html")).to_have_attribute("lang", "en")
        expect(strana.locator("#krug")).to_have_text(KRUG_TEKST["en"].format(3))
        expect(strana.locator("#dnevni-naslov")).to_contain_text("Daily challenge")
        expect(strana.locator("#nazad-dugme")).to_have_text("Back to the main game")
        expect(strana.locator("#rang-naslov")).to_contain_text("Today's leaderboard")
        expect(strana.locator("#rang-prazno")).to_have_text("No saved results today yet.")
        self.proveri_cisto(zapis)

    def test_izgled_na_tri_sirine_pocetna_i_dnevni(self):
        danas_dan = timezone.localdate()
        for ime, poeni in ((SIROKO_IME, 90), (DUGO_IME[:20], 80), ("Пера", 70)):
            upisi_red(ime, poeni, dan=danas_dan)
            upisi_red(f"Г{poeni}", poeni - 1)  # glavna lista, da obe liste imaju redove
        izgled = {}
        for dimenzije in EKRANI_DNEVNOG:
            sirina = dimenzije[0]
            with self.subTest(strana="pocetna", sirina=sirina):
                strana, zapis = self.otvori_pocetnu(dimenzije)
                expect(strana.locator("#rang-dana-redovi tr")).to_have_count(3)
                expect(strana.locator("#rang-redovi tr")).to_have_count(3)
                self.proveri_bez_prelivanja(strana, f"pocetna-{sirina}")
                self.assertEqual(strana.evaluate(JS_DANA_CELIJE), [])
                izgled[f"pocetna-{sirina}"] = strana.evaluate(JS_PRELIVANJE)["skrol"]
                self.snimi(strana, f"dnevni-pocetna-{sirina}")
                self.proveri_cisto(zapis)
            with self.subTest(strana="dnevni krug 1", sirina=sirina):
                strana, zapis = self.otvori_dnevni(self.dnevno_stanje(), dimenzije)
                expect(strana.locator("#rang-redovi tr")).to_have_count(3)
                self.proveri_bez_prelivanja(strana, f"dnevni-{sirina}")
                self.assertEqual(strana.evaluate(JS_RANG_CELIJE), [])
                self.snimi(strana, f"dnevni-krug-{sirina}")
                self.proveri_cisto(zapis)
            with self.subTest(strana="dnevni zavrsen", sirina=sirina):
                strana, zapis = self.otvori_dnevni(self.dnevno_stanje(po_tezini), dimenzije)
                expect(strana.locator("#rang-redovi tr")).to_have_count(3)
                self.proveri_bez_prelivanja(strana, f"dnevni-zavrsen-{sirina}")
                self.snimi(strana, f"dnevni-zavrsen-{sirina}")
                self.proveri_cisto(zapis)
        self.assertEqual(set(izgled), {"pocetna-375", "pocetna-768", "pocetna-1440"})

    def test_engleski_na_telefonu_bez_prelivanja(self):
        upisi_red("Player", 77, dan=timezone.localdate())
        strana, zapis = self.otvori_pocetnu(TELEFON, ENGLESKI)
        expect(strana.locator("#rang-dana-naslov")).to_contain_text("Today's leaderboard")
        expect(strana.locator("#dnevni-dugme")).to_contain_text("Play the daily challenge")
        expect(strana.locator("#rang-dana-redovi tr")).to_have_count(1)
        self.proveri_bez_prelivanja(strana, "pocetna-en-375")
        self.snimi(strana, "dnevni-pocetna-en-375")
        strana.locator("#dnevni-dugme").click()
        strana.wait_for_url(self.live_server_url + "/dnevni/")
        expect(strana.locator("#dnevni-naslov")).to_contain_text("Daily challenge")
        self.proveri_bez_prelivanja(strana, "dnevni-en-375")
        self.snimi(strana, "dnevni-en-375")
        self.proveri_cisto(zapis)


# ---------- Prijava neprikladnog imena kroz pregledac (odluka 2026-11-12, projekat-domen tok 11) ----------

EKRANI_PRIJAVE = (TELEFON, TABLET, (1280, 900))
PRIJAVA_NASLOV = {"sr": "Пријави неприкладно име", "en": "Report an inappropriate name"}
PRIJAVA_DUGME = {"sr": "Пошаљи пријаву", "en": "Send report"}
PRIJAVA_PRIMLJENA = {"sr": "Пријава је примљена. Хвала.", "en": "Report received. Thank you."}
PRIJAVA_NIJE_NA_LISTI = "Овај резултат више није на ранг листи. Освежите страну."
PRIJAVLJENA_NASLOV = {"sr": "Пријављена имена", "en": "Reported names"}
PRIJAVLJENA_PRAZNO = "Нема пријављених имена."
OSTAVLJENO = {"sr": "Име је остављено, а пријаве су уклоњене.", "en": "The name was kept and the reports were removed."}
BROJ_PRIJAVA = {"sr": "Број пријава", "en": "Number of reports"}
RADNJE_PRIJAVLJENOG = {"sr": ["Остави", "Обриши"], "en": ["Keep", "Delete"]}
IME_ZDESNA = "שלום עולם 123"  # zdesna nalevo, sa ciframa: redni broj opcije ne sme da se pomeri
ODELJAK_PRIJAVLJENIH = 'section[aria-labelledby="mod-prijavljena"]'

# Izbor, dugme i poruka bloka prijave ostaju unutar svog odeljka liste i prozora.
JS_BLOK_PRIJAVE = """(blok) => {
  const sirina = document.documentElement.clientWidth;
  const odeljak = blok.closest('section').getBoundingClientRect();
  const van = [];
  for (const e of blok.querySelectorAll('summary, label, select, button, [data-mesto="prijava-poruka"]')) {
    const r = e.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    if (r.right > Math.min(sirina, odeljak.right) + 0.5 || r.left < Math.max(0, odeljak.left) - 0.5) {
      van.push(e.tagName + ' ' + JSON.stringify([r.left, r.right, odeljak.left, odeljak.right, sirina]));
    }
  }
  const naslov = blok.querySelector('summary').getBoundingClientRect();
  const izbor = blok.querySelector('select').getBoundingClientRect();
  const dugme = blok.querySelector('button').getBoundingClientRect();
  return {van: van, naslov: naslov.height, izbor: izbor.height, dugme: dugme.height};
}"""

# Dve radnje uz prijavljeno ime: polozaj svake, i polozaj stavke i prozora.
JS_RADNJE = """(stavka) => {
  const s = stavka.getBoundingClientRect();
  return {
    sirina: document.documentElement.clientWidth,
    stavka: [s.left, s.right],
    radnje: Array.from(stavka.querySelectorAll('.mod-radnje .mod-radnja')).map((e) => {
      const r = e.getBoundingClientRect();
      return {tekst: e.firstChild.textContent.trim(), levo: r.left, desno: r.right, vrh: r.top, visina: r.height};
    }),
  };
}"""


def tekst_opcije(mesto, ime):
    """Natpis opcije po ugovoru: redni broj, pa ime izmedju U+2068 i U+2069."""
    return f"{mesto}. ⁨{ime}⁩"


@override_settings(PASSWORD_HASHERS=BRZI_HES)
class PrijavaTokTests(OsnovaToka):
    """Igrac prijavljuje ime ispod liste; moderator na pregledu jedno ostavlja, a drugo brise. Izgled: 375/768/1280."""

    def setUp(self):
        super().setUp()
        obrisi_brojace()
        self.addCleanup(obrisi_brojace)

    def adresa(self, putanja):
        return self.live_server_url + putanja

    def snimi(self, strana, ime):
        if SNIMCI:
            strana.wait_for_function("() => document.getAnimations().length === 0")
            strana.screenshot(path=os.path.join(SNIMCI, f"{ime}.png"), full_page=True, animations="disabled")

    def blok(self, strana, odeljak="#rang"):
        return strana.locator(f'{odeljak} [data-mesto="prijava"]')

    def deo(self, strana, mesto, odeljak="#rang"):
        return self.blok(strana, odeljak).locator(f'[data-mesto="{mesto}"]')

    def opcije(self, strana, odeljak="#rang"):
        return self.deo(strana, "prijava-izbor", odeljak).locator("option")

    def iskljucene(self, strana, odeljak="#rang"):
        return self.opcije(strana, odeljak).evaluate_all("(o) => o.map((e) => e.disabled)")

    def posalji_prijavu(self, strana, oznaka, odeljak="#rang"):
        """Bira red po vrednosti (natpis nosi nevidljive znake), salje i ceka odgovor servera."""
        self.deo(strana, "prijava-izbor", odeljak).select_option(value=oznaka)
        dugme = self.deo(strana, "prijava-dugme", odeljak)
        expect(dugme).to_be_enabled()
        with strana.expect_response(
            lambda o: o.url.endswith("/prijavi/") and o.request.method == "POST"
        ) as informacija:
            dugme.click()
        odgovor = informacija.value
        self.assertEqual(odgovor.request.post_data_json, {"red": oznaka})
        return odgovor

    def prijavi_moderatora(self, strana, ime):
        strana.goto(self.adresa("/moderator/prijava/"))
        strana.locator("#username").fill(ime)
        strana.locator("#password").fill(LOZINKA)
        with strana.expect_navigation():
            strana.locator("form.mod-forma button[type=submit]").click()
        expect(strana).to_have_url(self.adresa("/moderator/"))

    def stavka(self, strana, ime):
        return strana.locator(f"{ODELJAK_PRIJAVLJENIH} li.mod-stavka", has_text=ime)

    def broj_prijava(self, stavka, jez="sr"):
        natpis = stavka.page.locator("dt", has_text=BROJ_PRIJAVA[jez])
        return stavka.locator("dl.mod-meta > div", has=natpis).locator("dd")

    def test_igrac_prijavljuje_moderator_ostavlja_i_brise(self):
        napravi_moderatora("Mod")
        prvi = upisi_red("Први", 90)
        drugi = upisi_red("Други", 80)
        treci = upisi_red("Трећи", 70)
        for _ in range(2):  # dve tudje prijave reda koji ce moderator obrisati
            upisi_prijavu(drugi)
        strana, zapis = self.otvori("seme-prijava-imena")

        # Blok ispod glavne liste: vidljiv jer lista ima redove, zatvoren dok ga igrac ne otvori.
        blok = self.blok(strana)
        expect(blok).to_be_visible()
        expect(blok.locator("summary")).to_have_text(PRIJAVA_NASLOV["sr"])
        self.assertFalse(blok.evaluate("(e) => e.open"))
        expect(self.deo(strana, "prijava-forma")).to_be_hidden()
        # Lista dana je prazna: njen blok ostaje skriven.
        expect(self.blok(strana, "#rang-dana-sekcija")).to_have_count(1)
        expect(self.blok(strana, "#rang-dana-sekcija")).to_be_hidden()
        blok.locator("summary").click()
        expect(self.deo(strana, "prijava-forma")).to_be_visible()
        expect(blok.locator("label")).to_have_text("Име које пријављујете")
        dugme = self.deo(strana, "prijava-dugme")
        expect(dugme).to_have_text(PRIJAVA_DUGME["sr"])
        expect(dugme).to_be_enabled()
        opcije = self.opcije(strana)
        expect(opcije).to_have_count(3)
        self.assertEqual(
            opcije.evaluate_all("(o) => o.map((e) => [e.value, e.textContent, e.disabled])"),
            [[oznaka_reda(red), tekst_opcije(mesto, red.ime), False]
             for mesto, red in enumerate((prvi, drugi, treci), start=1)],
        )
        poruka = self.deo(strana, "prijava-poruka")
        expect(poruka).to_be_hidden()

        odgovor = self.posalji_prijavu(strana, oznaka_reda(prvi))
        self.assertEqual((odgovor.status, odgovor.json()), (200, {"primljeno": True}))
        expect(poruka).to_be_visible()
        expect(poruka).to_have_text(PRIJAVA_PRIMLJENA["sr"])
        # Prijavljena opcija je iskljucena, izbor je presao na prvu slobodnu, dugme i dalje radi.
        self.assertEqual(self.iskljucene(strana), [True, False, False])
        expect(self.deo(strana, "prijava-izbor")).to_have_value(oznaka_reda(drugi))
        expect(dugme).to_be_enabled()
        # Prijava nista ne sakriva: lista igraca je ista.
        expect(strana.locator('#rang-redovi [data-mesto="ime"]')).to_have_text(["Први", "Други", "Трећи"])
        self.assertEqual(
            list(PrijavaImena.objects.order_by("id").values_list("rezultat_id", flat=True)),
            [drugi.id, drugi.id, prvi.id],
        )
        self.proveri_cisto(zapis)

        # Moderator: oba imena u odeljku, sa brojem prijava; glavna lista ispod je netaknuta.
        mod = self.novi_kontekst().new_page()
        zapis_mod = Zapis(mod)
        self.prijavi_moderatora(mod, "Mod")
        odeljak = mod.locator(ODELJAK_PRIJAVLJENIH)
        expect(odeljak.locator("h2")).to_have_text(PRIJAVLJENA_NASLOV["sr"])
        expect(odeljak.locator("li.mod-stavka")).to_have_count(2)
        expect(self.broj_prijava(self.stavka(mod, "Први"))).to_have_text("1")
        expect(self.broj_prijava(self.stavka(mod, "Други"))).to_have_text("2")
        glavna = mod.locator('section[aria-labelledby="mod-rezultati"] li.mod-stavka')
        expect(glavna).to_have_count(3)

        # „Остави“: poruka, ime nestaje iz odeljka, a ostaje na glavnoj listi.
        with mod.expect_navigation():
            self.stavka(mod, "Први").locator(".mod-radnje form button").click()
        expect(mod).to_have_url(self.adresa("/moderator/?poruka=ostavljeno"))
        expect(mod.locator(".mod-poruka-ok")).to_have_text(OSTAVLJENO["sr"])
        expect(odeljak.locator("li.mod-stavka")).to_have_count(1)
        expect(self.stavka(mod, "Први")).to_have_count(0)
        expect(self.stavka(mod, "Други")).to_have_count(1)
        expect(glavna).to_have_count(3)
        expect(glavna.filter(has_text="Први")).to_have_count(1)

        # Drugo ime: brisanje kroz postojecu potvrdu.
        with mod.expect_navigation():
            self.stavka(mod, "Други").locator(".mod-radnje a.mod-obrisi").click()
        expect(mod).to_have_url(self.adresa(f"/moderator/rezultat/{drugi.id}/"))
        expect(mod.locator("h1")).to_have_text("Обрисати овај резултат?")
        with mod.expect_navigation():
            mod.locator("form.mod-potvrda button[type=submit]").click()
        expect(mod).to_have_url(self.adresa("/moderator/?poruka=obrisano"))
        expect(mod.locator(".mod-poruka-ok")).to_have_text("Обрисано.")
        expect(odeljak.locator("li.mod-stavka")).to_have_count(0)
        expect(odeljak.locator(".rang-prazno")).to_have_text(PRIJAVLJENA_PRAZNO)
        expect(glavna).to_have_count(2)
        expect(glavna.filter(has_text="Други")).to_have_count(0)

        # Dnevnik nosi obe odluke, najnoviju prvu.
        with mod.expect_navigation():
            mod.locator(".mod-meni a", has_text="Дневник").click()
        zapisi = mod.locator("li.mod-zapis")
        expect(zapisi).to_have_count(2)
        expect(zapisi.nth(0)).to_contain_text("обрисан резултат")
        expect(zapisi.nth(0)).to_contain_text("Други")
        expect(zapisi.nth(1)).to_contain_text("одбачена пријава имена")
        expect(zapisi.nth(1)).to_contain_text("Први")
        self.proveri_cisto(zapis_mod)
        self.assertEqual(PrijavaImena.objects.count(), 0)
        self.assertEqual(set(Rezultat.objects.values_list("ime", flat=True)), {"Први", "Трећи"})

        # Kartica igraca jos pokazuje obrisan red: prijava tog reda daje poruku da ga vise nema (ocekivan 409).
        odgovor = self.posalji_prijavu(strana, oznaka_reda(drugi))
        self.assertEqual((odgovor.status, odgovor.json()), (409, {"greska": "nije_na_listi"}))
        expect(poruka).to_have_text(PRIJAVA_NIJE_NA_LISTI)
        self.assertEqual(self.iskljucene(strana), [True, False, False])
        expect(dugme).to_be_enabled()
        self.assertEqual(zapis.losi_odgovori(), [f"409 {self.adresa('/prijavi/')}"])
        self.assertEqual(len(zapis.konzola), 1, zapis.konzola)
        self.assertIn("409", zapis.konzola[0])
        self.assertEqual((zapis.izuzeci, zapis.neuspeli), ([], []))

        # Posle osvezavanja: ostavljeno ime je i dalje na listi igraca, obrisano nije.
        strana.reload()
        expect(strana.locator('#rang-redovi [data-mesto="ime"]')).to_have_text(["Први", "Трећи"])
        self.assertEqual(self.opcije(strana).evaluate_all("(o) => o.map((e) => e.value)"),
                         [oznaka_reda(prvi), oznaka_reda(treci)])
        self.assertEqual(len(zapis.losi_odgovori()), 1)
        self.assertEqual((zapis.izuzeci, zapis.neuspeli), ([], []))

    def proveri_blok(self, strana, odeljak, oznaka, otvoren=True):
        mere = self.blok(strana, odeljak).evaluate(JS_BLOK_PRIJAVE)
        with self.subTest(ekran=oznaka, odeljak=odeljak):
            self.assertEqual(mere["van"], [])
            self.assertGreaterEqual(mere["naslov"], 44, mere)  # meta dodira
            if otvoren:
                self.assertGreaterEqual(mere["izbor"], 36, mere)
                self.assertGreaterEqual(mere["dugme"], 44, mere)

    def test_izgled_bloka_na_tri_sirine(self):
        """Blok zatvoren, otvoren i posle slanja, ispod obe liste, sa najsirim imenom i imenom zdesna nalevo."""
        imena = (SIROKO_IME, IME_ZDESNA, DUGO_IME[:20])
        glavni = [upisi_red(ime, 90 - 10 * i) for i, ime in enumerate(imena)]
        dnevni = [upisi_red(ime, 90 - 10 * i, dan=timezone.localdate()) for i, ime in enumerate(imena)]
        odeljci = (("#rang-dana-sekcija", dnevni), ("#rang", glavni))
        provereno = set()
        for dimenzije, jezik in [(d, SRPSKI) for d in EKRANI_PRIJAVE] + [(TELEFON, ENGLESKI)]:
            sirina, jez = dimenzije[0], jezik[:2]
            with self.subTest(sirina=sirina, jezik=jez):
                strana, zapis = self.otvori(f"seme-izgled-prijave-{sirina}-{jez}", dimenzije, jezik=jezik)
                self.assertEqual(strana.evaluate("() => document.documentElement.clientWidth"), sirina)
                for odeljak, _ in odeljci:
                    expect(self.blok(strana, odeljak)).to_be_visible()
                    expect(self.blok(strana, odeljak).locator("summary")).to_have_text(PRIJAVA_NASLOV[jez])
                    expect(self.deo(strana, "prijava-forma", odeljak)).to_be_hidden()
                    self.proveri_blok(strana, odeljak, f"zatvoren-{sirina}-{jez}", otvoren=False)
                self.proveri_bez_prelivanja(strana, f"prijava-zatvoren-{sirina}-{jez}")
                self.snimi(strana, f"prijava-1-zatvoren-{sirina}-{jez}")

                for odeljak, _ in odeljci:
                    self.blok(strana, odeljak).locator("summary").click()
                    expect(self.deo(strana, "prijava-forma", odeljak)).to_be_visible()
                    expect(self.deo(strana, "prijava-dugme", odeljak)).to_have_text(PRIJAVA_DUGME[jez])
                    self.assertEqual(self.opcije(strana, odeljak).all_text_contents(),
                                     [tekst_opcije(mesto, ime) for mesto, ime in enumerate(imena, start=1)])
                    # Natpis je vezan za izbor, a id je jedinstven i kad strana ima dva bloka.
                    izbor = self.deo(strana, "prijava-izbor", odeljak)
                    oznaka = izbor.get_attribute("id")
                    self.assertEqual(self.blok(strana, odeljak).locator("label").get_attribute("for"), oznaka)
                    self.assertEqual(strana.locator(f'[id="{oznaka}"]').count(), 1)
                    for redni in range(len(imena)):  # svako ime izabrano: izbor ostaje u odeljku
                        izbor.select_option(index=redni)
                        self.proveri_blok(strana, odeljak, f"otvoren-{sirina}-{jez}-{redni}")
                self.proveri_bez_prelivanja(strana, f"prijava-otvoren-{sirina}-{jez}")
                self.snimi(strana, f"prijava-2-otvoren-{sirina}-{jez}")

                # Slanje iz oba bloka: ime zdesna nalevo sa liste dana, najsire sa glavne.
                for (odeljak, redovi), redni in zip(odeljci, (1, 0)):
                    odgovor = self.posalji_prijavu(strana, oznaka_reda(redovi[redni]), odeljak)
                    self.assertEqual(odgovor.status, 200)
                    poruka = self.deo(strana, "prijava-poruka", odeljak)
                    expect(poruka).to_be_visible()
                    expect(poruka).to_have_text(PRIJAVA_PRIMLJENA[jez])
                    self.assertEqual(self.iskljucene(strana, odeljak), [i == redni for i in range(len(imena))])
                    self.proveri_blok(strana, odeljak, f"poslato-{sirina}-{jez}")
                self.proveri_bez_prelivanja(strana, f"prijava-poslato-{sirina}-{jez}")
                self.snimi(strana, f"prijava-3-poslato-{sirina}-{jez}")
                self.proveri_cisto(zapis)
                provereno.add((sirina, jez))
        self.assertEqual(provereno, {(375, "sr"), (768, "sr"), (1280, "sr"), (375, "en")})

    def proveri_radnje(self, strana, ime, oznaka, jez):
        stavka = self.stavka(strana, ime)
        expect(stavka).to_have_count(1)
        mere = stavka.evaluate(JS_RADNJE)
        with self.subTest(ekran=oznaka, ime=ime):
            self.assertEqual([r["tekst"] for r in mere["radnje"]], RADNJE_PRIJAVLJENOG[jez])
            ostavi, obrisi = mere["radnje"]
            self.assertLess(abs(ostavi["vrh"] - obrisi["vrh"]), 1, mere)   # u istom redu
            self.assertLessEqual(ostavi["desno"], obrisi["levo"], mere)    # ne preklapaju se
            for radnja in mere["radnje"]:
                self.assertGreaterEqual(radnja["visina"], 44, mere)
                self.assertGreaterEqual(radnja["levo"], mere["stavka"][0] - 0.5, mere)
                self.assertLessEqual(radnja["desno"], min(mere["stavka"][1], mere["sirina"]) + 0.5, mere)

    def proveri_mere_moderatora(self, strana, oznaka):
        mere = strana.evaluate(JS_PRELIVANJE_MOD)
        with self.subTest(ekran=oznaka):
            self.assertLessEqual(mere["skrol"], mere["sirina"], mere)
            self.assertEqual(mere["van"], [])
            self.assertEqual(mere["odseceno"], [])

    def test_izgled_odeljka_moderatora_na_tri_sirine(self):
        """Odeljak sa najsirim imenom (100 prijava, dnevni red) i imenom zdesna nalevo; dva dugmeta u redu."""
        napravi_moderatora("Mod")
        for jezik in (SRPSKI, ENGLESKI):
            jez = jezik[:2]
            PrijavaImena.objects.all().delete()
            Rezultat.objects.all().delete()
            sirok = upisi_red(SIROKO_IME, 90, dan=timezone.localdate())
            zdesna = upisi_red(IME_ZDESNA, 80)
            for _ in range(parametri.PRIJAVA_NAJVISE):
                upisi_prijavu(sirok)
            upisi_prijavu(zdesna)
            with self.subTest(jezik=jez):
                strana = self.novi_kontekst(jezik=jezik).new_page()
                zapis = Zapis(strana)
                self.prijavi_moderatora(strana, "Mod")
                expect(strana.locator("html")).to_have_attribute("lang", jez)
                odeljak = strana.locator(ODELJAK_PRIJAVLJENIH)
                expect(odeljak.locator("h2")).to_have_text(PRIJAVLJENA_NASLOV[jez])
                expect(odeljak.locator("li.mod-stavka")).to_have_count(2)
                expect(self.broj_prijava(self.stavka(strana, SIROKO_IME), jez)).to_have_text(
                    str(parametri.PRIJAVA_NAJVISE))
                for sirina, visina in EKRANI_PRIJAVE:
                    strana.set_viewport_size({"width": sirina, "height": visina})
                    strana.wait_for_function("() => document.getAnimations().length === 0")
                    self.assertEqual(strana.evaluate("() => document.documentElement.clientWidth"), sirina)
                    self.proveri_mere_moderatora(strana, f"prijavljena-{sirina}-{jez}")
                    for ime in (SIROKO_IME, IME_ZDESNA):
                        self.proveri_radnje(strana, ime, f"prijavljena-{sirina}-{jez}", jez)
                    self.snimi(strana, f"mod-prijavljena-{sirina}-{jez}")
                # Posle „Остави“: poruka iznad odeljka, jedna stavka; isto merenje na sve tri sirine.
                with strana.expect_navigation():
                    self.stavka(strana, IME_ZDESNA).locator(".mod-radnje form button").click()
                expect(strana.locator(".mod-poruka-ok")).to_have_text(OSTAVLJENO[jez])
                expect(odeljak.locator("li.mod-stavka")).to_have_count(1)
                for sirina, visina in EKRANI_PRIJAVE:
                    strana.set_viewport_size({"width": sirina, "height": visina})
                    strana.wait_for_function("() => document.getAnimations().length === 0")
                    self.proveri_mere_moderatora(strana, f"ostavljeno-{sirina}-{jez}")
                    self.proveri_radnje(strana, SIROKO_IME, f"ostavljeno-{sirina}-{jez}", jez)
                    expect(strana.locator(".mod-poruka-ok")).to_be_visible()
                    self.snimi(strana, f"mod-ostavljeno-{sirina}-{jez}")
                self.proveri_cisto(zapis)


# Lazni AudioContext: belezi frekvencije i oblik talasa svakog tona, a ne svira nista.
LAZNI_ZVUK = """
window.__ton = [];
window.__kontekst = 0;
window.AudioContext = class {
  constructor() { window.__kontekst += 1; this.currentTime = 0; this.state = "running"; this.destination = {}; }
  resume() { return Promise.resolve(); }
  createGain() {
    const g = () => ({ setValueAtTime() {}, linearRampToValueAtTime() {}, exponentialRampToValueAtTime() {} });
    return { gain: g(), connect() {} };
  }
  createOscillator() {
    const o = { type: "", connect() {}, start() {}, stop() {} };
    o.frequency = { setValueAtTime: (f) => window.__ton.push([o.type, f]) };
    return o;
  }
};
"""
ZVUK_UKLJUCEN_UNAPRED = 'try { localStorage.setItem("orkestrator.zvuk", "1"); } catch (e) {}'
NATPIS_ZVUKA = {"sr": ("Звук: укључен", "Звук: искључен"), "en": ("Sound: on", "Sound: off")}


class ZvukTokTests(OsnovaToka):
    def tonovi(self, strana):
        return strana.evaluate("() => window.__ton.slice()")

    def isprazni(self, strana):
        strana.evaluate("() => { window.__ton.length = 0; }")

    def test_podrazumevano_iskljuceno_i_potez_ne_svira(self):
        seme = nadji_seme(po_tezini, lambda i: motor.DORADA in i and motor.USPEH in i)
        strana, zapis = self.otvori(seme, skripta=LAZNI_ZVUK)
        dugme = strana.locator("#zvuk-dugme")
        expect(dugme).to_be_visible()
        expect(dugme).to_have_attribute("aria-pressed", "false")
        expect(dugme).to_have_text(NATPIS_ZVUKA["sr"][1])
        self.assertIsNone(strana.evaluate("() => localStorage.getItem('orkestrator.zvuk')"))
        self.odigraj_krug(strana, 1, po_tezini(1))
        self.assertEqual(self.tonovi(strana), [])
        self.assertEqual(strana.evaluate("() => window.__kontekst"), 0)
        self.proveri_cisto(zapis)

    def test_klik_ukljucuje_izbor_ostaje_posle_ponovnog_ucitavanja(self):
        strana, zapis = self.otvori("zvuk-izbor", skripta=LAZNI_ZVUK)
        dugme = strana.locator("#zvuk-dugme")
        dugme.click()
        expect(dugme).to_have_attribute("aria-pressed", "true")
        expect(dugme).to_have_text(NATPIS_ZVUKA["sr"][0])
        self.assertEqual(strana.evaluate("() => localStorage.getItem('orkestrator.zvuk')"), "1")
        # Klik na prekidac nije potez: nema tona, ali je kontekst napravljen posle radnje igraca.
        self.assertEqual(self.tonovi(strana), [])
        self.assertEqual(strana.evaluate("() => window.__kontekst"), 1)
        strana.reload()
        expect(strana.locator("#krug")).to_have_text(KRUG_TEKST["sr"].format(1))
        expect(dugme).to_have_attribute("aria-pressed", "true")
        expect(dugme).to_have_text(NATPIS_ZVUKA["sr"][0])
        # Ucitavanje strane sa ukljucenim zvukom ne svira i ne pravi kontekst.
        self.assertEqual(self.tonovi(strana), [])
        self.assertEqual(strana.evaluate("() => window.__kontekst"), 0)
        dugme.click()
        expect(dugme).to_have_attribute("aria-pressed", "false")
        self.assertEqual(strana.evaluate("() => localStorage.getItem('orkestrator.zvuk')"), "0")
        strana.reload()
        expect(strana.locator("#krug")).to_have_text(KRUG_TEKST["sr"].format(1))
        expect(dugme).to_have_attribute("aria-pressed", "false")
        self.proveri_cisto(zapis)

    def test_engleski_natpis_i_dnevna_strana(self):
        strana, zapis = self.otvori("zvuk-en", skripta=LAZNI_ZVUK, jezik=ENGLESKI)
        dugme = strana.locator("#zvuk-dugme")
        expect(dugme).to_have_text(NATPIS_ZVUKA["en"][1])
        dugme.click()
        expect(dugme).to_have_text(NATPIS_ZVUKA["en"][0])
        strana.goto(self.live_server_url + "/dnevni/")
        expect(strana.locator("#zvuk-dugme")).to_be_visible()
        expect(strana.locator("#zvuk-dugme")).to_have_attribute("aria-pressed", "true")
        self.proveri_cisto(zapis)

    def test_bez_web_audio_prekidac_je_sakriven_bez_greske(self):
        skripta = "delete window.AudioContext; delete window.webkitAudioContext;"
        strana, zapis = self.otvori("zvuk-bez", skripta=skripta)
        expect(strana.locator("#zvuk-dugme")).to_be_hidden()
        self.odigraj_krug(strana, 1, po_tezini(1))
        self.proveri_cisto(zapis)

    def test_bez_skladista_prekidac_radi_do_zatvaranja_strane(self):
        skripta = LAZNI_ZVUK + """
        Object.defineProperty(window, "localStorage", { get() { throw new Error("zabranjeno"); } });
        """
        strana, zapis = self.otvori("zvuk-bez-skladista", skripta=skripta)
        dugme = strana.locator("#zvuk-dugme")
        expect(dugme).to_have_attribute("aria-pressed", "false")
        dugme.click()
        expect(dugme).to_have_attribute("aria-pressed", "true")
        self.assertEqual(zapis.izuzeci, [])

    def test_zvuk_zavisi_samo_od_statusa(self):
        # Uspeh i tih neuspeh nose isti status "gotovo" i moraju zvucati isto; dorada zvuci drugacije.
        seme = nadji_seme(
            po_tezini,
            lambda i: motor.TIHI_NEUSPEH in i and motor.USPEH in i and motor.DORADA in i,
        )
        referenca = odigraj_celu(seme, po_tezini)
        strana, zapis = self.otvori(seme, skripta=LAZNI_ZVUK)
        strana.locator("#zvuk-dugme").click()
        po_ishodu = {}
        for krug in range(1, 9):
            self.isprazni(strana)
            self.odigraj_krug(strana, krug, po_tezini(krug))
            ton = self.tonovi(strana)
            self.assertGreaterEqual(len(ton), 1, f"krug {krug} nije zasvirao")
            po_ishodu.setdefault(referenca["istorija"][krug - 1]["ishod"], []).append(ton)
        # Svaki krug istog ishoda zvuci isto (to pokriva i dva kruga sa statusom "gotovo").
        for ishod, svirano in po_ishodu.items():
            with self.subTest(ishod=ishod):
                self.assertTrue(all(ton == svirano[0] for ton in svirano), svirano)
        uspeh = po_ishodu[motor.USPEH][0]
        tih = po_ishodu[motor.TIHI_NEUSPEH][0]
        dorada = po_ishodu[motor.DORADA][0]
        self.assertEqual(uspeh, tih)
        self.assertNotEqual(uspeh, dorada)
        self.proveri_cisto(zapis)

    def test_ne_svira_na_gresku_ni_pri_ucitavanju(self):
        seme = nadji_seme(po_tezini, lambda i: motor.DORADA in i)
        strana, zapis = self.otvori(seme, skripta=LAZNI_ZVUK + ZVUK_UKLJUCEN_UNAPRED)
        expect(strana.locator("#zvuk-dugme")).to_have_attribute("aria-pressed", "true")
        self.assertEqual(self.tonovi(strana), [])
        for kod, telo in ((400, '{"greska": "neispravan_zahtev"}'), (409, '{"greska": "nema_igre"}')):
            with self.subTest(status=kod):
                def odgovori(ruta, _zahtev, kod=kod, telo=telo):
                    ruta.fulfill(status=kod, content_type="application/json", body=telo)

                strana.route("**/potez/", odgovori)
                self.izaberi(strana, po_tezini(1))
                expect(strana.locator("#potvrdi")).to_be_enabled()
                with strana.expect_response(lambda o: o.url.endswith("/potez/")):
                    strana.locator("#potvrdi").click()
                expect(strana.locator("#potvrdi")).to_be_enabled()
                self.assertEqual(self.tonovi(strana), [])
                strana.unroute("**/potez/")
        strana.route("**/potez/", lambda ruta: ruta.abort())
        strana.locator("#potvrdi").click()
        expect(strana.locator("#potvrdi")).to_be_enabled()
        self.assertEqual(self.tonovi(strana), [])
        strana.unroute("**/potez/")
        # Pravi odgovor posle gresaka svira.
        self.odigraj_krug(strana, 1, po_tezini(1))
        self.assertGreaterEqual(len(self.tonovi(strana)), 1)

    def test_izgled_prekidaca_na_tri_sirine(self):
        seme = nadji_seme(po_tezini, lambda i: motor.DORADA in i)
        for jezik in (SRPSKI, ENGLESKI):
            for sirina, visina in (TELEFON, TABLET, (1280, 900)):
                with self.subTest(jezik=jezik, sirina=sirina):
                    strana, zapis = self.otvori(seme, dimenzije=(sirina, visina), skripta=LAZNI_ZVUK, jezik=jezik)
                    dugme = strana.locator("#zvuk-dugme")
                    oznaka = f"zvuk-{jezik[:2]}-{sirina}"
                    expect(dugme).to_be_visible()
                    self.proveri_bez_prelivanja(strana, f"{oznaka}-iskljuceno")
                    self.snimi(strana, f"{oznaka}-iskljuceno")
                    dugme.click()
                    expect(dugme).to_have_attribute("aria-pressed", "true")
                    self.odigraj_krug(strana, 1, po_tezini(1))
                    strana.wait_for_function("() => document.getAnimations().length === 0")
                    self.proveri_bez_prelivanja(strana, f"{oznaka}-ukljuceno")
                    self.snimi(strana, f"{oznaka}-ukljuceno-posle-kruga")
                    self.proveri_cisto(zapis)

    def snimi(self, strana, ime):
        if SNIMCI:
            strana.wait_for_function("() => document.getAnimations().length === 0")
            strana.screenshot(path=os.path.join(SNIMCI, f"{ime}.png"), full_page=True, animations="disabled")

    def test_pravi_audio_context_bez_greske_u_konzoli(self):
        strana, zapis = self.otvori("zvuk-pravi")
        strana.locator("#zvuk-dugme").click()
        expect(strana.locator("#zvuk-dugme")).to_have_attribute("aria-pressed", "true")
        self.odigraj_krug(strana, 1, po_tezini(1))
        self.odigraj_krug(strana, 2, po_tezini(2))
        self.proveri_cisto(zapis)


# ---------- Spojevi zahteva 2026-11-12 (kontrolni skup nad celinom) ----------

# Svaki par vidljivih delova zaglavlja koji se preklapa (preko 0,5 px u obe ose) i deo van okvira zaglavlja.
JS_ZAGLAVLJE_PREKLAPANJE = """() => {
  const delovi = ['.vrh-naslov .znak', '.vrh-naslov .vrh-tekst', '#kako-link', '#jezik-forma', '#zvuk-dugme']
    .map((s) => [s, document.querySelector(s)])
    .filter(([, e]) => e && !e.hidden && e.getBoundingClientRect().width > 0);
  const sudari = [];
  for (let i = 0; i < delovi.length; i++) {
    for (let j = i + 1; j < delovi.length; j++) {
      const a = delovi[i][1].getBoundingClientRect();
      const b = delovi[j][1].getBoundingClientRect();
      const x = Math.min(a.right, b.right) - Math.max(a.left, b.left);
      const y = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      if (x > 0.5 && y > 0.5) sudari.push(delovi[i][0] + ' x ' + delovi[j][0]);
    }
  }
  const okvir = document.querySelector('.vrh-naslov').getBoundingClientRect();
  const van = delovi.filter(([, e]) => {
    const r = e.getBoundingClientRect();
    return r.right > okvir.right + 0.5 || r.left < okvir.left - 0.5;
  }).map(([s]) => s);
  return { vidljivi: delovi.map(([s]) => s), sudari: sudari, van: van };
}"""

# Elementi van ekrana koji NISU unutar .table-responsive (tabela sme da klizi samo u svom okviru).
JS_VAN_OSIM_TABELE = """() => {
  const sirina = document.documentElement.clientWidth;
  return [...document.body.querySelectorAll('*')].filter((e) => {
    if (e.closest('template, .table-responsive') || e.matches('.btn-check, script, style')) return false;
    const r = e.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && (r.right > sirina + 0.5 || r.left < -0.5);
  }).map((e) => e.tagName + '#' + e.id + '.' + e.className);
}"""

SNIMCI_QA = os.environ.get("ORKESTRATOR_SNIMCI_QA")
SIRINE_ZAGLAVLJA = (TELEFON, TABLET, (1280, 900))


def stavka_istorije(broj, dnevna=False):
    stavka = {
        "vrsta": "dnevna" if dnevna else "obicna",
        "kraj": (timezone.now() - datetime.timedelta(hours=broj)).astimezone(datetime.timezone.utc).isoformat(),
        "poeni": 100 - broj * 7,
        "ocena": OCENE[min(broj // 3, 3)],
        "cena": 123.4567 + broj,
        "minuti": 1234.5 + broj,
    }
    if dnevna:
        stavka["dan"] = timezone.localdate().isoformat()
    return stavka


class SpojeviTokTests(OsnovaToka):
    def snimi_qa(self, strana, ime, lokator=None):
        if not SNIMCI_QA:
            return
        os.makedirs(SNIMCI_QA, exist_ok=True)
        strana.wait_for_function("() => document.getAnimations().length === 0")
        putanja = os.path.join(SNIMCI_QA, f"{ime}.png")
        if lokator is None:
            strana.screenshot(path=putanja, full_page=True, animations="disabled")
        else:
            lokator.screenshot(path=putanja, animations="disabled")

    def otvori_sa_istorijom(self, dimenzije, jezik, istorija):
        sesija = SessionStore()
        sesija["igra"] = motor.nova_igra("spoj-istorija")
        sesija["istorija"] = istorija
        sesija.create()
        kontekst = self.novi_kontekst(dimenzije, jezik=jezik)
        kontekst.add_cookies(
            [{"name": settings.SESSION_COOKIE_NAME, "value": sesija.session_key, "url": self.live_server_url}]
        )
        strana = kontekst.new_page()
        zapis = Zapis(strana)
        strana.goto(self.live_server_url + "/")
        expect(strana.locator("#krug")).to_have_text(KRUG_TEKST[jezik[:2]].format(1))
        return strana, zapis

    def test_tok_kako_zvuk_osam_krugova_istorija(self):
        seme = nadji_seme(po_tezini, lambda i: motor.DORADA in i and motor.USPEH in i)
        strana, zapis = self.otvori(seme, skripta=LAZNI_ZVUK)
        expect(strana.locator("#istorija-prazno")).to_be_visible()
        # Pocetna -> "Како се игра" -> nazad.
        strana.locator("#kako-link").click()
        expect(strana).to_have_url(self.live_server_url + "/kako-se-igra/")
        expect(strana.locator("#kako-primer")).to_be_visible()
        strana.go_back()
        expect(strana).to_have_url(self.live_server_url + "/")
        expect(strana.locator("#krug")).to_have_text(KRUG_TEKST["sr"].format(1))
        # Zvuk ukljucen, osam krugova, svaki krug svira.
        dugme = strana.locator("#zvuk-dugme")
        dugme.click()
        expect(dugme).to_have_attribute("aria-pressed", "true")
        svirano = []
        for krug in range(1, 9):
            pre = strana.evaluate("() => window.__ton.length")
            self.odigraj_krug(strana, krug, po_tezini(krug))
            svirano.append(strana.evaluate("() => window.__ton.length") - pre)
        self.assertTrue(all(n >= 1 for n in svirano), svirano)
        poeni = strana.locator('#zavrsni [data-mesto="poeni"]').inner_text().strip()
        self.assertRegex(poeni, r"^\d+$")
        # Ponovno ucitavanje: "Моје партије" ima tu partiju, zvuk je i dalje ukljucen.
        strana.reload()
        expect(strana.locator("#zavrsni")).to_be_visible()
        redovi = strana.locator("#istorija-tabela tbody tr")
        expect(redovi).to_have_count(1)
        celije = redovi.first.locator("td")
        expect(celije.nth(1)).to_have_text("Обична игра")
        expect(celije.nth(2)).to_have_text(poeni)
        expect(dugme).to_have_attribute("aria-pressed", "true")
        expect(dugme).to_have_text(NATPIS_ZVUKA["sr"][0])
        self.snimi_qa(strana, "tok-posle-ucitavanja-1440")
        self.proveri_cisto(zapis)

    def test_zaglavlje_tri_sirine_oba_jezika(self):
        for jezik in (SRPSKI, ENGLESKI):
            for dimenzije in SIRINE_ZAGLAVLJA:
                oznaka = f"zaglavlje-{jezik[:2]}-{dimenzije[0]}"
                with self.subTest(oznaka):
                    strana, zapis = self.otvori("spoj-zaglavlje", dimenzije, jezik=jezik)
                    dugme = strana.locator("#zvuk-dugme")
                    expect(dugme).to_be_visible()
                    expect(strana.locator("#kako-link")).to_be_visible()
                    for stanje in ("iskljuceno", "ukljuceno"):
                        if stanje == "ukljuceno":
                            dugme.click()
                            expect(dugme).to_have_attribute("aria-pressed", "true")
                        mere = strana.evaluate(JS_ZAGLAVLJE_PREKLAPANJE)
                        self.assertEqual(len(mere["vidljivi"]), 5, mere)
                        self.assertEqual(mere["sudari"], [], f"{oznaka}-{stanje}")
                        self.assertEqual(mere["van"], [], f"{oznaka}-{stanje}")
                        self.proveri_bez_prelivanja(strana, f"{oznaka}-{stanje}")
                        self.snimi_qa(strana, f"{oznaka}-{stanje}", strana.locator(".vrh"))
                    self.proveri_cisto(zapis)

    def test_375_istorija_i_kako_se_igra(self):
        istorija = [stavka_istorije(n, dnevna=n % 2 == 0) for n in range(10)]
        for jezik in (SRPSKI, ENGLESKI):
            with self.subTest(jezik=jezik, strana="istorija"):
                strana, zapis = self.otvori_sa_istorijom(TELEFON, jezik, istorija)
                expect(strana.locator("#istorija-tabela tbody tr")).to_have_count(10)
                mere = strana.evaluate(JS_PRELIVANJE)
                self.assertLessEqual(mere["skrol"], mere["sirina"], mere)
                self.assertEqual(strana.evaluate(JS_VAN_OSIM_TABELE), [])
                okvir = strana.evaluate("""() => {
                  const o = document.querySelector('#istorija .table-responsive');
                  return { klizi: o.scrollWidth > o.clientWidth, desno: o.getBoundingClientRect().right,
                           sirina: document.documentElement.clientWidth };
                }""")
                self.assertLessEqual(okvir["desno"], okvir["sirina"] + 0.5, okvir)
                strana.locator("#istorija").scroll_into_view_if_needed()
                self.snimi_qa(strana, f"istorija-{jezik[:2]}-375", strana.locator("#istorija"))
                self.snimi_qa(strana, f"pocetna-sa-istorijom-{jezik[:2]}-375")
                self.proveri_cisto(zapis)
            with self.subTest(jezik=jezik, strana="kako-se-igra"):
                kontekst = self.novi_kontekst(TELEFON, jezik=jezik)
                strana = kontekst.new_page()
                zapis = Zapis(strana)
                odgovor = strana.goto(self.live_server_url + "/kako-se-igra/")
                self.assertEqual(odgovor.status, 200)
                expect(strana.locator("#kako-primer")).to_be_visible()
                self.proveri_bez_prelivanja(strana, f"kako-{jezik[:2]}-375")
                self.snimi_qa(strana, f"kako-{jezik[:2]}-375")
                self.proveri_cisto(zapis)
