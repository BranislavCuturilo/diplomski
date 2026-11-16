"""Izmena klijenta: stranica „Kako se igra“ sa pravilima i primerom jednog kruga."""

from decimal import Decimal

from django.test import Client, TestCase

from igra import parametri as p
from igra import pravila
from igra.pravila import Izbori

from .test_http import posalji, telo, zapocni
from .test_jezik import CIRILICA, na_engleskom

URL = "/kako-se-igra/"


class KakoSeIgraTest(TestCase):
    def test_link_sa_pocetnog_ekrana(self):
        self.assertContains(self.client.get("/"), f'id="kako-se-igra" class="btn dugme-sporedno w-100 mt-2" href="{URL}"')

    def test_stranica_ima_pravila(self):
        odgovor = self.client.get(URL)
        self.assertTemplateUsed(odgovor, "igra/kako_se_igra.html")
        for tekst in (
            "Како се игра",
            "8 кругова",
            "24 $",
            "150 мин",
            "0,18 $/M",
            "време ×0,5",
            "токени ×3,6",
            "готово",
            "враћено на дораду",
            "Тиха грешка",
            p.NAPOMENA_O_PARAMETRIMA,
        ):
            self.assertContains(odgovor, tekst)

    def test_kazne_i_ocene_dolaze_iz_parametara(self):
        bodovanje = p.BODOVANJA[p.BODOVANJE_TEKUCE]
        odgovor = self.client.get(URL)
        for tekst in (
            f"Почињеш са {p.POCETNI_POENI} поена",
            f"множе са {p.DORADA_PUTA}, а на крају губиш {p.DORADA_POENI} поена",
            f"×{p.TIHI_DODATAK_CENE_PUTA}",
            f"и губиш {bodovanje.tihi_poeni} поена",
            f"−{bodovanje.kazna_budzet} поена за сваких започетих {bodovanje.korak_budzeta_procenata} процената"
            f" прекорачења (2,40 $), највише −{bodovanje.kazna_budzet_max}",
            f"Прекорачен рок: −{p.KAZNA_ROK} поена.",
        ):
            self.assertContains(odgovor, tekst)
        ocene = [(r["od"], r["do"]) for r in odgovor.context["ocene"]]
        self.assertEqual(ocene, [(85, 100), (65, 84), (40, 64), (0, 39)])
        self.assertContains(odgovor, "<td>85–100</td><td>одличан оркестратор</td>", html=False)

    def test_primer_je_racun_igre(self):
        racun = pravila.racun_za_tezinu(p.PRIMER_TEZINA, Izbori(*p.PRIMER_IZBORI))
        # Sonnet, high, taman, 3 agenta na zadatku tezine 2: 300.000 x 1,3 tokena po 3,60 $/M, 15 x 0,8 x 0,5 min.
        self.assertEqual((racun.cena, racun.minuti), (Decimal("1.404"), Decimal("6.0")))
        odgovor = self.client.get(URL)
        primer = odgovor.context["primer"]
        self.assertEqual(primer["izbori"], ["Sonnet", "high", "таман", "3 агента"])
        self.assertEqual((primer["cena"], primer["minuti"]), ("1,404", "6"))
        self.assertEqual((primer["budzet_posle"], primer["rok_posle"]), ("22,596", "144"))
        self.assertEqual((primer["cena_dorade"], primer["minuti_dorade"]), ("2,808", "12"))
        self.assertEqual((primer["budzet_posle_dorade"], primer["rok_posle_dorade"]), ("21,192", "138"))
        self.assertContains(odgovor, "Sonnet · high · таман · 3 агента")
        self.assertContains(odgovor, "1,404 $ · 6 мин")

    def test_ne_otkriva_skrivene_podatke(self):
        sadrzaj = self.client.get(URL).content.decode()
        # Pravi zadaci se ne pominju, pa stranica ne kaze koji je tezak ni koji je tih.
        for zadatak in p.ZADACI:
            self.assertNotIn(zadatak.naziv, sadrzaj)
        self.assertNotIn(p.PRIMER_ZADATAK, [z.naziv for z in p.ZADACI])
        for rec in ("шанс", "тежин", "бонус", "семе"):
            self.assertNotIn(rec, sadrzaj.lower())

    def test_ista_za_svakoga_i_ne_dira_sesiju(self):
        partija = zapocni(self.client)
        posalji(self.client, telo(1))
        odgovor = self.client.get(URL)
        self.assertEqual(odgovor.content, Client().get(URL).content)
        self.assertNotIn("sessionid", odgovor.cookies)
        self.assertEqual(dict(self.client.session), {"partija_id": partija.pk})
        self.assertEqual(posalji(self.client, telo(2)).status_code, 200)

    def test_samo_get(self):
        self.assertEqual(self.client.post(URL).status_code, 405)

    def test_na_engleskom(self):
        odgovor = na_engleskom().get(URL)
        sadrzaj = odgovor.content.decode()
        self.assertIsNone(CIRILICA.search(sadrzaj))
        for tekst in ("How to play", "Example of one round", "Sonnet · high · just right · 3 agents",
                      "1.404 $ · 6 min", "22.596 $", "Silent error", "excellent orchestrator"):
            self.assertContains(odgovor, tekst)
