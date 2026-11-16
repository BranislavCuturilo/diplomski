"""HTTP ugovor kroz Django klijent: plan.md, odeljak 6."""

import json
import re
from unittest import mock

from django.conf import settings
from django.contrib.sessions.models import Session
from django.core import signing
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.views.debug import SafeExceptionReporterFilter

from igra import motor

from .test_motor import (
    KRUGOVI,
    OPUS_HIGH,
    izbori,
    ishodi,
    nadji_seme,
    odigraj_celu,
    po_tezini,
    sve_haiku_low_malo,
    sve_opus,
)

JSON_TIP = "application/json"
ZABRANJENI_KLJUCEVI = {"seme", "sansa", "tezina", "ishod", "uspeh", "neuspeh", "bonus", "izbori"}
ZABRANJENE_RECI = re.compile(r"\b(seme|sansa|tih|tezina|ishod|uspeh|neuspeh|bonus)\b")
ZABRANJENE_RECI_CIRILICA = re.compile(r"(шанс|тежин|\bсеме\b)", re.IGNORECASE)
JSON_SCRIPT = re.compile(r'<script id="stanje-igre" type="application/json">(.*?)</script>', re.S)
UPIS_SESIJE = re.compile(r'^(INSERT INTO|UPDATE) "django_session"')
CITANJE_SESIJE = re.compile(r'^SELECT .* FROM "django_session"')

KLJUCEVI_PRIKAZA = {
    "faza",
    "krug",
    "ukupno_krugova",
    "zadatak",
    "budzet",
    "rok",
    "poslednji",
    "procene",
    "zavrsni",
}
KLJUCEVI_ZAVRSNOG = {
    "poeni",
    "ocena",
    "ukupna_cena",
    "ukupni_minuti",
    "budzet_prekoracen",
    "rok_prekoracen",
    "tihe_greske",
    "lekcije",
    "napomena",
}
KLJUCEVI_MERE = {"limit", "potroseno", "preostalo"}
KLJUCEVI_POSLEDNJEG = {"krug", "zadatak", "cena", "minuti", "status"}


def svi_kljucevi(objekat):
    if isinstance(objekat, dict):
        for kljuc, vrednost in objekat.items():
            yield kljuc
            yield from svi_kljucevi(vrednost)
    elif isinstance(objekat, list):
        for vrednost in objekat:
            yield from svi_kljucevi(vrednost)


def skriveni_kljucevi(objekat, zavrsena):
    nadjeni = set()
    for kljuc in svi_kljucevi(objekat):
        if kljuc in ZABRANJENI_KLJUCEVI:
            nadjeni.add(kljuc)
        elif kljuc.startswith("tih") and not (zavrsena and kljuc == "tihe_greske"):
            nadjeni.add(kljuc)
    return nadjeni


def stanje_iz_html(odgovor):
    pogodak = JSON_SCRIPT.search(odgovor.content.decode("utf-8"))
    if pogodak is None:
        raise AssertionError("nema json_script bloka stanje-igre")
    return json.loads(pogodak.group(1))


class OsnovaPrikaza(TestCase):
    def postavi_igru(self, seme, klijent=None):
        klijent = klijent or self.client
        sesija = klijent.session
        sesija["igra"] = motor.nova_igra(seme)
        sesija.save()

    def potez(self, krug, izbor=OPUS_HIGH, klijent=None):
        klijent = klijent or self.client
        telo = json.dumps({"krug": krug, "izbori": izbor})
        return klijent.post(reverse("potez"), data=telo, content_type=JSON_TIP)

    def sirovo(self, telo, klijent=None, tip=JSON_TIP):
        klijent = klijent or self.client
        return klijent.post(reverse("potez"), data=telo, content_type=tip)

    def stanje(self, klijent=None):
        return (klijent or self.client).session["igra"]

    def odigraj_do(self, krugova, strategija=sve_opus, klijent=None):
        for krug in range(1, krugova + 1):
            odgovor = self.potez(krug, strategija(krug), klijent=klijent)
            self.assertEqual(odgovor.status_code, 200)
        return odgovor


