import random
from decimal import Decimal
from unittest import mock

from django.test import SimpleTestCase

from igra import parametri as p
from igra import pravila
from igra.pravila import Izbori

from .pomocno import HIGH_HAIKU, HIGH_OPUS, SVE_OPUS, neuspesni_krugovi

SVE_HAIKU = [HIGH_HAIKU] * 8


class ParametriTest(SimpleTestCase):
    def test_tihi_su_krugovi_5_6_i_8(self):
        self.assertEqual([z.krug for z in p.ZADACI if z.tih], [5, 6, 8])

    def test_redosled_tezina(self):
        self.assertEqual([z.tezina for z in p.ZADACI], [1, 1, 1, 2, 3, 3, 2, 3])

    def test_budzet_i_rok(self):
        self.assertEqual((p.BUDZET, p.ROK), (24, 150))


class RacunTest(SimpleTestCase):
    def test_osnovni_potez(self):
        racun = pravila.racun_poteza(1, HIGH_HAIKU)
        self.assertEqual(racun.cena, Decimal("0.018"))
        self.assertEqual(racun.minuti, Decimal("2.5"))
        self.assertEqual(racun.sansa, 90)

    def test_svi_mnozioci_zajedno(self):
        racun = pravila.racun_poteza(8, Izbori("opus", "max", "sve", "50_agenata"))
        self.assertEqual(racun.cena, Decimal("81.18144"))
        self.assertEqual(racun.minuti, Decimal("100.8"))
        self.assertEqual(racun.sansa, 66)

    def test_sonnet_sa_tri_agenta_na_tezini_2(self):
        racun = pravila.racun_poteza(4, Izbori("sonnet", "high", "taman", "3_agenta"))
        self.assertEqual(racun.cena, Decimal("1.404"))
        self.assertEqual(racun.minuti, Decimal("6"))
        self.assertEqual(racun.sansa, 85)

    def test_sansa_donja_granica(self):
        racun = pravila.racun_poteza(5, Izbori("haiku", "low", "malo", "50_agenata"))
        self.assertEqual(racun.sansa, 5)

    def test_ogranicenje_sanse(self):
        self.assertEqual(pravila.ogranici_sansu(100), 99)
        self.assertEqual(pravila.ogranici_sansu(99), 99)
        self.assertEqual(pravila.ogranici_sansu(5), 5)
        self.assertEqual(pravila.ogranici_sansu(4), 5)


class IshodTest(SimpleTestCase):
    def test_formula_iz_pravila_2(self):
        for seme in ("a", "b", "123"):
            for krug in range(1, 9):
                kocka = random.Random(f"{seme}:{krug}").randint(1, 100)
                self.assertTrue(pravila.uspeh_kruga(seme, krug, kocka))
                if kocka > 1:
                    self.assertFalse(pravila.uspeh_kruga(seme, krug, kocka - 1))

    def test_isti_ulaz_isti_ishod(self):
        potezi = SVE_OPUS
        self.assertEqual(
            pravila.konacni_rezultat("seme", potezi), pravila.konacni_rezultat("seme", potezi)
        )
        self.assertEqual(
            pravila.vidljivo_stanje("seme", potezi[:3]),
            pravila.vidljivo_stanje("seme", potezi[:3]),
        )

    def test_uspeh(self):
        with neuspesni_krugovi():
            ishod = pravila.odigraj_krug("s", 1, HIGH_OPUS)
        self.assertEqual((ishod.vrsta, ishod.status), (pravila.USPEH, "готово"))
        self.assertEqual((ishod.cena, ishod.minuti), (Decimal("0.72"), Decimal("5")))

    def test_neuspeh_koji_nije_tih_duplira_cenu_i_minute(self):
        with neuspesni_krugovi(1):
            ishod = pravila.odigraj_krug("s", 1, HIGH_OPUS)
        self.assertEqual((ishod.vrsta, ishod.status), (pravila.DORADA, "враћено на дораду"))
        self.assertEqual((ishod.cena, ishod.minuti), (Decimal("1.44"), Decimal("10")))

    def test_tihi_neuspeh_izgleda_kao_uspeh(self):
        with neuspesni_krugovi():
            uspeh = pravila.odigraj_krug("s", 5, HIGH_OPUS)
        with neuspesni_krugovi(5):
            tihi = pravila.odigraj_krug("s", 5, HIGH_OPUS)
        self.assertEqual(tihi.vrsta, pravila.TIHI_NEUSPEH)
        self.assertEqual(
            (tihi.status, tihi.cena, tihi.minuti), (uspeh.status, uspeh.cena, uspeh.minuti)
        )

    def test_vidljivo_stanje_ne_sadrzi_troskove_tihih_gresaka(self):
        with neuspesni_krugovi(5):
            stanje = pravila.vidljivo_stanje("s", SVE_OPUS)
        self.assertEqual(stanje.budzet_preostalo, Decimal("24") - Decimal("19.44"))
        self.assertEqual(stanje.rok_preostalo, Decimal("15"))

    def test_vidljivo_stanje_moze_biti_negativno(self):
        skupo = Izbori("opus", "max", "sve", "50_agenata")
        with neuspesni_krugovi():
            stanje = pravila.vidljivo_stanje("s", [skupo] * 8)
        self.assertTrue(stanje.budzet_prekoracen)
        self.assertTrue(stanje.rok_prekoracen)
        self.assertLess(stanje.budzet_preostalo, 0)


