"""HTTP ugovor kroz Django klijent: plan.md, odeljak 6."""

import copy
import io
import csv
import datetime
import hashlib
import html as html_modul
import importlib
import itertools
import json
import logging
import os
import pathlib
import re
import secrets
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import urllib.parse
from io import StringIO
from unittest import mock
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import SESSION_KEY, get_user_model
from django.contrib.auth.hashers import MD5PasswordHasher, make_password
from django.contrib.auth.models import Permission
from django.contrib.sessions.models import Session
from django.core import signing
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import CommandError, call_command
from django.db import DEFAULT_DB_ALIAS, IntegrityError, connection, connections, transaction
from django.db.backends.utils import CursorWrapper
from django.db.utils import ConnectionHandler
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.db.models import F, Value
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.template.loader import render_to_string
from django.test.utils import CaptureQueriesContext
from django.urls import get_resolver, reverse
from django.utils import timezone, translation
from django.utils.crypto import salted_hmac
from django.utils.module_loading import import_string
from django.utils.translation import gettext, ngettext
from django.views.debug import SafeExceptionReporterFilter

from igra import brisanje, forme, imena, moderacija, motor, nalozi, tekstovi, views
from igra import parametri as p
from igra.models import (
    DeljeniRezultat,
    NalogModeratora,
    NepodobnoIme,
    PokusajPrijave,
    PrijavaImena,
    Rezultat,
    ZapisDnevnika,
)

from .test_motor import (
    KRUGOVI,
    LEKCIJE_SR,
    NAPOMENA_SR,
    NEVIDLJIVI_ZNACI,
    OCENE_SR,
    ODBIJENA_IMENA,
    OPUS_HIGH,
    PRIHVACENA_IMENA,
    SEME_JEDNA_TIHA,
    ZADACI_SR,
    bez_verzije,
    izbori,
    ishodi,
    nadji_seme,
    nevidljivi_polozaji,
    odigraj_celu,
    po_tezini,
    staro_zavrseno,
    sve_haiku_low_malo,
    sve_opus,
)

JSON_TIP = "application/json"
ZABRANJENI_KLJUCEVI = {
    "seme", "sansa", "tezina", "ishod", "uspeh", "neuspeh", "bonus", "izbori",
    # Rang lista: bela lista je ime, poeni, ocena, datum (plan 10.5).
    "id", "partija", "sacuvan", "kljuc",
}
ZABRANJENE_RECI = re.compile(r"\b(seme|sansa|tih|tezina|ishod|uspeh|neuspeh|bonus)\b")
ZABRANJENE_RECI_CIRILICA = re.compile(r"(шанс|тежин|\bсеме\b)", re.IGNORECASE)
# Plan 12.9: engleski prevod ne sme da imenuje sansu, tezinu ni seme (pravila za translate, P1).
ZABRANJENE_RECI_EN = re.compile(r"\b(chance|chances|odds|difficulty|seed)\b", re.IGNORECASE)
CIRILICA = re.compile(r"[Ѐ-ӿ]+")
JEZICI = ("sr", "en")


def klijent_jezika(jezik=None, **opcije):
    """Django klijent sa kolacicem jezika (ime iz settings, plan 12.2); None je bez kolacica."""
    klijent = Client(**opcije)
    if jezik is not None:
        klijent.cookies[settings.LANGUAGE_COOKIE_NAME] = jezik
    return klijent
JSON_SCRIPT = re.compile(r'<script id="stanje-igre" type="application/json">(.*?)</script>', re.S)
RANG_SCRIPT = re.compile(r'<script id="rang-lista" type="application/json">(.*?)</script>', re.S)
UPIS_SESIJE = re.compile(r'^(INSERT INTO|UPDATE) "django_session"')
CITANJE_SESIJE = re.compile(r'^SELECT .* FROM "django_session"')
UPIS_REZULTATA = re.compile(r'^INSERT INTO "igra_rezultat"')
KLJUCEVI_RANGA = {"lista", "sacuvano", "moj"}
# "red" je javna oznaka reda za prijavu imena (odluka 2026-11-12); nije id ni partija.
KLJUCEVI_REDA = {"ime", "poeni", "ocena", "datum", "stara_pravila", "red"}
# So i duzina oznake reda su prepisane iz ugovora, ne citaju se iz views.py.
SO_OZNAKE_REDA = "igra.prijava_imena.red"
OBLIK_OZNAKE_REDA = re.compile(r"[0-9a-f]{32}")
# Stavka sifarnika koju nijedan drugi tekst ne sadrzi, pa pretraga ne pogadja slucajno.
STAVKA_SIFARNIKA = "qzxstavkasifarnika"
PARTIJE = itertools.count(1)
SESIJE_PRIJAVA = itertools.count(1)

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
    "budzet_procenat",
    "kazna_budzet",
    "rok_prekoracen",
    "tihe_greske",
    "lekcije",
}
KLJUCEVI_MERE = {"limit", "potroseno", "preostalo"}
KLJUCEVI_POSLEDNJEG = {"krug", "zadatak", "cena", "minuti", "status"}
# Kljucevi zadataka redom krugova (ugovor 12.10).
ZADACI_KLJUCEVI = ["prevod", "sablon", "css", "crud", "model", "prava", "testovi", "revizija"]
TEKSTOVI_SCRIPT = re.compile(r'<script id="tekstovi" type="application/json">(.*?)</script>', re.S)


def tekstovi_iz_html(odgovor):
    pogodak = TEKSTOVI_SCRIPT.search(odgovor.content.decode("utf-8"))
    if pogodak is None:
        raise AssertionError("nema json_script bloka tekstovi")
    return json.loads(pogodak.group(1))


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


def rang_iz_html(odgovor):
    pogodak = RANG_SCRIPT.search(odgovor.content.decode("utf-8"))
    if pogodak is None:
        raise AssertionError("nema json_script bloka rang-lista")
    return json.loads(pogodak.group(1))


def upisi_red(ime="Пера", poeni=50, sacuvan=None, ocena=None, pravila=p.PRAVILA_TEKUCA, dan=None):
    """Red rang liste upisan kroz ORM; svaki dobija svoju partiju (polje je jedinstveno). dan: dnevni izazov."""
    podaci = {
        "ime": ime,
        "poeni": poeni,
        "ocena": ocena or motor.oceni(poeni),
        "pravila": pravila,
        "partija": f"test-partija-{next(PARTIJE)}",
        "dan": dan,
    }
    if sacuvan is not None:
        podaci["sacuvan"] = sacuvan
    return Rezultat.objects.create(**podaci)


def utc(*delovi):
    return datetime.datetime(*delovi, tzinfo=datetime.timezone.utc)


def oznaka_reda(red):
    """Javna oznaka reda liste po ugovoru: HMAC-SHA256 partije sa solju, prve 32 heksadecimalne cifre."""
    return salted_hmac(SO_OZNAKE_REDA, red.partija, algorithm="sha256").hexdigest()[:32]


def upisi_prijavu(red, kada=None):
    """Prijava imena upisana kroz ORM (priprema testa); svaka dobija svoj trag sesije, pa su sve razlicite."""
    polja = {"rezultat": red, "sesija": f"test-sesija-{next(SESIJE_PRIJAVA)}"}
    if kada is not None:
        polja["kada"] = kada
    return PrijavaImena.objects.create(**polja)


# Deljenje rezultata (plan 11.9). Ocekivane vrednosti su prepisane iz plana, ne citaju se iz koda.
DELJENO_SCRIPT = re.compile(r'<script id="deljeni-rezultat" type="application/json">(.*?)</script>', re.S)
KLJUCEVI_DELJENOG = {"zavrsni", "ime", "datum"}
KLJUCEVI_PODELI = {"url", "istice"}
KLJUCEVI_TIHE = {"krug", "zadatak", "dodatak_cena", "dodatak_minuti"}
KLJUCEVI_LEKCIJE = {"oznaka", "odeljak"}
OBLIK_TOKENA = re.compile(r"[A-Za-z0-9_-]{22}")
URL_DELJENJA = re.compile(r"http://testserver/r/([^/]+)/")
UPIS_DELJENOG = re.compile(r'^INSERT INTO "igra_deljenirezultat"')
TRIDESET_DANA = datetime.timedelta(days=30)
BEOGRAD = ZoneInfo("Europe/Belgrade")
NEDOSTUPNO = "Овај резултат више није доступан."
DELJENE_PARTIJE = itertools.count(1)


def strategija_najduza(krug):
    """Pali svih pet lekcija; uz tri tihe greske zavrsni ekran ima najvise stavki."""
    return izbori("opus" if krug == 1 else "haiku", "max", "sve", "pedeset")


def konteksti_odgovora(odgovor):
    """Konteksti svih sablona odgovora: jedan Context, ContextList (sablon sa include) ili nijedan."""
    kontekst = odgovor.context
    if kontekst is None:
        return []
    if isinstance(kontekst, list):  # django.test.utils.ContextList
        return list(kontekst)
    return [kontekst]


def deljeno_iz_html(odgovor):
    pogodak = DELJENO_SCRIPT.search(odgovor.content.decode("utf-8"))
    if pogodak is None:
        raise AssertionError("nema json_script bloka deljeni-rezultat")
    return json.loads(pogodak.group(1))


def token_iz_url(url):
    pogodak = URL_DELJENJA.fullmatch(url)
    if pogodak is None:
        raise AssertionError(f"url nije link za deljenje: {url!r}")
    return pogodak.group(1)


def upisi_deljeno(stanje=None, nastao=None, istice=None, **dodatno):
    """Red deljenog rezultata upisan kroz ORM. Bez stanja dobija svoju partiju (polje je jedinstveno)."""
    if stanje is None:
        stanje = odigraj_celu(f"seme-upisi-deljeno-{next(DELJENE_PARTIJE)}", sve_opus)
    nastao = nastao or timezone.now()
    return DeljeniRezultat.objects.create(
        token=secrets.token_urlsafe(16),
        partija=motor.oznaka_partije(stanje),
        zavrsni=motor.za_deljenje(stanje),
        nastao=nastao,
        istice=istice or nastao + TRIDESET_DANA,
        **dodatno,
    )


def istekao_red(stanje=None, dana_posle=1):
    sada = timezone.now()
    return upisi_deljeno(
        stanje, nastao=sada - TRIDESET_DANA - datetime.timedelta(days=dana_posle),
        istice=sada - datetime.timedelta(days=dana_posle),
    )


class PomocPrikaza:
    """Pomocne metode za TestCase i TransactionTestCase."""

    def postavi_igru(self, seme, klijent=None, stanje=None):
        klijent = klijent or self.client
        sesija = klijent.session
        sesija["igra"] = stanje if stanje is not None else motor.nova_igra(seme)
        sesija.save()

    def postavi_zavrsenu(self, seme, klijent=None, strategija=sve_opus):
        stanje = odigraj_celu(seme, strategija)
        self.postavi_igru(seme, klijent, stanje)
        return stanje

    def sacuvaj(self, ime, klijent=None):
        klijent = klijent or self.client
        telo = json.dumps({"ime": ime})
        return klijent.post(reverse("sacuvaj"), data=telo, content_type=JSON_TIP)

    def sacuvaj_sirovo(self, telo, klijent=None, tip=JSON_TIP):
        klijent = klijent or self.client
        return klijent.post(reverse("sacuvaj"), data=telo, content_type=tip)

    def podeli(self, klijent=None, **dodatno):
        return (klijent or self.client).post(reverse("podeli"), **dodatno)

    def podeli_json(self, klijent=None):
        odgovor = self.podeli(klijent)
        self.assertEqual(odgovor.status_code, 200, odgovor.content)
        return json.loads(odgovor.content)

    def deljena(self, token, klijent=None):
        return (klijent or self.client).get(reverse("deljeno", args=[token]))

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


class OsnovaPrikaza(PomocPrikaza, TestCase):
    pass


class SkrivenoTests(OsnovaPrikaza):
    def proveri_bez_skrivenog(self, odgovor, seme, zavrsena, html=False):
        # Seme, oznaka partije (sha256 semena) i stavka sifarnika ne smeju ni u telo ni u zaglavlja.
        tajne = (seme, motor.oznaka_partije({"seme": seme}), STAVKA_SIFARNIKA)
        for tajna in tajne:
            self.assertNotIn(tajna.encode("utf-8"), odgovor.content)
            for zaglavlje, vrednost in odgovor.items():
                self.assertNotIn(tajna, str(vrednost), zaglavlje)
        if html:
            # json_script pise ne-ASCII kao \uXXXX, pa se mapa tekstova proverava i procitana.
            tekstovi = json.dumps(tekstovi_iz_html(odgovor), ensure_ascii=False)
            for tekst in (odgovor.content.decode("utf-8"), tekstovi):
                self.assertEqual(ZABRANJENE_RECI.findall(tekst), [])
                self.assertEqual(ZABRANJENE_RECI_CIRILICA.findall(tekst), [])
                self.assertEqual(ZABRANJENE_RECI_EN.findall(tekst), [])
            podaci = {"stanje": stanje_iz_html(odgovor), "rang": rang_iz_html(odgovor)}
        else:
            podaci = json.loads(odgovor.content)
        self.assertEqual(skriveni_kljucevi(podaci, zavrsena), set())

    def proveri_deljenu(self, odgovor, seme, token):
        """Deljena strana (200 ili 404): bez semena, partije, sifarnika i tokena u telu i zaglavljima."""
        tajne = (seme, motor.oznaka_partije({"seme": seme}), STAVKA_SIFARNIKA, token)
        for tajna in tajne:
            self.assertNotIn(tajna.encode("utf-8"), odgovor.content)
            for zaglavlje, vrednost in odgovor.items():
                self.assertNotIn(tajna, str(vrednost), zaglavlje)
        tekst = odgovor.content.decode("utf-8")
        if odgovor.status_code == 200:
            tekst += json.dumps(tekstovi_iz_html(odgovor), ensure_ascii=False)
        self.assertEqual(ZABRANJENE_RECI.findall(tekst), [])
        self.assertEqual(ZABRANJENE_RECI_CIRILICA.findall(tekst), [])
        self.assertEqual(ZABRANJENE_RECI_EN.findall(tekst), [])
        if odgovor.status_code == 200:
            podaci = deljeno_iz_html(odgovor)
            self.assertEqual(set(podaci), KLJUCEVI_DELJENOG)
            self.assertEqual(skriveni_kljucevi(podaci, True), set())

    def proveri_token_samo_u_url(self, odgovor, token):
        podaci = json.loads(odgovor.content)
        self.assertEqual(set(podaci), KLJUCEVI_PODELI)
        self.assertEqual(token_iz_url(podaci["url"]), token)
        self.assertEqual(odgovor.content.count(token.encode()), 1)
        for zaglavlje, vrednost in odgovor.items():
            self.assertNotIn(token, str(vrednost), zaglavlje)

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

    def test_detektor_nalazi_oznaku_partije_i_stavku(self):
        # Kontrola: provera trazi tacne vrednosti, i one postoje na serveru.
        NepodobnoIme.objects.create(kljuc=STAVKA_SIFARNIKA)
        seme = "tajno-seme-detektor-rang"
        self.postavi_zavrsenu(seme)
        self.assertEqual(self.sacuvaj("Играч").status_code, 200)
        red = Rezultat.objects.get()
        self.assertEqual(red.partija, motor.oznaka_partije({"seme": seme}))
        lazni = mock.Mock(content=json.dumps({"x": red.partija}).encode(), items=lambda: [])
        with self.assertRaises(AssertionError):
            self.proveri_bez_skrivenog(lazni, seme, True)
        lazni.content = json.dumps({"x": STAVKA_SIFARNIKA}).encode()
        with self.assertRaises(AssertionError):
            self.proveri_bez_skrivenog(lazni, seme, True)
        self.assertEqual(skriveni_kljucevi({"lista": [{"id": 1, "partija": "p"}]}, True), {"id", "partija"})

    def test_nijedan_odgovor_ne_sadrzi_skriveno(self):
        NepodobnoIme.objects.create(kljuc=STAVKA_SIFARNIKA)
        upisi_red("Ранији играч", 70)
        videnih_tihih = 0
        sacuvanih = 0
        # Plan 12.9: isto i pod engleskim (kolacic jezika), uz ZABRANJENE_RECI_EN.
        strategije = list(enumerate((sve_haiku_low_malo, po_tezini, sve_opus)))
        for jezik, (rb, strategija) in itertools.product(JEZICI, strategije):
            seme = f"tajno-seme-{jezik}-{rb}-x9q"
            klijent = klijent_jezika(jezik)
            self.postavi_igru(seme, klijent)
            for krug in KRUGOVI:
                with self.subTest(seme=seme, krug=krug):
                    strana = klijent.get(reverse("pocetna"))
                    self.assertEqual(strana["Content-Language"], jezik)
                    self.proveri_bez_skrivenog(strana, seme, False, html=True)
                    pogresan = self.potez(krug + 1, strategija(krug), klijent)
                    self.assertEqual(pogresan.status_code, 409)
                    self.proveri_bez_skrivenog(pogresan, seme, False)
                    los = self.potez(krug, {**OPUS_HIGH, "model": "gpt"}, klijent)
                    self.assertEqual(los.status_code, 400)
                    self.proveri_bez_skrivenog(los, seme, False)
                    rano = self.sacuvaj("Играч", klijent)
                    self.assertEqual(json.loads(rano.content)["greska"], "igra_nije_zavrsena")
                    self.proveri_bez_skrivenog(rano, seme, False)
                    rano_deljenje = self.podeli(klijent)
                    self.assertEqual(rano_deljenje.status_code, 409)
                    self.assertEqual(json.loads(rano_deljenje.content), {"greska": "igra_nije_zavrsena"})
                    self.proveri_bez_skrivenog(rano_deljenje, seme, False)
                    prihvacen = self.potez(krug, strategija(krug), klijent)
                    self.assertEqual(prihvacen.status_code, 200)
                    self.proveri_bez_skrivenog(prihvacen, seme, krug == 8)
            konacno = klijent.get(reverse("pocetna"))
            self.proveri_bez_skrivenog(konacno, seme, True, html=True)
            odbijen = self.potez(8, OPUS_HIGH, klijent)
            self.assertEqual(odbijen.status_code, 409)
            self.proveri_bez_skrivenog(odbijen, seme, True)

            # Deljenje pre cuvanja: 200 dva puta (isti link), deljena strana bez imena.
            with self.subTest(seme=seme, deljenje="podeli"):
                deljenje = self.podeli(klijent)
                self.assertEqual(deljenje.status_code, 200)
                self.proveri_bez_skrivenog(deljenje, seme, True)
                token = token_iz_url(json.loads(deljenje.content)["url"])
                self.proveri_token_samo_u_url(deljenje, token)
                ponovo = self.podeli(klijent)
                self.assertEqual(ponovo.content, deljenje.content)
                self.proveri_bez_skrivenog(ponovo, seme, True)
                strana = self.deljena(token, klijent_jezika(jezik))
                self.assertEqual(strana.status_code, 200)
                self.assertEqual(strana["Content-Language"], jezik)
                self.assertIsNone(deljeno_iz_html(strana)["ime"])
                self.proveri_deljenu(strana, seme, token)
                igra_posle = klijent.get(reverse("pocetna"))
                self.assertNotIn(token.encode(), igra_posle.content)
                self.proveri_bez_skrivenog(igra_posle, seme, True, html=True)

            # Cuvanje: 400 (oblik, ime, sifarnik), 200, 409, pa GET posle cuvanja.
            for ime, status, greska in (
                (" Играч", 400, "neispravno_ime"),
                (STAVKA_SIFARNIKA.upper(), 400, "nepodobno_ime"),
                (f"Играч {rb}", 200, None),
                (f"Играч {rb}", 409, "vec_sacuvano"),
            ):
                with self.subTest(seme=seme, cuvanje=status, greska=greska):
                    odgovor = self.sacuvaj(ime, klijent)
                    self.assertEqual(odgovor.status_code, status)
                    self.assertEqual(json.loads(odgovor.content).get("greska"), greska)
                    self.proveri_bez_skrivenog(odgovor, seme, True)
            sirov = self.sacuvaj_sirovo(b"{", klijent)
            self.assertEqual(sirov.status_code, 400)
            self.proveri_bez_skrivenog(sirov, seme, True)
            posle = klijent.get(reverse("pocetna"))
            self.assertTrue(rang_iz_html(posle)["sacuvano"])
            self.proveri_bez_skrivenog(posle, seme, True, html=True)
            self.assertNotIn(token.encode(), posle.content)
            sacuvanih += 1

            # Deljena strana posle cuvanja nosi ime, i dalje bez skrivenog; 404 isto.
            with self.subTest(seme=seme, deljenje="posle cuvanja"):
                strana = self.deljena(token, klijent_jezika(jezik))
                self.assertEqual(deljeno_iz_html(strana)["ime"], f"Играч {rb}")
                self.proveri_deljenu(strana, seme, token)
                posle_deljenja = self.podeli(klijent)
                self.assertEqual(posle_deljenja.content, deljenje.content)
                nepostojeci = self.deljena(secrets.token_urlsafe(16), klijent_jezika(jezik))
                self.assertEqual(nepostojeci.status_code, 404)
                self.proveri_deljenu(nepostojeci, seme, token)

            kolacici = "".join(k.value for k in klijent.cookies.values())
            self.assertNotIn(seme, kolacici)
            self.assertNotIn(token, kolacici)
            videnih_tihih += ishodi(self.stanje(klijent)).count(motor.TIHI_NEUSPEH)
        self.assertGreater(videnih_tihih, 0, "provera mora da prodje kroz bar jedan tih neuspeh")
        self.assertEqual(sacuvanih, 3 * len(JEZICI))
        self.assertEqual(Rezultat.objects.count(), 1 + 3 * len(JEZICI))

    def test_rang_tacan_skup_kljuceva(self):
        upisi_red("Други", 90)
        self.postavi_zavrsenu("seme-skup-kljuceva")
        provere = {
            "GET pre cuvanja": rang_iz_html(self.client.get(reverse("pocetna"))),
            "200": json.loads(self.sacuvaj("Играч").content),
            "409": json.loads(self.sacuvaj("Играч").content),
            "GET posle cuvanja": rang_iz_html(self.client.get(reverse("pocetna"))),
            "409 nema igre": json.loads(self.sacuvaj("Играч", Client()).content),
        }
        self.assertEqual(set(provere["200"]), {"rang"})
        self.assertEqual(set(provere["409"]), {"greska", "rang"})
        self.assertEqual(set(provere["409 nema igre"]), {"greska", "rang"})
        for ime, podaci in provere.items():
            rang = podaci.get("rang", podaci)
            with self.subTest(ime=ime):
                self.assertEqual(set(rang), KLJUCEVI_RANGA)
                self.assertGreaterEqual(len(rang["lista"]), 1)
                for red in rang["lista"]:
                    self.assertEqual(set(red), KLJUCEVI_REDA)
                    self.assertIsInstance(red["poeni"], int)
                    self.assertIsInstance(red["ime"], str)

    def test_partija_ne_izlazi(self):
        seme = "seme-partija-ne-izlazi"
        self.postavi_zavrsenu(seme)
        odgovori = [self.sacuvaj("Играч"), self.sacuvaj("Играч"), self.client.get(reverse("pocetna"))]
        red = Rezultat.objects.get()
        self.assertEqual(red.partija, motor.oznaka_partije({"seme": seme}))
        self.assertEqual(self.stanje()["sacuvan"], red.id)
        for odgovor in odgovori:
            with self.subTest(status=odgovor.status_code):
                self.assertNotIn(red.partija.encode(), odgovor.content)
                self.assertNotIn(b'"partija"', odgovor.content)
                self.assertNotIn(b'"id"', odgovor.content)
                self.assertNotIn(b'"sacuvan"', odgovor.content)

    def test_tih_neuspeh_bajt_identican_uspehu(self):
        uspesi = [motor.USPEH] * 4
        uspeh = nadji_seme(sve_opus, lambda i: i[:5] == uspesi + [motor.USPEH])
        tih = nadji_seme(sve_opus, lambda i: i[:5] == uspesi + [motor.TIHI_NEUSPEH])
        self.assertNotEqual(uspeh, tih)
        csrf = re.compile(rb'name="csrfmiddlewaretoken" value="[^"]+"')
        for jezik in JEZICI:
            prvi, drugi = klijent_jezika(jezik), klijent_jezika(jezik)
            self.postavi_igru(uspeh, prvi)
            self.postavi_igru(tih, drugi)
            for krug in range(1, 6):
                with self.subTest(jezik=jezik, krug=krug):
                    a = self.potez(krug, OPUS_HIGH, prvi)
                    b = self.potez(krug, OPUS_HIGH, drugi)
                    self.assertEqual(a.status_code, 200)
                    self.assertEqual(b.status_code, a.status_code)
                    self.assertEqual(b.content, a.content)
            self.assertEqual(self.stanje(prvi)["istorija"][4]["ishod"], motor.USPEH)
            self.assertEqual(self.stanje(drugi)["istorija"][4]["ishod"], motor.TIHI_NEUSPEH)
            strana_a, strana_b = prvi.get(reverse("pocetna")), drugi.get(reverse("pocetna"))
            with self.subTest(jezik=jezik, strana="pocetna"):
                self.assertEqual(strana_a["Content-Language"], jezik)
                self.assertEqual(stanje_iz_html(strana_a), stanje_iz_html(strana_b))
                # Cela strana je ista bajt po bajt; razlikuje se samo CSRF token sesije.
                self.assertEqual(len(csrf.findall(strana_a.content)), 2)
                self.assertEqual(csrf.sub(b"", strana_b.content), csrf.sub(b"", strana_a.content))

    def test_status_tihog_neuspeha_je_gotovo(self):
        seme = nadji_seme(sve_opus, lambda i: i[4] == motor.TIHI_NEUSPEH)
        for jezik, tekst in (("sr", "готово"), ("en", "done")):
            with self.subTest(jezik=jezik):
                klijent = klijent_jezika(jezik)
                self.postavi_igru(seme, klijent)
                podaci = json.loads(self.odigraj_do(5, klijent=klijent).content)
                self.assertEqual(podaci["poslednji"]["status"], "gotovo")
                self.assertEqual(podaci["poslednji"]["krug"], 5)
                # Tekst statusa na ekranu dolazi iz iste mape za oba ishoda.
                self.assertEqual(tekstovi_iz_html(klijent.get(reverse("pocetna")))["status"]["gotovo"], tekst)

    def test_status_dorade(self):
        seme = nadji_seme(lambda _k: izbori("haiku"), lambda i: i[0] == motor.DORADA)
        for jezik, tekst in (("sr", "враћено на дораду"), ("en", "sent back for rework")):
            with self.subTest(jezik=jezik):
                klijent = klijent_jezika(jezik)
                self.postavi_igru(seme, klijent)
                podaci = json.loads(self.potez(1, izbori("haiku"), klijent).content)
                self.assertEqual(podaci["poslednji"]["status"], "dorada")
                self.assertEqual(podaci["poslednji"]["cena"], 0.036)
                self.assertEqual(podaci["poslednji"]["minuti"], 5.0)
                self.assertEqual(tekstovi_iz_html(klijent.get(reverse("pocetna")))["status"]["dorada"], tekst)

    def test_tacan_skup_kljuceva_javnog_prikaza(self):
        seme = nadji_seme(
            sve_opus, lambda i: i.count(motor.TIHI_NEUSPEH) >= 1
        )
        self.postavi_igru(seme)
        pocetak = stanje_iz_html(self.client.get(reverse("pocetna")))
        self.assertEqual(set(pocetak), KLJUCEVI_PRIKAZA)
        self.assertIsNone(pocetak["poslednji"])
        self.assertIsNone(pocetak["zavrsni"])
        self.assertEqual(pocetak["zadatak"], "prevod")

        for krug in range(1, 8):
            podaci = json.loads(self.potez(krug).content)
            with self.subTest(krug=krug):
                self.assertEqual(set(podaci), KLJUCEVI_PRIKAZA)
                self.assertEqual(podaci["faza"], "igra")
                self.assertEqual(podaci["zadatak"], ZADACI_KLJUCEVI[krug])
                self.assertEqual(podaci["poslednji"]["zadatak"], ZADACI_KLJUCEVI[krug - 1])
                self.assertIn(podaci["poslednji"]["status"], {"gotovo", "dorada"})
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
        self.assertEqual(set(kraj["zavrsni"]["lekcije"][0]), {"oznaka", "odeljak"})
        self.assertIn(kraj["zavrsni"]["tihe_greske"][0]["zadatak"], {"model", "prava", "revizija"})
        self.assertIn(kraj["zavrsni"]["ocena"], {"odlican", "solidan", "skup", "pozar"})

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
        self.assertEqual(pocetak["zadatak"], "prevod")
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
        odgovor = self.client.get(reverse("pocetna"))
        kljucevi = [stanje_iz_html(odgovor)["zadatak"]]
        for krug in range(1, 8):
            kljucevi.append(json.loads(self.potez(krug).content)["zadatak"])
        self.assertEqual(kljucevi, ZADACI_KLJUCEVI)
        # Naziv na ekranu je tekst skripte po kljucu, na jeziku strane (sr bez Accept-Language).
        self.assertEqual(
            [tekstovi_iz_html(odgovor)["zadaci"][k] for k in kljucevi], [ZADACI_SR[k] for k in kljucevi]
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
        self.assertEqual(z["ocena"], "odlican")
        self.assertEqual(z["ukupna_cena"], 19.44)
        self.assertEqual(z["ukupni_minuti"], 135.0)
        self.assertFalse(z["budzet_prekoracen"])
        self.assertFalse(z["rok_prekoracen"])
        self.assertEqual(z["tihe_greske"], [])
        self.assertEqual(z["lekcije"], [{"oznaka": "opus_lako", "odeljak": "3.2"}])
        # Napomena izlazi iz JSON-a odgovora (plan 12.3); skripta je cita iz mape tekstova strane.
        self.assertNotIn("napomena", z)
        tekstovi = tekstovi_iz_html(self.client.get(reverse("pocetna")))
        self.assertEqual(tekstovi["napomena"], NAPOMENA_SR)
        self.assertEqual(tekstovi["lekcije"]["opus_lako"], LEKCIJE_SR["opus_lako"])
        self.assertEqual(tekstovi["ocene"]["odlican"], "одличан оркестратор")

    def test_tih_neuspeh_prekoracuje_oba_limita(self):
        seme = nadji_seme(
            sve_opus, lambda i: i == [motor.USPEH] * 4 + [motor.TIHI_NEUSPEH] + [motor.USPEH] * 3
        )
        self.postavi_igru(seme)
        kraj = json.loads(self.odigraj_do(8).content)
        z = kraj["zavrsni"]
        self.assertEqual(z["poeni"], 5)
        self.assertEqual(z["ocena"], "pozar")
        self.assertEqual(z["ukupna_cena"], 32.4)
        self.assertEqual(z["ukupni_minuti"], 165.0)
        self.assertEqual(
            z["tihe_greske"],
            [
                {
                    "krug": 5,
                    "zadatak": "model",
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


class CuvanjeTests(OsnovaPrikaza):
    """POST /sacuvaj/: plan 10.3, uslov 9."""

    def red_sesije(self, klijent=None):
        return Session.objects.get(pk=(klijent or self.client).session.session_key).session_data

    def test_sacuvaj_200_poeni_i_ocena_iz_stanja(self):
        # Partija sa 5 poena: poeni i ocena nisu podrazumevane vrednosti.
        seme = nadji_seme(
            sve_opus, lambda i: i == [motor.USPEH] * 4 + [motor.TIHI_NEUSPEH] + [motor.USPEH] * 3
        )
        stanje = self.postavi_zavrsenu(seme)
        self.assertEqual((stanje["rezultat"]["poeni"], stanje["rezultat"]["ocena"]), (5, "pozar"))
        odgovor = self.sacuvaj("Пера")
        self.assertEqual(odgovor.status_code, 200)
        self.assertEqual(odgovor["Content-Type"], JSON_TIP)
        red = Rezultat.objects.get()
        self.assertEqual((red.ime, red.poeni, red.ocena), ("Пера", 5, "pozar"))
        datum = timezone.localtime(red.sacuvan).strftime("%d.%m.%Y")
        self.assertEqual(
            json.loads(odgovor.content),
            {
                "rang": {
                    "lista": [{"ime": "Пера", "poeni": 5, "ocena": "pozar", "datum": datum,
                               "stara_pravila": False, "red": oznaka_reda(red)}],
                    "sacuvano": True,
                    "moj": 0,
                }
            },
        )
        self.assertEqual(self.stanje()["sacuvan"], red.id)
        # Ostatak stanja je netaknut.
        self.assertEqual({k: v for k, v in self.stanje().items() if k != "sacuvan"}, stanje)

    def test_poeni_u_zahtevu_400(self):
        self.postavi_zavrsenu("seme-poeni-u-zahtevu")
        pre = self.stanje()
        for telo in (
            {"ime": "Пера", "poeni": 100},
            {"ime": "Пера", "ocena": "одличан оркестратор"},
            {"ime": "Пера", "poeni": 100, "ocena": "одличан оркестратор"},
            {"poeni": 100},
        ):
            with self.subTest(telo=telo):
                odgovor = self.sacuvaj_sirovo(json.dumps(telo))
                self.assertEqual(odgovor.status_code, 400)
                self.assertEqual(json.loads(odgovor.content), {"greska": "neispravan_zahtev"})
                self.assertEqual(Rezultat.objects.count(), 0)
                self.assertEqual(self.stanje(), pre)
        # Kontrola: isto ime bez dodatnih kljuceva prolazi.
        self.assertEqual(self.sacuvaj("Пера").status_code, 200)

    def test_sacuvaj_neispravan_zahtev_400(self):
        self.postavi_zavrsenu("seme-neispravan-zahtev")
        ispravno = json.dumps({"ime": "Пера"})
        slucajevi = {
            "nije json": b"nije json",
            "prazno telo": b"",
            "neispravan utf-8": b'\xff\xfe{"ime": "a"}',
            "niz": json.dumps(["Пера"]).encode(),
            "broj": b"3",
            "string": json.dumps("Пера").encode(),
            "null": b"null",
            "telo preko 2 KB": (ispravno + " " * 2100).encode(),
            "duboko ugnezdeno": b"[" * 1024 + b"]" * 1024,
            "prazan objekat": b"{}",
            "dodatni kljuc": json.dumps({"ime": "Пера", "x": 1}).encode(),
            "pogresan kljuc": json.dumps({"name": "Пера"}).encode(),
            "ime broj": json.dumps({"ime": 1}).encode(),
            "ime null": json.dumps({"ime": None}).encode(),
            "ime true": json.dumps({"ime": True}).encode(),
            "ime niz": json.dumps({"ime": ["Пера"]}).encode(),
            "ime objekat": json.dumps({"ime": {"a": "b"}}).encode(),
        }
        pre = self.stanje()
        for ime, telo in slucajevi.items():
            with self.subTest(ime=ime):
                odgovor = self.sacuvaj_sirovo(telo)
                self.assertEqual(odgovor.status_code, 400)
                self.assertEqual(json.loads(odgovor.content), {"greska": "neispravan_zahtev"})
                self.assertEqual(self.stanje(), pre)
        self.assertEqual(Rezultat.objects.count(), 0)
        # Kontrola: telo tacno 2 KB prolazi, pa granica nije niza.
        dopuna = ispravno + " " * (2048 - len(ispravno.encode()))
        self.assertEqual(self.sacuvaj_sirovo(dopuna.encode()).status_code, 200)

    def test_sacuvaj_prednost_400_nad_409(self):
        NepodobnoIme.objects.create(kljuc="zabranjeno")
        bez_igre = Client()
        u_toku = Client()
        self.postavi_igru("seme-prednost-u-toku", u_toku)
        sacuvano = Client()
        self.postavi_zavrsenu("seme-prednost-sacuvano", sacuvano)
        self.assertEqual(self.sacuvaj("Пера", sacuvano).status_code, 200)
        for opis, klijent in (("bez igre", bez_igre), ("u toku", u_toku), ("vec sacuvano", sacuvano)):
            with self.subTest(opis=opis):
                self.assertEqual(json.loads(self.sacuvaj(" x", klijent).content), {"greska": "neispravno_ime"})
                self.assertEqual(
                    json.loads(self.sacuvaj("Забрањено", klijent).content), {"greska": "nepodobno_ime"}
                )
                odgovor = self.sacuvaj_sirovo(b"{}", klijent)
                self.assertEqual(odgovor.status_code, 400)
                self.assertEqual(json.loads(odgovor.content), {"greska": "neispravan_zahtev"})
                # Kontrola: ispravno ime za isti klijent daje 409, pa je 400 imao prednost.
                self.assertEqual(self.sacuvaj("Пера", klijent).status_code, 409)
        self.assertEqual(Rezultat.objects.count(), 1)

    def test_ime_pravila(self):
        for rb, (opis, ime) in enumerate(PRIHVACENA_IMENA.items()):
            with self.subTest(prihvaceno=opis):
                klijent = Client()
                self.postavi_zavrsenu(f"seme-ime-prihvaceno-{rb}", klijent)
                odgovor = self.sacuvaj(ime, klijent)
                self.assertEqual(odgovor.status_code, 200, odgovor.content)
                nfc = unicodedata.normalize("NFC", ime)
                red = Rezultat.objects.get(id=self.stanje(klijent)["sacuvan"])
                self.assertEqual(red.ime, nfc)
                self.assertLessEqual(len(red.ime), p.IME_MAKS)
        self.assertEqual(Rezultat.objects.count(), len(PRIHVACENA_IMENA))
        self.assertEqual(
            Rezultat.objects.filter(ime="Đorđe Šćepanović").count(), 1, "NFD se cuva kao NFC"
        )

        self.postavi_zavrsenu("seme-ime-odbijeno")
        pre = self.stanje()
        for opis, ime in ODBIJENA_IMENA.items():
            with self.subTest(odbijeno=opis):
                odgovor = self.sacuvaj(ime)
                self.assertEqual(odgovor.status_code, 400)
                # Odgovor ne ponavlja ime.
                self.assertEqual(json.loads(odgovor.content), {"greska": "neispravno_ime"})
                self.assertEqual(self.stanje(), pre)
        self.assertEqual(Rezultat.objects.count(), len(PRIHVACENA_IMENA))

    def test_nevidljivi_400_svuda(self):
        # Svih 269 znakova iz plana 10.4 (tacka 7), sam / na kraju / usred imena, kroz HTTP.
        self.postavi_zavrsenu("seme-nevidljivi")
        pre = self.stanje()
        prosli = []
        tela = set()
        for znak in NEVIDLJIVI_ZNACI:
            for polozaj, ime in nevidljivi_polozaji(znak).items():
                odgovor = self.sacuvaj(ime)
                tela.add((odgovor.status_code, odgovor.content))
                if odgovor.status_code != 400:
                    prosli.append((f"U+{ord(znak):04X}", polozaj, odgovor.status_code))
        self.assertEqual(prosli, [])
        self.assertEqual(tela, {(400, b'{"greska": "neispravno_ime"}')})
        self.assertEqual(Rezultat.objects.count(), 0)
        self.assertEqual(self.stanje(), pre)
        # Kontrola: ista partija se cuva kad je ime ispravno.
        self.assertEqual(self.sacuvaj("Пера").status_code, 200)

    def test_surogat_kao_sirov_json(self):
        self.postavi_zavrsenu("seme-surogat")
        odgovor = self.sacuvaj_sirovo(b'{"ime": "\\ud800"}')
        self.assertEqual(odgovor.status_code, 400)
        self.assertEqual(json.loads(odgovor.content), {"greska": "neispravno_ime"})
        self.assertEqual(Rezultat.objects.count(), 0)

    def test_ista_imena_dozvoljena(self):
        for rb in range(2):
            klijent = Client()
            self.postavi_zavrsenu(f"seme-isto-ime-{rb}", klijent)
            self.assertEqual(self.sacuvaj("Пера Перић", klijent).status_code, 200)
        self.assertEqual(Rezultat.objects.filter(ime="Пера Перић").count(), 2)

    def test_full_clean_odbija_lose_ime(self):
        for opis, ime in {**ODBIJENA_IMENA, "21 znak": "Ш" * 21}.items():
            with self.subTest(opis=opis):
                red = Rezultat(ime=ime, poeni=50, ocena="skup", pravila=p.PRAVILA_TEKUCA, partija=f"fc-{opis}")
                with self.assertRaises(ValidationError) as greska:
                    red.full_clean()
                self.assertIn("ime", greska.exception.message_dict)
        # Kontrola: ispravan red prolazi full_clean.
        Rezultat(ime="Пера", poeni=50, ocena="skup", pravila=p.PRAVILA_TEKUCA, partija="fc-ok").full_clean()

    def test_ocena_samo_kljuc(self):
        # Plan 12.4: CHECK igra_ocena_kljuc; tekst ocene ne ulazi ni kroz full_clean ni kroz ORM.
        for rb, ocena in enumerate(("скуп учитељ", "costly lesson", "", "Skup")):
            with self.subTest(ocena=ocena):
                red = Rezultat(ime="Пера", poeni=50, ocena=ocena, pravila=p.PRAVILA_TEKUCA, partija=f"ocena-{rb}")
                with self.assertRaises(ValidationError):
                    red.full_clean()
                with self.assertRaises(IntegrityError), transaction.atomic():
                    red.save()
        self.assertEqual(Rezultat.objects.count(), 0)
        # Kontrola: svaki kljuc prolazi.
        for rb, ocena in enumerate(("odlican", "solidan", "skup", "pozar")):
            Rezultat(ime="Пера", poeni=50, ocena=ocena, pravila=p.PRAVILA_TEKUCA, partija=f"kljuc-{rb}").full_clean()
            Rezultat.objects.create(
                ime="Пера", poeni=50, ocena=ocena, pravila=p.PRAVILA_TEKUCA, partija=f"kljuc-{rb}"
            )
        self.assertEqual(Rezultat.objects.count(), 4)

    def test_maxlength_jednak_ime_maks(self):
        html = self.client.get(reverse("pocetna")).content.decode("utf-8")
        polje = re.search(r'<input[^>]*id="rang-ime"[^>]*>', html)
        self.assertIsNotNone(polje)
        self.assertRegex(polje.group(0), rf'maxlength="{p.IME_MAKS}"')
        self.assertEqual(Rezultat._meta.get_field("ime").max_length, p.IME_MAKS)
        self.assertEqual(p.IME_MAKS, 20)

    def test_drugo_cuvanje_409_jedan_red(self):
        stanje = self.postavi_zavrsenu("seme-drugo-cuvanje")
        self.assertEqual(self.sacuvaj("Пера").status_code, 200)
        posle_prvog = self.stanje()
        drugi = self.sacuvaj("Мика")
        self.assertEqual(drugi.status_code, 409)
        podaci = json.loads(drugi.content)
        self.assertEqual(podaci["greska"], "vec_sacuvano")
        self.assertTrue(podaci["rang"]["sacuvano"])
        self.assertEqual(podaci["rang"]["moj"], 0)
        self.assertEqual([r["ime"] for r in podaci["rang"]["lista"]], ["Пера"])
        self.assertEqual(Rezultat.objects.count(), 1)
        self.assertEqual(self.stanje(), posle_prvog)
        self.assertEqual(Rezultat.objects.get().poeni, stanje["rezultat"]["poeni"])

    def test_nova_posle_cuvanja_novi_upis(self):
        self.postavi_zavrsenu("seme-nova-posle")
        self.assertEqual(self.sacuvaj("Пера").status_code, 200)
        self.assertEqual(self.client.post(reverse("nova")).status_code, 302)
        self.assertNotIn("sacuvan", self.stanje())
        self.assertEqual(self.sacuvaj("Пера").status_code, 409)
        self.odigraj_do(8)
        odgovor = self.sacuvaj("Пера")
        self.assertEqual(odgovor.status_code, 200)
        self.assertEqual(Rezultat.objects.count(), 2)
        self.assertEqual(len(set(Rezultat.objects.values_list("partija", flat=True))), 2)

    def test_igra_nije_zavrsena_409(self):
        self.postavi_igru("seme-nije-zavrsena")
        odigrano = 0
        for krugova in (0, 3, 7):
            with self.subTest(krugova=krugova):
                for krug in range(odigrano + 1, krugova + 1):
                    self.assertEqual(self.potez(krug).status_code, 200)
                odigrano = krugova
                pre = self.stanje()
                red_pre = self.red_sesije()
                odgovor = self.sacuvaj("Пера")
                self.assertEqual(odgovor.status_code, 409)
                podaci = json.loads(odgovor.content)
                self.assertEqual(podaci["greska"], "igra_nije_zavrsena")
                self.assertEqual(podaci["rang"], {"lista": [], "sacuvano": False, "moj": None})
                self.assertEqual(self.stanje(), pre)
                self.assertEqual(self.red_sesije(), red_pre)
        self.assertEqual(self.stanje()["krug"], 8)
        self.assertEqual(Rezultat.objects.count(), 0)

    def test_sacuvaj_nema_igre_409(self):
        upisi_red("Други", 80)
        klijent = Client()
        odgovor = self.sacuvaj("Пера", klijent)
        self.assertEqual(odgovor.status_code, 409)
        podaci = json.loads(odgovor.content)
        self.assertEqual(podaci["greska"], "nema_igre")
        self.assertEqual(podaci["rang"]["sacuvano"], False)
        self.assertIsNone(podaci["rang"]["moj"])
        self.assertEqual([r["ime"] for r in podaci["rang"]["lista"]], ["Други"])
        self.assertEqual(Rezultat.objects.count(), 1)

    def test_izgubljena_oznaka_409_jedan_red(self):
        # Ono sto bi video drugi istovremeni zahtev da je sesiju procitao pre upisa prvog.
        stanje = self.postavi_zavrsenu("seme-izgubljena-oznaka")
        postojeci = Rezultat.objects.create(
            ime="Први", poeni=10, ocena="pozar", pravila=p.PRAVILA_TEKUCA, partija=motor.oznaka_partije(stanje)
        )
        odgovor = self.sacuvaj("Други")
        self.assertEqual(odgovor.status_code, 409)
        self.assertEqual(json.loads(odgovor.content)["greska"], "vec_sacuvano")
        self.assertEqual(list(Rezultat.objects.values_list("id", "ime")), [(postojeci.id, "Први")])
        self.assertEqual(self.stanje(), stanje)

    def test_odbijeno_cuvanje_bez_upisa(self):
        NepodobnoIme.objects.create(kljuc="zabranjeno")
        sacuvano = Client()
        self.postavi_zavrsenu("seme-odbijeno-sacuvano", sacuvano)
        self.assertEqual(self.sacuvaj("Пера", sacuvano).status_code, 200)
        u_toku = Client()
        self.postavi_igru("seme-odbijeno-u-toku", u_toku)
        zavrseno = Client()
        self.postavi_zavrsenu("seme-odbijeno-zavrseno", zavrseno)
        slucajevi = [
            ("neispravno ime", 400, lambda: self.sacuvaj(" x", zavrseno)),
            ("nepodobno ime", 400, lambda: self.sacuvaj("ZA BRANJENO", zavrseno)),
            ("neispravan zahtev", 400, lambda: self.sacuvaj_sirovo(b"[]", zavrseno)),
            ("igra nije zavrsena", 409, lambda: self.sacuvaj("Пера", u_toku)),
            ("vec sacuvano", 409, lambda: self.sacuvaj("Пера", sacuvano)),
            ("nema igre", 409, lambda: self.sacuvaj("Пера", Client())),
        ]
        for ime, status, radnja in slucajevi:
            with self.subTest(ime=ime):
                with CaptureQueriesContext(connection) as uhvaceno:
                    odgovor = radnja()
                upiti = [u["sql"] for u in uhvaceno]
                self.assertEqual(odgovor.status_code, status)
                self.assertEqual([u for u in upiti if UPIS_SESIJE.match(u)], [])
                self.assertEqual([u for u in upiti if UPIS_REZULTATA.match(u)], [])
        self.assertEqual(Rezultat.objects.count(), 1)

    def test_sacuvaj_200_tacno_jedan_upis_sesije(self):
        self.postavi_zavrsenu("seme-jedan-upis")
        with CaptureQueriesContext(connection) as uhvaceno:
            odgovor = self.sacuvaj("Пера")
        upiti = [u["sql"] for u in uhvaceno]
        self.assertEqual(odgovor.status_code, 200)
        self.assertEqual(len([u for u in upiti if UPIS_SESIJE.match(u)]), 1, upiti)
        self.assertEqual(len([u for u in upiti if UPIS_REZULTATA.match(u)]), 1, upiti)

    def test_sacuvaj_cita_i_upisuje_u_istoj_transakciji(self):
        self.postavi_zavrsenu("seme-transakcija-cuvanja")
        with CaptureQueriesContext(connection) as uhvaceno:
            odgovor = self.sacuvaj("Пера")
        upiti = [u["sql"] for u in uhvaceno]
        self.assertEqual(odgovor.status_code, 200)
        # U TestCase-u je spoljni atomic prikaza SAVEPOINT; sve izmedju njega i RELEASE je pod bravom.
        otvaranje = next(i for i, upit in enumerate(upiti) if upit.startswith("SAVEPOINT"))
        zatvaranje = upiti.index("RELEASE " + upiti[otvaranje])
        citanja = [i for i, upit in enumerate(upiti) if CITANJE_SESIJE.match(upit)]
        upisi_reda = [i for i, upit in enumerate(upiti) if UPIS_REZULTATA.match(upit)]
        upisi_sesije = [i for i, upit in enumerate(upiti) if UPIS_SESIJE.match(upit)]
        self.assertEqual(len(citanja), 1, upiti)
        self.assertEqual(len(upisi_reda), 1, upiti)
        self.assertEqual(len(upisi_sesije), 1, upiti)
        self.assertLess(otvaranje, citanja[0], upiti)
        self.assertLess(citanja[0], upisi_reda[0], upiti)
        self.assertLess(upisi_reda[0], upisi_sesije[0], upiti)
        self.assertLess(upisi_sesije[0], zatvaranje, upiti)

    def test_sacuvaj_bez_csrf_403(self):
        klijent = Client(enforce_csrf_checks=True)
        self.postavi_zavrsenu("seme-csrf-cuvanje", klijent)
        klijent.get(reverse("pocetna"))
        token = klijent.cookies["csrftoken"].value
        pre = self.stanje(klijent)
        telo = json.dumps({"ime": "Пера"})
        odgovor = klijent.post(reverse("sacuvaj"), data=telo, content_type=JSON_TIP)
        self.assertEqual(odgovor.status_code, 403)
        self.assertEqual(Rezultat.objects.count(), 0)
        self.assertEqual(self.stanje(klijent), pre)
        # Kontrola: isti klijent sa tokenom prolazi, pa 403 dolazi od CSRF-a.
        odgovor = klijent.post(
            reverse("sacuvaj"), data=telo, content_type=JSON_TIP, headers={"X-CSRFToken": token}
        )
        self.assertEqual(odgovor.status_code, 200)

    def test_sacuvaj_get_405(self):
        self.postavi_zavrsenu("seme-405")
        for metoda in (self.client.get, self.client.put, self.client.delete):
            with self.subTest(metoda=metoda.__name__):
                odgovor = metoda(reverse("sacuvaj"))
                self.assertEqual(odgovor.status_code, 405)
                self.assertEqual(odgovor.content, b"")
        self.assertEqual(Rezultat.objects.count(), 0)


class SifarnikTests(OsnovaPrikaza):
    def setUp(self):
        NepodobnoIme.objects.create(kljuc="zabranjeno")

    def test_nepodobno_ime_400(self):
        self.postavi_zavrsenu("seme-nepodobno")
        pre = self.stanje()
        red_pre = Session.objects.get(pk=self.client.session.session_key).session_data
        for ime in ("Забрањено", "ZABRANJENO", "za branjeno", "Za-bra.nje.no", "ЗАБРАЊЕНО!"):
            with self.subTest(ime=ime):
                with CaptureQueriesContext(connection) as uhvaceno:
                    odgovor = self.sacuvaj(ime)
                self.assertEqual(odgovor.status_code, 400)
                self.assertEqual(json.loads(odgovor.content), {"greska": "nepodobno_ime"})
                self.assertEqual([u["sql"] for u in uhvaceno if UPIS_SESIJE.match(u["sql"])], [])
                self.assertEqual(self.stanje(), pre)
        self.assertEqual(Session.objects.get(pk=self.client.session.session_key).session_data, red_pre)
        self.assertEqual(Rezultat.objects.count(), 0)
        # Kontrola: posle uklanjanja stavke isto ime prolazi.
        NepodobnoIme.objects.all().delete()
        self.assertEqual(self.sacuvaj("Забрањено").status_code, 200)

    def test_rec_u_imenu_nije_odbijena(self):
        for rb, ime in enumerate(("Забрањено воће", "Nezabranjeno", "zabranjeno1")):
            with self.subTest(ime=ime):
                klijent = Client()
                self.postavi_zavrsenu(f"seme-rec-u-imenu-{rb}", klijent)
                self.assertEqual(self.sacuvaj(ime, klijent).status_code, 200)
        self.assertEqual(Rezultat.objects.count(), 3)

    def test_nepodobno_telo_bez_sadrzaja(self):
        NepodobnoIme.objects.create(kljuc="druganepodobna")
        self.postavi_zavrsenu("seme-telo-nepodobno")
        tela = {self.sacuvaj(ime).content for ime in ("Забрањено", "Друга Неподобна")}
        self.assertEqual(tela, {b'{"greska": "nepodobno_ime"}'})

    def test_sifarnik_ne_izlazi(self):
        NepodobnoIme.objects.create(kljuc=STAVKA_SIFARNIKA)
        self.postavi_zavrsenu("seme-sifarnik-ne-izlazi")
        odgovori = {
            "GET": self.client.get(reverse("pocetna")),
            "400 nepodobno": self.sacuvaj(STAVKA_SIFARNIKA.upper()),
            "400 neispravno": self.sacuvaj(" x"),
            "200": self.sacuvaj("Пера"),
            "409": self.sacuvaj("Пера"),
            "GET posle": self.client.get(reverse("pocetna")),
            "potez 409": self.potez(1),
        }
        self.assertEqual(odgovori["400 nepodobno"].status_code, 400)
        self.assertEqual(odgovori["200"].status_code, 200)
        for ime, odgovor in odgovori.items():
            with self.subTest(ime=ime):
                self.assertNotIn(STAVKA_SIFARNIKA.encode(), odgovor.content)
                self.assertNotIn(b"zabranjeno", odgovor.content)
                konteksti = konteksti_odgovora(odgovor)
                if ime.startswith("GET"):
                    # Strana se crta iz sablona, pa provera mora da vidi bar jedan kontekst.
                    self.assertGreaterEqual(len(konteksti), 1)
                for kontekst in konteksti:
                    self.assertNotIn(STAVKA_SIFARNIKA, json.dumps(kontekst.flatten(), default=str))

    def test_pocetni_sifarnik_normalizovan(self):
        # Podaci iz migracije 0002 (TestCase ih ne brise).
        kljucevi = list(NepodobnoIme.objects.exclude(kljuc="zabranjeno").values_list("kljuc", flat=True))
        self.assertGreaterEqual(len(kljucevi), 30)
        for kljuc in kljucevi:
            with self.subTest(kljuc=kljuc):
                self.assertTrue(kljuc)
                self.assertEqual(imena.kljuc_imena(kljuc), kljuc)


class SifarnikPodBravomTests(PomocPrikaza, TransactionTestCase):
    """Bez spoljne test transakcije: vidi se pravi BEGIN IMMEDIATE i COMMIT prikaza (plan 10.3)."""

    CITANJE_SIFARNIKA = re.compile(r'^SELECT .* FROM "igra_nepodobnoime"')
    POCETAK = re.compile(r"^BEGIN\b")

    def upiti(self, ime):
        with CaptureQueriesContext(connection) as uhvaceno:
            odgovor = self.sacuvaj(ime)
        return odgovor, [u["sql"] for u in uhvaceno]

    def indeksi(self, uzorak, upiti):
        return [i for i, upit in enumerate(upiti) if uzorak.match(upit)]

    def test_sifarnik_posle_begin_pre_citanja_sesije(self):
        NepodobnoIme.objects.create(kljuc="zabranjeno")
        self.postavi_zavrsenu("seme-brava-prihvaceno")
        odgovor, upiti = self.upiti("Пера")
        self.assertEqual(odgovor.status_code, 200)
        pocetak = self.indeksi(self.POCETAK, upiti)
        sifarnik = self.indeksi(self.CITANJE_SIFARNIKA, upiti)
        sesija = self.indeksi(CITANJE_SESIJE, upiti)
        red = self.indeksi(UPIS_REZULTATA, upiti)
        upis_sesije = self.indeksi(UPIS_SESIJE, upiti)
        kraj = [i for i, upit in enumerate(upiti) if upit.startswith("COMMIT")]
        self.assertEqual(len(pocetak), 1, upiti)
        self.assertEqual(upiti[pocetak[0]], "BEGIN IMMEDIATE", upiti)
        self.assertEqual(len(sifarnik), 1, upiti)
        self.assertEqual(len(sesija), 1, upiti)
        self.assertEqual(len(kraj), 1, upiti)
        self.assertLess(pocetak[0], sifarnik[0], upiti)
        self.assertLess(sifarnik[0], sesija[0], upiti)
        self.assertLess(sesija[0], red[0], upiti)
        self.assertLess(red[0], upis_sesije[0], upiti)
        self.assertLess(upis_sesije[0], kraj[0], upiti)

    def test_odbijeno_sifarnikom_pod_bravom_bez_sesije(self):
        NepodobnoIme.objects.create(kljuc="zabranjeno")
        self.postavi_zavrsenu("seme-brava-odbijeno")
        pre = self.stanje()
        odgovor, upiti = self.upiti("За Брањено")
        self.assertEqual(odgovor.status_code, 400)
        self.assertEqual(json.loads(odgovor.content), {"greska": "nepodobno_ime"})
        pocetak = self.indeksi(self.POCETAK, upiti)
        sifarnik = self.indeksi(self.CITANJE_SIFARNIKA, upiti)
        self.assertEqual(len(pocetak), 1, upiti)
        self.assertEqual(len(sifarnik), 1, upiti)
        self.assertLess(pocetak[0], sifarnik[0], upiti)
        self.assertEqual(self.indeksi(CITANJE_SESIJE, upiti), [], upiti)
        self.assertEqual(self.indeksi(UPIS_SESIJE, upiti) + self.indeksi(UPIS_REZULTATA, upiti), [], upiti)
        self.assertEqual(self.stanje(), pre)
        self.assertEqual(Rezultat.objects.count(), 0)


class KomandeTests(TestCase):
    def pokreni(self, *argumenti, **opcije):
        izlaz = StringIO()
        call_command(*argumenti, stdout=izlaz, **opcije)
        return izlaz.getvalue()

    def test_dodaj_upisuje_kljuc(self):
        izlaz = self.pokreni("nepodobno_dodaj", "Шкра Бало", "Ђурђевак")
        self.assertIn("skrabalo", izlaz)
        self.assertIn("djurdjevak", izlaz)
        self.assertTrue(NepodobnoIme.objects.filter(kljuc="skrabalo").exists())
        self.assertTrue(NepodobnoIme.objects.filter(kljuc="djurdjevak").exists())

    def test_dodaj_postojece_bez_greske(self):
        self.pokreni("nepodobno_dodaj", "skrabalo")
        izlaz = self.pokreni("nepodobno_dodaj", "ŠKRABALO", "novarec")
        self.assertIn("vec postoji", izlaz)
        self.assertEqual(NepodobnoIme.objects.filter(kljuc="skrabalo").count(), 1)
        self.assertTrue(NepodobnoIme.objects.filter(kljuc="novarec").exists())

    def test_dodaj_nalazi_ime_sa_nevidljivim(self):
        # Red sacuvan pre ispravke imena: kljuc_imena skida nevidljive i bez ime_ispravno.
        pogodjen = upisi_red("Шкраㅤбало", 50)
        izlaz = self.pokreni("nepodobno_dodaj", "skrabalo")
        self.assertIn(f"id={pogodjen.id}", izlaz)

    def test_dodaj_prazan_kljuc_greska(self):
        pre = NepodobnoIme.objects.count()
        with self.assertRaises(CommandError):
            self.pokreni("nepodobno_dodaj", "novarec", "!!! 😀")
        self.assertFalse(NepodobnoIme.objects.filter(kljuc="novarec").exists())
        self.assertEqual(NepodobnoIme.objects.count(), pre)

    def test_dodaj_ispisuje_a_ne_brise_rezultate(self):
        pogodjen = upisi_red("Шкра-бало", 50)
        drugi = upisi_red("Пера", 60)
        izlaz = self.pokreni("nepodobno_dodaj", "skrabalo")
        self.assertIn(f"id={pogodjen.id}", izlaz)
        self.assertNotIn(f"id={drugi.id}", izlaz)
        self.assertIn("rezultat_obrisi", izlaz)
        self.assertEqual(Rezultat.objects.count(), 2)

    def test_dodaj_obrisi_rezultate(self):
        pogodjen = upisi_red("Шкра-бало", 50)
        drugi = upisi_red("Пера", 60)
        izlaz = self.pokreni("nepodobno_dodaj", "skrabalo", obrisi_rezultate=True)
        self.assertIn(f"id={pogodjen.id}", izlaz)
        self.assertIn("Obrisano rezultata: 1", izlaz)
        self.assertEqual(list(Rezultat.objects.values_list("id", flat=True)), [drugi.id])
        self.assertTrue(NepodobnoIme.objects.filter(kljuc="skrabalo").exists())

    def test_ukloni(self):
        NepodobnoIme.objects.create(kljuc="skrabalo")
        NepodobnoIme.objects.create(kljuc="ostaje")
        izlaz = self.pokreni("nepodobno_ukloni", "ШКРАБАЛО")
        self.assertIn("skrabalo", izlaz)
        self.assertFalse(NepodobnoIme.objects.filter(kljuc="skrabalo").exists())
        self.assertTrue(NepodobnoIme.objects.filter(kljuc="ostaje").exists())

    def test_ukloni_nepostojece_nista_ne_brise(self):
        NepodobnoIme.objects.create(kljuc="skrabalo")
        pre = NepodobnoIme.objects.count()
        with self.assertRaises(CommandError):
            self.pokreni("nepodobno_ukloni", "skrabalo", "nemaovereci")
        self.assertTrue(NepodobnoIme.objects.filter(kljuc="skrabalo").exists())
        self.assertEqual(NepodobnoIme.objects.count(), pre)

    def test_rezultati_ispis_sa_id(self):
        treci = upisi_red("Трећи", 40, utc(2026, 11, 1, 10))
        prvi = upisi_red("Први", 90, utc(2026, 11, 2, 10))
        drugi = upisi_red("Други", 40, utc(2026, 10, 1, 10))
        redovi = self.pokreni("rezultati").splitlines()
        self.assertEqual(len(redovi), 3)
        for mesto, (red, ime) in enumerate(((prvi, "Први"), (drugi, "Други"), (treci, "Трећи")), 1):
            with self.subTest(mesto=mesto):
                self.assertTrue(redovi[mesto - 1].startswith(f"{mesto}. id={red.id} "), redovi)
                self.assertIn(ime, redovi[mesto - 1])
                self.assertIn(f"poeni={red.poeni}", redovi[mesto - 1])
        # Datum u beogradskom vremenu.
        self.assertIn("01.10.2026 12:00:00", redovi[1])

    def test_rezultati_prazno(self):
        self.assertIn("Nema sacuvanih rezultata", self.pokreni("rezultati"))

    def test_rezultat_obrisi(self):
        brise = upisi_red("Брише", 50)
        ostaje = upisi_red("Остаје", 60)
        izlaz = self.pokreni("rezultat_obrisi", str(brise.id))
        self.assertIn(f"id={brise.id}", izlaz)
        self.assertEqual(list(Rezultat.objects.values_list("id", flat=True)), [ostaje.id])

    def test_rezultat_obrisi_nepostojeci_nista_ne_brise(self):
        postoji = upisi_red("Постоји", 50)
        with self.assertRaises(CommandError):
            self.pokreni("rezultat_obrisi", str(postoji.id), str(postoji.id + 1000))
        self.assertTrue(Rezultat.objects.filter(id=postoji.id).exists())


class RangListaTests(OsnovaPrikaza):
    def lista(self, klijent=None):
        return rang_iz_html((klijent or self.client).get(reverse("pocetna")))

    def test_rang_json_script_daje_recnik(self):
        prazna = self.lista()
        self.assertEqual(prazna, {"lista": [], "sacuvano": False, "moj": None})
        pera = upisi_red("Пера", 85, utc(2026, 11, 10, 9))
        rang = self.lista()
        self.assertIsInstance(rang, dict)
        self.assertEqual(
            rang["lista"],
            [{"ime": "Пера", "poeni": 85, "ocena": "odlican", "datum": "10.11.2026", "stara_pravila": False,
              "red": oznaka_reda(pera)}],
        )

    def test_redosled_poeni_pa_ranije(self):
        upisi_red("Ц", 50, utc(2026, 11, 3))
        upisi_red("А", 80, utc(2026, 11, 5))
        upisi_red("Б", 50, utc(2026, 11, 1))
        upisi_red("Д", 80, utc(2026, 11, 2))
        upisi_red("Е", 0, utc(2026, 1, 1))
        self.assertEqual([r["ime"] for r in self.lista()["lista"]], ["Д", "А", "Б", "Ц", "Е"])

    def test_isti_trenutak_po_redu_upisa(self):
        trenutak = utc(2026, 11, 10, 12)
        for ime in ("Први", "Други", "Трећи"):
            upisi_red(ime, 70, trenutak)
        self.assertEqual([r["ime"] for r in self.lista()["lista"]], ["Први", "Други", "Трећи"])

    def test_najvise_10(self):
        for i in range(11):
            upisi_red(f"Играч {i}", 50 + i, utc(2026, 11, 1 + i))
        lista = self.lista()["lista"]
        self.assertEqual(len(lista), 10)
        self.assertEqual([r["poeni"] for r in lista], list(range(60, 50, -1)))
        self.assertNotIn("Играч 0", [r["ime"] for r in lista])

    def test_datum_beogradsko_vreme(self):
        upisi_red("Зима", 90, utc(2026, 11, 9, 23, 30))
        upisi_red("Лето", 80, utc(2026, 7, 1, 22, 30))
        upisi_red("Пре поноћи", 70, utc(2026, 7, 1, 21, 59))
        self.assertEqual(
            [(r["ime"], r["datum"]) for r in self.lista()["lista"]],
            [("Зима", "10.11.2026"), ("Лето", "02.07.2026"), ("Пре поноћи", "01.07.2026")],
        )

    def test_ime_xss_u_json_script(self):
        imena_xss = ["</script><b>x", "<img src onerror=a>", "<!--", "&lt;b&gt;"]
        for rb, ime in enumerate(imena_xss):
            klijent = Client()
            self.postavi_zavrsenu(f"seme-xss-{rb}", klijent)
            self.assertEqual(self.sacuvaj(ime, klijent).status_code, 200, ime)
        html = self.client.get(reverse("pocetna")).content.decode("utf-8")
        self.assertNotIn("</script><b>x", html)
        self.assertNotIn("<img src onerror", html)
        self.assertNotIn("<!--", html)
        self.assertNotIn("<b>x", html)
        self.assertEqual(sorted(r["ime"] for r in rang_iz_html_tekst(html)["lista"]), sorted(imena_xss))
        # Ceo dokument ima tacno onoliko </script> koliko ima skripti.
        self.assertEqual(html.count("</script>"), html.count("<script"))

    def test_moj_posle_cuvanja_i_osvezavanja(self):
        sada = timezone.now()
        upisi_red("Пера", 100, sada - datetime.timedelta(hours=2))
        upisi_red("Пера", 5, sada - datetime.timedelta(hours=1))
        upisi_red("Пера", 5, sada + datetime.timedelta(hours=1))
        seme = nadji_seme(
            sve_opus, lambda i: i == [motor.USPEH] * 4 + [motor.TIHI_NEUSPEH] + [motor.USPEH] * 3
        )
        self.postavi_zavrsenu(seme)
        rang = json.loads(self.sacuvaj("Пера").content)["rang"]
        self.assertEqual([r["poeni"] for r in rang["lista"]], [100, 5, 5, 5])
        self.assertEqual(rang["moj"], 2)
        self.assertTrue(rang["sacuvano"])
        posle = self.lista()
        self.assertEqual(posle["moj"], 2)
        self.assertTrue(posle["sacuvano"])
        self.assertEqual(posle["lista"], rang["lista"])
        # Drugi posetilac vidi istu listu bez isticanja.
        drugi = Client()
        tudja = self.lista(drugi)
        self.assertEqual((tudja["moj"], tudja["sacuvano"]), (None, False))
        self.assertEqual(tudja["lista"], rang["lista"])

    def test_moj_null_posle_nove(self):
        self.postavi_zavrsenu("seme-moj-nova")
        self.assertEqual(json.loads(self.sacuvaj("Пера").content)["rang"]["moj"], 0)
        self.client.post(reverse("nova"))
        rang = self.lista()
        self.assertEqual((rang["moj"], rang["sacuvano"]), (None, False))
        self.assertEqual([r["ime"] for r in rang["lista"]], ["Пера"])

    def test_sacuvano_van_prvih_10(self):
        for i in range(10):
            upisi_red(f"Играч {i}", 100, utc(2026, 1, 1 + i))
        seme = nadji_seme(sve_opus, lambda i: motor.TIHI_NEUSPEH in i)
        self.postavi_zavrsenu(seme)
        odgovor = self.sacuvaj("Последњи")
        self.assertEqual(odgovor.status_code, 200)
        rang = json.loads(odgovor.content)["rang"]
        self.assertEqual(len(rang["lista"]), 10)
        self.assertIsNone(rang["moj"])
        self.assertTrue(rang["sacuvano"])
        self.assertNotIn("Последњи", [r["ime"] for r in rang["lista"]])
        self.assertTrue(Rezultat.objects.filter(ime="Последњи").exists())
        posle = self.lista()
        self.assertEqual((posle["moj"], posle["sacuvano"]), (None, True))


def rang_iz_html_tekst(html):
    pogodak = RANG_SCRIPT.search(html)
    if pogodak is None:
        raise AssertionError("nema json_script bloka rang-lista")
    return json.loads(pogodak.group(1))


def seme_25_poena():
    """Partija sa 5 poena (25 po pravilima 1) i jednom tihom greskom: poeni nisu podrazumevana vrednost (100)."""
    return nadji_seme(
        sve_opus, lambda i: i == [motor.USPEH] * 4 + [motor.TIHI_NEUSPEH] + [motor.USPEH] * 3
    )


class DeljenjeTests(OsnovaPrikaza):
    """POST /podeli/: plan 11.3, uslov 10."""

    def red_sesije(self, klijent=None):
        red = Session.objects.get(pk=(klijent or self.client).session.session_key)
        return red.session_data, red.expire_date

    def uz_upite(self, radnja):
        with CaptureQueriesContext(connection) as uhvaceno:
            odgovor = radnja()
        return odgovor, [u["sql"] for u in uhvaceno]

    def test_podeli_200_url_i_istice(self):
        stanje = self.postavi_zavrsenu(seme_25_poena())
        pre = timezone.now()
        odgovor = self.podeli()
        posle = timezone.now()
        self.assertEqual(odgovor.status_code, 200)
        self.assertEqual(odgovor["Content-Type"], JSON_TIP)
        podaci = json.loads(odgovor.content)
        self.assertEqual(set(podaci), KLJUCEVI_PODELI)
        red = DeljeniRezultat.objects.get()
        token = token_iz_url(podaci["url"])
        self.assertEqual(token, red.token)
        self.assertIsNotNone(OBLIK_TOKENA.fullmatch(token), token)
        self.assertLessEqual(pre, red.nastao)
        self.assertLessEqual(red.nastao, posle)
        self.assertEqual(red.istice - red.nastao, TRIDESET_DANA)
        self.assertEqual(podaci["istice"], red.istice.astimezone(BEOGRAD).strftime("%d.%m.%Y"))
        self.assertEqual(red.partija, motor.oznaka_partije(stanje))
        self.assertEqual(red.zavrsni, motor.javni_prikaz(stanje)["zavrsni"])
        self.assertEqual(red.zavrsni["poeni"], 5)
        # Oznaka u sesiji je id reda; ostatak stanja netaknut.
        self.assertEqual(self.stanje()["podeljeno"], red.id)
        self.assertEqual({k: v for k, v in self.stanje().items() if k != "podeljeno"}, stanje)
        self.assertEqual(Rezultat.objects.count(), 0)

    def test_istice_u_beogradskom_vremenu(self):
        # 23:30 UTC je vec sledeci dan u Beogradu: datum isteka mora biti u TIME_ZONE, ne u UTC.
        trenutak = timezone.now().replace(hour=23, minute=30, second=0, microsecond=0)
        self.postavi_zavrsenu("seme-istice-beograd")
        with mock.patch("igra.views.timezone.now", return_value=trenutak):
            podaci = self.podeli_json()
        red = DeljeniRezultat.objects.get()
        self.assertEqual(red.nastao, trenutak)
        ocekivano = (trenutak + TRIDESET_DANA).astimezone(BEOGRAD).strftime("%d.%m.%Y")
        self.assertNotEqual(ocekivano, (trenutak + TRIDESET_DANA).strftime("%d.%m.%Y"))
        self.assertEqual(podaci["istice"], ocekivano)

    def test_ponovni_klik_isti_link(self):
        self.postavi_zavrsenu("seme-ponovni-klik")
        prvi = self.podeli()
        self.assertEqual(prvi.status_code, 200)
        sesija_pre = self.red_sesije()
        drugi, upiti = self.uz_upite(self.podeli)
        self.assertEqual(drugi.status_code, 200)
        self.assertEqual(drugi.content, prvi.content)
        self.assertEqual([u for u in upiti if UPIS_DELJENOG.match(u)], [], upiti)
        self.assertEqual([u for u in upiti if UPIS_SESIJE.match(u)], [], upiti)
        self.assertEqual(self.red_sesije(), sesija_pre)
        self.assertEqual(DeljeniRezultat.objects.count(), 1)

    def test_posle_osvezavanja_isti_link(self):
        self.postavi_zavrsenu("seme-osvezavanje-deljenja")
        prvi = self.podeli_json()
        osvezeno = self.client.get(reverse("pocetna"))
        self.assertEqual(osvezeno.status_code, 200)
        self.assertEqual(stanje_iz_html(osvezeno)["faza"], "zavrsena")
        self.assertEqual(self.podeli_json(), prvi)
        self.assertEqual(DeljeniRezultat.objects.count(), 1)

    def test_izgubljena_oznaka_isti_link(self):
        # Ono sto bi video drugi istovremeni zahtev da je sesiju procitao pre upisa prvog.
        stanje = self.postavi_zavrsenu("seme-izgubljena-oznaka-deljenja")
        postojeci = upisi_deljeno(stanje)
        self.assertNotIn("podeljeno", self.stanje())
        podaci = self.podeli_json()
        self.assertEqual(token_iz_url(podaci["url"]), postojeci.token)
        self.assertEqual(list(DeljeniRezultat.objects.values_list("id", flat=True)), [postojeci.id])
        self.assertEqual(self.stanje()["podeljeno"], postojeci.id)

    def test_nova_posle_deljenja_nov_link(self):
        self.postavi_zavrsenu("seme-nova-posle-deljenja")
        prvi = self.podeli_json()
        self.assertEqual(self.client.post(reverse("nova")).status_code, 302)
        self.assertNotIn("podeljeno", self.stanje())
        rano = self.podeli()
        self.assertEqual(rano.status_code, 409)
        self.assertEqual(json.loads(rano.content), {"greska": "igra_nije_zavrsena"})
        self.odigraj_do(8)
        drugi = self.podeli_json()
        self.assertNotEqual(drugi["url"], prvi["url"])
        self.assertEqual(DeljeniRezultat.objects.count(), 2)
        self.assertEqual(len(set(DeljeniRezultat.objects.values_list("partija", flat=True))), 2)
        # Stari link i dalje otvara staru partiju.
        self.assertEqual(self.deljena(token_iz_url(prvi["url"])).status_code, 200)
        self.assertEqual(self.deljena(token_iz_url(drugi["url"])).status_code, 200)

    def test_podeli_cita_i_upisuje_u_istoj_transakciji(self):
        self.postavi_zavrsenu("seme-transakcija-deljenja")
        odgovor, upiti = self.uz_upite(self.podeli)
        self.assertEqual(odgovor.status_code, 200)
        # U TestCase-u je spoljni atomic prikaza SAVEPOINT; sve izmedju njega i RELEASE je pod bravom.
        otvaranje = next(i for i, upit in enumerate(upiti) if upit.startswith("SAVEPOINT"))
        zatvaranje = upiti.index("RELEASE " + upiti[otvaranje])
        citanja = [i for i, upit in enumerate(upiti) if CITANJE_SESIJE.match(upit)]
        upisi_reda = [i for i, upit in enumerate(upiti) if UPIS_DELJENOG.match(upit)]
        upisi_sesije = [i for i, upit in enumerate(upiti) if UPIS_SESIJE.match(upit)]
        self.assertEqual(len(citanja), 1, upiti)
        self.assertEqual(len(upisi_reda), 1, upiti)
        self.assertEqual(len(upisi_sesije), 1, upiti)
        self.assertLess(otvaranje, citanja[0], upiti)
        self.assertLess(citanja[0], upisi_reda[0], upiti)
        self.assertLess(upisi_reda[0], upisi_sesije[0], upiti)
        self.assertLess(upisi_sesije[0], zatvaranje, upiti)

    def test_podeli_nema_igre_409(self):
        klijent = Client()
        sesija_pre = Session.objects.count()
        odgovor, upiti = self.uz_upite(lambda: self.podeli(klijent))
        self.assertEqual(odgovor.status_code, 409)
        self.assertEqual(json.loads(odgovor.content), {"greska": "nema_igre"})
        self.assertEqual([u for u in upiti if UPIS_SESIJE.match(u) or UPIS_DELJENOG.match(u)], [])
        self.assertEqual(Session.objects.count(), sesija_pre)
        self.assertEqual(DeljeniRezultat.objects.count(), 0)

    def test_podeli_nezavrsena_409(self):
        self.postavi_igru("seme-deljenje-nezavrsena")
        odigrano = 0
        for krugova in (0, 3, 7):
            with self.subTest(krugova=krugova):
                for krug in range(odigrano + 1, krugova + 1):
                    self.assertEqual(self.potez(krug).status_code, 200)
                odigrano = krugova
                pre = self.stanje()
                sesija_pre = self.red_sesije()
                odgovor, upiti = self.uz_upite(self.podeli)
                self.assertEqual(odgovor.status_code, 409)
                self.assertEqual(json.loads(odgovor.content), {"greska": "igra_nije_zavrsena"})
                self.assertEqual([u for u in upiti if UPIS_SESIJE.match(u) or UPIS_DELJENOG.match(u)], [])
                self.assertEqual(self.stanje(), pre)
                self.assertEqual(self.red_sesije(), sesija_pre)
        self.assertEqual(DeljeniRezultat.objects.count(), 0)
        # Kontrola: posle 8. kruga ista sesija dobija link.
        self.assertEqual(self.potez(8).status_code, 200)
        self.assertEqual(self.podeli().status_code, 200)

    def test_podeli_isteklo_409(self):
        def istekni(red):
            sada = timezone.now()
            DeljeniRezultat.objects.filter(id=red.id).update(
                nastao=sada - TRIDESET_DANA - datetime.timedelta(days=1),
                istice=sada - datetime.timedelta(days=1),
            )

        def obrisi(red):
            DeljeniRezultat.objects.filter(id=red.id).delete()

        for opis, izmena in (("istekao red", istekni), ("obrisan red", obrisi)):
            with self.subTest(opis=opis):
                klijent = Client()
                self.postavi_zavrsenu(f"seme-isteklo-{opis}", klijent)
                prvi = self.podeli_json(klijent)
                red = DeljeniRezultat.objects.get(token=token_iz_url(prvi["url"]))
                izmena(red)
                broj_pre = DeljeniRezultat.objects.count()
                pre = self.stanje(klijent)
                sesija_pre = self.red_sesije(klijent)
                odgovor, upiti = self.uz_upite(lambda: self.podeli(klijent))
                self.assertEqual(odgovor.status_code, 409)
                self.assertEqual(json.loads(odgovor.content), {"greska": "deljenje_isteklo"})
                self.assertEqual([u for u in upiti if UPIS_SESIJE.match(u) or UPIS_DELJENOG.match(u)], [])
                self.assertEqual(DeljeniRezultat.objects.count(), broj_pre)
                self.assertEqual(self.stanje(klijent), pre)
                self.assertEqual(self.red_sesije(klijent), sesija_pre)

        with self.subTest(opis="izgubljena oznaka, istekao red"):
            klijent = Client()
            stanje = self.postavi_zavrsenu("seme-isteklo-bez-oznake", klijent)
            istekao = istekao_red(stanje)
            odgovor = self.podeli(klijent)
            self.assertEqual(odgovor.status_code, 409)
            self.assertEqual(json.loads(odgovor.content), {"greska": "deljenje_isteklo"})
            self.assertEqual(DeljeniRezultat.objects.filter(partija=istekao.partija).count(), 1)
            self.assertNotIn("podeljeno", self.stanje(klijent))

    def test_podeli_bez_csrf_403(self):
        klijent = Client(enforce_csrf_checks=True)
        self.postavi_zavrsenu("seme-csrf-deljenje", klijent)
        klijent.get(reverse("pocetna"))
        token = klijent.cookies["csrftoken"].value
        pre = self.stanje(klijent)
        odgovor = self.podeli(klijent)
        self.assertEqual(odgovor.status_code, 403)
        self.assertEqual(DeljeniRezultat.objects.count(), 0)
        self.assertEqual(self.stanje(klijent), pre)
        # Kontrola: isti klijent sa tokenom prolazi, pa 403 dolazi od CSRF-a.
        odgovor = self.podeli(klijent, headers={"X-CSRFToken": token})
        self.assertEqual(odgovor.status_code, 200)
        self.assertEqual(DeljeniRezultat.objects.count(), 1)

    def test_podeli_get_405(self):
        self.postavi_zavrsenu("seme-deljenje-405")
        for metoda in (self.client.get, self.client.put, self.client.delete):
            with self.subTest(metoda=metoda.__name__):
                odgovor = metoda(reverse("podeli"))
                self.assertEqual(odgovor.status_code, 405)
                self.assertEqual(odgovor.content, b"")
        self.assertEqual(DeljeniRezultat.objects.count(), 0)
        self.assertNotIn("podeljeno", self.stanje())

    def test_podeli_ne_cita_telo(self):
        stanje = self.postavi_zavrsenu(seme_25_poena())
        zadat_token = "A" * 22
        telo = json.dumps({"poeni": 100, "token": zadat_token, "url": "http://napadac.example/r/x/"})
        odgovor = self.podeli(data=telo, content_type=JSON_TIP)
        self.assertEqual(odgovor.status_code, 200)
        podaci = json.loads(odgovor.content)
        red = DeljeniRezultat.objects.get()
        self.assertNotEqual(red.token, zadat_token)
        self.assertEqual(token_iz_url(podaci["url"]), red.token)
        self.assertEqual(red.zavrsni["poeni"], stanje["rezultat"]["poeni"])
        self.assertEqual(red.zavrsni["poeni"], 5)
        # Ni neispravno telo ne daje 400: telo se ne cita.
        drugi = Client()
        self.postavi_zavrsenu("seme-telo-necitljivo", drugi)
        self.assertEqual(self.podeli(drugi, data=b"{", content_type=JSON_TIP).status_code, 200)

    def test_deljenje_bez_imena(self):
        upisi_red("Туђе име", 90)
        self.postavi_zavrsenu("seme-deljenje-bez-imena")
        podaci = self.podeli_json()
        self.assertEqual(Rezultat.objects.count(), 1)
        self.assertNotIn("sacuvan", self.stanje())
        strana = self.deljena(token_iz_url(podaci["url"]))
        self.assertEqual(strana.status_code, 200)
        self.assertIsNone(deljeno_iz_html(strana)["ime"])
        self.assertNotIn("Туђе име".encode(), strana.content)
        # Deljenje ne zatvara rang listu: ista partija se posle cuva.
        self.assertEqual(self.sacuvaj("Пера").status_code, 200)

    def test_token_nasumican(self):
        seme = "seme-token-nasumican-3c1d"
        stanje = self.postavi_zavrsenu(seme)
        with mock.patch("igra.views.secrets.token_urlsafe", wraps=secrets.token_urlsafe) as izvor:
            podaci = self.podeli_json()
        izvor.assert_called_once_with(16)
        red = DeljeniRezultat.objects.get()
        token = token_iz_url(podaci["url"])
        self.assertEqual(token, red.token)
        self.assertIsNotNone(OBLIK_TOKENA.fullmatch(token), token)
        partija = motor.oznaka_partije(stanje)
        for tajna in (seme, partija):
            with self.subTest(tajna=tajna[:12]):
                self.assertNotIn(token, tajna)
                self.assertNotIn(tajna, token)
        # Token je ono sto je izvor vratio, ne vrednost izvedena iz partije.
        self.assertNotEqual(token, partija[:22])

    def test_tokeni_razliciti(self):
        tokeni = []
        for rb in range(20):
            klijent = Client()
            self.postavi_zavrsenu(f"seme-tokeni-{rb}", klijent)
            tokeni.append(token_iz_url(self.podeli_json(klijent)["url"]))
        self.assertEqual(len(tokeni), 20)
        self.assertEqual(len(set(tokeni)), 20)
        for token in tokeni:
            self.assertIsNotNone(OBLIK_TOKENA.fullmatch(token), token)
        self.assertEqual(DeljeniRezultat.objects.count(), 20)


class OznakaTudjePartijeTests(OsnovaPrikaza):
    """Revizija N1: oznaka `sacuvan` ili `podeljeno` koja pokazuje na red DRUGE partije racuna se kao izgubljena.

    Posle `migrate igra 0002` ili `zero` pa `migrate` AUTOINCREMENT krece od 1, pa id iz stare sesije
    pripadne tudjem redu. Ovde se to pravi bez migracije: red druge partije dobija bas id iz oznake.
    """

    ID_IZ_OZNAKE = 4242

    def igra_sa_oznakom(self, seme, kljuc, broj, strategija=sve_opus):
        stanje = odigraj_celu(seme, strategija)
        oznaceno = motor.oznaci_podeljeno(stanje, broj) if kljuc == "podeljeno" else motor.oznaci_sacuvano(stanje, broj)
        self.postavi_igru(seme, stanje=oznaceno)
        return stanje

    def tudji_deljeni(self, **dodatno):
        tudje = odigraj_celu("seme-tudja-partija-n1", sve_opus)
        return upisi_deljeno(tudje, id=self.ID_IZ_OZNAKE, **dodatno)

    # ---------- podeli ----------

    def test_podeli_oznaka_na_tudji_red_daje_nov_link_tekuce_partije(self):
        tudji = self.tudji_deljeni()
        stanje = self.igra_sa_oznakom(seme_25_poena(), "podeljeno", self.ID_IZ_OZNAKE)
        self.assertNotEqual(tudji.partija, motor.oznaka_partije(stanje))
        self.assertNotEqual(tudji.zavrsni["poeni"], stanje["rezultat"]["poeni"])
        odgovor = self.podeli()
        self.assertEqual(odgovor.status_code, 200)
        self.assertNotIn(tudji.token.encode(), odgovor.content)
        podaci = json.loads(odgovor.content)
        self.assertEqual(set(podaci), KLJUCEVI_PODELI)
        moj = DeljeniRezultat.objects.get(partija=motor.oznaka_partije(stanje))
        self.assertEqual(token_iz_url(podaci["url"]), moj.token)
        self.assertNotEqual(moj.id, self.ID_IZ_OZNAKE)
        # Oznaka prepisana na sopstveni red; tudji red netaknut.
        self.assertEqual(self.stanje()["podeljeno"], moj.id)
        self.assertEqual(DeljeniRezultat.objects.get(id=self.ID_IZ_OZNAKE).token, tudji.token)
        self.assertEqual(DeljeniRezultat.objects.count(), 2)
        # Link pokazuje rezultat tekuce partije, ne tudje.
        strana = self.deljena(moj.token, Client())
        self.assertEqual(deljeno_iz_html(strana)["zavrsni"], motor.javni_prikaz(stanje)["zavrsni"])
        # Ponovni klik: isti link, i dalje nikad tudji.
        ponovo = self.podeli()
        self.assertEqual(ponovo.content, odgovor.content)
        self.assertNotIn(tudji.token.encode(), ponovo.content)
        self.assertEqual(DeljeniRezultat.objects.count(), 2)

    def test_podeli_oznaka_na_tudji_istekao_red_daje_nov_link(self):
        sada = timezone.now()
        tudji = self.tudji_deljeni(nastao=sada - TRIDESET_DANA - datetime.timedelta(days=1),
                                   istice=sada - datetime.timedelta(days=1))
        stanje = self.igra_sa_oznakom("seme-n1-tudji-istekao", "podeljeno", self.ID_IZ_OZNAKE)
        odgovor = self.podeli()
        self.assertEqual(odgovor.status_code, 200)
        moj = DeljeniRezultat.objects.get(partija=motor.oznaka_partije(stanje))
        self.assertEqual(token_iz_url(json.loads(odgovor.content)["url"]), moj.token)
        self.assertNotIn(tudji.token.encode(), odgovor.content)

    def test_podeli_oznaka_na_tudji_red_a_sopstveni_postoji(self):
        tudji = self.tudji_deljeni()
        stanje = self.igra_sa_oznakom("seme-n1-oba-reda", "podeljeno", self.ID_IZ_OZNAKE)
        sopstveni = upisi_deljeno(stanje)
        podaci = self.podeli_json()
        self.assertEqual(token_iz_url(podaci["url"]), sopstveni.token)
        self.assertNotEqual(token_iz_url(podaci["url"]), tudji.token)
        self.assertEqual(self.stanje()["podeljeno"], sopstveni.id)
        self.assertEqual(DeljeniRezultat.objects.count(), 2)

    def test_podeli_oznaka_na_nepostojeci_red_409(self):
        self.igra_sa_oznakom("seme-n1-nepostojeci", "podeljeno", self.ID_IZ_OZNAKE)
        self.assertFalse(DeljeniRezultat.objects.filter(id=self.ID_IZ_OZNAKE).exists())
        for pokusaj in (1, 2):
            with self.subTest(pokusaj=pokusaj):
                odgovor = self.podeli()
                self.assertEqual(odgovor.status_code, 409)
                self.assertEqual(json.loads(odgovor.content), {"greska": "deljenje_isteklo"})
        self.assertEqual(DeljeniRezultat.objects.count(), 0)
        self.assertEqual(self.stanje()["podeljeno"], self.ID_IZ_OZNAKE)

    # ---------- rang i sacuvaj ----------

    def tudji_rezultat(self):
        return Rezultat.objects.create(
            id=self.ID_IZ_OZNAKE, ime="Туђи играч", poeni=95, ocena=motor.oceni(95), pravila=p.PRAVILA_TEKUCA,
            partija=motor.oznaka_partije({"seme": "seme-tudja-partija-n1"}),
        )

    def test_rang_oznaka_na_tudji_red_nije_moj(self):
        self.tudji_rezultat()
        upisi_red("Трећи", 10)
        self.igra_sa_oznakom(seme_25_poena(), "sacuvan", self.ID_IZ_OZNAKE)
        rang = rang_iz_html(self.client.get(reverse("pocetna")))
        self.assertEqual([r["ime"] for r in rang["lista"]], ["Туђи играч", "Трећи"])
        self.assertEqual((rang["sacuvano"], rang["moj"]), (False, None))
        # Isti rang i u telu odbijenog cuvanja (400 ne nosi rang; 409 nosi).
        drugi = Client()
        self.postavi_igru("seme-n1-u-toku", drugi, motor.oznaci_sacuvano(motor.nova_igra("seme-n1-u-toku"), self.ID_IZ_OZNAKE))
        rano = json.loads(self.sacuvaj("Пера", drugi).content)
        self.assertEqual(rano["greska"], "igra_nije_zavrsena")
        self.assertEqual((rano["rang"]["sacuvano"], rano["rang"]["moj"]), (False, None))

    def test_sacuvaj_oznaka_na_tudji_red_cuva_tekucu_partiju(self):
        tudji = self.tudji_rezultat()
        stanje = self.igra_sa_oznakom(seme_25_poena(), "sacuvan", self.ID_IZ_OZNAKE)
        odgovor = self.sacuvaj("Пера")
        self.assertEqual(odgovor.status_code, 200, odgovor.content)
        moj = Rezultat.objects.get(partija=motor.oznaka_partije(stanje))
        self.assertEqual((moj.ime, moj.poeni), ("Пера", 5))
        self.assertEqual(self.stanje()["sacuvan"], moj.id)
        self.assertNotEqual(moj.id, self.ID_IZ_OZNAKE)
        rang = json.loads(odgovor.content)["rang"]
        self.assertEqual([r["ime"] for r in rang["lista"]], ["Туђи играч", "Пера"])
        self.assertEqual((rang["sacuvano"], rang["moj"]), (True, 1))
        # Tudji red netaknut i ne oznacen; posle osvezavanja isto.
        tudji.refresh_from_db()
        self.assertEqual((tudji.ime, tudji.poeni), ("Туђи играч", 95))
        posle = rang_iz_html(self.client.get(reverse("pocetna")))
        self.assertEqual((posle["sacuvano"], posle["moj"]), (True, 1))
        # Tacno jednom: drugi pokusaj 409.
        drugi = self.sacuvaj("Мика")
        self.assertEqual(drugi.status_code, 409)
        self.assertEqual(json.loads(drugi.content)["greska"], "vec_sacuvano")
        self.assertEqual(Rezultat.objects.count(), 2)

    def test_oznaka_obrisanog_reda_ostaje_sacuvana(self):
        stanje = self.postavi_zavrsenu("seme-n1-obrisan")
        upisi_red("Други", 70)
        self.assertEqual(self.sacuvaj("Пера").status_code, 200)
        call_command("rezultat_obrisi", str(self.stanje()["sacuvan"]), stdout=StringIO())
        self.assertFalse(Rezultat.objects.filter(partija=motor.oznaka_partije(stanje)).exists())
        rang = rang_iz_html(self.client.get(reverse("pocetna")))
        self.assertEqual((rang["sacuvano"], rang["moj"]), (True, None))
        self.assertEqual([r["ime"] for r in rang["lista"]], ["Други"])
        odgovor = self.sacuvaj("Опет")
        self.assertEqual(odgovor.status_code, 409)
        self.assertEqual(json.loads(odgovor.content)["greska"], "vec_sacuvano")
        self.assertFalse(Rezultat.objects.filter(partija=motor.oznaka_partije(stanje)).exists())


class DeljenaStranaTests(OsnovaPrikaza):
    """GET /r/<token>/: plan 11.4 i 11.5, uslov 10."""

    def podeli_partiju(self, seme, klijent=None, strategija=strategija_najduza):
        stanje = self.postavi_zavrsenu(seme, klijent, strategija)
        return stanje, token_iz_url(self.podeli_json(klijent)["url"])

    def test_strana_iste_partije(self):
        seme = nadji_seme(strategija_najduza, lambda i: i.count(motor.TIHI_NEUSPEH) == 3)
        stanje, token = self.podeli_partiju(seme)
        odgovor = self.deljena(token, Client())
        self.assertEqual(odgovor.status_code, 200)
        self.assertTemplateUsed(odgovor, "igra/deljeno.html")
        self.assertTemplateUsed(odgovor, "igra/_zavrsni.html")
        zavrsni = deljeno_iz_html(odgovor)["zavrsni"]
        self.assertEqual(zavrsni, motor.javni_prikaz(stanje)["zavrsni"])
        self.assertEqual(len(zavrsni["tihe_greske"]), 3)
        self.assertEqual(len(zavrsni["lekcije"]), 5)

    def test_strana_samo_za_citanje(self):
        _, token = self.podeli_partiju("seme-samo-citanje")
        html = self.deljena(token, Client()).content.decode("utf-8")
        for zabranjeno in (
            "<form", 'id="kontrole"', 'id="potvrdi"', 'id="rang-forma"', 'id="deli"',
            'id="nova-forma"', 'id="stanje-igre"', 'id="rang-lista"', "csrfmiddlewaretoken",
            "data-url-",
        ):
            with self.subTest(zabranjeno=zabranjeno):
                self.assertNotIn(zabranjeno, html)
        self.assertEqual(html.count('id="zavrsni"'), 1)
        self.assertIn("Ово је завршена партија; овде се не може играти.", html)
        self.assertIn("<title>Подељени резултат · Оркестратор</title>", html)
        dugme = re.search(r'<a id="igraj-i-ti"[^>]*>', html)
        self.assertIsNotNone(dugme)
        self.assertIn('href="/"', dugme.group(0))
        # Kontrola: strana igre ima sve sto deljena nema.
        igra = self.client.get(reverse("pocetna")).content.decode("utf-8")
        for postoji in ('id="rang-forma"', 'id="deli"', 'id="nova-forma"', "csrfmiddlewaretoken"):
            self.assertIn(postoji, igra)

    def test_granica_isteka(self):
        red = upisi_deljeno()
        for opis, sada, status in (
            ("1 mikrosekunda pre", red.istice - datetime.timedelta(microseconds=1), 200),
            ("tacno istice", red.istice, 404),
            ("dan posle", red.istice + datetime.timedelta(days=1), 404),
        ):
            with self.subTest(opis=opis):
                with mock.patch("igra.views.timezone.now", return_value=sada):
                    self.assertEqual(self.deljena(red.token, Client()).status_code, status)

    def test_istekao_i_nepostojeci_isti(self):
        vazeci = upisi_deljeno()
        istekao = istekao_red()
        nepostojeci = secrets.token_urlsafe(16)
        self.assertFalse(DeljeniRezultat.objects.filter(token=nepostojeci).exists())
        # Kontrola: vazeci token daje 200, pa su 21, 23 znaka i %0A blizu pravog linka.
        self.assertEqual(self.deljena(vazeci.token, Client()).status_code, 200)
        putanje = {
            "istekao": f"/r/{istekao.token}/",
            "nepostojeci": f"/r/{nepostojeci}/",
            "21 znak": f"/r/{vazeci.token[:21]}/",
            "23 znaka": f"/r/{vazeci.token}A/",
            "%0A posle vazeceg": f"/r/{vazeci.token}%0A/",
            "istekao uz %0A": f"/r/{istekao.token}%0A/",
        }
        tela = {}
        for opis, putanja in putanje.items():
            with self.subTest(opis=opis):
                odgovor = Client().get(putanja)
                self.assertEqual(odgovor.status_code, 404)
                tela[opis] = odgovor.content
        self.assertEqual(len(tela), len(putanje))
        self.assertEqual(len(set(tela.values())), 1, tela)
        telo = tela["istekao"].decode("utf-8")
        self.assertIn(NEDOSTUPNO, telo)
        self.assertIn("Линк за дељење важи 30 дана.", telo)
        self.assertIn("<title>Резултат није доступан · Оркестратор</title>", telo)
        self.assertNotIn("deljeni-rezultat", telo)
        self.assertNotIn('id="zavrsni"', telo)

    def test_strana_ne_pravi_sesiju(self):
        _, token = self.podeli_partiju("seme-bez-sesije")
        for opis, putanja in (
            ("200", reverse("deljeno", args=[token])),
            ("404", reverse("deljeno", args=[secrets.token_urlsafe(16)])),
        ):
            with self.subTest(opis=opis, klijent="svez"):
                klijent = Client()
                sesija_pre = Session.objects.count()
                odgovor = klijent.get(putanja)
                self.assertEqual(odgovor.status_code, int(opis))
                self.assertEqual(len(odgovor.cookies), 0, odgovor.cookies)
                self.assertEqual(len(klijent.cookies), 0)
                self.assertEqual(Session.objects.count(), sesija_pre)
                self.assertNotIn(b"csrfmiddlewaretoken", odgovor.content)
            # Plan 12.9: Vary: Cookie je sada obavezan (jezik iz kolacica), pa dokaz da strana ne dira
            # sesiju ne cita zaglavlje nego upite: klijent sa postojecom sesijom, nijedan upit nad sesijom.
            with self.subTest(opis=opis, klijent="sa sesijom"):
                klijent = Client()
                self.postavi_igru(f"seme-posetilac-bez-citanja-{opis}", klijent)
                kolacici_pre = {ime: k.value for ime, k in klijent.cookies.items()}
                self.assertIn(settings.SESSION_COOKIE_NAME, kolacici_pre)
                red_pre = Session.objects.get(pk=klijent.session.session_key)
                with CaptureQueriesContext(connection) as uhvaceno:
                    odgovor = klijent.get(putanja)
                upiti = [u["sql"] for u in uhvaceno]
                self.assertEqual(odgovor.status_code, int(opis))
                # Kontrola: upiti strane su uhvaceni (deljeni rezultat se trazi u bazi).
                self.assertTrue(any('"igra_deljenirezultat"' in u for u in upiti), upiti)
                self.assertEqual(
                    [u for u in upiti if CITANJE_SESIJE.match(u) or UPIS_SESIJE.match(u)], [], upiti
                )
                self.assertEqual(len(odgovor.cookies), 0, odgovor.cookies)
                self.assertEqual({ime: k.value for ime, k in klijent.cookies.items()}, kolacici_pre)
                red_posle = Session.objects.get(pk=red_pre.pk)
                self.assertEqual((red_posle.session_data, red_posle.expire_date),
                                 (red_pre.session_data, red_pre.expire_date))
                self.assertNotIn(b"csrfmiddlewaretoken", odgovor.content)
        # Kontrola: isti svez klijent na pocetnoj dobija oba kolacica i Vary: Cookie.
        klijent = Client()
        pocetna = klijent.get(reverse("pocetna"))
        self.assertEqual(set(pocetna.cookies), {"sessionid", "csrftoken"})
        self.assertIn("Cookie", pocetna["Vary"])
        # Kontrola: detektor upita vidi citanje sesije kad ga prikaz radi.
        with CaptureQueriesContext(connection) as uhvaceno:
            self.assertEqual(klijent.get(reverse("pocetna")).status_code, 200)
        self.assertTrue([u["sql"] for u in uhvaceno if CITANJE_SESIJE.match(u["sql"])])

    def test_strana_ne_menja_igru_posetioca(self):
        _, token = self.podeli_partiju("seme-tudja-partija")
        posetilac = Client()
        self.postavi_igru("seme-posetilac", posetilac)
        self.odigraj_do(2, klijent=posetilac)
        stanje_pre = self.stanje(posetilac)
        sesija_pre = Session.objects.get(pk=posetilac.session.session_key)
        for putanja, status in ((reverse("deljeno", args=[token]), 200), (reverse("deljeno", args=["x" * 22]), 404)):
            with self.subTest(putanja=putanja):
                odgovor = posetilac.get(putanja)
                self.assertEqual(odgovor.status_code, status)
                self.assertEqual(len(odgovor.cookies), 0)
        sesija_posle = Session.objects.get(pk=posetilac.session.session_key)
        self.assertEqual(sesija_posle.session_data, sesija_pre.session_data)
        self.assertEqual(sesija_posle.expire_date, sesija_pre.expire_date)
        self.assertEqual(self.stanje(posetilac), stanje_pre)
        # Posetilac nastavlja svoju partiju od istog kruga.
        self.assertEqual(self.potez(3, klijent=posetilac).status_code, 200)
        self.assertEqual(self.stanje(posetilac)["krug"], 4)

    def test_zaglavlja(self):
        _, token = self.podeli_partiju("seme-zaglavlja")
        for opis, odgovor in (
            ("200", self.deljena(token, Client())),
            ("404", self.deljena(secrets.token_urlsafe(16), Client())),
        ):
            with self.subTest(opis=opis):
                self.assertEqual(odgovor.status_code, int(opis))
                kes = odgovor["Cache-Control"]
                for deo in ("no-store", "private", "no-cache", "max-age=0"):
                    self.assertIn(deo, kes)
                self.assertEqual(odgovor["Referrer-Policy"], "no-referrer")
                self.assertEqual(odgovor["X-Robots-Tag"], "noindex, nofollow")
                self.assertEqual(odgovor["X-Frame-Options"], "DENY")
                self.assertIn(b'<meta name="robots" content="noindex, nofollow">', odgovor.content)
                # Plan 12.2: jezik zavisi od zaglavlja i kolacica, pa kes mora da razlikuje oba.
                vary = {deo.strip() for deo in odgovor["Vary"].split(",")}
                self.assertLessEqual({"Accept-Language", "Cookie"}, vary, odgovor["Vary"])
                self.assertEqual(odgovor["Content-Language"], "sr")
        # Kontrola: bez prikaza deljene strane middleware salje same-origin.
        self.assertEqual(self.client.get(reverse("pocetna"))["Referrer-Policy"], "same-origin")

    def test_deljeno_post_405(self):
        red = upisi_deljeno()
        for ime in ("post", "put", "delete"):
            with self.subTest(metoda=ime):
                odgovor = getattr(Client(), ime)(reverse("deljeno", args=[red.token]))
                self.assertEqual(odgovor.status_code, 405)
        # Kontrola: GET istog linka radi.
        self.assertEqual(self.deljena(red.token).status_code, 200)

    def test_deljeno_tacan_skup_kljuceva(self):
        seme = nadji_seme(strategija_najduza, lambda i: i.count(motor.TIHI_NEUSPEH) >= 1)
        self.postavi_zavrsenu(seme, strategija=strategija_najduza)
        podeli = json.loads(self.podeli().content)
        self.assertEqual(set(podeli), KLJUCEVI_PODELI)
        self.assertEqual(self.sacuvaj("Пера").status_code, 200)
        for opis, klijent in (("posetilac", Client()), ("igrac", self.client)):
            with self.subTest(opis=opis):
                podaci = deljeno_iz_html(self.deljena(token_iz_url(podeli["url"]), klijent))
                self.assertEqual(set(podaci), KLJUCEVI_DELJENOG)
                self.assertEqual(set(podaci["zavrsni"]), KLJUCEVI_ZAVRSNOG)
                self.assertGreaterEqual(len(podaci["zavrsni"]["tihe_greske"]), 1)
                self.assertGreaterEqual(len(podaci["zavrsni"]["lekcije"]), 1)
                for tiha in podaci["zavrsni"]["tihe_greske"]:
                    self.assertEqual(set(tiha), KLJUCEVI_TIHE)
                for lekcija in podaci["zavrsni"]["lekcije"]:
                    self.assertEqual(set(lekcija), KLJUCEVI_LEKCIJE)
                self.assertEqual(podaci["ime"], "Пера")

    def test_deljeno_bez_skrivenog(self):
        seme = next(
            kandidat for kandidat in (f"tajno-seme-deljeno-x9q-{i}" for i in range(1000))
            if motor.TIHI_NEUSPEH in ishodi(odigraj_celu(kandidat, sve_opus))
        )
        stanje = odigraj_celu(seme, sve_opus)
        self.postavi_igru(seme, stanje=stanje)
        # Prepoznatljiv id i trenuci: provera trazi tacne vrednosti, ne imena polja.
        nastao = utc(2026, 11, 3, 7, 41, 29, 123457)
        red = upisi_deljeno(stanje, nastao=nastao, id=7340561)
        self.assertEqual(self.podeli_json()["url"], f"http://testserver/r/{red.token}/")
        with mock.patch("igra.views.timezone.now", return_value=utc(2026, 11, 10, 12)):
            odgovor = self.deljena(red.token, Client())
        self.assertEqual(odgovor.status_code, 200)
        # Kontrola: vrednosti koje se traze postoje na serveru.
        self.assertEqual(red.partija, motor.oznaka_partije({"seme": seme}))
        self.assertEqual(self.stanje()["podeljeno"], 7340561)
        html = odgovor.content.decode("utf-8")
        for tajna in (seme, red.partija, "7340561", red.token, "07:41", "08:41", "41:29", "123457",
                      "2026-11-03", "2026-12-03", "03.12.2026"):
            with self.subTest(tajna=tajna):
                self.assertNotIn(tajna, html)
                for zaglavlje, vrednost in odgovor.items():
                    self.assertNotIn(tajna, str(vrednost), zaglavlje)
        self.assertEqual(ZABRANJENE_RECI.findall(html), [])
        self.assertEqual(ZABRANJENE_RECI_CIRILICA.findall(html), [])
        podaci = deljeno_iz_html(odgovor)
        self.assertEqual(skriveni_kljucevi(podaci, zavrsena=True), set())
        self.assertEqual(
            set(svi_kljucevi(podaci)) & {"token", "nastao", "istice", "podeljeno", "partija", "id"}, set()
        )
        self.assertGreaterEqual(len(podaci["zavrsni"]["tihe_greske"]), 1)
        self.assertEqual(podaci["datum"], "03.11.2026")

    def test_deljeno_json_script_daje_recnik(self):
        _, token = self.podeli_partiju("seme-deljeno-skript")
        podaci = deljeno_iz_html(self.deljena(token, Client()))
        self.assertIsInstance(podaci, dict)
        self.assertIsInstance(podaci["zavrsni"], dict)
        self.assertIsInstance(podaci["zavrsni"]["poeni"], int)
        self.assertIsInstance(podaci["zavrsni"]["ukupna_cena"], float)
        self.assertIsInstance(podaci["zavrsni"]["tihe_greske"], list)
        self.assertIsNone(podaci["ime"])
        self.assertRegex(podaci["datum"], r"^\d{2}\.\d{2}\.\d{4}$")
        self.assertEqual(podaci["datum"], timezone.now().astimezone(BEOGRAD).strftime("%d.%m.%Y"))

    def test_datum_dan_nastanka_linka(self):
        # D1: datum je dan nastanka linka u Beogradu, a ne dan otvaranja strane.
        for nastao, ocekivano in (
            (utc(2026, 11, 9, 22, 59), "09.11.2026"),
            (utc(2026, 11, 9, 23, 0), "10.11.2026"),
            (utc(2026, 7, 1, 21, 59), "01.07.2026"),
            (utc(2026, 7, 1, 22, 0), "02.07.2026"),
        ):
            with self.subTest(nastao=nastao):
                red = upisi_deljeno(nastao=nastao)
                with mock.patch("igra.views.timezone.now", return_value=nastao + datetime.timedelta(days=20)):
                    odgovor = self.deljena(red.token, Client())
                self.assertEqual(odgovor.status_code, 200)
                self.assertEqual(deljeno_iz_html(odgovor)["datum"], ocekivano)

    def test_ime_posle_kasnijeg_cuvanja(self):
        _, token = self.podeli_partiju("seme-ime-kasnije")
        pre = self.deljena(token, Client())
        self.assertIsNone(deljeno_iz_html(pre)["ime"])
        self.assertEqual(self.sacuvaj("Пера Перић").status_code, 200)
        posle = self.deljena(token, Client())
        self.assertEqual(posle.status_code, 200)
        self.assertEqual(deljeno_iz_html(posle)["ime"], "Пера Перић")
        self.assertEqual(deljeno_iz_html(posle)["zavrsni"], deljeno_iz_html(pre)["zavrsni"])

    def test_ime_sacuvano_pre(self):
        self.postavi_zavrsenu("seme-ime-pre")
        self.assertEqual(self.sacuvaj("Мика").status_code, 200)
        token = token_iz_url(self.podeli_json()["url"])
        self.assertEqual(deljeno_iz_html(self.deljena(token, Client()))["ime"], "Мика")

    def test_ime_nestaje_posle_rezultat_obrisi(self):
        _, token = self.podeli_partiju("seme-ime-obrisano")
        self.assertEqual(self.sacuvaj("Брисање").status_code, 200)
        self.assertEqual(deljeno_iz_html(self.deljena(token, Client()))["ime"], "Брисање")
        call_command("rezultat_obrisi", str(self.stanje()["sacuvan"]), stdout=StringIO())
        odgovor = self.deljena(token, Client())
        self.assertEqual(odgovor.status_code, 200)
        self.assertIsNone(deljeno_iz_html(odgovor)["ime"])
        self.assertNotIn("Брисање".encode(), odgovor.content)

    def test_ime_xss_u_json_script(self):
        ime = "</script><b>x"
        _, token = self.podeli_partiju("seme-deljeno-xss")
        self.assertEqual(self.sacuvaj(ime).status_code, 200)
        odgovor = self.deljena(token, Client())
        html = odgovor.content.decode("utf-8")
        self.assertNotIn("</script><b>x", html)
        self.assertNotIn("<b>x", html)
        self.assertEqual(deljeno_iz_html(odgovor)["ime"], ime)
        # Ceo dokument ima tacno onoliko </script> koliko ima skripti.
        self.assertEqual(html.count("</script>"), html.count("<script"))
        # Ime je samo u json_script bloku; van njega ga nema ni u kakvom obliku.
        bez_skripte = DELJENO_SCRIPT.sub("", html)
        self.assertNotIn("u003C/script", bez_skripte)
        self.assertNotIn("&lt;/script&gt;", bez_skripte)
        self.assertIn("\\u003C/script\\u003E\\u003Cb\\u003Ex", html)


class DeljenjeModelTests(TestCase):
    """DeljeniRezultat: granica isteka i ogranicenja baze (plan 11.2)."""

    def test_istekli_i_vazeci_granica(self):
        red = upisi_deljeno(nastao=utc(2026, 11, 10, 12))
        self.assertEqual(red.istice, utc(2026, 12, 10, 12))
        for opis, sada, vazi in (
            ("1 mikrosekunda pre", red.istice - datetime.timedelta(microseconds=1), True),
            ("tacno istice", red.istice, False),
            ("sekund posle", red.istice + datetime.timedelta(seconds=1), False),
            ("nastanak", red.nastao, True),
        ):
            with self.subTest(opis=opis):
                vazeci = list(DeljeniRezultat.objects.vazeci(sada).values_list("id", flat=True))
                istekli = list(DeljeniRezultat.objects.istekli(sada).values_list("id", flat=True))
                self.assertEqual(vazeci, [red.id] if vazi else [])
                self.assertEqual(istekli, [] if vazi else [red.id])
                self.assertEqual(red.istekao(sada), not vazi)

    def test_istice_posle_nastanka(self):
        sada = timezone.now()
        stanje = odigraj_celu("seme-model-ogranicenja", sve_opus)
        for opis, izmene in (
            ("istice jednako nastanku", {"istice": sada}),
            ("istice pre nastanka", {"istice": sada - datetime.timedelta(seconds=1)}),
            ("prazan token", {"token": ""}),
        ):
            with self.subTest(opis=opis):
                podaci = {"token": secrets.token_urlsafe(16), "partija": f"partija-{opis}",
                          "zavrsni": motor.za_deljenje(stanje), "nastao": sada,
                          "istice": sada + TRIDESET_DANA, **izmene}
                with self.assertRaises(IntegrityError), transaction.atomic():
                    DeljeniRezultat.objects.create(**podaci)
        self.assertEqual(DeljeniRezultat.objects.count(), 0)
        # Kontrola: isti red sa ispravnim rokom se upisuje.
        upisi_deljeno(stanje, nastao=sada)
        self.assertEqual(DeljeniRezultat.objects.count(), 1)

    def test_token_i_partija_jedinstveni(self):
        prvi = upisi_deljeno()
        drugo_stanje = odigraj_celu("seme-model-jedinstven", sve_opus)
        for opis, izmene in (
            ("isti token", {"token": prvi.token}),
            ("ista partija", {"partija": prvi.partija}),
        ):
            with self.subTest(opis=opis):
                podaci = {"token": secrets.token_urlsafe(16),
                          "partija": motor.oznaka_partije(drugo_stanje),
                          "zavrsni": motor.za_deljenje(drugo_stanje), "nastao": timezone.now(),
                          "istice": timezone.now() + TRIDESET_DANA, **izmene}
                with self.assertRaises(IntegrityError), transaction.atomic():
                    DeljeniRezultat.objects.create(**podaci)
        self.assertEqual(DeljeniRezultat.objects.count(), 1)

    def test_full_clean_duzina_tokena(self):
        red = upisi_deljeno()
        red.full_clean(validate_unique=False)
        red.token = red.token + "A"
        with self.assertRaises(ValidationError) as greska:
            red.full_clean(validate_unique=False)
        self.assertIn("token", greska.exception.message_dict)


class DeljeniKomandeTests(PomocPrikaza, TestCase):
    """Komande deljeni, deljeni_obrisi, deljeni_ocisti (plan 11.8)."""

    def pokreni(self, *argumenti, **opcije):
        izlaz = StringIO()
        call_command(*argumenti, stdout=izlaz, **opcije)
        return izlaz.getvalue()

    def test_ocisti_brise_samo_istekle(self):
        sada = timezone.now()
        istekao = upisi_deljeno(nastao=sada - TRIDESET_DANA - datetime.timedelta(days=1),
                                istice=sada - datetime.timedelta(days=1))
        vazeci = upisi_deljeno(nastao=sada - TRIDESET_DANA + datetime.timedelta(days=1),
                               istice=sada + datetime.timedelta(days=1))
        self.assertEqual(self.pokreni("deljeni_ocisti").strip(), "obrisano isteklih: 1")
        self.assertEqual(list(DeljeniRezultat.objects.values_list("id", flat=True)), [vazeci.id])
        self.assertFalse(DeljeniRezultat.objects.filter(id=istekao.id).exists())
        self.assertEqual(self.pokreni("deljeni_ocisti").strip(), "obrisano isteklih: 0")
        self.assertEqual(self.deljena(vazeci.token).status_code, 200)

    def test_ocisti_prazno(self):
        self.assertEqual(self.pokreni("deljeni_ocisti").strip(), "obrisano isteklih: 0")
        self.assertEqual(DeljeniRezultat.objects.count(), 0)

    def test_deljeni_ispis_bez_tokena(self):
        self.assertIn("Nema deljenih rezultata.", self.pokreni("deljeni"))
        stanje = odigraj_celu(seme_25_poena(), sve_opus)
        sa_imenom = upisi_deljeno(stanje, nastao=utc(2026, 11, 9, 23, 30),
                                  istice=timezone.now() + datetime.timedelta(days=1))
        Rezultat.objects.create(ime="Пера", poeni=5, ocena="pozar", pravila=p.PRAVILA_TEKUCA, partija=sa_imenom.partija)
        istekao = istekao_red()
        redovi = self.pokreni("deljeni").splitlines()
        self.assertEqual(len(redovi), 2, redovi)
        self.assertTrue(redovi[0].startswith(f"id={sa_imenom.id} "), redovi)
        self.assertTrue(redovi[1].startswith(f"id={istekao.id} "), redovi)
        self.assertIn("nastao=10.11.2026 00:30:00", redovi[0])
        self.assertIn(" vazi ", redovi[0])
        self.assertIn(" istekao ", redovi[1])
        self.assertIn("poeni=5 ", redovi[0])
        # Komanda ispisuje kljuc ocene, isto kao u bazi (plan 12.7).
        self.assertIn("ocena='pozar'", redovi[0])
        self.assertIn("ime='Пера'", redovi[0])
        self.assertTrue(redovi[1].endswith("ime=-"), redovi[1])
        ceo = "\n".join(redovi)
        for red in (sa_imenom, istekao):
            self.assertNotIn(red.token, ceo)
            self.assertNotIn(red.partija, ceo)

    def test_deljeni_po_tokenu(self):
        prvi = upisi_deljeno()
        drugi = upisi_deljeno()
        redovi = self.pokreni("deljeni", token=drugi.token).splitlines()
        self.assertEqual(len(redovi), 1, redovi)
        self.assertTrue(redovi[0].startswith(f"id={drugi.id} "), redovi)
        self.assertNotIn(drugi.token, redovi[0])
        self.assertNotIn(f"id={prvi.id} ", redovi[0])
        nepoznat = secrets.token_urlsafe(16)
        izlaz = self.pokreni("deljeni", token=nepoznat)
        self.assertIn("Nema deljenog rezultata sa tim tokenom.", izlaz)
        self.assertNotIn(nepoznat, izlaz)

    def test_deljeni_obrisi(self):
        stanje = self.postavi_zavrsenu("seme-komanda-obrisi")
        token = token_iz_url(self.podeli_json()["url"])
        brise = DeljeniRezultat.objects.get(token=token)
        ostaje = upisi_deljeno()
        izlaz = self.pokreni("deljeni_obrisi", str(brise.id))
        self.assertIn(f"obrisano: id={brise.id} ", izlaz)
        self.assertNotIn(token, izlaz)
        self.assertEqual(list(DeljeniRezultat.objects.values_list("id", flat=True)), [ostaje.id])
        # Link odmah daje 404; ta partija novi link ne dobija.
        self.assertEqual(self.deljena(token, Client()).status_code, 404)
        odgovor = self.podeli()
        self.assertEqual(odgovor.status_code, 409)
        self.assertEqual(json.loads(odgovor.content), {"greska": "deljenje_isteklo"})
        self.assertEqual(self.stanje()["podeljeno"], brise.id)
        self.assertEqual(self.stanje()["seme"], stanje["seme"])
        self.assertEqual(self.deljena(ostaje.token).status_code, 200)

    def test_deljeni_obrisi_nepostojeci_nista_ne_brise(self):
        postoji = upisi_deljeno()
        with self.assertRaises(CommandError):
            self.pokreni("deljeni_obrisi", str(postoji.id), str(postoji.id + 1000))
        self.assertTrue(DeljeniRezultat.objects.filter(id=postoji.id).exists())
        self.assertEqual(self.deljena(postoji.token).status_code, 200)


# ---------- Srpski i engleski (plan 12, uslov 11) ----------

LANG_HTML = re.compile(r'<html lang="([^"]+)">')
NASLOV_HTML = re.compile(r"<title>(.*?)</title>", re.S)
JSON_BLOKOVI = re.compile(r'<script id="([^"]+)" type="application/json">(.*?)</script>', re.S)
# Jedini dozvoljeni cirilicni tekst na engleskoj strani: naziv drugog jezika u elementu sa lang="sr".
SRPSKI_IZBOR = re.compile(r'<(button|a)\b[^>]*\blang="sr"[^>]*>Српски</\1>')
MESTO_VREDNOSTI = re.compile(r"%\((\w+)\)s")
DOZVOLJENA_LATINICA = {"Haiku", "Sonnet", "Opus", "low", "high", "max", "CSS", "CRUD"}
KATALOG = pathlib.Path(settings.BASE_DIR) / "locale"
TRAJANJE_KOLACICA = 365 * 24 * 60 * 60


def jezik_strane(odgovor):
    pogodak = LANG_HTML.search(odgovor.content.decode("utf-8"))
    return pogodak.group(1) if pogodak else None


def naslov_strane(odgovor):
    pogodak = NASLOV_HTML.search(odgovor.content.decode("utf-8"))
    return pogodak.group(1) if pogodak else None


def svi_tekstovi(objekat):
    """Svi stringovi u JSON objektu (vrednosti, ne kljucevi)."""
    if isinstance(objekat, str):
        yield objekat
    elif isinstance(objekat, dict):
        for vrednost in objekat.values():
            yield from svi_tekstovi(vrednost)
    elif isinstance(objekat, list):
        for vrednost in objekat:
            yield from svi_tekstovi(vrednost)


def json_blokovi(odgovor):
    return {ime: json.loads(sadrzaj) for ime, sadrzaj in JSON_BLOKOVI.findall(odgovor.content.decode("utf-8"))}


def _neescape(tekst):
    zamene = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}
    return re.sub(r"\\(.)", lambda m: zamene[m.group(1)], tekst)


def procitaj_po(putanja):
    """(zaglavlje, stavke) .po kataloga. Stavka: msgid, msgid_plural, msgstr ili msgstr[n], oznake (#,)."""
    zaglavlje, stavke = None, []
    for blok in re.split(r"\n\s*\n", pathlib.Path(putanja).read_text(encoding="utf-8")):
        polja, oznake, polje = {}, set(), None
        for red in blok.splitlines():
            if red.startswith("#~"):  # zastarela stavka: nije u katalogu
                polja = {}
                break
            if red.startswith("#,"):
                oznake.update(o.strip() for o in red[2:].split(","))
                continue
            if red.startswith("#") or not red.strip():
                continue
            pocetak = re.match(r'(msgid_plural|msgid|msgstr(?:\[\d+\])?) "(.*)"$', red)
            if pocetak:
                polje = pocetak.group(1)
                polja[polje] = _neescape(pocetak.group(2))
                continue
            nastavak = re.match(r'"(.*)"$', red)
            if nastavak is None or polje is None:
                raise AssertionError(f"neocekivan red u {putanja}: {red!r}")
            polja[polje] += _neescape(nastavak.group(1))
        if "msgid" not in polja:
            continue
        if polja["msgid"] == "":
            zaglavlje = polja["msgstr"]
            continue
        stavke.append({**polja, "oznake": oznake})
    return zaglavlje, stavke


def oblici(stavka):
    """Prevodi stavke: [msgstr] ili [msgstr[0], msgstr[1], ...]."""
    if "msgid_plural" in stavka:
        return [stavka[k] for k in sorted((k for k in stavka if k.startswith("msgstr[")),
                                          key=lambda k: int(k[7:-1]))]
    return [stavka["msgstr"]]


def oznaceni_tekstovi():
    """Svaki tekst oznacen za prevod u parametri.py i tekstovi.py (plan 12.3), sa mestom porekla."""
    tekstovi_ = [(f"zadatak {z['kljuc']}", z["naziv"]) for z in p.ZADACI]
    for grupa, opcije in (("model", p.MODELI), ("nivo", p.NIVOI)):
        tekstovi_ += [(f"{grupa} {k} opis", o["opis"]) for k, o in opcije.items()]
    for grupa, opcije in (("kontekst", p.KONTEKSTI), ("podela", p.PODELE)):
        tekstovi_ += [(f"{grupa} {k} {polje}", o[polje]) for k, o in opcije.items() for polje in ("naziv", "opis")]
    tekstovi_ += [(f"ocena {k}", v) for k, v in p.NAZIVI_OCENA.items()]
    tekstovi_ += [(f"status {k}", v) for k, v in p.NAZIVI_STATUSA.items()]
    tekstovi_ += [(f"lekcija {k}", v["tekst"]) for k, v in p.LEKCIJE.items()]
    tekstovi_ += [("napomena", p.NAPOMENA), ("pitanjeNova", tekstovi.PITANJE_NOVA)]
    for ime, mapa in (("poruka", tekstovi.PORUKE), ("deljenje", tekstovi.DELJENJE), ("obrazac", tekstovi.OBRASCI)):
        tekstovi_ += [(f"{ime} {k}", v) for k, v in mapa.items()]
    return tekstovi_


class JezikTests(OsnovaPrikaza):
    """Uslov 11: jezik pregledaca, kolacic, POST /jezik/ (plan 12.2, 12.9)."""

    def strana(self, klijent=None, **zaglavlja):
        odgovor = (klijent or Client()).get(reverse("pocetna"), headers=zaglavlja)
        self.assertEqual(odgovor.status_code, 200)
        return odgovor

    def proveri_jezik(self, odgovor, jezik):
        krug = {"sr": "Круг %(krug)s од %(ukupno)s", "en": "Round %(krug)s of %(ukupno)s"}[jezik]
        self.assertEqual(odgovor["Content-Language"], jezik)
        self.assertEqual(jezik_strane(odgovor), jezik)
        self.assertEqual(naslov_strane(odgovor), {"sr": "Оркестратор", "en": "Orchestrator"}[jezik])
        self.assertEqual(tekstovi_iz_html(odgovor)["obrasci"]["krug"], krug)

    def test_podrazumevano_sr(self):
        self.assertEqual(settings.LANGUAGE_CODE, "sr")
        self.assertEqual(settings.LANGUAGES, [("sr", "Српски"), ("en", "English")])
        odgovor = self.strana()
        self.proveri_jezik(odgovor, "sr")
        vary = {deo.strip() for deo in odgovor["Vary"].split(",")}
        self.assertLessEqual({"Accept-Language", "Cookie"}, vary)

    def test_accept_language(self):
        for zaglavlje, jezik in (
            ("en-US", "en"), ("en-GB", "en"), ("en", "en"), ("de", "sr"), ("sr-Latn", "sr"),
            ("de, en;q=0.5", "en"), ("sr, en", "sr"), ("en;q=0.4, sr;q=0.9", "sr"),
        ):
            with self.subTest(zaglavlje=zaglavlje):
                self.proveri_jezik(self.strana(accept_language=zaglavlje), jezik)

    def test_kolacic_jaci_od_zaglavlja(self):
        for kolacic, zaglavlje in (("sr", "en-US"), ("en", "sr")):
            with self.subTest(kolacic=kolacic):
                self.proveri_jezik(self.strana(klijent_jezika(kolacic), accept_language=zaglavlje), kolacic)

    def test_nepodrzan_kolacic(self):
        for kolacic, zaglavlje, jezik in (("de", None, "sr"), ("de", "en-US", "en"), ("xx-yy", None, "sr")):
            with self.subTest(kolacic=kolacic, zaglavlje=zaglavlje):
                zaglavlja = {"accept_language": zaglavlje} if zaglavlje else {}
                self.proveri_jezik(self.strana(klijent_jezika(kolacic), **zaglavlja), jezik)

    def test_dugme_jezika(self):
        forma = re.compile(r'<form id="jezik-forma"[^>]*>(.*?)</form>', re.S)
        for jezik, drugi, naziv in (("sr", "en", "English"), ("en", "sr", "Српски")):
            with self.subTest(jezik=jezik):
                html = self.strana(klijent_jezika(jezik)).content.decode("utf-8")
                pocetak = re.search(r'<form id="jezik-forma"[^>]*>', html).group(0)
                self.assertIn('method="post"', pocetak)
                self.assertIn(f'action="{reverse("jezik")}"', pocetak)
                telo = forma.search(html).group(1)
                self.assertIn('name="csrfmiddlewaretoken"', telo)
                self.assertIn('<input type="hidden" name="next" value="/">', telo)
                dugme = re.findall(r'<button[^>]*id="jezik-dugme"[^>]*>([^<]*)</button>', telo)
                self.assertEqual(dugme, [naziv])
                self.assertRegex(telo, rf'name="language" value="{drugi}" lang="{drugi}">{naziv}<')

    def test_jezik_post_kolacic(self):
        klijent = Client()
        self.postavi_igru("seme-jezik-post", klijent)
        odgovor = klijent.post(reverse("jezik"), {"language": "en", "next": reverse("pocetna")})
        self.assertEqual(odgovor.status_code, 302)
        self.assertEqual(odgovor["Location"], "/")
        self.assertEqual(settings.LANGUAGE_COOKIE_NAME, "django_language")
        kolacic = odgovor.cookies[settings.LANGUAGE_COOKIE_NAME]
        self.assertEqual(kolacic.value, "en")
        self.assertEqual(int(kolacic["max-age"]), TRAJANJE_KOLACICA)
        self.assertEqual(kolacic["samesite"], "Lax")
        self.assertTrue(kolacic["httponly"])
        self.assertEqual(kolacic["path"], "/")
        self.proveri_jezik(self.strana(klijent, accept_language="sr"), "en")
        # Nazad na srpski istim putem.
        nazad = klijent.post(reverse("jezik"), {"language": "sr", "next": "/"})
        self.assertEqual(nazad.cookies[settings.LANGUAGE_COOKIE_NAME].value, "sr")
        self.proveri_jezik(self.strana(klijent, accept_language="en"), "sr")

    def test_jezik_get_405(self):
        for metoda in ("get", "put", "delete"):
            with self.subTest(metoda=metoda):
                odgovor = getattr(self.client, metoda)(reverse("jezik") + "?language=en&next=/")
                self.assertEqual(odgovor.status_code, 405)
                self.assertNotIn(settings.LANGUAGE_COOKIE_NAME, odgovor.cookies)

    def test_jezik_bez_csrf_403(self):
        klijent = Client(enforce_csrf_checks=True)
        klijent.get(reverse("pocetna"))
        token = klijent.cookies["csrftoken"].value
        odgovor = klijent.post(reverse("jezik"), {"language": "en", "next": "/"})
        self.assertEqual(odgovor.status_code, 403)
        self.assertNotIn(settings.LANGUAGE_COOKIE_NAME, odgovor.cookies)
        self.proveri_jezik(self.strana(klijent), "sr")
        # Kontrola: isti klijent sa tokenom prolazi, pa 403 dolazi od CSRF-a.
        odgovor = klijent.post(reverse("jezik"), {"language": "en", "next": "/", "csrfmiddlewaretoken": token})
        self.assertEqual(odgovor.status_code, 302)
        self.assertEqual(odgovor.cookies[settings.LANGUAGE_COOKIE_NAME].value, "en")

    # Revizija 2026-11-11: Django set_language prihvata svaki kod sa Django katalogom; /jezik/ samo LANGUAGES.
    NEPODRZANI_KODOVI = {
        "de": "de", "sr-x1": "sr-x1", "EN": "EN", "en-us": "en-us", "prazno": "",
        "4500 znakova": "en-" + "a" * 4500,
    }

    def test_jezik_samo_iz_liste(self):
        slucajevi = {**{opis: {"language": kod, "next": "/"} for opis, kod in self.NEPODRZANI_KODOVI.items()},
                     "bez polja": {"next": "/"}}
        for opis, podaci in slucajevi.items():
            with self.subTest(opis=opis):
                klijent = Client()
                with mock.patch("igra.views.set_language", wraps=views.set_language) as django_prikaz:
                    odgovor = klijent.post(reverse("jezik"), podaci)
                self.assertEqual(odgovor.status_code, 400)
                self.assertEqual(odgovor.content, b"")
                self.assertNotIn(settings.LANGUAGE_COOKIE_NAME, odgovor.cookies)
                self.assertNotIn(settings.LANGUAGE_COOKIE_NAME, klijent.cookies)
                django_prikaz.assert_not_called()
                # Kolacic nije upisan, pa sledeca strana ostaje srpska.
                self.assertEqual(klijent.get(reverse("pocetna"))["Content-Language"], "sr")
        # Kontrola: podrzani kodovi i dalje prolaze kroz set_language (302 i kolacic).
        for kod in ("sr", "en"):
            with self.subTest(kod=kod):
                with mock.patch("igra.views.set_language", wraps=views.set_language) as django_prikaz:
                    odgovor = Client().post(reverse("jezik"), {"language": kod, "next": "/"})
                self.assertEqual(odgovor.status_code, 302)
                self.assertEqual(odgovor.cookies[settings.LANGUAGE_COOKIE_NAME].value, kod)
                django_prikaz.assert_called_once()

    def test_kes_prevoda_ne_raste(self):
        from django.utils.translation import trans_real

        # Kodovi koje Django pre ispravke prima (postoji katalog ili osnovni jezik): svaki bi trajno usao u kes.
        kodovi = ["sr-x1", "sr-x2", "en-x3", "fr", "it", "pt-br", "de-x4", "EN-X5"]
        trans_real.translation("sr")  # podrzani jezici su vec u kesu posle prvog zahteva
        trans_real.translation("en")
        pre = set(trans_real._translations)
        for kod in kodovi:
            for sledeca in ("/", reverse("deljeno", args=["x" * 22]), "/r/abc/"):
                with self.subTest(kod=kod, next=sledeca):
                    odgovor = Client().post(reverse("jezik"), {"language": kod, "next": sledeca})
                    self.assertEqual(odgovor.status_code, 400)
            odgovor = Client().get(reverse("deljeno", args=["x" * 22]), {"jezik": kod})
            self.assertEqual(odgovor["Content-Language"], "sr")
        self.assertEqual(set(trans_real._translations) - pre, set())
        self.assertEqual(len(trans_real._translations), len(pre))

    def test_jezik_next_spolja(self):
        for sledeca in ("http://napadac.example/", "//napadac.example/", "https://napadac.example/r/x/",
                        "javascript:alert(1)"):
            with self.subTest(next=sledeca):
                odgovor = Client().post(reverse("jezik"), {"language": "en", "next": sledeca})
                self.assertEqual(odgovor.status_code, 302)
                adresa = urllib.parse.urlsplit(odgovor["Location"])
                self.assertEqual((adresa.scheme, adresa.netloc), ("", ""), odgovor["Location"])
                self.assertNotIn("napadac", odgovor["Location"])
        # Kontrola: bezbedan next se postuje, pa provera iznad vidi pravu odluku Django-a.
        odgovor = Client().post(reverse("jezik"), {"language": "en", "next": "/r/abc/"})
        self.assertEqual(odgovor["Location"], "/r/abc/")

    def test_jezik_ne_dira_sesiju(self):
        self.postavi_igru("seme-jezik-sesija")
        self.odigraj_do(2)
        pre = self.stanje()
        red_pre = Session.objects.get(pk=self.client.session.session_key)
        with CaptureQueriesContext(connection) as uhvaceno:
            odgovor = self.client.post(reverse("jezik"), {"language": "en", "next": "/"})
        self.assertEqual(odgovor.status_code, 302)
        self.assertEqual([u["sql"] for u in uhvaceno if UPIS_SESIJE.match(u["sql"])], [])
        red_posle = Session.objects.get(pk=red_pre.pk)
        self.assertEqual((red_posle.session_data, red_posle.expire_date), (red_pre.session_data, red_pre.expire_date))
        self.assertEqual(self.stanje(), pre)
        self.assertEqual(stanje_iz_html(self.client.get(reverse("pocetna")))["krug"], 3)

    def test_promena_jezika_usred_partije(self):
        seme = nadji_seme(po_tezini, lambda i: motor.TIHI_NEUSPEH in i and motor.DORADA in i)
        samo_sr, menja = klijent_jezika("sr"), klijent_jezika("sr")
        self.postavi_igru(seme, samo_sr)
        self.postavi_igru(seme, menja)
        for krug in KRUGOVI:
            if krug == 5:
                self.assertEqual(menja.post(reverse("jezik"), {"language": "en", "next": "/"}).status_code, 302)
                strana_en, strana_sr = self.strana(menja), self.strana(samo_sr)
                self.proveri_jezik(strana_en, "en")
                self.proveri_jezik(strana_sr, "sr")
                self.assertEqual(stanje_iz_html(strana_en), stanje_iz_html(strana_sr))
                self.assertEqual(stanje_iz_html(strana_en)["krug"], 5)
            with self.subTest(krug=krug):
                a = self.potez(krug, po_tezini(krug), samo_sr)
                b = self.potez(krug, po_tezini(krug), menja)
                self.assertEqual(a.status_code, 200)
                self.assertEqual(b.content, a.content)
        self.assertEqual(self.stanje(menja), self.stanje(samo_sr))
        self.assertEqual(self.stanje(menja), odigraj_celu(seme, po_tezini))
        kraj_en, kraj_sr = self.strana(menja), self.strana(samo_sr)
        self.proveri_jezik(kraj_en, "en")
        self.assertEqual(stanje_iz_html(kraj_en), stanje_iz_html(kraj_sr))
        self.assertEqual(stanje_iz_html(kraj_en)["faza"], "zavrsena")

    def test_json_ne_zavisi_od_jezika(self):
        seme = nadji_seme(po_tezini, lambda i: motor.TIHI_NEUSPEH in i and motor.DORADA in i)
        klijenti = {jezik: klijent_jezika(jezik) for jezik in JEZICI}
        for klijent in klijenti.values():
            self.postavi_igru(seme, klijent)
        for krug in KRUGOVI:
            with self.subTest(krug=krug):
                tela = {j: self.potez(krug, po_tezini(krug), k).content for j, k in klijenti.items()}
                self.assertEqual(tela["en"], tela["sr"])
                odbijeno = {j: self.potez(krug, po_tezini(krug), k).content for j, k in klijenti.items()}
                self.assertEqual(odbijeno["en"], odbijeno["sr"])
                lose = {j: self.potez(krug + 1, {**OPUS_HIGH, "model": "gpt"}, k).content
                        for j, k in klijenti.items()}
                self.assertEqual(lose["en"], lose["sr"])
        for jezik, klijent in klijenti.items():
            with self.subTest(jezik=jezik, strana="pocetna"):
                self.assertEqual(self.strana(klijent)["Content-Language"], jezik)
        self.assertEqual(stanje_iz_html(self.strana(klijenti["en"])),
                         stanje_iz_html(self.strana(klijenti["sr"])))
        # Rang: isti JSON osim datuma, koji je jedini zavisan od jezika (plan 12.3). Ista partija
        # (isto seme) se cuva jednom, pa engleski klijent dobija 409 sa istom listom.
        upisi_red("Drugi", 40)
        prvi = self.sacuvaj("Igrac", klijenti["sr"])
        self.assertEqual(prvi.status_code, 200)
        drugi = self.sacuvaj("Igrac", klijenti["en"])
        self.assertEqual(drugi.status_code, 409)
        rang = {"sr": json.loads(prvi.content)["rang"], "en": json.loads(drugi.content)["rang"],
                "en strana": rang_iz_html(self.strana(klijenti["en"]))}
        bez_datuma = {j: [{k: v for k, v in red.items() if k != "datum"} for red in r["lista"]] for j, r in rang.items()}
        self.assertEqual(len(bez_datuma["sr"]), 2)
        self.assertEqual(bez_datuma["en"], bez_datuma["sr"])
        self.assertEqual(bez_datuma["en strana"], bez_datuma["sr"])
        self.assertRegex(rang["sr"]["lista"][0]["datum"], r"^\d{2}\.\d{2}\.\d{4}$")
        self.assertRegex(rang["en"]["lista"][0]["datum"], r"^\d{4}-\d{2}-\d{2}$")

    def test_datumi_po_jeziku(self):
        # 23:30 UTC je vec sledeci dan u Beogradu, i na engleskom (plan 12.2: TIME_ZONE na oba jezika).
        trenutak = utc(2026, 11, 9, 23, 30)
        ocekivano = {
            "sr": {"istice": "10.12.2026", "deljeno": "10.11.2026"},
            "en": {"istice": "2026-12-10", "deljeno": "2026-11-10"},
        }
        for jezik in JEZICI:
            with self.subTest(jezik=jezik):
                klijent = klijent_jezika(jezik)
                self.postavi_zavrsenu(f"seme-datum-{jezik}", klijent)
                with mock.patch("igra.views.timezone.now", return_value=trenutak):
                    podeli = self.podeli_json(klijent)
                    deljena = self.deljena(token_iz_url(podeli["url"]), klijent)
                self.assertEqual(podeli["istice"], ocekivano[jezik]["istice"])
                self.assertEqual(deljeno_iz_html(deljena)["datum"], ocekivano[jezik]["deljeno"])

    def test_rang_na_jeziku_posmatraca(self):
        pera = upisi_red("Pera", 85, utc(2026, 11, 9, 23, 30))
        ana = upisi_red("Ana", 20, utc(2026, 7, 1, 22, 30))
        for jezik, datumi, ocene in (
            ("sr", ["10.11.2026", "02.07.2026"], ["одличан оркестратор", "пожар"]),
            ("en", ["2026-11-10", "2026-07-02"], ["excellent orchestrator", "disaster"]),
        ):
            with self.subTest(jezik=jezik):
                odgovor = self.strana(klijent_jezika(jezik))
                self.proveri_jezik(odgovor, jezik)
                lista = rang_iz_html(odgovor)["lista"]
                # Oznaka reda ne zavisi od jezika.
                self.assertEqual(
                    lista,
                    [{"ime": "Pera", "poeni": 85, "ocena": "odlican", "datum": datumi[0], "stara_pravila": False,
                      "red": oznaka_reda(pera)},
                     {"ime": "Ana", "poeni": 20, "ocena": "pozar", "datum": datumi[1], "stara_pravila": False,
                      "red": oznaka_reda(ana)}],
                )
                tekst = tekstovi_iz_html(odgovor)["ocene"]
                self.assertEqual([tekst[r["ocena"]] for r in lista], ocene)

    def test_deljena_na_jeziku_posmatraca(self):
        stanje = odigraj_celu(nadji_seme(strategija_najduza, lambda i: motor.TIHI_NEUSPEH in i), strategija_najduza)
        red = upisi_deljeno(stanje, nastao=utc(2026, 11, 9, 23, 30))
        Rezultat.objects.create(ime="Пера", poeni=stanje["rezultat"]["poeni"], ocena=stanje["rezultat"]["ocena"],
                                pravila=p.PRAVILA_TEKUCA, partija=red.partija)
        with mock.patch("igra.views.timezone.now", return_value=utc(2026, 11, 20)):
            strane = {j: self.deljena(red.token, klijent_jezika(j)) for j in JEZICI}
            nedostupne = {j: self.deljena(secrets.token_urlsafe(16), klijent_jezika(j)) for j in JEZICI}
        for jezik, naslov, datum in (
            ("sr", "Подељени резултат · Оркестратор", "10.11.2026"),
            ("en", "Shared result · Orchestrator", "2026-11-10"),
        ):
            with self.subTest(jezik=jezik):
                odgovor = strane[jezik]
                self.assertEqual(odgovor.status_code, 200)
                self.assertEqual(odgovor["Content-Language"], jezik)
                self.assertEqual(jezik_strane(odgovor), jezik)
                self.assertEqual(naslov_strane(odgovor), naslov)
                self.assertEqual(deljeno_iz_html(odgovor)["datum"], datum)
                # Ime igraca se ne prevodi.
                self.assertEqual(deljeno_iz_html(odgovor)["ime"], "Пера")
        bez_datuma = {j: {k: v for k, v in deljeno_iz_html(o).items() if k != "datum"} for j, o in strane.items()}
        self.assertEqual(bez_datuma["en"], bez_datuma["sr"])
        self.assertEqual(tekstovi_iz_html(strane["en"])["ocene"]["odlican"], "excellent orchestrator")
        for jezik, naslov, poruka in (
            ("sr", "Резултат није доступан · Оркестратор", NEDOSTUPNO),
            ("en", "Result not available · Orchestrator", "This result is no longer available."),
        ):
            with self.subTest(jezik=jezik, status=404):
                odgovor = nedostupne[jezik]
                self.assertEqual(odgovor.status_code, 404)
                self.assertEqual((odgovor["Content-Language"], jezik_strane(odgovor)), (jezik, jezik))
                self.assertEqual(naslov_strane(odgovor), naslov)
                self.assertIn(poruka, odgovor.content.decode("utf-8"))

    def test_deljena_parametar_jezika(self):
        red = upisi_deljeno()
        putanja = reverse("deljeno", args=[red.token])
        nedostupna = reverse("deljeno", args=[secrets.token_urlsafe(16)])
        bez = Client().get(putanja)
        self.assertEqual(bez["Content-Language"], "sr")
        for opis, klijent, upit, zaglavlja, jezik in (
            ("bez kolacica", Client(), "?jezik=en", {}, "en"),
            ("kolacic sr", klijent_jezika("sr"), "?jezik=en", {}, "en"),
            ("kolacic en", klijent_jezika("en"), "?jezik=sr", {}, "sr"),
            ("zaglavlje en", Client(), "?jezik=sr", {"accept_language": "en-US"}, "sr"),
        ):
            for put, status in ((putanja, 200), (nedostupna, 404)):
                with self.subTest(opis=opis, status=status):
                    kolacici_pre = {ime: k.value for ime, k in klijent.cookies.items()}
                    odgovor = klijent.get(put + upit, headers=zaglavlja)
                    self.assertEqual(odgovor.status_code, status)
                    self.assertEqual(odgovor["Content-Language"], jezik)
                    self.assertEqual(jezik_strane(odgovor), jezik)
                    # Vazi samo za ovaj odgovor: bez Set-Cookie, kolacici klijenta isti.
                    self.assertEqual(len(odgovor.cookies), 0, odgovor.cookies)
                    self.assertEqual({ime: k.value for ime, k in klijent.cookies.items()}, kolacici_pre)
                    drugi = {"sr": "en", "en": "sr"}[jezik]
                    self.assertIn(f'id="jezik-link" class="btn jezik-dugme dugme-sporedno" href="?jezik={drugi}"',
                                  odgovor.content.decode("utf-8"))
        # Nepoznata vrednost se zanemaruje i ne ispisuje: odgovor je isti kao bez parametra.
        for vrednost in ("qzxjezik", "de", "EN", "en-us", "<b>"):
            with self.subTest(vrednost=vrednost):
                odgovor = Client().get(putanja, {"jezik": vrednost})
                self.assertEqual(odgovor.status_code, 200)
                self.assertEqual(odgovor.content, bez.content)
                self.assertEqual(odgovor["Content-Language"], "sr")
        self.assertNotIn(b"qzxjezik", Client().get(putanja + "?jezik=qzxjezik").content)
        self.assertNotIn(b"qzxjezik", Client().get(nedostupna + "?jezik=qzxjezik").content)


class PrevodTests(OsnovaPrikaza):
    """Nijedan neprevedeni tekst; mnozina; formati (plan 12.8, 12.9)."""

    def proveri_bez_cirilice(self, odgovor, opis):
        html = odgovor.content.decode("utf-8")
        with self.subTest(strana=opis):
            self.assertEqual(odgovor["Content-Language"], "en")
            self.assertEqual(jezik_strane(odgovor), "en")
            bez_izbora, izbora = SRPSKI_IZBOR.subn("", html)
            self.assertEqual(izbora, 1, "dugme ili link „Српски“ sa lang=\"sr\"")
            self.assertEqual(CIRILICA.findall(bez_izbora), [])
            # json_script pise ne-ASCII kao \uXXXX: svaki blok se proverava procitan.
            blokovi = json_blokovi(odgovor)
            if odgovor.status_code == 200:
                self.assertIn("tekstovi", blokovi)
            else:
                self.assertEqual(blokovi, {})  # 404 nema skriptu ni podatke
            for ime, sadrzaj in blokovi.items():
                self.assertEqual([t for t in svi_tekstovi(sadrzaj) if CIRILICA.search(t)], [], ime)

    def test_engleska_bez_cirilice(self):
        for rb, poeni in enumerate((100, 95, 90, 80, 70, 60, 50, 30, 20, 0)):
            upisi_red(f"Igrac {rb} Latinica", poeni)
        self.assertEqual({motor.oceni(r.poeni) for r in Rezultat.objects.all()}, set(OCENE_SR))
        klijent = klijent_jezika("en")
        self.postavi_igru("seme-engleska", klijent)
        self.proveri_bez_cirilice(klijent.get(reverse("pocetna")), "igra, prvi krug")
        self.odigraj_do(3, klijent=klijent)
        u_toku = klijent.get(reverse("pocetna"))
        self.assertIsNotNone(stanje_iz_html(u_toku)["poslednji"])
        self.proveri_bez_cirilice(u_toku, "igra u toku")

        seme = nadji_seme(strategija_najduza, lambda i: i.count(motor.TIHI_NEUSPEH) == 3)
        self.postavi_zavrsenu(seme, klijent, strategija_najduza)
        zavrsna = klijent.get(reverse("pocetna"))
        zavrsni = stanje_iz_html(zavrsna)["zavrsni"]
        self.assertEqual((len(zavrsni["tihe_greske"]), len(zavrsni["lekcije"])), (3, 5))
        self.assertEqual(len(rang_iz_html(zavrsna)["lista"]), 10)
        self.proveri_bez_cirilice(zavrsna, "zavrsni ekran sa rang listom")
        token = token_iz_url(self.podeli_json(klijent)["url"])
        self.assertEqual(self.sacuvaj("Latin Name", klijent).status_code, 200)
        deljena = self.deljena(token, klijent)
        self.assertEqual(deljena.status_code, 200)
        self.proveri_bez_cirilice(deljena, "deljena 200")
        nedostupna = self.deljena(secrets.token_urlsafe(16), klijent)
        self.assertEqual(nedostupna.status_code, 404)
        self.proveri_bez_cirilice(nedostupna, "deljena 404")
        # Kontrola: ista provera na srpskoj strani nalazi cirilicu.
        srpska = klijent_jezika("sr").get(reverse("pocetna")).content.decode("utf-8")
        self.assertGreater(len(CIRILICA.findall(SRPSKI_IZBOR.sub("", srpska))), 20)

    def test_tekstovi_en_bez_cirilice(self):
        with translation.override("sr"):
            srpski = tekstovi.za_skriptu()
        with translation.override("en"):
            engleski = tekstovi.za_skriptu()
        svi = list(svi_tekstovi(engleski))
        self.assertGreater(len(svi), 40)
        self.assertEqual([t for t in svi if CIRILICA.search(t)], [])
        # Isti oblik na oba jezika: svaka grupa ima iste kljuceve.
        self.assertEqual(set(engleski), set(srpski))
        for grupa, vrednost in srpski.items():
            if isinstance(vrednost, dict):
                with self.subTest(grupa=grupa):
                    self.assertEqual(set(engleski[grupa]), set(vrednost))
        # Kontrola: srpska mapa ima cirilicu, pa provera vidi tekst.
        self.assertTrue([t for t in svi_tekstovi(srpski) if CIRILICA.search(t)])

    def test_tekstovi_sr_latinica(self):
        def latinica(mapa):
            reci = set()
            for tekst in svi_tekstovi(mapa):
                reci.update(re.findall(r"[A-Za-z]+", MESTO_VREDNOSTI.sub("", tekst)))
            return reci

        with translation.override("sr"):
            srpski = tekstovi.za_skriptu()
            # Kljuc opcije (haiku, malo...) je vrednost polja, ne tekst na ekranu.
            opcije = [[o["naziv"], o["opis"]] for g in tekstovi.opcije(motor.javne_opcije()).values() for o in g]
        self.assertEqual(latinica(srpski) - DOZVOLJENA_LATINICA, set())
        self.assertEqual(latinica(opcije) - DOZVOLJENA_LATINICA, set())
        # Kontrola: provera vidi latinicu engleske mape.
        with translation.override("en"):
            self.assertIn("Round", latinica(tekstovi.za_skriptu()))

    def test_parametri_prevedeni(self):
        oznaceni = oznaceni_tekstovi()
        self.assertGreater(len(oznaceni), 60)
        for poreklo, tekst in oznaceni:
            with self.subTest(poreklo=poreklo):
                with translation.override("en"):
                    engleski = gettext(tekst)
                with translation.override("sr"):
                    srpski = gettext(tekst)
                self.assertNotEqual(engleski, tekst)
                self.assertEqual(CIRILICA.findall(engleski), [])
                self.assertEqual(srpski, tekst)
        # Nazivi modela i nivoa nisu oznaceni i isti su na oba jezika (MVP 6).
        for jezik in JEZICI:
            with translation.override(jezik):
                opcije = tekstovi.opcije(motor.javne_opcije())
            with self.subTest(jezik=jezik):
                self.assertEqual([o["naziv"] for o in opcije["model"]], ["Haiku", "Sonnet", "Opus"])
                self.assertEqual([o["naziv"] for o in opcije["nivo"]], ["low", "high", "max"])

    def test_mesta_za_vrednosti_ista(self):
        provereno = 0
        for jezik in JEZICI:
            _, stavke = procitaj_po(KATALOG / jezik / "LC_MESSAGES" / "django.po")
            for stavka in stavke:
                izvor = set(MESTO_VREDNOSTI.findall(stavka["msgid"]))
                if "msgid_plural" in stavka:
                    self.assertEqual(set(MESTO_VREDNOSTI.findall(stavka["msgid_plural"])), izvor, stavka["msgid"])
                for oblik in oblici(stavka):
                    if not oblik:
                        continue  # sr bez prevoda: vazi msgid
                    with self.subTest(jezik=jezik, msgid=stavka["msgid"][:40]):
                        self.assertEqual(set(MESTO_VREDNOSTI.findall(oblik)), izvor)
                        if izvor:
                            # Prevod se sklapa bez greske, kao u tekstovi.py i blocktranslate.
                            oblik % {ime: "x" for ime in izvor}
                            provereno += 1
        self.assertGreater(provereno, 10)
        # Isto i kroz pravi gettext: obrasci skripte na oba jezika nose ista mesta.
        for kljuc, obrazac in tekstovi.OBRASCI.items():
            with self.subTest(obrazac=kljuc):
                with translation.override("en"):
                    self.assertEqual(sorted(MESTO_VREDNOSTI.findall(gettext(obrazac))),
                                     sorted(MESTO_VREDNOSTI.findall(obrazac)))

    # Mnozina, n = 1, 2, 5, 21 (craft-i18n: srpski ima tri oblika, engleski dva).
    MNOZINA = {
        "sr": {
            "rang": {1: "1 најбољи сачувани резултат", 2: "2 најбоља сачувана резултата",
                     5: "5 најбољих сачуваних резултата", 21: "21 најбољи сачувани резултат"},
            "pomoc": {1: "Од 1 до 1 знака.", 2: "Од 1 до 2 знака.", 5: "Од 1 до 5 знакова.",
                      21: "Од 1 до 21 знака."},
            "dana": {1: "Линк за дељење важи 1 дан.", 2: "Линк за дељење важи 2 дана.",
                     5: "Линк за дељење важи 5 дана.", 21: "Линк за дељење важи 21 дан."},
            "van_liste": {1: "Резултат је сачуван, али није међу 1 најбољим.",
                          2: "Резултат је сачуван, али није међу 2 најбоља.",
                          5: "Резултат је сачуван, али није међу 5 најбољих.",
                          21: "Резултат је сачуван, али није међу 21 најбољим."},
            "ime": {n: f"Име мора имати од 1 до {n} {oblik}, без размака на почетку и крају и без невидљивих знакова."
                    for n, oblik in ((1, "знака"), (2, "знака"), (5, "знакова"), (21, "знака"))},
        },
        "en": {
            "rang": {1: "1 best saved result", 2: "2 best saved results", 5: "5 best saved results",
                     21: "21 best saved results"},
            "pomoc": {1: "From 1 to 1 character.", 2: "From 1 to 2 characters.", 5: "From 1 to 5 characters.",
                      21: "From 1 to 21 characters."},
            "dana": {1: "Share link valid for 1 day.", 2: "Share link valid for 2 days.",
                     5: "Share link valid for 5 days.", 21: "Share link valid for 21 days."},
            "van_liste": {n: f"The result is saved, but it is not in the top {n}." for n in (1, 2, 5, 21)},
            "ime": {n: f"The name must have 1 to {n} {oblik}, with no spaces at the start or end and no invisible characters."
                    for n, oblik in ((1, "character"), (2, "characters"), (5, "characters"), (21, "characters"))},
        },
    }

    def mnozina(self, jezik):
        rang = re.compile(r'<p class="rang-podnaslov">(.*?)</p>', re.S)
        pomoc = re.compile(r'<div id="rang-pomoc" class="rang-pomoc">(.*?)</div>', re.S)
        dana = re.compile(r'<p class="nedostupno-pomoc">(.*?)</p>', re.S)
        nedostupna = reverse("deljeno", args=[secrets.token_urlsafe(16)])
        dobijeno = {deo: {} for deo in self.MNOZINA[jezik]}
        for n in (1, 2, 5, 21):
            klijent = klijent_jezika(jezik)
            with mock.patch.dict(views.BROJEVI, {"rang_mesta": n, "ime_maks": n}):
                html = klijent.get(reverse("pocetna")).content.decode("utf-8")
            dobijeno["rang"][n] = rang.search(html).group(1).strip()
            dobijeno["pomoc"][n] = pomoc.search(html).group(1).strip()
            with mock.patch.object(p, "DELJENJE_DANA", n):
                odgovor = klijent.get(nedostupna)
            self.assertEqual(odgovor.status_code, 404)
            dobijeno["dana"][n] = dana.search(odgovor.content.decode("utf-8")).group(1).strip()
            with mock.patch.object(p, "RANG_MESTA", n), mock.patch.object(p, "IME_MAKS", n), \
                    translation.override(jezik):
                poruke = tekstovi.za_skriptu()["poruke"]
            dobijeno["van_liste"][n] = poruke["rangVanListe"]
            dobijeno["ime"][n] = poruke["neispravnoIme"]
        for deo, ocekivano in self.MNOZINA[jezik].items():
            with self.subTest(jezik=jezik, deo=deo):
                self.assertEqual(dobijeno[deo], ocekivano)

    def test_mnozina_sr(self):
        self.mnozina("sr")

    def test_mnozina_en(self):
        self.mnozina("en")

    def test_mnozina_na_pravim_brojevima(self):
        # Brojevi iz parametri: 10 mesta, 20 znakova, 30 dana.
        for jezik, delovi in (
            ("sr", ("10 најбољих сачуваних резултата", "Од 1 до 20 знакова.", "Линк за дељење важи 30 дана.")),
            ("en", ("10 best saved results", "From 1 to 20 characters.", "Share link valid for 30 days.")),
        ):
            with self.subTest(jezik=jezik):
                klijent = klijent_jezika(jezik)
                html = klijent.get(reverse("pocetna")).content.decode("utf-8")
                nedostupna = klijent.get(reverse("deljeno", args=[secrets.token_urlsafe(16)])).content.decode("utf-8")
                self.assertIn(delovi[0], html)
                self.assertIn(delovi[1], html)
                self.assertIn(delovi[2], nedostupna)

    def test_formati_svi_jezici(self):
        self.assertEqual(set(tekstovi.FORMATI), {kod for kod, _ in settings.LANGUAGES})
        ocekivano = {
            "sr": {"zarez": ",", "novac": "%(iznos)s $", "minuti": "%(iznos)s мин",
                   "procenat": "%(iznos)s %"},
            "en": {"zarez": ".", "novac": "$%(iznos)s", "minuti": "%(iznos)s min",
                   "procenat": "%(iznos)s%"},
        }
        datumi = {
            "sr": ["10.11.2026", "02.07.2026", "01.07.2026"],
            "en": ["2026-11-10", "2026-07-02", "2026-07-01"],
        }
        for jezik in JEZICI:
            with self.subTest(jezik=jezik), translation.override(jezik):
                self.assertEqual(set(tekstovi.FORMATI[jezik]), {"datum", "zarez", "novac", "minuti", "procenat"})
                self.assertEqual(tekstovi.za_skriptu()["format"], ocekivano[jezik])
                self.assertEqual(
                    [tekstovi.datum(t) for t in (utc(2026, 11, 9, 23, 30), utc(2026, 7, 1, 22, 30),
                                                 utc(2026, 7, 1, 21, 59))],
                    datumi[jezik],
                )

    def test_tekstovi_ne_zavise_od_stanja(self):
        seme = nadji_seme(strategija_najduza, lambda i: i.count(motor.TIHI_NEUSPEH) == 3)
        for jezik in JEZICI:
            klijenti = [klijent_jezika(jezik) for _ in range(3)]
            self.postavi_igru(f"seme-tekstovi-{jezik}", klijenti[0])
            self.postavi_igru(f"seme-tekstovi-{jezik}", klijenti[1])
            self.odigraj_do(4, klijent=klijenti[1])
            self.postavi_zavrsenu(seme, klijenti[2], strategija_najduza)
            sirovo = [TEKSTOVI_SCRIPT.search(k.get(reverse("pocetna")).content.decode("utf-8")).group(1)
                      for k in klijenti]
            with self.subTest(jezik=jezik):
                self.assertGreater(len(sirovo[0]), 1000)
                self.assertEqual(sirovo[1], sirovo[0])
                self.assertEqual(sirovo[2], sirovo[0])
        # Kontrola: mape dva jezika se razlikuju, pa poredjenje vidi tekst.
        self.assertNotEqual(tekstovi_iz_html(klijent_jezika("sr").get(reverse("pocetna"))),
                            tekstovi_iz_html(klijent_jezika("en").get(reverse("pocetna"))))


class KatalogTests(TestCase):
    """locale/{en,sr}: potpun engleski, srpska mnozina, .mo iz tekuceg .po (plan 12.8)."""

    def katalog(self, jezik):
        return procitaj_po(KATALOG / jezik / "LC_MESSAGES" / "django.po")

    def test_en_potpun(self):
        zaglavlje, stavke = self.katalog("en")
        self.assertIn("Plural-Forms: nplurals=2; plural=(n != 1);", zaglavlje)
        self.assertGreaterEqual(len(stavke), 100)
        self.assertGreaterEqual(len([s for s in stavke if "msgid_plural" in s]), 5)
        for stavka in stavke:
            with self.subTest(msgid=stavka["msgid"][:40]):
                self.assertNotIn("fuzzy", stavka["oznake"])
                prevodi = oblici(stavka)
                self.assertEqual(len(prevodi), 2 if "msgid_plural" in stavka else 1)
                for prevod in prevodi:
                    self.assertNotEqual(prevod.strip(), "")
                    self.assertEqual(CIRILICA.findall(prevod), [])
                    # blocktranslate ne escape-uje prevod: HTML u msgstr bi presao na stranu.
                    self.assertNotRegex(prevod, r"[<>]")

    def test_sr_samo_mnozina(self):
        zaglavlje, stavke = self.katalog("sr")
        self.assertIn(
            "Plural-Forms: nplurals=3; plural=(n%10==1 && n%100!=11 ? 0 : n%10>=2 && "
            "n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2);", zaglavlje
        )
        mnozine = [s for s in stavke if "msgid_plural" in s]
        self.assertGreaterEqual(len(mnozine), 5)
        for stavka in stavke:
            with self.subTest(msgid=stavka["msgid"][:40]):
                self.assertNotIn("fuzzy", stavka["oznake"])
                if "msgid_plural" in stavka:
                    prevodi = oblici(stavka)
                    self.assertEqual(len(prevodi), 3)
                    self.assertEqual([t for t in prevodi if not t.strip()], [])
                    self.assertEqual([t for t in prevodi if re.search(r"[A-Za-z]{2,}", MESTO_VREDNOSTI.sub("", t))], [])
                else:
                    # Srpski izvor vazi kao jeste: prevod je prazan ili isti kao msgid.
                    self.assertIn(stavka["msgstr"], ("", stavka["msgid"]))
        _, engleske = self.katalog("en")
        self.assertEqual({s["msgid"] for s in stavke}, {s["msgid"] for s in engleske})

    def test_mo_iz_tekuceg_po(self):
        for jezik in JEZICI:
            po = KATALOG / jezik / "LC_MESSAGES" / "django.po"
            mo = po.with_suffix(".mo")
            with self.subTest(jezik=jezik, provera="vreme"):
                self.assertTrue(mo.exists())
                self.assertGreaterEqual(mo.stat().st_mtime, po.stat().st_mtime)
        # Ponasanje: svaka stavka iz .po daje isti tekst kroz gettext (zastareo .mo ovde pada).
        _, engleske = self.katalog("en")
        _, srpske = self.katalog("sr")
        for jezik, stavke in (("en", engleske), ("sr", srpske)):
            with translation.override(jezik):
                for stavka in stavke:
                    with self.subTest(jezik=jezik, msgid=stavka["msgid"][:40]):
                        if "msgid_plural" in stavka:
                            # Prvi broj iz svakog oblika: en 1, 2; sr 1, 2, 5.
                            for n, ocekivano in zip((1, 2, 5), oblici(stavka)):
                                self.assertEqual(ngettext(stavka["msgid"], stavka["msgid_plural"], n), ocekivano)
                        else:
                            self.assertEqual(gettext(stavka["msgid"]), stavka["msgstr"] or stavka["msgid"])


class StaraSesijaTests(OsnovaPrikaza):
    """Zavrsena partija iz sesije pre kljuceva radi kroz sve prikaze (plan 12.4, motor.nadogradi)."""

    def test_stara_zavrsena_sesija(self):
        seme = nadji_seme(strategija_najduza, lambda i: i.count(motor.TIHI_NEUSPEH) >= 2)
        novo = odigraj_celu(seme, strategija_najduza)
        staro = staro_zavrseno(novo, sa_napomenom=True)
        self.postavi_igru(seme, stanje=staro)
        red_pre = Session.objects.get(pk=self.client.session.session_key).session_data
        for jezik in JEZICI:
            with self.subTest(jezik=jezik):
                self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = jezik
                strana = self.client.get(reverse("pocetna"))
                self.assertEqual(strana["Content-Language"], jezik)
                self.assertEqual(stanje_iz_html(strana), motor.javni_prikaz(novo))
        # GET ne upisuje sesiju (plan 12.4: upis samo tamo gde prikaz vec pise sesiju).
        self.assertEqual(Session.objects.get(pk=self.client.session.session_key).session_data, red_pre)
        self.assertEqual(self.stanje(), staro)
        odbijen = self.potez(8)
        self.assertEqual(odbijen.status_code, 409)
        self.assertEqual(json.loads(odbijen.content)["stanje"], motor.javni_prikaz(novo))

        token = token_iz_url(self.podeli_json()["url"])
        self.assertEqual(DeljeniRezultat.objects.get().zavrsni, motor.za_deljenje(novo))
        self.assertEqual(deljeno_iz_html(self.deljena(token, Client()))["zavrsni"], motor.javni_prikaz(novo)["zavrsni"])
        odgovor = self.sacuvaj("Пера")
        self.assertEqual(odgovor.status_code, 200, odgovor.content)
        self.assertEqual(Rezultat.objects.get().ocena, novo["rezultat"]["ocena"])
        self.assertEqual(json.loads(odgovor.content)["rang"]["lista"][0]["ocena"], novo["rezultat"]["ocena"])
        # Posle upisa sesija nosi kljuceve.
        sesija = self.stanje()
        self.assertEqual(sesija["rezultat"]["ocena"], novo["rezultat"]["ocena"])
        self.assertEqual(sesija["rezultat"]["lekcije"], novo["rezultat"]["lekcije"])
        self.assertEqual(sesija["rezultat"]["tihe_greske"], novo["rezultat"]["tihe_greske"])


def stari_snimak(snimak):
    """Snimak zavrsnog ekrana kakav je DeljeniRezultat cuvao pre 0004: tekst i napomena."""
    staro = copy_snimka(snimak)
    staro["ocena"] = OCENE_SR[staro["ocena"]]
    for greska in staro["tihe_greske"]:
        greska["zadatak"] = ZADACI_SR[greska["zadatak"]]
    staro["lekcije"] = [{"tekst": LEKCIJE_SR[l["oznaka"]], "odeljak": l["odeljak"]} for l in staro["lekcije"]]
    staro["napomena"] = NAPOMENA_SR
    return staro


def copy_snimka(snimak):
    return json.loads(json.dumps(snimak))


class MigracijaTekstaTests(TransactionTestCase):
    """0004_tekst_u_kljuceve i 0005 (plan 12.4): napred, nazad, neprepoznat tekst, CHECK posle 0005."""

    PRE = [("igra", "0003_deljenirezultat")]
    KLJUCEVI = [("igra", "0004_tekst_u_kljuceve")]
    CHECK = [("igra", "0005_rezultat_igra_ocena_kljuc")]

    def setUp(self):
        self.addCleanup(self.na_poslednju)
        self.migracija = importlib.import_module("igra.migrations.0004_tekst_u_kljuceve")

    def migriraj(self, cilj):
        izvrsilac = MigrationExecutor(connection)
        izvrsilac.migrate(cilj)
        izvrsilac.loader.build_graph()
        return izvrsilac.loader.project_state(cilj).apps

    def na_poslednju(self):
        # Redovi testa bi zaustavili povratak na poslednju migraciju; TransactionTestCase ih ionako brise.
        with connection.cursor() as kursor:
            kursor.execute('DELETE FROM "igra_rezultat"')
            kursor.execute('DELETE FROM "igra_deljenirezultat"')
        izvrsilac = MigrationExecutor(connection)
        izvrsilac.migrate(izvrsilac.loader.graph.leaf_nodes())

    def primenjene(self):
        return {ime for app, ime in MigrationRecorder(connection).applied_migrations() if app == "igra"}

    def snimci(self):
        stanje = odigraj_celu(nadji_seme(strategija_najduza, lambda i: i.count(motor.TIHI_NEUSPEH) == 3),
                              strategija_najduza)
        novi = motor.za_deljenje(stanje)
        self.assertEqual((len(novi["tihe_greske"]), len(novi["lekcije"])), (3, 5))
        return novi, stari_snimak(novi)

    def upisi(self, apps, ocene, snimci):
        Rezultat_ = apps.get_model("igra", "Rezultat")
        Deljeni = apps.get_model("igra", "DeljeniRezultat")
        sada = timezone.now()
        for rb, ocena in enumerate(ocene):
            Rezultat_.objects.create(ime=f"Играч {rb}", poeni=50, ocena=ocena, partija=f"migracija-{rb}")
        for rb, snimak in enumerate(snimci):
            Deljeni.objects.create(token=f"t{rb:021d}", partija=f"migracija-d-{rb}", zavrsni=snimak,
                                   nastao=sada, istice=sada + TRIDESET_DANA)

    def procitaj(self, apps):
        Rezultat_ = apps.get_model("igra", "Rezultat")
        Deljeni = apps.get_model("igra", "DeljeniRezultat")
        return (list(Rezultat_.objects.order_by("id").values_list("ocena", flat=True)),
                list(Deljeni.objects.order_by("id").values_list("zavrsni", flat=True)))

    def test_napred_i_nazad(self):
        novi, stari = self.snimci()
        apps = self.migriraj(self.PRE)
        self.upisi(apps, list(OCENE_SR.values()), [stari])
        pre = self.procitaj(apps)
        apps = self.migriraj(self.KLJUCEVI)
        self.assertEqual(self.procitaj(apps), (list(OCENE_SR), [novi]))
        self.assertNotIn("napomena", self.procitaj(apps)[1][0])
        apps = self.migriraj(self.PRE)
        self.assertEqual(self.procitaj(apps), pre)
        self.assertEqual(self.procitaj(apps)[1][0]["napomena"], NAPOMENA_SR)
        # Ponovo napred, pa CHECK: ista baza prolazi i 0005.
        apps = self.migriraj(self.CHECK)
        self.assertEqual(self.procitaj(apps), (list(OCENE_SR), [novi]))

    def test_vec_u_cilju_se_preskace(self):
        novi, stari = self.snimci()
        apps = self.migriraj(self.PRE)
        self.upisi(apps, ["pozar", "солидан"], [novi, stari])
        apps = self.migriraj(self.KLJUCEVI)
        self.assertEqual(self.procitaj(apps), (["pozar", "solidan"], [novi, novi]))
        # Nazad: vrednost koja je vec tekst ostaje.
        Rezultat_ = apps.get_model("igra", "Rezultat")
        Rezultat_.objects.create(ime="Текст", poeni=50, ocena="скуп учитељ", partija="migracija-tekst")
        apps = self.migriraj(self.PRE)
        self.assertEqual(self.procitaj(apps), (["пожар", "солидан", "скуп учитељ"], [stari, stari]))

    def test_neprepoznat_tekst_zaustavlja_i_ne_menja_nista(self):
        novi, stari = self.snimci()
        los_snimak = copy_snimka(stari)
        los_snimak["lekcije"][1]["tekst"] = "Непозната лекција."
        apps = self.migriraj(self.PRE)
        self.upisi(apps, ["одлично", "пожар"], [stari, los_snimak])
        pre = self.procitaj(apps)
        Rezultat_ = apps.get_model("igra", "Rezultat")
        Deljeni = apps.get_model("igra", "DeljeniRezultat")
        los_red = Rezultat_.objects.get(ocena="одлично")
        los_deljeni = Deljeni.objects.order_by("id").last()
        with self.assertRaises(self.migracija.NeprepoznatTekst) as greska:
            self.migriraj(self.KLJUCEVI)
        poruka = str(greska.exception)
        self.assertIn(f"Rezultat:{los_red.id}:'одлично'", poruka)
        self.assertIn(f"DeljeniRezultat:{los_deljeni.id}:", poruka)
        self.assertIn("Непозната лекција.", poruka)
        # Nista nije promenjeno, ni prepoznati redovi; 0004 nije zabelezena.
        apps = MigrationExecutor(connection).loader.project_state(self.PRE).apps
        self.assertEqual(self.procitaj(apps), pre)
        self.assertIn("0003_deljenirezultat", self.primenjene())
        self.assertNotIn("0004_tekst_u_kljuceve", self.primenjene())

    def test_0005_odbija_tekst(self):
        apps = self.migriraj(self.KLJUCEVI)
        Rezultat_ = apps.get_model("igra", "Rezultat")
        preskocen = Rezultat_.objects.create(ime="Текст", poeni=50, ocena="пожар", partija="migracija-0005")
        # Tekst koji je 0004 propustila zaustavlja 0005.
        with self.assertRaises(IntegrityError):
            self.migriraj(self.CHECK)
        self.assertNotIn("0005_rezultat_igra_ocena_kljuc", self.primenjene())
        Rezultat_.objects.filter(id=preskocen.id).delete()
        apps = self.migriraj(self.CHECK)
        Rezultat_ = apps.get_model("igra", "Rezultat")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Rezultat_.objects.create(ime="Текст", poeni=50, ocena="скуп учитељ", partija="migracija-0005-b")
        # Kontrola: kljuc prolazi.
        Rezultat_.objects.create(ime="Кључ", poeni=50, ocena="skup", partija="migracija-0005-c")
        self.assertEqual(Rezultat_.objects.count(), 1)


# Plan 13 (novo bodovanje), T-P. Ocekivani tekst i brojevi su prepisani iz plana 13.1 i 13.4, ne citaju se iz koda.
MINUS = "−"
BUDZET_KAZNE = {
    "sr": {kazna: f"Буџет је прекорачен за %(procenat)s ({MINUS}{kazna} поена)." for kazna in (10, 20, 30, 40, 50)},
    "en": {kazna: f"Budget exceeded by %(procenat)s ({MINUS}{kazna} points)." for kazna in (10, 20, 30, 40, 50)},
}
FORMAT_PROCENTA = {"sr": "%(iznos)s %", "en": "%(iznos)s%"}
OZNAKA_STARIH = {"sr": "старо бодовање", "en": "old scoring"}
LEGENDA_STARIH = {
    "sr": "Старо бодовање: резултат је бодован по ранијим правилима, са другачијим казнама за тиху грешку и буџет.",
    "en": "Old scoring: this result was scored under the earlier rules, with different penalties for silent errors "
          "and the budget.",
}
SABLON_OZNAKE = re.compile(r'<span class="rang-pravila" data-mesto="pravila" hidden>([^<]*)</span>')
LEGENDA_HTML = re.compile(r'<p id="rang-legenda" class="rang-legenda" hidden>([^<]*)</p>')
TEZINA_OSMOG = 3  # Bezbednosna revizija; tezine po krugu 1 1 1 2 3 3 2 3


def recenica_kazne(jezik, procenat, kazna):
    """Recenica koju skripta sastavlja iz budzetKazne i format.procenat, istim zamenama."""
    return BUDZET_KAZNE[jezik][kazna].replace(
        "%(procenat)s", FORMAT_PROCENTA[jezik].replace("%(iznos)s", str(procenat))
    )


def seme_uspesnog_osmog(izbor=OPUS_HIGH):
    sansa = motor.racun(TEZINA_OSMOG, izbor)["sansa"]
    return next(str(i) for i in range(1000) if motor.uspeh_kruga(str(i), 8, sansa))


def stanje_pred_osmi(seme, ukupna_cena, pravila=p.PRAVILA_TEKUCA, izbor=OPUS_HIGH):
    """Nezavrsena partija pred 8. krug, podesena da posle uspesnog 8. kruga ukupna cena bude tacno zadata.

    Krugovi 1-7 su uspeh bez troska; pravila=None daje sesiju bez kljuca (pre verzija).
    """
    stanje = motor.nova_igra(seme)
    stanje["krug"] = 8
    stanje["istorija"] = [
        {"krug": k, "izbori": izbori("haiku"), "cena": 0.0, "minuti": 0.0, "ishod": motor.USPEH} for k in range(1, 8)
    ]
    stanje["potroseno"] = ukupna_cena - motor.racun(TEZINA_OSMOG, izbor)["cena"]
    if pravila is None:
        del stanje["pravila"]
    else:
        stanje["pravila"] = pravila
    return stanje


class BodovanjePrikazTests(OsnovaPrikaza):
    """Plan 13.7 T-P: verzija pravila kroz prikaze, rang listu, deljenje i komandu."""

    def seme_jedna_tiha(self, posle=None):
        """sve_opus: 32,40 $ = 35 %, rok prekoracen (test_motor.PravilaTests). posle: drugo seme istih ishoda."""
        prvo = nadji_seme(sve_opus, lambda i: i == SEME_JEDNA_TIHA)
        if posle is None:
            return prvo
        return next(str(i) for i in range(int(posle) + 1, 20000)
                    if ishodi(odigraj_celu(str(i), sve_opus)) == SEME_JEDNA_TIHA)

    def zavrsni_iz_potez(self, odgovor):
        self.assertEqual(odgovor.status_code, 200, odgovor.content)
        return json.loads(odgovor.content)["zavrsni"]

    # --- rang lista ---

    def test_red_liste_tacno_sest_kljuceva_i_oznaka_po_verziji(self):
        upisi_red("Нови", 90, utc(2026, 11, 11, 9), pravila=2)
        upisi_red("Стари", 80, utc(2026, 11, 10, 9), pravila=1)
        lista = rang_iz_html(self.client.get(reverse("pocetna")))["lista"]
        self.assertEqual(len(lista), 2)
        for red in lista:
            with self.subTest(ime=red["ime"]):
                self.assertEqual(set(red), KLJUCEVI_REDA)
                # Pet polja reda i javna oznaka reda za prijavu imena (odluka 2026-11-12).
                self.assertEqual(len(red), 6)
        self.assertEqual([(r["ime"], r["stara_pravila"]) for r in lista], [("Нови", False), ("Стари", True)])
        # Bool, ne broj verzije (assertEqual bi pustio 0 i 1).
        self.assertIs(lista[0]["stara_pravila"], False)
        self.assertIs(lista[1]["stara_pravila"], True)

    def test_oznaka_i_legenda_u_sablonu_skrivene_na_oba_jezika(self):
        upisi_red("Стари", 80, pravila=1)
        for jezik in JEZICI:
            with self.subTest(jezik=jezik):
                html = klijent_jezika(jezik).get(reverse("pocetna")).content.decode("utf-8")
                # Server ih iscrta jednom i skrivene; prikazuje ih skripta (test_tok).
                self.assertEqual(SABLON_OZNAKE.findall(html), [OZNAKA_STARIH[jezik]])
                self.assertEqual(LEGENDA_HTML.findall(html), [LEGENDA_STARIH[jezik]])

    def test_sacuvaj_nove_partije_upisuje_2(self):
        stanje = self.postavi_zavrsenu("seme-bodovanje-novo")
        self.assertEqual(stanje["pravila"], 2)
        odgovor = self.sacuvaj("Нови")
        self.assertEqual(odgovor.status_code, 200, odgovor.content)
        self.assertEqual(Rezultat.objects.get().pravila, 2)
        self.assertIs(json.loads(odgovor.content)["rang"]["lista"][0]["stara_pravila"], False)

    def test_stara_zavrsena_sesija_cuva_se_kao_1(self):
        seme = self.seme_jedna_tiha()
        # Partija zavrsena pre isporuke: bodovana po verziji 1, sesija bez "pravila" i bez novih kljuceva.
        staro = bez_verzije(odigraj_celu(seme, sve_opus, pravila=1))
        self.assertEqual(staro["rezultat"]["poeni"], 25)
        self.postavi_igru(seme, stanje=staro)
        zavrsni = stanje_iz_html(self.client.get(reverse("pocetna")))["zavrsni"]
        self.assertTrue(zavrsni["budzet_prekoracen"])
        self.assertEqual((zavrsni["budzet_procenat"], zavrsni["kazna_budzet"], zavrsni["poeni"]), (None, None, 25))

        odgovor = self.sacuvaj("Стари")
        self.assertEqual(odgovor.status_code, 200, odgovor.content)
        red = Rezultat.objects.get()
        self.assertEqual((red.pravila, red.poeni), (1, 25))
        self.assertIs(json.loads(odgovor.content)["rang"]["lista"][0]["stara_pravila"], True)
        # Sacuvani poeni se ne preracunavaju, ni u sesiji.
        self.assertEqual(self.stanje()["rezultat"]["poeni"], 25)
        self.assertNotIn("kazna_budzet", self.stanje()["rezultat"])

    def test_stara_nezavrsena_sesija_kroz_potez_po_pravilima_1(self):
        seme = self.seme_jedna_tiha()
        self.postavi_igru(seme, stanje=bez_verzije(motor.nova_igra(seme)))
        self.assertNotIn("pravila", self.stanje())
        zavrsni = self.zavrsni_iz_potez(self.odigraj_do(8))
        # Pravila 1: 100 - 25 (tiha) - 30 (budzet) - 20 (rok); procenat se racuna i za staru partiju.
        self.assertEqual(
            (zavrsni["poeni"], zavrsni["budzet_procenat"], zavrsni["kazna_budzet"], zavrsni["ocena"]),
            (25, 35, 30, "pozar"),
        )
        self.assertEqual(self.stanje()["pravila"], 1)
        for jezik in JEZICI:
            with self.subTest(jezik=jezik):
                t = tekstovi_iz_html(klijent_jezika(jezik).get(reverse("pocetna")))
                sablon = t["budzetKazne"][str(zavrsni["kazna_budzet"])]
                procenat = t["format"]["procenat"].replace("%(iznos)s", str(zavrsni["budzet_procenat"]))
                self.assertEqual(sablon.replace("%(procenat)s", procenat), recenica_kazne(jezik, 35, 30))
        self.assertEqual(recenica_kazne("sr", 35, 30), "Буџет је прекорачен за 35 % (−30 поена).")

        # Ista partija sacuvana: red verzije 1, sa oznakom.
        self.assertEqual(self.sacuvaj("Стари").status_code, 200)
        self.assertEqual(Rezultat.objects.get().pravila, 1)

        # Nova partija istih ishoda (drugo seme: partija je jedinstvena) u drugom pregledacu: verzija 2, bez oznake.
        drugi = Client()
        drugo = self.seme_jedna_tiha(posle=seme)
        self.postavi_igru(drugo, klijent=drugi)
        zavrsni_novi = self.zavrsni_iz_potez(self.odigraj_do(8, klijent=drugi))
        # Pravila 2: 100 - 35 - 40 (35 % = 4 koraka) - 20.
        self.assertEqual((zavrsni_novi["poeni"], zavrsni_novi["budzet_procenat"], zavrsni_novi["kazna_budzet"]),
                         (5, 35, 40))
        self.assertEqual(self.sacuvaj("Нови", klijent=drugi).status_code, 200)
        lista = rang_iz_html(Client().get(reverse("pocetna")))["lista"]
        self.assertEqual([(r["ime"], r["poeni"], r["stara_pravila"]) for r in lista],
                         [("Стари", 25, True), ("Нови", 5, False)])
        self.assertEqual(dict(Rezultat.objects.values_list("ime", "pravila")), {"Стари": 1, "Нови": 2})

    # --- klijent ne zadaje verziju ---

    def test_potez_odbija_pravila_u_telu(self):
        self.postavi_igru("seme-pravila-telo")
        pre = self.stanje()
        telo = json.dumps({"krug": 1, "izbori": OPUS_HIGH, "pravila": 1})
        odgovor = self.sirovo(telo)
        self.assertEqual(odgovor.status_code, 400)
        self.assertEqual(json.loads(odgovor.content), {"greska": "neispravan_zahtev"})
        self.assertEqual(self.stanje(), pre)

    def test_pravila_iz_upita_se_ne_citaju(self):
        # Stara sesija ostaje 1 i kad klijent trazi 2; nova ostaje 2 i kad trazi 1.
        prvo = self.seme_jedna_tiha()
        for pocetno, trazeno, ocekivano, seme in ((None, 2, 1, prvo), (2, 1, 2, self.seme_jedna_tiha(posle=prvo))):
            with self.subTest(pocetno=pocetno):
                klijent = Client()
                stanje = motor.nova_igra(seme)
                if pocetno is None:
                    stanje = bez_verzije(stanje)
                self.postavi_igru(seme, klijent=klijent, stanje=stanje)
                for krug in KRUGOVI:
                    telo = json.dumps({"krug": krug, "izbori": OPUS_HIGH})
                    odgovor = klijent.post(f"{reverse('potez')}?pravila={trazeno}", data=telo, content_type=JSON_TIP)
                    self.assertEqual(odgovor.status_code, 200)
                self.assertEqual(json.loads(odgovor.content)["zavrsni"]["kazna_budzet"], {1: 30, 2: 40}[ocekivano])
                odgovor = klijent.post(f"{reverse('sacuvaj')}?pravila={trazeno}",
                                       data=json.dumps({"ime": f"Играч {ocekivano}"}), content_type=JSON_TIP)
                self.assertEqual(odgovor.status_code, 200, odgovor.content)
                self.assertEqual(Rezultat.objects.get(ime=f"Играч {ocekivano}").pravila, ocekivano)

    def test_sacuvaj_odbija_pravila_u_telu(self):
        self.postavi_zavrsenu("seme-pravila-cuvanje")
        for telo, tip in (
            (json.dumps({"ime": "Пера", "pravila": 1}), JSON_TIP),
            (json.dumps({"ime": "Пера", "pravila": 2}), JSON_TIP),
            ("ime=Пера&pravila=1", "application/x-www-form-urlencoded"),
        ):
            with self.subTest(telo=telo):
                odgovor = self.sacuvaj_sirovo(telo.encode("utf-8"), tip=tip)
                self.assertEqual(odgovor.status_code, 400)
                self.assertEqual(json.loads(odgovor.content), {"greska": "neispravan_zahtev"})
        self.assertEqual(Rezultat.objects.count(), 0)
        self.assertIsNone(motor.sacuvani_red(self.stanje()))

    def test_nova_ne_cita_pravila_iz_forme(self):
        self.client.post(reverse("nova"), data={"pravila": "1", "seme": "x"})
        self.assertEqual(self.stanje()["pravila"], 2)

    def test_javni_prikaz_ne_nosi_verziju(self):
        for stanje in (motor.nova_igra("seme-javni-v"), odigraj_celu("seme-javni-v", sve_opus)):
            with self.subTest(zavrsena=stanje["zavrsena"]):
                self.postavi_igru("seme-javni-v", stanje=stanje)
                strana = self.client.get(reverse("pocetna"))
                self.assertNotIn("pravila", set(svi_kljucevi(stanje_iz_html(strana))))
        # Kontrola: provera nalazi kljuc kad postoji.
        self.assertIn("pravila", set(svi_kljucevi({"a": [{"pravila": 2}]})))

    # --- granica 10 % kroz prikaz ---

    def test_granica_10_posto_kroz_potez(self):
        seme = seme_uspesnog_osmog()
        slucajevi = (
            ("tacno 10 %", 26.40, 2, 10, 10, 90),
            ("10,01 %", 26.4024, 2, 11, 20, 80),
            ("tacno 10 %, pravila 1", 26.40, 1, 10, 30, 70),
            ("10,01 %, sesija bez kljuca", 26.4024, None, 11, 30, 70),
        )
        for opis, cena, pravila, procenat, kazna, poeni in slucajevi:
            with self.subTest(opis=opis):
                klijent = Client()
                self.postavi_igru(seme, klijent=klijent, stanje=stanje_pred_osmi(seme, cena, pravila))
                zavrsni = self.zavrsni_iz_potez(self.potez(8, klijent=klijent))
                self.assertAlmostEqual(zavrsni["ukupna_cena"], cena, places=4)
                self.assertFalse(zavrsni["rok_prekoracen"])
                self.assertEqual(zavrsni["tihe_greske"], [])
                self.assertTrue(zavrsni["budzet_prekoracen"])
                self.assertEqual((zavrsni["budzet_procenat"], zavrsni["kazna_budzet"], zavrsni["poeni"]),
                                 (procenat, kazna, poeni))
                # Isto i na osvezenoj strani.
                self.assertEqual(stanje_iz_html(klijent.get(reverse("pocetna")))["zavrsni"], zavrsni)
        self.assertEqual(recenica_kazne("sr", 10, 10), "Буџет је прекорачен за 10 % (−10 поена).")
        self.assertEqual(recenica_kazne("sr", 11, 20), "Буџет је прекорачен за 11 % (−20 поена).")

    def test_tacno_budzet_bez_kazne(self):
        seme = seme_uspesnog_osmog()
        self.postavi_igru(seme, stanje=stanje_pred_osmi(seme, 24.0))
        zavrsni = self.zavrsni_iz_potez(self.potez(8))
        self.assertEqual((zavrsni["budzet_prekoracen"], zavrsni["budzet_procenat"], zavrsni["kazna_budzet"],
                          zavrsni["poeni"]), (False, 0, 0, 100))

    # --- tekst skripte ---

    def test_budzet_kazne_oba_jezika(self):
        for jezik in JEZICI:
            with self.subTest(jezik=jezik):
                t = tekstovi_iz_html(klijent_jezika(jezik).get(reverse("pocetna")))
                self.assertEqual(t["budzetKazne"], {str(k): v for k, v in BUDZET_KAZNE[jezik].items()})
                self.assertEqual(t["format"]["procenat"], FORMAT_PROCENTA[jezik])

    # --- deljenje ---

    def test_stari_snimak_deljeno_200_null(self):
        stanje = odigraj_celu(self.seme_jedna_tiha(), sve_opus, pravila=1)
        snimak = motor.za_deljenje(stanje)
        stari = {k: v for k, v in snimak.items() if k not in ("budzet_procenat", "kazna_budzet")}
        red = upisi_deljeno(stanje)
        DeljeniRezultat.objects.filter(id=red.id).update(zavrsni=stari)
        self.assertNotIn("kazna_budzet", DeljeniRezultat.objects.get(id=red.id).zavrsni)
        Rezultat.objects.create(ime="Стари", poeni=25, ocena="pozar", pravila=1, partija=red.partija)
        for jezik in JEZICI:
            with self.subTest(jezik=jezik):
                odgovor = klijent_jezika(jezik).get(reverse("deljeno", args=[red.token]))
                self.assertEqual(odgovor.status_code, 200)
                deljeni = deljeno_iz_html(odgovor)
                self.assertEqual(set(deljeni), KLJUCEVI_DELJENOG)
                self.assertEqual(set(deljeni["zavrsni"]), KLJUCEVI_ZAVRSNOG)
                self.assertTrue(deljeni["zavrsni"]["budzet_prekoracen"])
                self.assertIsNone(deljeni["zavrsni"]["budzet_procenat"])
                self.assertIsNone(deljeni["zavrsni"]["kazna_budzet"])
                self.assertEqual(deljeni["ime"], "Стари")
                html = odgovor.content.decode("utf-8")
                # Deljena strana nema oznaku ni legendu (plan 13.3), ni za red verzije 1.
                self.assertNotIn(OZNAKA_STARIH[jezik], html)
                self.assertNotIn("rang-legenda", html)
                self.assertNotIn("stara_pravila", html)
        # Kontrola: nov snimak iste partije nosi brojeve.
        self.assertEqual((snimak["budzet_procenat"], snimak["kazna_budzet"]), (35, 30))

    # --- komanda i model ---

    def test_komanda_rezultati_ispisuje_verziju(self):
        stari = upisi_red("Стари", 80, pravila=1)
        novi = upisi_red("Нови", 90, pravila=2)
        izlaz = StringIO()
        call_command("rezultati", stdout=izlaz)
        redovi = izlaz.getvalue().splitlines()
        self.assertEqual(len(redovi), 2)
        self.assertIn(f"id={novi.id} ", redovi[0])
        self.assertIn(" pravila=2 ", redovi[0])
        self.assertIn(f"id={stari.id} ", redovi[1])
        self.assertIn(" pravila=1 ", redovi[1])

    def test_model_trazi_poznatu_verziju(self):
        osnova = {"ime": "Пера", "poeni": 50, "ocena": "skup"}
        with self.assertRaises(ValidationError) as greska:
            Rezultat(**osnova, partija="bez-verzije").full_clean()
        self.assertIn("pravila", greska.exception.message_dict)
        for los in (0, 3):
            with self.subTest(pravila=los):
                with self.assertRaises(ValidationError):
                    Rezultat(**osnova, pravila=los, partija=f"los-{los}").full_clean()
                with self.assertRaises(IntegrityError), transaction.atomic():
                    Rezultat.objects.create(**osnova, pravila=los, partija=f"los-{los}")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Rezultat.objects.create(**osnova, partija="bez-verzije")
        # Necela verzija mimo int() polja (nalaz revizije 2026-11-11): tabela nije STRICT, pa bi je opseg iz
        # 0007 primio kao REAL. Sirov INSERT i izraz u update(); create bi 1.5 secao na 1.
        with self.assertRaisesMessage(IntegrityError, "igra_pravila_poznata"), transaction.atomic():
            with connection.cursor() as kursor:
                kursor.execute(
                    'INSERT INTO "igra_rezultat" (ime, poeni, ocena, pravila, sacuvan, partija) '
                    "VALUES ('Сирово', 50, 'skup', 1.5, '2026-11-11 10:00:00', 'sirovo-1.5')"
                )
        for rb, (opis, izraz) in enumerate((("Value(1.5)", Value(1.5)), ('F("pravila") + 0.5', F("pravila") + 0.5))):
            with self.subTest(update=opis):
                with self.assertRaisesMessage(IntegrityError, "igra_pravila_poznata"), transaction.atomic():
                    red = Rezultat.objects.create(**osnova, pravila=1, partija=f"izraz-{rb}")
                    Rezultat.objects.filter(id=red.id).update(pravila=izraz)
        for dobar in (1, 2):
            Rezultat(**osnova, pravila=dobar, partija=f"dobar-{dobar}").full_clean()
        self.assertEqual(Rezultat.objects.count(), 0)


class MigracijaPravilaTests(TransactionTestCase):
    """0006_rezultat_pravila (plan 13.7 T-P, 13.9), 0007_pravila_opseg i 0008_pravila_nabrajanje: napred, nazad,
    ponovo napred; samo test baza."""

    PRE = [("igra", "0005_rezultat_igra_ocena_kljuc")]
    POSLE = [("igra", "0006_rezultat_pravila")]
    OPSEG = [("igra", "0007_pravila_opseg")]
    NABRAJANJE = [("igra", "0008_pravila_nabrajanje")]
    PRE_KLJUCEVA = [("igra", "0003_deljenirezultat")]
    # Tacan tekst CHECK-a u semi SQLite-a posle 0006, 0007 i 0008.
    CHECK_0006 = 'CONSTRAINT "igra_pravila_poznata" CHECK ("pravila" IN (1, 2))'
    CHECK_0007 = 'CONSTRAINT "igra_pravila_poznata" CHECK (("pravila" >= 1 AND "pravila" <= 2))'
    CHECK_0008 = 'CONSTRAINT "igra_pravila_poznata" CHECK (("pravila" = 1 OR "pravila" = 2))'
    # Necele verzije (nalaz revizije 2026-11-11). Tabela nije STRICT: kolona INTEGER afiniteta cuva ih kao REAL;
    # '1.5' afinitet pretvara u 1.5. IN iz 0006 i nabrajanje iz 0008 ih odbijaju, opseg iz 0007 ne.
    NECELE = (
        ("INSERT 1.5", 1.5),
        ("INSERT '1.5'", "1.5"),
        ("INSERT 1.999999", 1.999999),
        ("update Value(1.5)", Value(1.5)),
        ('update F("pravila") + 0.5', F("pravila") + 0.5),
    )

    def setUp(self):
        # Zastita: test baza nikad nije db.sqlite3 projekta.
        ime = str(connection.settings_dict["NAME"])
        self.assertNotIn("db.sqlite3", ime)
        self.assertTrue(ime.startswith("file:memorydb") or ime == ":memory:", ime)
        self.addCleanup(self.na_poslednju)

    def migriraj(self, cilj):
        izvrsilac = MigrationExecutor(connection)
        izvrsilac.migrate(cilj)
        izvrsilac.loader.build_graph()
        return izvrsilac.loader.project_state(cilj).apps

    def na_poslednju(self, obrisi=True):
        if obrisi:
            with connection.cursor() as kursor:
                kursor.execute('DELETE FROM "igra_rezultat"')
                kursor.execute('DELETE FROM "igra_deljenirezultat"')
        izvrsilac = MigrationExecutor(connection)
        izvrsilac.migrate(izvrsilac.loader.graph.leaf_nodes())

    def kolone(self):
        # PRAGMA, ne introspection: u stanju 0006 Django parser kolacija pada (0007 to ispravlja).
        with connection.cursor() as kursor:
            kursor.execute('PRAGMA table_info("igra_rezultat")')
            return {red[1] for red in kursor.fetchall()}

    def sema(self):
        # CREATE TABLE iz sqlite_master; radi i u stanju 0006, gde introspekcija pada.
        with connection.cursor() as kursor:
            kursor.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'igra_rezultat'")
            sql = kursor.fetchone()[0]
        self.assertEqual(sql.count('"igra_pravila_poznata"'), 1, sql)
        return sql

    def introspekcija(self):
        with connection.cursor() as kursor:
            opis = connection.introspection.get_table_description(kursor, "igra_rezultat")
            ogranicenja = connection.introspection.get_constraints(kursor, "igra_rezultat")
        return {k.name for k in opis}, ogranicenja

    def upisi_verziju(self, apps, vrednost, partija):
        # Mimo int() polja: izraz kroz update() jednog ispravnog reda, sve ostalo sirovim INSERT-om.
        if hasattr(vrednost, "resolve_expression"):
            R = apps.get_model("igra", "Rezultat")
            red = R.objects.create(ime="Израз", poeni=50, ocena="skup", pravila=1, partija=partija)
            R.objects.filter(id=red.id).update(pravila=vrednost)
            return
        with connection.cursor() as kursor:
            kursor.execute(
                'INSERT INTO "igra_rezultat" (ime, poeni, ocena, pravila, sacuvan, partija) '
                "VALUES ('Сирово', 50, 'skup', %s, '2026-11-11 10:00:00', %s)",
                [vrednost, partija],
            )

    def upisane_verzije(self, prefiks):
        # Vrednost i tip kako ih SQLite cuva; zatim brise probne redove, da redovi() ostanu netaknuti.
        with connection.cursor() as kursor:
            kursor.execute(
                'SELECT pravila, typeof(pravila) FROM "igra_rezultat" WHERE partija LIKE %s ORDER BY id',
                [f"{prefiks}%"],
            )
            upisane = kursor.fetchall()
            kursor.execute('DELETE FROM "igra_rezultat" WHERE partija LIKE %s', [f"{prefiks}%"])
        return upisane

    def odbija_nepoznate(self, apps, necele=True):
        # necele=False samo u stanju 0007, ciji opseg ih propusta (vidi propusta_necele).
        R = apps.get_model("igra", "Rezultat")
        for verzija in (0, 3):
            with self.subTest(odbija=verzija):
                with self.assertRaisesMessage(IntegrityError, "igra_pravila_poznata"), transaction.atomic():
                    R.objects.create(ime="Лош", poeni=50, ocena="skup", pravila=verzija, partija=f"m7-los-{verzija}")
                with self.assertRaisesMessage(IntegrityError, "igra_pravila_poznata"), transaction.atomic():
                    self.upisi_verziju(apps, verzija, f"m-sirovo-{verzija}")
        # NULL ne odbija CHECK (NULL nije netacno), nego NOT NULL kolone. Poruka sa imenom kolone (qa 2026-11-11):
        # samo "NOT NULL" prolazi i kad je pravila nullable, a INSERT padne na drugoj NOT NULL koloni.
        with self.assertRaisesMessage(IntegrityError, "NOT NULL constraint failed: igra_rezultat.pravila"), transaction.atomic():
            self.upisi_verziju(apps, None, "m-sirovo-null")
        if necele:
            for rb, (opis, vrednost) in enumerate(self.NECELE):
                with self.subTest(odbija=opis):
                    with self.assertRaisesMessage(IntegrityError, "igra_pravila_poznata"), transaction.atomic():
                        self.upisi_verziju(apps, vrednost, f"m-necela-{rb}")
        self.assertEqual(self.upisane_verzije("m-"), [])

    def prihvata_poznate(self, apps):
        # '1' i '2.0' afinitet INTEGER pretvara u ceo broj pre provere, isto pod IN iz 0006.
        for rb, vrednost in enumerate((1, 2, "1", "2.0")):
            self.upisi_verziju(apps, vrednost, f"m-poznata-{rb}")
        self.assertEqual(self.upisane_verzije("m-poznata-"), [(1, "integer"), (2, "integer"), (1, "integer"), (2, "integer")])

    def propusta_necele(self, apps):
        # Kontrola za odbija_nepoznate: u stanju 0007 svaka putanja iz NECELE stvarno upisuje necelu verziju,
        # pa odbijanje u 0006 i 0008 dolazi od CHECK-a, ne od upisa koji ne radi.
        for rb, (_opis, vrednost) in enumerate(self.NECELE):
            self.upisi_verziju(apps, vrednost, f"m-necela-{rb}")
        self.assertEqual(
            self.upisane_verzije("m-necela-"),
            [(1.5, "real"), (1.5, "real"), (1.999999, "real"), (1.5, "real"), (1.5, "real")],
        )

    def redovi(self, apps):
        return list(
            apps.get_model("igra", "Rezultat").objects.order_by("id").values_list("id", "ime", "poeni", "ocena")
        )

    def verzije(self, apps):
        return list(apps.get_model("igra", "Rezultat").objects.order_by("id").values_list("pravila", flat=True))

    def test_napred_nazad_napred(self):
        apps = self.migriraj(self.PRE)
        self.assertNotIn("pravila", self.kolone())
        R = apps.get_model("igra", "Rezultat")
        for rb, (poeni, ocena) in enumerate(((90, "odlican"), (50, "skup"), (10, "pozar"))):
            R.objects.create(ime=f"Играч {rb}", poeni=poeni, ocena=ocena, partija=f"m6-{rb}")
        pre = self.redovi(apps)
        self.assertEqual(len(pre), 3)

        apps = self.migriraj(self.POSLE)
        self.assertIn("pravila", self.kolone())
        self.assertEqual(self.redovi(apps), pre)
        self.assertEqual(self.verzije(apps), [1, 1, 1])
        R = apps.get_model("igra", "Rezultat")
        # Bez default-a posle migracije: zaboravljen upis pada (preserve_default=False).
        self.assertFalse(R._meta.get_field("pravila").has_default())
        self.assertFalse(Rezultat._meta.get_field("pravila").has_default())
        for opis, vrednost in (("3", 3), ("0", 0), ("NULL", None)):
            with self.subTest(odbija=opis):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    R.objects.create(ime="Лош", poeni=50, ocena="skup", pravila=vrednost, partija=f"m6-los-{opis}")
        # Sirov INSERT bez kolone: baza nema DEFAULT, pa NOT NULL odbija.
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as kursor:
                kursor.execute(
                    'INSERT INTO "igra_rezultat" (ime, poeni, ocena, sacuvan, partija) '
                    "VALUES ('Сирово', 50, 'skup', '2026-11-11 10:00:00', 'm6-sirovo')"
                )
        novi = R.objects.create(ime="Нови", poeni=70, ocena="solidan", pravila=2, partija="m6-novi")
        self.assertEqual(self.verzije(apps), [1, 1, 1, 2])
        sa_novim = self.redovi(apps)

        # Nazad: kolona nestaje, ostalo netaknuto (i red verzije 2).
        apps = self.migriraj(self.PRE)
        self.assertNotIn("pravila", self.kolone())
        self.assertEqual(self.redovi(apps), sa_novim)

        # Ponovo napred: svi redovi 1, i nekadasnji red verzije 2 (ocekivano, plan 13.9).
        apps = self.migriraj(self.POSLE)
        self.assertEqual(self.redovi(apps), sa_novim)
        self.assertEqual(self.verzije(apps), [1, 1, 1, 1])
        self.assertEqual(apps.get_model("igra", "Rezultat").objects.get(id=novi.id).pravila, 1)

    # Nalaz qa 2026-11-11: u stanju 0006 Django introspekcija tabele pada (IndexError u sqlite3
    # introspection._get_column_collations). CHECK "pravila" IN (1, 2) je poslednji u CREATE TABLE; Django
    # sece tekst po ", " i poslednji komad "2" ostaje prazan posle column[1:]. Pada i get_constraints, pa i
    # inspectdb i operacija seme koja trazi imena ogranicenja. 0007 isti CHECK pise opsegom, 0008 nabrajanjem
    # sa OR; nijedan nema ", ".
    def test_introspekcija_tabele_posle_0008(self):
        # Baza testa je na poslednjoj migraciji.
        self.assertIn(self.CHECK_0008, self.sema())
        kolone, ogranicenja = self.introspekcija()
        self.assertEqual(kolone, self.kolone())
        self.assertIn("pravila", kolone)
        self.assertIn("igra_pravila_poznata", ogranicenja)
        self.assertTrue(ogranicenja["igra_pravila_poznata"]["check"])
        self.assertEqual(set(ogranicenja["igra_pravila_poznata"]["columns"]), {"pravila"})
        izlaz = StringIO()
        call_command("inspectdb", "igra_rezultat", stdout=izlaz)
        model = izlaz.getvalue()
        self.assertIn("class IgraRezultat(models.Model):", model)
        self.assertIn("    pravila = models.PositiveSmallIntegerField()", model)
        self.assertIn("db_table = 'igra_rezultat'", model)

    def test_0007_napred_nazad_napred(self):
        # Polazi od stanja prave baze pre 0007 (0006 primenjena), ovde sa redovima obe verzije.
        apps = self.migriraj(self.POSLE)
        self.assertIn(self.CHECK_0006, self.sema())
        R = apps.get_model("igra", "Rezultat")
        for rb, (poeni, ocena, verzija) in enumerate(((90, "odlican", 1), (50, "skup", 2), (10, "pozar", 1))):
            R.objects.create(ime=f"Играч {rb}", poeni=poeni, ocena=ocena, pravila=verzija, partija=f"m7-{rb}")
        pre = self.redovi(apps)
        self.assertEqual(len(pre), 3)
        self.assertEqual(self.verzije(apps), [1, 2, 1])

        # Napred: opseg umesto IN, redovi i verzije netaknuti, introspekcija radi, 0 i 3 odbijeni.
        # Necele prolaze opseg (nalaz revizije 2026-11-11); zatvara ih 0008.
        apps = self.migriraj(self.OPSEG)
        sql = self.sema()
        self.assertIn(self.CHECK_0007, sql)
        self.assertNotIn(self.CHECK_0006, sql)
        self.assertEqual((self.redovi(apps), self.verzije(apps)), (pre, [1, 2, 1]))
        self.assertIn("igra_pravila_poznata", self.introspekcija()[1])
        self.odbija_nepoznate(apps, necele=False)
        self.propusta_necele(apps)

        # Nazad: CHECK iz 0006, redovi i verzije netaknuti, i dalje samo 1 i 2, necele odbijene.
        apps = self.migriraj(self.POSLE)
        sql = self.sema()
        self.assertIn(self.CHECK_0006, sql)
        self.assertNotIn(self.CHECK_0007, sql)
        self.assertEqual((self.redovi(apps), self.verzije(apps)), (pre, [1, 2, 1]))
        self.odbija_nepoznate(apps)
        self.prihvata_poznate(apps)

        # Ponovo napred.
        apps = self.migriraj(self.OPSEG)
        self.assertIn(self.CHECK_0007, self.sema())
        self.assertEqual((self.redovi(apps), self.verzije(apps)), (pre, [1, 2, 1]))
        self.assertIn("igra_pravila_poznata", self.introspekcija()[1])

    def test_0008_napred_nazad_napred(self):
        # Polazi od stanja prave baze pre 0008 (0007 primenjena), ovde sa redovima obe verzije.
        apps = self.migriraj(self.OPSEG)
        self.assertIn(self.CHECK_0007, self.sema())
        R = apps.get_model("igra", "Rezultat")
        for rb, (poeni, ocena, verzija) in enumerate(((90, "odlican", 1), (50, "skup", 2), (10, "pozar", 1))):
            R.objects.create(ime=f"Играч {rb}", poeni=poeni, ocena=ocena, pravila=verzija, partija=f"m8-{rb}")
        pre = self.redovi(apps)
        self.assertEqual(len(pre), 3)
        self.assertEqual(self.verzije(apps), [1, 2, 1])

        # Red sa necelom verzijom (samo mimo aplikacije) zaustavlja 0008 na kopiji tabele; sve se vraca.
        self.upisi_verziju(apps, 1.5, "m8-necela")
        with self.assertRaisesMessage(IntegrityError, "igra_pravila_poznata"):
            self.migriraj(self.NABRAJANJE)
        self.assertIn(self.CHECK_0007, self.sema())
        self.assertEqual(self.upisane_verzije("m8-necela"), [(1.5, "real")])

        # Napred: nabrajanje umesto opsega, redovi i verzije netaknuti, introspekcija radi, necele odbijene.
        apps = self.migriraj(self.NABRAJANJE)
        sql = self.sema()
        self.assertIn(self.CHECK_0008, sql)
        self.assertNotIn(self.CHECK_0007, sql)
        self.assertEqual((self.redovi(apps), self.verzije(apps)), (pre, [1, 2, 1]))
        kolone, ogranicenja = self.introspekcija()
        self.assertEqual(kolone, self.kolone())
        self.assertEqual(set(ogranicenja["igra_pravila_poznata"]["columns"]), {"pravila"})
        self.odbija_nepoznate(apps)
        self.prihvata_poznate(apps)

        # Nazad: opseg iz 0007, redovi i verzije netaknuti; necele opet prolaze.
        apps = self.migriraj(self.OPSEG)
        sql = self.sema()
        self.assertIn(self.CHECK_0007, sql)
        self.assertNotIn(self.CHECK_0008, sql)
        self.assertEqual((self.redovi(apps), self.verzije(apps)), (pre, [1, 2, 1]))
        self.odbija_nepoznate(apps, necele=False)
        self.propusta_necele(apps)

        # Ponovo napred.
        apps = self.migriraj(self.NABRAJANJE)
        self.assertIn(self.CHECK_0008, self.sema())
        self.assertEqual((self.redovi(apps), self.verzije(apps)), (pre, [1, 2, 1]))
        self.assertIn("igra_pravila_poznata", self.introspekcija()[1])
        self.odbija_nepoznate(apps)

    def test_0004_nazad_sa_novim_kljucevima_snimka(self):
        stanje = odigraj_celu(nadji_seme(strategija_najduza, lambda i: i.count(motor.TIHI_NEUSPEH) == 3),
                              strategija_najduza)
        snimak = motor.za_deljenje(stanje)
        self.assertIsInstance(snimak["kazna_budzet"], int)
        self.assertIsInstance(snimak["budzet_procenat"], int)
        sada = timezone.now()
        red = DeljeniRezultat.objects.create(token="t" * 22, partija="m6-deljeni", zavrsni=snimak,
                                             nastao=sada, istice=sada + TRIDESET_DANA)

        apps = self.migriraj(self.PRE_KLJUCEVA)
        nazad = apps.get_model("igra", "DeljeniRezultat").objects.get(id=red.id).zavrsni
        # Tekst umesto kljuceva i napomena, a novi kljucevi ostaju netaknuti.
        self.assertEqual(nazad, stari_snimak(snimak))
        self.assertEqual((nazad["budzet_procenat"], nazad["kazna_budzet"]),
                         (snimak["budzet_procenat"], snimak["kazna_budzet"]))

        self.na_poslednju(obrisi=False)
        self.assertEqual(DeljeniRezultat.objects.get(id=red.id).zavrsni, snimak)
        odgovor = Client().get(reverse("deljeno", args=[red.token]))
        self.assertEqual(odgovor.status_code, 200)
        self.assertEqual(deljeno_iz_html(odgovor)["zavrsni"], motor.deljeni_prikaz(snimak))


# ---------------------------------------------------------------------------------------------------------
# Moderator (plan 14.8). Ocekivane vrednosti su prepisane iz plana 14 i prihvacenih odstupanja, ne citaju se
# iz koda. Brzi hes samo ovde: PBKDF2 bi svaku prijavu u testu usporio za stotine milisekundi.
# ---------------------------------------------------------------------------------------------------------

User = get_user_model()
BRZI_HES = ["django.contrib.auth.hashers.MD5PasswordHasher"]
LOZINKA = "Zelena-Reka-Tece-42"
LOZINKA2 = "Plavo-Nebo-Iznad-17"
LOZINKA3 = "Crveni-Most-Stoji-93"
PRIJAVA_PUTANJA = "/moderator/prijava/"
PORUKA_PRIJAVE = "Погрешно корисничко име или лозинка."
POGRESNA_LOZINKA_SR = "Погрешна лозинка."
ISTA_LOZINKA_SR = "Нова лозинка мора да се разликује од старе."
ISTA_LOZINKA_EN = "The new password must be different from the old one."
TEKST_403 = "Ову страну види само главни модератор."
NEDOZVOLJENO_SR = "Радња није дозвољена."
POSLEDNJI_GLAVNI_SR = "Мора остати бар један активан главни модератор."
ISTEKLO_SR = "Линк за ову партију више није доступан."
CSRF_U_FORMI = re.compile(rb'name="csrfmiddlewaretoken" value="[^"]+"')
# Iznad SQLite INTEGER: prikaz ga ne sme pretvoriti u 500.
VELIKI_ID = 2**63
NEPOSTOJECI_ID = 987654
RUTE_MODERATORA = {
    "moderator", "moderator_odjava", "moderator_rezultat", "moderator_link", "moderator_dnevnik",
    "moderator_lozinka", "moderator_nalozi", "moderator_nalozi_nalog",
    "moderator_izvoz_glavne", "moderator_izvoz_dana", "moderator_ostavi",
    "moderator_statistika",
}
RUTE_GLAVNOG = {"moderator_nalozi", "moderator_nalozi_nalog"}
KLJUCEVI_SNIMKA = {"ime", "poeni", "ocena", "datum"}
KLJUCEVI_ZAPISA = {"kada", "ko", "radnja", "nad", "snimak"}
XSS_IMENA = ("</script><b>x", "<svg onload=a()>")


def dozvola(kod):
    return Permission.objects.get(content_type__app_label="igra", codename=kod)


def obrisi_brojace():
    """Brojac neuspeha prijave je u bazi (PokusajPrijave); usred testa ga brise kao da je prozor istekao."""
    PokusajPrijave.objects.all().delete()


def napravi_moderatora(ime, glavni=False, mora_promeniti=False, lozinka=LOZINKA):
    """Moderator mimo servisa (priprema testa, bez zapisa u dnevniku)."""
    korisnik = User.objects.create_user(ime, password=lozinka)
    korisnik.user_permissions.add(dozvola("moderira"))
    if glavni:
        korisnik.user_permissions.add(dozvola("upravlja_nalozima"))
    NalogModeratora.objects.create(korisnik=korisnik, mora_promeniti=mora_promeniti)
    return korisnik


def napravi_korisnika_bez_dozvole(ime, lozinka=LOZINKA):
    return User.objects.create_user(ime, password=lozinka)


def bez_csrf(telo):
    # CSRF token u formi je maskiran po odgovoru (prihvaceno odstupanje).
    return CSRF_U_FORMI.sub(b"", telo)


def otisak_baze():
    """Sve sto moderatorska radnja moze da promeni: dnevnik, redovi, prijave imena, nalozi, lozinke, dozvole."""
    return (
        list(ZapisDnevnika.objects.order_by("id").values_list("id", "radnja")),
        list(Rezultat.objects.order_by("id").values_list("id", flat=True)),
        list(DeljeniRezultat.objects.order_by("id").values_list("id", flat=True)),
        list(PrijavaImena.objects.order_by("id").values_list("id", "rezultat_id")),
        list(User.objects.order_by("id").values_list("id", "username", "password", "is_active", "last_login")),
        sorted(User.user_permissions.through.objects.values_list("user_id", "permission__codename")),
        list(NalogModeratora.objects.order_by("pk").values_list("pk", "mora_promeniti")),
    )


def glavni_bez_moderira():
    """Pravilo 3 iz 14.5: id-jevi sa upravlja_nalozima bez moderira (mora biti prazno)."""
    glavni = set(dozvola("upravlja_nalozima").user_set.values_list("pk", flat=True))
    moderiraju = set(dozvola("moderira").user_set.values_list("pk", flat=True))
    return sorted(glavni - moderiraju)


def greske_polja(html, id_polja):
    """Poruke greske polja; greska se racuna samo ako polje ima .is-invalid i .invalid-feedback je SLEDECI brat."""
    polje = re.search(r'<input [^>]*\bid="%s"[^>]*>' % re.escape(id_polja), html)
    if polje is None:
        raise AssertionError(f"nema polja {id_polja}")
    if "is-invalid" not in polje.group(0):
        return []
    posle = re.match(
        r'\s*<div class="invalid-feedback" id="%s-greska">((?:<div>.*?</div>)+)</div>' % re.escape(id_polja),
        html[polje.end():], re.S,
    )
    if posle is None:
        raise AssertionError(f"{id_polja}: .is-invalid bez .invalid-feedback kao sledeceg brata")
    return [html_modul.unescape(poruka) for poruka in re.findall(r"<div>(.*?)</div>", posle.group(1), re.S)]


def poruke_greske(html):
    """Opste greske forme i poruke odbijanja (.mod-poruka-greska)."""
    return [
        html_modul.unescape(poruka)
        for poruka in re.findall(r'<p class="mod-poruka mod-poruka-greska" role="alert">(.*?)</p>', html, re.S)
    ]


def vidljiv_tekst(html):
    """Tekst koji korisnik vidi ili cuje: bez skripti, stilova i ikonica; uz aria-label."""
    bez = re.sub(r"<(script|style|svg|template)\b.*?</\1>", " ", html, flags=re.S)
    oznake = re.findall(r'aria-label="([^"]*)"', bez)
    tekst = re.sub(r"<[^>]+>", " ", bez)
    return html_modul.unescape(" ".join([tekst, *oznake]))


def lokacija(odgovor):
    return urllib.parse.urlsplit(odgovor["Location"]).path


@override_settings(PASSWORD_HASHERS=BRZI_HES)
class OsnovaModeratora(PomocPrikaza, TestCase):
    def setUp(self):
        super().setUp()
        obrisi_brojace()  # brojac neuspeha prijave je u bazi; TestCase ga i sam vraca posle testa
        self.addCleanup(obrisi_brojace)

    def prijavi(self, ime, lozinka=LOZINKA, klijent=None, **dodatno):
        klijent = klijent or self.client
        return klijent.post(reverse("moderator_prijava"), {"username": ime, "password": lozinka, **dodatno})

    def klijent_za(self, korisnik, lozinka=LOZINKA, klijent=None):
        klijent = klijent or Client()
        odgovor = self.prijavi(korisnik.get_username(), lozinka, klijent)
        self.assertEqual(odgovor.status_code, 302, odgovor.content[:400])
        return klijent

    def promeni(self, klijent, stara, nova, nova2=None):
        return klijent.post(
            reverse("moderator_lozinka"),
            {"old_password": stara, "new_password1": nova, "new_password2": nova2 or nova},
        )

    def radnja(self, klijent, nad, radnja, moja=LOZINKA, **polja):
        return klijent.post(
            reverse("moderator_nalozi_nalog", args=[nad.pk]), {"radnja": radnja, "moja_lozinka": moja, **polja}
        )

    def dodaj(self, klijent, ime, lozinka=LOZINKA2, lozinka2=None, glavni=False, moja=LOZINKA):
        podaci = {"ime": ime, "lozinka1": lozinka, "lozinka2": lozinka2 or lozinka, "moja_lozinka": moja}
        if glavni:
            podaci["glavni"] = "on"
        return klijent.post(reverse("moderator_nalozi"), podaci)

    def ima_pristup(self, klijent):
        """Prijavljen moderator bez obavezne promene: dnevnik je 200."""
        return klijent.get(reverse("moderator_dnevnik")).status_code == 200

    def assertNaPrijavu(self, odgovor):
        self.assertEqual(odgovor.status_code, 302)
        self.assertEqual(lokacija(odgovor), PRIJAVA_PUTANJA)

    def assertOdbijeno(self, funkcija, kod):
        with self.assertRaises(nalozi.Odbijeno) as greska:
            funkcija()
        self.assertEqual(greska.exception.kod, kod)

    def zapis(self):
        return ZapisDnevnika.objects.najnoviji().first()


def rute_moderatora():
    """Sve rute moderator* iz URLconf-a osim prijave, sa oznakom da li primaju id. Nova ruta ulazi sama."""
    return {
        obrazac.name: bool(obrazac.pattern.converters)
        for obrazac in get_resolver().url_patterns
        if obrazac.name and obrazac.name.startswith("moderator") and obrazac.name != "moderator_prijava"
    }


class ModeratorMatricaTests(OsnovaModeratora):
    def setUp(self):
        super().setUp()
        self.glavni = napravi_moderatora("Glavni", glavni=True)
        self.mod = napravi_moderatora("Mod")
        self.cilj = napravi_moderatora("CiljniNalog")
        self.rezultat = upisi_red("Резултат", 70)
        self.link = upisi_deljeno()
        # Rezultat sa prijavom imena: odbijen zahtev je ne sme obrisati (otisak_baze nosi i prijave).
        self.prijavljen = upisi_red("Пријављен", 60)
        upisi_prijavu(self.prijavljen)

    def adrese(self, ruta, sa_id):
        if not sa_id:
            return [(reverse(ruta), "bez")]
        postoji = {
            "moderator_rezultat": self.rezultat.id,
            "moderator_ostavi": self.rezultat.id,
            "moderator_link": self.link.id,
            "moderator_nalozi_nalog": self.cilj.pk,
        }[ruta]
        slucajevi = [(postoji, "postoji"), (NEPOSTOJECI_ID, "nema"), (VELIKI_ID, "veliki")]
        if ruta == "moderator_ostavi":
            slucajevi.append((self.prijavljen.id, "prijavljen"))
        return [(reverse(ruta, args=[broj]), slucaj) for broj, slucaj in slucajevi]

    def svi_zahtevi(self):
        for ruta, sa_id in sorted(rute_moderatora().items()):
            for adresa, slucaj in self.adrese(ruta, sa_id):
                for metoda in ("get", "post"):
                    yield ruta, adresa, slucaj, metoda

    @staticmethod
    def ocekivano(uloga, ruta, slucaj, metoda):
        """Kod za prijavljenog moderatora ili glavnog; None: zahtev se ovde ne salje (menja stanje)."""
        if ruta in RUTE_GLAVNOG and uloga == "moderator":
            return 403  # pre citanja id-a: i za nepostojeci
        if ruta == "moderator_odjava":
            return 405 if metoda == "get" else None
        if ruta == "moderator_ostavi":
            if metoda == "get":
                return 405  # samo POST; metoda se proverava pre citanja id-a
            if slucaj in ("nema", "veliki"):
                return 404
            # Bez prijava: preusmerenje "vec_reseno", nista se ne menja. Sa prijavom POST menja stanje: test_ostavi_*.
            return 302 if slucaj == "postoji" else None
        if slucaj in ("nema", "veliki"):
            return 404
        if ruta in ("moderator_rezultat", "moderator_link"):
            return 200 if metoda == "get" else None  # POST brise: test_brisanje_*
        if ruta in ("moderator_dnevnik", "moderator_izvoz_glavne", "moderator_izvoz_dana", "moderator_statistika"):
            return 200 if metoda == "get" else 405
        if ruta == "moderator_nalozi_nalog":
            return 200 if metoda == "get" else 400  # POST bez radnje
        return 200

    def test_rute_su_poznate(self):
        rute = rute_moderatora()
        self.assertEqual(set(rute), RUTE_MODERATORA)
        self.assertEqual({r for r, sa_id in rute.items() if sa_id},
                         {"moderator_rezultat", "moderator_ostavi", "moderator_link", "moderator_nalozi_nalog"})

    def test_matrica_ruta_odbijeni_302(self):
        igrac = Client()
        self.postavi_zavrsenu("seme-matrica-igrac", igrac)
        igra = igrac.session["igra"]
        bez_dozvole = Client()
        bez_dozvole.force_login(napravi_korisnika_bez_dozvole("BezDozvole"))
        # Dozvola bez NalogModeratora nije moderator.
        bez_naloga_korisnik = napravi_korisnika_bez_dozvole("BezNaloga")
        bez_naloga_korisnik.user_permissions.add(dozvola("moderira"), dozvola("upravlja_nalozima"))
        bez_naloga = Client()
        bez_naloga.force_login(bez_naloga_korisnik)
        # Superuser sa nalogom i obe dozvole: has_perm bi mu dao sve, uloga() nista.
        super_korisnik = User.objects.create_superuser("Super", password=LOZINKA)
        super_korisnik.user_permissions.add(dozvola("moderira"), dozvola("upravlja_nalozima"))
        NalogModeratora.objects.create(korisnik=super_korisnik, mora_promeniti=False)
        superuser = Client()
        superuser.force_login(super_korisnik)
        deaktiviran = self.klijent_za(napravi_moderatora("Deaktiviran", glavni=True))
        User.objects.filter(username="Deaktiviran").update(is_active=False)
        pre = otisak_baze()
        for opis, klijent in (("neprijavljen", Client()), ("igrac sa partijom", igrac),
                              ("bez dozvole", bez_dozvole), ("dozvola bez naloga", bez_naloga),
                              ("superuser", superuser), ("deaktiviran posle prijave", deaktiviran)):
            for ruta, adresa, slucaj, metoda in self.svi_zahtevi():
                with self.subTest(klijent=opis, adresa=adresa, metoda=metoda):
                    odgovor = getattr(klijent, metoda)(adresa)
                    self.assertNaPrijavu(odgovor)
                    self.assertEqual(urllib.parse.parse_qs(urllib.parse.urlsplit(odgovor["Location"]).query),
                                     {"next": [adresa]})
        self.assertEqual(otisak_baze(), pre)
        self.assertEqual(igrac.session["igra"], igra)

    def test_matrica_ruta_moderator_i_glavni(self):
        klijenti = {"moderator": self.klijent_za(self.mod), "glavni": self.klijent_za(self.glavni)}
        pre = otisak_baze()
        tela_403 = set()
        poslato = {"moderator": 0, "glavni": 0}
        for uloga, klijent in klijenti.items():
            for ruta, adresa, slucaj, metoda in self.svi_zahtevi():
                kod = self.ocekivano(uloga, ruta, slucaj, metoda)
                if kod is None:
                    continue
                poslato[uloga] += 1
                with self.subTest(uloga=uloga, adresa=adresa, metoda=metoda):
                    odgovor = getattr(klijent, metoda)(adresa)
                    self.assertEqual(odgovor.status_code, kod, odgovor.content[:300])
                    if kod == 404:
                        self.assertEqual(odgovor.content, b"")  # prazan 404, bez spiska ruta
                    if kod == 403:
                        # Forma jezika nosi next = trazena putanja (prihvaceno odstupanje).
                        tela_403.add(bez_csrf(odgovor.content).replace(adresa.encode(), b"PUTANJA"))
                        self.assertIn(TEKST_403, odgovor.content.decode("utf-8"))
                        self.assertNotIn(b"CiljniNalog", odgovor.content)
        self.assertGreater(poslato["moderator"], 20)
        self.assertEqual(len(tela_403), 1)
        self.assertEqual(otisak_baze(), pre)
        # Odjava je POST i odjavljuje: poslednja.
        for klijent in klijenti.values():
            self.assertNaPrijavu(klijent.post(reverse("moderator_odjava")))

    def test_stavka_moderatori_samo_glavnom(self):
        adresa = reverse("moderator_nalozi").encode()
        self.assertNotIn(adresa, self.klijent_za(self.mod).get(reverse("moderator")).content)
        self.assertIn(adresa, self.klijent_za(self.glavni).get(reverse("moderator")).content)

    def test_mora_promeniti_pre_403(self):
        for opis, korisnik in (("moderator", napravi_moderatora("Novajlija", mora_promeniti=True)),
                               ("glavni", napravi_moderatora("NoviGlavni", glavni=True, mora_promeniti=True))):
            klijent = self.klijent_za(korisnik)
            for ruta, adresa, slucaj, metoda in self.svi_zahtevi():
                if ruta == "moderator_odjava":
                    continue
                with self.subTest(uloga=opis, adresa=adresa, metoda=metoda):
                    odgovor = getattr(klijent, metoda)(adresa)
                    if ruta == "moderator_lozinka":
                        self.assertEqual(odgovor.status_code, 200)
                    else:
                        self.assertEqual(odgovor.status_code, 302)
                        self.assertEqual(odgovor["Location"], reverse("moderator_lozinka"))
            self.assertTrue(Rezultat.objects.filter(pk=self.rezultat.pk).exists())
            self.assertNaPrijavu(klijent.post(reverse("moderator_odjava")))
        # Servis ne pusti nalog sa obaveznom promenom ni mimo prikaza.
        self.assertOdbijeno(lambda: brisanje.obrisi_rezultate([self.rezultat.id], ko=User.objects.get(
            username="Novajlija")), "nema_prava")
        self.assertTrue(Rezultat.objects.filter(pk=self.rezultat.pk).exists())


class PrijavaModeratoraTests(OsnovaModeratora):
    def setUp(self):
        super().setUp()
        self.mod = napravi_moderatora("Mod")

    def test_prijava_cuva_igru(self):
        klijent = Client()
        self.postavi_igru("seme-prijava-cuva", klijent)
        self.assertEqual(klijent.get(reverse("moderator_prijava")).status_code, 200)
        igra = klijent.session["igra"]
        kljuc = klijent.session.session_key
        csrf = klijent.cookies[settings.CSRF_COOKIE_NAME].value
        odgovor = self.prijavi("Mod", klijent=klijent)
        self.assertEqual(odgovor.status_code, 302)
        self.assertEqual(odgovor["Location"], reverse("moderator"))
        sesija = klijent.session
        self.assertEqual(sesija["igra"], igra)
        self.assertNotEqual(sesija.session_key, kljuc)  # cycle_key
        self.assertFalse(Session.objects.filter(session_key=kljuc).exists())
        self.assertNotEqual(klijent.cookies[settings.CSRF_COOKIE_NAME].value, csrf)  # rotate_token
        self.assertEqual(sesija.get_expiry_age(), settings.MODERATOR_SESIJA_SEKUNDI)
        self.assertEqual(settings.MODERATOR_SESIJA_SEKUNDI, 8 * 3600)
        # Partija igra dalje u istoj sesiji.
        self.assertEqual(self.potez(1, klijent=klijent).status_code, 200)
        self.assertTrue(self.ima_pristup(klijent))

    def test_isti_odgovor_za_sve_neuspehe(self):
        neaktivan = napravi_moderatora("Neaktivan")
        User.objects.filter(pk=neaktivan.pk).update(is_active=False)
        napravi_korisnika_bez_dozvole("BezDozvole")
        bez_naloga = napravi_korisnika_bez_dozvole("BezNaloga")
        bez_naloga.user_permissions.add(dozvola("moderira"))
        super_korisnik = User.objects.create_superuser("Super", password=LOZINKA)
        NalogModeratora.objects.create(korisnik=super_korisnik, mora_promeniti=False)
        slucajevi = (
            ("pogresna lozinka", "Mod", "pogresna-lozinka-1"),
            ("nepostojece ime", "NePostoji", LOZINKA),
            ("neaktivan", "Neaktivan", LOZINKA),
            ("bez dozvole", "BezDozvole", LOZINKA),
            ("dozvola bez naloga", "BezNaloga", LOZINKA),
            ("superuser", "Super", LOZINKA),
        )
        tela = set()
        for opis, ime, lozinka in slucajevi:
            with self.subTest(opis):
                klijent = Client()
                odgovor = self.prijavi(ime, lozinka, klijent)
                self.assertEqual(odgovor.status_code, 200)
                self.assertNotIn(SESSION_KEY, klijent.session)
                html = odgovor.content.decode("utf-8")
                self.assertEqual(poruke_greske(html), [PORUKA_PRIJAVE])
                self.assertNotIn(lozinka, html)  # lozinka se ne vraca u polje
                tela.add(bez_csrf(odgovor.content).replace(ime.encode(), b"IME"))
        self.assertEqual(len(tela), 1)

    def test_next_van_sajta_ignorisan(self):
        for sledeca in ("https://zlo.example/", "//zlo.example/", "http://testserver@zlo.example/",
                        "javascript:alert(1)", "/\\zlo.example/"):
            with self.subTest(next=sledeca):
                obrisi_brojace()
                klijent = Client()
                strana = klijent.get(reverse("moderator_prijava"), {"next": sledeca})
                self.assertEqual(strana.context["next"], "")
                # Forma prijave ne nosi tudji next (forma jezika nosi celu putanju; set_language je proverava).
                forma = strana.content.split(b'class="mod-forma"', 1)[1]
                self.assertNotIn(b'name="next"', forma)
                odgovor = self.prijavi("Mod", klijent=klijent, next=sledeca)
                self.assertEqual(odgovor.status_code, 302)
                self.assertEqual(odgovor["Location"], reverse("moderator"))
        # Kontrola: unutrasnji next se postuje.
        klijent = Client()
        odbijen = klijent.get(reverse("moderator_dnevnik"))
        self.assertEqual(odbijen["Location"], PRIJAVA_PUTANJA + "?next=/moderator/dnevnik/")
        strana = klijent.get(odbijen["Location"])
        self.assertIn(b'name="next" value="/moderator/dnevnik/"', strana.content)
        odgovor = self.prijavi("Mod", klijent=klijent, next="/moderator/dnevnik/")
        self.assertEqual(odgovor["Location"], "/moderator/dnevnik/")

    def test_next_koji_nije_putanja(self):
        # Revizija 2026-11-11: redirect(next) je "foo" uzimao kao ime rute, pa je uspesna prijava davala
        # NoReverseMatch (500), a ime postojece rute vodilo na tu rutu. Prihvata se samo putanja ("/...").
        for sledeca in ("foo", "moderator_nalozi", "moderator_nalozi_nalog", "pocetna", "?x=1", "zlo.example",
                        "moderator/dnevnik/", "./dnevnik/", " /moderator/dnevnik/"):
            with self.subTest(next=sledeca):
                klijent = Client()
                strana = klijent.get(reverse("moderator_prijava"), {"next": sledeca})
                self.assertEqual(strana.context["next"], "")
                odgovor = self.prijavi("Mod", klijent=klijent, next=sledeca)
                self.assertEqual(odgovor.status_code, 302)
                self.assertEqual(odgovor["Location"], reverse("moderator"))
                self.assertTrue(self.ima_pristup(klijent))
        # Kontrola: putanja sa upitom ostaje kakva jeste (HttpResponseRedirect, ne reverse).
        odgovor = self.prijavi("Mod", klijent=Client(), next="/moderator/?poruka=obrisano")
        self.assertEqual(odgovor["Location"], "/moderator/?poruka=obrisano")


@override_settings(DEBUG=True, PASSWORD_HASHERS=BRZI_HES)
class LozinkaNaTehnickojStraniTests(OsnovaModeratora):
    OZNAKA_KVARA = "ubaceni-kvar-moderator-5d1e"
    TAJNA = "Tajna-Nova-Lozinka-8x7"

    def setUp(self):
        super().setUp()
        self.glavni = napravi_moderatora("Glavni", glavni=True)
        self.mod = napravi_moderatora("Mod")
        self.neaktivan = napravi_moderatora("Neaktivan")
        User.objects.filter(pk=self.neaktivan.pk).update(is_active=False)

    def kvar(self, cilj, adresa, podaci, prijavljen=True):
        klijent = Client(raise_request_exception=False)
        if prijavljen:
            self.klijent_za(self.glavni, klijent=klijent)
        with mock.patch(cilj, side_effect=RuntimeError(self.OZNAKA_KVARA)):
            odgovor = klijent.post(adresa, podaci)
        self.assertEqual(odgovor.status_code, 500)
        telo = odgovor.content.decode("utf-8")
        self.assertIn(self.OZNAKA_KVARA, telo)
        return telo

    def slucajevi(self):
        nalog = reverse("moderator_nalozi_nalog", args=[self.mod.pk])
        neaktivan = reverse("moderator_nalozi_nalog", args=[self.neaktivan.pk])
        nove = {"lozinka1": self.TAJNA, "lozinka2": self.TAJNA, "moja_lozinka": LOZINKA}
        return (
            ("prijava", "igra.forme.rezervisi_pokusaj", reverse("moderator_prijava"),
             {"username": "Glavni", "password": LOZINKA}, False),
            ("dodavanje", "igra.forme.DodajForma", reverse("moderator_nalozi"),
             {"ime": "Novi", **nove}, True),
            ("aktiviranje", "igra.nalozi.aktiviraj", neaktivan, {"radnja": "aktiviraj", **nove}, True),
            ("postavljanje", "igra.nalozi.postavi_lozinku", nalog, {"radnja": "lozinka", **nove}, True),
            ("promena", "igra.nalozi.promeni_svoju", reverse("moderator_lozinka"),
             {"old_password": LOZINKA, "new_password1": self.TAJNA, "new_password2": self.TAJNA}, True),
        )

    def test_lozinka_nije_na_tehnickoj_strani(self):
        # Kao u settings.py (DEBUG = True): Django SafeExceptionReporterFilter.is_active tada vraca False, pa bez
        # FilterBezPromenljivih.is_active sensitive_post_parameters ne skriva nista (qa i security, 2026-11-11).
        # Test runner postavlja DEBUG = False, pa bez override_settings ovaj test ne bi nista dokazao.
        self.assertTrue(settings.DEBUG)
        for opis, cilj, adresa, podaci, prijavljen in self.slucajevi():
            with self.subTest(opis):
                telo = self.kvar(cilj, adresa, podaci, prijavljen)
                self.assertNotIn(LOZINKA, telo)
                self.assertNotIn(self.TAJNA, telo)

    def test_kontrola_bez_filtera_lozinka_se_vidi(self):
        # Dokaz da bi provera nasla lozinku: bez sensitive_post_parameters POST ide na stranu.
        with mock.patch(
            "orkestrator.greske.FilterBezPromenljivih.get_post_parameters", lambda self, request: request.POST
        ):
            for opis, cilj, adresa, podaci, prijavljen in self.slucajevi():
                with self.subTest(opis):
                    telo = self.kvar(cilj, adresa, podaci, prijavljen)
                    self.assertIn(LOZINKA if opis == "prijava" else self.TAJNA, telo)


class OgranicenjePrijaveTests(OsnovaModeratora):
    def setUp(self):
        super().setUp()
        self.mod = napravi_moderatora("Mod")

    def neuspesi(self, ime, broj):
        for redni in range(broj):
            odgovor = self.prijavi(ime, f"pogresna-{redni}", Client())
            self.assertEqual(odgovor.status_code, 200)
            self.assertIsNone(odgovor.context["blokirano"])

    def assertBlokirano(self, odgovor, minuta=15):
        self.assertEqual(odgovor.status_code, 200)
        self.assertEqual(odgovor.context["blokirano"], minuta)
        oblik = "минут" if minuta % 10 == 1 and minuta % 100 != 11 else "минута"
        poruka = f"Превише неуспешних покушаја. Покушајте поново за {minuta} {oblik}."
        self.assertIn(poruka, poruke_greske(odgovor.content.decode("utf-8")))

    def test_cetiri_neuspeha_ne_blokiraju(self):
        self.neuspesi("Mod", settings.PRIJAVA_POKUSAJA - 1)
        self.assertEqual(self.prijavi("Mod", klijent=Client()).status_code, 302)

    def test_peti_neuspeh_blokira_i_ispravnu(self):
        self.assertEqual(settings.PRIJAVA_POKUSAJA, 5)
        self.neuspesi("Mod", 5)
        pre = User.objects.get(pk=self.mod.pk).last_login
        klijent = Client()
        # Isto ime drugim slovima, ispravna lozinka.
        self.assertBlokirano(self.prijavi("mod", klijent=klijent))
        self.assertNotIn(SESSION_KEY, klijent.session)
        self.assertEqual(User.objects.get(pk=self.mod.pk).last_login, pre)  # authenticate nije pozvan

    def test_blokada_i_za_nepostojece_ime(self):
        self.neuspesi("NePostoji", 5)
        self.assertBlokirano(self.prijavi("NePostoji", klijent=Client()))
        # Drugo ime nije blokirano.
        self.assertEqual(self.prijavi("Mod", klijent=Client()).status_code, 302)

    def test_blokada_istice(self):
        self.assertEqual(settings.PRIJAVA_BLOKADA_SEKUNDI, 900)
        self.neuspesi("Mod", 5)
        sada = time.time()
        with mock.patch("time.time", return_value=sada + 841):
            self.assertBlokirano(self.prijavi("Mod", klijent=Client()), minuta=1)
        with mock.patch("time.time", return_value=sada + 901):
            self.assertEqual(self.prijavi("Mod", klijent=Client()).status_code, 302)

    def test_blokada_tece_od_poslednjeg_neuspeha(self):
        # Jedan sat za sve: forme zovu time.time() kroz modul time u trenutku poziva i taj trenutak upisuju u bazu
        # (PokusajPrijave.istice), pa patch "time.time" pomera i istek reda i poruku "za N minuta". Bez sleep-a:
        # test je deterministican i traje koliko i ostali.
        self.assertEqual((settings.PRIJAVA_POKUSAJA, settings.PRIJAVA_BLOKADA_SEKUNDI), (5, 900))
        pocetak = time.time()
        sat = [pocetak]
        with mock.patch("time.time", new=lambda: sat[0]):
            self.neuspesi("Mod", 4)
            sat[0] = pocetak + 600
            self.neuspesi("Mod", 1)  # peti neuspeh, 10 minuta posle prvog
            # Rok tece od petog (15 minuta), ne od prvog (5): proverava istice.
            self.assertBlokirano(self.prijavi("Mod", klijent=Client()))
            # 1441 s od prvog: red prvog roka bi istekao; drzi ga istice upisan posle petog.
            sat[0] = pocetak + 600 + 841
            self.assertBlokirano(self.prijavi("Mod", klijent=Client()), minuta=1)
            # Blokirani pokusaji rok ne pomeraju: 901 s posle petog prijava prolazi.
            sat[0] = pocetak + 600 + 901
            self.assertEqual(self.prijavi("Mod", klijent=Client()).status_code, 302)

    def test_uspeh_brise_brojac(self):
        self.neuspesi("Mod", 4)
        self.assertEqual(self.prijavi("Mod", klijent=Client()).status_code, 302)
        self.neuspesi("Mod", 4)
        self.assertEqual(self.prijavi("Mod", klijent=Client()).status_code, 302)

    def test_pogresna_potvrda_lozinkom_broji(self):
        glavni = napravi_moderatora("Glavni", glavni=True)
        klijent = self.klijent_za(glavni)
        pre = otisak_baze()
        for redni in range(5):
            odgovor = self.dodaj(klijent, f"Novi{redni}", moja="pogresna")
            self.assertEqual(greske_polja(odgovor.content.decode("utf-8"), "moja_lozinka"),
                             [POGRESNA_LOZINKA_SR])
        # Sesta potvrda, i ispravna, je blokirana; prijava istog imena takodje.
        odgovor = self.dodaj(klijent, "NoviSesti")
        self.assertEqual(greske_polja(odgovor.content.decode("utf-8"), "moja_lozinka"),
                         ["Превише неуспешних покушаја. Покушајте поново за 15 минута."])
        self.assertEqual(otisak_baze(), pre)
        self.assertBlokirano(self.prijavi("Glavni", klijent=Client()))

    def test_pogresna_stara_lozinka_broji(self):
        klijent = self.klijent_za(self.mod)
        for _ in range(5):
            odgovor = self.promeni(klijent, "pogresna", LOZINKA2)
            self.assertEqual(odgovor.status_code, 200)
            self.assertEqual(greske_polja(odgovor.content.decode("utf-8"), "old_password"),
                             [POGRESNA_LOZINKA_SR])
        self.assertBlokirano(self.prijavi("Mod", klijent=Client()))
        self.assertTrue(User.objects.get(pk=self.mod.pk).check_password(LOZINKA))

    # Revizija 2026-11-11: provera blokade pre authenticate i brojac get pa set posle nisu bili atomicni, pa je
    # od 40 istovremenih pokusaja proveru proslo 38. Pokusaj se sada rezervise atomicno, pre provere.

    @staticmethod
    def istovremeno(broj, posao):
        """broj niti krece zajedno; vraca ishod svake.

        Brojac je u bazi, a test baza je SQLite u memoriji: druga veza ne sme da pise dok test drzi svoju
        transakciju. Zato niti dele vezu testa (kao live server), a naredbe idu jedna po jedna, kao pisci u SQLite
        (jedna veza Python-ovog sqlite3 ne podnosi istovremene naredbe). Izmedju dve naredbe niti se smenjuju, pa
        brojac koji cita pa upisuje (dve naredbe) ovde sigurno propusta.
        """
        veza = connections[DEFAULT_DB_ALIAS]
        brava = threading.Lock()
        prava_naredba = CursorWrapper.execute

        def naredba(kursor, *argumenti, **opcije):
            with brava:
                vrednost = prava_naredba(kursor, *argumenti, **opcije)
            time.sleep(0.02)  # van brave: posle svake naredbe druge niti stizu na red
            return vrednost

        prepreka = threading.Barrier(broj)
        ishodi = [None] * broj

        def nit(redni):
            connections[DEFAULT_DB_ALIAS] = veza
            prepreka.wait()
            ishodi[redni] = posao(redni)

        niti = [threading.Thread(target=nit, args=(redni,)) for redni in range(broj)]
        veza.inc_thread_sharing()
        try:
            with mock.patch.object(CursorWrapper, "execute", naredba):
                for jedna in niti:
                    jedna.start()
                for jedna in niti:
                    jedna.join()
        finally:
            veza.dec_thread_sharing()
        return ishodi

    @staticmethod
    def sporo(funkcija):
        """funkcija, pa kratko cekanje: kao PBKDF2 (pola sekunde), pa su istovremeni zahtevi zaista u preklopu."""

        def omotac(*argumenti, **opcije):
            vrednost = funkcija(*argumenti, **opcije)
            time.sleep(0.02)
            return vrednost

        return omotac

    def test_istovremene_prijave_najvise_pet_provera(self):
        provere = []

        def authenticate(request=None, **podaci):
            provere.append(podaci["username"])
            return None  # pogresna lozinka

        def pokusaj(redni):
            forma = forme.PrijavaForma(None, data={"username": "Mod", "password": f"pogadjam-{redni}"})
            return forma.is_valid(), forma.blokirano

        with mock.patch("django.contrib.auth.forms.authenticate", self.sporo(authenticate)):
            ishodi = self.istovremeno(40, pokusaj)
        self.assertEqual(len(provere), settings.PRIJAVA_POKUSAJA)
        self.assertEqual((ishodi.count((False, None)), ishodi.count((False, 15))), (5, 35))
        # Posle talasa ni ispravna lozinka ne prolazi.
        self.assertBlokirano(self.prijavi("Mod", klijent=Client()))

    def test_istovremene_potvrde_najvise_pet_provera(self):
        # Isti brojac za potvrdu sopstvenom lozinkom i za staru lozinku pri promeni (_proveri_sopstvenu).
        provere = []
        prava_provera = forme.check_password

        def provera(lozinka, hes):
            provere.append(lozinka)
            return prava_provera(lozinka, hes)

        def pokusaj(redni):
            try:
                forme._proveri_sopstvenu(self.mod, f"pogresna-{redni}")
            except ValidationError as greska:
                return greska.code
            return "proslo"

        with mock.patch("igra.forme.check_password", self.sporo(provera)):
            ishodi = self.istovremeno(40, pokusaj)
        self.assertEqual(len(provere), settings.PRIJAVA_POKUSAJA)
        self.assertEqual(sorted(ishodi), ["blokirano"] * 35 + ["pogresna_lozinka"] * 5)
        self.assertBlokirano(self.prijavi("Mod", klijent=Client()))

    def test_poplava_imena_ne_istiskuje_blokadu(self):
        # Revizija 2026-11-11: u podrazumevanom LocMem kesu (MAX_ENTRIES 300) 320 neuspeha za nasumicna imena
        # istisne kljuc blokade. Brojac je sada u bazi (odluka P2); poplava ni u njemu ni u podrazumevanom kesu
        # ne istiskuje blokadu.
        self.addCleanup(cache.clear)
        self.neuspesi("Mod", 5)
        for redni in range(400):
            ime = f"poplava-{redni}"
            self.assertIsNone(forme.rezervisi_pokusaj(ime))
            forme.zabelezi_neuspeh(ime)
            cache.set(ime, redni)
        self.assertBlokirano(self.prijavi("Mod", klijent=Client()))

    def test_bez_lozinke_nije_pokusaj(self):
        # Bez lozinke ili bez imena AuthenticationForm ne zove authenticate: provere nema, pa se ne broji i ne
        # pravi red u bazi. Inace bi napadac punio tabelu brojaca bez PBKDF2.
        with mock.patch("igra.forme.rezervisi_pokusaj", wraps=forme.rezervisi_pokusaj) as rezervacija:
            for _ in range(settings.PRIJAVA_POKUSAJA + 1):
                self.assertEqual(self.prijavi("Mod", "", Client()).status_code, 200)
                self.assertEqual(self.prijavi("   ", "nesto-dugo-1", Client()).status_code, 200)
            rezervacija.assert_not_called()
            # Kontrola: prijava sa lozinkom rezervise pokusaj, i prolazi.
            self.assertEqual(self.prijavi("Mod", klijent=Client()).status_code, 302)
            rezervacija.assert_called_once_with("Mod")


class OdjavaICsrfTests(OsnovaModeratora):
    def setUp(self):
        super().setUp()
        self.glavni = napravi_moderatora("Glavni", glavni=True)
        self.mod = napravi_moderatora("Mod")
        self.rezultat = upisi_red("Резултат", 70)
        self.link = upisi_deljeno()

    def test_odjava_samo_post(self):
        klijent = self.klijent_za(self.mod)
        self.assertEqual(klijent.get(reverse("moderator_odjava")).status_code, 405)
        self.assertTrue(self.ima_pristup(klijent))

    def test_odjava_cuva_igru_i_brise_prijavu(self):
        klijent = Client()
        self.postavi_igru("seme-odjava", klijent)
        self.klijent_za(self.mod, klijent=klijent)
        self.assertEqual(self.potez(1, klijent=klijent).status_code, 200)
        igra = klijent.session["igra"]
        kljuc = klijent.session.session_key
        odgovor = klijent.post(reverse("moderator_odjava"))
        self.assertEqual(odgovor.status_code, 302)
        self.assertEqual(odgovor["Location"], reverse("moderator_prijava"))
        self.assertNotIn(SESSION_KEY, klijent.session)
        self.assertEqual(klijent.session["igra"], igra)
        self.assertFalse(Session.objects.filter(session_key=kljuc).exists())
        self.assertNaPrijavu(klijent.get(reverse("moderator_dnevnik")))
        self.assertEqual(self.potez(2, klijent=klijent).status_code, 200)

    def test_post_bez_csrf_403_i_bez_izmene(self):
        klijent = Client(enforce_csrf_checks=True)
        klijent.force_login(self.glavni)
        self.assertEqual(klijent.get(reverse("moderator")).status_code, 200)  # postavlja CSRF kolacic
        pre = otisak_baze()
        zahtevi = (
            (reverse("moderator_prijava"), {"username": "Glavni", "password": LOZINKA}),
            (reverse("moderator_odjava"), {}),
            (reverse("moderator"), {"token": self.link.token}),
            (reverse("moderator_rezultat", args=[self.rezultat.id]), {}),
            (reverse("moderator_link", args=[self.link.id]), {}),
            (reverse("moderator_lozinka"),
             {"old_password": LOZINKA, "new_password1": LOZINKA2, "new_password2": LOZINKA2}),
            (reverse("moderator_nalozi"),
             {"ime": "Novi", "lozinka1": LOZINKA2, "lozinka2": LOZINKA2, "moja_lozinka": LOZINKA}),
            (reverse("moderator_nalozi_nalog", args=[self.mod.pk]), {"radnja": "deaktiviraj", "moja_lozinka": LOZINKA}),
        )
        for adresa, podaci in zahtevi:
            with self.subTest(adresa=adresa):
                self.assertEqual(klijent.post(adresa, podaci).status_code, 403)
        self.assertEqual(otisak_baze(), pre)
        self.assertEqual(klijent.get(reverse("moderator_dnevnik")).status_code, 200)  # i dalje prijavljen
        # Kontrola: isti zahtev sa tokenom brise.
        token = klijent.cookies[settings.CSRF_COOKIE_NAME].value
        odgovor = klijent.post(reverse("moderator_rezultat", args=[self.rezultat.id]),
                               {"csrfmiddlewaretoken": token})
        self.assertEqual(odgovor.status_code, 302)
        self.assertFalse(Rezultat.objects.filter(pk=self.rezultat.pk).exists())


class BrisanjeModeratoraTests(OsnovaModeratora):
    def setUp(self):
        super().setUp()
        self.glavni = napravi_moderatora("Glavni", glavni=True)
        self.mod = napravi_moderatora("Mod")
        self.klijent = self.klijent_za(self.mod)

    def igrac_sa_sacuvanom(self, seme, ime, podeli=True):
        """Igrac koji je sacuvao i (po zelji) podelio partiju kroz prikaze; vraca klijent, red i token."""
        igrac = Client()
        self.postavi_zavrsenu(seme, igrac)
        self.assertEqual(self.sacuvaj(ime, igrac).status_code, 200)
        red = Rezultat.objects.get(ime=ime)
        token = token_iz_url(self.podeli_json(igrac)["url"]) if podeli else None
        return igrac, red, token

    def test_get_potvrde_ne_brise(self):
        red = upisi_red("Остаје", 60)
        link = upisi_deljeno()
        pre = otisak_baze()
        for adresa, vrsta in ((reverse("moderator_rezultat", args=[red.id]), "rezultat"),
                              (reverse("moderator_link", args=[link.id]), "link")):
            with self.subTest(vrsta):
                odgovor = self.klijent.get(adresa)
                self.assertEqual(odgovor.status_code, 200)
                self.assertEqual(odgovor.context["vrsta"], vrsta)
                self.assertEqual(odgovor.context["akcija"], adresa)
                html = odgovor.content.decode("utf-8")
                self.assertIn("Потврди брисање", html)
                self.assertIn("Брисање се уписује у дневник.", html)
        self.assertEqual(otisak_baze(), pre)

    def test_brisanje_rezultata(self):
        igrac, red, token = self.igrac_sa_sacuvanom("seme-brisanje-rezultata", "Брисани")
        ostaje = upisi_red("Остаје", 10)
        pre = ZapisDnevnika.objects.count()
        odgovor = self.klijent.post(reverse("moderator_rezultat", args=[red.id]))
        self.assertEqual(odgovor.status_code, 302)
        self.assertEqual(odgovor["Location"], reverse("moderator") + "?poruka=obrisano")
        self.assertFalse(Rezultat.objects.filter(pk=red.id).exists())
        self.assertTrue(Rezultat.objects.filter(pk=ostaje.id).exists())
        self.assertEqual(ZapisDnevnika.objects.count(), pre + 1)
        zapis = self.zapis()
        self.assertEqual((zapis.radnja, zapis.ko_id, zapis.nad_id, zapis.red, zapis.partija),
                         ("rezultat_obrisan", self.mod.pk, None, red.id, red.partija))
        self.assertEqual(set(zapis.snimak), KLJUCEVI_SNIMKA)
        self.assertEqual(zapis.snimak, {"ime": "Брисани", "poeni": red.poeni, "ocena": red.ocena,
                                        "datum": red.sacuvan.isoformat()})
        sve = json.dumps(zapis.snimak)
        self.assertNotIn(red.partija, sve)
        self.assertNotIn(token, sve)
        # Rezultat obrisan, link iste partije ostaje.
        self.assertEqual(self.deljena(token).status_code, 200)
        # PRG: poruka na pregledu.
        strana = self.klijent.get(odgovor["Location"])
        self.assertIn("Обрисано.", strana.content.decode("utf-8"))

    def test_igrac_vidi_sacuvano_van_liste(self):
        igrac, red, _ = self.igrac_sa_sacuvanom("seme-van-liste", "ВанЛисте", podeli=False)
        self.klijent.post(reverse("moderator_rezultat", args=[red.id]))
        rang = rang_iz_html(igrac.get(reverse("pocetna")))
        self.assertEqual((rang["sacuvano"], rang["moj"]), (True, None))
        self.assertNotIn("ВанЛисте", [r["ime"] for r in rang["lista"]])

    def test_jedanaesti_ulazi_na_listu(self):
        redovi = [upisi_red(f"Ред{broj}", 90 - broj) for broj in range(11)]
        pre = [r["ime"] for r in rang_iz_html(self.client.get(reverse("pocetna")))["lista"]]
        self.assertEqual(pre, [f"Ред{broj}" for broj in range(10)])
        self.klijent.post(reverse("moderator_rezultat", args=[redovi[0].id]))
        posle = [r["ime"] for r in rang_iz_html(self.client.get(reverse("pocetna")))["lista"]]
        self.assertEqual(posle, [f"Ред{broj}" for broj in range(1, 11)])

    def test_brisanje_linka(self):
        igrac, red, token = self.igrac_sa_sacuvanom("seme-brisanje-linka", "Линковани")
        link = DeljeniRezultat.objects.get(token=token)
        self.assertEqual(deljeno_iz_html(self.deljena(token))["ime"], "Линковани")
        pre = ZapisDnevnika.objects.count()
        odgovor = self.klijent.post(reverse("moderator_link", args=[link.id]))
        self.assertEqual(odgovor["Location"], reverse("moderator") + "?poruka=obrisano")
        self.assertEqual(ZapisDnevnika.objects.count(), pre + 1)
        zapis = self.zapis()
        self.assertEqual((zapis.radnja, zapis.ko_id, zapis.red, zapis.partija),
                         ("link_obrisan", self.mod.pk, link.id, link.partija))
        self.assertEqual(zapis.snimak, {"ime": "Линковани", "poeni": link.zavrsni["poeni"],
                                        "ocena": link.zavrsni["ocena"], "datum": link.nastao.isoformat()})
        self.assertNotIn(token, json.dumps(zapis.snimak))
        # Obrisan link: isti 404 i isti bajtovi kao link koji nikad nije postojao.
        obrisan = self.deljena(token)
        nikad = self.deljena(secrets.token_urlsafe(16))
        self.assertEqual(obrisan.status_code, 404)
        self.assertEqual(obrisan.content, nikad.content)
        self.assertEqual(obrisan.headers.get("Content-Type"), nikad.headers.get("Content-Type"))
        # Link obrisan, rezultat ostaje.
        self.assertTrue(Rezultat.objects.filter(pk=red.id).exists())

    def test_vec_obrisano_preusmerenje(self):
        red = upisi_red("Брише", 50)
        link = upisi_deljeno()
        drugi = self.klijent_za(self.glavni)
        for ruta, broj in (("moderator_rezultat", red.id), ("moderator_link", link.id)):
            with self.subTest(ruta):
                adresa = reverse(ruta, args=[broj])
                self.assertEqual(self.klijent.post(adresa).status_code, 302)
                pre = ZapisDnevnika.objects.count()
                for odgovor in (drugi.get(adresa), drugi.post(adresa)):
                    self.assertEqual(odgovor.status_code, 302)
                    self.assertEqual(odgovor["Location"], reverse("moderator") + "?poruka=vec_obrisano")
                self.assertEqual(ZapisDnevnika.objects.count(), pre)
        html = drugi.get(reverse("moderator") + "?poruka=vec_obrisano").content.decode("utf-8")
        self.assertIn("Ово је већ обрисано.", html)

    def test_obrisan_izmedju_citanja_i_brave(self):
        red = upisi_red("Трка", 50)
        pravo = brisanje.obrisi_rezultate

        def drugi_moderator_prvi(ids, ko):
            pravo(ids, ko=User.objects.get(pk=self.glavni.pk))
            return pravo(ids, ko=ko)

        with mock.patch("igra.brisanje.obrisi_rezultate", side_effect=drugi_moderator_prvi):
            odgovor = self.klijent.post(reverse("moderator_rezultat", args=[red.id]))
        self.assertEqual(odgovor["Location"], reverse("moderator") + "?poruka=vec_obrisano")
        self.assertEqual(list(ZapisDnevnika.objects.values_list("ko__username", flat=True)), ["Glavni"])

    def test_nepostojeci_id_404(self):
        for ruta in ("moderator_rezultat", "moderator_link"):
            for broj in (NEPOSTOJECI_ID, VELIKI_ID, 2**63 - 1, 0):
                for metoda in ("get", "post"):
                    with self.subTest(ruta=ruta, broj=broj, metoda=metoda):
                        odgovor = getattr(self.klijent, metoda)(reverse(ruta, args=[broj]))
                        self.assertEqual(odgovor.status_code, 404)
                        self.assertEqual(odgovor.content, b"")
        # Istekao link nije u opsegu potvrde: isti 404.
        istekao = istekao_red()
        self.assertEqual(self.klijent.get(reverse("moderator_link", args=[istekao.id])).status_code, 404)
        self.assertTrue(DeljeniRezultat.objects.filter(pk=istekao.id).exists())

    def test_nepoznata_poruka_ignorisana(self):
        for poruka in ("<x>", "obrisano2", ""):
            with self.subTest(poruka=poruka):
                odgovor = self.klijent.get(reverse("moderator"), {"poruka": poruka})
                self.assertIsNone(odgovor.context["poruka"])
                self.assertNotIn(b"&lt;x&gt;", odgovor.content)
                self.assertNotIn("Обрисано.".encode(), odgovor.content)

    def test_ime_nestaje_sa_deljene(self):
        igrac, red, token = self.igrac_sa_sacuvanom("seme-ime-nestaje", "Нестаје")
        self.assertEqual(deljeno_iz_html(self.deljena(token))["ime"], "Нестаје")
        self.klijent.post(reverse("moderator_rezultat", args=[red.id]))
        odgovor = self.deljena(token)
        self.assertEqual(odgovor.status_code, 200)
        self.assertIsNone(deljeno_iz_html(odgovor)["ime"])
        self.assertNotIn("Нестаје", odgovor.content.decode("utf-8"))

    def test_moderator_i_glavni_brisu(self):
        glavni = self.klijent_za(self.glavni)
        for opis, klijent, korisnik in (("moderator", self.klijent, self.mod), ("glavni", glavni, self.glavni)):
            with self.subTest(opis):
                red = upisi_red(f"Брише {opis}", 40)
                link = upisi_deljeno()
                self.assertEqual(klijent.post(reverse("moderator_rezultat", args=[red.id])).status_code, 302)
                self.assertEqual(klijent.post(reverse("moderator_link", args=[link.id])).status_code, 302)
                self.assertFalse(Rezultat.objects.filter(pk=red.id).exists())
                self.assertFalse(DeljeniRezultat.objects.filter(pk=link.id).exists())
                self.assertEqual(
                    list(ZapisDnevnika.objects.filter(red__in=[red.id, link.id], ko=korisnik)
                         .order_by("radnja").values_list("radnja", flat=True)),
                    ["link_obrisan", "rezultat_obrisan"],
                )

    def test_pretraga_linka(self):
        _, _, token = self.igrac_sa_sacuvanom("seme-pretraga", "Тражени")
        link = DeljeniRezultat.objects.get(token=token)
        for unos in (f"http://testserver/r/{token}/", token, f"  https://drugi.example/r/{token}/?x=1  "):
            with self.subTest(unos=unos):
                odgovor = self.klijent.post(reverse("moderator"), {"token": unos})
                self.assertEqual(odgovor.status_code, 200)
                self.assertEqual(odgovor.context["pronadjen"]["id"], link.id)
                self.assertEqual(odgovor.context["pronadjen"]["ime"], "Тражени")
                self.assertNotIn(token.encode(), odgovor.content)
                self.assertNotIn(link.partija.encode(), odgovor.content)
        self.assertIsNone(self.klijent.get(reverse("moderator")).context["pronadjen"])
        self.klijent.post(reverse("moderator_link", args=[link.id]))
        for unos in (token, "x" * 22, "nije-token", "a" * 5000):
            with self.subTest(nema=unos[:30]):
                odgovor = self.klijent.post(reverse("moderator"), {"token": unos})
                self.assertIs(odgovor.context["pronadjen"], False)
                self.assertIn("Тај линк не постоји или више није доступан.", odgovor.content.decode("utf-8"))


class GarancijaBrisanjaTests(OsnovaModeratora):
    SEME = "seme-garancija-obrisane"

    def setUp(self):
        super().setUp()
        self.mod = napravi_moderatora("Mod")
        self.klijent = self.klijent_za(self.mod)

    def igrac_bez_oznake(self):
        """Ista partija u novoj sesiji, bez oznaka sacuvano i podeljeno (npr. kopija sesije)."""
        klijent = Client()
        self.postavi_zavrsenu(self.SEME, klijent)
        return klijent

    def assertCuvanje409(self, klijent):
        odgovor = self.sacuvaj("Опет", klijent)
        self.assertEqual(odgovor.status_code, 409)
        self.assertEqual(json.loads(odgovor.content)["greska"], "vec_sacuvano")

    def assertDeljenje409(self, klijent):
        odgovor = self.podeli(klijent)
        self.assertEqual(odgovor.status_code, 409)
        self.assertEqual(json.loads(odgovor.content), {"greska": "deljenje_isteklo"})

    def test_obrisana_partija_409(self):
        igrac = Client()
        self.postavi_zavrsenu(self.SEME, igrac)
        self.assertEqual(self.sacuvaj("Прво", igrac).status_code, 200)
        token = token_iz_url(self.podeli_json(igrac)["url"])
        red = Rezultat.objects.get(ime="Прво")
        link = DeljeniRezultat.objects.get(token=token)
        self.klijent.post(reverse("moderator_rezultat", args=[red.id]))
        self.klijent.post(reverse("moderator_link", args=[link.id]))
        for opis, klijent in (("sa oznakom", igrac), ("bez oznake", self.igrac_bez_oznake())):
            with self.subTest(opis):
                self.assertCuvanje409(klijent)
                self.assertDeljenje409(klijent)
        self.assertEqual(Rezultat.objects.count(), 0)
        self.assertEqual(DeljeniRezultat.objects.count(), 0)
        # Tekst poruke na zavrsnom ekranu (plan 14.7).
        poruke = tekstovi_iz_html(igrac.get(reverse("pocetna")))["poruke"]
        self.assertEqual(poruke["deljenjeIsteklo"], ISTEKLO_SR)

    def test_obrisana_partija_posle_ponovne_upotrebe_id(self):
        igrac = Client()
        self.postavi_zavrsenu(self.SEME, igrac)
        self.sacuvaj("Прво", igrac)
        token = token_iz_url(self.podeli_json(igrac)["url"])
        red = Rezultat.objects.get(ime="Прво")
        link = DeljeniRezultat.objects.get(token=token)
        self.klijent.post(reverse("moderator_rezultat", args=[red.id]))
        self.klijent.post(reverse("moderator_link", args=[link.id]))
        # Prepravka tabele vraca brojac: druga partija dobija iste id-jeve.
        with connection.cursor() as kursor:
            kursor.execute("UPDATE sqlite_sequence SET seq = %s WHERE name = 'igra_rezultat'", [red.id - 1])
            kursor.execute("UPDATE sqlite_sequence SET seq = %s WHERE name = 'igra_deljenirezultat'", [link.id - 1])
        drugi = Client()
        self.postavi_zavrsenu("seme-garancija-druga", drugi)
        self.assertEqual(self.sacuvaj("Друго", drugi).status_code, 200)
        self.podeli_json(drugi)
        self.assertEqual(Rezultat.objects.get(ime="Друго").id, red.id)
        self.assertEqual(DeljeniRezultat.objects.get().id, link.id)
        for opis, klijent in (("sa oznakom", igrac), ("bez oznake", self.igrac_bez_oznake())):
            with self.subTest(opis):
                self.assertCuvanje409(klijent)
                self.assertDeljenje409(klijent)
        self.assertFalse(Rezultat.objects.filter(partija=red.partija).exists())
        self.assertFalse(DeljeniRezultat.objects.filter(partija=red.partija).exists())

    def test_obrisana_komandom_409(self):
        stanje = odigraj_celu(self.SEME, sve_opus)
        partija = motor.oznaka_partije(stanje)
        red = Rezultat.objects.create(ime="Команда", poeni=stanje["rezultat"]["poeni"],
                                      ocena=stanje["rezultat"]["ocena"], pravila=p.PRAVILA_TEKUCA, partija=partija)
        call_command("rezultat_obrisi", str(red.id), stdout=StringIO())
        self.assertCuvanje409(self.igrac_bez_oznake())

    def test_dnevnik_dana_veci_od_sesije(self):
        self.assertEqual(settings.DNEVNIK_DANA, 365)
        self.assertGreater(settings.DNEVNIK_DANA * 86400, settings.SESSION_COOKIE_AGE)


class NaloziModeratoraTests(OsnovaModeratora):
    def setUp(self):
        super().setUp()
        self.glavni = napravi_moderatora("Glavni", glavni=True)
        self.mod = napravi_moderatora("Mod")
        self.klijent = self.klijent_za(self.glavni)

    def tearDown(self):
        self.assertEqual(glavni_bez_moderira(), [])  # pravilo 3 posle svakog testa
        self.assertTrue(nalozi.ima_aktivnog_glavnog())  # pravilo 1
        super().tearDown()

    def svez(self, korisnik):
        return User.objects.select_related("nalog_moderatora").get(pk=korisnik.pk)

    def test_dodaj(self):
        for ime, glavni in (("Novi", False), ("NoviGlavni", True)):
            with self.subTest(ime=ime):
                odgovor = self.dodaj(self.klijent, ime, glavni=glavni)
                self.assertEqual(odgovor.status_code, 302)
                self.assertEqual(odgovor["Location"], reverse("moderator_nalozi"))
                novi = self.svez(User.objects.get(username=ime))
                self.assertEqual((novi.is_active, novi.is_staff, novi.is_superuser), (True, False, False))
                self.assertTrue(novi.check_password(LOZINKA2))
                self.assertTrue(novi.nalog_moderatora.mora_promeniti)
                self.assertEqual(nalozi.uloga(novi), "glavni" if glavni else "moderator")
                zapis = self.zapis()
                self.assertEqual((zapis.radnja, zapis.ko_id, zapis.nad_id, zapis.snimak),
                                 ("moderator_dodat", self.glavni.pk, novi.pk, {"glavni": glavni}))
                # Lista naloga ga prikazuje sa oznakom obavezne promene.
                lista = {n["ime"]: n for n in self.klijent.get(reverse("moderator_nalozi")).context["nalozi"]}
                self.assertEqual((lista[ime]["glavni"], lista[ime]["mora_promeniti"], lista[ime]["aktivan"]),
                                 (glavni, True, True))

    def test_dodaj_odbija(self):
        napravi_moderatora("Пера")
        pre = otisak_baze()
        slucajevi = (
            ("isto ime, druga slova", {"ime": "MOD"}, "ime"),
            ("isto ime, cirilica", {"ime": "пера"}, "ime"),
            ("nedozvoljen znak", {"ime": "<svg onload=a()>"}, "ime"),
            ("prazno ime", {"ime": ""}, "ime"),
            ("kratka lozinka", {"ime": "Novi", "lozinka": "Kratka-1"}, "lozinka1"),
            ("samo cifre", {"ime": "Novi", "lozinka": "839201746583"}, "lozinka1"),
            ("cesta lozinka", {"ime": "Novi", "lozinka": "password1234"}, "lozinka1"),
            ("slicna imenu", {"ime": "Dragoljubovic", "lozinka": "dragoljubovic1"}, "lozinka1"),
            ("ne poklapaju se", {"ime": "Novi", "lozinka2": LOZINKA3}, "lozinka2"),
            ("pogresna potvrda", {"ime": "Novi", "moja": "pogresna"}, "moja_lozinka"),
        )
        for opis, podaci, polje in slucajevi:
            with self.subTest(opis):
                obrisi_brojace()
                odgovor = self.dodaj(self.klijent, **podaci)
                self.assertEqual(odgovor.status_code, 200)
                self.assertNotEqual(greske_polja(odgovor.content.decode("utf-8"), polje), [])
        self.assertEqual(otisak_baze(), pre)
        # Servis odbija isto i mimo forme (komanda, trka).
        with self.assertRaises(ValidationError):
            nalozi.dodaj(self.glavni, "пера", LOZINKA2)
        with self.assertRaises(ValidationError):
            nalozi.dodaj(None, "Novi", "Kratka-1")
        self.assertEqual(otisak_baze(), pre)

    def test_ne_sebe(self):
        drugi = napravi_moderatora("Drugi", glavni=True)
        odgovor = self.klijent.get(reverse("moderator_nalozi_nalog", args=[self.glavni.pk]))
        self.assertNotIn("deaktiviraj", odgovor.context["radnje"])
        self.assertNotIn("lozinka", odgovor.context["radnje"])
        self.assertNotIn('value="deaktiviraj"', odgovor.content.decode("utf-8"))
        pre = otisak_baze()
        odgovor = self.radnja(self.klijent, self.glavni, "deaktiviraj")
        self.assertEqual(odgovor.status_code, 200)
        self.assertEqual(odgovor.context["odbijeno"], "nije_dozvoljeno")
        self.assertEqual(poruke_greske(odgovor.content.decode("utf-8")), [NEDOZVOLJENO_SR])
        self.assertOdbijeno(lambda: nalozi.deaktiviraj(self.glavni, self.glavni), "ne_sebe")
        self.assertOdbijeno(lambda: nalozi.postavi_lozinku(self.glavni, self.glavni, LOZINKA3), "ne_sebe")
        self.assertEqual(otisak_baze(), pre)
        self.assertTrue(self.svez(drugi).is_active)

    def test_poruke_odbijanja_servisa_na_strani(self):
        # Strana je zastarela: servis odbija, a strana kaze zasto (poslednji_glavni ima svoj tekst).
        drugi = napravi_moderatora("Drugi", glavni=True)
        pravo = nalozi.oduzmi_ulogu

        def drugi_prvi_oduzima(ko, nad):
            pravo(None, User.objects.get(pk=drugi.pk))
            return pravo(ko, nad)

        with mock.patch("igra.nalozi.oduzmi_ulogu", side_effect=drugi_prvi_oduzima):
            odgovor = self.radnja(self.klijent, self.glavni, "oduzmi_ulogu")
        self.assertEqual(odgovor.status_code, 200)
        self.assertEqual(odgovor.context["odbijeno"], "poslednji_glavni")
        self.assertEqual(poruke_greske(odgovor.content.decode("utf-8")), [POSLEDNJI_GLAVNI_SR])
        self.assertEqual(odgovor.context["radnje"], [])  # strana pokazuje tekuce stanje
        self.assertEqual(nalozi.uloga(self.svez(self.glavni)), "glavni")

    def test_poslednji_glavni(self):
        pre = otisak_baze()
        for opis, radnja in (
            ("deaktivacija komandom", lambda: nalozi.deaktiviraj(None, self.glavni)),
            ("oduzimanje komandom", lambda: nalozi.oduzmi_ulogu(None, self.glavni)),
            ("oduzimanje sebi", lambda: nalozi.oduzmi_ulogu(self.glavni, self.glavni)),
        ):
            with self.subTest(opis):
                self.assertOdbijeno(radnja, "poslednji_glavni")
        self.assertEqual(otisak_baze(), pre)
        # Neaktivan glavni i superuser se ne racunaju.
        neaktivan = napravi_moderatora("NeaktivanGlavni", glavni=True)
        User.objects.filter(pk=neaktivan.pk).update(is_active=False)
        User.objects.create_superuser("Super", password=LOZINKA)
        self.assertOdbijeno(lambda: nalozi.deaktiviraj(None, self.glavni), "poslednji_glavni")
        # Strana sopstvenog naloga poslednjeg glavnog ne nudi nista; POST oduzimanja ne prolazi.
        odgovor = self.klijent.get(reverse("moderator_nalozi_nalog", args=[self.glavni.pk]))
        self.assertEqual(odgovor.context["radnje"], [])
        self.assertNotIn("Одузми улогу главног", odgovor.content.decode("utf-8"))
        odgovor = self.radnja(self.klijent, self.glavni, "oduzmi_ulogu")
        self.assertEqual(odgovor.context["odbijeno"], "nije_dozvoljeno")
        self.assertEqual(nalozi.uloga(self.svez(self.glavni)), "glavni")
        # Sa dva glavna oduzimanje sebi prolazi; posle toga nalozi* je 403.
        drugi = napravi_moderatora("Drugi", glavni=True)
        self.assertIn("oduzmi_ulogu", self.klijent.get(
            reverse("moderator_nalozi_nalog", args=[self.glavni.pk])).context["radnje"])
        odgovor = self.radnja(self.klijent, self.glavni, "oduzmi_ulogu")
        self.assertEqual(odgovor.status_code, 302)
        self.assertEqual(odgovor["Location"], reverse("moderator"))
        self.assertEqual(nalozi.uloga(self.svez(self.glavni)), "moderator")
        self.assertEqual(self.klijent.get(reverse("moderator_nalozi")).status_code, 403)
        zapis = self.zapis()
        self.assertEqual((zapis.radnja, zapis.ko_id, zapis.nad_id), ("uloga_oduzeta", self.glavni.pk, self.glavni.pk))
        # Sada je drugi poslednji.
        self.assertOdbijeno(lambda: nalozi.deaktiviraj(None, drugi), "poslednji_glavni")

    def test_glavni_deaktivira_glavnog(self):
        drugi = napravi_moderatora("Drugi", glavni=True)
        odgovor = self.radnja(self.klijent, drugi, "deaktiviraj")
        self.assertEqual(odgovor.status_code, 302)
        drugi = self.svez(drugi)
        self.assertFalse(drugi.is_active)
        self.assertNotIn(drugi.pk, nalozi.id_glavnih())
        zapis = self.zapis()
        self.assertEqual((zapis.radnja, zapis.ko_id, zapis.nad_id, zapis.snimak),
                         ("moderator_deaktiviran", self.glavni.pk, drugi.pk, {"glavni": True}))
        strana = self.klijent.get(reverse("moderator_nalozi_nalog", args=[drugi.pk]))
        self.assertEqual(strana.context["radnje"], ["aktiviraj"])
        odgovor = self.radnja(self.klijent, drugi, "aktiviraj", lozinka1=LOZINKA3, lozinka2=LOZINKA3)
        self.assertEqual(odgovor.status_code, 302)
        drugi = self.svez(drugi)
        self.assertTrue(drugi.is_active)
        self.assertEqual(nalozi.uloga(drugi), "moderator")  # uloga se ne vraca sama
        self.assertTrue(drugi.nalog_moderatora.mora_promeniti)
        self.assertEqual(self.zapis().radnja, "moderator_aktiviran")
        # Drugi se prijavljuje novom lozinkom i mora da je promeni.
        klijent = self.klijent_za(drugi, LOZINKA3)
        self.assertEqual(klijent.get(reverse("moderator"))["Location"], reverse("moderator_lozinka"))

    def test_uzajamna_deaktivacija_glavnih(self):
        drugi = napravi_moderatora("Drugi", glavni=True)
        # Oba objekta su ucitana pre prve radnje, kao request.user dva istovremena zahteva.
        a_staro = User.objects.get(pk=self.glavni.pk)
        b_staro = User.objects.get(pk=drugi.pk)
        self.assertEqual((nalozi.uloga(a_staro), nalozi.uloga(b_staro)), ("glavni", "glavni"))
        nalozi.deaktiviraj(a_staro, b_staro)
        pre = otisak_baze()
        self.assertOdbijeno(lambda: nalozi.deaktiviraj(b_staro, a_staro), "nema_prava")
        self.assertEqual(otisak_baze(), pre)
        self.assertEqual(list(nalozi.aktivni_glavni().values_list("username", flat=True)), ["Glavni"])

    def test_uzajamna_deaktivacija_kroz_stranu(self):
        drugi = napravi_moderatora("Drugi", glavni=True)
        klijent_b = self.klijent_za(drugi)
        pravo = nalozi.deaktiviraj

        def a_stize_prvi(ko, nad):
            # A deaktivira B izmedju dekoratora B-ovog zahteva i brave.
            pravo(User.objects.get(pk=self.glavni.pk), User.objects.get(pk=drugi.pk))
            return pravo(ko, nad)

        adresa = reverse("moderator_nalozi_nalog", args=[self.glavni.pk])
        with mock.patch("igra.nalozi.deaktiviraj", side_effect=a_stize_prvi):
            odgovor = klijent_b.post(adresa, {"radnja": "deaktiviraj", "moja_lozinka": LOZINKA})
        self.assertEqual(odgovor.status_code, 302)
        self.assertEqual(odgovor["Location"], adresa)
        self.assertTrue(self.svez(self.glavni).is_active)
        self.assertFalse(self.svez(drugi).is_active)
        self.assertEqual(list(nalozi.aktivni_glavni().values_list("username", flat=True)), ["Glavni"])
        self.assertNaPrijavu(klijent_b.get(adresa))

    def test_deaktiviran_odjavljen_igra_ostaje(self):
        igrac = Client()
        self.postavi_igru("seme-deaktiviran", igrac)
        self.klijent_za(self.mod, klijent=igrac)
        self.assertTrue(self.ima_pristup(igrac))
        igra = igrac.session["igra"]
        self.assertEqual(self.radnja(self.klijent, self.mod, "deaktiviraj").status_code, 302)
        self.assertNaPrijavu(igrac.get(reverse("moderator")))
        self.assertEqual(igrac.session["igra"], igra)
        self.assertEqual(self.potez(1, klijent=igrac).status_code, 200)
        odgovor = self.prijavi("Mod", klijent=Client())
        self.assertEqual(poruke_greske(odgovor.content.decode("utf-8")), [PORUKA_PRIJAVE])

    def test_postavi_lozinku_gasi_sesije(self):
        vlasnik = self.klijent_za(self.mod)
        self.assertTrue(self.ima_pristup(vlasnik))
        odgovor = self.radnja(self.klijent, self.mod, "lozinka", lozinka1=LOZINKA3, lozinka2=LOZINKA3)
        self.assertEqual(odgovor.status_code, 302)
        self.assertNaPrijavu(vlasnik.get(reverse("moderator_dnevnik")))
        zapis = self.zapis()
        self.assertEqual((zapis.radnja, zapis.ko_id, zapis.nad_id), ("lozinka_postavljena", self.glavni.pk, self.mod.pk))
        self.assertEqual(self.prijavi("Mod", LOZINKA, Client()).status_code, 200)  # stara ne vazi
        novi = self.klijent_za(self.mod, LOZINKA3)
        self.assertEqual(novi.get(reverse("moderator_dnevnik"))["Location"], reverse("moderator_lozinka"))
        self.assertTrue(self.ima_pristup(self.klijent))  # glavni ostaje prijavljen

    def test_promeni_svoju_cuva_sesiju_i_igru(self):
        for korisnik in (self.mod, self.glavni):
            with self.subTest(korisnik.get_username()):
                NalogModeratora.objects.filter(pk=korisnik.pk).update(mora_promeniti=True)
                klijent = Client()
                self.postavi_igru(f"seme-promena-{korisnik.pk}", klijent)
                self.klijent_za(korisnik, klijent=klijent)
                druga = self.klijent_za(korisnik)
                igra = klijent.session["igra"]
                strana = klijent.get(reverse("moderator_lozinka"))
                self.assertIn("Морате да промените лозинку пре наставка.", strana.content.decode("utf-8"))
                odgovor = self.promeni(klijent, LOZINKA, LOZINKA3)
                self.assertEqual(odgovor.status_code, 302)
                self.assertEqual(odgovor["Location"], reverse("moderator"))
                self.assertTrue(self.ima_pristup(klijent))
                self.assertEqual(klijent.session["igra"], igra)
                self.assertNaPrijavu(druga.get(reverse("moderator_dnevnik")))  # ostale sesije ugasene
                svez = self.svez(korisnik)
                self.assertFalse(svez.nalog_moderatora.mora_promeniti)
                self.assertTrue(svez.check_password(LOZINKA3))
                zapis = self.zapis()
                self.assertEqual((zapis.radnja, zapis.ko_id, zapis.nad_id),
                                 ("lozinka_promenjena", korisnik.pk, korisnik.pk))

    def test_promena_lozinke_greske_vidljive(self):
        klijent = self.klijent_za(self.mod)
        pre = otisak_baze()
        for opis, stara, nova, nova2, polje in (
            ("kratka", LOZINKA, "Kratka-1", None, "new_password2"),
            ("ne poklapaju se", LOZINKA, LOZINKA2, LOZINKA3, "new_password2"),
            ("pogresna stara", "pogresna", LOZINKA2, None, "old_password"),
        ):
            with self.subTest(opis):
                obrisi_brojace()
                odgovor = self.promeni(klijent, stara, nova, nova2)
                self.assertEqual(odgovor.status_code, 200)
                self.assertNotEqual(greske_polja(odgovor.content.decode("utf-8"), polje), [])
                self.assertNotIn(nova, odgovor.content.decode("utf-8"))
        self.assertEqual(otisak_baze(), pre)

    def test_promena_odbija_istu_lozinku(self):
        # Revizija 2026-11-11: obavezna promena je prihvatala istu pocetnu lozinku i skidala mora_promeniti.
        NalogModeratora.objects.filter(pk=self.mod.pk).update(mora_promeniti=True)
        klijent = self.klijent_za(self.mod)
        pre = otisak_baze()
        odgovor = self.promeni(klijent, LOZINKA, LOZINKA)
        self.assertEqual(odgovor.status_code, 200)
        self.assertEqual(poruke_greske(odgovor.content.decode("utf-8")), [ISTA_LOZINKA_SR])
        self.assertEqual(otisak_baze(), pre)
        self.assertEqual(klijent.get(reverse("moderator_dnevnik"))["Location"], reverse("moderator_lozinka"))
        en = self.klijent_za(self.mod, klijent=klijent_jezika("en"))
        odgovor = self.promeni(en, LOZINKA, LOZINKA)
        self.assertEqual(poruke_greske(odgovor.content.decode("utf-8")), [ISTA_LOZINKA_EN])
        # Servis odbija i mimo forme, i bez obavezne promene.
        NalogModeratora.objects.filter(pk=self.mod.pk).update(mora_promeniti=False)
        with self.assertRaises(ValidationError) as greska:
            nalozi.promeni_svoju(self.mod, LOZINKA, LOZINKA)
        self.assertEqual(greska.exception.code, "ista_lozinka")
        self.assertTrue(self.svez(self.mod).check_password(LOZINKA))
        self.assertFalse(ZapisDnevnika.objects.filter(radnja="lozinka_promenjena").exists())
        # Kontrola: druga lozinka prolazi.
        self.assertEqual(self.promeni(klijent, LOZINKA, LOZINKA2).status_code, 302)

    def test_hes_lozinke_van_brave(self):
        # Revizija 2026-11-11: PBKDF2 pod IMMEDIATE bravom drzi celu SQLite bazu stotine ms, pa potez igraca za to
        # vreme dobija "database is locked" (500). Provera i hes lozinke idu pre transaction.atomic() servisa.
        osnova = len(connection.atomic_blocks)  # TestCase: atomic klase i testa; servis bi dodao jos jedan
        dubine = []
        pravi_hes = MD5PasswordHasher.encode

        def hes(hasher, lozinka, so):
            dubine.append(len(connection.atomic_blocks))
            return pravi_hes(hasher, lozinka, so)

        neaktivan = napravi_moderatora("Neaktivan")
        User.objects.filter(pk=neaktivan.pk).update(is_active=False)
        # verify (provera stare lozinke) racuna isti encode.
        with mock.patch.object(MD5PasswordHasher, "encode", hes):
            for opis, radnja in (
                ("dodaj", lambda: nalozi.dodaj(self.glavni, "Novi", LOZINKA2)),
                ("aktiviraj", lambda: nalozi.aktiviraj(self.glavni, neaktivan, LOZINKA3)),
                ("postavi_lozinku", lambda: nalozi.postavi_lozinku(self.glavni, self.mod, LOZINKA3)),
                ("promeni_svoju", lambda: nalozi.promeni_svoju(self.mod, LOZINKA3, LOZINKA2)),
            ):
                with self.subTest(opis):
                    dubine.clear()
                    radnja()
                    self.assertNotEqual(dubine, [])  # hes je racunat, pa tvrdnja ispod ne prolazi prazno
                    self.assertEqual(set(dubine), {osnova})
        self.assertEqual(list(ZapisDnevnika.objects.order_by("id").values_list("radnja", flat=True)),
                         ["moderator_dodat", "moderator_aktiviran", "lozinka_postavljena", "lozinka_promenjena"])
        self.assertTrue(self.svez(self.mod).check_password(LOZINKA2))

    def test_lozinka_promenjena_pre_brave_odbija(self):
        # Hes se racuna pre brave. Ako u medjuvremenu neko promeni lozinku, radnja je ne sme pregaziti, niti
        # prihvatiti staru lozinku proverenu protiv hesa koji vise ne vazi.
        neaktivan = napravi_moderatora("Neaktivan")
        User.objects.filter(pk=neaktivan.pk).update(is_active=False)
        tudja = make_password("Tudja-Lozinka-Izmedju-55")
        pravi_hes = nalozi.make_password

        def tudja_izmedju(nad):
            def hes(lozinka):
                vrednost = pravi_hes(lozinka)
                User.objects.filter(pk=nad.pk).update(password=tudja)  # druga promena: posle citanja, pre brave
                return vrednost
            return hes

        def bez_lozinke(otisak):
            dnevnik, rezultati, deljeni, prijave, korisnici, dozvole, nalozi_ = otisak
            return dnevnik, [(pk, ime, aktivan) for pk, ime, _, aktivan, _ in korisnici], dozvole, nalozi_

        for opis, nad, radnja in (
            ("aktiviraj", neaktivan, lambda: nalozi.aktiviraj(self.glavni, neaktivan, LOZINKA3)),
            ("postavi_lozinku", self.mod, lambda: nalozi.postavi_lozinku(self.glavni, self.mod, LOZINKA3)),
            ("promeni_svoju", self.mod, lambda: nalozi.promeni_svoju(self.mod, LOZINKA, LOZINKA3)),
        ):
            with self.subTest(opis):
                User.objects.filter(pk=nad.pk).update(password=make_password(LOZINKA))
                pre = otisak_baze()
                with mock.patch("igra.nalozi.make_password", tudja_izmedju(nad)):
                    self.assertOdbijeno(radnja, "lozinka_promenjena")
                self.assertEqual(self.svez(nad).password, tudja)
                self.assertEqual(bez_lozinke(otisak_baze()), bez_lozinke(pre))
        # Strana naloga: opsta poruka odbijanja, ne 500.
        User.objects.filter(pk=self.mod.pk).update(password=make_password(LOZINKA))
        with mock.patch("igra.nalozi.make_password", tudja_izmedju(self.mod)):
            odgovor = self.radnja(self.klijent, self.mod, "lozinka", lozinka1=LOZINKA3, lozinka2=LOZINKA3)
        self.assertEqual(odgovor.status_code, 200)
        self.assertEqual(poruke_greske(odgovor.content.decode("utf-8")), [NEDOZVOLJENO_SR])

    def test_potvrda_ne_menja_hes(self):
        # Revizija 2026-11-11: korisnik.check_password pri nadogradnji hesa (drugi pozeljni hes ili vise
        # iteracija posle podizanja Django-a) upisuje nov hes, a nov hes menja hes sesije i odjavljuje glavnog.
        hes = self.svez(self.glavni).password
        self.assertTrue(hes.startswith("md5$"))
        with override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.PBKDF2PasswordHasher", *BRZI_HES]):
            odgovor = self.radnja(self.klijent, self.mod, "dodeli_ulogu")
        self.assertEqual(odgovor.status_code, 302)
        self.assertEqual(nalozi.uloga(self.svez(self.mod)), "glavni")
        self.assertEqual(self.svez(self.glavni).password, hes)
        self.assertTrue(self.ima_pristup(self.klijent))

    def test_aktiviraj_trazi_novu_lozinku(self):
        nalozi.deaktiviraj(self.glavni, self.mod)
        pre = otisak_baze()
        for opis, podaci, polje in (
            ("bez lozinke", {}, "aktiviraj-lozinka1"),
            ("kratka", {"lozinka1": "Kratka-1", "lozinka2": "Kratka-1"}, "aktiviraj-lozinka1"),
            ("ne poklapaju se", {"lozinka1": LOZINKA2, "lozinka2": LOZINKA3}, "aktiviraj-lozinka2"),
        ):
            with self.subTest(opis):
                odgovor = self.radnja(self.klijent, self.mod, "aktiviraj", **podaci)
                self.assertEqual(odgovor.status_code, 200)
                self.assertNotEqual(greske_polja(odgovor.content.decode("utf-8"), polje), [])
        self.assertEqual(otisak_baze(), pre)
        self.radnja(self.klijent, self.mod, "aktiviraj", lozinka1=LOZINKA3, lozinka2=LOZINKA3)
        mod = self.svez(self.mod)
        self.assertTrue(mod.is_active)
        self.assertFalse(mod.check_password(LOZINKA))
        self.assertTrue(mod.nalog_moderatora.mora_promeniti)

    def test_potvrda_sopstvenom_lozinkom(self):
        drugi = napravi_moderatora("Drugi", glavni=True)
        neaktivan = napravi_moderatora("Neaktivan")
        User.objects.filter(pk=neaktivan.pk).update(is_active=False)
        nove = {"lozinka1": LOZINKA3, "lozinka2": LOZINKA3}
        slucajevi = (
            ("deaktiviraj", self.mod, {}, "deaktiviraj-moja_lozinka"),
            ("lozinka", self.mod, nove, "lozinka-moja_lozinka"),
            ("dodeli_ulogu", self.mod, {}, "dodeli-moja_lozinka"),
            ("oduzmi_ulogu", drugi, {}, "oduzmi-moja_lozinka"),
            ("aktiviraj", neaktivan, nove, "aktiviraj-moja_lozinka"),
        )
        pre = otisak_baze()
        for radnja, nad, polja, id_polja in slucajevi:
            for moja in ("pogresna", ""):
                with self.subTest(radnja=radnja, moja=moja):
                    obrisi_brojace()
                    odgovor = self.radnja(self.klijent, nad, radnja, moja=moja, **polja)
                    self.assertEqual(odgovor.status_code, 200)
                    self.assertNotEqual(greske_polja(odgovor.content.decode("utf-8"), id_polja), [])
        self.assertEqual(otisak_baze(), pre)
        # Kontrola: ispravna potvrda prolazi.
        self.assertEqual(self.radnja(self.klijent, self.mod, "dodeli_ulogu").status_code, 302)
        self.assertEqual(nalozi.uloga(self.svez(self.mod)), "glavni")
        self.assertEqual(self.zapis().radnja, "uloga_dodeljena")

    def test_nepoznata_i_neponudjena_radnja(self):
        pre = otisak_baze()
        for radnja in ("nepoznata", "", "obrisi"):
            with self.subTest(radnja=radnja):
                self.assertEqual(self.radnja(self.klijent, self.mod, radnja).status_code, 400)
        odgovor = self.radnja(self.klijent, self.mod, "aktiviraj", lozinka1=LOZINKA3, lozinka2=LOZINKA3)
        self.assertEqual(odgovor.status_code, 200)
        self.assertEqual(odgovor.context["odbijeno"], "nije_dozvoljeno")
        self.assertEqual(poruke_greske(odgovor.content.decode("utf-8")), [NEDOZVOLJENO_SR])
        odgovor = self.radnja(self.klijent, self.mod, "oduzmi_ulogu")  # mod nije glavni
        self.assertEqual(odgovor.context["odbijeno"], "nije_dozvoljeno")
        self.assertEqual(otisak_baze(), pre)

    def test_glavni_uvek_moderator(self):
        # Nalog sa upravlja_nalozima bez moderira nije ni moderator ni glavni, i ne moze to da postane.
        bez = User.objects.create_user("BezModerira", password=LOZINKA)
        bez.user_permissions.add(dozvola("upravlja_nalozima"))
        NalogModeratora.objects.create(korisnik=bez, mora_promeniti=False)
        bez = self.svez(bez)
        self.assertIsNone(nalozi.uloga(bez))
        self.assertNotIn(bez.pk, nalozi.aktivni_glavni().values_list("pk", flat=True))
        self.assertOdbijeno(lambda: nalozi.dodeli_ulogu(self.glavni, bez), "nije_aktivan")
        self.assertEqual(self.prijavi("BezModerira", klijent=Client()).status_code, 200)
        # Rucno pokvaren nalog se ne racuna kao glavni: poslednji pravi glavni ostaje zasticen.
        self.assertOdbijeno(lambda: nalozi.deaktiviraj(None, self.glavni), "poslednji_glavni")
        # Aktiviranje skida upravlja_nalozima, pa kvar ne prezivi.
        User.objects.filter(pk=bez.pk).update(is_active=False)
        nalozi.aktiviraj(self.glavni, bez, LOZINKA3)
        self.assertNotIn(bez.pk, nalozi.id_glavnih())
        # Radnje servisa ostavljaju pravilo 3 (proverava i tearDown).
        novi = nalozi.dodaj(self.glavni, "NoviGlavni", LOZINKA2, glavni=True)
        nalozi.dodeli_ulogu(self.glavni, self.mod)
        nalozi.oduzmi_ulogu(self.glavni, novi)
        self.assertEqual(glavni_bez_moderira(), [])

    def test_nalog_id_van_opsega_404(self):
        bez = napravi_korisnika_bez_dozvole("BezNaloga")
        super_korisnik = User.objects.create_superuser("Super", password=LOZINKA)
        for broj in (bez.pk, super_korisnik.pk, NEPOSTOJECI_ID, VELIKI_ID):
            for metoda in ("get", "post"):
                with self.subTest(broj=broj, metoda=metoda):
                    podaci = {"radnja": "deaktiviraj", "moja_lozinka": LOZINKA} if metoda == "post" else {}
                    odgovor = getattr(self.klijent, metoda)(reverse("moderator_nalozi_nalog", args=[broj]), podaci)
                    self.assertEqual(odgovor.status_code, 404)
                    self.assertEqual(odgovor.content, b"")
        self.assertTrue(self.svez(bez).is_active)
        # Lista naloga: samo moderatori.
        imena_naloga = [n["ime"] for n in self.klijent.get(reverse("moderator_nalozi")).context["nalozi"]]
        self.assertEqual(imena_naloga, ["Glavni", "Mod"])


class DnevnikModeratoraTests(OsnovaModeratora):
    def setUp(self):
        super().setUp()
        self.glavni = napravi_moderatora("Glavni", glavni=True)
        self.mod = napravi_moderatora("Mod")

    def zapis_naloga(self, kada=None, radnja="moderator_aktiviran"):
        polja = {"radnja": radnja, "ko": self.glavni, "nad": self.mod}
        if kada is not None:
            polja["kada"] = kada
        return ZapisDnevnika.objects.upisi(**polja)

    def test_save_odbija_izmenu(self):
        zapis = self.zapis_naloga()
        zapis.snimak = {"glavni": True}
        with self.assertRaisesMessage(ValueError, "dnevnik se ne menja"):
            zapis.save()
        with self.assertRaisesMessage(ValueError, "dnevnik se ne menja"):
            ZapisDnevnika.objects.get(pk=zapis.pk).save(update_fields=["radnja"])
        self.assertEqual(ZapisDnevnika.objects.get(pk=zapis.pk).snimak, {})

    def test_update_okidac(self):
        zapis = self.zapis_naloga()
        for opis, izmena in (
            ("QuerySet.update", lambda: ZapisDnevnika.objects.filter(pk=zapis.pk).update(snimak={"x": 1})),
            ("sirov UPDATE", lambda: connection.cursor().execute(
                "UPDATE igra_zapisdnevnika SET radnja = 'uloga_oduzeta' WHERE id = %s", [zapis.pk])),
        ):
            with self.subTest(opis):
                with self.assertRaisesMessage(IntegrityError, "dnevnik se ne menja"):
                    with transaction.atomic():
                        izmena()
        procitan = ZapisDnevnika.objects.get(pk=zapis.pk)
        self.assertEqual((procitan.radnja, procitan.snimak), ("moderator_aktiviran", {}))
        # DELETE nije zabranjen (flush, dnevnik_ocisti).
        ZapisDnevnika.objects.filter(pk=zapis.pk).delete()
        self.assertFalse(ZapisDnevnika.objects.exists())

    def test_okidac_postoji(self):
        # 0010 odbija izmenu, 0011 zamenu (INSERT sa id-jem postojeceg zapisa).
        okidaci = {"igra_zapis_bez_izmene": "BEFORE UPDATE", "igra_zapis_bez_zamene": "BEFORE INSERT"}
        with connection.cursor() as kursor:
            kursor.execute("SELECT name, tbl_name, sql FROM sqlite_master WHERE type = 'trigger' AND name IN (%s, %s)",
                           list(okidaci))
            redovi = {ime: (tabela, sql) for ime, tabela, sql in kursor.fetchall()}
        self.assertEqual(set(redovi), set(okidaci))
        for ime, dogadjaj in okidaci.items():
            with self.subTest(ime):
                tabela, sql = redovi[ime]
                self.assertEqual(tabela, "igra_zapisdnevnika")
                self.assertIn(dogadjaj, sql.upper())
                self.assertIn("RAISE(ABORT", sql.upper())

    def test_zamena_okidac(self):
        # Revizija 2026-11-11: sirov INSERT OR REPLACE sa id-jem postojeceg zapisa brisao je stari red i upisivao
        # nov, a okidac na UPDATE zamenu ne vidi.
        zapis = self.zapis_naloga()
        kolone = "id, kada, radnja, ko_id, nad_id, red, partija"
        kopija = f"({kolone}, snimak) SELECT {kolone}, '{{\"glavni\": true}}' FROM igra_zapisdnevnika WHERE id = %s"
        for opis, naredba in (("INSERT OR REPLACE", "INSERT OR REPLACE INTO"), ("REPLACE", "REPLACE INTO"),
                              ("INSERT OR IGNORE", "INSERT OR IGNORE INTO"), ("INSERT", "INSERT INTO")):
            with self.subTest(opis):
                with self.assertRaisesMessage(IntegrityError, "dnevnik se ne menja"):
                    with transaction.atomic():
                        connection.cursor().execute(f"{naredba} igra_zapisdnevnika {kopija}", [zapis.pk])
        procitan = ZapisDnevnika.objects.get(pk=zapis.pk)
        self.assertEqual((procitan.radnja, procitan.snimak, procitan.kada), ("moderator_aktiviran", {}, zapis.kada))
        self.assertEqual(ZapisDnevnika.objects.count(), 1)
        # Obican upis prolazi: ORM bez id-a i sirov INSERT sa novim id-jem; brisanje (dnevnik_ocisti, flush) takodje.
        drugi = self.zapis_naloga()
        with connection.cursor() as kursor:
            kursor.execute(f"INSERT INTO igra_zapisdnevnika ({kolone}, snimak) SELECT %s, kada, radnja, ko_id, "
                           f"nad_id, red, partija, snimak FROM igra_zapisdnevnika WHERE id = %s", [drugi.pk + 100, zapis.pk])
        self.assertEqual(ZapisDnevnika.objects.count(), 3)
        ZapisDnevnika.objects.filter(pk=zapis.pk).delete()
        self.assertEqual(sorted(ZapisDnevnika.objects.values_list("pk", flat=True)), [drugi.pk, drugi.pk + 100])

    def test_ogranicenja_tabele(self):
        # Brisanje nosi red i partiju; radnja nad nalogom nosi nad. Baza odbija i mimo full_clean.
        for opis, polja in (
            ("brisanje bez partije", {"radnja": "rezultat_obrisan", "red": 1}),
            ("brisanje sa nad", {"radnja": "link_obrisan", "red": 1, "partija": "x", "nad": self.mod}),
            ("nalog bez nad", {"radnja": "moderator_dodat"}),
            ("nepoznata radnja", {"radnja": "nesto", "nad": self.mod}),
        ):
            with self.subTest(opis):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        ZapisDnevnika(**polja).save(force_insert=True)
                with self.assertRaises(ValidationError):
                    ZapisDnevnika.objects.upisi(**polja)
        self.assertFalse(ZapisDnevnika.objects.exists())

    def test_komanda_upisuje_bez_ko(self):
        rezultat = upisi_red("Команда", 40)
        link = upisi_deljeno()
        sifarnik = upisi_red("Шкрабало", 30)
        call_command("rezultat_obrisi", str(rezultat.id), stdout=StringIO())
        call_command("deljeni_obrisi", str(link.id), stdout=StringIO())
        call_command("nepodobno_dodaj", "skrabalo", obrisi_rezultate=True, stdout=StringIO())
        zapisi = list(ZapisDnevnika.objects.order_by("id"))
        self.assertEqual([(z.radnja, z.ko_id, z.red) for z in zapisi], [
            ("rezultat_obrisan", None, rezultat.id), ("link_obrisan", None, link.id),
            ("rezultat_obrisan", None, sifarnik.id),
        ])
        self.assertEqual([z.partija for z in zapisi], [rezultat.partija, link.partija, sifarnik.partija])
        html = self.klijent_za(self.mod).get(reverse("moderator_dnevnik")).content.decode("utf-8")
        self.assertEqual(html.count("развијалац (команда)"), 3)

    def test_uloga_u_dnevniku(self):
        klijent = self.klijent_za(self.glavni)
        self.radnja(klijent, self.mod, "dodeli_ulogu")
        self.radnja(klijent, self.mod, "oduzmi_ulogu")
        self.assertEqual(
            list(ZapisDnevnika.objects.order_by("id").values_list("radnja", "ko", "nad")),
            [("uloga_dodeljena", self.glavni.pk, self.mod.pk), ("uloga_oduzeta", self.glavni.pk, self.mod.pk)],
        )
        odgovor = klijent.get(reverse("moderator_dnevnik"))
        html = odgovor.content.decode("utf-8")
        self.assertIn("додељена улога главног", html)
        self.assertIn("одузета улога главног", html)
        self.assertEqual([z["radnja"] for z in odgovor.context["zapisi"]], ["uloga_oduzeta", "uloga_dodeljena"])

    def test_redosled_i_kolone(self):
        sacuvan = utc(2026, 11, 9, 23, 30)
        ZapisDnevnika.objects.upisi(radnja="rezultat_obrisan", ko=self.mod, red=7, partija="p" * 64,
                                    kada=utc(2026, 11, 10, 13, 5),
                                    snimak={"ime": "Снимљени", "poeni": 55, "ocena": "skup",
                                            "datum": sacuvan.isoformat()})
        self.zapis_naloga(utc(2026, 11, 10, 12, 0))
        self.zapis_naloga(utc(2026, 11, 10, 14, 0), radnja="moderator_dodat")
        odgovor = self.klijent_za(self.mod).get(reverse("moderator_dnevnik"))
        zapisi = odgovor.context["zapisi"]
        self.assertEqual([z["radnja"] for z in zapisi], ["moderator_dodat", "rezultat_obrisan", "moderator_aktiviran"])
        for zapis in zapisi:
            self.assertEqual(set(zapis), KLJUCEVI_ZAPISA)
        # 13:05 UTC je 14:05 u Beogradu; datum snimka 23:30 UTC je sledeci dan.
        self.assertEqual(zapisi[1], {
            "kada": "10.11.2026 14:05", "ko": "Mod", "radnja": "rezultat_obrisan", "nad": None,
            "snimak": {"ime": "Снимљени", "poeni": 55, "ocena": OCENE_SR["skup"], "datum": "10.11.2026"},
        })
        self.assertEqual(zapisi[0]["snimak"], {"glavni": False})
        self.assertIsNone(zapisi[2]["snimak"])
        self.assertEqual((zapisi[2]["ko"], zapisi[2]["nad"]), ("Glavni", "Mod"))
        html = odgovor.content.decode("utf-8")
        self.assertIn("10.11.2026 14:05", html)
        self.assertIn("обрисан резултат", html)
        self.assertNotIn("p" * 64, html)
        # Engleski: format datuma iz tekstovi.FORMATI.
        en = self.klijent_za(self.mod, klijent=klijent_jezika("en"))
        zapisi_en = en.get(reverse("moderator_dnevnik")).context["zapisi"]
        self.assertEqual(zapisi_en[1]["kada"], "2026-11-10 14:05")
        self.assertEqual(zapisi_en[1]["snimak"]["datum"], "2026-11-10")

    def test_sto_najnovijih(self):
        pocetak = utc(2026, 1, 1)
        for broj in range(101):
            self.zapis_naloga(pocetak + datetime.timedelta(minutes=broj))
        zapisi = self.klijent_za(self.mod).get(reverse("moderator_dnevnik")).context["zapisi"]
        self.assertEqual(len(zapisi), 100)
        self.assertEqual(zapisi[0]["kada"], "01.01.2026 02:40")  # 01:40 UTC, najnoviji
        self.assertEqual(zapisi[-1]["kada"], "01.01.2026 01:01")  # najstariji (00:00 UTC) ispada

    def test_prazan_dnevnik(self):
        html = self.klijent_za(self.mod).get(reverse("moderator_dnevnik")).content.decode("utf-8")
        self.assertIn("Дневник је празан.", html)

    def test_partija_ne_izlazi(self):
        igrac = Client()
        stanje = self.postavi_zavrsenu("seme-partija-ne-izlazi", igrac)
        self.sacuvaj("Партија", igrac)
        token = token_iz_url(self.podeli_json(igrac)["url"])
        red = Rezultat.objects.get(ime="Партија")
        link = DeljeniRezultat.objects.get(token=token)
        klijent = self.klijent_za(self.glavni)
        strane = [klijent.get(reverse("moderator")),
                  klijent.post(reverse("moderator"), {"token": token}),
                  klijent.get(reverse("moderator_rezultat", args=[red.id])),
                  klijent.get(reverse("moderator_link", args=[link.id]))]
        klijent.post(reverse("moderator_rezultat", args=[red.id]))
        klijent.post(reverse("moderator_link", args=[link.id]))
        # Dokaz da vrednost postoji tamo gde sme da bude: dnevnik je cuva.
        self.assertEqual(set(ZapisDnevnika.objects.values_list("partija", flat=True)), {red.partija})
        self.assertEqual(len(red.partija), 64)
        strane.append(klijent.get(reverse("moderator_dnevnik")))
        strane.append(klijent.get(reverse("moderator")))
        for odgovor in strane:
            with self.subTest(adresa=odgovor.wsgi_request.path, metoda=odgovor.wsgi_request.method):
                self.assertEqual(odgovor.status_code, 200)
                for tajna in (red.partija, token, stanje["seme"]):
                    self.assertNotIn(tajna.encode(), odgovor.content)

    def test_moderator_vidi_ceo_dnevnik(self):
        klijent_glavnog = self.klijent_za(self.glavni)
        self.dodaj(klijent_glavnog, "Novi")
        brisanje.obrisi_rezultate([upisi_red("Туђи", 20).id], ko=self.glavni)
        call_command("deljeni_obrisi", str(upisi_deljeno().id), stdout=StringIO())
        odgovor = self.klijent_za(self.mod).get(reverse("moderator_dnevnik"))
        self.assertEqual(odgovor.status_code, 200)
        self.assertEqual(len(odgovor.context["zapisi"]), 3)
        self.assertEqual({z["radnja"] for z in odgovor.context["zapisi"]},
                         {"moderator_dodat", "rezultat_obrisan", "link_obrisan"})


class SkrivenoModeratorTests(OsnovaModeratora):
    def setUp(self):
        super().setUp()
        self.glavni = napravi_moderatora("Glavni", glavni=True)
        self.mod = napravi_moderatora("Mod")

    def test_bez_skrivenog(self):
        NepodobnoIme.objects.create(kljuc=STAVKA_SIFARNIKA)
        klijent = Client()
        stanje = self.postavi_zavrsenu("seme-moderator-skriveno-91c2", klijent)
        self.klijent_za(self.glavni, klijent=klijent)
        rezultat = upisi_red("Јавни", 70)
        link = upisi_deljeno()
        tajne = [stanje["seme"], STAVKA_SIFARNIKA, rezultat.partija, link.partija, link.token]
        # Dokaz da bi provera nasla seme: ono je u sesiji ovog pregledaca.
        self.assertEqual(klijent.session["igra"]["seme"], stanje["seme"])
        strane = {
            "pregled": klijent.get(reverse("moderator")),
            "potvrda rezultata": klijent.get(reverse("moderator_rezultat", args=[rezultat.id])),
            "potvrda linka": klijent.get(reverse("moderator_link", args=[link.id])),
            "dnevnik": klijent.get(reverse("moderator_dnevnik")),
            "nalozi": klijent.get(reverse("moderator_nalozi")),
            "nalog": klijent.get(reverse("moderator_nalozi_nalog", args=[self.mod.pk])),
            "lozinka": klijent.get(reverse("moderator_lozinka")),
        }
        for opis, odgovor in strane.items():
            with self.subTest(opis):
                self.assertEqual(odgovor.status_code, 200)
                for tajna in tajne:
                    self.assertNotIn(tajna.encode(), odgovor.content)

    def test_imena_escapeovana(self):
        klijent = self.klijent_za(self.glavni)
        for ime in XSS_IMENA:
            with self.subTest(ime=ime):
                link = upisi_deljeno()
                rezultat = Rezultat.objects.create(ime=ime, poeni=link.zavrsni["poeni"],
                                                   ocena=link.zavrsni["ocena"], pravila=p.PRAVILA_TEKUCA,
                                                   partija=link.partija)
                bezbedno = html_modul.escape(ime, quote=False).encode()
                strane = [klijent.get(reverse("moderator")),
                          klijent.post(reverse("moderator"), {"token": link.token}),
                          klijent.get(reverse("moderator_rezultat", args=[rezultat.id])),
                          klijent.get(reverse("moderator_link", args=[link.id]))]
                klijent.post(reverse("moderator_link", args=[link.id]))
                klijent.post(reverse("moderator_rezultat", args=[rezultat.id]))
                strane.append(klijent.get(reverse("moderator_dnevnik")))
                for odgovor in strane:
                    self.assertNotIn(ime.encode(), odgovor.content)
                    self.assertIn(bezbedno, odgovor.content)
        # Korisnicko ime ne prima ove znakove (nalozi i nalog): proverava test_dodaj_odbija.


@override_settings(PASSWORD_HASHERS=BRZI_HES)
class KomandeModeratoraTests(TestCase):
    def setUp(self):
        obrisi_brojace()

    def komanda(self, *argumenti, lozinke=(), **opcije):
        izlaz = StringIO()
        with mock.patch("getpass.getpass", side_effect=list(lozinke)):
            call_command(*argumenti, stdout=izlaz, **opcije)
        return izlaz.getvalue()

    def test_moderator_dodaj(self):
        with self.assertRaisesMessage(CommandError, "--glavni"):
            self.komanda("moderator_dodaj", "Prvi")
        self.assertFalse(User.objects.exists())
        izlaz = self.komanda("moderator_dodaj", "Prvi", glavni=True, lozinke=[LOZINKA, LOZINKA])
        self.assertIn("Prvi", izlaz)
        self.assertNotIn(LOZINKA, izlaz)
        prvi = User.objects.get(username="Prvi")
        self.assertEqual(nalozi.uloga(prvi), "glavni")
        self.assertTrue(prvi.nalog_moderatora.mora_promeniti)
        self.assertTrue(prvi.check_password(LOZINKA))
        self.assertEqual(list(ZapisDnevnika.objects.values_list("radnja", "ko", "nad", "snimak")),
                         [("moderator_dodat", None, prvi.pk, {"glavni": True})])
        self.komanda("moderator_dodaj", "Drugi", lozinke=[LOZINKA, LOZINKA])
        self.assertEqual(nalozi.uloga(User.objects.get(username="Drugi")), "moderator")
        pre = otisak_baze()
        for opis, ime, lozinke in (("isto ime", "prvi", []), ("kratka lozinka", "Treci", ["Kratka-1"] * 2),
                                   ("ne poklapaju se", "Treci", [LOZINKA, LOZINKA2]),
                                   ("nedozvoljen znak", "a b", [])):
            with self.subTest(opis):
                with self.assertRaises(CommandError):
                    self.komanda("moderator_dodaj", ime, lozinke=lozinke)
        self.assertEqual(otisak_baze(), pre)

    def test_moderator_lozinka_otkljucava(self):
        glavni = napravi_moderatora("Glavni", glavni=True)
        mod = napravi_moderatora("Mod")
        self.komanda("moderator_lozinka", "mod", lozinke=[LOZINKA2, LOZINKA2])
        mod = User.objects.get(pk=mod.pk)
        self.assertTrue(mod.check_password(LOZINKA2))
        self.assertTrue(mod.nalog_moderatora.mora_promeniti)
        nalozi.deaktiviraj(glavni, mod)
        izlaz = self.komanda("moderator_lozinka", "Mod", lozinke=[LOZINKA3, LOZINKA3])
        self.assertIn("aktiviran", izlaz)
        mod = User.objects.get(pk=mod.pk)
        self.assertTrue(mod.is_active)
        self.assertEqual(nalozi.uloga(mod), "moderator")
        self.assertEqual(list(ZapisDnevnika.objects.order_by("id").values_list("radnja", "ko")),
                         [("lozinka_postavljena", None), ("moderator_deaktiviran", glavni.pk),
                          ("moderator_aktiviran", None)])
        with self.assertRaises(CommandError):
            self.komanda("moderator_lozinka", "NePostoji")

    def test_moderator_glavni(self):
        glavni = napravi_moderatora("Glavni", glavni=True)
        mod = napravi_moderatora("Mod")
        with self.assertRaisesMessage(CommandError, "Mora ostati bar jedan aktivan glavni"):
            self.komanda("moderator_glavni", "Glavni", oduzmi=True)
        self.assertEqual(nalozi.uloga(User.objects.get(pk=glavni.pk)), "glavni")
        self.komanda("moderator_glavni", "Mod")
        self.assertEqual(nalozi.uloga(User.objects.get(pk=mod.pk)), "glavni")
        self.komanda("moderator_glavni", "Glavni", oduzmi=True)
        self.assertEqual(nalozi.uloga(User.objects.get(pk=glavni.pk)), "moderator")
        self.assertEqual(list(ZapisDnevnika.objects.order_by("id").values_list("radnja", "ko", "nad")),
                         [("uloga_dodeljena", None, mod.pk), ("uloga_oduzeta", None, glavni.pk)])

    def test_moderator_deaktiviraj(self):
        napravi_moderatora("Glavni", glavni=True)
        mod = napravi_moderatora("Mod")
        with self.assertRaisesMessage(CommandError, "Mora ostati bar jedan aktivan glavni"):
            self.komanda("moderator_deaktiviraj", "Glavni")
        izlaz = self.komanda("moderator_deaktiviraj", "Mod")
        self.assertIn("Aktivnih moderatora: 1, aktivnih glavnih: 1.", izlaz)
        self.assertFalse(User.objects.get(pk=mod.pk).is_active)

    def test_moderatori(self):
        self.assertIn("Nema moderatora", self.komanda("moderatori"))
        napravi_moderatora("Glavni", glavni=True)
        napravi_moderatora("Mod", mora_promeniti=True)
        User.objects.create_superuser("Super", password=LOZINKA)
        redovi = self.komanda("moderatori").splitlines()
        self.assertEqual(redovi[0], "ime='Glavni' aktivan=da glavni=da mora_promeniti=ne poslednja_prijava=-")
        self.assertEqual(redovi[1], "ime='Mod' aktivan=da glavni=ne mora_promeniti=da poslednja_prijava=-")
        self.assertIn("UPOZORENJE: 'Super' je superuser", redovi[-1])

    def test_dnevnik_ocisti(self):
        mod = napravi_moderatora("Mod")
        sada = timezone.now()
        stari = ZapisDnevnika.objects.upisi(radnja="moderator_aktiviran", nad=mod,
                                            kada=sada - datetime.timedelta(days=366))
        novi = ZapisDnevnika.objects.upisi(radnja="moderator_aktiviran", nad=mod,
                                           kada=sada - datetime.timedelta(days=364))
        for dana in (14, 1, 0):
            with self.subTest(dana=dana):
                with self.assertRaises(CommandError):
                    self.komanda("dnevnik_ocisti", dana=dana)
                self.assertEqual(ZapisDnevnika.objects.count(), 2)
        self.assertIn("obrisano zapisa: 1", self.komanda("dnevnik_ocisti"))
        self.assertEqual(list(ZapisDnevnika.objects.values_list("pk", flat=True)), [novi.pk])
        self.assertFalse(ZapisDnevnika.objects.filter(pk=stari.pk).exists())
        self.assertIn("obrisano zapisa: 1", self.komanda("dnevnik_ocisti", dana=15))


class JezikModeratoraTests(OsnovaModeratora):
    """Svaka moderatorska strana i 403 na sr i en, bez neprevedenog teksta (plan 14.8, red jezik)."""

    # Imena u podacima su latinicom i ascii, pa ne lice ni na srpski ni na engleski tekst strane.
    IMENA = {"Glavni", "Mod", "Rezultatko", "Linkic", "Novajlija", "Neaktivan", "Blokiran"}

    def setUp(self):
        super().setUp()
        self.glavni = napravi_moderatora("Glavni", glavni=True)
        self.mod = napravi_moderatora("Mod")
        self.novajlija = napravi_moderatora("Novajlija", mora_promeniti=True)
        self.neaktivan = napravi_moderatora("Neaktivan")
        User.objects.filter(pk=self.neaktivan.pk).update(is_active=False)
        self.rezultat = upisi_red("Rezultatko", 70)
        self.link = upisi_deljeno()
        Rezultat.objects.create(ime="Linkic", poeni=self.link.zavrsni["poeni"], ocena=self.link.zavrsni["ocena"],
                                pravila=p.PRAVILA_TEKUCA, partija=self.link.partija)
        # Po jedan zapis svake radnje.
        for radnja in ("moderator_dodat", "moderator_deaktiviran", "moderator_aktiviran", "lozinka_postavljena",
                       "lozinka_promenjena", "uloga_dodeljena", "uloga_oduzeta"):
            ZapisDnevnika.objects.upisi(radnja=radnja, ko=self.glavni, nad=self.mod,
                                        snimak={"glavni": True} if radnja == "moderator_dodat" else {})
        brisanje.obrisi_rezultate([upisi_red("Rezultatko", 30).id], ko=None)
        brisanje.obrisi_deljene([upisi_deljeno().id], ko=self.mod)
        # Prijava imena: jedno ime ceka odluku (odeljak na pregledu), jedno je ostavljeno (zapis u dnevniku).
        upisi_prijavu(self.rezultat)
        ostavljen = upisi_red("Rezultatko", 20)
        upisi_prijavu(ostavljen)
        brisanje.odbaci_prijave([ostavljen.id], ko=self.mod)

    def strane(self, jezik):
        glavni = self.klijent_za(self.glavni, klijent=klijent_jezika(jezik))
        mod = self.klijent_za(self.mod, klijent=klijent_jezika(jezik))
        novajlija = self.klijent_za(self.novajlija, klijent=klijent_jezika(jezik))
        anon = klijent_jezika(jezik)
        strane = {
            "prijava": anon.get(reverse("moderator_prijava")),
            "prijava greska": self.prijavi("Mod", "pogresna", anon),
            "pregled": glavni.get(reverse("moderator") + "?poruka=obrisano"),
            "pregled vec obrisano": glavni.get(reverse("moderator") + "?poruka=vec_obrisano"),
            "pregled ostavljeno": glavni.get(reverse("moderator") + "?poruka=ostavljeno"),
            "pregled vec reseno": glavni.get(reverse("moderator") + "?poruka=vec_reseno"),
            "pretraga": glavni.post(reverse("moderator"), {"token": self.link.token}),
            "pretraga bez pogotka": glavni.post(reverse("moderator"), {"token": "x" * 22}),
            "potvrda rezultata": glavni.get(reverse("moderator_rezultat", args=[self.rezultat.id])),
            "potvrda linka": glavni.get(reverse("moderator_link", args=[self.link.id])),
            "dnevnik": mod.get(reverse("moderator_dnevnik")),
            "lozinka obavezna": novajlija.get(reverse("moderator_lozinka")),
            "lozinka greske": self.promeni(mod, "pogresna", "kratka", "druga"),
            "lozinka ista": self.promeni(mod, LOZINKA, LOZINKA),
            "nalozi": glavni.get(reverse("moderator_nalozi")),
            "nalozi greske": self.dodaj(glavni, "mod", lozinka="12345", lozinka2="6789", moja="pogresna"),
            "nalog": glavni.get(reverse("moderator_nalozi_nalog", args=[self.mod.pk])),
            "nalog greska": self.radnja(glavni, self.mod, "lozinka", moja="", lozinka1="kratka"),
            "nalog neaktivan": glavni.get(reverse("moderator_nalozi_nalog", args=[self.neaktivan.pk])),
            "nalog nije dozvoljeno": self.radnja(glavni, self.mod, "aktiviraj"),
            "zabranjeno": mod.get(reverse("moderator_nalozi")),
        }
        for _ in range(settings.PRIJAVA_POKUSAJA):
            self.prijavi("Blokiran", "pogresna", anon)
        strane["prijava blokada"] = self.prijavi("Blokiran", "pogresna", anon)
        obrisi_brojace()
        return strane

    def test_strane_sr(self):
        for opis, odgovor in self.strane("sr").items():
            with self.subTest(opis):
                self.assertIn(odgovor.status_code, (200, 403))
                html = odgovor.content.decode("utf-8")
                self.assertIn('<html lang="sr">', html)
                tekst = vidljiv_tekst(html)
                latinica = set(re.findall(r"[A-Za-z]{2,}", tekst)) - self.IMENA - {"English"}
                self.assertEqual(latinica, set(), tekst)

    def test_strane_en(self):
        for opis, odgovor in self.strane("en").items():
            with self.subTest(opis):
                self.assertIn(odgovor.status_code, (200, 403))
                html = odgovor.content.decode("utf-8")
                self.assertIn('<html lang="en">', html)
                tekst = vidljiv_tekst(html)
                self.assertEqual(set(CIRILICA.findall(tekst)) - {"Српски"}, set(), tekst)

    def test_kljucni_tekst_en(self):
        strane = self.strane("en")
        for opis, ocekivano in (
            ("prijava greska", "Wrong username or password."),
            ("zabranjeno", "Only the head moderator can see this page."),
            ("pregled", "Deleted."),
            ("pregled vec obrisano", "This has already been deleted."),
            ("pregled", "Reported names"),
            ("pregled", "Number of reports"),
            ("pregled ostavljeno", "The name was kept and the reports were removed."),
            ("pregled vec reseno", "These reports have already been resolved."),
            ("dnevnik", "name report dismissed"),
            ("lozinka obavezna", "You must change your password before continuing."),
            ("nalog nije dozvoljeno", "Action not allowed."),
            ("dnevnik", "developer (command)"),
            ("prijava blokada", "Too many failed attempts. Try again in 15 minutes."),
            ("nalozi greske", "Wrong password."),
            ("lozinka ista", ISTA_LOZINKA_EN),
        ):
            with self.subTest(opis):
                self.assertIn(ocekivano, vidljiv_tekst(strane[opis].content.decode("utf-8")))
        self.assertEqual(strane["zabranjeno"].status_code, 403)


# ---------- javna isporuka (plan 15.4-15.7, 15.11 T4, ugovor 15.12) ----------

PROBNI_HOST = "orkestrator.example"
PROBNO_POREKLO = f"https://{PROBNI_HOST}"
# Plan 15.4, vrednost CSP-a, doslovno.
CSP_OCEKIVANO = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; "
    "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)
# Zahtev kakav stize iza Nginx-a: Host domena i prepisan X-Forwarded-Proto (plan 15.4, 15.7).
IZA_NGINXA = {"host": PROBNI_HOST, "x-forwarded-proto": "https"}
URL_DELJENJA_HTTPS = re.compile(r"https://orkestrator\.example/r/([A-Za-z0-9_-]{22})/")


def probno_okruzenje(baza):
    """Promenljive iz ugovora 15.12, sa vrednostima koje check --deploy prihvata (kljuc 70 znakova, nasumican)."""
    return {
        "DJANGO_SECRET_KEY": "probni-" + secrets.token_urlsafe(48),
        "DJANGO_ALLOWED_HOSTS": PROBNI_HOST,
        "DJANGO_CSRF_TRUSTED_ORIGINS": PROBNO_POREKLO,
        "DJANGO_BAZA": str(baza),
        "DJANGO_HSTS_SEKUNDI": "3600",
    }


def pokreni_pod_prod(argumenti, okruzenje):
    """Nov proces pod settings_prod: od okruzenja ovog procesa samo ono sto nije DJANGO_*, pa dato okruzenje."""
    cisto = {ime: vrednost for ime, vrednost in os.environ.items() if not ime.startswith("DJANGO_")}
    cisto.update(okruzenje)
    cisto["DJANGO_SETTINGS_MODULE"] = "orkestrator.settings_prod"
    cisto["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, *argumenti], cwd=settings.BASE_DIR, env=cisto, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=120,
    )


def ucitaj_prod(okruzenje):
    """settings_prod uvezen u ovom procesu pod datim okruzenjem; modul ne ostaje u sys.modules."""
    with mock.patch.dict(os.environ, okruzenje):
        sys.modules.pop("orkestrator.settings_prod", None)
        try:
            return importlib.import_module("orkestrator.settings_prod")
        finally:
            sys.modules.pop("orkestrator.settings_prod", None)


def prod_razlike(prod):
    """Sve sto settings_prod menja u odnosu na settings.py, za override_settings.

    Bez baze (testovi ostaju na svojoj), loga (FilterLogaTests ga gradi iz istog recnika) i kljuca (sesije testa).
    """
    osnova = importlib.import_module("orkestrator.settings")
    return {
        ime: getattr(prod, ime)
        for ime in dir(prod)
        if ime.isupper()
        and ime not in {"DATABASES", "LOGGING", "SECRET_KEY"}
        and getattr(prod, ime) != getattr(osnova, ime, object())
    }


class SettingsProdTests(TestCase):
    """Plan 15.4 i 15.11 (T1): server ne krece bez obaveznog podatka; check --deploy bez nalaza."""

    UVOZ = ["-c", "import orkestrator.settings_prod as s; print('UVEZENO', s.DEBUG, s.ALLOWED_HOSTS)"]
    PROVERA = ["manage.py", "check", "--deploy", "--fail-level", "WARNING"]
    NEISPRAVNO = (
        ("DJANGO_SECRET_KEY", None),
        ("DJANGO_SECRET_KEY", "   "),
        ("DJANGO_ALLOWED_HOSTS", None),
        ("DJANGO_ALLOWED_HOSTS", " , "),
        ("DJANGO_BAZA", None),
        ("DJANGO_BAZA", " "),
        ("DJANGO_CSRF_TRUSTED_ORIGINS", "http://orkestrator.example"),
        ("DJANGO_CSRF_TRUSTED_ORIGINS", "orkestrator.example"),
        ("DJANGO_CSRF_TRUSTED_ORIGINS", "https://orkestrator.example, http://drugi.example"),
        ("DJANGO_HSTS_SEKUNDI", "jedan sat"),
        ("DJANGO_HSTS_SEKUNDI", "-1"),
        ("DJANGO_HSTS_SEKUNDI", ""),
        ("DJANGO_HSTS_SEKUNDI", "²"),
        ("DJANGO_HSTS_SEKUNDI", "３６００"),
        # Isti niz cita i Nginx (15-provera-okruzenja.sh): bez skracivanja razmaka, bez 0 i bez ubacene direktive.
        ("DJANGO_HSTS_SEKUNDI", "0"),
        ("DJANGO_HSTS_SEKUNDI", "000"),
        # Vodeca nula: Django bi slao max-age=3600, a Nginx doslovno max-age=03600 (provera.sh poredi zaglavlja).
        ("DJANGO_HSTS_SEKUNDI", "03600"),
        ("DJANGO_HSTS_SEKUNDI", " 3600"),
        ("DJANGO_HSTS_SEKUNDI", "3600 "),
        ("DJANGO_HSTS_SEKUNDI", "3600\n"),
        ("DJANGO_HSTS_SEKUNDI", '3600" always; add_header X-Ubaceno "da'),
    )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        privremeni = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.addClassCleanup(privremeni.cleanup)
        cls.okruzenje = probno_okruzenje(pathlib.Path(privremeni.name) / "db.sqlite3")

    def test_uvoz_sa_probnim_okruzenjem(self):
        # Kontrola za test ispod: isti poziv sa svim podacima prolazi, pa pad dolazi od podatka koji fali.
        proces = pokreni_pod_prod(self.UVOZ, self.okruzenje)
        self.assertEqual(proces.returncode, 0, proces.stderr[-800:])
        self.assertIn("UVEZENO False ['orkestrator.example']", proces.stdout)

    def test_uvoz_pada_bez_obaveznog_ili_sa_neispravnim(self):
        for ime, vrednost in self.NEISPRAVNO:
            with self.subTest(ime=ime, vrednost=vrednost):
                okruzenje = dict(self.okruzenje)
                if vrednost is None:
                    del okruzenje[ime]
                else:
                    okruzenje[ime] = vrednost
                proces = pokreni_pod_prod(self.UVOZ, okruzenje)
                self.assertNotEqual(proces.returncode, 0)
                self.assertNotIn("UVEZENO", proces.stdout)
                poslednji = proces.stderr.strip().splitlines()[-1]
                self.assertTrue(poslednji.startswith("django.core.exceptions.ImproperlyConfigured: "), poslednji)
                self.assertIn(ime, poslednji)  # poruka imenuje promenljivu
                self.assertNotIn(self.okruzenje["DJANGO_SECRET_KEY"], proces.stderr)  # i ne ispisuje kljuc

    def test_check_deploy_bez_nalaza(self):
        proces = pokreni_pod_prod(self.PROVERA, self.okruzenje)
        self.assertEqual(proces.returncode, 0, proces.stdout + proces.stderr)
        self.assertIn("System check identified no issues", proces.stdout)

    def test_check_deploy_kontrola_kratak_kljuc(self):
        # Dokaz da provera gore zaista nalazi: kljuc kraci od 50 znakova je security.W009, i izlazni kod vise nije 0.
        # (Ranije je kontrola bila HSTS 0, ali 0 sada odbija vec uvoz settings_prod; vidi NEISPRAVNO.)
        proces = pokreni_pod_prod(self.PROVERA, {**self.okruzenje, "DJANGO_SECRET_KEY": "kratak-probni-kljuc"})
        self.assertNotEqual(proces.returncode, 0)
        self.assertIn("security.W009", proces.stdout + proces.stderr)

    def test_hsts_sekundi_iz_okruzenja(self):
        # Probna vrednost 3600 je ista kao podrazumevana, pa se vrednost iz okruzenja dokazuje drugom: drugi korak
        # HSTS-a (DEPLOY.md 11). Bez includeSubDomains i preload ni posle podizanja.
        prod = ucitaj_prod({**self.okruzenje, "DJANGO_HSTS_SEKUNDI": "31536000"})
        self.assertEqual(prod.SECURE_HSTS_SECONDS, 31536000)
        self.assertIs(prod.SECURE_HSTS_INCLUDE_SUBDOMAINS, False)
        self.assertIs(prod.SECURE_HSTS_PRELOAD, False)

    def test_baza_csp_i_log_na_serveru(self):
        prod = ucitaj_prod(self.okruzenje)
        osnova = importlib.import_module("orkestrator.settings")
        self.assertIs(prod.DEBUG, False)
        self.assertEqual(prod.DATABASES["default"]["NAME"], self.okruzenje["DJANGO_BAZA"])
        # WAL, timeout i IMMEDIATE iz settings.py vaze i na serveru.
        self.assertEqual(prod.DATABASES["default"]["OPTIONS"], osnova.DATABASES["default"]["OPTIONS"])
        self.assertEqual(prod.DATABASES["default"]["OPTIONS"]["init_command"], "PRAGMA journal_mode=WAL")
        self.assertEqual(prod.SECURE_CSP, osnova.SECURE_CSP)
        self.assertIn("django.middleware.csp.ContentSecurityPolicyMiddleware", prod.MIDDLEWARE)
        # Svaki zapis servera ide kroz filter loga (plan 15.4); bez mejla.
        log = prod.LOGGING
        self.assertEqual(log["filters"]["bez_tajni"]["()"], "orkestrator.greske.FilterLoga")
        self.assertEqual(list(log["handlers"]), ["stdout"])
        self.assertEqual(log["handlers"]["stdout"]["filters"], ["bez_tajni"])
        self.assertEqual(log["root"]["handlers"], ["stdout"])
        for ime in ("django", "django.request", "django.security"):
            self.assertEqual(log["loggers"][ime]["handlers"], ["stdout"], ime)
        self.assertEqual(log["loggers"]["django.request"]["level"], "ERROR")
        self.assertFalse(getattr(prod, "ADMINS", []))


class ProdukcijaTests(OsnovaPrikaza):
    """Vrednosti iz settings_prod (plan 15.4, 15.7, 15.11 T4): iza Nginx-a, https."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.razlike = prod_razlike(ucitaj_prod(probno_okruzenje("/data/db.sqlite3")))

    def setUp(self):
        super().setUp()
        izmena = override_settings(**self.razlike)
        izmena.enable()
        self.addCleanup(izmena.disable)

    def test_link_za_deljenje_je_https_na_domenu(self):
        klijent = Client(enforce_csrf_checks=True, headers=IZA_NGINXA)
        self.assertEqual(klijent.get("/").status_code, 200)  # sesija i csrftoken, kao u pregledacu
        self.postavi_zavrsenu("seme-prod-link", klijent=klijent)
        odgovor = klijent.post(
            reverse("podeli"), headers={"x-csrftoken": klijent.cookies["csrftoken"].value, "origin": PROBNO_POREKLO}
        )
        self.assertEqual(odgovor.status_code, 200, odgovor.content[:300])
        url = json.loads(odgovor.content)["url"]
        pogodak = URL_DELJENJA_HTTPS.fullmatch(url)
        self.assertIsNotNone(pogodak, url)
        self.assertTrue(DeljeniRezultat.objects.filter(token=pogodak.group(1)).exists())
        self.assertEqual(klijent.get(urllib.parse.urlsplit(url).path).status_code, 200)

    def test_kolacici_nose_secure_i_hsts(self):
        klijent = Client(headers=IZA_NGINXA)
        odgovor = klijent.get("/")
        self.assertEqual(odgovor.status_code, 200)
        for ime in (settings.SESSION_COOKIE_NAME, settings.CSRF_COOKIE_NAME):
            with self.subTest(ime):
                self.assertIn(ime, odgovor.cookies)
                self.assertIs(odgovor.cookies[ime]["secure"], True)
        jezik = klijent.post(reverse("jezik"), {"language": "en", "next": "/"})
        self.assertEqual(jezik.status_code, 302)
        self.assertIs(jezik.cookies[settings.LANGUAGE_COOKIE_NAME]["secure"], True)
        # Prvi korak HSTS-a (plan 15.4): 3600 s, bez includeSubDomains i bez preload.
        self.assertEqual(odgovor["Strict-Transport-Security"], "max-age=3600")

    def test_http_bez_zaglavlja_preusmerava_na_https(self):
        odgovor = Client(headers={"host": PROBNI_HOST}).get("/r/nesto/?jezik=en")
        self.assertEqual(odgovor.status_code, 301)
        self.assertEqual(odgovor["Location"], "https://orkestrator.example/r/nesto/?jezik=en")
        self.assertEqual(len(odgovor.cookies), 0)

    def test_strani_host_400_bez_linka(self):
        klijent = Client(headers=IZA_NGINXA)
        klijent.get("/")
        self.postavi_zavrsenu("seme-prod-strani-host", klijent=klijent)
        with self.assertLogs("django.security.DisallowedHost", "ERROR"):
            odgovor = klijent.post(reverse("podeli"), headers={"host": "napadac.example"})
        self.assertEqual(odgovor.status_code, 400)
        self.assertEqual(naslov_strane(odgovor), "Захтев није исправан · Оркестратор")
        self.assertNotIn(b"napadac", odgovor.content)
        self.assertEqual(DeljeniRezultat.objects.count(), 0)

    def test_zdravlje_iza_nginxa_i_bez_proto(self):
        # Provera iz kontejnera salje Host i X-Forwarded-Proto (plan 15.5); bez proto dobija 301.
        odgovor = Client(headers=IZA_NGINXA).get(reverse("zdravlje"))
        self.assertEqual((odgovor.status_code, odgovor.content, len(odgovor.cookies)), (200, b'{"ok": true}', 0))
        self.assertEqual(Client(headers={"host": PROBNI_HOST}).get(reverse("zdravlje")).status_code, 301)


class ZdravljeTests(OsnovaPrikaza):
    """Plan 15.5, ugovor 15.12: GET i HEAD, 200 {"ok": true}, bez sesije i bez kolacica."""

    def test_get_200_bez_kolacica_i_bez_sesije(self):
        pre = Session.objects.count()
        with CaptureQueriesContext(connection) as upiti:
            odgovor = Client().get("/zdravlje/")
        self.assertEqual(odgovor.status_code, 200)
        self.assertEqual(odgovor["Content-Type"], "application/json")
        self.assertEqual(odgovor.content, b'{"ok": true}')
        self.assertEqual(len(odgovor.cookies), 0)
        self.assertNotIn("Cookie", odgovor.get("Vary", ""))
        self.assertIn("no-cache", odgovor["Cache-Control"])
        self.assertEqual(Session.objects.count(), pre)
        # Tacno jedno citanje baze, i to tabele igre, ne sesije.
        self.assertEqual(len(upiti.captured_queries), 1, upiti.captured_queries)
        self.assertIn('"igra_rezultat"', upiti.captured_queries[0]["sql"])

    def test_postojeca_sesija_netaknuta(self):
        self.postavi_igru("seme-zdravlje")
        kljuc = self.client.session.session_key
        pre = Session.objects.get(session_key=kljuc).expire_date
        odgovor = self.client.get("/zdravlje/")
        self.assertEqual(odgovor.status_code, 200)
        self.assertEqual(len(odgovor.cookies), 0)
        self.assertEqual(Session.objects.get(session_key=kljuc).expire_date, pre)

    def test_head_200_bez_kolacica(self):
        pre = Session.objects.count()
        odgovor = Client().head("/zdravlje/")
        self.assertEqual(odgovor.status_code, 200)
        self.assertEqual(odgovor["Content-Type"], "application/json")
        self.assertEqual(len(odgovor.cookies), 0)
        self.assertEqual(Session.objects.count(), pre)

    def test_post_405(self):
        odgovor = Client().post("/zdravlje/")
        self.assertEqual(odgovor.status_code, 405)
        self.assertEqual(odgovor["Allow"], "GET, HEAD")
        self.assertEqual(len(odgovor.cookies), 0)


NASLOVI_GRESAKA = {
    "400": {"sr": ("Захтев није исправан · Оркестратор", "Захтев није исправан."),
            "en": ("Invalid request · Orchestrator", "This request is not valid.")},
    "403": {"sr": ("Забрањено · Оркестратор", "Приступ није дозвољен."),
            "en": ("Forbidden · Orchestrator", "Access is not allowed.")},
    "403_csrf": {"sr": ("Страна је истекла · Оркестратор", "Страна је истекла."),
                 "en": ("Page expired · Orchestrator", "This page has expired.")},
    "404": {"sr": ("Страна није пронађена · Оркестратор", "Ова страна не постоји."),
            "en": ("Page not found · Orchestrator", "This page does not exist.")},
    "500": {"sr": ("Грешка · Оркестратор", "Нешто је пошло по злу."),
            "en": ("Error · Orchestrator", "Something went wrong.")},
}
H1_GRESKE = re.compile(r'<h1 class="nedostupno-naslov">(.*?)</h1>', re.S)
# Sta odaje tehnicku stranu Django-a ili njegovu podrazumevanu stranu greske.
TEHNICKI_DETALJI = (
    "Traceback", "Django", "DEBUG", "CSRF", "csrf", "Exception", "URLconf", "urlpatterns", "Request Method",
    "settings.py", "reason", "moderator/", "Not Found", "Bad Request", "Server Error", "Internal",
)
SKRIPTA_TAG = re.compile(r"<script\b([^>]*)>", re.I)


def inline_nalazi(html):
    """Sve sto CSP iz plana 15.4 blokira: ugradjena skripta, style=, on*=, <style>, javascript:."""
    nalazi = [f"<script{a}>" for a in SKRIPTA_TAG.findall(html) if 'type="application/json"' not in a and "src=" not in a]
    nalazi += re.findall(r"<[a-z][^>]*\sstyle\s*=[^>]*>", html, re.I)
    nalazi += re.findall(r"<[a-z][^>]*\son[a-z]+\s*=[^>]*>", html, re.I)
    nalazi += re.findall(r"<style\b|javascript:", html, re.I)
    return nalazi


@override_settings(DEBUG=False)
class StraneGresakaTests(OsnovaPrikaza):
    """Plan 15.4: 400, 403, 403_csrf, 404 i 500 na sr i en, bez tehnickih detalja i bez odjeka unosa."""

    def proveri_stranu(self, odgovor, status, vrsta, jezik, tajne=()):
        self.assertEqual(odgovor.status_code, status)
        self.assertEqual(odgovor["Content-Type"], "text/html; charset=utf-8")
        html = odgovor.content.decode("utf-8")
        naslov, h1 = NASLOVI_GRESAKA[vrsta][jezik]
        self.assertEqual(jezik_strane(odgovor), jezik)
        self.assertEqual(naslov_strane(odgovor), naslov)
        self.assertEqual(H1_GRESKE.findall(html), [h1])
        for rec in (*TEHNICKI_DETALJI, *tajne):
            self.assertNotIn(rec, html)
        self.assertEqual(inline_nalazi(html), [])
        self.assertEqual(odgovor["Content-Security-Policy"], CSP_OCEKIVANO)
        return html

    def test_400_strani_host(self):
        for jezik in JEZICI:
            with self.subTest(jezik):
                with self.assertNumQueries(0), self.assertLogs("django.security.DisallowedHost", "ERROR"):
                    odgovor = klijent_jezika(jezik).get("/", headers={"host": "napadac-qzx.example"})
                self.proveri_stranu(odgovor, 400, "400", jezik, tajne=("napadac", "qzx"))
                self.assertEqual(len(odgovor.cookies), 0)

    def test_403(self):
        for jezik in JEZICI:
            with self.subTest(jezik):
                with mock.patch("igra.views._stanje", side_effect=PermissionDenied("tajni-razlog-qzx403")):
                    with self.assertLogs("django.request", "WARNING"):
                        odgovor = klijent_jezika(jezik).get("/")
                self.proveri_stranu(odgovor, 403, "403", jezik, tajne=("tajni-razlog", "qzx403"))

    def test_403_csrf_nova_i_prijava(self):
        for jezik, putanja, sa_kolacicem in itertools.product(JEZICI, ("/nova/", PRIJAVA_PUTANJA), (False, True)):
            with self.subTest(jezik=jezik, putanja=putanja, sa_kolacicem=sa_kolacicem):
                klijent = klijent_jezika(jezik, enforce_csrf_checks=True)
                if sa_kolacicem:
                    klijent.get("/")  # csrftoken kolacic postoji, token u POST-u ne
                    self.assertIn(settings.CSRF_COOKIE_NAME, klijent.cookies)
                self.postavi_igru("seme-csrf-qzx", klijent)
                pre = self.stanje(klijent)
                with self.assertLogs("django.security.csrf", "WARNING"):
                    odgovor = klijent.post(putanja, {"username": "Mod", "password": "lozinka-qzx"})
                self.proveri_stranu(odgovor, 403, "403_csrf", jezik, tajne=("cookie", "token", "lozinka-qzx"))
                self.assertEqual(self.stanje(klijent), pre)  # nova igra nije pocela
                self.assertEqual(PokusajPrijave.objects.count(), 0)  # prijava nije pokusana

    def test_404_nepoznata_putanja_bez_odjeka(self):
        for jezik in JEZICI:
            with self.subTest(jezik):
                with self.assertNumQueries(0), self.assertLogs("django.request", "WARNING"):
                    odgovor = klijent_jezika(jezik).get("/nepostoji-qzx7/<b>x</b>/?q=upit-qzx")
                self.proveri_stranu(odgovor, 404, "404", jezik, tajne=("nepostoji", "qzx", "&lt;b"))

    def test_404_kontrola_tehnicka_strana_odaje_rute(self):
        # Dokaz da bi provera nasla spisak ruta i odjek putanje: pod DEBUG = True ih Django ispisuje.
        with override_settings(DEBUG=True), self.assertLogs("django.request", "WARNING"):
            odgovor = Client().get("/nepostoji-qzx7/")
        html = odgovor.content.decode("utf-8")
        self.assertEqual(odgovor.status_code, 404)
        self.assertIn("moderator/", html)
        self.assertIn("nepostoji-qzx7", html)
        self.assertIn("URLconf", html)

    def test_500(self):
        for jezik in JEZICI:
            with self.subTest(jezik):
                klijent = klijent_jezika(jezik, raise_request_exception=False)
                with mock.patch("igra.views._stanje", side_effect=RuntimeError("kvar-qzx500")):
                    with self.assertLogs("django.request", "ERROR"):
                        odgovor = klijent.get("/")
                self.proveri_stranu(odgovor, 500, "500", jezik, tajne=("kvar-qzx500", "RuntimeError", "_stanje"))

    def test_deljena_404_ostaje_svoja_strana(self):
        # Plan 15.4: deljena 404 ne ide kroz handler404; isti bajtovi kao sablon deljeno.html sa istim kontekstom.
        isteklo = istekao_red()
        for jezik in JEZICI:
            with self.subTest(jezik):
                klijent = klijent_jezika(jezik)
                odgovori = [
                    self.deljena(token, klijent)
                    for token in ("neispravan", secrets.token_urlsafe(16), isteklo.token)
                ]
                self.assertEqual([o.status_code for o in odgovori], [404, 404, 404])
                self.assertEqual(len({o.content for o in odgovori}), 1)
                with translation.override(jezik):
                    ocekivano = render_to_string(
                        "igra/deljeno.html",
                        {"deljeno": None, "dana": p.DELJENJE_DANA, "tekstovi": tekstovi.za_skriptu()},
                        request=odgovori[0].wsgi_request,
                    )
                self.assertEqual(odgovori[0].content, ocekivano.encode("utf-8"))
                html = odgovori[0].content.decode("utf-8")
                self.assertNotIn(NASLOVI_GRESAKA["404"][jezik][1], html)
                self.assertEqual(H1_GRESKE.findall(html), [])
                self.assertEqual(odgovori[0]["Referrer-Policy"], "no-referrer")


class BezbednosnaZaglavljaTests(OsnovaModeratora):
    """Plan 15.4: CSP, nosniff, Referrer-Policy, X-Frame-Options i COOP na igri, deljenoj i moderatoru."""

    def strane(self):
        glavni = self.klijent_za(napravi_moderatora("Glavni", glavni=True))
        igrac = Client()
        pocetna = igrac.get("/")
        zavrseni = Client()
        self.postavi_zavrsenu(seme_najduze(), klijent=zavrseni, strategija=strategija_najduza)
        red = upisi_deljeno()
        with self.assertLogs("django.request", "WARNING"):
            nepostojeca = igrac.get("/nepostoji/")
        return {
            "igra": pocetna,
            "igra zavrsena": zavrseni.get("/"),
            "deljena": igrac.get(reverse("deljeno", args=[red.token])),
            "deljena 404": igrac.get("/r/neispravan/"),
            "prijava": Client().get(reverse("moderator_prijava")),
            "moderator pregled": glavni.get(reverse("moderator")),
            "moderator dnevnik": glavni.get(reverse("moderator_dnevnik")),
            "moderator lozinka": glavni.get(reverse("moderator_lozinka")),
            "moderator nalozi": glavni.get(reverse("moderator_nalozi")),
            "strana 404": nepostojeca,
            "zdravlje": igrac.get(reverse("zdravlje")),
        }

    def test_zaglavlja_na_svakoj_strani(self):
        for opis, odgovor in self.strane().items():
            with self.subTest(opis):
                self.assertIn(odgovor.status_code, (200, 404))
                self.assertEqual(odgovor["Content-Security-Policy"], CSP_OCEKIVANO)
                self.assertFalse(odgovor.has_header("Content-Security-Policy-Report-Only"))
                self.assertEqual(odgovor["X-Content-Type-Options"], "nosniff")
                self.assertEqual(odgovor["X-Frame-Options"], "DENY")
                self.assertEqual(odgovor["Cross-Origin-Opener-Policy"], "same-origin")
                # Deljena zadrzava no-referrer (token je u URL-u), ostale same-origin.
                ocekivano = "no-referrer" if opis.startswith("deljena") else "same-origin"
                self.assertEqual(odgovor["Referrer-Policy"], ocekivano)

    def test_html_bez_onoga_sto_csp_blokira(self):
        strane = self.strane()
        del strane["zdravlje"]
        for opis, odgovor in strane.items():
            with self.subTest(opis):
                html = odgovor.content.decode("utf-8")
                self.assertIn("<html", html)
                self.assertEqual(inline_nalazi(html), [])

    def test_kontrola_inline_nalazi(self):
        # Dokaz da provera gore nalazi svaku vrstu: bez ovoga prazan spisak ne znaci nista.
        html = (
            '<script>a()</script><script id="x" type="application/json">{}</script><script src="/s.js"></script>'
            '<p style="color:red">x</p><a href="javascript:a()">y</a><img src="/i.png" onerror="a()"><style>p{}</style>'
        )
        self.assertEqual(len(inline_nalazi(html)), 5, inline_nalazi(html))


def seme_najduze():
    """Partija koja pali svih pet lekcija (najvise sablona na zavrsnom ekranu)."""
    return nadji_seme(strategija_najduza, lambda i: motor.TIHI_NEUSPEH in i)


class FilterLogaTests(OsnovaPrikaza):
    """Plan 15.4: zapis 500 na /r/<token>/ pod LOGGING iz settings_prod bez tokena, semena i kljuca sesije."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.log = ucitaj_prod(probno_okruzenje("/data/db.sqlite3")).LOGGING

    def rukovalac(self, tok, sa_filterom):
        """Rukovalac koji LOGGING iz settings_prod daje logeru django.request, ali u tok umesto u stdout."""
        opis = self.log["handlers"][self.log["loggers"]["django.request"]["handlers"][0]]
        rukovalac = logging.StreamHandler(tok)
        rukovalac.setFormatter(logging.Formatter(self.log["formatters"][opis["formatter"]]["format"]))
        if sa_filterom:
            for ime in opis["filters"]:
                rukovalac.addFilter(import_string(self.log["filters"][ime]["()"])())
        return rukovalac

    def zapis_500_na_deljenoj(self, sa_filterom):
        seme = secrets.token_hex(16)  # isti oblik kao views._nova_igra
        klijent = Client(raise_request_exception=False)
        self.postavi_igru(seme, klijent)
        kljuc = klijent.session.session_key
        red = upisi_deljeno()

        def kvar(_red):
            raise RuntimeError(f"kvar na /r/{red.token}/ uz seme {seme} i sesiju {kljuc}")

        tok = StringIO()
        loger = logging.getLogger("django.request")
        staro = (loger.handlers[:], loger.level, loger.propagate)
        loger.handlers = [self.rukovalac(tok, sa_filterom)]
        loger.setLevel(self.log["loggers"]["django.request"]["level"])
        loger.propagate = False
        try:
            with mock.patch("igra.views._javni_deljeni", side_effect=kvar):
                odgovor = self.deljena(red.token, klijent)
        finally:
            loger.handlers, loger.propagate = staro[0], staro[2]
            loger.setLevel(staro[1])
        self.assertEqual(odgovor.status_code, 500)
        tajne = (red.token, seme, kljuc)
        self.assertEqual([len(t) for t in tajne], [22, 32, 32])
        return tok.getvalue(), tajne

    def test_500_na_deljenoj_bez_tajni(self):
        zapis, tajne = self.zapis_500_na_deljenoj(sa_filterom=True)
        self.assertIn("ERROR django.request: Internal Server Error: /r/-/", zapis)
        self.assertIn("RuntimeError: kvar na /r/-/ uz seme [skriveno] i sesiju [skriveno]", zapis)
        for tajna in tajne:
            self.assertNotIn(tajna, zapis)

    def test_kontrola_bez_filtera_tajne_su_u_zapisu(self):
        zapis, tajne = self.zapis_500_na_deljenoj(sa_filterom=False)
        for tajna in tajne:
            self.assertIn(tajna, zapis)


# Nov proces: dictConfig menja ceo logging procesa. logconfig_dict iz deploy/gunicorn.conf.py kao u gunicorn 27
# (glogging.Logger.setup: CONFIG_DEFAULTS.update, a recnik nosi sve kljuceve, pa je to isto sto i dictConfig njega
# samog); /app je na sys.path pre toga (gunicorn app.base.chdir). Opcionalno posle toga django.setup(), kao radnik
# koji ucitava aplikaciju pod settings_prod. Poruka i trag su doslovno oblik gunicorn workers/base.handle_error.
SKRIPTA_GUNICORN_LOGA = r'''
import logging, logging.config, runpy, sys
koren, token, seme, sa_filterom, sa_djangom = sys.argv[1:4] + [a == "1" for a in sys.argv[4:6]]
sys.path.insert(0, koren)
konf = runpy.run_path(koren + "/deploy/gunicorn.conf.py")["logconfig_dict"]
if not sa_filterom:
    for rukovalac in konf["handlers"].values():
        rukovalac.pop("filters", None)
logging.config.dictConfig(konf)
if sa_djangom:
    import django
    django.setup()
greska_log = logging.getLogger("gunicorn.error")
greska_log.info("Booting worker")
try:
    raise RuntimeError("kvar na /r/" + token + "/ uz seme " + seme)
except RuntimeError:
    greska_log.exception("Error handling request %s", "/r/" + token + "/")
logging.getLogger("gunicorn.access").info("pristup /r/%s/", token)
'''


class GunicornLogTests(TestCase):
    """Plan 15.4: log gresaka gunicorn-a (logconfig_dict) bez tokena linka i semena, i u poruci i u tragu."""

    def zapis(self, sa_filterom, sa_djangom):
        token, seme = secrets.token_urlsafe(16), secrets.token_hex(16)
        okruzenje = {ime: vrednost for ime, vrednost in os.environ.items() if not ime.startswith("DJANGO_")}
        okruzenje["PYTHONIOENCODING"] = "utf-8"
        privremeni = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(privremeni.cleanup)
        if sa_djangom:
            okruzenje.update(probno_okruzenje(pathlib.Path(privremeni.name) / "db.sqlite3"))
            okruzenje["DJANGO_SETTINGS_MODULE"] = "orkestrator.settings_prod"
        proces = subprocess.run(
            [sys.executable, "-c", SKRIPTA_GUNICORN_LOGA, str(settings.BASE_DIR), token, seme,
             "1" if sa_filterom else "0", "1" if sa_djangom else "0"],
            cwd=settings.BASE_DIR, env=okruzenje, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=120,
        )
        self.assertEqual(proces.returncode, 0, proces.stderr[-800:])
        self.assertEqual([len(token), len(seme)], [22, 32])
        # Rukovalac iz logconfig_dict pise na stderr u formatu "generic"; pristupni log nema rukovalac.
        self.assertRegex(proces.stderr, r"\[\d+\] \[INFO\] Booting worker\n")
        return proces.stdout + proces.stderr, (token, seme)

    def test_greska_na_deljenoj_bez_tajni(self):
        # Bez DJANGO_SETTINGS_MODULE (master uvozi filter pre aplikacije) i posle settings_prod.LOGGING (radnik).
        for sa_djangom in (False, True):
            with self.subTest(sa_djangom=sa_djangom):
                zapis, tajne = self.zapis(sa_filterom=True, sa_djangom=sa_djangom)
                self.assertRegex(zapis, r"\[\d+\] \[ERROR\] Error handling request /r/-/\n")
                self.assertIn("RuntimeError: kvar na /r/-/ uz seme [skriveno]", zapis)
                for tajna in tajne:
                    self.assertNotIn(tajna, zapis)

    def test_kontrola_bez_filtera_tajne_su_u_zapisu(self):
        zapis, (token, seme) = self.zapis(sa_filterom=False, sa_djangom=False)
        self.assertIn(f"Error handling request /r/{token}/", zapis)
        self.assertIn(f"RuntimeError: kvar na /r/{token}/ uz seme {seme}", zapis)


class BazaKopijaTests(PomocPrikaza, TransactionTestCase):
    """Plan 15.6 i ugovor 15.12. TransactionTestCase: VACUUM INTO ne radi unutar transakcije."""

    def setUp(self):
        super().setUp()
        privremeni = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(privremeni.cleanup)
        self.dir = pathlib.Path(privremeni.name)

    @staticmethod
    def redovi(izvrsi, tabela):
        return [tuple(red) for red in izvrsi(f'SELECT * FROM "{tabela}" ORDER BY rowid')]

    def test_kopija_prolazi_proveru_i_ima_iste_redove(self):
        upisi_red("Пера", 70)
        upisi_red("Мика", 40)
        upisi_deljeno()
        NepodobnoIme.objects.create(kljuc=STAVKA_SIFARNIKA)
        Client().get("/")  # red sesije sa partijom
        cilj = self.dir / "kopija.sqlite3"
        izlaz = StringIO()
        call_command("baza_kopija", str(cilj), stdout=izlaz)
        self.assertIn("integrity_check: ok", izlaz.getvalue())

        # Isti pretvaraci kolona kao Django veza (datumi), pa se redovi porede kao vrednosti.
        veza = sqlite3.connect(
            f"{cilj.as_uri()}?mode=ro", uri=True, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
        )
        try:
            self.assertEqual(veza.execute("PRAGMA integrity_check").fetchall(), [("ok",)])
            tabele = connection.introspection.table_names()
            kopija_tabele = [red[0] for red in veza.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )]
            self.assertEqual(kopija_tabele, sorted(tabele))
            with connection.cursor() as kursor:
                def izvor(sql):
                    kursor.execute(sql)
                    return kursor.fetchall()

                for tabela in tabele:
                    with self.subTest(tabela):
                        self.assertEqual(self.redovi(lambda sql: veza.execute(sql).fetchall(), tabela),
                                         self.redovi(izvor, tabela))
                broj = {t: len(self.redovi(izvor, t)) for t in
                        ("igra_rezultat", "igra_deljenirezultat", "django_session", "igra_nepodobnoime")}
            # Tvrdnja "isti redovi" ne prolazi prazno: tabele koje nosi ovaj test nisu prazne.
            self.assertEqual(broj["igra_rezultat"], 2)
            self.assertEqual(broj["igra_deljenirezultat"], 1)
            self.assertEqual(broj["django_session"], 1)
            self.assertGreaterEqual(broj["igra_nepodobnoime"], 1)
        finally:
            veza.close()

    def test_postojeca_putanja_greska_i_netaknuta(self):
        upisi_red("Пера", 70)
        datoteka = self.dir / "postoji.sqlite3"
        datoteka.write_bytes(b"ne dirati")
        pre = datoteka.stat().st_mtime_ns
        with self.assertRaises(CommandError) as greska:
            call_command("baza_kopija", str(datoteka), stdout=StringIO())
        self.assertIn("vec postoji", str(greska.exception))
        self.assertEqual(datoteka.read_bytes(), b"ne dirati")
        self.assertEqual(datoteka.stat().st_mtime_ns, pre)

        prazna = self.dir / "prazna.sqlite3"
        prazna.touch()
        with self.assertRaises(CommandError):
            call_command("baza_kopija", str(prazna), stdout=StringIO())
        self.assertEqual(prazna.read_bytes(), b"")

        direktorijum = self.dir / "direktorijum"
        direktorijum.mkdir()
        with self.assertRaises(CommandError):
            call_command("baza_kopija", str(direktorijum), stdout=StringIO())
        self.assertTrue(direktorijum.is_dir())
        self.assertEqual(list(direktorijum.iterdir()), [])


class WalTests(TestCase):
    """Plan 15.4: veza iz DATABASES ima journal_mode wal i timeout 5 s. Test baza je u memoriji, pa datoteka."""

    def rezim(self, opcije):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as dir:
            podesavanja = {**settings.DATABASES[DEFAULT_DB_ALIAS], "NAME": os.path.join(dir, "wal.sqlite3"),
                           "OPTIONS": opcije, "TEST": {}}
            veza = ConnectionHandler({DEFAULT_DB_ALIAS: podesavanja})[DEFAULT_DB_ALIAS]
            try:
                with veza.cursor() as kursor:
                    kursor.execute("PRAGMA journal_mode")
                    rezim = kursor.fetchone()[0]
                    kursor.execute("PRAGMA busy_timeout")
                    cekanje = kursor.fetchone()[0]
            finally:
                veza.close()
        return rezim, cekanje

    def test_veza_ima_wal_i_timeout(self):
        opcije = settings.DATABASES[DEFAULT_DB_ALIAS]["OPTIONS"]
        self.assertEqual(opcije["timeout"], 5)  # isto kao podrazumevano u sqlite3, pa se cita i iz podesavanja
        self.assertEqual(self.rezim(opcije), ("wal", 5000))

    def test_kontrola_opcije_menjaju_rezim_i_cekanje(self):
        # Dokaz da provera razlikuje: nova datoteka bez init_command ostaje "delete", a busy_timeout prati opciju.
        self.assertEqual(self.rezim({"timeout": 1}), ("delete", 1000))


# ---------- Dnevni izazov (PLAN-dnevni-izazov.md, Talas 3) ----------

DAN = datetime.date(2026, 11, 12)
SUTRA = DAN + datetime.timedelta(days=1)
JUCE = DAN - datetime.timedelta(days=1)
RANG_DANA_SCRIPT = re.compile(r'<script id="rang-dana" type="application/json">(.*?)</script>', re.S)
# Engleski tekst novih poruka prepisan iz plana (tabela "tekst (sr -> en)"), ne cita se iz .po.
TEKSTOVI_DNEVNOG = {
    "Дневни изазов": "Daily challenge",
    "Ранг листа дана": "Today's leaderboard",
    "Играј дневни изазов": "Play the daily challenge",
    "Назад на главну игру": "Back to the main game",
    "Данас још нема сачуваних резултата.": "No saved results today yet.",
    "Данас сви играју исту партију: исти задаци и исти исходи. Дневни изазов се игра једном.":
        "Today everyone plays the same game: the same tasks and the same outcomes. The daily challenge is played once.",
    "Главна ранг листа": "Main leaderboard",
    "Дневни изазов, данас": "Daily challenge, today",
    "дневни изазов": "daily challenge",
}


def rang_dana_iz_html(odgovor):
    pogodak = RANG_DANA_SCRIPT.search(odgovor.content.decode("utf-8"))
    if pogodak is None:
        raise AssertionError("nema json_script bloka rang-dana")
    return json.loads(pogodak.group(1))


class OsnovaDnevnog(OsnovaPrikaza):
    """Dan zadaje test (views._danas je jedino mesto koje ga cita); self.dan se menja usred testa."""

    def setUp(self):
        super().setUp()
        self.dan = DAN
        zakrpa = mock.patch.object(views, "_danas", lambda: self.dan)
        zakrpa.start()
        self.addCleanup(zakrpa.stop)

    def dnevni(self, klijent=None):
        return (klijent or self.client).get(reverse("dnevni"))

    def dnevno_stanje(self, klijent):
        return klijent.session["dnevna"]

    def dnevni_potez(self, krug, izbor=OPUS_HIGH, klijent=None):
        telo = json.dumps({"krug": krug, "izbori": izbor})
        return (klijent or self.client).post(reverse("dnevni_potez"), data=telo, content_type=JSON_TIP)

    def dnevni_sacuvaj(self, ime, klijent=None):
        telo = json.dumps({"ime": ime})
        return (klijent or self.client).post(reverse("dnevni_sacuvaj"), data=telo, content_type=JSON_TIP)

    def dnevni_podeli(self, klijent=None):
        return (klijent or self.client).post(reverse("dnevni_podeli"))

    def odigraj_dnevnu(self, klijent, strategija=po_tezini, do=8):
        odgovori = []
        for krug in range(1, do + 1):
            odgovor = self.dnevni_potez(krug, strategija(krug), klijent)
            self.assertEqual(odgovor.status_code, 200, odgovor.content)
            odgovori.append(odgovor)
        self.assertEqual(len(odgovori), do)
        return odgovori

    def novi_igrac(self):
        klijent = Client()
        self.assertEqual(self.dnevni(klijent).status_code, 200)
        return klijent

    def zavrsen_igrac(self, strategija=po_tezini):
        klijent = self.novi_igrac()
        self.odigraj_dnevnu(klijent, strategija)
        self.assertTrue(self.dnevno_stanje(klijent)["zavrsena"])
        return klijent


class DnevnoSemeTests(OsnovaDnevnog):
    """Tacka (1): seme dana je isto za sve u istom danu, razlicito po danima i zavisi od SECRET_KEY."""

    def test_isti_dan_isto_seme_u_dve_sesije_a_razlicita_oznaka(self):
        prvi, drugi = self.novi_igrac(), self.novi_igrac()
        a, b = self.dnevno_stanje(prvi), self.dnevno_stanje(drugi)
        self.assertRegex(a["seme"], r"^[0-9a-f]{64}$")
        self.assertEqual(a["seme"], b["seme"])
        self.assertEqual(a["seme"], views._dnevno_seme(DAN))
        self.assertEqual((a["dan"], b["dan"]), ("2026-11-12", "2026-11-12"))
        self.assertRegex(a["oznaka"], r"^[0-9a-f]{32}$")
        self.assertNotEqual(a["oznaka"], b["oznaka"])
        self.assertNotEqual(prvi.session.session_key, drugi.session.session_key)

    def test_drugi_dan_drugo_seme(self):
        prvi = self.novi_igrac()
        self.dan = SUTRA
        drugi = self.novi_igrac()
        a, b = self.dnevno_stanje(prvi), self.dnevno_stanje(drugi)
        self.assertEqual(b["dan"], "2026-11-13")
        self.assertNotEqual(a["seme"], b["seme"])
        semena = {views._dnevno_seme(DAN + datetime.timedelta(days=i)) for i in range(30)}
        self.assertEqual(len(semena), 30)

    def test_seme_nije_funkcija_samog_datuma(self):
        # Zamena SECRET_KEY menja seme; bez toga bi ga svako izracunao iz datuma.
        obicno = self.dnevno_stanje(self.novi_igrac())["seme"]
        with override_settings(SECRET_KEY="drugi-tajni-kljuc-za-test-dnevnog-semena-1234567890"):
            drugo = self.dnevno_stanje(self.novi_igrac())["seme"]
            self.assertEqual(drugo, views._dnevno_seme(DAN))
        self.assertNotEqual(obicno, drugo)
        self.assertEqual(obicno, views._dnevno_seme(DAN))
        iso = DAN.isoformat().encode()
        javno = {hashlib.sha256(iso).hexdigest(), hashlib.md5(iso).hexdigest(), DAN.isoformat(), DAN.strftime("%d.%m.%Y")}
        self.assertNotIn(obicno, javno)
        self.assertNotIn(drugo, javno)

    def test_obicna_igra_ne_dobija_seme_dana(self):
        self.client.get(reverse("pocetna"))
        igra = self.client.session["igra"]
        self.assertNotEqual(igra["seme"], views._dnevno_seme(DAN))
        self.assertNotIn("dan", igra)
        self.assertNotIn("oznaka", igra)
        self.assertNotIn("dnevna", self.client.session)  # pocetna ne pravi dnevnu partiju


class DnevnoSkrivenoTests(OsnovaDnevnog):
    """Tacka (2): seme, oznaka i njihovi sha256 nisu ni u jednom odgovoru dnevne igre."""

    def tajne(self, klijent):
        stanje = self.dnevno_stanje(klijent)
        return {
            "seme": stanje["seme"],
            "sha256(seme)": hashlib.sha256(stanje["seme"].encode()).hexdigest(),
            "oznaka": stanje["oznaka"],
            "sha256(oznaka)": motor.oznaka_partije(stanje),
        }

    def proveri(self, odgovor, tajne, opis):
        telo = odgovor.content.decode("utf-8")
        zaglavlja = " ".join(f"{k}: {v}" for k, v in odgovor.items())
        kolacici = " ".join(f"{k}={v.value}" for k, v in odgovor.cookies.items())
        for ime, tajna in tajne.items():
            for gde, tekst in (("telo", telo), ("zaglavlja", zaglavlja), ("kolacici", kolacici)):
                self.assertNotIn(tajna, tekst, f"{ime} u {gde}: {opis}")

    def test_detektor_nalazi_tajne_tamo_gde_smeju_da_budu(self):
        klijent = self.zavrsen_igrac()
        tajne = self.tajne(klijent)
        self.assertEqual(len(set(tajne.values())), 4)
        sirovo = json.dumps(self.dnevno_stanje(klijent))
        self.assertIn(tajne["seme"], sirovo)
        self.assertIn(tajne["oznaka"], sirovo)
        self.assertEqual(self.dnevni_sacuvaj("Тајна", klijent).status_code, 200)
        self.assertEqual(Rezultat.objects.get().partija, tajne["sha256(oznaka)"])
        for ime, tajna in tajne.items():
            with self.subTest(ime):
                lazni = mock.Mock(content=json.dumps({"x": tajna}).encode(), items=lambda: [], cookies={})
                with self.assertRaises(AssertionError):
                    self.proveri(lazni, tajne, "kontrola")
                lazni = mock.Mock(content=b"{}", items=lambda t=tajna: [("X-Test", t)], cookies={})
                with self.assertRaises(AssertionError):
                    self.proveri(lazni, tajne, "kontrola")

    def test_nijedan_odgovor_ne_odaje_seme_ni_oznaku(self):
        klijent = Client()
        odgovori = [("dnevni", self.dnevni(klijent))]
        tajne = self.tajne(klijent)
        odgovori += [(f"potez {i}", o) for i, o in enumerate(self.odigraj_dnevnu(klijent), start=1)]
        self.assertEqual(len(odgovori), 9)
        odgovori.append(("dnevni posle kraja", self.dnevni(klijent)))
        sacuvano = self.dnevni_sacuvaj("Играч", klijent)
        self.assertEqual(sacuvano.status_code, 200)
        odgovori.append(("sacuvaj", sacuvano))
        podeljeno = self.dnevni_podeli(klijent)
        self.assertEqual(podeljeno.status_code, 200)
        odgovori.append(("podeli", podeljeno))
        token = token_iz_url(json.loads(podeljeno.content)["url"])
        deljeno = self.deljena(token, Client())
        self.assertEqual(deljeno.status_code, 200)
        odgovori.append(("deljeno", deljeno))
        odgovori.append(("pocetna", klijent.get(reverse("pocetna"))))
        # Odbijeni zahtevi nose stanje i listu, pa i oni.
        odgovori.append(("potez 409", self.dnevni_potez(1, klijent=klijent)))
        odgovori.append(("sacuvaj 409", self.dnevni_sacuvaj("Играч", klijent)))
        self.assertEqual(odgovori[-1][1].status_code, 409)
        for opis, odgovor in odgovori:
            with self.subTest(opis):
                self.proveri(odgovor, tajne, opis)
        # Kolacici klijenta (sesija, CSRF): vrednosti su kljuc sesije i token, ne tajne.
        self.assertGreater(len(klijent.cookies), 0)
        for ime, kolacic in klijent.cookies.items():
            for tajna in tajne.values():
                self.assertNotIn(tajna, kolacic.value, ime)

    def test_dnevni_json_i_html_bez_zabranjenih_kljuceva(self):
        klijent = Client()
        odgovor = self.dnevni(klijent)
        podaci = {"stanje": stanje_iz_html(odgovor), "rang": rang_iz_html(odgovor)}
        self.assertEqual(skriveni_kljucevi(podaci, False), set())
        odgovori = self.odigraj_dnevnu(klijent)
        for krug, odgovor in enumerate(odgovori, start=1):
            with self.subTest(krug=krug):
                self.assertEqual(skriveni_kljucevi(json.loads(odgovor.content), krug == 8), set())
        for kljuc in ("dan", "oznaka", "seme"):
            self.assertNotIn(kljuc, set(svi_kljucevi(json.loads(odgovori[-1].content))))


class DnevniIstiIshodTests(OsnovaDnevnog):
    """Tacka (3): dva klijenta, isti izbori, isti JSON svih osam poteza."""

    def telo_poteza(self, klijent):
        return [json.loads(o.content) for o in self.odigraj_dnevnu(klijent)]

    def test_isti_izbori_isti_json_svih_osam_poteza(self):
        a, b = self.telo_poteza(self.novi_igrac()), self.telo_poteza(self.novi_igrac())
        self.assertEqual(len(a), 8)
        self.assertEqual(a, b)
        # Nezavisno od prikaza: motor nad semenom dana daje isti niz.
        stanje = motor.nova_igra(views._dnevno_seme(DAN))
        ocekivano = []
        for krug in KRUGOVI:
            stanje = motor.odigraj_potez(stanje, krug, po_tezini(krug))
            ocekivano.append(motor.javni_prikaz(stanje))
        self.assertEqual(a, ocekivano)
        self.assertEqual(a[-1]["faza"], "zavrsena")

    def test_ishodi_se_menjaju_od_dana_do_dana(self):
        # Fiksan kljuc: niz po danima je deterministican. Isti niz svih dana bi znacio da seme ne ulazi u ishod.
        with override_settings(SECRET_KEY="fiksni-kljuc-za-niz-ishoda-0123456789abcdef"):
            nizovi = set()
            for pomak in range(6):
                self.dan = DAN + datetime.timedelta(days=pomak)
                nizovi.add(json.dumps(self.telo_poteza(self.novi_igrac()), sort_keys=True))
        self.assertGreater(len(nizovi), 1)

    def test_isti_izbori_isti_zavrsni_ekran_i_poeni(self):
        prvi, drugi = self.zavrsen_igrac(sve_opus), self.zavrsen_igrac(sve_opus)
        a, b = self.dnevno_stanje(prvi), self.dnevno_stanje(drugi)
        self.assertEqual(a["rezultat"], b["rezultat"])
        self.assertEqual(ishodi(a), ishodi(b))
        self.assertEqual(len(ishodi(a)), 8)

    def test_razliciti_izbori_razliciti_tok_u_istom_danu(self):
        # Kontrola: ishod zavisi i od izbora, ne samo od semena.
        opus = self.zavrsen_igrac(sve_opus)
        haiku = self.zavrsen_igrac(sve_haiku_low_malo)
        self.assertNotEqual(self.dnevno_stanje(opus)["rezultat"], self.dnevno_stanje(haiku)["rezultat"])


class DnevnoCuvanjeTests(OsnovaDnevnog):
    """Tacka (4): dva igraca istog dana oba cuvaju; brisanje jednog ne blokira drugog."""

    def test_dva_igraca_istog_dana_oba_cuvaju(self):
        a, b = self.zavrsen_igrac(), self.zavrsen_igrac()
        self.assertEqual(self.dnevno_stanje(a)["seme"], self.dnevno_stanje(b)["seme"])
        prvi, drugi = self.dnevni_sacuvaj("Прва", a), self.dnevni_sacuvaj("Друга", b)
        self.assertEqual((prvi.status_code, drugi.status_code), (200, 200), (prvi.content, drugi.content))
        redovi = list(Rezultat.objects.order_by("id"))
        self.assertEqual([r.ime for r in redovi], ["Прва", "Друга"])
        self.assertEqual({r.dan for r in redovi}, {DAN})
        self.assertEqual(
            {r.partija for r in redovi},
            {motor.oznaka_partije(self.dnevno_stanje(a)), motor.oznaka_partije(self.dnevno_stanje(b))},
        )
        self.assertEqual(len({r.partija for r in redovi}), 2)
        # Odgovor drugog vec vidi oba reda, a "moj" je njegov.
        rang = json.loads(drugi.content)["rang"]
        self.assertEqual(len(rang["lista"]), 2)
        self.assertEqual(rang["lista"][rang["moj"]]["ime"], "Друга")

    def test_ponovno_cuvanje_iste_partije_409_a_drugi_igrac_nije_pogodjen(self):
        a, b = self.zavrsen_igrac(), self.zavrsen_igrac()
        self.assertEqual(self.dnevni_sacuvaj("Прва", a).status_code, 200)
        ponovo = self.dnevni_sacuvaj("Прва опет", a)
        self.assertEqual(ponovo.status_code, 409)
        self.assertEqual(json.loads(ponovo.content)["greska"], "vec_sacuvano")
        self.assertEqual(Rezultat.objects.count(), 1)
        self.assertEqual(self.dnevni_sacuvaj("Друга", b).status_code, 200)
        self.assertEqual(Rezultat.objects.count(), 2)

    def test_brisanje_jednog_ne_blokira_drugog(self):
        a, b, c = self.zavrsen_igrac(), self.zavrsen_igrac(), self.zavrsen_igrac()
        self.assertEqual(self.dnevni_sacuvaj("Прва", a).status_code, 200)
        brisanje.obrisi_rezultate([Rezultat.objects.get(ime="Прва").id])
        self.assertEqual(Rezultat.objects.count(), 0)
        self.assertEqual(ZapisDnevnika.objects.filter(radnja="rezultat_obrisan").count(), 1)
        # Drugi i treci igrac istog dana (isto seme) cuvaju bez smetnje.
        self.assertEqual(self.dnevni_sacuvaj("Друга", b).status_code, 200)
        self.assertEqual(self.dnevni_sacuvaj("Трећа", c).status_code, 200)
        self.assertEqual(sorted(Rezultat.objects.values_list("ime", flat=True)), ["Друга", "Трећа"])
        # Obrisana partija se i dalje ne cuva ponovo.
        ponovo = self.dnevni_sacuvaj("Прва", a)
        self.assertEqual(ponovo.status_code, 409)
        self.assertEqual(json.loads(ponovo.content)["greska"], "vec_sacuvano")
        self.assertEqual(Rezultat.objects.count(), 2)

    def test_brisanje_linka_jednog_ne_blokira_deljenje_drugog(self):
        a, b = self.zavrsen_igrac(), self.zavrsen_igrac()
        prvi, drugi = self.dnevni_podeli(a), self.dnevni_podeli(b)
        self.assertEqual((prvi.status_code, drugi.status_code), (200, 200))
        self.assertNotEqual(json.loads(prvi.content)["url"], json.loads(drugi.content)["url"])
        self.assertEqual(DeljeniRezultat.objects.count(), 2)
        prvi_red = DeljeniRezultat.objects.get(partija=motor.oznaka_partije(self.dnevno_stanje(a)))
        brisanje.obrisi_deljene([prvi_red.id])
        treci = self.zavrsen_igrac()
        self.assertEqual(self.dnevni_podeli(treci).status_code, 200)
        self.assertEqual(self.dnevni_podeli(b).status_code, 200)  # ponovni klik: isti link
        obrisan = self.dnevni_podeli(a)  # obrisan link se ne pravi ponovo
        self.assertEqual(obrisan.status_code, 409)
        self.assertEqual(json.loads(obrisan.content)["greska"], "deljenje_isteklo")

    def test_cuvanje_bez_zavrsene_partije_409(self):
        klijent = self.novi_igrac()
        odgovor = self.dnevni_sacuvaj("Рано", klijent)
        self.assertEqual(odgovor.status_code, 409)
        self.assertEqual(json.loads(odgovor.content)["greska"], "igra_nije_zavrsena")
        self.assertEqual(Rezultat.objects.count(), 0)
        self.assertEqual(self.dnevni_podeli(klijent).status_code, 409)
        self.assertEqual(DeljeniRezultat.objects.count(), 0)


class DnevneListeTests(OsnovaDnevnog):
    """Tacka (5): glavna i lista dana se ne mesaju; lista dana je samo danas, najvise 10, po rangu."""

    def test_dnevni_red_nije_na_glavnoj_a_obicni_nije_na_listi_dana(self):
        dnevni = upisi_red("Дневни", 70, dan=DAN)
        obicni = upisi_red("Обични", 60)
        self.assertEqual(list(Rezultat.objects.glavna()), [obicni])
        self.assertEqual(list(Rezultat.objects.dana(DAN)), [dnevni])
        odgovor = self.client.get(reverse("pocetna"))
        self.assertEqual([r["ime"] for r in rang_iz_html(odgovor)["lista"]], ["Обични"])
        self.assertEqual([r["ime"] for r in rang_dana_iz_html(odgovor)["lista"]], ["Дневни"])
        # Lista na dnevnoj strani je lista dana.
        self.assertEqual([r["ime"] for r in rang_iz_html(self.dnevni())["lista"]], ["Дневни"])

    def test_cuvanje_kroz_prikaze_upisuje_pravu_listu(self):
        klijent = self.zavrsen_igrac()
        self.assertEqual(self.dnevni_sacuvaj("Дневна", klijent).status_code, 200)
        self.postavi_zavrsenu("seme-obicna-lista")
        self.assertEqual(self.sacuvaj("Обична").status_code, 200)
        dnevna, obicna = Rezultat.objects.get(ime="Дневна"), Rezultat.objects.get(ime="Обична")
        self.assertEqual((dnevna.dan, obicna.dan), (DAN, None))
        odgovor = self.client.get(reverse("pocetna"))
        self.assertEqual([r["ime"] for r in rang_iz_html(odgovor)["lista"]], ["Обична"])
        self.assertEqual([r["ime"] for r in rang_dana_iz_html(odgovor)["lista"]], ["Дневна"])
        # Drugi igrac vidi iste dve liste; svaka ima samo svoj red.
        odgovor = klijent.get(reverse("pocetna"))
        self.assertEqual([r["ime"] for r in rang_iz_html(odgovor)["lista"]], ["Обична"])
        self.assertEqual([r["ime"] for r in rang_dana_iz_html(odgovor)["lista"]], ["Дневна"])

    def test_odgovor_cuvanja_nosi_listu_svoje_igre(self):
        upisi_red("Glavni-red", p.POCETNI_POENI)
        upisi_red("Dnevni-red", p.POCETNI_POENI, dan=DAN)
        self.postavi_zavrsenu("seme-lista-u-odgovoru")
        glavna = json.loads(self.sacuvaj("Обична").content)["rang"]["lista"]
        self.assertEqual([r["ime"] for r in glavna], ["Glavni-red", "Обична"])
        klijent = self.zavrsen_igrac()
        dana = json.loads(self.dnevni_sacuvaj("Дневна", klijent).content)["rang"]["lista"]
        self.assertEqual([r["ime"] for r in dana], ["Dnevni-red", "Дневна"])

    def test_lista_dana_samo_danas_najvise_deset_po_rangu(self):
        for poeni in range(30, 95, 5):  # 13 redova danas: 30, 35, ..., 90
            upisi_red(f"Д{poeni}", poeni, dan=DAN)
        upisi_red("Juce", 100, dan=JUCE)
        upisi_red("Sutra", 100, dan=SUTRA)
        upisi_red("Glavna", 95)
        odgovor = self.client.get(reverse("pocetna"))
        lista = rang_dana_iz_html(odgovor)["lista"]
        self.assertEqual(len(lista), p.RANG_MESTA)
        self.assertEqual([r["ime"] for r in lista], [f"Д{poeni}" for poeni in range(90, 40, -5)])
        self.assertEqual([r["poeni"] for r in lista], list(range(90, 40, -5)))
        self.assertEqual(set(rang_dana_iz_html(odgovor)), KLJUCEVI_RANGA)
        for red in lista:
            self.assertEqual(set(red), KLJUCEVI_REDA)
        self.assertEqual([r["ime"] for r in rang_iz_html(odgovor)["lista"]], ["Glavna"])

    def test_jednaki_poeni_raniji_iznad_pa_manji_id(self):
        prvo, kasnije = utc(2026, 11, 12, 8, 0, 0), utc(2026, 11, 12, 9, 0, 0)
        upisi_red("Kasnije", 60, sacuvan=kasnije, dan=DAN)
        upisi_red("Raniji-b", 60, sacuvan=prvo, dan=DAN)
        upisi_red("Raniji-a", 60, sacuvan=prvo, dan=DAN)
        upisi_red("Vise", 61, sacuvan=kasnije, dan=DAN)
        lista = rang_dana_iz_html(self.client.get(reverse("pocetna")))["lista"]
        self.assertEqual([r["ime"] for r in lista], ["Vise", "Raniji-b", "Raniji-a", "Kasnije"])

    def test_posle_ponoci_lista_dana_je_prazna_a_redovi_ostaju(self):
        upisi_red("Danas", 70, dan=DAN)
        self.assertEqual(len(rang_dana_iz_html(self.client.get(reverse("pocetna")))["lista"]), 1)
        self.dan = SUTRA
        podaci = rang_dana_iz_html(self.client.get(reverse("pocetna")))
        self.assertEqual(podaci, {"lista": [], "sacuvano": False, "moj": None})
        self.assertEqual(Rezultat.objects.count(), 1)

    def test_moj_red_na_listi_dana_samo_za_danasnju_partiju(self):
        upisi_red("Drugi", p.POCETNI_POENI, dan=DAN)
        klijent = self.zavrsen_igrac()
        self.assertEqual(self.dnevni_sacuvaj("Мој", klijent).status_code, 200)
        podaci = rang_dana_iz_html(klijent.get(reverse("pocetna")))
        self.assertTrue(podaci["sacuvano"])
        self.assertEqual(podaci["lista"][podaci["moj"]]["ime"], "Мој")
        self.assertEqual(podaci["moj"], 1)
        # Glavna lista ne zna za dnevnu partiju.
        glavna = rang_iz_html(klijent.get(reverse("pocetna")))
        self.assertEqual((glavna["lista"], glavna["sacuvano"], glavna["moj"]), ([], False, None))
        self.dan = SUTRA
        sutra = rang_dana_iz_html(klijent.get(reverse("pocetna")))
        self.assertEqual(sutra, {"lista": [], "sacuvano": False, "moj": None})

    def test_dana_zahteva_dan_i_ne_prima_none(self):
        with self.assertRaises(ValueError):
            Rezultat.objects.dana(None)

    def test_nijedan_citac_liste_ne_zaobilazi_glavna_i_dana(self):
        zabranjeno = re.compile(r"Rezultat\.objects\.(najboljih|po_rangu|all)\(")
        self.assertEqual(zabranjeno.findall("lista = Rezultat.objects.najboljih()"), ["najboljih"])  # kontrola
        self.assertEqual(zabranjeno.findall("Rezultat.objects.glavna().najboljih()"), [])
        koren = pathlib.Path(settings.BASE_DIR) / "igra"
        izvori = [
            putanja for putanja in koren.rglob("*.py")
            if "tests" not in putanja.parts and "migrations" not in putanja.parts
        ]
        self.assertGreater(len(izvori), 10)
        for putanja in izvori:
            with self.subTest(putanja.name):
                self.assertEqual(zabranjeno.findall(putanja.read_text(encoding="utf-8")), [])


class DnevniPonocTests(OsnovaDnevnog):
    """Tacka (6): ponovni GET vraca istu partiju; sledeci dan nova; potez i cuvanje posle ponoci nose stari dan."""

    def test_ponovni_get_vraca_istu_partiju_usred_igre(self):
        klijent = self.novi_igrac()
        self.odigraj_dnevnu(klijent, do=3)
        pre = copy.deepcopy(self.dnevno_stanje(klijent))
        odgovor = self.dnevni(klijent)
        self.assertEqual(odgovor.status_code, 200)
        self.assertEqual(self.dnevno_stanje(klijent), pre)
        stanje = stanje_iz_html(odgovor)
        self.assertEqual(stanje["krug"], 4)
        self.assertEqual(stanje["faza"], "igra")
        self.assertEqual(stanje["poslednji"]["krug"], 3)

    def test_ponovni_get_vraca_zavrsenu_partiju(self):
        klijent = self.zavrsen_igrac()
        pre = copy.deepcopy(self.dnevno_stanje(klijent))
        for _ in range(2):
            stanje = stanje_iz_html(self.dnevni(klijent))
            self.assertEqual(stanje["faza"], "zavrsena")
            self.assertIsNotNone(stanje["zavrsni"])
        self.assertEqual(self.dnevno_stanje(klijent), pre)
        # Nema druge dnevne partije istog dana ni kroz potez: zavrsena je zavrsena.
        self.assertEqual(self.dnevni_potez(1, klijent=klijent).status_code, 409)

    def test_sledeci_dan_nova_partija(self):
        klijent = self.zavrsen_igrac()
        stara = copy.deepcopy(self.dnevno_stanje(klijent))
        self.dan = SUTRA
        stanje = stanje_iz_html(self.dnevni(klijent))
        nova = self.dnevno_stanje(klijent)
        self.assertEqual((stanje["krug"], stanje["faza"]), (1, "igra"))
        self.assertEqual(nova["dan"], "2026-11-13")
        self.assertNotEqual(nova["seme"], stara["seme"])
        self.assertNotEqual(nova["oznaka"], stara["oznaka"])
        self.assertEqual(nova["istorija"], [])

    def test_potez_posle_ponoci_nastavlja_staru_partiju(self):
        klijent = self.novi_igrac()
        self.odigraj_dnevnu(klijent, do=7)
        self.dan = SUTRA
        odgovor = self.dnevni_potez(8, po_tezini(8), klijent)
        self.assertEqual(odgovor.status_code, 200)
        stanje = self.dnevno_stanje(klijent)
        self.assertEqual((stanje["dan"], stanje["zavrsena"], len(stanje["istorija"])), ("2026-11-12", True, 8))
        # Ni potez ne pravi novu partiju: dnevna ostaje stara dok se strana ne ucita.
        self.assertEqual(stanje["seme"], views._dnevno_seme(DAN))

    def test_cuvanje_posle_ponoci_upisuje_stari_dan(self):
        klijent = self.novi_igrac()
        self.odigraj_dnevnu(klijent)
        self.dan = SUTRA
        odgovor = self.dnevni_sacuvaj("Pred ponoc", klijent)
        self.assertEqual(odgovor.status_code, 200, odgovor.content)
        self.assertEqual(Rezultat.objects.get().dan, DAN)
        # Odgovor nosi listu dana partije, ne novog dana.
        rang = json.loads(odgovor.content)["rang"]
        self.assertEqual([r["ime"] for r in rang["lista"]], ["Pred ponoc"])
        self.assertTrue(rang["sacuvano"])
        # Na listi novog dana ga nema; na listi starog dana ga ima.
        self.assertEqual(rang_dana_iz_html(klijent.get(reverse("pocetna")))["lista"], [])
        self.dan = DAN
        self.assertEqual(len(rang_dana_iz_html(klijent.get(reverse("pocetna")))["lista"]), 1)

    def test_deljenje_posle_ponoci_radi(self):
        klijent = self.zavrsen_igrac()
        self.dan = SUTRA
        odgovor = self.dnevni_podeli(klijent)
        self.assertEqual(odgovor.status_code, 200)
        token = token_iz_url(json.loads(odgovor.content)["url"])
        self.assertEqual(self.deljena(token, Client()).status_code, 200)

    def test_sacuvana_partija_ne_sprecava_novu_sutradan(self):
        klijent = self.zavrsen_igrac()
        self.assertEqual(self.dnevni_sacuvaj("Juce", klijent).status_code, 200)
        self.dan = SUTRA
        self.dnevni(klijent)
        self.odigraj_dnevnu(klijent, sve_opus)
        self.assertEqual(self.dnevni_sacuvaj("Danas", klijent).status_code, 200)
        self.assertEqual(
            sorted(Rezultat.objects.values_list("ime", "dan")), sorted([("Juce", DAN), ("Danas", SUTRA)])
        )


class DnevneRuteTests(OsnovaDnevnog):
    """Tacka (7): nova ne dira dnevnu; nema dnevni/nova/; dnevni/potez/ bez stanja je 409."""

    def test_nova_ne_dira_dnevnu(self):
        klijent = Client()
        klijent.get(reverse("pocetna"))
        self.dnevni(klijent)
        self.odigraj_dnevnu(klijent, do=2)
        dnevna = copy.deepcopy(klijent.session["dnevna"])
        stara_igra = copy.deepcopy(klijent.session["igra"])
        self.assertEqual(klijent.post(reverse("nova")).status_code, 302)
        self.assertEqual(len(dnevna["istorija"]), 2)
        self.assertEqual(klijent.session["dnevna"], dnevna)
        self.assertNotEqual(klijent.session["igra"]["seme"], stara_igra["seme"])
        self.assertEqual(klijent.session["igra"]["krug"], 1)

    def test_obicni_potez_ne_dira_dnevnu_i_obrnuto(self):
        klijent = Client()
        klijent.get(reverse("pocetna"))
        self.dnevni(klijent)
        dnevna = copy.deepcopy(klijent.session["dnevna"])
        igra = copy.deepcopy(klijent.session["igra"])
        self.assertEqual(self.potez(1, klijent=klijent).status_code, 200)
        self.assertEqual(klijent.session["dnevna"], dnevna)
        self.assertEqual(len(klijent.session["igra"]["istorija"]), 1)
        self.assertEqual(self.dnevni_potez(1, klijent=klijent).status_code, 200)
        self.assertEqual(len(klijent.session["igra"]["istorija"]), 1)
        self.assertEqual(len(klijent.session["dnevna"]["istorija"]), 1)
        self.assertNotEqual(klijent.session["igra"]["seme"], klijent.session["dnevna"]["seme"])
        self.assertEqual(klijent.session["igra"]["seme"], igra["seme"])

    def test_vrstu_ne_zadaje_klijent(self):
        klijent = Client()
        klijent.get(reverse("pocetna"))
        self.dnevni(klijent)
        telo = json.dumps({"krug": 1, "izbori": OPUS_HIGH, "vrsta": "dnevna"})
        odgovor = klijent.post(reverse("potez"), data=telo, content_type=JSON_TIP)
        self.assertEqual(odgovor.status_code, 400)
        telo = json.dumps({"krug": 1, "izbori": OPUS_HIGH})
        odgovor = klijent.post(reverse("potez") + "?vrsta=dnevna", data=telo, content_type=JSON_TIP)
        self.assertEqual(odgovor.status_code, 200)
        self.assertEqual(len(klijent.session["igra"]["istorija"]), 1)
        self.assertEqual(klijent.session["dnevna"]["istorija"], [])

    def test_dnevni_nova_ne_postoji(self):
        klijent = self.novi_igrac()
        pre = copy.deepcopy(klijent.session["dnevna"])
        self.assertEqual(klijent.post("/dnevni/nova/").status_code, 404)
        self.assertEqual(klijent.get("/dnevni/nova/").status_code, 404)
        self.assertEqual(klijent.session["dnevna"], pre)
        imena = {o.name for o in get_resolver().url_patterns if o.name and o.name.startswith("dnevni")}
        self.assertEqual(imena, {"dnevni", "dnevni_potez", "dnevni_sacuvaj", "dnevni_podeli"})

    def test_bez_stanja_409_nema_igre_i_ne_pravi_partiju(self):
        klijent = Client()
        odgovor = self.dnevni_potez(1, klijent=klijent)
        self.assertEqual(odgovor.status_code, 409)
        self.assertEqual(json.loads(odgovor.content), {"greska": "nema_igre", "stanje": None})
        odgovor = self.dnevni_sacuvaj("Нико", klijent)
        self.assertEqual(odgovor.status_code, 409)
        self.assertEqual(json.loads(odgovor.content)["greska"], "nema_igre")
        odgovor = self.dnevni_podeli(klijent)
        self.assertEqual(odgovor.status_code, 409)
        self.assertEqual(json.loads(odgovor.content), {"greska": "nema_igre"})
        self.assertNotIn("dnevna", klijent.session)
        self.assertNotIn("igra", klijent.session)
        self.assertEqual((Rezultat.objects.count(), DeljeniRezultat.objects.count()), (0, 0))

    def test_dnevni_potez_sa_obicnom_igrom_a_bez_dnevne_je_409(self):
        klijent = Client()
        klijent.get(reverse("pocetna"))
        odgovor = self.dnevni_potez(1, klijent=klijent)
        self.assertEqual(odgovor.status_code, 409)
        self.assertEqual(json.loads(odgovor.content)["greska"], "nema_igre")
        self.assertEqual(klijent.session["igra"]["istorija"], [])
        self.assertNotIn("dnevna", klijent.session)

    def test_neispravan_zahtev_ima_prednost_nad_409_i_metode(self):
        klijent = Client()
        odgovor = klijent.post(reverse("dnevni_potez"), data="nije json", content_type=JSON_TIP)
        self.assertEqual(odgovor.status_code, 400)
        telo = json.dumps({"krug": 1, "izbori": {"model": "x"}})
        self.assertEqual(klijent.post(reverse("dnevni_potez"), data=telo, content_type=JSON_TIP).status_code, 400)
        self.assertEqual(klijent.post(reverse("dnevni_sacuvaj"), data="{}", content_type=JSON_TIP).status_code, 400)
        for ruta in ("dnevni_potez", "dnevni_sacuvaj", "dnevni_podeli"):
            with self.subTest(ruta):
                self.assertEqual(klijent.get(reverse(ruta)).status_code, 405)
        self.assertEqual(klijent.post(reverse("dnevni")).status_code, 405)

    def test_nove_post_rute_traze_csrf(self):
        klijent = Client(enforce_csrf_checks=True)
        klijent.get(reverse("dnevni"))
        self.assertIn(settings.CSRF_COOKIE_NAME, klijent.cookies)
        pre = copy.deepcopy(klijent.session["dnevna"])
        telo = json.dumps({"krug": 1, "izbori": OPUS_HIGH})
        self.assertEqual(klijent.post(reverse("dnevni_potez"), data=telo, content_type=JSON_TIP).status_code, 403)
        ime = json.dumps({"ime": "Х"})
        self.assertEqual(klijent.post(reverse("dnevni_sacuvaj"), data=ime, content_type=JSON_TIP).status_code, 403)
        self.assertEqual(klijent.post(reverse("dnevni_podeli")).status_code, 403)
        self.assertEqual(klijent.session["dnevna"], pre)
        # Kontrola: isti zahtev sa tokenom prolazi.
        token = klijent.cookies[settings.CSRF_COOKIE_NAME].value
        odgovor = klijent.post(
            reverse("dnevni_potez"), data=telo, content_type=JSON_TIP, headers={"X-CSRFToken": token}
        )
        self.assertEqual(odgovor.status_code, 200)

    def test_dnevni_get_postavlja_csrf_kolacic_i_ne_kesira(self):
        odgovor = Client().get(reverse("dnevni"))
        self.assertIn(settings.CSRF_COOKIE_NAME, odgovor.cookies)
        self.assertIn("no-cache", odgovor["Cache-Control"])
        self.assertIn("no-store", odgovor["Cache-Control"])


class DnevnaOdjavaTests(OsnovaModeratora):
    """Tacka (7): odjava moderatora prenosi i igru i dnevnu partiju u novu sesiju."""

    def setUp(self):
        super().setUp()
        zakrpa = mock.patch.object(views, "_danas", lambda: DAN)
        zakrpa.start()
        self.addCleanup(zakrpa.stop)
        self.mod = napravi_moderatora("Mod")

    def test_odjava_moderatora_cuva_i_igru_i_dnevnu(self):
        klijent = Client()
        klijent.get(reverse("pocetna"))
        klijent.get(reverse("dnevni"))
        self.klijent_za(self.mod, klijent=klijent)
        telo = json.dumps({"krug": 1, "izbori": OPUS_HIGH})
        self.assertEqual(klijent.post(reverse("dnevni_potez"), data=telo, content_type=JSON_TIP).status_code, 200)
        self.assertEqual(self.potez(1, klijent=klijent).status_code, 200)
        dnevna, igra = copy.deepcopy(klijent.session["dnevna"]), copy.deepcopy(klijent.session["igra"])
        self.assertEqual(len(dnevna["istorija"]), 1)
        kljuc = klijent.session.session_key
        self.assertEqual(klijent.post(reverse("moderator_odjava")).status_code, 302)
        self.assertNotIn(SESSION_KEY, klijent.session)
        self.assertNotEqual(klijent.session.session_key, kljuc)
        self.assertEqual(klijent.session["dnevna"], dnevna)
        self.assertEqual(klijent.session["igra"], igra)
        # Dnevna partija se nastavlja posle odjave.
        telo = json.dumps({"krug": 2, "izbori": OPUS_HIGH})
        self.assertEqual(klijent.post(reverse("dnevni_potez"), data=telo, content_type=JSON_TIP).status_code, 200)

    def test_odjava_bez_dnevne_ne_pravi_dnevnu(self):
        klijent = Client()
        klijent.get(reverse("pocetna"))
        self.klijent_za(self.mod, klijent=klijent)
        self.assertEqual(klijent.post(reverse("moderator_odjava")).status_code, 302)
        self.assertNotIn("dnevna", klijent.session)
        self.assertIn("igra", klijent.session)


class DnevniPrikazTests(OsnovaDnevnog):
    """Tacka (9): rang-dana parsira u dict; jezik en je stvarno aktivan; ids, adrese i tekstovi nove strane."""

    def test_rang_dana_na_pocetnoj_parsira_u_dict_sa_belom_listom(self):
        upisi_red("Играч", 66, dan=DAN)
        podaci = rang_dana_iz_html(self.client.get(reverse("pocetna")))
        self.assertIsInstance(podaci, dict)
        self.assertEqual(set(podaci), KLJUCEVI_RANGA)
        self.assertEqual(len(podaci["lista"]), 1)
        red = podaci["lista"][0]
        self.assertEqual(set(red), KLJUCEVI_REDA)
        self.assertEqual((red["ime"], red["poeni"], red["stara_pravila"]), ("Играч", 66, False))
        self.assertEqual(red["datum"], tekstovi.datum(Rezultat.objects.get().sacuvan))
        self.assertEqual(skriveni_kljucevi(podaci, True), set())
        self.assertEqual(podaci["sacuvano"], False)
        self.assertIsNone(podaci["moj"])

    def test_id_sekcije_je_rang_dana_sekcija_a_json_ostaje_rang_dana(self):
        html = self.client.get(reverse("pocetna")).content.decode("utf-8")
        self.assertEqual(html.count('id="rang-dana-sekcija"'), 1)
        self.assertEqual(html.count('<script id="rang-dana" type="application/json">'), 1)
        for id_elementa in ("rang-dana-naslov", "rang-dana-tabela", "rang-dana-redovi", "rang-dana-prazno", "dnevni-dugme"):
            with self.subTest(id_elementa):
                self.assertEqual(html.count(f'id="{id_elementa}"'), 1)
        # id mora biti jedinstven: "rang-dana" nosi samo json_script, sekcija ima drugi id.
        self.assertEqual(html.count('id="rang-dana"'), 1)
        self.assertRegex(html, r'id="dnevni-dugme"[^>]*href="/dnevni/"')
        self.assertNotIn("nazad-dugme", html)

    def test_dnevna_strana_nema_listu_dana_ni_novu_igru(self):
        html = self.dnevni().content.decode("utf-8")
        for nema in ('id="nova-forma"', 'action="/nova/"', 'id="dnevni-dugme"', 'id="rang-dana-sekcija"',
                     'id="rang-dana"', "Нова игра"):
            with self.subTest(nema):
                self.assertNotIn(nema, html)
        self.assertEqual(html.count('id="nazad-dugme"'), 1)
        self.assertRegex(html, r'id="nazad-dugme"[^>]*href="/"')
        self.assertEqual(html.count('id="dnevni"'), 1)
        self.assertEqual(html.count("12.11.2026"), 1)
        # Izbor jezika vraca na dnevnu stranu, ne na pocetnu.
        self.assertIn('name="next" value="/dnevni/"', html)

    def test_adrese_dnevne_strane_su_dnevne_a_pocetne_obicne(self):
        dnevna = self.dnevni().content.decode("utf-8")
        obicna = self.client.get(reverse("pocetna")).content.decode("utf-8")
        for html, adrese in (
            (dnevna, ("/dnevni/potez/", "/dnevni/sacuvaj/", "/dnevni/podeli/")),
            (obicna, ("/potez/", "/sacuvaj/", "/podeli/")),
        ):
            for atribut, adresa in zip(("potez", "sacuvaj", "podeli"), adrese):
                with self.subTest(atribut=atribut, adresa=adresa):
                    self.assertIn(f'data-url-{atribut}="{adresa}"', html)

    def test_srpski_tekstovi_na_obe_strane(self):
        pocetna = self.client.get(reverse("pocetna")).content.decode("utf-8")
        dnevna = self.dnevni().content.decode("utf-8")
        for tekst in ("Дневни изазов", "Играј дневни изазов", "Ранг листа дана", "Данас још нема сачуваних резултата."):
            with self.subTest(tekst):
                self.assertIn(tekst, pocetna)
        for tekst in ("Дневни изазов", "Назад на главну игру", "Ранг листа дана"):
            with self.subTest(tekst):
                self.assertIn(tekst, dnevna)

    def test_engleski_je_stvarno_aktivan_na_obe_strane(self):
        klijent = klijent_jezika("en")
        pocetna = klijent.get(reverse("pocetna"))
        dnevna = klijent.get(reverse("dnevni"))
        self.assertEqual(pocetna["Content-Language"], "en")
        self.assertEqual(dnevna["Content-Language"], "en")
        pocetna, dnevna = pocetna.content.decode("utf-8"), dnevna.content.decode("utf-8")
        self.assertIn('<html lang="en">', pocetna)
        self.assertIn('<html lang="en">', dnevna)
        for tekst in ("Daily challenge", "Play the daily challenge", "Today's leaderboard", "No saved results today yet."):
            with self.subTest(tekst):
                self.assertIn(tekst, pocetna)
        recenica = "Today everyone plays the same game: the same tasks and the same outcomes. The daily challenge is played once."
        for tekst in ("Daily challenge", "Back to the main game", "Today's leaderboard", "No saved results today yet.", recenica):
            with self.subTest(tekst):
                self.assertIn(tekst, dnevna)
        for ostalo in ("Дневни изазов", "Играј дневни изазов", "Назад на главну игру", "Ранг листа дана"):
            with self.subTest(ostalo):
                self.assertNotIn(ostalo, pocetna)
                self.assertNotIn(ostalo, dnevna)
        # Datum dana na engleskoj strani je Y-m-d.
        self.assertIn("2026-11-12", dnevna)

    def test_katalozi_nose_sve_nove_poruke_na_oba_jezika(self):
        for srpski, engleski in TEKSTOVI_DNEVNOG.items():
            with self.subTest(srpski[:30]):
                self.assertTrue(engleski)
                self.assertNotEqual(engleski, srpski)
                with translation.override("en"):
                    self.assertEqual(gettext(srpski), engleski)
                with translation.override("sr"):
                    self.assertEqual(gettext(srpski), srpski)


class DnevniModeratorTests(OsnovaModeratora):
    """Pregled, brisanje i dnevnik za dnevne redove (moderacija.py i brisanje.py)."""

    def setUp(self):
        super().setUp()
        zakrpa = mock.patch.object(views, "_danas", lambda: DAN)
        zakrpa.start()
        self.addCleanup(zakrpa.stop)
        self.mod = napravi_moderatora("Mod")
        self.klijent = self.klijent_za(self.mod)

    def test_pregled_ima_dve_liste_koje_se_ne_mesaju(self):
        upisi_red("Glavni1", 90)
        upisi_red("Glavni2", 80)
        juce = upisi_red("Jucerasnji", 95, dan=JUCE)
        for poeni in range(10, 70, 5):  # 12 redova danas
            upisi_red(f"Dan{poeni}", poeni, dan=DAN)
        odgovor = self.klijent.get(reverse("moderator"))
        self.assertEqual(odgovor.status_code, 200)
        glavna, dana = odgovor.context["rezultati"], odgovor.context["rezultati_dana"]
        self.assertEqual([r["ime"] for r in glavna], ["Glavni1", "Glavni2"])
        self.assertEqual([r["mesto"] for r in glavna], [1, 2])
        self.assertEqual(len(dana), 12)
        self.assertEqual([r["mesto"] for r in dana], list(range(1, 13)))
        self.assertEqual([r["poeni"] for r in dana], list(range(65, 5, -5)))
        self.assertTrue(all(r["javno"] for r in glavna))
        self.assertEqual([r["javno"] for r in dana], [True] * p.RANG_MESTA + [False] * 2)
        self.assertTrue(all(r["dan"] for r in dana))
        self.assertTrue(all(r["dan"] is None for r in glavna))
        self.assertNotIn(juce.id, {r["id"] for r in glavna + dana})
        html = odgovor.content.decode("utf-8")
        self.assertIn("Главна ранг листа", html)
        self.assertIn("Дневни изазов, данас", html)

    def test_mesto_u_potvrdi_se_broji_u_istoj_listi(self):
        upisi_red("Glavni1", 90)
        upisi_red("Glavni2", 80)
        dnevni = upisi_red("Dnevni", 50, dan=DAN)
        odgovor = self.klijent.get(reverse("moderator_rezultat", args=[dnevni.id]))
        self.assertEqual(odgovor.status_code, 200)
        red = odgovor.context["red"]
        self.assertEqual((red["mesto"], red["javno"]), (1, True))  # mesto 3 bi znacilo da se liste mesaju

    def test_starije_dnevne_redove_moderator_ne_brise_a_komanda_brise(self):
        juce = upisi_red("Jucerasnji", 70, dan=JUCE)
        self.assertEqual(self.klijent.get(reverse("moderator_rezultat", args=[juce.id])).status_code, 404)
        self.assertEqual(self.klijent.post(reverse("moderator_rezultat", args=[juce.id])).status_code, 404)
        self.assertTrue(Rezultat.objects.filter(pk=juce.pk).exists())
        call_command("rezultat_obrisi", str(juce.id), stdout=StringIO())
        self.assertFalse(Rezultat.objects.filter(pk=juce.pk).exists())
        self.assertEqual(ZapisDnevnika.objects.get().snimak["dan"], "2026-11-11")

    def test_brisanje_dnevnog_reda_nosi_dan_u_snimku_a_obicnog_ne(self):
        dnevni = upisi_red("Dnevni", 70, dan=DAN)
        obicni = upisi_red("Obicni", 60)
        for red in (dnevni, obicni):
            odgovor = self.klijent.post(reverse("moderator_rezultat", args=[red.id]))
            self.assertEqual(odgovor.status_code, 302)
        self.assertEqual(Rezultat.objects.count(), 0)
        zapisi = {z.snimak["ime"]: z.snimak for z in ZapisDnevnika.objects.all()}
        self.assertEqual(set(zapisi), {"Dnevni", "Obicni"})
        self.assertEqual(set(zapisi["Dnevni"]), KLJUCEVI_SNIMKA | {"dan"})
        self.assertEqual(zapisi["Dnevni"]["dan"], "2026-11-12")
        self.assertEqual(set(zapisi["Obicni"]), KLJUCEVI_SNIMKA)

    def test_dnevnik_oznacava_samo_dnevni_red_na_oba_jezika(self):
        brisanje.obrisi_rezultate([upisi_red("Dnevni", 70, dan=DAN).id], ko=self.mod)
        brisanje.obrisi_rezultate([upisi_red("Obicni", 60).id], ko=self.mod)
        for jezik, oznaka in (("sr", "дневни изазов"), ("en", "daily challenge")):
            with self.subTest(jezik):
                klijent = klijent_jezika(jezik)
                self.klijent_za(self.mod, klijent=klijent)
                odgovor = klijent.get(reverse("moderator_dnevnik"))
                self.assertEqual(odgovor.status_code, 200)
                self.assertEqual(vidljiv_tekst(odgovor.content.decode("utf-8")).count(oznaka), 1)
                opisi = [z["snimak"] for z in odgovor.context["zapisi"]]
                self.assertEqual(len(opisi), 2)
                self.assertEqual(sorted(("dan" in s) for s in opisi), [False, True])
        # Dnevnik ne nosi partiju ni seme.
        for zapis in ZapisDnevnika.objects.all():
            self.assertNotIn("partija", zapis.snimak)


class DnevneKomandeTests(TestCase):
    def pokreni(self, *argumenti):
        izlaz = StringIO()
        call_command(*argumenti, stdout=izlaz)
        return izlaz.getvalue()

    def test_rezultati_bez_dana_ispisuje_samo_glavnu_listu(self):
        upisi_red("Glavni", 50)
        upisi_red("Dnevni", 70, dan=DAN)
        izlaz = self.pokreni("rezultati")
        self.assertIn("'Glavni'", izlaz)
        self.assertNotIn("'Dnevni'", izlaz)
        self.assertIn("dan=None", izlaz)
        self.assertEqual(len(izlaz.strip().splitlines()), 1)

    def test_rezultati_sa_danom_ispisuje_listu_tog_dana_po_rangu(self):
        upisi_red("Glavni", 99)
        upisi_red("Nizi", 40, dan=DAN)
        upisi_red("Visi", 80, dan=DAN)
        upisi_red("Drugi dan", 90, dan=JUCE)
        izlaz = self.pokreni("rezultati", "--dan", "2026-11-12").strip().splitlines()
        self.assertEqual(len(izlaz), 2)
        self.assertIn("1. ", izlaz[0])
        self.assertIn("'Visi'", izlaz[0])
        self.assertIn("'Nizi'", izlaz[1])
        self.assertTrue(all("dan=2026-11-12" in red for red in izlaz))
        self.assertIn("'Drugi dan'", self.pokreni("rezultati", "--dan", "2026-11-11"))
        self.assertEqual(self.pokreni("rezultati", "--dan", "2026-01-01").strip(), "Nema sacuvanih rezultata.")

    def test_rezultati_odbija_los_dan(self):
        upisi_red("Dnevni", 70, dan=DAN)
        for dan in ("12.11.2026", "2026-13-01", "", "juce", "2026-11-12; DROP"):
            with self.subTest(dan=dan), self.assertRaises(CommandError):
                self.pokreni("rezultati", "--dan", dan)


class MigracijaDanTests(TransactionTestCase):
    """Tacka (8): 0013_rezultat_dan na bazi sa redovima; samo test baza (MigrationExecutor, kao 0006-0008)."""

    PRE = [("igra", "0012_pokusaj_prijave")]
    POSLE = [("igra", "0013_rezultat_dan")]

    def setUp(self):
        # Zastita: test baza nikad nije db.sqlite3 projekta.
        ime = str(connection.settings_dict["NAME"])
        self.assertNotIn("db.sqlite3", ime)
        self.assertTrue(ime.startswith("file:memorydb") or ime == ":memory:", ime)
        self.addCleanup(self.na_poslednju)

    def migriraj(self, cilj):
        izvrsilac = MigrationExecutor(connection)
        izvrsilac.migrate(cilj)
        izvrsilac.loader.build_graph()
        return izvrsilac.loader.project_state(cilj).apps

    def na_poslednju(self):
        with connection.cursor() as kursor:
            kursor.execute('DELETE FROM "igra_rezultat"')
        izvrsilac = MigrationExecutor(connection)
        izvrsilac.migrate(izvrsilac.loader.graph.leaf_nodes())

    def kolone(self):
        with connection.cursor() as kursor:
            kursor.execute('PRAGMA table_info("igra_rezultat")')
            return {red[1]: red for red in kursor.fetchall()}

    def indeksi(self):
        with connection.cursor() as kursor:
            kursor.execute("SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'igra_rezultat'")
            return {red[0] for red in kursor.fetchall()}

    def test_dan_je_null_a_glavna_lista_ista(self):
        apps = self.migriraj(self.PRE)
        self.assertNotIn("dan", self.kolone())
        self.assertNotIn("igra_dan_rang_idx", self.indeksi())
        R = apps.get_model("igra", "Rezultat")
        raniji, kasniji = utc(2026, 11, 10, 8, 0, 0), utc(2026, 11, 11, 8, 0, 0)
        for ime, poeni, sacuvan in (("Prvi", 90, kasniji), ("Drugi", 70, kasniji), ("Treci", 70, raniji), ("Cetvrti", 10, raniji)):
            R.objects.create(ime=ime, poeni=poeni, ocena="skup", pravila=2, partija=f"mig-{ime}", sacuvan=sacuvan)
        pre = list(
            R.objects.order_by("-poeni", "sacuvan", "id").values_list("id", "ime", "poeni", "ocena", "pravila", "partija", "sacuvan")
        )
        self.assertEqual([red[1] for red in pre], ["Prvi", "Treci", "Drugi", "Cetvrti"])

        self.migriraj(self.POSLE)
        kolone = self.kolone()
        self.assertIn("dan", kolone)
        self.assertEqual(kolone["dan"][2].upper(), "DATE")
        self.assertEqual(kolone["dan"][3], 0)  # nullable
        self.assertIsNone(kolone["dan"][4])  # bez default-a
        self.assertIn("igra_dan_rang_idx", self.indeksi())
        with connection.cursor() as kursor:
            kursor.execute('PRAGMA index_info("igra_dan_rang_idx")')
            self.assertEqual([red[2] for red in kursor.fetchall()], ["dan", "poeni", "sacuvan", "id"])
        self.assertEqual(Rezultat.objects.count(), 4)
        self.assertEqual(Rezultat.objects.filter(dan__isnull=False).count(), 0)
        posle = list(
            Rezultat.objects.glavna().po_rangu().values_list("id", "ime", "poeni", "ocena", "pravila", "partija", "sacuvan")
        )
        self.assertEqual(posle, pre)
        self.assertEqual([r.ime for r in Rezultat.objects.glavna().najboljih()], ["Prvi", "Treci", "Drugi", "Cetvrti"])
        self.assertEqual(list(Rezultat.objects.dana(DAN)), [])

    def test_posle_migracije_dnevni_red_ide_samo_na_listu_dana(self):
        self.migriraj(self.PRE)
        self.migriraj(self.POSLE)
        stari = upisi_red("Stari", 50)
        novi = upisi_red("Novi", 60, dan=DAN)
        self.assertEqual(list(Rezultat.objects.glavna()), [stari])
        self.assertEqual(list(Rezultat.objects.dana(DAN)), [novi])
        novi.refresh_from_db()
        self.assertEqual(novi.dan, DAN)


class IzvozRangListeTests(OsnovaModeratora):
    """CSV izvoz glavne i danasnje dnevne liste: samo moderator, cela lista, Excel (BOM, ';'), bez formula."""

    def setUp(self):
        super().setUp()
        zakrpa = mock.patch.object(views, "_danas", lambda: DAN)
        zakrpa.start()
        self.addCleanup(zakrpa.stop)
        self.mod = self.klijent_za(napravi_moderatora("Mod"))

    def redovi(self, odgovor):
        tekst = odgovor.content.decode("utf-8")
        self.assertTrue(tekst.startswith("﻿"))
        return list(csv.reader(io.StringIO(tekst[1:], newline=""), delimiter=";"))

    def test_bez_prijave_na_prijavu(self):
        for ruta in ("moderator_izvoz_glavne", "moderator_izvoz_dana"):
            self.assertNaPrijavu(Client().get(reverse(ruta)))

    def test_glavna_cela_lista_po_rangu_bez_dnevnih(self):
        for i in range(moderacija.PREGLED_REDOVA + 5):
            upisi_red(ime=f"Igrac{i}", poeni=40)
        upisi_red(ime="Prvi", poeni=90)
        upisi_red(ime="Dnevni", poeni=95, dan=DAN)
        odgovor = self.mod.get(reverse("moderator_izvoz_glavne"))
        self.assertEqual(odgovor.status_code, 200)
        self.assertIn("attachment", odgovor["Content-Disposition"])
        redovi = self.redovi(odgovor)
        self.assertEqual(len(redovi), 1 + moderacija.PREGLED_REDOVA + 6)
        self.assertEqual(redovi[1][:3], ["1", "Prvi", "90"])
        self.assertNotIn("Dnevni", odgovor.content.decode("utf-8"))

    def test_dnevna_samo_danas(self):
        upisi_red(ime="Danas", poeni=60, dan=DAN)
        upisi_red(ime="Juce", poeni=70, dan=DAN - datetime.timedelta(days=1))
        upisi_red(ime="Obican", poeni=80)
        odgovor = self.mod.get(reverse("moderator_izvoz_dana"))
        self.assertIn(DAN.isoformat(), odgovor["Content-Disposition"])
        self.assertEqual([r[1] for r in self.redovi(odgovor)[1:]], ["Danas"])

    def test_ime_kao_formula_ne_izvrsava_se(self):
        upisi_red(ime="=1+1", poeni=50)
        redovi = self.redovi(self.mod.get(reverse("moderator_izvoz_glavne")))
        self.assertEqual(redovi[1][1], "'=1+1")

    def test_zarez_u_imenu_ne_deli_celiju(self):
        # Excel sa zarezom kao separatorom: polje pod navodnicima ostaje jedna celija, pa "=" nije pocetak.
        upisi_red(ime="x,=1+1", poeni=50)
        tekst = self.mod.get(reverse("moderator_izvoz_glavne")).content.decode("utf-8")[1:]
        po_zarezu = list(csv.reader(io.StringIO(tekst, newline="")))
        self.assertFalse(any(c.lstrip().startswith("=") for red in po_zarezu for c in red))

    def test_pregled_ima_linkove(self):
        upisi_red(poeni=50)
        upisi_red(poeni=50, dan=DAN)
        sadrzaj = self.mod.get(reverse("moderator")).content.decode("utf-8")
        self.assertIn(reverse("moderator_izvoz_glavne"), sadrzaj)
        self.assertIn(reverse("moderator_izvoz_dana"), sadrzaj)


# ---------- Prijava neprikladnog imena (odluka 2026-11-12) ----------
# Statusi, kodovi gresaka i tekstovi su prepisani iz ugovora (plan u projekat-odluke), ne citaju se iz koda.

PRIJAVA_PRIMLJENA = {"sr": "Пријава је примљена. Хвала.", "en": "Report received. Thank you."}
PRIJAVA_NIJE_NA_LISTI = {
    "sr": "Овај резултат више није на ранг листи. Освежите страну.",
    "en": "This result is no longer on the leaderboard. Refresh the page.",
}
# Tekst bloka prijave u sablonu igre: naslov, natpis izbora, dugme, pomoc.
TEKSTOVI_PRIJAVE = {
    "sr": ("Пријави неприкладно име", "Име које пријављујете", "Пошаљи пријаву",
           "Модератор ће прегледати име и одлучити да ли се резултат брише."),
    "en": ("Report an inappropriate name", "Name you are reporting", "Send report",
           "A moderator will review the name and decide whether the result is deleted."),
}
# Odeljak na pregledu moderatora: naslov, dva natpisa, dugme odluke i dve poruke posle odluke.
TEKSTOVI_PRIJAVLJENIH = {
    "sr": {"naslov": "Пријављена имена", "broj": "Број пријава", "prva": "Прва пријава", "ostavi": "Остави",
           "ostavljeno": "Име је остављено, а пријаве су уклоњене.", "vec_reseno": "Ове пријаве су већ решене.",
           "prazno": "Нема пријављених имена."},
    "en": {"naslov": "Reported names", "broj": "Number of reports", "prva": "First report", "ostavi": "Keep",
           "ostavljeno": "The name was kept and the reports were removed.",
           "vec_reseno": "These reports have already been resolved.", "prazno": "No reported names."},
}
RADNJA_ODBACENA = {"sr": "одбачена пријава имена", "en": "name report dismissed"}
UPIS_PRIJAVE = re.compile(r'^INSERT INTO "igra_prijavaimena"')
BLOK_PRIJAVE = re.compile(r'<details class="rang-prijava" data-mesto="prijava" hidden>')
DUGME_OSTAVI = re.compile(
    r'<form method="post" action="(/moderator/rezultat/\d+/ostavi/)">.*?'
    r'<button type="submit" class="btn dugme dugme-sporedno mod-radnja">([^<]*)<', re.S
)
KLJUCEVI_PRIJAVLJENOG = {"id", "mesto", "ime", "poeni", "ocena", "datum", "javno", "dan", "prijava", "prva_prijava"}


@override_settings(PASSWORD_HASHERS=BRZI_HES)
class PrijavaImenaTests(OsnovaDnevnog):
    """POST /prijavi/: igrac prijavljuje ime sa glavne liste ili sa liste dana; o imenu odlucuje moderator."""

    def igrac(self):
        """Nov posetilac: GET pocetne pravi partiju, pa sesija sa partijom postoji."""
        klijent = Client()
        self.assertEqual(klijent.get(reverse("pocetna")).status_code, 200)
        return klijent

    def prijavi_sirovo(self, telo, klijent=None, tip=JSON_TIP):
        return (klijent or self.client).post(reverse("prijavi"), data=telo, content_type=tip)

    def prijavi(self, oznaka, klijent=None):
        return self.prijavi_sirovo(json.dumps({"red": oznaka}), klijent)

    def assertPrimljeno(self, odgovor):
        self.assertEqual(odgovor.status_code, 200, odgovor.content)
        self.assertEqual(odgovor["Content-Type"], JSON_TIP)
        self.assertEqual(json.loads(odgovor.content), {"primljeno": True})

    def assertGreska(self, odgovor, status, greska):
        self.assertEqual(odgovor.status_code, status, odgovor.content)
        self.assertEqual(json.loads(odgovor.content), {"greska": greska})

    def test_red_liste_nosi_oznaku_koja_nije_id_ni_partija(self):
        glavni = [upisi_red(f"Glavni{i}", 90 - i) for i in range(3)]
        dnevni = upisi_red("Dnevni", 50, dan=DAN)
        odgovor = self.client.get(reverse("pocetna"))
        glavna, dana = rang_iz_html(odgovor)["lista"], rang_dana_iz_html(odgovor)["lista"]
        self.assertEqual([r["red"] for r in glavna], [oznaka_reda(r) for r in glavni])
        self.assertEqual([r["red"] for r in dana], [oznaka_reda(dnevni)])
        oznake = [r["red"] for r in glavna + dana]
        self.assertEqual(len(set(oznake)), 4)
        for oznaka in oznake:
            self.assertIsNotNone(OBLIK_OZNAKE_REDA.fullmatch(oznaka), oznaka)
        # Nije id ni partija, a partija nije ni u odgovoru (kontrola: u bazi postoji).
        for red in glavni + [dnevni]:
            with self.subTest(ime=red.ime):
                self.assertTrue(Rezultat.objects.filter(partija=red.partija).exists())
                self.assertNotEqual(oznaka_reda(red), str(red.id))
                self.assertNotIn(oznaka_reda(red), red.partija)
                self.assertNotIn(red.partija.encode(), odgovor.content)
        # Ista za drugog posetioca i na drugom jeziku: red se prepoznaje i sa tudje strane.
        engleska = rang_iz_html(klijent_jezika("en").get(reverse("pocetna")))["lista"]
        self.assertEqual([r["red"] for r in engleska], [r["red"] for r in glavna])
        # Zavisi od SECRET_KEY: bez kljuca se iz partije ne racuna.
        with override_settings(SECRET_KEY="drugi-kljuc-za-oznaku-reda-" + "x" * 30):
            pod_drugim = rang_iz_html(Client().get(reverse("pocetna")))["lista"]
        self.assertEqual([r["ime"] for r in pod_drugim], [r["ime"] for r in glavna])
        for staro, novo in zip(glavna, pod_drugim):
            self.assertNotEqual(staro["red"], novo["red"])

    def test_prijava_upisuje_jednu_po_sesiji_i_nista_ne_sakriva(self):
        red = upisi_red("Ружно", 70)
        ostali = upisi_red("Друго", 60)
        prvi, drugi = self.igrac(), self.igrac()
        stanje_pre = prvi.session["igra"]
        self.assertPrimljeno(self.prijavi(oznaka_reda(red), prvi))
        prijava = PrijavaImena.objects.get()
        self.assertEqual(prijava.rezultat_id, red.id)
        # Trag sesije je HMAC (64 heksadecimalne cifre), nikad kljuc sesije.
        self.assertRegex(prijava.sesija, r"^[0-9a-f]{64}$")
        self.assertNotIn(prvi.session.session_key, prijava.sesija)
        # Ista sesija i isti red: isti odgovor, bez drugog upisa. Druga sesija: druga prijava.
        self.assertPrimljeno(self.prijavi(oznaka_reda(red), prvi))
        self.assertEqual(PrijavaImena.objects.count(), 1)
        self.assertPrimljeno(self.prijavi(oznaka_reda(red), drugi))
        self.assertEqual(PrijavaImena.objects.filter(rezultat=red).count(), 2)
        self.assertEqual(PrijavaImena.objects.values("sesija").distinct().count(), 2)
        self.assertFalse(PrijavaImena.objects.filter(rezultat=ostali).exists())
        # Prijava nista ne sakriva, ne brise i ne dira partiju: odlucuje moderator.
        lista = rang_iz_html(prvi.get(reverse("pocetna")))["lista"]
        self.assertEqual([r["ime"] for r in lista], ["Ружно", "Друго"])
        self.assertEqual(prvi.session["igra"], stanje_pre)
        self.assertTrue(Rezultat.objects.filter(pk=red.pk).exists())
        self.assertFalse(ZapisDnevnika.objects.exists())

    def test_bez_partije_409_bez_upisa_i_bez_nove_sesije(self):
        red = upisi_red("Ружно", 70)
        izmisljen = Client()
        izmisljen.cookies[settings.SESSION_COOKIE_NAME] = "izmisljenkljucsesije0123456789ab"
        bez_partije = Client()
        sesija = bez_partije.session
        sesija["nesto"] = 1
        sesija.save()
        sesija_pre = Session.objects.count()
        for opis, klijent in (("bez sesije", Client()), ("izmisljen sessionid", izmisljen),
                              ("sesija bez partije", bez_partije)):
            with self.subTest(opis):
                self.assertGreska(self.prijavi(oznaka_reda(red), klijent), 409, "nema_igre")
        self.assertFalse(PrijavaImena.objects.exists())
        self.assertEqual(Session.objects.count(), sesija_pre)
        # Kontrola: isti zahtev iz sesije sa partijom prolazi; dovoljna je i samo dnevna partija.
        samo_dnevna = self.novi_igrac()
        self.assertNotIn("igra", samo_dnevna.session)
        self.assertPrimljeno(self.prijavi(oznaka_reda(red), samo_dnevna))
        self.assertPrimljeno(self.prijavi(oznaka_reda(red), self.igrac()))
        self.assertEqual(PrijavaImena.objects.count(), 2)

    def test_neispravan_zahtev_400_pre_citanja_sesije(self):
        red = upisi_red("Ружно", 70)
        oznaka = oznaka_reda(red)
        igrac = self.igrac()
        tela = [
            "{", "", "[]", '"' + oznaka + '"', "5", "null", "true",
            json.dumps({}), json.dumps({"oznaka": oznaka}), json.dumps({"red": oznaka, "ime": "x"}),
            json.dumps({"red": None}), json.dumps({"red": 5}), json.dumps({"red": True}),
            json.dumps({"red": [oznaka]}), json.dumps({"red": {"red": oznaka}}),
            json.dumps({"red": "A" * 32}), json.dumps({"red": oznaka[:-1]}), json.dumps({"red": oznaka + "0"}),
            json.dumps({"red": oznaka + "\n"}), json.dumps({"red": " " + oznaka}), json.dumps({"red": ""}),
            json.dumps({"red": str(red.id)}), json.dumps({"red": red.partija}),
            json.dumps({"red": oznaka, "x": "y" * 3000}),  # telo preko 2 KB
        ]
        for telo in tela:
            for opis, klijent in (("sa partijom", igrac), ("bez partije", Client())):
                with self.subTest(telo=telo[:40], klijent=opis):
                    self.assertGreska(self.prijavi_sirovo(telo, klijent), 400, "neispravan_zahtev")
        # Forma umesto JSON-a: isto.
        self.assertGreska(igrac.post(reverse("prijavi"), {"red": oznaka}), 400, "neispravan_zahtev")
        self.assertFalse(PrijavaImena.objects.exists())
        # Kontrola: ispravno telo iz iste sesije prolazi.
        self.assertPrimljeno(self.prijavi(oznaka, igrac))
        self.assertEqual(PrijavaImena.objects.count(), 1)

    def test_prijaviti_se_moze_samo_red_sa_ekrana(self):
        redovi = [upisi_red(f"Glavni{i}", 90 - i) for i in range(p.RANG_MESTA + 1)]
        danas = upisi_red("Danas", 50, dan=DAN)
        juce = upisi_red("Juce", 50, dan=JUCE)
        sutra = upisi_red("Sutra", 50, dan=SUTRA)
        igrac = self.igrac()
        for opis, red in (("deseti na glavnoj", redovi[p.RANG_MESTA - 1]), ("lista danas", danas)):
            with self.subTest(opis):
                self.assertPrimljeno(self.prijavi(oznaka_reda(red), igrac))
        for opis, oznaka in (
            ("jedanaesti na glavnoj", oznaka_reda(redovi[p.RANG_MESTA])),
            ("lista juce", oznaka_reda(juce)),
            ("lista sutra", oznaka_reda(sutra)),
            ("nepostojeca oznaka", "0" * 32),
        ):
            with self.subTest(opis):
                self.assertGreska(self.prijavi(oznaka, igrac), 409, "nije_na_listi")
        self.assertEqual(set(PrijavaImena.objects.values_list("rezultat_id", flat=True)),
                         {redovi[p.RANG_MESTA - 1].id, danas.id})
        # Red obrisan posle ucitavanja strane: ista greska, bez upisa.
        obrisan = oznaka_reda(redovi[0])
        brisanje.obrisi_rezultate([redovi[0].id])
        self.assertGreska(self.prijavi(obrisan, igrac), 409, "nije_na_listi")
        # Brisanjem prvog jedanaesti ulazi na listu, pa tek tada moze da se prijavi.
        self.assertPrimljeno(self.prijavi(oznaka_reda(redovi[p.RANG_MESTA]), igrac))
        self.assertEqual(PrijavaImena.objects.count(), 3)

    def test_ostavljeno_ime_se_vise_ne_belezi_a_odgovor_je_isti(self):
        red = upisi_red("Sporno", 70)
        drugi = upisi_red("Drugo", 60)
        self.assertPrimljeno(self.prijavi(oznaka_reda(red), self.igrac()))
        brisanje.odbaci_prijave([red.id], ko=napravi_moderatora("Mod"))
        self.assertFalse(PrijavaImena.objects.exists())
        posle = self.prijavi(oznaka_reda(red), self.igrac())
        self.assertPrimljeno(posle)
        self.assertFalse(PrijavaImena.objects.exists())
        # Isti bajtovi kao prijava koja se belezi: odgovor ne odaje odluku moderatora.
        obicna = self.prijavi(oznaka_reda(drugi), self.igrac())
        self.assertEqual(PrijavaImena.objects.filter(rezultat=drugi).count(), 1)
        self.assertEqual((posle.status_code, posle.content), (obicna.status_code, obicna.content))

    def test_po_rezultatu_se_belezi_najvise_prijava(self):
        self.assertEqual(p.PRIJAVA_NAJVISE, 100)
        red = upisi_red("Sporno", 70)
        drugi = upisi_red("Drugo", 60)
        with mock.patch.object(p, "PRIJAVA_NAJVISE", 2):
            for _ in range(4):
                self.assertPrimljeno(self.prijavi(oznaka_reda(red), self.igrac()))
            # Granica je po rezultatu: drugi red i dalje prima prijave.
            self.assertPrimljeno(self.prijavi(oznaka_reda(drugi), self.igrac()))
        self.assertEqual(PrijavaImena.objects.filter(rezultat=red).count(), 2)
        self.assertEqual(PrijavaImena.objects.filter(rezultat=drugi).count(), 1)

    def test_prijave_liste_minulog_dana_se_brisu_uz_sledecu_prijavu(self):
        glavni = upisi_red("Glavni", 70)
        danas = upisi_red("Danas", 60, dan=DAN)
        juce = upisi_red("Juce", 60, dan=JUCE)
        for red in (glavni, danas, juce, juce):
            upisi_prijavu(red)
        self.assertEqual(PrijavaImena.objects.filter(rezultat=juce).count(), 2)
        # Odbijen zahtev nista ne brise.
        self.assertGreska(self.prijavi("0" * 32, self.igrac()), 409, "nije_na_listi")
        self.assertEqual(PrijavaImena.objects.filter(rezultat=juce).count(), 2)
        self.assertPrimljeno(self.prijavi(oznaka_reda(glavni), self.igrac()))
        self.assertEqual(sorted(PrijavaImena.objects.values_list("rezultat__ime", flat=True)),
                         ["Danas", "Glavni", "Glavni"])
        self.assertTrue(Rezultat.objects.filter(pk=juce.pk).exists())

    def test_samo_post_i_csrf(self):
        red = upisi_red("Sporno", 70)
        self.assertEqual(self.igrac().get(reverse("prijavi")).status_code, 405)
        strog = Client(enforce_csrf_checks=True)
        self.assertEqual(strog.get(reverse("pocetna")).status_code, 200)
        telo = json.dumps({"red": oznaka_reda(red)})
        self.assertEqual(strog.post(reverse("prijavi"), data=telo, content_type=JSON_TIP).status_code, 403)
        self.assertFalse(PrijavaImena.objects.exists())
        sa_tokenom = strog.post(reverse("prijavi"), data=telo, content_type=JSON_TIP,
                                headers={"x-csrftoken": strog.cookies["csrftoken"].value})
        self.assertPrimljeno(sa_tokenom)
        self.assertEqual(PrijavaImena.objects.count(), 1)

    def test_prijava_ne_upisuje_sesiju(self):
        red = upisi_red("Sporno", 70)
        igrac = self.igrac()
        with CaptureQueriesContext(connection) as uhvaceno:
            self.assertPrimljeno(self.prijavi(oznaka_reda(red), igrac))
        upiti = [upit["sql"] for upit in uhvaceno]
        self.assertEqual([upit for upit in upiti if UPIS_SESIJE.match(upit)], [])
        self.assertEqual(len([upit for upit in upiti if UPIS_PRIJAVE.match(upit)]), 1, upiti)

    def test_blok_prijave_na_obe_strane_i_tekst_na_oba_jezika(self):
        for jezik in JEZICI:
            klijent = klijent_jezika(jezik)
            odgovor = klijent.get(reverse("pocetna"))
            pocetna = odgovor.content.decode("utf-8")
            dnevna = klijent.get(reverse("dnevni")).content.decode("utf-8")
            with self.subTest(jezik=jezik):
                # Pocetna ima dve liste (glavnu i listu dana), dnevna strana jednu. Blok je skriven dok ga
                # skripta ne napuni redovima liste.
                self.assertEqual(len(BLOK_PRIJAVE.findall(pocetna)), 2)
                self.assertEqual(len(BLOK_PRIJAVE.findall(dnevna)), 1)
                self.assertEqual(pocetna.count('data-url-prijavi="/prijavi/"'), 2)
                self.assertEqual(dnevna.count('data-url-prijavi="/prijavi/"'), 1)
                for prefiks in ("rang", "rang-dana"):
                    for deo in ("izbor", "pomoc"):
                        self.assertEqual(pocetna.count(f'id="{prefiks}-prijava-{deo}"'), 1, (prefiks, deo))
                    self.assertEqual(pocetna.count(f'for="{prefiks}-prijava-izbor"'), 1, prefiks)
                    self.assertEqual(pocetna.count(f'aria-describedby="{prefiks}-prijava-pomoc"'), 1, prefiks)
                vidljivo = vidljiv_tekst(pocetna)
                for tekst in TEKSTOVI_PRIJAVE[jezik]:
                    self.assertEqual(vidljivo.count(tekst), 2, tekst)
                poruke = tekstovi_iz_html(odgovor)["poruke"]
                self.assertEqual(poruke["prijavaPrimljena"], PRIJAVA_PRIMLJENA[jezik])
                self.assertEqual(poruke["prijavaNijeNaListi"], PRIJAVA_NIJE_NA_LISTI[jezik])
        # Deljena strana je samo za citanje: bez bloka i bez adrese prijave.
        deljena = self.deljena(upisi_deljeno().token)
        self.assertEqual(deljena.status_code, 200)
        self.assertNotIn(b"data-url-prijavi", deljena.content)
        self.assertNotIn(b'data-mesto="prijava"', deljena.content)

    def test_ogranicenja_tabele_prijava(self):
        red = upisi_red("Sporno", 70)
        PrijavaImena.objects.create(rezultat=red, sesija="a" * 64)
        for opis, sesija in (("ista sesija za isti red", "a" * 64), ("prazan trag sesije", "")):
            with self.subTest(opis):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        PrijavaImena.objects.create(rezultat=red, sesija=sesija)
        self.assertEqual(PrijavaImena.objects.count(), 1)
        # Ista sesija sme da prijavi drugi red.
        PrijavaImena.objects.create(rezultat=upisi_red("Drugo", 60), sesija="a" * 64)
        self.assertEqual(PrijavaImena.objects.count(), 2)


class PrijavljenaImenaModeratorTests(OsnovaModeratora):
    """Odeljak „Пријављена имена“ na pregledu, odluka „Остави“ i njen zapis u dnevniku."""

    def setUp(self):
        super().setUp()
        zakrpa = mock.patch.object(views, "_danas", lambda: DAN)
        zakrpa.start()
        self.addCleanup(zakrpa.stop)
        self.glavni = napravi_moderatora("Glavni", glavni=True)
        self.mod = napravi_moderatora("Mod")
        self.klijent = self.klijent_za(self.mod)

    def prijavljeni(self, klijent=None):
        odgovor = (klijent or self.klijent).get(reverse("moderator"))
        self.assertEqual(odgovor.status_code, 200)
        return odgovor.context["prijavljeni"]

    def ostavi(self, red, klijent=None):
        return (klijent or self.klijent).post(reverse("moderator_ostavi", args=[red.id]))

    def test_pregled_reda_prijavljena_po_broju_pa_po_prvoj_prijavi(self):
        jedna = upisi_red("Jedna", 70)
        tri = upisi_red("Tri", 60)
        dnevni = upisi_red("Dnevni", 50, dan=DAN)
        bez = upisi_red("Bez prijave", 40)
        juce = upisi_red("Juce", 90, dan=JUCE)
        upisi_prijavu(jedna, utc(2026, 11, 10, 13, 5))
        for sat in (9, 8, 10):
            upisi_prijavu(tri, utc(2026, 11, 11, sat, 0))
        upisi_prijavu(dnevni, utc(2026, 11, 10, 12, 0))
        upisi_prijavu(juce)
        upisi_prijavu(juce)
        odgovor = self.klijent.get(reverse("moderator"))
        prijavljeni = odgovor.context["prijavljeni"]
        # Najvise prijava prvo; kod jednakih starija prva prijava. Red bez prijave i red liste ranijeg dana nisu tu.
        self.assertEqual([r["ime"] for r in prijavljeni], ["Tri", "Dnevni", "Jedna"])
        self.assertEqual([r["id"] for r in prijavljeni], [tri.id, dnevni.id, jedna.id])
        self.assertEqual([r["prijava"] for r in prijavljeni], [3, 1, 1])
        for opis in prijavljeni:
            self.assertEqual(set(opis), KLJUCEVI_PRIJAVLJENOG)
        # Najranija od tri prijave je 08:00 UTC, u Beogradu 09:00; 13:05 UTC je 14:05.
        self.assertEqual([r["prva_prijava"] for r in prijavljeni],
                         ["11.11.2026 09:00", "10.11.2026 13:00", "10.11.2026 14:05"])
        # Mesto se broji u listi reda: glavna je Jedna 70, Tri 60, Bez prijave 40; dnevni je prvi na listi dana.
        self.assertEqual([(r["mesto"], r["javno"]) for r in prijavljeni], [(2, True), (1, True), (1, True)])
        self.assertEqual([r["dan"] is not None for r in prijavljeni], [False, True, False])
        html = odgovor.content.decode("utf-8")
        self.assertEqual([adresa for adresa, _ in DUGME_OSTAVI.findall(html)],
                         [reverse("moderator_ostavi", args=[red.id]) for red in (tri, dnevni, jedna)])
        for red in (bez, juce):
            self.assertNotIn(reverse("moderator_ostavi", args=[red.id]), html)
        # Trag sesije i partija ne idu ni moderatoru (kontrola: u bazi postoje).
        self.assertEqual(PrijavaImena.objects.count(), 7)
        for prijava in PrijavaImena.objects.all():
            self.assertNotIn(prijava.sesija.encode(), odgovor.content)
        for red in (jedna, tri, dnevni):
            self.assertNotIn(red.partija.encode(), odgovor.content)
        # Engleski: datum i vreme iz tekstovi.FORMATI.
        engleski = self.klijent_za(self.mod, klijent=klijent_jezika("en"))
        self.assertEqual(self.prijavljeni(engleski)[0]["prva_prijava"], "2026-11-11 09:00")

    def test_bez_prijava_prazan_odeljak(self):
        upisi_red("Bez prijave", 40)
        odgovor = self.klijent.get(reverse("moderator"))
        self.assertEqual(odgovor.context["prijavljeni"], [])
        html = odgovor.content.decode("utf-8")
        self.assertIn(TEKSTOVI_PRIJAVLJENIH["sr"]["prazno"], html)
        self.assertEqual(DUGME_OSTAVI.findall(html), [])

    def test_mesto_prijavljenog_ispod_prikazanih_redova(self):
        for i in range(moderacija.PREGLED_REDOVA):
            upisi_red(f"Igrac{i}", 90)
        poslednji = upisi_red("Poslednji", 10)
        upisi_prijavu(poslednji)
        (opis,) = self.prijavljeni()
        self.assertEqual((opis["ime"], opis["mesto"], opis["javno"]),
                         ("Poslednji", moderacija.PREGLED_REDOVA + 1, False))

    def test_ostavi_brise_prijave_upisuje_dnevnik_i_ime_ostaje(self):
        red = upisi_red("Sporno", 70, utc(2026, 11, 10, 9))
        drugi = upisi_red("Drugo", 60)
        upisi_prijavu(red)
        upisi_prijavu(red)
        upisi_prijavu(drugi)
        odgovor = self.ostavi(red)
        self.assertEqual(odgovor.status_code, 302)
        self.assertEqual(odgovor["Location"], reverse("moderator") + "?poruka=ostavljeno")
        # Prijave tog rezultata su obrisane, tudje nisu; rezultat ostaje.
        self.assertEqual(list(PrijavaImena.objects.values_list("rezultat_id", flat=True)), [drugi.id])
        self.assertTrue(Rezultat.objects.filter(pk=red.pk).exists())
        zapis = ZapisDnevnika.objects.get()
        self.assertEqual((zapis.radnja, zapis.ko_id, zapis.nad_id, zapis.red, zapis.partija),
                         ("prijava_odbacena", self.mod.pk, None, red.id, red.partija))
        self.assertEqual(zapis.snimak, {"ime": "Sporno", "poeni": 70, "ocena": "solidan",
                                        "datum": "2026-11-10T09:00:00+00:00"})
        # PRG: poruka na pregledu, a ime vise nije medju prijavljenima.
        strana = self.klijent.get(odgovor["Location"])
        self.assertIn(TEKSTOVI_PRIJAVLJENIH["sr"]["ostavljeno"], strana.content.decode("utf-8"))
        self.assertEqual([r["ime"] for r in strana.context["prijavljeni"]], ["Drugo"])
        # Igraci ga i dalje vide na listi.
        lista = rang_iz_html(Client().get(reverse("pocetna")))["lista"]
        self.assertEqual([r["ime"] for r in lista], ["Sporno", "Drugo"])
        # Rezultat se i posle ove odluke brise sa pregleda.
        self.assertEqual(self.klijent.post(reverse("moderator_rezultat", args=[red.id])).status_code, 302)
        self.assertFalse(Rezultat.objects.filter(pk=red.pk).exists())
        self.assertEqual(list(ZapisDnevnika.objects.order_by("id").values_list("radnja", flat=True)),
                         ["prijava_odbacena", "rezultat_obrisan"])

    def test_ostavi_dnevni_red_nosi_dan_u_snimku(self):
        dnevni = upisi_red("Dnevni", 50, dan=DAN)
        upisi_prijavu(dnevni)
        self.assertEqual(self.ostavi(dnevni)["Location"], reverse("moderator") + "?poruka=ostavljeno")
        snimak = ZapisDnevnika.objects.get().snimak
        self.assertEqual(set(snimak), KLJUCEVI_SNIMKA | {"dan"})
        self.assertEqual(snimak["dan"], "2026-11-12")

    def test_ostavi_bez_prijava_ili_drugi_put_nista_ne_upisuje(self):
        bez = upisi_red("Bez prijave", 40)
        red = upisi_red("Sporno", 70)
        upisi_prijavu(red)
        pre = otisak_baze()
        odgovor = self.ostavi(bez)
        self.assertEqual(odgovor["Location"], reverse("moderator") + "?poruka=vec_reseno")
        self.assertEqual(otisak_baze(), pre)
        self.assertIn(TEKSTOVI_PRIJAVLJENIH["sr"]["vec_reseno"],
                      self.klijent.get(odgovor["Location"]).content.decode("utf-8"))
        # Dva moderatora: prvi odlucuje, drugi dobija "vec reseno", a dnevnik ima jedan zapis.
        self.assertEqual(self.ostavi(red)["Location"], reverse("moderator") + "?poruka=ostavljeno")
        drugi = self.klijent_za(self.glavni)
        self.assertEqual(self.ostavi(red, drugi)["Location"], reverse("moderator") + "?poruka=vec_reseno")
        self.assertEqual(list(ZapisDnevnika.objects.values_list("radnja", "ko__username")),
                         [("prijava_odbacena", "Mod")])

    def test_ostavi_nepostojeci_obrisan_i_van_opsega(self):
        for broj in (NEPOSTOJECI_ID, VELIKI_ID, 2**63 - 1, 0):
            with self.subTest(broj=broj):
                odgovor = self.klijent.post(reverse("moderator_ostavi", args=[broj]))
                self.assertEqual((odgovor.status_code, odgovor.content), (404, b""))
        # Red liste ranijeg dana nije u opsegu moderatorskih strana (kao brisanje): 404, a prijave ostaju.
        juce = upisi_red("Juce", 70, dan=JUCE)
        upisi_prijavu(juce)
        self.assertEqual(self.ostavi(juce).status_code, 404)
        self.assertEqual(PrijavaImena.objects.filter(rezultat=juce).count(), 1)
        # Obrisan rezultat: poruka "vec obrisano", bez novog zapisa.
        red = upisi_red("Obrisan", 50)
        upisi_prijavu(red)
        self.klijent.post(reverse("moderator_rezultat", args=[red.id]))
        pre = ZapisDnevnika.objects.count()
        self.assertEqual(self.ostavi(red)["Location"], reverse("moderator") + "?poruka=vec_obrisano")
        self.assertEqual(ZapisDnevnika.objects.count(), pre)
        # GET nista ne menja: ruta je samo POST.
        ziv = upisi_red("Ziv", 60)
        upisi_prijavu(ziv)
        self.assertEqual(self.klijent.get(reverse("moderator_ostavi", args=[ziv.id])).status_code, 405)
        self.assertEqual(PrijavaImena.objects.filter(rezultat=ziv).count(), 1)
        self.assertFalse(ZapisDnevnika.objects.filter(radnja="prijava_odbacena").exists())

    def test_ostavi_bez_prijave_moderatora_i_bez_csrf(self):
        red = upisi_red("Sporno", 70)
        upisi_prijavu(red)
        adresa = reverse("moderator_ostavi", args=[red.id])
        strog = Client(enforce_csrf_checks=True)
        strog.force_login(self.mod)
        self.assertEqual(strog.get(reverse("moderator")).status_code, 200)  # postavlja CSRF kolacic
        pre = otisak_baze()
        self.assertNaPrijavu(Client().post(adresa))
        self.assertEqual(strog.post(adresa).status_code, 403)
        self.assertEqual(otisak_baze(), pre)
        # Kontrola: isti zahtev sa tokenom ostavlja ime.
        token = strog.cookies[settings.CSRF_COOKIE_NAME].value
        odgovor = strog.post(adresa, {"csrfmiddlewaretoken": token})
        self.assertEqual(odgovor["Location"], reverse("moderator") + "?poruka=ostavljeno")
        self.assertFalse(PrijavaImena.objects.exists())

    def test_brisanje_prijavljenog_rezultata_odnosi_prijave(self):
        red = upisi_red("Sporno", 70)
        upisi_prijavu(red)
        upisi_prijavu(red)
        self.assertEqual(self.klijent.get(reverse("moderator_rezultat", args=[red.id])).status_code, 200)
        self.assertEqual(PrijavaImena.objects.count(), 2)  # GET potvrde nista ne brise
        odgovor = self.klijent.post(reverse("moderator_rezultat", args=[red.id]))
        self.assertEqual(odgovor["Location"], reverse("moderator") + "?poruka=obrisano")
        self.assertFalse(PrijavaImena.objects.exists())
        self.assertFalse(Rezultat.objects.filter(pk=red.pk).exists())
        self.assertEqual(list(ZapisDnevnika.objects.values_list("radnja", flat=True)), ["rezultat_obrisan"])
        self.assertEqual(self.prijavljeni(), [])
        # I komanda razvijaca odnosi prijave sa redom.
        drugi = upisi_red("Komanda", 60)
        upisi_prijavu(drugi)
        call_command("rezultat_obrisi", str(drugi.id), stdout=StringIO())
        self.assertFalse(PrijavaImena.objects.exists())

    def test_servis_proverava_ulogu_pod_bravom_i_ne_upisuje_delimicno(self):
        red = upisi_red("Sporno", 70)
        upisi_prijavu(red)
        bez_uloge = napravi_korisnika_bez_dozvole("BezDozvole")
        deaktiviran = napravi_moderatora("Deaktiviran")
        User.objects.filter(pk=deaktiviran.pk).update(is_active=False)  # objekat u memoriji je i dalje aktivan
        novajlija = napravi_moderatora("Novajlija", mora_promeniti=True)
        pre = otisak_baze()
        for opis, ko in (("bez uloge", bez_uloge), ("deaktiviran posle citanja", deaktiviran),
                         ("mora da promeni lozinku", novajlija)):
            with self.subTest(opis):
                self.assertOdbijeno(lambda: brisanje.odbaci_prijave([red.id], ko=ko), "nema_prava")
        # Jedan red bez prijave ili nepostojeci id: nista se ne upisuje ni za ostale.
        bez_prijave = upisi_red("Bez prijave", 40)
        pre = otisak_baze()
        with self.assertRaises(brisanje.NemaPrijava):
            brisanje.odbaci_prijave([red.id, bez_prijave.id], ko=self.mod)
        with self.assertRaises(brisanje.NemaReda):
            brisanje.odbaci_prijave([red.id, NEPOSTOJECI_ID], ko=self.mod)
        self.assertEqual(otisak_baze(), pre)
        self.assertEqual(PrijavaImena.objects.filter(rezultat=red).count(), 1)

    def test_odluka_drugog_moderatora_izmedju_citanja_i_brave(self):
        pravo = brisanje.odbaci_prijave
        glavni = User.objects.get(pk=self.glavni.pk)
        for opis, prvi, poruka in (
            ("ostavljen", lambda red: pravo([red.id], ko=glavni), "vec_reseno"),
            ("obrisan", lambda red: brisanje.obrisi_rezultate([red.id], ko=glavni), "vec_obrisano"),
        ):
            with self.subTest(opis):
                red = upisi_red(f"Trka {opis}", 50)
                upisi_prijavu(red)

                def drugi_moderator_prvi(ids, ko, red=red, prvi=prvi):
                    prvi(red)
                    return pravo(ids, ko=ko)

                with mock.patch("igra.brisanje.odbaci_prijave", side_effect=drugi_moderator_prvi):
                    odgovor = self.ostavi(red)
                self.assertEqual(odgovor["Location"], reverse("moderator") + "?poruka=" + poruka)
                self.assertEqual(
                    list(ZapisDnevnika.objects.filter(red=red.id).values_list("ko__username", flat=True)), ["Glavni"]
                )

    def test_uloga_oduzeta_izmedju_dekoratora_i_brave(self):
        red = upisi_red("Sporno", 70)
        upisi_prijavu(red)
        pravo = brisanje.odbaci_prijave

        def deaktiviran_pa_radnja(ids, ko):
            User.objects.filter(pk=self.mod.pk).update(is_active=False)
            return pravo(ids, ko=ko)

        with mock.patch("igra.brisanje.odbaci_prijave", side_effect=deaktiviran_pa_radnja):
            odgovor = self.ostavi(red)
        # Servis odbija, jer ulogu cita ponovo pod bravom; pregled zatim vodi na prijavu.
        self.assertEqual((odgovor.status_code, odgovor["Location"]), (302, reverse("moderator")))
        self.assertNaPrijavu(self.klijent.get(odgovor["Location"]))
        self.assertEqual(PrijavaImena.objects.count(), 1)
        self.assertFalse(ZapisDnevnika.objects.exists())

    def test_dnevnik_prikazuje_odbacenu_prijavu_na_oba_jezika(self):
        red = upisi_red("Sporno", 70, utc(2026, 11, 9, 23, 30))
        upisi_prijavu(red)
        self.assertEqual(self.ostavi(red).status_code, 302)
        # 23:30 UTC je sledeci dan u Beogradu; 70 poena je ocena "solidan".
        for jezik, datum, ocena in (("sr", "10.11.2026", "солидан"), ("en", "2026-11-10", "solid")):
            with self.subTest(jezik=jezik):
                klijent = self.klijent_za(self.mod, klijent=klijent_jezika(jezik))
                odgovor = klijent.get(reverse("moderator_dnevnik"))
                (zapis,) = odgovor.context["zapisi"]
                self.assertEqual(set(zapis), KLJUCEVI_ZAPISA)
                self.assertEqual((zapis["radnja"], zapis["ko"], zapis["nad"]), ("prijava_odbacena", "Mod", None))
                self.assertEqual(zapis["snimak"], {"ime": "Sporno", "poeni": 70, "ocena": ocena, "datum": datum})
                self.assertEqual(vidljiv_tekst(odgovor.content.decode("utf-8")).count(RADNJA_ODBACENA[jezik]), 1)
                # Kljuc radnje nije tekst na ekranu, a partija nikad ne izlazi.
                self.assertNotIn(b"prijava_odbacena", odgovor.content)
                self.assertNotIn(red.partija.encode(), odgovor.content)

    def test_ogranicenja_dnevnika_za_odbacenu_prijavu(self):
        for opis, polja in (
            ("bez reda i partije", {"radnja": "prijava_odbacena"}),
            ("bez partije", {"radnja": "prijava_odbacena", "red": 1}),
            ("sa nad", {"radnja": "prijava_odbacena", "red": 1, "partija": "x", "nad": self.mod}),
        ):
            with self.subTest(opis):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        ZapisDnevnika(**polja).save(force_insert=True)
                with self.assertRaises(ValidationError):
                    ZapisDnevnika.objects.upisi(**polja)
        self.assertFalse(ZapisDnevnika.objects.exists())
        ZapisDnevnika.objects.upisi(radnja="prijava_odbacena", red=1, partija="x", ko=self.mod)
        self.assertEqual(ZapisDnevnika.objects.count(), 1)

    def test_imena_escapeovana_medju_prijavljenima(self):
        for ime in XSS_IMENA:
            upisi_prijavu(upisi_red(ime, 50))
        odgovor = self.klijent.get(reverse("moderator"))
        self.assertEqual(len(odgovor.context["prijavljeni"]), len(XSS_IMENA))
        for ime in XSS_IMENA:
            with self.subTest(ime=ime):
                self.assertNotIn(ime.encode(), odgovor.content)
                self.assertIn(html_modul.escape(ime, quote=False).encode(), odgovor.content)

    def test_tekst_odeljka_i_poruka_na_oba_jezika(self):
        upisi_prijavu(upisi_red("Latin Name", 50))
        for jezik in JEZICI:
            tekst = TEKSTOVI_PRIJAVLJENIH[jezik]
            klijent = self.klijent_za(self.mod, klijent=klijent_jezika(jezik))
            with self.subTest(jezik=jezik):
                html = klijent.get(reverse("moderator")).content.decode("utf-8")
                vidljivo = vidljiv_tekst(html)
                for kljuc in ("naslov", "broj", "prva"):
                    self.assertEqual(vidljivo.count(tekst[kljuc]), 1, tekst[kljuc])
                self.assertEqual([natpis for _, natpis in DUGME_OSTAVI.findall(html)], [tekst["ostavi"]])
                for poruka in ("ostavljeno", "vec_reseno"):
                    strana = klijent.get(reverse("moderator"), {"poruka": poruka})
                    self.assertEqual(strana.context["poruka"], poruka)
                    self.assertEqual(vidljiv_tekst(strana.content.decode("utf-8")).count(tekst[poruka]), 1)


class MigracijaPrijavaTests(TransactionTestCase):
    """0014_prijava_imena na bazi sa zapisima dnevnika, unapred i unazad; samo test baza (kao 0013).

    Prepravka tabele dnevnika brise okidace nepromenljivosti (0010, 0011): migracija ih mora vratiti.
    """

    PRE = [("igra", "0013_rezultat_dan")]
    POSLE = [("igra", "0014_prijava_imena")]
    OKIDACI = {"igra_zapis_bez_izmene", "igra_zapis_bez_zamene"}
    SNIMAK = {"ime": "Обрисан", "poeni": 55, "ocena": "skup", "datum": "2026-11-09T23:30:00+00:00"}

    def setUp(self):
        # Zastita: test baza nikad nije db.sqlite3 projekta.
        ime = str(connection.settings_dict["NAME"])
        self.assertNotIn("db.sqlite3", ime)
        self.assertTrue(ime.startswith("file:memorydb") or ime == ":memory:", ime)
        self.addCleanup(self.na_poslednju)

    def migriraj(self, cilj):
        izvrsilac = MigrationExecutor(connection)
        izvrsilac.migrate(cilj)
        izvrsilac.loader.build_graph()
        return izvrsilac.loader.project_state(cilj).apps

    def na_poslednju(self):
        with connection.cursor() as kursor:
            if "igra_prijavaimena" in connection.introspection.table_names(kursor):
                kursor.execute('DELETE FROM "igra_prijavaimena"')
            kursor.execute('DELETE FROM "igra_zapisdnevnika"')
            kursor.execute('DELETE FROM "igra_rezultat"')
        izvrsilac = MigrationExecutor(connection)
        izvrsilac.migrate(izvrsilac.loader.graph.leaf_nodes())

    def tabele(self):
        with connection.cursor() as kursor:
            return set(connection.introspection.table_names(kursor))

    def okidaci(self):
        with connection.cursor() as kursor:
            kursor.execute("SELECT name FROM sqlite_master WHERE type = 'trigger' AND tbl_name = 'igra_zapisdnevnika'")
            return {red[0] for red in kursor.fetchall()}

    def sema_dnevnika(self):
        with connection.cursor() as kursor:
            kursor.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'igra_zapisdnevnika'")
            return kursor.fetchone()[0]

    def zapisi(self):
        with connection.cursor() as kursor:
            kursor.execute("SELECT id, kada, radnja, ko_id, nad_id, red, partija, snimak "
                           "FROM igra_zapisdnevnika ORDER BY id")
            return kursor.fetchall()

    def assertDnevnikNepromenljiv(self, broj):
        zamena = ("INSERT OR REPLACE INTO igra_zapisdnevnika (id, kada, radnja, red, partija, snimak) "
                  "SELECT id, kada, radnja, red, partija, '{}' FROM igra_zapisdnevnika WHERE id = %s")
        for opis, naredba in (("UPDATE", "UPDATE igra_zapisdnevnika SET snimak = '{}' WHERE id = %s"),
                              ("REPLACE", zamena)):
            with self.subTest(okidac=opis):
                with self.assertRaisesMessage(IntegrityError, "dnevnik se ne menja"):
                    with transaction.atomic():
                        connection.cursor().execute(naredba, [broj])

    def test_unapred_zapisi_netaknuti_i_okidaci_ponovo_postoje(self):
        apps = self.migriraj(self.PRE)
        self.assertEqual(self.okidaci(), self.OKIDACI)
        self.assertNotIn("igra_prijavaimena", self.tabele())
        Korisnik = apps.get_model("auth", "User")
        Zapis = apps.get_model("igra", "ZapisDnevnika")
        mod = Korisnik.objects.create(username="Mod", password="!")
        Zapis.objects.create(radnja="rezultat_obrisan", ko=mod, red=7, partija="a" * 64,
                             kada=utc(2026, 11, 10, 12), snimak=self.SNIMAK)
        Zapis.objects.create(radnja="link_obrisan", red=3, partija="b" * 64, kada=utc(2026, 11, 10, 13),
                             snimak=self.SNIMAK)
        Zapis.objects.create(radnja="moderator_dodat", ko=mod, nad=mod, kada=utc(2026, 11, 10, 14),
                             snimak={"glavni": False})
        pre = self.zapisi()
        self.assertEqual([red[2] for red in pre], ["rezultat_obrisan", "link_obrisan", "moderator_dodat"])

        self.migriraj(self.POSLE)
        self.assertEqual(self.zapisi(), pre)
        self.assertEqual(self.okidaci(), self.OKIDACI)
        self.assertDnevnikNepromenljiv(pre[0][0])
        self.assertEqual(self.zapisi(), pre)
        self.assertIn("igra_prijavaimena", self.tabele())
        sema = self.sema_dnevnika()
        self.assertIn("igra_dnevnik_red_partija", sema)
        self.assertNotIn("igra_dnevnik_brisanje_red", sema)
        # Nova radnja se upisuje, ali samo sa redom i partijom; novi zapis dobija id iza postojecih.
        novi = ZapisDnevnika.objects.upisi(radnja="prijava_odbacena", red=9, partija="c" * 64, snimak=self.SNIMAK)
        self.assertGreater(novi.id, max(red[0] for red in pre))
        with self.assertRaises(IntegrityError), transaction.atomic():
            ZapisDnevnika(radnja="prijava_odbacena").save(force_insert=True)

    def test_unazad_brise_odbacene_prijave_i_vraca_okidace(self):
        self.migriraj(self.POSLE)
        red = upisi_red("Sporno", 70)
        upisi_prijavu(red)
        ostaje = ZapisDnevnika.objects.upisi(radnja="rezultat_obrisan", red=7, partija="a" * 64, snimak=self.SNIMAK)
        ZapisDnevnika.objects.upisi(radnja="prijava_odbacena", red=red.id, partija=red.partija, snimak=self.SNIMAK)
        pre = self.zapisi()
        self.assertEqual([zapis[2] for zapis in pre], ["rezultat_obrisan", "prijava_odbacena"])

        self.migriraj(self.PRE)
        # Stara ogranicenja ne primaju novu radnju: njeni zapisi su obrisani, ostali su isti.
        self.assertEqual(self.zapisi(), pre[:1])
        self.assertEqual(self.okidaci(), self.OKIDACI)
        self.assertDnevnikNepromenljiv(ostaje.id)
        self.assertNotIn("igra_prijavaimena", self.tabele())
        sema = self.sema_dnevnika()
        self.assertIn("igra_dnevnik_brisanje_red", sema)
        self.assertNotIn("prijava_odbacena", sema)
        with self.assertRaises(IntegrityError), transaction.atomic():
            connection.cursor().execute(
                "INSERT INTO igra_zapisdnevnika (kada, radnja, red, partija, snimak) "
                "VALUES ('2026-11-12 12:00:00', 'prijava_odbacena', 9, 'x', '{}')"
            )
        # Rezultat ostaje; prijave su otisle sa tabelom.
        with connection.cursor() as kursor:
            kursor.execute('SELECT ime FROM "igra_rezultat"')
            self.assertEqual(kursor.fetchall(), [("Sporno",)])

        # I ponovo unapred, sa istim zapisom i okidacima.
        self.migriraj(self.POSLE)
        self.assertEqual(self.zapisi(), pre[:1])
        self.assertEqual(self.okidaci(), self.OKIDACI)
        self.assertEqual(PrijavaImena.objects.count(), 0)


class JavnaRangListaTests(OsnovaPrikaza):
    """Javna rang lista za partnere: api/rang-lista/, bela lista polja, bez sesije i kolacica."""

    DAN = datetime.date(2026, 11, 12)
    JUCE = datetime.date(2026, 11, 11)
    KLJUCEVI_REDA = {"mesto", "ime", "poeni", "ocena", "datum", "staro_bodovanje"}

    def setUp(self):
        super().setUp()
        zakrpa = mock.patch.object(views, "_danas", lambda: self.DAN)
        zakrpa.start()
        self.addCleanup(zakrpa.stop)

    def uzmi(self, **dodatno):
        return Client().get("/api/rang-lista/", **dodatno)

    def test_ruta_i_ime(self):
        self.assertEqual(reverse("javna_rang_lista"), "/api/rang-lista/")

    def test_oblik_tela_i_redosled(self):
        pre = timezone.now() - datetime.timedelta(days=2)
        upisi_red("Drugi", 80, sacuvan=pre)
        upisi_red("Prvi", 90)
        upisi_red("Raniji", 70, sacuvan=pre)
        upisi_red("Kasniji", 70)
        odgovor = self.uzmi()
        self.assertEqual(odgovor.status_code, 200)
        telo = json.loads(odgovor.content)
        self.assertEqual(set(telo), {"verzija", "glavna", "danas"})
        self.assertEqual(telo["verzija"], 1)
        self.assertEqual([r["ime"] for r in telo["glavna"]], ["Prvi", "Drugi", "Raniji", "Kasniji"])
        self.assertEqual([r["mesto"] for r in telo["glavna"]], [1, 2, 3, 4])
        for red in telo["glavna"]:
            self.assertEqual(set(red), self.KLJUCEVI_REDA)
        prvi = telo["glavna"][0]
        self.assertEqual(prvi["poeni"], 90)
        self.assertEqual(prvi["ocena"], motor.oceni(90))
        self.assertEqual(prvi["datum"], timezone.localtime(timezone.now()).date().isoformat())
        self.assertIs(prvi["staro_bodovanje"], False)
        self.assertEqual(telo["danas"], {"dan": "2026-11-12", "redovi": []})

    def test_najvise_deset_po_listi(self):
        for i in range(12):
            upisi_red(f"G{i}", 50 + i)
            upisi_red(f"D{i}", 50 + i, dan=self.DAN)
        telo = json.loads(self.uzmi().content)
        self.assertEqual(len(telo["glavna"]), 10)
        self.assertEqual(len(telo["danas"]["redovi"]), 10)
        self.assertEqual(telo["glavna"][0]["poeni"], 61)
        self.assertEqual(telo["glavna"][-1]["poeni"], 52)

    def test_liste_se_ne_mesaju_i_juce_nije_danas(self):
        upisi_red("Obican", 60)
        upisi_red("Dnevni", 70, dan=self.DAN)
        upisi_red("Juce", 99, dan=self.JUCE)
        telo = json.loads(self.uzmi().content)
        self.assertEqual([r["ime"] for r in telo["glavna"]], ["Obican"])
        self.assertEqual([r["ime"] for r in telo["danas"]["redovi"]], ["Dnevni"])

    def test_telo_bez_id_oznake_reda_i_hesa_partije(self):
        crveni = upisi_red("Obican", 60)
        dnevni = upisi_red("Dnevni", 70, dan=self.DAN)
        odgovor = self.uzmi()
        tekst = odgovor.content.decode("utf-8")
        telo = json.loads(tekst)
        zabranjeni_kljucevi = {"id", "pk", "red", "partija", "token", "prijave", "stara_pravila", "pravila", "dan_reda"}
        for red in telo["glavna"] + telo["danas"]["redovi"]:
            self.assertEqual(zabranjeni_kljucevi & set(red), set())
        for rezultat in (crveni, dnevni):
            self.assertNotIn(rezultat.partija, tekst)
            self.assertNotIn(views._oznaka_reda(rezultat), tekst)
        # Provera nije prazna: oznaka reda postoji i ima oblik koji bi se ovde pojavio.
        self.assertRegex(views._oznaka_reda(crveni), r"^[0-9a-f]{32}$")
        self.assertNotIn("sessionid", tekst)

    def test_obrisan_rezultat_nestaje(self):
        upisi_red("Ostaje", 60)
        brise = upisi_red("Brise", 90)
        self.assertEqual(len(json.loads(self.uzmi().content)["glavna"]), 2)
        brise.delete()
        self.assertEqual([r["ime"] for r in json.loads(self.uzmi().content)["glavna"]], ["Ostaje"])

    def test_staro_bodovanje(self):
        upisi_red("Staro", 80, pravila=p.PRAVILA_STARA)
        upisi_red("Novo", 70)
        redovi = {r["ime"]: r for r in json.loads(self.uzmi().content)["glavna"]}
        self.assertIs(redovi["Staro"]["staro_bodovanje"], True)
        self.assertIs(redovi["Novo"]["staro_bodovanje"], False)

    def test_ime_kako_je_sacuvano(self):
        upisi_red('<b>"x"</b>', 60)
        self.assertEqual(json.loads(self.uzmi().content)["glavna"][0]["ime"], '<b>"x"</b>')

    def test_post_405_a_head_radi(self):
        self.assertEqual(Client().post("/api/rang-lista/").status_code, 405)
        odgovor = Client().head("/api/rang-lista/")
        self.assertEqual(odgovor.status_code, 200)

    def test_bez_kolacica_sesije_i_vary_cookie(self):
        pre = Session.objects.count()
        klijent = Client(enforce_csrf_checks=True)
        odgovor = klijent.get("/api/rang-lista/")
        self.assertEqual(odgovor.status_code, 200)
        self.assertEqual(len(odgovor.cookies), 0)
        self.assertNotIn("Set-Cookie", odgovor.headers)
        self.assertNotIn("Cookie", odgovor.get("Vary", ""))
        self.assertEqual(Session.objects.count(), pre)

    def test_zaglavlja(self):
        odgovor = self.uzmi()
        self.assertEqual(odgovor["Content-Type"], "application/json")
        self.assertEqual(odgovor["Access-Control-Allow-Origin"], "*")
        self.assertEqual(odgovor["Cache-Control"], "public, max-age=60")

    def test_isti_odgovor_za_svaki_jezik(self):
        upisi_red("Pera", 60)
        upisi_red("Mika", 70, dan=self.DAN)
        sr = self.uzmi(headers={"accept-language": "sr"})
        en = self.uzmi(headers={"accept-language": "en"})
        kolacic = Client()
        kolacic.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
        en_kolacic = kolacic.get("/api/rang-lista/")
        self.assertEqual(sr.content, en.content)
        self.assertEqual(sr.content, en_kolacic.content)
        self.assertIn('"datum": "', sr.content.decode())


# ---------- Statistika moderatora (zahtev 2026-11-12): ZavrsenaPartija i moderator/statistika/ ----------

from igra.models import ZavrsenaPartija  # noqa: E402  (nova klasa na kraju datoteke, bez izmene uvoza na vrhu)


def upisi_zavrsenu(dan, poeni=50, vrsta="obicna"):
    red = ZavrsenaPartija(dan=dan, vrsta=vrsta, poeni=poeni)
    red.full_clean()
    red.save()
    return red


def celije_reda(red_html):
    return [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<t[hd][^>]*>.*?</t[hd]>", red_html, re.S)]


class ZavrsenaPartijaUpisTests(OsnovaDnevnog):
    """Upis u views.potez: jedan red po partiji koja stigne do zavrsnog ekrana, obicnoj i dnevnoj."""

    def redovi(self):
        return list(ZavrsenaPartija.objects.order_by("id").values_list("dan", "vrsta", "poeni"))

    def test_obicna_jedan_red_tek_posle_osmog_kruga(self):
        self.postavi_igru("seme-statistika-obicna")
        self.odigraj_do(7)
        self.assertEqual(self.redovi(), [])
        self.assertEqual(self.potez(8).status_code, 200)
        poeni = self.stanje()["rezultat"]["poeni"]
        self.assertEqual(self.redovi(), [(DAN, "obicna", poeni)])
        # Zavrsen potez se ne ponavlja (409), pa ni red.
        for krug in (8, 9):
            self.assertEqual(self.potez(krug).status_code, 409)
        self.assertEqual(self.redovi(), [(DAN, "obicna", poeni)])

    def test_dnevna_jedan_red(self):
        klijent = self.novi_igrac()
        self.odigraj_dnevnu(klijent, do=7)
        self.assertEqual(self.redovi(), [])
        self.assertEqual(self.dnevni_potez(8, po_tezini(8), klijent).status_code, 200)
        poeni = self.dnevno_stanje(klijent)["rezultat"]["poeni"]
        self.assertEqual(self.redovi(), [(DAN, "dnevna", poeni)])
        self.assertEqual(self.dnevni_potez(8, po_tezini(8), klijent).status_code, 409)
        self.assertEqual(self.redovi(), [(DAN, "dnevna", poeni)])

    def test_dnevna_posle_ponoci_ide_na_dan_zavrsetka(self):
        klijent = self.novi_igrac()
        self.odigraj_dnevnu(klijent, do=7)
        self.dan = SUTRA
        self.assertEqual(self.dnevni_potez(8, po_tezini(8), klijent).status_code, 200)
        stanje = self.dnevno_stanje(klijent)
        self.assertEqual(stanje["dan"], DAN.isoformat())  # partija je pocela juce
        self.assertEqual(self.redovi(), [(SUTRA, "dnevna", stanje["rezultat"]["poeni"])])

    def test_dve_partije_dva_reda(self):
        self.postavi_igru("seme-statistika-prva")
        self.odigraj_do(8)
        klijent = self.zavrsen_igrac()
        self.assertEqual(sorted(vrsta for _dan, vrsta, _poeni in self.redovi()), ["dnevna", "obicna"])
        self.assertEqual(self.dnevni_potez(1, klijent=klijent).status_code, 409)
        self.assertEqual(len(self.redovi()), 2)

    def test_odbijen_i_neispravan_potez_ne_upisuju(self):
        self.postavi_igru("seme-statistika-odbijen")
        self.odigraj_do(3)
        self.assertEqual(self.potez(8).status_code, 409)  # pogresan krug
        self.assertEqual(self.sirovo(json.dumps({"krug": 4, "izbori": {"model": "x"}})).status_code, 400)
        self.assertEqual(self.potez(4, klijent=Client()).status_code, 409)  # nema igre
        self.assertEqual(self.redovi(), [])

    def test_stariji_redovi_se_brisu_pri_upisu(self):
        granica = DAN - datetime.timedelta(days=views.STATISTIKA_DANA - 1)
        upisi_zavrsenu(granica - datetime.timedelta(days=1), 10)
        upisi_zavrsenu(granica, 20)
        self.zavrsen_igrac()
        redovi = self.redovi()
        self.assertEqual(len(redovi), 2)
        self.assertEqual(redovi[0], (granica, "obicna", 20))
        self.assertEqual(redovi[1][:2], (DAN, "dnevna"))

    def test_model_ne_cuva_nista_o_igracu(self):
        self.assertEqual({f.name for f in ZavrsenaPartija._meta.get_fields()}, {"id", "dan", "vrsta", "poeni"})

    def test_baza_odbija_nepoznatu_vrstu_i_poene_van_opsega(self):
        for polja in ({"vrsta": "druga", "poeni": 50}, {"vrsta": "obicna", "poeni": p.POCETNI_POENI + 1}):
            with self.subTest(polja), self.assertRaises(IntegrityError), transaction.atomic():
                ZavrsenaPartija.objects.create(dan=DAN, **polja)


class StatistikaModeratoraTests(OsnovaModeratora):
    """moderator/statistika/: 7 dana, najnoviji prvi, jedan upit; isti pristup kao ostale moderatorske strane."""

    def setUp(self):
        super().setUp()
        zakrpa = mock.patch.object(views, "_danas", lambda: DAN)
        zakrpa.start()
        self.addCleanup(zakrpa.stop)
        self.mod = napravi_moderatora("Mod")

    def dani(self, jezik="sr"):
        klijent = self.klijent_za(self.mod, klijent=klijent_jezika(jezik))
        odgovor = klijent.get(reverse("moderator_statistika"))
        self.assertEqual(odgovor.status_code, 200)
        return odgovor.context["dani"]

    def test_sedam_dana_najnoviji_prvi_i_prazni_dani(self):
        upisi_zavrsenu(DAN - datetime.timedelta(days=2), 60)
        dani = self.dani()
        self.assertEqual(
            [d["datum"] for d in dani],
            [(DAN - datetime.timedelta(days=n)).strftime("%d.%m.%Y") for n in range(7)],
        )
        prazan = {"ukupno": 0, "obicnih": 0, "dnevnih": 0, "prosek": "—"}
        for indeks, dan in enumerate(dani):
            with self.subTest(indeks):
                bez_datuma = {k: v for k, v in dan.items() if k != "datum"}
                if indeks == 2:
                    self.assertEqual(bez_datuma, {"ukupno": 1, "obicnih": 1, "dnevnih": 0, "prosek": "60,0"})
                else:
                    self.assertEqual(bez_datuma, prazan)

    def test_prosek_jedna_decimala_pola_navise(self):
        # 289 / 4 = 72,25: pola navise daje 72,3 (zaokruzivanje "na paran" dalo bi 72,2).
        for poeni in (72, 72, 72, 73):
            upisi_zavrsenu(DAN, poeni)
        # 211 / 3 = 70,333...
        for poeni, vrsta in ((70, "obicna"), (70, "dnevna"), (71, "dnevna")):
            upisi_zavrsenu(JUCE, poeni, vrsta)
        dani = self.dani()
        self.assertEqual((dani[0]["ukupno"], dani[0]["prosek"]), (4, "72,3"))
        self.assertEqual(
            (dani[1]["ukupno"], dani[1]["obicnih"], dani[1]["dnevnih"], dani[1]["prosek"]), (3, 1, 2, "70,3")
        )
        en = self.dani(jezik="en")
        self.assertEqual((en[0]["prosek"], en[1]["prosek"]), ("72.3", "70.3"))
        self.assertEqual(en[0]["datum"], "2026-11-12")

    def test_stariji_od_sedam_dana_i_buduci_se_ne_vide(self):
        upisi_zavrsenu(DAN - datetime.timedelta(days=6), 40)
        upisi_zavrsenu(DAN - datetime.timedelta(days=7), 90)
        upisi_zavrsenu(SUTRA, 90)
        dani = self.dani()
        self.assertEqual([d["ukupno"] for d in dani], [0, 0, 0, 0, 0, 0, 1])
        self.assertEqual(dani[-1]["prosek"], "40,0")
        # Granice su u upitu, ne samo u prikazu: baza ne vraca dane van prozora.
        self.assertEqual(set(ZavrsenaPartija.objects.po_danu(DAN - datetime.timedelta(days=6), DAN)),
                         {DAN - datetime.timedelta(days=6)})

    def test_jedan_upit_nad_tabelom(self):
        for pomak in range(7):
            upisi_zavrsenu(DAN - datetime.timedelta(days=pomak), 50 + pomak)
        klijent = self.klijent_za(self.mod)
        with CaptureQueriesContext(connection) as upiti:
            odgovor = klijent.get(reverse("moderator_statistika"))
        self.assertEqual(odgovor.status_code, 200)
        nad_tabelom = [u["sql"] for u in upiti.captured_queries if "igra_zavrsenapartija" in u["sql"]]
        self.assertEqual(len(nad_tabelom), 1, nad_tabelom)
        self.assertIn("GROUP BY", nad_tabelom[0])
        self.assertEqual([d["ukupno"] for d in odgovor.context["dani"]], [1] * 7)

    def test_tabela_u_html(self):
        upisi_zavrsenu(DAN, 72)
        upisi_zavrsenu(DAN, 73, "dnevna")
        html = self.klijent_za(self.mod).get(reverse("moderator_statistika")).content.decode("utf-8")
        tabela = re.search(r'<table id="statistika-tabela".*?</table>', html, re.S).group(0)
        redovi = re.findall(r"<tr>(.*?)</tr>", re.search(r"<tbody>(.*?)</tbody>", tabela, re.S).group(1), re.S)
        self.assertEqual(len(redovi), 7)
        self.assertEqual(celije_reda(redovi[0]), ["12.11.2026", "2", "1", "1", "72,5"])
        self.assertEqual(celije_reda(redovi[6]), ["06.11.2026", "0", "0", "0", "—"])

    def test_anoniman_i_bez_dozvole_na_prijavu(self):
        bez_dozvole = Client()
        bez_dozvole.force_login(napravi_korisnika_bez_dozvole("BezDozvole"))
        upisi_zavrsenu(DAN, 72)
        for klijent in (Client(), bez_dozvole):
            odgovor = klijent.get(reverse("moderator_statistika"))
            self.assertNaPrijavu(odgovor)
            self.assertNotIn(b"statistika-tabela", odgovor.content)

    def test_samo_get_i_bez_kesa(self):
        klijent = self.klijent_za(self.mod)
        self.assertEqual(klijent.post(reverse("moderator_statistika")).status_code, 405)
        odgovor = klijent.get(reverse("moderator_statistika"))
        self.assertIn("no-cache", odgovor["Cache-Control"])
        self.assertIn("private", odgovor["Cache-Control"])

    def test_obavezna_promena_lozinke_pre_strane(self):
        klijent = self.klijent_za(napravi_moderatora("Novajlija", mora_promeniti=True))
        odgovor = klijent.get(reverse("moderator_statistika"))
        self.assertEqual(odgovor.status_code, 302)
        self.assertEqual(odgovor["Location"], reverse("moderator_lozinka"))

    def test_veza_u_meniju(self):
        klijent = self.klijent_za(self.mod)
        adresa = reverse("moderator_statistika")
        self.assertIn(f'href="{adresa}"', klijent.get(reverse("moderator_dnevnik")).content.decode("utf-8"))
        html = klijent.get(adresa).content.decode("utf-8")
        self.assertRegex(html, rf'href="{re.escape(adresa)}" aria-current="page"')

    def test_strana_na_oba_jezika(self):
        upisi_zavrsenu(DAN, 72)
        upisi_zavrsenu(DAN, 73)
        for jezik, naslov, prosek in (("sr", "Одигране партије по дану", "72,5"),
                                      ("en", "Games played per day", "72.5")):
            with self.subTest(jezik):
                klijent = self.klijent_za(self.mod, klijent=klijent_jezika(jezik))
                html = klijent.get(reverse("moderator_statistika")).content.decode("utf-8")
                self.assertIn(f'<html lang="{jezik}">', html)
                h1 = re.search(r"<h1 [^>]*>(.*?)</h1>", html, re.S).group(1)
                self.assertEqual(re.sub(r"<[^>]+>", "", h1).strip(), naslov)
                self.assertIn(f'<td class="rang-broj">{prosek}</td>', html)
                tekst = vidljiv_tekst(html)
                if jezik == "en":
                    self.assertEqual(set(CIRILICA.findall(tekst)) - {"Српски"}, set(), tekst)
                    self.assertIn("Average", tekst)
                    self.assertIn("the average is the mean score", tekst)
                else:
                    self.assertEqual(set(re.findall(r"[A-Za-z]{2,}", tekst)) - {"Mod", "English"}, set(), tekst)


def tekst_strane(odgovor):
    """Vidljiv tekst HTML-a: bez oznaka i sa raspakovanim entitetima, jedan razmak izmedju reci."""
    html = odgovor.content.decode("utf-8")
    html = re.sub(r"<form id=\"jezik-forma\".*?</form>", " ", html, flags=re.S)  # dugme drugog jezika nosi njegov naziv
    bez_oznaka = re.sub(r"<[^>]+>", " ", html)
    # Samo ASCII beline: \s bi pojeo i nerazdvojni razmak, koji je deo formata iznosa.
    return re.sub(r"[ \t\r\n]+", " ", html_modul.unescape(bez_oznaka))


def skriveno_na_strani(tekst, napomena):
    """Sve sto strana pravila ne sme da kaze (pravilo 1 projekat-domen); prazna lista je cista strana."""
    nalazi = []
    tekst = tekst.replace(napomena, "")  # trajna napomena sme da kaze "verovatnoce"
    for rec in (r"шанс", r"chance", r"success rate", r"probabilit", r"вероватно", r"\bseme\b", r"\bseed\b"):
        if re.search(rec, tekst, re.I):
            nalazi.append(rec)
    # Jedini procenat na strani je korak kazne za budzet; procenat uspeha bi bio drugi broj.
    dozvoljeno = {str(p.KAZNE[p.PRAVILA_TEKUCA]["budzet_korak_procenata"])}
    for broj in re.findall(r"(\d+)[\s ]?%", tekst):
        if broj not in dozvoljeno:
            nalazi.append(f"procenat {broj}")
    # Spisak tihih zadataka: ime bilo kog tihog zadatka na bilo kom jeziku.
    for jezik in JEZICI:
        with translation.override(jezik):
            for zadatak in p.ZADACI:
                if zadatak["tih"] and gettext(zadatak["naziv"]) in tekst:
                    nalazi.append(f"tih zadatak {zadatak['kljuc']}")
    return nalazi


class KakoSeIgraTests(OsnovaPrikaza):
    """Strana "Kako se igra" (zahtev klijenta 2026-11-12): samo citanje, bez skrivenih podataka."""

    def uzmi(self, jezik="sr", klijent=None):
        klijent = klijent or klijent_jezika(jezik)
        return klijent.get(reverse("kako_se_igra"))

    def test_ruta(self):
        self.assertEqual(reverse("kako_se_igra"), "/kako-se-igra/")

    def test_200_na_oba_jezika(self):
        for jezik in JEZICI:
            with self.subTest(jezik=jezik):
                odgovor = self.uzmi(jezik)
                self.assertEqual(odgovor.status_code, 200)
                self.assertEqual(odgovor["Content-Language"], jezik)
                self.assertContains(odgovor, f'<html lang="{jezik}">')
                self.assertIn("no-cache", odgovor["Cache-Control"])

    def test_engleska_strana_bez_cirilice(self):
        # Ime zadatka i opisi opcija dolaze iz kataloga: cirilica na engleskoj strani znaci propusten prevod.
        tekst = tekst_strane(self.uzmi("en"))
        self.assertEqual(CIRILICA.findall(tekst), [])
        self.assertIn("How to play", tekst)

    def test_srpska_strana_bez_neprevedenih_mesta(self):
        tekst = tekst_strane(self.uzmi("sr"))
        self.assertNotIn("%(", tekst)
        self.assertNotIn("{{", tekst)

    def test_link_sa_pocetne_i_dnevne_na_oba_jezika(self):
        for jezik, natpis in (("sr", "Како се игра"), ("en", "How to play")):
            for adresa in ("/", "/dnevni/"):
                with self.subTest(jezik=jezik, adresa=adresa):
                    odgovor = klijent_jezika(jezik).get(adresa)
                    self.assertContains(
                        odgovor,
                        f'<a id="kako-link" class="btn jezik-dugme dugme-sporedno kako-veza" href="/kako-se-igra/">{natpis}</a>',
                    )

    def test_link_nazad_na_igru(self):
        self.assertContains(self.uzmi(), 'id="nazad-na-igru" class="btn dugme dugme-glavno" href="/"')

    def test_bez_sesije_i_bez_partije(self):
        pre = Session.objects.count()
        for jezik in JEZICI:
            klijent = klijent_jezika(jezik)
            odgovor = self.uzmi(klijent=klijent)
            self.assertEqual(odgovor.status_code, 200)
            self.assertNotIn(settings.SESSION_COOKIE_NAME, odgovor.cookies)
            self.assertNotIn(settings.SESSION_COOKIE_NAME, klijent.cookies)
        self.assertEqual(Session.objects.count(), pre)

    def test_postojeca_sesija_netaknuta(self):
        self.postavi_igru("seme-kako")
        kljuc = self.client.session.session_key
        pre = Session.objects.get(session_key=kljuc)
        odgovor = self.client.get(reverse("kako_se_igra"))
        self.assertEqual(odgovor.status_code, 200)
        posle = Session.objects.get(session_key=kljuc)
        self.assertEqual((posle.session_data, posle.expire_date), (pre.session_data, pre.expire_date))
        self.assertEqual(self.stanje(), motor.nova_igra("seme-kako"))

    def test_bez_citanja_sesije(self):
        with CaptureQueriesContext(connection) as upiti:
            self.uzmi()
        self.assertEqual([u["sql"] for u in upiti.captured_queries if "django_session" in u["sql"]], [])

    def test_post_405(self):
        for metoda in ("post", "put", "delete", "patch"):
            with self.subTest(metoda=metoda):
                odgovor = getattr(Client(), metoda)(reverse("kako_se_igra"))
                self.assertEqual(odgovor.status_code, 405)

    def test_promena_jezika_vodi_nazad_na_stranu(self):
        klijent = Client()
        pre = Session.objects.count()
        odgovor = klijent.post(reverse("jezik"), {"language": "en", "next": reverse("kako_se_igra")}, follow=True)
        self.assertEqual(odgovor.redirect_chain[-1][0], "/kako-se-igra/")
        self.assertEqual(odgovor["Content-Language"], "en")
        self.assertContains(odgovor, "How to play")
        self.assertEqual(Session.objects.count(), pre)
        self.assertContains(odgovor, 'name="next" value="/kako-se-igra/"')

    def test_pravila_iz_parametara(self):
        kazne = p.KAZNE[p.PRAVILA_TEKUCA]
        for jezik in JEZICI:
            with self.subTest(jezik=jezik):
                with translation.override(jezik):
                    ocekivano = [
                        tekstovi.novac(p.BUDZET, 0),
                        tekstovi.minuti(p.ROK, 0),
                        str(p.KRUGOVA),
                        str(kazne["dorada"]),
                        str(kazne["tiha"]),
                        str(kazne["budzet_po_koraku"]),
                        tekstovi.procenat(kazne["budzet_korak_procenata"]),
                        str(kazne["budzet_maks"]),
                        str(kazne["rok"]),
                        str(p.POCETNI_POENI),
                        gettext(p.NAPOMENA),
                    ]
                    for prag, kljuc in p.OCENE:
                        ocekivano += [str(prag), tekstovi.ocena(kljuc)]
                    for lista in tekstovi.opcije(motor.javne_opcije()).values():
                        for o in lista:
                            ocekivano += [o["naziv"], o["opis"]]
                tekst = tekst_strane(self.uzmi(jezik))
                for deo in ocekivano:
                    self.assertIn(deo, tekst)

    def test_mnozina_uz_imenicu(self):
        # Broj uz imenicu ide kroz ngettext: srpski "8 кругова", engleski "100 points".
        self.assertIn(f"{p.KRUGOVA} кругова", tekst_strane(self.uzmi("sr")))
        en = tekst_strane(self.uzmi("en"))
        self.assertIn(f"{p.POCETNI_POENI} points", en)
        self.assertIn(f"lose {p.KAZNE[p.PRAVILA_TEKUCA]['dorada']} points", en)

    def ishod_prvog_kruga(self, trazeni):
        for i in itertools.count(1):
            stanje = motor.odigraj_potez(motor.nova_igra(f"kako-{i}"), views.PRIMER_KRUG, views.PRIMER_IZBORI)
            if stanje["istorija"][0]["ishod"] == trazeni:
                return stanje["istorija"][0]

    def test_primer_jednak_racunu_motora(self):
        # Brojevi primera su isti kao u stvarno odigranom prvom krugu sa istim izborom: prolaz i dorada.
        self.assertEqual(views.PRIMER_IZBORI, {"model": "sonnet", "nivo": "high", "kontekst": "taman", "podela": "sam"})
        prolaz = self.ishod_prvog_kruga(motor.USPEH)
        dorada = self.ishod_prvog_kruga(motor.DORADA)
        self.assertEqual(dorada["cena"], prolaz["cena"] * p.MNOZILAC_DORADE)
        for jezik in JEZICI:
            with self.subTest(jezik=jezik):
                with translation.override(jezik):
                    ocekivano = [
                        tekstovi.novac(round(prolaz["cena"], 3), 3),
                        tekstovi.minuti(round(prolaz["minuti"], 1), 1),
                        tekstovi.novac(round(dorada["cena"], 3), 3),
                        tekstovi.minuti(round(dorada["minuti"], 1), 1),
                        gettext(p.NAZIVI_STATUSA[p.STATUS_GOTOVO]),
                        gettext(p.NAZIVI_STATUSA[p.STATUS_DORADA]),
                        gettext(p.ZADACI[0]["naziv"]),
                    ]
                tekst = tekst_strane(self.uzmi(jezik))
                for deo in ocekivano:
                    self.assertIn(deo, tekst)
        # Konkretne vrednosti (Sonnet high, kontekst taman, sam, zadatak tezine 1): 0,36 $ i 4 min; dorada duplo.
        sr = tekst_strane(self.uzmi("sr"))
        for deo in ("0,360 $", "0,720 $", "4,0 мин", "8,0 мин"):
            self.assertIn(deo, sr)

    def test_nema_skrivenih_podataka(self):
        for jezik in JEZICI:
            with self.subTest(jezik=jezik):
                with translation.override(jezik):
                    napomena = gettext(p.NAPOMENA)
                odgovor = self.uzmi(jezik)
                self.assertEqual(skriveno_na_strani(tekst_strane(odgovor), napomena), [])
                html = odgovor.content.decode("utf-8")
                # Nema ni JSON-a stanja, ni skripte, ni podataka o zadacima u atributima.
                for trag in ("stanje-igre", "<script", "data-tih", "tezina"):
                    self.assertNotIn(trag, html)

    def test_provera_skrivenog_hvata_curenje(self):
        # Tvrdnju dokazuje njen pad: iste provere nad stranom sa umetnutim curenjem moraju nesto da nadju.
        napomena = gettext(p.NAPOMENA)
        tihi = next(z for z in p.ZADACI if z["tih"])
        with translation.override("sr"):
            ime_tihog = gettext(tihi["naziv"])
        procurelo = tekst_strane(self.uzmi("sr")) + f" Шанса за успех има 85%. {ime_tihog}."
        nalazi = skriveno_na_strani(procurelo, napomena)
        self.assertIn("procenat 85", nalazi)
        self.assertIn(f"tih zadatak {tihi['kljuc']}", nalazi)
        self.assertTrue(any("шанс" in n for n in nalazi))

    def test_napomena_na_strani(self):
        for jezik in JEZICI:
            with self.subTest(jezik=jezik):
                with translation.override(jezik):
                    napomena = gettext(p.NAPOMENA)
                self.assertIn(napomena, tekst_strane(self.uzmi(jezik)))


class IstorijaPartijaTests(OsnovaDnevnog):
    """Istorija pregledaca: poslednjih 10 zavrsenih partija u sesiji (request.session["istorija"]), bez modela."""

    KLJUCEVI_OBICNE = {"vrsta", "kraj", "poeni", "ocena", "cena", "minuti"}

    def zavrsi_obicnu(self, seme, klijent=None, strategija=sve_opus):
        klijent = klijent or self.client
        self.postavi_igru(seme, klijent)
        self.odigraj_do(8, strategija, klijent)
        return klijent

    def istorija(self, klijent=None):
        return (klijent or self.client).session.get("istorija")

    def odeljak(self, odgovor):
        html = odgovor.content.decode()
        pocetak = html.index('id="istorija"')
        return html[pocetak:html.index("</section>", pocetak)]

    def test_zavrsena_partija_upisuje_tacno_jednu_stavku(self):
        self.zavrsi_obicnu("istorija-1")
        stavke = self.istorija()
        self.assertEqual(len(stavke), 1)
        stavka = stavke[0]
        self.assertEqual(set(stavka), self.KLJUCEVI_OBICNE)
        zavrsni = motor.javni_prikaz(self.stanje())["zavrsni"]
        self.assertEqual(stavka["vrsta"], "obicna")
        self.assertEqual(stavka["poeni"], zavrsni["poeni"])
        self.assertEqual(stavka["ocena"], zavrsni["ocena"])
        self.assertIn(stavka["ocena"], p.NAZIVI_OCENA)  # kljuc, ne tekst
        self.assertEqual(stavka["cena"], zavrsni["ukupna_cena"])
        self.assertEqual(stavka["minuti"], zavrsni["ukupni_minuti"])
        self.assertTrue(stavka["kraj"].endswith("+00:00"))  # ISO, UTC

    def test_nezavrsena_partija_nista_ne_upisuje(self):
        self.postavi_igru("istorija-2")
        self.odigraj_do(7)
        self.assertIsNone(self.istorija())

    def test_zavrsen_potez_ne_moze_ponoviti_pa_nema_druge_stavke(self):
        self.zavrsi_obicnu("istorija-3")
        ponovo = self.potez(8)
        self.assertEqual(ponovo.status_code, 409)
        self.assertEqual(len(self.istorija()), 1)

    def test_jedanaesta_partija_izbacuje_najstariju(self):
        prvi_kraj = None
        for broj in range(11):
            self.zavrsi_obicnu(f"istorija-niz-{broj}")
            if broj == 0:
                prvi_kraj = self.istorija()[0]["kraj"]
        stavke = self.istorija()
        self.assertEqual(p.ISTORIJA_MAKS, 10)
        self.assertEqual(len(stavke), 10)
        krajevi = [s["kraj"] for s in stavke]
        self.assertNotIn(prvi_kraj, krajevi)
        self.assertEqual(krajevi, sorted(krajevi, reverse=True))  # najnovija prva
        self.assertEqual(len(set(krajevi)), 10)

    def test_dnevna_se_upisuje_sa_vrstom_i_danom(self):
        klijent = self.zavrsen_igrac()
        stavke = self.istorija(klijent)
        self.assertEqual(len(stavke), 1)
        self.assertEqual(stavke[0]["vrsta"], "dnevna")
        self.assertEqual(stavke[0]["dan"], "2026-11-12")
        self.assertEqual(set(stavke[0]), self.KLJUCEVI_OBICNE | {"dan"})
        self.assertEqual(self.dnevni_potez(8, klijent=klijent).status_code, 409)
        self.assertEqual(len(self.istorija(klijent)), 1)

    def test_obe_vrste_dele_jednu_listu_najnovija_prva(self):
        self.zavrsi_obicnu("istorija-obe")
        self.assertEqual(self.dnevni().status_code, 200)
        self.odigraj_dnevnu(self.client)
        self.assertEqual([s["vrsta"] for s in self.istorija()], ["dnevna", "obicna"])

    def test_stavka_i_strana_nemaju_skriveno(self):
        seme = "istorija-skriveno-1234"
        stanje = self.zavrsi_obicnu(seme).session["igra"]
        stavka = self.istorija()[0]
        # Kontrola dokaza: seme stvarno postoji u stanju sesije, pa bi ga provera tamo nasla.
        self.assertIn(seme, json.dumps(stanje))
        for kljuc in stavka:
            for rec in ("seme", "oznaka", "partija", "hes", "sansa", "tiha"):
                self.assertNotIn(rec, kljuc)
        tajne = (seme, motor.oznaka_partije(stanje))
        for tajna in tajne:
            self.assertNotIn(tajna, json.dumps(stavka))
        for adresa in (reverse("pocetna"), reverse("dnevni")):
            odeljak = self.odeljak(self.client.get(adresa))
            self.assertIn('id="istorija-tabela"', odeljak)
            for tajna in tajne:
                self.assertNotIn(tajna, odeljak)
            self.assertNotIn("sansa", odeljak.lower())

    def test_stavka_dnevne_nema_oznaku_ni_seme(self):
        klijent = self.zavrsen_igrac()
        stanje = self.dnevno_stanje(klijent)
        sirova = json.dumps(self.istorija(klijent))
        # Kontrola dokaza: oznaka i seme su u stanju dnevne partije.
        self.assertIn(stanje["oznaka"], json.dumps(stanje))
        self.assertIn(stanje["seme"], json.dumps(stanje))
        for tajna in (stanje["oznaka"], stanje["seme"], motor.oznaka_partije(stanje)):
            self.assertNotIn(tajna, sirova)

    def test_odeljak_se_vidi_na_obe_strane_sa_redovima(self):
        self.zavrsi_obicnu("istorija-strane")
        zavrsni = motor.javni_prikaz(self.stanje())["zavrsni"]
        self.assertEqual(self.dnevni().status_code, 200)
        self.odigraj_dnevnu(self.client)
        for adresa in (reverse("pocetna"), reverse("dnevni")):
            odgovor = self.client.get(adresa)
            self.assertContains(odgovor, "Моје партије")
            odeljak = self.odeljak(odgovor)
            self.assertEqual(odeljak.count("<tr>"), 3)  # zaglavlje i dve partije
            self.assertIn(tekstovi.datum(timezone.now()), odeljak)
            self.assertIn("Обична игра", odeljak)
            self.assertIn("Дневни изазов", odeljak)
            self.assertIn(tekstovi.ocena(zavrsni["ocena"]), odeljak)
            self.assertIn(tekstovi.novac(zavrsni["ukupna_cena"]), odeljak)
            self.assertIn(tekstovi.minuti(zavrsni["ukupni_minuti"]), odeljak)
            self.assertIn("само у овом прегледачу", odeljak)
            self.assertIn("14 дана", odeljak)

    def test_prazno_stanje(self):
        for adresa in (reverse("pocetna"), reverse("dnevni")):
            odgovor = self.client.get(adresa)
            self.assertContains(odgovor, "Моје партије")
            odeljak = self.odeljak(odgovor)
            self.assertIn('id="istorija-prazno"', odeljak)
            self.assertIn("Још нема завршених партија у овом прегледачу.", odeljak)
            self.assertNotIn("<table", odeljak)
            self.assertIn("само у овом прегледачу", odeljak)

    def test_engleski_prevod_i_format(self):
        self.zavrsi_obicnu("istorija-en")
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
        odeljak = self.odeljak(self.client.get(reverse("pocetna")))
        self.assertIn("My games", odeljak)
        self.assertIn("Regular game", odeljak)
        self.assertIn("only in this browser", odeljak)
        self.assertIn(timezone.localdate().isoformat(), odeljak)  # datum Y-m-d na engleskom
        self.assertIn("$", odeljak)

    def test_pokvarena_istorija_ne_rusi_stranu(self):
        for pokvareno in ("x", {"a": 1}, [None, 5, {"vrsta": "obicna"}, {"vrsta": "obicna", "kraj": "nije"}]):
            sesija = self.client.session
            sesija["istorija"] = pokvareno
            sesija.save()
            odgovor = self.client.get(reverse("pocetna"))
            self.assertEqual(odgovor.status_code, 200)
            self.assertIn('id="istorija-prazno"', self.odeljak(odgovor))

    def test_pokvarena_istorija_ne_rusi_potez(self):
        sesija = self.client.session
        sesija["istorija"] = "x"
        sesija.save()
        self.zavrsi_obicnu("istorija-pokvarena")
        self.assertEqual(len(self.istorija()), 1)

    def test_prijava_i_odjava_moderatora_cuvaju_istoriju(self):
        napravi_moderatora("istorija-mod")
        self.zavrsi_obicnu("istorija-moderator")
        pre = self.istorija()
        self.assertEqual(len(pre), 1)
        obrisi_brojace()
        self.addCleanup(obrisi_brojace)
        odgovor = self.client.post(
            reverse("moderator_prijava"), {"username": "istorija-mod", "password": LOZINKA}
        )
        self.assertEqual(odgovor.status_code, 302)
        self.assertIn(SESSION_KEY, self.client.session)
        self.assertEqual(self.istorija(), pre)
        odjava = self.client.post(reverse("moderator_odjava"))
        self.assertEqual(odjava.status_code, 302)
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.assertEqual(self.istorija(), pre)
        self.assertContains(self.client.get(reverse("pocetna")), 'id="istorija-tabela"')


class ZvukPrikazTests(OsnovaPrikaza):
    """Prekidac zvuka ishoda kruga: u zaglavlju igre i dnevne strane, ne na deljenoj; tekst na oba jezika."""

    NATPISI = {"sr": ("Звук: укључен", "Звук: искључен"), "en": ("Sound: on", "Sound: off")}
    PREKIDAC = re.compile(r'<button type="button" id="zvuk-dugme"[^>]*>([^<]*)</button>')

    def test_prekidac_na_pocetnoj_i_dnevnoj_ne_na_deljenoj(self):
        for jezik in JEZICI:
            for ime in ("pocetna", "dnevni"):
                with self.subTest(jezik=jezik, strana=ime):
                    odgovor = klijent_jezika(jezik).get(reverse(ime))
                    self.assertEqual(odgovor.status_code, 200)
                    pogodak = self.PREKIDAC.search(odgovor.content.decode("utf-8"))
                    self.assertIsNotNone(pogodak, "nema prekidaca zvuka")
                    self.assertIn('aria-pressed="false"', pogodak.group(0))
                    # Podrazumevano iskljuceno; skripta ga otkriva tek kad postoji Web Audio.
                    self.assertIn(" hidden", pogodak.group(0))
                    self.assertEqual(pogodak.group(1), self.NATPISI[jezik][1])
            with self.subTest(jezik=jezik, strana="deljeno"):
                red = upisi_deljeno()
                odgovor = klijent_jezika(jezik).get(reverse("deljeno", args=[red.token]))
                self.assertEqual(odgovor.status_code, 200)
                self.assertNotIn("zvuk-dugme", odgovor.content.decode("utf-8"))

    def test_tekstovi_nose_natpise_zvuka_na_oba_jezika(self):
        for jezik in JEZICI:
            with self.subTest(jezik=jezik):
                odgovor = klijent_jezika(jezik).get(reverse("pocetna"))
                zvuk = tekstovi_iz_html(odgovor)["zvuk"]
                self.assertEqual(zvuk, {"ukljucen": self.NATPISI[jezik][0], "iskljucen": self.NATPISI[jezik][1]})


# ---------- Spojevi zahteva 2026-11-12 (kontrolni skup nad celinom): istorija + statistika + javna lista ----------


class SpojeviZahtevaTests(OsnovaDnevnog, OsnovaModeratora):
    """Veze izmedju pet delova koje su radjene odvojeno: potez upisuje istoriju i statistiku zajedno;
    rang lista (sacuvaj, moderator, api) ne dira ni jedno ni drugo."""

    def setUp(self):
        super().setUp()
        self.mod = napravi_moderatora("Spoj")
        self.moderator = self.klijent_za(self.mod)

    def oba(self, klijent=None):
        istorija = (klijent or self.client).session.get("istorija") or []
        statistika = list(ZavrsenaPartija.objects.order_by("id").values_list("dan", "vrsta", "poeni"))
        return [(s["vrsta"], s["poeni"]) for s in istorija], statistika

    def api(self):
        odgovor = Client().get(reverse("javna_rang_lista"))
        self.assertEqual(odgovor.status_code, 200)
        return json.loads(odgovor.content)

    def statistika_danas(self):
        odgovor = self.moderator.get(reverse("moderator_statistika"))
        self.assertEqual(odgovor.status_code, 200)
        return odgovor.context["dani"][0]

    def test_zavrsen_potez_obicne_upisuje_oba_sa_istim_poenima(self):
        self.postavi_igru("spoj-obicna")
        self.odigraj_do(7)
        self.assertEqual(self.oba(), ([], []))
        self.assertEqual(self.potez(8, sve_opus(8)).status_code, 200)
        poeni = self.stanje()["rezultat"]["poeni"]
        self.assertEqual(self.oba(), ([("obicna", poeni)], [(DAN, "obicna", poeni)]))

    def test_zavrsen_potez_dnevne_upisuje_oba_sa_istim_poenima(self):
        klijent = self.novi_igrac()
        self.odigraj_dnevnu(klijent, do=7)
        self.assertEqual(self.oba(klijent), ([], []))
        self.assertEqual(self.dnevni_potez(8, po_tezini(8), klijent).status_code, 200)
        poeni = self.dnevno_stanje(klijent)["rezultat"]["poeni"]
        self.assertEqual(self.oba(klijent), ([("dnevna", poeni)], [(DAN, "dnevna", poeni)]))

    def test_odbijen_potez_ne_upisuje_ni_jedno(self):
        # Obicna: zavrsena partija, pa 409 (igra_zavrsena), 409 (pogresan krug) i 400 (nepoznat izbor).
        self.postavi_igru("spoj-odbijen")
        self.odigraj_do(8)
        pre = self.oba()
        self.assertEqual(len(pre[0]), 1)
        self.assertEqual(len(pre[1]), 1)
        self.assertEqual(self.potez(8).status_code, 409)
        self.assertEqual(self.potez(9).status_code, 409)
        self.assertEqual(self.sirovo(json.dumps({"krug": 8, "izbori": {"model": "x"}})).status_code, 400)
        self.assertEqual(self.oba(), pre)
        # Dnevna: zavrsena, pa ponovljen osmi krug.
        klijent = self.zavrsen_igrac()
        pre_dnevne = self.oba(klijent)
        self.assertEqual(len(pre_dnevne[1]), 2)
        self.assertEqual(self.dnevni_potez(8, po_tezini(8), klijent).status_code, 409)
        self.assertEqual(self.oba(klijent), pre_dnevne)

    def test_pad_upisa_statistike_ponistava_i_istoriju_i_potez(self):
        # Oba upisa su u istoj transakciji sa potezom: pad jednog ne sme da ostavi drugi.
        self.postavi_igru("spoj-pad")
        self.odigraj_do(7)
        with mock.patch.object(views.ZavrsenaPartija, "save", side_effect=IntegrityError("pad")):
            with self.assertRaises(IntegrityError):
                self.potez(8, sve_opus(8))
        self.assertEqual(self.oba(), ([], []))
        stanje = self.stanje()
        self.assertFalse(stanje["zavrsena"])
        self.assertEqual(len(stanje["istorija"]), 7)
        # Ponovljen potez posle pada prolazi i upisuje oba tacno jednom.
        self.assertEqual(self.potez(8, sve_opus(8)).status_code, 200)
        self.assertEqual(len(self.oba()[0]), 1)
        self.assertEqual(len(self.oba()[1]), 1)

    def test_sacuvana_obicna_u_api_brisanje_moderatora_ne_dira_istoriju_ni_statistiku(self):
        self.postavi_igru("spoj-api-obicna")
        self.odigraj_do(8)
        poeni = self.stanje()["rezultat"]["poeni"]
        self.assertEqual(self.sacuvaj("SpojObican").status_code, 200)
        glavna = self.api()["glavna"]
        self.assertEqual([(r["ime"], r["poeni"]) for r in glavna], [("SpojObican", poeni)])
        pre = self.oba()
        self.assertEqual(len(pre[0]), 1)
        self.assertEqual((self.statistika_danas()["ukupno"], self.statistika_danas()["obicnih"]), (1, 1))
        red = Rezultat.objects.get(ime="SpojObican")
        odgovor = self.moderator.post(reverse("moderator_rezultat", args=[red.id]))
        self.assertEqual(odgovor.status_code, 302)
        self.assertFalse(Rezultat.objects.filter(pk=red.id).exists())
        self.assertEqual(self.api()["glavna"], [])
        self.assertEqual(self.oba(), pre)
        self.assertEqual((self.statistika_danas()["ukupno"], self.statistika_danas()["obicnih"]), (1, 1))
        # Odeljak "Моје партије" na strani i dalje ima partiju.
        html = self.client.get(reverse("pocetna")).content.decode("utf-8")
        odeljak = html[html.index('id="istorija"'):]
        self.assertIn('id="istorija-tabela"', odeljak[: odeljak.index("</section>")])

    def test_sacuvana_dnevna_u_api_danas_brisanje_ne_dira_istoriju_ni_statistiku(self):
        klijent = self.zavrsen_igrac()
        poeni = self.dnevno_stanje(klijent)["rezultat"]["poeni"]
        self.assertEqual(self.dnevni_sacuvaj("SpojDnevni", klijent).status_code, 200)
        telo = self.api()
        self.assertEqual(telo["glavna"], [])
        self.assertEqual([(r["ime"], r["poeni"]) for r in telo["danas"]["redovi"]], [("SpojDnevni", poeni)])
        pre = self.oba(klijent)
        self.assertEqual(pre[0], [("dnevna", poeni)])
        self.assertEqual(self.statistika_danas()["dnevnih"], 1)
        red = Rezultat.objects.get(ime="SpojDnevni")
        self.assertEqual(self.moderator.post(reverse("moderator_rezultat", args=[red.id])).status_code, 302)
        self.assertEqual(self.api()["danas"]["redovi"], [])
        self.assertEqual(self.oba(klijent), pre)
        self.assertEqual(self.statistika_danas()["dnevnih"], 1)