class SkrivenoTests(OsnovaPrikaza):
    def proveri_bez_skrivenog(self, odgovor, seme, zavrsena, html=False):
        self.assertNotIn(seme.encode("utf-8"), odgovor.content)
        for zaglavlje, vrednost in odgovor.items():
            self.assertNotIn(seme, str(vrednost), zaglavlje)
        if html:
            tekst = odgovor.content.decode("utf-8")
            self.assertEqual(ZABRANJENE_RECI.findall(tekst), [])
            self.assertEqual(ZABRANJENE_RECI_CIRILICA.findall(tekst), [])
            podaci = stanje_iz_html(odgovor)
        else:
            podaci = json.loads(odgovor.content)
        self.assertEqual(skriveni_kljucevi(podaci, zavrsena), set())

    def test_detektor_nalazi_skriveno_u_sirovom_stanju(self):
        seme = "tajno-seme-detektor"
        self.postavi_igru(seme)
        self.potez(1)
        sirovo = self.stanje()
        self.assertEqual(sirovo["seme"], seme)
        self.assertIn(seme, json.dumps(sirovo))
        self.assertEqual(skriveni_kljucevi(sirovo, False), {"seme", "ishod", "izbori"})
        self.assertEqual(skriveni_kljucevi({"tih": True}, False), {"tih"})
        self.assertEqual(skriveni_kljucevi({"tihe_greske": []}, False), {"tihe_greske"})
        self.assertEqual(skriveni_kljucevi({"tihe_greske": []}, True), set())
        self.assertEqual(ZABRANJENE_RECI.findall('{"sansa": 3}'), ["sansa"])

    def test_nijedan_odgovor_ne_sadrzi_skriveno(self):
        videnih_tihih = 0
        for rb, strategija in enumerate((sve_haiku_low_malo, po_tezini, sve_opus)):
            seme = f"tajno-seme-{rb}-x9q"
            klijent = Client()
            self.postavi_igru(seme, klijent)
            for krug in KRUGOVI:
                with self.subTest(seme=seme, krug=krug):
                    self.proveri_bez_skrivenog(klijent.get(reverse("pocetna")), seme, False, html=True)
                    pogresan = self.potez(krug + 1, strategija(krug), klijent)
                    self.assertEqual(pogresan.status_code, 409)
                    self.proveri_bez_skrivenog(pogresan, seme, False)
                    los = self.potez(krug, {**OPUS_HIGH, "model": "gpt"}, klijent)
                    self.assertEqual(los.status_code, 400)
                    self.proveri_bez_skrivenog(los, seme, False)
                    prihvacen = self.potez(krug, strategija(krug), klijent)
                    self.assertEqual(prihvacen.status_code, 200)
                    self.proveri_bez_skrivenog(prihvacen, seme, krug == 8)
            konacno = klijent.get(reverse("pocetna"))
            self.proveri_bez_skrivenog(konacno, seme, True, html=True)
            odbijen = self.potez(8, OPUS_HIGH, klijent)
            self.assertEqual(odbijen.status_code, 409)
            self.proveri_bez_skrivenog(odbijen, seme, True)
            kolacici = "".join(k.value for k in klijent.cookies.values())
            self.assertNotIn(seme, kolacici)
            videnih_tihih += ishodi(self.stanje(klijent)).count(motor.TIHI_NEUSPEH)
        self.assertGreater(videnih_tihih, 0, "provera mora da prodje kroz bar jedan tih neuspeh")

    def test_tih_neuspeh_bajt_identican_uspehu(self):
        uspesi = [motor.USPEH] * 4
        uspeh = nadji_seme(sve_opus, lambda i: i[:5] == uspesi + [motor.USPEH])
        tih = nadji_seme(sve_opus, lambda i: i[:5] == uspesi + [motor.TIHI_NEUSPEH])
        self.assertNotEqual(uspeh, tih)
        prvi, drugi = Client(), Client()
        self.postavi_igru(uspeh, prvi)
        self.postavi_igru(tih, drugi)
        for krug in range(1, 6):
            with self.subTest(krug=krug):
                a = self.potez(krug, OPUS_HIGH, prvi)
                b = self.potez(krug, OPUS_HIGH, drugi)
                self.assertEqual(a.status_code, 200)
                self.assertEqual(b.status_code, a.status_code)
                self.assertEqual(b.content, a.content)
        self.assertEqual(self.stanje(prvi)["istorija"][4]["ishod"], motor.USPEH)
        self.assertEqual(self.stanje(drugi)["istorija"][4]["ishod"], motor.TIHI_NEUSPEH)
        self.assertEqual(
            stanje_iz_html(prvi.get(reverse("pocetna"))),
            stanje_iz_html(drugi.get(reverse("pocetna"))),
        )

    def test_status_tihog_neuspeha_je_gotovo(self):
        seme = nadji_seme(sve_opus, lambda i: i[4] == motor.TIHI_NEUSPEH)
        self.postavi_igru(seme)
        podaci = json.loads(self.odigraj_do(5).content)
        self.assertEqual(podaci["poslednji"]["status"], "готово")
        self.assertEqual(podaci["poslednji"]["krug"], 5)

    def test_status_dorade(self):
        seme = nadji_seme(lambda _k: izbori("haiku"), lambda i: i[0] == motor.DORADA)
        self.postavi_igru(seme)
        podaci = json.loads(self.potez(1, izbori("haiku")).content)
        self.assertEqual(podaci["poslednji"]["status"], "враћено на дораду")
        self.assertEqual(podaci["poslednji"]["cena"], 0.036)
        self.assertEqual(podaci["poslednji"]["minuti"], 5.0)

    def test_tacan_skup_kljuceva_javnog_prikaza(self):
        seme = nadji_seme(
            sve_opus, lambda i: i.count(motor.TIHI_NEUSPEH) >= 1
        )
        self.postavi_igru(seme)
        pocetak = stanje_iz_html(self.client.get(reverse("pocetna")))
        self.assertEqual(set(pocetak), KLJUCEVI_PRIKAZA)
        self.assertIsNone(pocetak["poslednji"])
        self.assertIsNone(pocetak["zavrsni"])
        self.assertEqual(set(pocetak["zadatak"]), {"naziv"})

        for krug in range(1, 8):
            podaci = json.loads(self.potez(krug).content)
            with self.subTest(krug=krug):
                self.assertEqual(set(podaci), KLJUCEVI_PRIKAZA)
                self.assertEqual(podaci["faza"], "igra")
                self.assertEqual(set(podaci["zadatak"]), {"naziv"})
                self.assertEqual(set(podaci["budzet"]), KLJUCEVI_MERE)
                self.assertEqual(set(podaci["rok"]), KLJUCEVI_MERE)
                self.assertEqual(set(podaci["poslednji"]), KLJUCEVI_POSLEDNJEG)
                self.assertEqual(len(podaci["procene"]), 81)
                for procena in podaci["procene"].values():
                    self.assertEqual(set(procena), {"cena", "minuti"})
                self.assertIsNone(podaci["zavrsni"])

        kraj = json.loads(self.potez(8).content)
        self.assertEqual(set(kraj), KLJUCEVI_PRIKAZA)
        self.assertEqual(kraj["faza"], "zavrsena")
        self.assertIsNone(kraj["zadatak"])
        self.assertIsNone(kraj["procene"])
        self.assertEqual(kraj["poslednji"]["krug"], 8)
        self.assertEqual(set(kraj["zavrsni"]), KLJUCEVI_ZAVRSNOG)
        self.assertGreaterEqual(len(kraj["zavrsni"]["tihe_greske"]), 1)
        self.assertEqual(
            set(kraj["zavrsni"]["tihe_greske"][0]),
            {"krug", "zadatak", "dodatak_cena", "dodatak_minuti"},
        )
        self.assertGreaterEqual(len(kraj["zavrsni"]["lekcije"]), 1)
        self.assertEqual(set(kraj["zavrsni"]["lekcije"][0]), {"tekst", "odeljak"})

    def test_kolacici_bez_stanja(self):
        seme = "tajno-seme-kolacic"
        self.postavi_igru(seme)
        odgovor = self.client.get(reverse("pocetna"))
        self.assertEqual(odgovor.status_code, 200)
        self.potez(1)
        self.assertEqual(set(self.client.cookies), {"sessionid", "csrftoken"})

        vrednost = self.client.cookies["sessionid"].value
        self.assertRegex(vrednost, r"^[a-z0-9]{32}$")
        self.assertNotIn(seme, vrednost)
        with self.assertRaises(signing.BadSignature):
            signing.loads(vrednost)

        # Kontrola: seme zaista postoji u sesiji koju taj kljuc oznacava, u bazi.
        red = Session.objects.get(pk=vrednost)
        self.assertEqual(red.get_decoded()["igra"]["seme"], seme)

    def test_session_engine_baza(self):
        self.assertEqual(settings.SESSION_ENGINE, "django.contrib.sessions.backends.db")


