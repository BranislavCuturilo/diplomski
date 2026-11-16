import itertools
import re

from django.contrib.staticfiles import finders
from django.test import Client, TestCase

from igra import pravila
from igra.models import Partija

from .pomocno import HIGH_OPUS
from .test_http import posalji, telo, zapocni

ZABRANJENE_RECI = re.compile(
    r"sansa|bonus|tezin|seme|\btih|шанс|бонус|тежин|семе|\bтих|randint", re.IGNORECASE
)
POLJA_ODGOVORA = {
    "krug",
    "status",
    "cena",
    "minuti",
    "budzet_preostalo",
    "rok_preostalo",
    "budzet_prekoracen",
    "rok_prekoracen",
    "sledeci",
    "zavrsena",
}
SEME = "tajnoseme0123456789abcdef"
CSRF_POLJE = re.compile(rb'name="csrfmiddlewaretoken" value="[^"]+"')


def seme_sa_ishodom_petog_kruga(vrsta):
    """Nalazi seme gde prva cetiri kruga uspevaju, a peti ima trazeni ishod."""
    for broj in itertools.count():
        seme = str(broj)
        ishodi = [pravila.odigraj_krug(seme, k, HIGH_OPUS).vrsta for k in range(1, 6)]
        if ishodi[:4] == [pravila.USPEH] * 4 and ishodi[4] == vrsta:
            return seme


class TajneTest(TestCase):
    def proveri_odgovor(self, odgovor):
        sadrzaj = odgovor.content.decode()
        self.assertNotIn(SEME, sadrzaj)
        self.assertIsNone(ZABRANJENE_RECI.search(sadrzaj), ZABRANJENE_RECI.search(sadrzaj))
        for naziv, kolacic in odgovor.cookies.items():
            self.assertIn(naziv, ("sessionid", "csrftoken"))
            self.assertNotIn(SEME, kolacic.value)

    def test_nijedan_odgovor_tokom_igre_nema_tajne(self):
        klijent = Client()
        self.proveri_odgovor(klijent.get("/"))
        self.proveri_odgovor(klijent.post("/nova/"))
        partija = Partija.objects.latest("pk")
        partija.seme = SEME
        partija.save()

        for krug in range(1, 9):
            self.proveri_odgovor(klijent.get("/"))
            self.proveri_odgovor(klijent.get("/kraj/"))
            self.proveri_odgovor(posalji(klijent, {**telo(krug), "model": "x"}))
            self.proveri_odgovor(posalji(klijent, telo(krug + 1)))

            odgovor = posalji(klijent, telo(krug))
            self.assertEqual(odgovor.status_code, 200)
            self.proveri_odgovor(odgovor)
            podaci = odgovor.json()
            self.assertEqual(set(podaci), POLJA_ODGOVORA)
            if podaci["sledeci"] is not None:
                self.assertEqual(set(podaci["sledeci"]), {"krug", "naziv"})

    def test_sesija_cuva_samo_id_partije(self):
        klijent = Client()
        zapocni(klijent, SEME)
        posalji(klijent, telo(1))
        self.assertEqual(set(klijent.session.keys()), {"partija_id"})
        self.assertNotIn(SEME, klijent.cookies["sessionid"].value)

    def test_seme_nije_ni_na_zavrsnom_ekranu(self):
        klijent = Client()
        zapocni(klijent, SEME)
        for krug in range(1, 9):
            posalji(klijent, telo(krug))
        self.assertNotContains(klijent.get("/kraj/"), SEME)

    def test_kontekst_igre_ima_samo_javna_polja(self):
        klijent = Client()
        zapocni(klijent, SEME)
        kontekst = klijent.get("/").context
        for grupa in kontekst["opcije"]:
            self.assertEqual(set(grupa), {"polje", "naslov", "opcije"})
            for opcija in grupa["opcije"]:
                self.assertEqual(set(opcija), {"kljuc", "naziv", "detalji"})

    def test_tihi_neuspeh_se_ne_razlikuje_od_uspeha(self):
        seme_uspeha = seme_sa_ishodom_petog_kruga(pravila.USPEH)
        seme_neuspeha = seme_sa_ishodom_petog_kruga(pravila.TIHI_NEUSPEH)

        def odigraj(seme):
            klijent = Client()
            zapocni(klijent, seme)
            odgovori = [posalji(klijent, telo(k)).content for k in range(1, 6)]
            stranica = CSRF_POLJE.sub(b"", klijent.get("/").content)
            return odgovori, stranica

        self.assertEqual(odigraj(seme_uspeha), odigraj(seme_neuspeha))

    def test_javascript_nema_parametre_igre(self):
        with open(finders.find("igra/igra.js"), encoding="utf-8") as datoteka:
            sadrzaj = datoteka.read()
        self.assertIsNone(ZABRANJENE_RECI.search(sadrzaj))
        self.assertNotIn("0.18", sadrzaj)
        self.assertNotIn("1000000", sadrzaj)