class KonacniRezultatTest(SimpleTestCase):
    def test_bez_gresaka(self):
        with neuspesni_krugovi():
            rezultat = pravila.konacni_rezultat("s", SVE_OPUS)
        self.assertEqual(rezultat.poeni, 100)
        self.assertEqual(rezultat.ocena, "одличан оркестратор")
        self.assertEqual(rezultat.ukupna_cena, Decimal("19.44"))
        self.assertEqual(rezultat.ukupni_minuti, Decimal("135"))
        self.assertEqual(rezultat.tihe_greske, ())

    def test_nezavrsena_partija_nema_rezultat(self):
        with self.assertRaises(ValueError):
            pravila.konacni_rezultat("s", SVE_OPUS[:7])

    def test_dorada_oduzima_5_poena(self):
        with neuspesni_krugovi(1):
            rezultat = pravila.konacni_rezultat("s", SVE_OPUS)
        self.assertEqual(rezultat.poeni, 95)
        self.assertEqual(rezultat.ukupna_cena, Decimal("20.16"))
        self.assertEqual(rezultat.ukupni_minuti, Decimal("140"))

    def test_tihi_neuspeh_dodaje_3_cene_i_minute_pa_oba_prekoracenja(self):
        with neuspesni_krugovi(5):
            rezultat = pravila.konacni_rezultat("s", SVE_OPUS)
        self.assertEqual(rezultat.ukupna_cena, Decimal("32.40"))
        self.assertEqual(rezultat.ukupni_minuti, Decimal("165"))
        # Budzet je prekoracen za 8,40 od 24, tj. 35 %: cetiri zapoceta koraka od 10 %.
        self.assertEqual(rezultat.poeni, 100 - 35 - 40 - 20)
        self.assertEqual([z.krug for z in rezultat.tihe_greske], [5])

    def test_tihi_neuspeh_bez_prekoracenja(self):
        with neuspesni_krugovi(5, 6):
            rezultat = pravila.konacni_rezultat("s", SVE_HAIKU)
        self.assertEqual(rezultat.poeni, 100 - 2 * 35)
        self.assertEqual([z.krug for z in rezultat.tihe_greske], [5, 6])

    def test_tri_tihe_greske_spustaju_na_nulu(self):
        with neuspesni_krugovi(5, 6, 8):
            rezultat = pravila.konacni_rezultat("s", SVE_HAIKU)
        self.assertEqual(rezultat.poeni, 0)
        self.assertEqual([z.krug for z in rezultat.tihe_greske], [5, 6, 8])

    def test_tacno_150_minuta_nije_prekoracenje(self):
        with neuspesni_krugovi(4):
            rezultat = pravila.konacni_rezultat("s", SVE_OPUS)
        self.assertEqual(rezultat.ukupni_minuti, Decimal("150"))
        self.assertEqual(rezultat.poeni, 95)

    def test_preko_150_minuta_je_kazna_20(self):
        with neuspesni_krugovi(4), mock.patch.object(p, "ROK", Decimal("149.99")):
            rezultat = pravila.konacni_rezultat("s", SVE_OPUS)
        self.assertEqual(rezultat.poeni, 95 - 20)

    def test_tacan_budzet_nije_prekoracenje(self):
        with neuspesni_krugovi(), mock.patch.object(p, "BUDZET", Decimal("19.44")):
            rezultat = pravila.konacni_rezultat("s", SVE_OPUS)
        self.assertEqual(rezultat.poeni, 100)

    def test_malo_preko_budzeta_je_jedan_korak(self):
        with neuspesni_krugovi(), mock.patch.object(p, "BUDZET", Decimal("19.439")):
            rezultat = pravila.konacni_rezultat("s", SVE_OPUS)
        self.assertEqual(rezultat.poeni, 90)

    def test_poeni_nisu_ispod_nule(self):
        with neuspesni_krugovi(*range(1, 9)):
            rezultat = pravila.konacni_rezultat("s", SVE_OPUS)
        self.assertEqual(rezultat.poeni, 0)
        self.assertEqual(rezultat.ocena, "пожар")

    def test_granice_ocena(self):
        ocekivano = {
            100: "одличан оркестратор",
            85: "одличан оркестратор",
            84: "солидан",
            65: "солидан",
            64: "скуп учитељ",
            40: "скуп учитељ",
            39: "пожар",
            0: "пожар",
        }
        for poeni, ocena in ocekivano.items():
            self.assertEqual(pravila.ocena_za_poene(poeni), ocena, poeni)