class DeterminizamHttpTests(OsnovaPrikaza):
    def test_isto_seme_isti_odgovori(self):
        for strategija in (sve_haiku_low_malo, po_tezini):
            seme = f"isto-{strategija.__name__}"
            prvi, drugi = Client(), Client()
            self.postavi_igru(seme, prvi)
            self.postavi_igru(seme, drugi)
            for krug in KRUGOVI:
                with self.subTest(strategija=strategija.__name__, krug=krug):
                    a = self.potez(krug, strategija(krug), prvi)
                    b = self.potez(krug, strategija(krug), drugi)
                    self.assertEqual(a.status_code, 200)
                    self.assertEqual(b.status_code, 200)
                    self.assertEqual(a.content, b.content)

    def test_igra_preko_http_isto_kao_motor(self):
        seme = "referenca-http"
        self.postavi_igru(seme)
        for krug in KRUGOVI:
            podaci = json.loads(self.potez(krug, po_tezini(krug)).content)
        self.assertEqual(podaci, motor.javni_prikaz(odigraj_celu(seme, po_tezini)))


class GreskeTests(OsnovaPrikaza):
    def setUp(self):
        self.seme = "seme-greske"
        self.postavi_igru(self.seme)

    def proveri_netaknuto(self, pre):
        self.assertEqual(self.stanje(), pre)

    def test_pogresan_krug_409(self):
        self.potez(1)
        pre = self.stanje()
        for krug in (1, 3, 0, -1, 9, 10**30):
            with self.subTest(krug=krug):
                odgovor = self.potez(krug)
                self.assertEqual(odgovor.status_code, 409)
                podaci = json.loads(odgovor.content)
                self.assertEqual(set(podaci), {"greska", "stanje"})
                self.assertEqual(podaci["greska"], "pogresan_krug")
                self.assertEqual(set(podaci["stanje"]), KLJUCEVI_PRIKAZA)
                self.assertEqual(podaci["stanje"]["krug"], 2)
                self.proveri_netaknuto(pre)

    def test_zavrsena_igra_409(self):
        self.odigraj_do(8)
        pre = self.stanje()
        self.assertTrue(pre["zavrsena"])
        for krug in (8, 9, 1):
            with self.subTest(krug=krug):
                odgovor = self.potez(krug)
                self.assertEqual(odgovor.status_code, 409)
                podaci = json.loads(odgovor.content)
                self.assertEqual(podaci["greska"], "igra_zavrsena")
                self.assertEqual(podaci["stanje"]["faza"], "zavrsena")
                self.proveri_netaknuto(pre)

    def test_nepoznat_izbor_400(self):
        pre = self.stanje()
        for polje, vrednost in (
            ("model", "gpt"),
            ("nivo", "ultra"),
            ("kontekst", "nista"),
            ("podela", "sto"),
        ):
            with self.subTest(polje=polje):
                odgovor = self.potez(1, {**OPUS_HIGH, polje: vrednost})
                self.assertEqual(odgovor.status_code, 400)
                self.assertEqual(json.loads(odgovor.content), {"greska": "neispravan_zahtev"})
                self.proveri_netaknuto(pre)

    def test_neispravan_zahtev_400(self):
        ispravno = {"krug": 1, "izbori": OPUS_HIGH}
        dopuna = lambda n: json.dumps(ispravno) + " " * n
        slucajevi = {
            "nije json": b"nije json",
            "prazno telo": b"",
            "neispravan utf-8": b'\xff\xfe{"krug": 1}',
            "niz": b"[]",
            "broj": b"3",
            "string": b'"krug"',
            "null": b"null",
            "telo preko 2 KB": dopuna(2100).encode(),
            "duboko ugnezdeno": b"[" * 1024 + b"]" * 1024,
            "duboko bez zatvaranja": b"[" * 2048,
            "duboko u izborima": (b'{"krug": 1, "izbori": ' + b"[" * 900 + b"]" * 900 + b"}"),
            "nema izbora": json.dumps({"krug": 1}).encode(),
            "nema kruga": json.dumps({"izbori": OPUS_HIGH}).encode(),
            "prazan objekat": b"{}",
            "krug true": json.dumps({"krug": True, "izbori": OPUS_HIGH}).encode(),
            "krug string": json.dumps({"krug": "1", "izbori": OPUS_HIGH}).encode(),
            "krug decimalan": json.dumps({"krug": 1.0, "izbori": OPUS_HIGH}).encode(),
            "krug null": json.dumps({"krug": None, "izbori": OPUS_HIGH}).encode(),
            "krug niz": json.dumps({"krug": [1], "izbori": OPUS_HIGH}).encode(),
            "krug NaN": b'{"krug": NaN, "izbori": ' + json.dumps(OPUS_HIGH).encode() + b"}",
            "izbori null": json.dumps({"krug": 1, "izbori": None}).encode(),
            "izbori niz": json.dumps({"krug": 1, "izbori": []}).encode(),
            "izbori string": json.dumps({"krug": 1, "izbori": "opus"}).encode(),
            "izbor nedostaje": json.dumps(
                {"krug": 1, "izbori": {"model": "opus", "nivo": "high", "kontekst": "taman"}}
            ).encode(),
            "vrednost niz": json.dumps({"krug": 1, "izbori": {**OPUS_HIGH, "model": []}}).encode(),
            "vrednost objekat": json.dumps(
                {"krug": 1, "izbori": {**OPUS_HIGH, "nivo": {}}}
            ).encode(),
            "vrednost broj": json.dumps(
                {"krug": 1, "izbori": {**OPUS_HIGH, "kontekst": 1}}
            ).encode(),
            "vrednost null": json.dumps(
                {"krug": 1, "izbori": {**OPUS_HIGH, "podela": None}}
            ).encode(),
        }
        pre = self.stanje()
        for ime, telo in slucajevi.items():
            with self.subTest(ime=ime):
                odgovor = self.sirovo(telo)
                self.assertEqual(odgovor.status_code, 400)
                self.assertEqual(json.loads(odgovor.content), {"greska": "neispravan_zahtev"})
                self.proveri_netaknuto(pre)

    def test_telo_tacno_2_kb_prolazi(self):
        telo = json.dumps({"krug": 1, "izbori": OPUS_HIGH})
        telo += " " * (2048 - len(telo))
        self.assertEqual(self.sirovo(telo.encode()).status_code, 200)

    def test_telo_2049_bajtova_odbijeno(self):
        telo = json.dumps({"krug": 1, "izbori": OPUS_HIGH})
        telo += " " * (2049 - len(telo))
        self.assertEqual(self.sirovo(telo.encode()).status_code, 400)

    def test_tela_koja_padaju_u_middleware_daju_400(self):
        csrf = Client(enforce_csrf_checks=True)
        self.postavi_igru("seme-csrf", csrf)
        csrf.get(reverse("pocetna"))
        token = csrf.cookies["csrftoken"].value
        pre = self.stanje(csrf)
        slucajevi = [
            ("multipart bez granice", b"--x", "multipart/form-data"),
            ("forma preko 2,5 MB", b"a=" + b"b" * (2621440 + 1), "application/x-www-form-urlencoded"),
            ("json preko 2,5 MB", b" " * (2621440 + 1), JSON_TIP),
        ]
        for ime, telo, tip in slucajevi:
            with self.subTest(ime=ime):
                odgovor = csrf.post(
                    reverse("potez"), data=telo, content_type=tip, headers={"X-CSRFToken": token}
                )
                self.assertEqual(odgovor.status_code, 400)
                self.assertEqual(self.stanje(csrf), pre)

    def test_stanje_netaknuto_posle_greske(self):
        self.potez(1)
        pre = self.stanje()
        red_pre = Session.objects.get(pk=self.client.session.session_key).session_data
        for ime, odgovor in (
            ("nepoznat izbor", self.potez(2, {**OPUS_HIGH, "model": "gpt"})),
            ("dodatni kljuc", self.sirovo(json.dumps({"krug": 2, "izbori": OPUS_HIGH, "cena": 0}))),
            ("nije json", self.sirovo(b"x")),
            ("pogresan krug", self.potez(5)),
        ):
            with self.subTest(ime=ime):
                self.assertIn(odgovor.status_code, (400, 409))
        red_posle = Session.objects.get(pk=self.client.session.session_key).session_data
        self.assertEqual(red_posle, red_pre)
        self.proveri_netaknuto(pre)
        # Kontrola: igra posle odbijenih zahteva ide dalje od istog kruga.
        self.assertEqual(self.potez(2).status_code, 200)
        self.assertEqual(self.stanje()["krug"], 3)

    def test_prednost_400_nad_409(self):
        los = {**OPUS_HIGH, "model": "gpt"}
        self.assertEqual(self.potez(5, los).status_code, 400)
        self.assertEqual(self.sirovo(json.dumps({"krug": 5})).status_code, 400)
        self.odigraj_do(8)
        self.assertEqual(self.potez(8, los).status_code, 400)
        bez_igre = Client()
        self.assertEqual(self.potez(1, los, bez_igre).status_code, 400)

    def test_nema_igre_409(self):
        klijent = Client()
        odgovor = self.potez(1, OPUS_HIGH, klijent)
        self.assertEqual(odgovor.status_code, 409)
        self.assertEqual(json.loads(odgovor.content), {"greska": "nema_igre", "stanje": None})

    def test_dodatni_kljuc_400(self):
        pre = self.stanje()
        slucajevi = [
            {"krug": 1, "izbori": OPUS_HIGH, "cena": 0},
            {"krug": 1, "izbori": OPUS_HIGH, "poeni": 100},
            {"krug": 1, "izbori": OPUS_HIGH, "ishod": "uspeh"},
            {"krug": 1, "izbori": OPUS_HIGH, "seme": "1"},
            {"krug": 1, "izbori": {**OPUS_HIGH, "cena": 0}},
        ]
        for telo in slucajevi:
            with self.subTest(telo=telo):
                odgovor = self.sirovo(json.dumps(telo))
                self.assertEqual(odgovor.status_code, 400)
                self.proveri_netaknuto(pre)

    def test_bez_csrf_403(self):
        klijent = Client(enforce_csrf_checks=True)
        self.postavi_igru("seme-csrf", klijent)
        klijent.get(reverse("pocetna"))
        token = klijent.cookies["csrftoken"].value
        pre = self.stanje(klijent)
        telo = json.dumps({"krug": 1, "izbori": OPUS_HIGH})

        odgovor = klijent.post(reverse("potez"), data=telo, content_type=JSON_TIP)
        self.assertEqual(odgovor.status_code, 403)
        self.assertEqual(klijent.post(reverse("nova")).status_code, 403)
        self.assertEqual(self.stanje(klijent), pre)

        # Kontrola: isti klijent sa tokenom prolazi, pa 403 dolazi od CSRF-a.
        odgovor = klijent.post(
            reverse("potez"), data=telo, content_type=JSON_TIP, headers={"X-CSRFToken": token}
        )
        self.assertEqual(odgovor.status_code, 200)
        odgovor = klijent.post(reverse("nova"), data={"csrfmiddlewaretoken": token})
        self.assertEqual(odgovor.status_code, 302)

    def test_potez_get_405(self):
        self.assertEqual(self.client.get(reverse("potez")).status_code, 405)
        self.assertEqual(self.client.put(reverse("potez")).status_code, 405)

    def test_nova_get_405(self):
        self.assertEqual(self.client.get(reverse("nova")).status_code, 405)

    def test_pocetna_post_405(self):
        self.assertEqual(self.client.post(reverse("pocetna")).status_code, 405)

    def test_dupli_potez_drugi_409_stanje_isto(self):
        prvi = self.potez(1)
        self.assertEqual(prvi.status_code, 200)
        posle_prvog = self.stanje()
        drugi = self.potez(1)
        self.assertEqual(drugi.status_code, 409)
        podaci = json.loads(drugi.content)
        self.assertEqual(podaci["greska"], "pogresan_krug")
        self.assertEqual(self.stanje(), posle_prvog)
        self.assertEqual(podaci["stanje"], json.loads(prvi.content))

    def test_dupli_potez_na_poslednjem_krugu(self):
        prvi = self.odigraj_do(8)
        posle = self.stanje()
        drugi = self.potez(8)
        self.assertEqual(drugi.status_code, 409)
        self.assertEqual(json.loads(drugi.content)["stanje"], json.loads(prvi.content))
        self.assertEqual(self.stanje(), posle)


