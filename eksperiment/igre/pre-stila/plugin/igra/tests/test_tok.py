"""Tok kroz pravi pregledac. Zamke sync API-ja i live servera: plan.md, odeljak 7."""

import os
import re

from django.conf import settings
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from playwright.sync_api import expect, sync_playwright

from igra import motor, parametri

from .test_motor import (
    OPUS_HIGH,
    izbori,
    ishodi,
    nadji_seme,
    odigraj_celu,
    po_tezini,
    sve_opus,
)
from .test_prikazi import skriveni_kljucevi

ASYNC_UNSAFE = "DJANGO_ALLOW_ASYNC_UNSAFE"
ZAVRSEN_TEKST = "Игра је завршена"
PITANJE_NOVA = "Започети нову игру? Текућа партија се губи."
NAPOMENA = (
    "Цене и нивои размишљања су стварни подаци; вероватноће, казне и "
    "поени су измишљени параметри игре."
)
DOZVOLJENA_LATINICA = {"Haiku", "Sonnet", "Opus", "low", "high", "max", "CSS", "CRUD"}

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


class Zapis:
    """Sve sto pregledac prijavi kao gresku, i svi odgovori servera."""

    def __init__(self, strana):
        self.konzola = []
        self.izuzeci = []
        self.neuspeli = []
        self.odgovori = []
        self.zahtevi_poteza = []
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

    def novi_kontekst(self, dimenzije=RACUNAR):
        sirina, visina = dimenzije
        kontekst = self.pregledac.new_context(viewport={"width": sirina, "height": visina})
        self.addCleanup(kontekst.close)
        return kontekst

    def otvori(self, seme, dimenzije=RACUNAR):
        # Test nit dira bazu samo pre prvog goto.
        sesija = SessionStore()
        sesija["igra"] = motor.nova_igra(seme)
        sesija.create()
        kontekst = self.novi_kontekst(dimenzije)
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
        expect(strana.locator("#krug")).to_have_text("Круг 1 од 8")
        return strana, zapis

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
            expect(strana.locator("#krug")).to_have_text(f"Круг {krug + 1} од 8")
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
        expect(zavrsni.locator('[data-mesto="ocena"]')).to_have_text(kraj["ocena"])
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
        expect(tihe.first).to_contain_text(kraj["tihe_greske"][0]["zadatak"])
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

    def test_nova_posle_kraja_bez_potvrde(self):
        strana, zapis = self.otvori("seme-nova-kraj")
        self.odigraj_celu_u_pregledacu(strana, sve_opus)
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
        strana, zapis = self.otvori(seme_najduze_partije())
        self.odigraj_celu_u_pregledacu(strana, najduza_partija)
        expect(strana.locator("#zavrsni")).to_be_visible()
        self.proveri_cisto(zapis)
        # Kontrola: zapis zaista vidi saobracaj koji proverava.
        self.assertEqual(len(zapis.zahtevi_poteza), 8)
        self.assertGreaterEqual(len(zapis.odgovori), 11)

    def test_latinica_samo_u_nazivima(self):
        strana, zapis = self.otvori(seme_najduze_partije())
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
        self.proveri_cisto(zapis)

    def proveri_bez_prelivanja(self, strana, oznaka):
        mere = strana.evaluate(JS_PRELIVANJE)
        with self.subTest(ekran=oznaka):
            self.assertLessEqual(mere["skrol"], mere["sirina"], mere)
            self.assertEqual(mere["van"], [])
            self.assertEqual(mere["odseceno"], [])

    def proveri_sirinu(self, dimenzije):
        strana, zapis = self.otvori(seme_najduze_partije(), dimenzije)
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

    def test_768_bez_horizontalnog_skrola(self):
        self.proveri_sirinu(TABLET)

    def test_1440_bez_horizontalnog_skrola(self):
        self.proveri_sirinu(RACUNAR)


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
