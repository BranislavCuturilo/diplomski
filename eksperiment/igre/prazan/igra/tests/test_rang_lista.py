from datetime import datetime, timedelta, timezone as dt_timezone

from django.test import Client, TestCase
from django.utils import timezone

from igra import pravila
from igra.models import Partija, Rezultat

from .pomocno import SVE_OPUS
from .test_http import posalji, telo, zapocni

URL_CUVANJA = "/rezultat/"
# I birac jezika ima aria-current, pa se trazi bas istaknut red rang liste.
ISTAKNUT_RED = 'rang-istaknut" aria-current="true"'


def zavrsi(klijent, seme="seme-ranga"):
    partija = zapocni(klijent, seme)
    for krug in range(1, 9):
        posalji(klijent, telo(krug))
    return partija


def dodaj(ime, poeni, sacuvan):
    partija = Partija.objects.create(seme="x")
    rezultat = Rezultat.objects.create(partija=partija, ime=ime, poeni=poeni, ocena=pravila.ocena_za_poene(poeni))
    Rezultat.objects.filter(pk=rezultat.pk).update(sacuvan=sacuvan)
    return rezultat


class CuvanjeTest(TestCase):
    def sacuvaj(self, ime, klijent=None, **visak):
        podaci = {} if ime is None else {"ime": ime}
        return (klijent or self.client).post(URL_CUVANJA, {**podaci, **visak})

    def test_cuvanje_racuna_poene_na_serveru(self):
        partija = zavrsi(self.client)
        odgovor = self.sacuvaj("  Ана   Петровић ", poeni="100", ocena="одличан оркестратор")
        self.assertRedirects(odgovor, "/#rang-lista", fetch_redirect_response=False)

        ocekivano = pravila.konacni_rezultat("seme-ranga", SVE_OPUS)
        rezultat = Rezultat.objects.get()
        self.assertEqual(
            (rezultat.partija_id, rezultat.ime, rezultat.poeni, rezultat.ocena),
            (partija.pk, "Ана Петровић", ocekivano.poeni, ocekivano.ocena),
        )

    def test_pocetni_ekran_istice_sacuvan_rezultat(self):
        zavrsi(self.client)
        self.sacuvaj("Ана")
        rezultat = Rezultat.objects.get()
        odgovor = self.client.get("/")
        self.assertTemplateUsed(odgovor, "igra/pocetak.html")
        self.assertContains(odgovor, "Ана")
        self.assertContains(odgovor, f"<strong>{rezultat.poeni}</strong>")
        self.assertContains(odgovor, rezultat.ocena)
        self.assertContains(odgovor, timezone.localtime(rezultat.sacuvan).strftime("%d.%m.%Y."))
        self.assertContains(odgovor, ISTAKNUT_RED, count=1)
        self.assertNotContains(odgovor, 'id="nazad-na-rezultat"')

    def test_drugi_igrac_ne_vidi_tudji_red_istaknut(self):
        zavrsi(self.client)
        self.sacuvaj("Ана")
        odgovor = Client().get("/")
        self.assertContains(odgovor, "Ана")
        self.assertNotContains(odgovor, ISTAKNUT_RED)

    def test_zavrsni_ekran_posle_cuvanja(self):
        zavrsi(self.client)
        self.sacuvaj("Ана")
        odgovor = self.client.get("/kraj/")
        self.assertContains(odgovor, "Резултат је сачуван као „Ана“.")
        self.assertNotContains(odgovor, 'id="forma-imena"')

    def test_neispravno_ime_je_400_i_nista_se_ne_cuva(self):
        zavrsi(self.client)
        for ime in (None, "", "    ", "a" * 31, "ж" * 31, "ime\x00", "a​b", "a\x7fb"):
            odgovor = self.sacuvaj(ime)
            self.assertEqual(odgovor.status_code, 400, repr(ime))
            self.assertTemplateUsed(odgovor, "igra/kraj.html")
            self.assertContains(odgovor, 'id="greska-imena"', status_code=400)
        self.assertEqual(Rezultat.objects.count(), 0)

    def test_ime_od_30_znakova_je_dozvoljeno(self):
        zavrsi(self.client)
        self.sacuvaj("ж" * 30)
        self.assertEqual(Rezultat.objects.get().ime, "ж" * 30)

    def test_ime_se_escapuje(self):
        zavrsi(self.client)
        self.sacuvaj("<script>alert(1)</script>")
        odgovor = self.client.get("/")
        self.assertContains(odgovor, "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertNotContains(odgovor, "<script>alert")

    def test_drugo_cuvanje_iste_partije_je_409(self):
        zavrsi(self.client)
        self.sacuvaj("Ана")
        odgovor = self.sacuvaj("Марко")
        self.assertEqual(odgovor.status_code, 409)
        self.assertEqual(list(Rezultat.objects.values_list("ime", flat=True)), ["Ана"])

    def test_cuvanje_tokom_igre_je_409(self):
        zapocni(self.client)
        posalji(self.client, telo(1))
        odgovor = self.sacuvaj("Ана")
        self.assertEqual(odgovor.status_code, 409)
        self.assertEqual(Rezultat.objects.count(), 0)

    def test_neispravno_ime_tokom_igre_je_400(self):
        zapocni(self.client)
        self.assertEqual(self.sacuvaj("").status_code, 400)

    def test_cuvanje_bez_partije_je_409(self):
        self.assertEqual(self.sacuvaj("Ана").status_code, 409)
        self.assertEqual(Rezultat.objects.count(), 0)

    def test_nova_igra_posle_cuvanja_ima_svoj_rezultat(self):
        zavrsi(self.client)
        self.sacuvaj("Ана")
        self.client.post("/nova/")
        for krug in range(1, 9):
            posalji(self.client, telo(krug))
        self.sacuvaj("Ана")
        self.assertEqual(Rezultat.objects.count(), 2)

    def test_get_nije_dozvoljen(self):
        self.assertEqual(self.client.get(URL_CUVANJA).status_code, 405)

    def test_csrf_zastita(self):
        klijent = Client(enforce_csrf_checks=True)
        self.assertEqual(klijent.post(URL_CUVANJA, {"ime": "Ана"}).status_code, 403)

    def test_rang_lista_nema_seme(self):
        zavrsi(self.client, seme="tajnoseme0123456789")
        self.sacuvaj("Ана")
        self.assertNotContains(self.client.get("/"), "tajnoseme0123456789")


class RangListaTest(TestCase):
    def setUp(self):
        self.sada = timezone.now()

    def redovi(self):
        return Client().get("/").context["rang_lista"]

    def test_prazna_lista(self):
        self.assertContains(Client().get("/"), "Још нема сачуваних резултата.")

    def test_najvise_deset_najboljih(self):
        for i in range(12):
            dodaj(f"Играч {i}", i * 5, self.sada - timedelta(minutes=i))
        redovi = self.redovi()
        self.assertEqual(len(redovi), 10)
        self.assertEqual([r["poeni"] for r in redovi], [55, 50, 45, 40, 35, 30, 25, 20, 15, 10])
        self.assertEqual([r["mesto"] for r in redovi], list(range(1, 11)))

    def test_isti_poeni_dele_mesto_a_raniji_ide_prvi(self):
        dodaj("Ана", 80, self.sada - timedelta(minutes=3))
        dodaj("Бора", 90, self.sada - timedelta(minutes=1))
        dodaj("Вера", 80, self.sada - timedelta(minutes=2))
        dodaj("Гоца", 70, self.sada - timedelta(minutes=4))
        redovi = self.redovi()
        self.assertEqual([r["ime"] for r in redovi], ["Бора", "Ана", "Вера", "Гоца"])
        self.assertEqual([r["mesto"] for r in redovi], [1, 2, 2, 4])

    def test_datum_po_beogradskom_vremenu(self):
        dodaj("Ана", 50, datetime(2026, 11, 9, 23, 30, tzinfo=dt_timezone.utc))
        self.assertEqual(self.redovi()[0]["datum"], "10.11.2026.")

    def test_red_ima_ime_poene_ocenu_i_datum(self):
        dodaj("Ана", 85, datetime(2026, 5, 1, 12, 0, tzinfo=dt_timezone.utc))
        odgovor = Client().get("/")
        for tekst in ("Ана", "<strong>85</strong>", "одличан оркестратор", "01.05.2026."):
            self.assertContains(odgovor, tekst)