class PocetnaTests(OsnovaPrikaza):
    def test_get_bez_igre_pravi_igru(self):
        odgovor = self.client.get(reverse("pocetna"))
        self.assertEqual(odgovor.status_code, 200)
        self.assertRegex(self.stanje()["seme"], r"^[0-9a-f]{32}$")
        self.assertEqual(self.stanje()["krug"], 1)

    def test_drugi_get_cuva_igru(self):
        self.client.get(reverse("pocetna"))
        seme = self.stanje()["seme"]
        self.client.get(reverse("pocetna"))
        self.assertEqual(self.stanje()["seme"], seme)

    def test_novi_posetioci_imaju_razlicito_seme(self):
        prvi, drugi = Client(), Client()
        prvi.get(reverse("pocetna"))
        drugi.get(reverse("pocetna"))
        self.assertNotEqual(self.stanje(prvi)["seme"], self.stanje(drugi)["seme"])

    def test_csrf_kolacic_i_bez_kesa(self):
        odgovor = self.client.get(reverse("pocetna"))
        self.assertIn("csrftoken", odgovor.cookies)
        self.assertIn("no-store", odgovor["Cache-Control"])

    def test_json_script_daje_recnik(self):
        self.postavi_igru("seme-skript")
        pocetak = stanje_iz_html(self.client.get(reverse("pocetna")))
        self.assertIsInstance(pocetak, dict)
        self.assertEqual(pocetak["krug"], 1)
        self.assertEqual(pocetak["faza"], "igra")
        self.assertEqual(pocetak["zadatak"]["naziv"], "Превод почетне стране")
        self.assertEqual(pocetak["budzet"], {"limit": 24, "potroseno": 0.0, "preostalo": 24.0})
        self.assertEqual(pocetak["rok"], {"limit": 150, "potroseno": 0.0, "preostalo": 150.0})

        # Srpska lokalizacija bi kroz {{ }} dala zarez i neispravan JSON.
        self.potez(1)
        posle = stanje_iz_html(self.client.get(reverse("pocetna")))
        self.assertEqual(posle["krug"], 2)
        self.assertEqual(posle["budzet"]["potroseno"], 0.72)

    def test_opcije_bez_brojeva_i_bez_podrazumevanog_izbora(self):
        odgovor = self.client.get(reverse("pocetna"))
        opcije = odgovor.context["opcije"]
        self.assertEqual(
            {g: [o["kljuc"] for o in v] for g, v in opcije.items()},
            {
                "model": ["haiku", "sonnet", "opus"],
                "nivo": ["low", "high", "max"],
                "kontekst": ["malo", "taman", "sve"],
                "podela": ["sam", "tri", "pedeset"],
            },
        )
        for grupa in opcije.values():
            for opcija in grupa:
                with self.subTest(opcija=opcija["kljuc"]):
                    self.assertEqual(set(opcija), {"kljuc", "naziv", "opis"})
                    self.assertNotRegex(opcija["opis"], r"[0-9%]")
                    self.assertNotIn("тих", opcija["opis"].lower())
        html = odgovor.content.decode("utf-8")
        radio = re.findall(r"<input[^>]*type=\"radio\"[^>]*>", html)
        self.assertEqual(len(radio), 12)
        self.assertEqual([r for r in radio if re.search(r"\bchecked\b", r)], [])

    def test_zadaci_redom_preko_http(self):
        self.postavi_igru("seme-redosled")
        nazivi = [stanje_iz_html(self.client.get(reverse("pocetna")))["zadatak"]["naziv"]]
        for krug in range(1, 8):
            nazivi.append(json.loads(self.potez(krug).content)["zadatak"]["naziv"])
        self.assertEqual(
            nazivi,
            [
                "Превод почетне стране",
                "Шаблон листе и форме",
                "CSS и прилагођавање телефону",
                "CRUD прикази",
                "Модел података и миграција",
                "Провера права приступа",
                "Аутоматски тестови",
                "Безбедносна ревизија",
            ],
        )

    def test_zavrsena_igra_ostaje_na_pocetnoj(self):
        self.postavi_igru("seme-kraj")
        self.odigraj_do(8)
        podaci = stanje_iz_html(self.client.get(reverse("pocetna")))
        self.assertEqual(podaci["faza"], "zavrsena")
        self.assertEqual(set(podaci["zavrsni"]), KLJUCEVI_ZAVRSNOG)