class BodovanjeTest(SimpleTestCase):
    """Izmena klijenta: nove partije se boduju strozije, stare zadrzavaju prvo bodovanje."""

    def test_nove_partije_koriste_drugo_bodovanje(self):
        self.assertEqual(p.BODOVANJE_TEKUCE, 2)
        self.assertEqual(p.BODOVANJA[2].tihi_poeni, 35)

    def test_kazna_raste_za_svaki_zapoceti_korak_od_10_posto(self):
        bodovanje = p.BODOVANJA[2]
        # Budzet je 24, pa je korak od 10 % tacno 2,40.
        ocekivano = {
            "24": 0,
            "24.0001": 10,
            "26.40": 10,
            "26.4001": 20,
            "28.80": 20,
            "33.60": 40,
            "33.61": 50,
            "36": 50,
            "48": 50,
            "1000": 50,
        }
        for cena, kazna in ocekivano.items():
            self.assertEqual(pravila.kazna_budzeta(Decimal(cena), bodovanje), kazna, cena)

    def test_prvo_bodovanje_ima_fiksnu_kaznu_30(self):
        bodovanje = p.BODOVANJA[1]
        for cena in ("24.0001", "26.40", "36", "1000"):
            self.assertEqual(pravila.kazna_budzeta(Decimal(cena), bodovanje), 30, cena)
        self.assertEqual(pravila.kazna_budzeta(Decimal("24"), bodovanje), 0)

    def test_prvo_bodovanje_daje_stare_poene(self):
        with neuspesni_krugovi(5):
            self.assertEqual(pravila.konacni_rezultat("s", SVE_OPUS, 1).poeni, 100 - 25 - 30 - 20)
        with neuspesni_krugovi(5, 6, 8):
            self.assertEqual(pravila.konacni_rezultat("s", SVE_HAIKU, 1).poeni, 25)
        with neuspesni_krugovi(), mock.patch.object(p, "BUDZET", Decimal("19.439")):
            self.assertEqual(pravila.konacni_rezultat("s", SVE_OPUS, 1).poeni, 70)

    def test_ostala_pravila_su_ista_u_obe_verzije(self):
        for neuspesni in ((), (1,), (4,)):
            with neuspesni_krugovi(*neuspesni):
                self.assertEqual(
                    pravila.konacni_rezultat("s", SVE_OPUS, 1), pravila.konacni_rezultat("s", SVE_OPUS, 2)
                )


class LekcijeTest(SimpleTestCase):
    def odeljci(self, potezi, *neuspesni):
        with neuspesni_krugovi(*neuspesni):
            return [l.odeljak for l in pravila.konacni_rezultat("s", potezi).lekcije]

    def sa_potezom(self, krug, izbori):
        potezi = list(SVE_HAIKU)
        potezi[krug - 1] = izbori
        return potezi

    def test_bez_uslova_nema_lekcija(self):
        self.assertEqual(self.odeljci(SVE_HAIKU), [])

    def test_tihi_neuspeh(self):
        self.assertEqual(self.odeljci(SVE_HAIKU, 5), ["4.2"])

    def test_vise_tihih_gresaka_daje_jednu_lekciju(self):
        self.assertEqual(self.odeljci(SVE_HAIKU, 5, 6, 8), ["4.2"])

    def test_dorada_nije_tihi_neuspeh(self):
        self.assertEqual(self.odeljci(SVE_HAIKU, 1), [])

    def test_opus_na_tezini_1(self):
        self.assertEqual(self.odeljci(self.sa_potezom(1, HIGH_OPUS)), ["3.2"])

    def test_opus_na_drugim_tezinama_nije_lekcija(self):
        self.assertEqual(self.odeljci(self.sa_potezom(4, HIGH_OPUS)), [])
        self.assertEqual(self.odeljci(self.sa_potezom(5, HIGH_OPUS)), [])

    def test_nivo_max(self):
        potezi = self.sa_potezom(2, Izbori("haiku", "max", "taman", "sam"))
        self.assertEqual(self.odeljci(potezi), ["3.3"])

    def test_kontekst_sve(self):
        potezi = self.sa_potezom(2, Izbori("haiku", "high", "sve", "sam"))
        self.assertEqual(self.odeljci(potezi), ["3.1"])

    def test_pedeset_agenata(self):
        potezi = self.sa_potezom(2, Izbori("haiku", "high", "taman", "50_agenata"))
        self.assertEqual(self.odeljci(potezi), ["5.3"])

    def test_tri_agenta_nisu_lekcija(self):
        potezi = self.sa_potezom(2, Izbori("haiku", "high", "taman", "3_agenta"))
        self.assertEqual(self.odeljci(potezi), [])
