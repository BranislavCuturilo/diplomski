"""Priprema za javni server: zaglavlja, stranice gresaka, odrzavanje, kopija baze i produkciona podesavanja."""

import json
import os
import secrets
import sqlite3
import subprocess
import sys
import tempfile
from datetime import timedelta
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.contrib.sessions.models import Session
from django.core.cache import caches
from django.core.management import call_command
from django.db import connection
from django.template.loader import render_to_string
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import include, path
from django.utils import timezone

from igra import moderacija
from igra import parametri as p
from igra.management.commands.odrzavanje import obrisi_napustene
from igra.models import Partija, Potez, Rezultat

from .test_http import posalji, telo, zapocni

SEME = "SEME-NE-SME-NAPOLJE"


def pad(request):
    raise RuntimeError(f"pad sa semenom {SEME}")


urlpatterns = [path("pad/", pad), path("", include("igra.urls"))]


class ZaglavljaTest(TestCase):
    def test_csp_na_svim_stranicama(self):
        partija = zapocni(self.client)
        for adresa in ("/", "/moderator/prijava/", "/nepostoji/"):
            csp = self.client.get(adresa).headers["Content-Security-Policy"]
            self.assertIn("script-src 'self'", csp)
            self.assertIn("frame-ancestors 'none'", csp)
            self.assertIn("default-src 'self'", csp)
            self.assertNotIn("unsafe-eval", csp)
        self.assertIsNotNone(partija)

    def test_ne_moze_u_okvir(self):
        self.assertEqual(self.client.get("/").headers["X-Frame-Options"], "DENY")

    def test_nema_ugradjenih_skripti(self):
        # CSP dozvoljava samo skripte sa sajta, pa ugradjena skripta ne bi radila.
        zapocni(self.client)
        for odgovor in (self.client.get("/"), Client().get("/"), self.client.get("/moderator/prijava/")):
            html = odgovor.content.decode()
            self.assertEqual(html.count("<script"), html.count("<script src="), odgovor.request["PATH_INFO"])
            self.assertNotIn(" onclick=", html)