class NovaTests(OsnovaPrikaza):
    def test_nova_302_i_novo_seme(self):
        self.postavi_igru("staro-seme")
        self.odigraj_do(8)
        odgovor = self.client.post(reverse("nova"))
        self.assertRedirects(odgovor, reverse("pocetna"), fetch_redirect_response=False)
        novo = self.stanje()
        self.assertNotEqual(novo["seme"], "staro-seme")
        self.assertRegex(novo["seme"], r"^[0-9a-f]{32}$")
        self.assertEqual(novo["krug"], 1)
        self.assertFalse(novo["zavrsena"])
        self.assertEqual(novo["istorija"], [])

    def test_nova_usred_igre_pravi_novu(self):
        self.postavi_igru("staro-seme")
        self.odigraj_do(3)
        odgovor = self.client.post(reverse("nova"))
        self.assertEqual(odgovor.status_code, 302)
        novo = self.stanje()
        self.assertNotEqual(novo["seme"], "staro-seme")
        self.assertEqual(novo["krug"], 1)
        self.assertEqual(novo["potroseno"], 0.0)

    def test_nova_ignorise_seme(self):
        self.client.post(reverse("nova"), data={"seme": "zadato", "krug": "8", "poeni": "100"})
        novo = self.stanje()
        self.assertNotEqual(novo["seme"], "zadato")
        self.assertEqual(novo["krug"], 1)


