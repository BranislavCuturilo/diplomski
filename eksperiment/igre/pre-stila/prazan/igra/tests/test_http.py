import json
from unittest import mock

from django.db import IntegrityError, transaction
from django.test import Client, TestCase

from igra import pravila
from igra.models import Partija, Potez
from igra.pravila import Izbori

from .pomocno import HIGH_HAIKU, HIGH_OPUS, neuspesni_krugovi

URL_POTEZA = "/api/potez/"


def telo(krug, izbori=HIGH_OPUS):
    return {"krug": krug, **izbori._asdict()}


def posalji(klijent, podaci):
    return klijent.post(URL_POTEZA, json.dumps(podaci), content_type="application/json")


def zapocni(klijent, seme=None):
    klijent.post("/nova/")
    partija = Partija.objects.latest("pk")
    if seme is not None:
        partija.seme = seme
        partija.save()
    return partija


def snimak():
    return (
        list(Partija.objects.order_by("pk").values()),
        list(Potez.objects.order_by("pk").values()),
    )


class OsnovniTokTest(TestCase):
    def test_bez_partije_je_pocetni_ekran(self):
        odgovor = self.client.get("/")
        self.assertTemplateUsed(odgovor, "igra/pocetak.html")
        self.assertContains(odgovor, "24 $")
        self.assertContains(odgovor, "150 мин")
        self.assertEqual(Partija.objects.count(), 0)

    def test_nova_igra_otvara_prvi_krug(self):
        odgovor = self.client.post("/nova/", follow=True)
        self.assertTemplateUsed(odgovor, "igra/igra.html")
        self.assertContains(odgovor, "Превод почетне стране")

    def test_opcije_imaju_mnozioce(self):
        zapocni(self.client)
        odgovor = self.client.get("/")
        for tekst in ("0,18 $/M", "7,20 $/M", "време ×0,5", "токени ×3,6", "време ×2,1"):
            self.assertContains(odgovor, tekst)

    def test_nova_igra_tokom_partije_ne_pravi_novu(self):
        partija = zapocni(self.client)
        posalji(self.client, telo(1))
        self.client.post("/nova/")
        self.assertEqual(Partija.objects.count(), 1)
        self.assertEqual(self.client.session["partija_id"], partija.pk)
        self.assertEqual(Potez.objects.count(), 1)

    def test_uspesan_potez(self):
        zapocni(self.client)
        with neuspesni_krugovi():
            odgovor = posalji(self.client, telo(1, HIGH_HAIKU))
        self.assertEqual(odgovor.status_code, 200)
        self.assertEqual(
            odgovor.json(),
            {
                "krug": 1,
                "status": "готово",
                "cena": "0,018",
                "minuti": "2,5",
                "budzet_preostalo": "23,982",
                "rok_preostalo": "147,5",
                "budzet_prekoracen": False,
                "rok_prekoracen": False,
                "sledeci": {"krug": 2, "naziv": "Шаблон листе и форме"},
                "zavrsena": False,
            },
        )

    def test_dorada(self):
        zapocni(self.client)
        with neuspesni_krugovi(1):
            odgovor = posalji(self.client, telo(1, HIGH_HAIKU)).json()
        self.assertEqual(odgovor["status"], "враћено на дораду")
        self.assertEqual((odgovor["cena"], odgovor["minuti"]), ("0,036", "5"))
        self.assertEqual(odgovor["sledeci"]["krug"], 2)

    def test_prekoracenje_se_prikazuje_i_igra_ide_dalje(self):
        zapocni(self.client)
        skupo = Izbori("opus", "max", "sve", "50_agenata")
        with neuspesni_krugovi():
            for krug in range(1, 5):
                odgovor = posalji(self.client, telo(krug, skupo))
                self.assertEqual(odgovor.status_code, 200)
            podaci = odgovor.json()
            stranica = self.client.get("/")
        self.assertTrue(podaci["budzet_prekoracen"])
        self.assertTrue(podaci["budzet_preostalo"].startswith("-"))
        self.assertContains(stranica, 'id="budzet" class="text-danger"')

    def test_cela_igra_do_zavrsnog_ekrana(self):
        zapocni(self.client)
        with neuspesni_krugovi(1, 5):
            for krug in range(1, 8):
                self.assertFalse(posalji(self.client, telo(krug)).json()["zavrsena"])
            poslednji = posalji(self.client, telo(8)).json()
            kraj = self.client.get("/kraj/")
        self.assertTrue(poslednji["zavrsena"])
        self.assertIsNone(poslednji["sledeci"])
        self.assertTemplateUsed(kraj, "igra/kraj.html")
        # Dorada -5, tihi neuspeh -25, obe kazne za prekoracenje.
        self.assertEqual(kraj.context["poeni"], 100 - 5 - 25 - 30 - 20)
        self.assertEqual(kraj.context["ocena"], "пожар")
        self.assertContains(kraj, "Модел података и миграција")
        self.assertContains(kraj, "Одељак 4.2 завршног рада")
        self.assertContains(kraj, "Одељак 3.2 завршног рада")
        self.assertContains(
            kraj,
            "Цене и нивои размишљања су стварни подаци; "
            "вероватноће, казне и поени су измишљени параметри игре.",
        )

    def test_kraj_tokom_partije_vraca_na_igru(self):
        zapocni(self.client)
        self.assertRedirects(self.client.get("/kraj/"), "/")

    def test_kraj_bez_partije_vraca_na_pocetak(self):
        self.assertRedirects(self.client.get("/kraj/"), "/")

    def test_zavrsena_igra_preusmerava_na_kraj_pa_nova_igra(self):
        stara = zapocni(self.client)
        for krug in range(1, 9):
            posalji(self.client, telo(krug))
        self.assertRedirects(self.client.get("/"), "/kraj/")

        odgovor = self.client.post("/nova/", follow=True)
        self.assertTemplateUsed(odgovor, "igra/igra.html")
        self.assertEqual(odgovor.context["krug"], 1)
        nova = Partija.objects.latest("pk")
        self.assertNotEqual(nova.pk, stara.pk)
        self.assertNotEqual(nova.seme, stara.seme)

    def test_ucitavanje_tokom_igre_cuva_stanje(self):
        zapocni(self.client)
        posalji(self.client, telo(1))
        odgovor = self.client.get("/")
        self.assertEqual(odgovor.context["krug"], 2)
        self.assertEqual(len(odgovor.context["istorija"]), 1)