class StraniceGresakaTest(TestCase):
    def test_404_je_stranica_igre(self):
        odgovor = self.client.get("/partija/nepostoji/")
        self.assertEqual(odgovor.status_code, 404)
        self.assertContains(odgovor, 'id="greska-stranice"', status_code=404)
        self.assertContains(odgovor, "Страница не постоји", status_code=404)

    def test_404_na_engleskom(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
        self.assertContains(self.client.get("/nepostoji/"), "Page not found", status_code=404)

    @override_settings(ROOT_URLCONF=__name__)
    def test_500_bez_tehnickih_detalja(self):
        klijent = Client(raise_request_exception=False)
        with self.assertLogs("django.request", "ERROR"):
            odgovor = klijent.get("/pad/")
        self.assertEqual(odgovor.status_code, 500)
        html = odgovor.content.decode()
        self.assertIn("Нешто није у реду", html)
        self.assertNotIn(SEME, html)
        self.assertNotIn("Traceback", html)
        self.assertNotIn("RuntimeError", html)

    def test_500_se_prikazuje_i_bez_zahteva(self):
        # Django sablon 500 prikazuje bez zahteva i bez dodataka konteksta.
        self.assertIn("Нешто није у реду", render_to_string("500.html"))


def napravi_partiju(pre_dana, potezi):
    partija = Partija.objects.create(seme="s")
    Partija.objects.filter(pk=partija.pk).update(napravljena=timezone.now() - timedelta(days=pre_dana))
    for krug in range(1, potezi + 1):
        Potez.objects.create(partija=partija, krug=krug, model="opus", nivo="high", kontekst="taman", podela="sam")
    return partija


class OdrzavanjeTest(TestCase):
    def test_brise_samo_napustene_partije(self):
        napustena = napravi_partiju(30, 3)
        prazna = napravi_partiju(30, 0)
        skorasnja = napravi_partiju(2, 3)
        zavrsena = napravi_partiju(400, p.BROJ_KRUGOVA)
        sacuvana = napravi_partiju(400, p.BROJ_KRUGOVA)
        Rezultat.objects.create(partija=sacuvana, ime="Ana", poeni=50, ocena="x")

        self.assertEqual(obrisi_napustene(), 2)
        ostale = set(Partija.objects.values_list("pk", flat=True))
        self.assertEqual(ostale, {skorasnja.pk, zavrsena.pk, sacuvana.pk})
        self.assertFalse(Potez.objects.filter(partija_id=napustena.pk).exists())
        self.assertNotIn(prazna.pk, ostale)

    def test_partija_dok_sesija_vazi_ostaje(self):
        # Granica je trajanje sesije uz dan rezerve: igrac jos moze da nastavi.
        dana = settings.SESSION_COOKIE_AGE // 86400
        napravi_partiju(dana, 3)
        self.assertEqual(obrisi_napustene(), 0)

    def test_igrac_nastavlja_nezavrsenu_partiju_posle_odrzavanja(self):
        zapocni(self.client)
        posalji(self.client, telo(1))
        call_command("odrzavanje", stdout=StringIO())
        self.assertEqual(posalji(self.client, telo(2)).status_code, 200)

    def test_komanda_brise_istekle_sesije(self):
        Session.objects.create(session_key="x" * 32, session_data="", expire_date=timezone.now() - timedelta(days=1))
        izlaz = StringIO()
        call_command("odrzavanje", stdout=izlaz)
        self.assertFalse(Session.objects.filter(session_key="x" * 32).exists())
        self.assertIn("Obrisano napustenih partija: 0.", izlaz.getvalue())


class RezervnaKopijaTest(TransactionTestCase):
    def test_kopija_je_ispravna_i_stare_se_brisu(self):
        napravi_partiju(1, 2)
        # Igrac upravo upisuje potez (otvorena transakcija): kopija ne sme da ga ceka.
        upis = connection.cursor()
        upis.execute("BEGIN IMMEDIATE")
        upis.execute("UPDATE igra_partija SET seme = 'u-toku'")
        self.addCleanup(lambda: (upis.execute("ROLLBACK"), upis.close()))
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            for stara in ("20200101-000000", "20200102-000000", "20200103-000000"):
                (folder / f"orkestrator-{stara}.sqlite3").write_bytes(b"")
            (folder / "druga-datoteka.txt").write_text("ostaje")

            call_command("rezervna_kopija", str(folder), "--zadrzi", "2", stdout=StringIO())

            kopije = sorted(f.name for f in folder.glob("orkestrator-*.sqlite3"))
            self.assertEqual(len(kopije), 2)
            self.assertEqual(kopije[0], "orkestrator-20200103-000000.sqlite3")
            self.assertTrue((folder / "druga-datoteka.txt").exists())
            self.assertFalse(list(folder.glob("*.delimicno")))
            veza = sqlite3.connect(folder / kopije[1])
            try:
                # Kopija ima potvrdjeno stanje, bez nedovrsenog upisa.
                self.assertEqual(veza.execute("SELECT seme FROM igra_partija").fetchall(), [("s",)])
            finally:
                veza.close()

    def test_zadrzi_mora_biti_pozitivno(self):
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            call_command("rezervna_kopija", tempfile.gettempdir(), "--zadrzi", "0")


BAZNI_KES = {"default": {"BACKEND": "django.core.cache.backends.db.DatabaseCache", "LOCATION": "kes_test"}}


@override_settings(CACHES=BAZNI_KES)
class DeljeniKesTest(TestCase):
    """Na serveru promasene prijave broji kes u bazi, zajednicki za sve gunicorn procese."""

    @classmethod
    def setUpTestData(cls):
        call_command("createcachetable", verbosity=0)

    def test_zakljucavanje_prijave_kroz_kes_u_bazi(self):
        for _ in range(moderacija.PRIJAVA_POKUSAJA):
            self.assertFalse(moderacija.prijava_zakljucana("Mika"))
            moderacija.zabelezi_promasaj("Mika")
        self.assertTrue(moderacija.prijava_zakljucana("mika"))
        with connection.cursor() as kursor:
            kursor.execute("SELECT count(*) FROM kes_test")
            self.assertEqual(kursor.fetchone()[0], 1)
        # Novi objekat kesa (kao drugi proces) vidi isti broj.
        self.assertTrue(caches.create_connection("default").get("prijava:mika") >= moderacija.PRIJAVA_POKUSAJA)


# Produkciona podesavanja se proveravaju u posebnom procesu, sa sopstvenom bazom.
KOREN = Path(settings.BASE_DIR)
DOBAR_KLJUC = secrets.token_urlsafe(64)

PROVERA = r"""
import json, re
import django
django.setup()
from django.core.management import call_command
from django.test import Client
call_command("migrate", verbosity=0)
call_command("createcachetable", verbosity=0)
call_command("collectstatic", interactive=False, verbosity=0)

HTTPS = {"HTTP_X_FORWARDED_PROTO": "https"}
k = Client(HTTP_HOST="orkestrator.example")
r = {}
o = k.get("/")
r["http"] = [o.status_code, o.headers.get("Location")]
r["los_host"] = Client(HTTP_HOST="napadac.example").get("/", **HTTPS).status_code
o = k.get("/", **HTTPS)
r["pocetna"] = o.status_code
r["hsts"] = o.headers.get("Strict-Transport-Security")
r["csp"] = "Content-Security-Policy" in o.headers
html = o.content.decode()
r["css"] = re.findall(r'href="(/static/igra/igra\.[0-9a-f]{12}\.css)"', html)
r["csrf_secure"] = bool(o.cookies["csrftoken"]["secure"])
o = k.post("/nova/", **HTTPS)
r["nova"] = o.status_code
r["sesija_secure"] = bool(o.cookies["sessionid"]["secure"])
r["sesija_httponly"] = bool(o.cookies["sessionid"]["httponly"])
r["igrac_secure"] = bool(o.cookies["igrac"]["secure"])
r["igrac_httponly"] = bool(o.cookies["igrac"]["httponly"])
o = k.get("/jezik/en/", **HTTPS)
r["jezik_secure"] = bool(o.cookies["jezik"]["secure"])
r["static_kroz_django"] = k.get("/static/igra/igra.css", **HTTPS).status_code
o = k.get("/nepostoji/", **HTTPS)
r["404"] = [o.status_code, "Page not found" in o.content.decode()]
print("REZULTAT" + json.dumps(r))
"""


class ProdukcijaTest(TestCase):
    def pokreni(self, argumenti, **okruzenje):
        env = {k: v for k, v in os.environ.items() if not k.startswith("ORKESTRATOR_")}
        env.update(DJANGO_SETTINGS_MODULE="orkestrator.settings_produkcija", PYTHONIOENCODING="utf-8", **okruzenje)
        return subprocess.run(
            [sys.executable, *argumenti], cwd=KOREN, env=env, capture_output=True, text=True, encoding="utf-8", timeout=180
        )

    def okruzenje(self, folder):
        return {
            "ORKESTRATOR_SECRET_KEY": DOBAR_KLJUC,
            "ORKESTRATOR_BAZA": str(Path(folder) / "db.sqlite3"),
            "ORKESTRATOR_STATIC": str(Path(folder) / "static"),
        }

    def test_bez_tajnog_kljuca_server_ne_krece(self):
        izlaz = self.pokreni(["manage.py", "check"])
        self.assertNotEqual(izlaz.returncode, 0)
        self.assertIn("ORKESTRATOR_SECRET_KEY", izlaz.stderr)

    def test_kratak_tajni_kljuc_se_odbija(self):
        izlaz = self.pokreni(["manage.py", "check"], ORKESTRATOR_SECRET_KEY="kratak")
        self.assertNotEqual(izlaz.returncode, 0)
        self.assertIn("50", izlaz.stderr)

    def test_provera_za_javni_server_prolazi(self):
        with tempfile.TemporaryDirectory() as folder:
            izlaz = self.pokreni(["manage.py", "check", "--deploy", "--fail-level", "WARNING"], **self.okruzenje(folder))
        self.assertEqual(izlaz.returncode, 0, izlaz.stdout + izlaz.stderr)

    def test_server_preko_https_sa_bezbednim_kolacicima(self):
        with tempfile.TemporaryDirectory() as folder:
            izlaz = self.pokreni(["-c", PROVERA], **self.okruzenje(folder))
        self.assertEqual(izlaz.returncode, 0, izlaz.stdout + izlaz.stderr)
        r = json.loads(izlaz.stdout.split("REZULTAT", 1)[1])
        self.assertEqual(r["http"], [301, "https://orkestrator.example/"])
        self.assertEqual(r["los_host"], 400)
        self.assertEqual(r["pocetna"], 200)
        self.assertEqual(r["hsts"], "max-age=31536000")
        self.assertTrue(r["csp"])
        self.assertEqual(len(r["css"]), 1, "staticke datoteke moraju imati hes u imenu")
        self.assertTrue(r["csrf_secure"])
        self.assertEqual(r["nova"], 302)
        self.assertTrue(r["sesija_secure"])
        self.assertTrue(r["sesija_httponly"])
        self.assertTrue(r["jezik_secure"])
        self.assertTrue(r["igrac_secure"])
        self.assertTrue(r["igrac_httponly"])
        self.assertEqual(r["static_kroz_django"], 404)
        self.assertEqual(r["404"], [404, True])