class ReferentneIgreTests(OsnovaPrikaza):
    def test_sve_uspesno_opus(self):
        seme = nadji_seme(sve_opus, lambda i: i == [motor.USPEH] * 8)
        self.postavi_igru(seme)
        kraj = json.loads(self.odigraj_do(8).content)
        z = kraj["zavrsni"]
        self.assertEqual(z["poeni"], 100)
        self.assertEqual(z["ocena"], "одличан оркестратор")
        self.assertEqual(z["ukupna_cena"], 19.44)
        self.assertEqual(z["ukupni_minuti"], 135.0)
        self.assertFalse(z["budzet_prekoracen"])
        self.assertFalse(z["rok_prekoracen"])
        self.assertEqual(z["tihe_greske"], [])
        self.assertEqual(
            z["lekcije"], [{"tekst": "Најскупљи модел није увек најбољи избор.", "odeljak": "3.2"}]
        )
        self.assertEqual(
            z["napomena"],
            "Цене и нивои размишљања су стварни подаци; вероватноће, казне и "
            "поени су измишљени параметри игре.",
        )

    def test_tih_neuspeh_prekoracuje_oba_limita(self):
        seme = nadji_seme(
            sve_opus, lambda i: i == [motor.USPEH] * 4 + [motor.TIHI_NEUSPEH] + [motor.USPEH] * 3
        )
        self.postavi_igru(seme)
        kraj = json.loads(self.odigraj_do(8).content)
        z = kraj["zavrsni"]
        self.assertEqual(z["poeni"], 25)
        self.assertEqual(z["ocena"], "пожар")
        self.assertEqual(z["ukupna_cena"], 32.4)
        self.assertEqual(z["ukupni_minuti"], 165.0)
        self.assertEqual(
            z["tihe_greske"],
            [
                {
                    "krug": 5,
                    "zadatak": "Модел података и миграција",
                    "dodatak_cena": 12.96,
                    "dodatak_minuti": 30.0,
                }
            ],
        )
        self.assertEqual(kraj["budzet"], {"limit": 24, "potroseno": 32.4, "preostalo": -8.4})
        self.assertEqual(kraj["rok"], {"limit": 150, "potroseno": 165.0, "preostalo": -15.0})