class GreskeTest(TestCase):
    def setUp(self):
        self.partija = zapocni(self.client)
        posalji(self.client, telo(1))

    def proveri(self, podaci_ili_bajtovi, kod):
        pre = snimak()
        if isinstance(podaci_ili_bajtovi, bytes):
            odgovor = self.client.post(
                URL_POTEZA, podaci_ili_bajtovi, content_type="application/json"
            )
        else:
            odgovor = posalji(self.client, podaci_ili_bajtovi)
        self.assertEqual(odgovor.status_code, kod, podaci_ili_bajtovi)
        self.assertEqual(list(odgovor.json()), ["greska"])
        self.assertEqual(snimak(), pre)

    def test_pogresan_krug_je_409(self):
        for krug in (1, 3, 0, -1, 8, 9, 10**30):
            self.proveri(telo(krug), 409)

    def test_neispravno_telo_je_400(self):
        for sirovo in (b"", b"nije json", b"[]", b"5", b"null", b'"tekst"', b"\xff\xfe\xff", b"[" * 200000):
            self.proveri(sirovo, 400)

    def test_nedostajuce_polje_je_400(self):
        for polje in ("krug", "model", "nivo", "kontekst", "podela"):
            podaci = telo(2)
            del podaci[polje]
            self.proveri(podaci, 400)

    def test_klijent_ne_sme_da_salje_visak_polja(self):
        for polje in ("cena", "poeni", "ishod", "minuti", "seme"):
            self.proveri({**telo(2), polje: 0}, 400)

    def test_neispravan_broj_kruga_je_400(self):
        for krug in ("2", 2.0, True, None, [2], {"krug": 2}):
            self.proveri({**telo(2), "krug": krug}, 400)

    def test_nepoznat_izbor_je_400(self):
        for polje in ("model", "nivo", "kontekst", "podela"):
            for vrednost in ("nepoznato", "", None, 1, ["opus"], {"a": 1}):
                self.proveri({**telo(2), polje: vrednost}, 400)

    def test_igra_se_nastavlja_posle_greske(self):
        self.proveri({**telo(2), "model": "gpt"}, 400)
        self.proveri(telo(5), 409)
        self.assertEqual(posalji(self.client, telo(2)).status_code, 200)

    def test_zavrsena_igra_je_409(self):
        for krug in range(2, 9):
            self.assertEqual(posalji(self.client, telo(krug)).status_code, 200)
        for krug in (8, 9, 1):
            self.proveri(telo(krug), 409)

    def test_neispravan_zahtev_u_zavrsenoj_igri_je_400(self):
        for krug in range(2, 9):
            posalji(self.client, telo(krug))
        self.proveri({**telo(9), "model": "gpt"}, 400)

    def test_dupli_potez_ne_menja_rezultat(self):
        prvi = posalji(self.client, telo(2))
        pre = snimak()
        drugi = posalji(self.client, telo(2, Izbori("haiku", "low", "malo", "sam")))
        self.assertEqual(prvi.status_code, 200)
        self.assertEqual(drugi.status_code, 409)
        self.assertEqual(snimak(), pre)

    def test_ogranicenje_baze_postaje_409(self):
        with mock.patch.object(Potez.objects, "create", side_effect=IntegrityError):
            odgovor = posalji(self.client, telo(2))
        self.assertEqual(odgovor.status_code, 409)

    def test_baza_odbija_dva_poteza_za_isti_krug(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Potez.objects.create(partija=self.partija, krug=1, **HIGH_OPUS._asdict())

    def test_potez_bez_partije_je_409(self):
        odgovor = posalji(Client(), telo(1))
        self.assertEqual(odgovor.status_code, 409)

    def test_get_na_api_nije_dozvoljen(self):
        self.assertEqual(self.client.get(URL_POTEZA).status_code, 405)

    def test_csrf_zastita_je_ukljucena(self):
        klijent = Client(enforce_csrf_checks=True)
        self.assertEqual(klijent.post("/nova/").status_code, 403)


class PonovljivostTest(TestCase):
    def odigraj(self, seme, potezi):
        klijent = Client()
        zapocni(klijent, seme)
        odgovori = [posalji(klijent, telo(k, i)).json() for k, i in enumerate(potezi, start=1)]
        return odgovori, klijent.get("/kraj/").context

    def test_isto_seme_i_isti_izbori_daju_isti_rezultat(self):
        potezi = [HIGH_HAIKU, HIGH_OPUS] * 4
        odgovori_a, kraj_a = self.odigraj("seme-1", potezi)
        odgovori_b, kraj_b = self.odigraj("seme-1", potezi)
        self.assertEqual(odgovori_a, odgovori_b)
        for kljuc in ("poeni", "ocena", "ukupna_cena", "ukupni_minuti", "tihe_greske", "lekcije"):
            self.assertEqual(kraj_a[kljuc], kraj_b[kljuc])

    def test_rezultat_odgovara_cistoj_funkciji(self):
        potezi = [HIGH_HAIKU] * 8
        for seme in ("0", "1", "2", "3"):
            _, kraj = self.odigraj(seme, potezi)
            self.assertEqual(kraj["poeni"], pravila.konacni_rezultat(seme, potezi).poeni)