class TransakcijaTests(OsnovaPrikaza):
    def test_rezim_transakcije_je_immediate(self):
        self.assertEqual(settings.DATABASES["default"]["OPTIONS"]["transaction_mode"], "IMMEDIATE")
        self.assertEqual(connection.transaction_mode, "IMMEDIATE")


class UpisSesijeTests(OsnovaPrikaza):
    def uz_upite(self, radnja):
        with CaptureQueriesContext(connection) as uhvaceno:
            odgovor = radnja()
        return odgovor, [upit["sql"] for upit in uhvaceno]

    def upisi(self, upiti):
        return [upit for upit in upiti if UPIS_SESIJE.match(upit)]

    def test_potez_200_tacno_jedan_upis(self):
        self.postavi_igru("seme-upis")
        odgovor, upiti = self.uz_upite(lambda: self.potez(1))
        self.assertEqual(odgovor.status_code, 200)
        self.assertEqual(len(self.upisi(upiti)), 1, upiti)
        self.assertEqual(self.stanje()["krug"], 2)

    def test_potez_cita_i_upisuje_u_istoj_transakciji(self):
        self.postavi_igru("seme-transakcija")
        odgovor, upiti = self.uz_upite(lambda: self.potez(1))
        self.assertEqual(odgovor.status_code, 200)
        # U TestCase-u je spoljni atomic prikaza SAVEPOINT; upis posle njegovog RELEASE je van brave.
        otvaranje = next(i for i, upit in enumerate(upiti) if upit.startswith("SAVEPOINT"))
        zatvaranje = upiti.index("RELEASE " + upiti[otvaranje])
        citanja = [i for i, upit in enumerate(upiti) if CITANJE_SESIJE.match(upit)]
        upisi = [i for i, upit in enumerate(upiti) if UPIS_SESIJE.match(upit)]
        self.assertEqual(len(upisi), 1, upiti)
        self.assertGreaterEqual(len(citanja), 1, upiti)
        self.assertLess(otvaranje, citanja[0], upiti)
        self.assertLess(citanja[-1], upisi[0], upiti)
        self.assertLess(upisi[0], zatvaranje, upiti)

    def test_odbijen_potez_nema_upisa(self):
        slucajevi = [
            ("pogresan krug", 409, lambda: self.potez(2)),
            ("nepoznat izbor", 400, lambda: self.potez(1, izbori("gpt"))),
            ("neispravan json", 400, lambda: self.sirovo("{")),
        ]
        self.postavi_igru("seme-odbijen")
        pre = self.stanje()
        for ime, status, radnja in slucajevi:
            with self.subTest(ime=ime):
                odgovor, upiti = self.uz_upite(radnja)
                self.assertEqual(odgovor.status_code, status)
                self.assertEqual(self.upisi(upiti), [])
                self.assertEqual(self.stanje(), pre)

    def test_zavrsena_igra_nema_upisa(self):
        self.postavi_igru("seme-zavrsena-upis")
        self.odigraj_do(8)
        odgovor, upiti = self.uz_upite(lambda: self.potez(8))
        self.assertEqual(odgovor.status_code, 409)
        self.assertEqual(json.loads(odgovor.content)["greska"], "igra_zavrsena")
        self.assertEqual(self.upisi(upiti), [])

    def test_bez_igre_nema_upisa(self):
        odgovor, upiti = self.uz_upite(lambda: self.potez(1, klijent=Client()))
        self.assertEqual(odgovor.status_code, 409)
        self.assertEqual(json.loads(odgovor.content)["greska"], "nema_igre")
        self.assertEqual(self.upisi(upiti), [])

    def test_nova_sa_sesijom_jedan_upis_u_postojecu(self):
        self.postavi_igru("seme-nova-upis")
        kljuc = self.client.session.session_key
        odgovor, upiti = self.uz_upite(lambda: self.client.post(reverse("nova")))
        self.assertEqual(odgovor.status_code, 302)
        self.assertEqual(len(self.upisi(upiti)), 1, upiti)
        self.assertEqual(self.client.session.session_key, kljuc)
        self.assertNotEqual(self.stanje()["seme"], "seme-nova-upis")

    def test_nova_bez_sesije_jedan_upis_i_kolacic(self):
        klijent = Client()
        odgovor, upiti = self.uz_upite(lambda: klijent.post(reverse("nova")))
        self.assertEqual(odgovor.status_code, 302)
        self.assertEqual(len(self.upisi(upiti)), 1, upiti)
        self.assertIn(settings.SESSION_COOKIE_NAME, odgovor.cookies)
        self.assertEqual(self.stanje(klijent)["krug"], 1)


@override_settings(DEBUG=True)
class TehnickaStranaTests(OsnovaPrikaza):
    SEME = "tajno-seme-tehnicka-strana-7f3a91"
    OZNAKA_KVARA = "ubaceni-kvar-b2c4"

    def pokreni_kvar(self, prihvata="text/html"):
        klijent = Client(raise_request_exception=False)
        self.postavi_igru(self.SEME, klijent=klijent)
        # Tvrdnja o odsustvu vredi samo ako seme zaista postoji u stanju koje prikaz drzi.
        self.assertEqual(self.stanje(klijent)["seme"], self.SEME)
        telo = json.dumps({"krug": 1, "izbori": OPUS_HIGH})
        with mock.patch("igra.views.motor.odigraj_potez", side_effect=RuntimeError(self.OZNAKA_KVARA)):
            odgovor = klijent.post(
                reverse("potez"), data=telo, content_type=JSON_TIP, headers={"accept": prihvata}
            )
        self.assertEqual(odgovor.status_code, 500)
        return odgovor.content.decode("utf-8")

    def test_tehnicka_strana_bez_semena(self):
        for prihvata in ("text/html", "text/plain"):
            with self.subTest(prihvata=prihvata):
                telo = self.pokreni_kvar(prihvata)
                self.assertIn(self.OZNAKA_KVARA, telo)
                self.assertNotIn(self.SEME, telo)

    def test_kontrola_bez_filtera_seme_se_vidi(self):
        # Dokaz da bi provera nasla seme: bez nase izmene filtera okvir prikaza ga ispisuje.
        with mock.patch(
            "orkestrator.greske.FilterBezPromenljivih.get_traceback_frame_variables",
            SafeExceptionReporterFilter.get_traceback_frame_variables,
        ):
            telo = self.pokreni_kvar()
        self.assertIn(self.OZNAKA_KVARA, telo)
        self.assertIn(self.SEME, telo)
