"""Pravila igre nad cistim motorom, bez servera.

Ocekivani brojevi su prepisani iz MVP.md i izracunati rucno, ne citaju se iz parametri.py:
test koji ocekivanje uzima iz koda koji proverava ne moze da padne.
"""

import ast
import copy
import json
import math
import pathlib
import random
from unittest import mock

from django.test import SimpleTestCase

from igra import motor
from igra import parametri as p

TEZINE = [1, 1, 1, 2, 3, 3, 2, 3]
TIHI_KRUGOVI = {5, 6, 8}
KRUGOVI = range(1, 9)
TACNOST = 9


def izbori(model="sonnet", nivo="high", kontekst="taman", podela="sam"):
    return {"model": model, "nivo": nivo, "kontekst": kontekst, "podela": podela}


OPUS_HIGH = izbori("opus")
HAIKU_LOW_MALO = izbori("haiku", "low", "malo")


def sve_opus(_krug):
    return OPUS_HIGH


def sve_haiku_low_malo(_krug):
    return HAIKU_LOW_MALO


def po_tezini(krug):
    tezina = TEZINE[krug - 1]
    if tezina == 1:
        return izbori("haiku")
    if tezina == 2:
        return izbori("sonnet", podela="tri")
    return izbori("opus")


def odigraj_celu(seme, strategija):
    stanje = motor.nova_igra(seme)
    for krug in KRUGOVI:
        stanje = motor.odigraj_potez(stanje, krug, strategija(krug))
    return stanje


def ishodi(stanje):
    return [r["ishod"] for r in stanje["istorija"]]


def nadji_seme(strategija, uslov, granica=20000):
    """Prvo seme iz niza 0, 1, 2... za koje ishodi cele partije ispunjavaju uslov."""
    for i in range(granica):
        seme = str(i)
        if uslov(ishodi(odigraj_celu(seme, strategija))):
            return seme
    raise AssertionError("nema semena sa trazenim ishodima")


def sirovo_stanje(potroseno=0.0, minuti=0.0, izmene=None):
    """Stanje posle 8. kruga, pred kontrolni skup; svi redovi su uspeh dok izmena ne kaze drugo."""
    istorija = []
    for krug in KRUGOVI:
        red = {
            "krug": krug,
            "izbori": izbori("haiku"),
            "cena": 0.0,
            "minuti": 0.0,
            "ishod": motor.USPEH,
        }
        red.update((izmene or {}).get(krug, {}))
        istorija.append(red)
    return {
        "seme": "s",
        "krug": 8,
        "zavrsena": False,
        "potroseno": potroseno,
        "minuti": minuti,
        "istorija": istorija,
        "rezultat": None,
    }


class ParametriTests(SimpleTestCase):
    def test_redosled_zadataka(self):
        ocekivano = [
            ("Превод почетне стране", 1, False),
            ("Шаблон листе и форме", 1, False),
            ("CSS и прилагођавање телефону", 1, False),
            ("CRUD прикази", 2, False),
            ("Модел података и миграција", 3, True),
            ("Провера права приступа", 3, True),
            ("Аутоматски тестови", 2, False),
            ("Безбедносна ревизија", 3, True),
        ]
        dobijeno = [(z["naziv"], z["tezina"], z["tih"]) for z in p.ZADACI]
        self.assertEqual(dobijeno, ocekivano)

    def test_osnovne_konstante(self):
        self.assertEqual(
            (p.KRUGOVA, p.BUDZET, p.ROK, p.POCETNI_POENI, p.MIN_POENI), (8, 24, 150, 100, 0)
        )
        self.assertEqual(
            (p.KAZNA_DORADA, p.KAZNA_TIHA, p.KAZNA_BUDZET, p.KAZNA_ROK), (5, 25, 30, 20)
        )

    def test_napomena_doslovno(self):
        self.assertEqual(
            p.NAPOMENA,
            "Цене и нивои размишљања су стварни подаци; вероватноће, казне и "
            "поени су измишљени параметри игре.",
        )

    def test_statusi_doslovno(self):
        self.assertEqual(p.STATUS_GOTOVO, "готово")
        self.assertEqual(p.STATUS_DORADA, "враћено на дораду")


class RacunTests(SimpleTestCase):
    SLUCAJEVI = [
        # model, po tezini
        (1, izbori("haiku"), 0.018, 2.5, 90),
        (2, izbori("haiku"), 0.054, 7.5, 65),
        (3, izbori("haiku"), 0.108, 15.0, 30),
        (1, izbori("sonnet"), 0.36, 4.0, 95),
        (2, izbori("sonnet"), 1.08, 12.0, 85),
        (3, izbori("sonnet"), 2.16, 24.0, 60),
        (1, izbori("opus"), 0.72, 5.0, 97),
        (2, izbori("opus"), 2.16, 15.0, 92),
        (3, izbori("opus"), 4.32, 30.0, 85),
        # nivo
        (1, izbori("sonnet", "low"), 0.1188, 2.4, 95),
        (2, izbori("sonnet", "low"), 0.3564, 7.2, 70),
        (3, izbori("sonnet", "low"), 0.7128, 14.4, 35),
        (1, izbori("sonnet", "max"), 1.044, 6.4, 96),
        (2, izbori("sonnet", "max"), 3.132, 19.2, 86),
        (3, izbori("sonnet", "max"), 6.264, 38.4, 61),
        # kontekst
        (1, izbori("sonnet", kontekst="malo"), 0.216, 4.0, 95),
        (2, izbori("sonnet", kontekst="malo"), 0.648, 12.0, 70),
        (3, izbori("sonnet", kontekst="malo"), 1.296, 24.0, 35),
        (1, izbori("sonnet", kontekst="sve"), 0.648, 4.0, 85),
        (2, izbori("sonnet", kontekst="sve"), 1.944, 12.0, 75),
        (3, izbori("sonnet", kontekst="sve"), 3.888, 24.0, 50),
        # podela
        (2, izbori("sonnet", podela="tri"), 1.404, 6.0, 85),
        (2, izbori("sonnet", podela="pedeset"), 3.888, 25.2, 75),
        (1, izbori("sonnet", podela="pedeset"), 1.296, 8.4, 85),
        (3, izbori("sonnet", podela="pedeset"), 7.776, 50.4, 50),
        # sve zajedno
        (3, izbori("opus", "max", "sve", "pedeset"), 81.18144, 100.8, 66),
        (1, izbori("haiku", "low", "malo", "sam"), 0.003564, 1.5, 90),
    ]

    def test_racun_po_redu_svake_tabele(self):
        for tezina, izbor, cena, minuti, sansa in self.SLUCAJEVI:
            with self.subTest(tezina=tezina, izbor=izbor):
                r = motor.racun(tezina, izbor)
                self.assertAlmostEqual(r["cena"], cena, places=TACNOST)
                self.assertAlmostEqual(r["minuti"], minuti, places=TACNOST)
                self.assertEqual(r["sansa"], sansa)

    def test_sansa_donja_granica_5(self):
        # 30 - 25 - 25 - 10 = -30
        r = motor.racun(3, izbori("haiku", "low", "malo", "pedeset"))
        self.assertEqual(r["sansa"], 5)

    def test_sansa_gornja_granica_99(self):
        # Pravi parametri daju najvise 98, pa granicu moze da pokaze samo veca ulazna sansa.
        self.assertEqual(motor.racun(1, izbori("opus", "max"))["sansa"], 98)
        with mock.patch.dict(p.MODELI["opus"]["sansa"], {1: 120}):
            self.assertEqual(motor.racun(1, izbori("opus", "high"))["sansa"], 99)

    def test_procene_81_kombinacija_bez_sanse(self):
        for tezina in (1, 2, 3):
            with self.subTest(tezina=tezina):
                procene = motor.procene(tezina)
                self.assertEqual(len(procene), 81)
                for vrednost in procene.values():
                    self.assertEqual(set(vrednost), {"cena", "minuti"})
        self.assertEqual(
            motor.procene(3)["opus|high|taman|sam"], {"cena": 4.32, "minuti": 30.0}
        )
        self.assertEqual(
            motor.procene(1)["haiku|low|malo|sam"], {"cena": 0.0036, "minuti": 1.5}
        )


class DeterminizamTests(SimpleTestCase):
    def test_formula_uspeha_doslovno(self):
        for seme in ("0", "42", "abc"):
            for krug in KRUGOVI:
                with self.subTest(seme=seme, krug=krug):
                    kocka = random.Random(f"{seme}:{krug}").randint(1, 100)
                    self.assertTrue(motor.uspeh_kruga(seme, krug, kocka))
                    self.assertFalse(motor.uspeh_kruga(seme, krug, kocka - 1))

    def test_isto_seme_isti_izbori_isti_rezultat(self):
        for seme in ("0", "1", "42", "seme-sa-tekstom"):
            for strategija in (sve_opus, sve_haiku_low_malo, po_tezini):
                with self.subTest(seme=seme, strategija=strategija.__name__):
                    self.assertEqual(
                        odigraj_celu(seme, strategija), odigraj_celu(seme, strategija)
                    )

    def test_razlicito_seme_menja_ishode(self):
        razlicitih = {tuple(ishodi(odigraj_celu(str(i), po_tezini))) for i in range(200)}
        self.assertGreater(len(razlicitih), 1)

    def test_globalni_random_ne_utice(self):
        self.addCleanup(random.setstate, random.getstate())
        random.seed(1)
        prvi = odigraj_celu("42", po_tezini)
        random.seed(987654)
        random.random()
        drugi = odigraj_celu("42", po_tezini)
        self.assertEqual(prvi, drugi)

    def test_motor_ne_trosi_globalni_random(self):
        self.addCleanup(random.setstate, random.getstate())
        random.seed(5)
        pre = random.getstate()
        odigraj_celu("42", po_tezini)
        self.assertEqual(random.getstate(), pre)

    def test_odigraj_ne_menja_ulaz(self):
        stanje = motor.nova_igra("42")
        for krug in KRUGOVI:
            pre = copy.deepcopy(stanje)
            ulaz = dict(OPUS_HIGH)
            novo = motor.odigraj_potez(stanje, krug, ulaz)
            self.assertEqual(stanje, pre)
            self.assertEqual(ulaz, OPUS_HIGH)
            self.assertIsNot(novo, stanje)
            self.assertIsNot(novo["istorija"], stanje["istorija"])
            stanje = novo

    def test_kontrolni_skup_ne_menja_ulaz(self):
        stanje = sirovo_stanje(potroseno=10.0, minuti=10.0)
        pre = copy.deepcopy(stanje)
        motor.kontrolni_skup(stanje)
        self.assertEqual(stanje, pre)

    def test_stanje_samo_json_tipovi(self):
        stanje = motor.nova_igra("7")
        for krug in KRUGOVI:
            stanje = motor.odigraj_potez(stanje, krug, po_tezini(krug))
            povratak = json.loads(json.dumps(stanje))
            self.assertEqual(povratak, stanje)
            stanje = povratak


class ProveraPotezaTests(SimpleTestCase):
    def test_poznati_izbori_prolaze(self):
        self.assertIsNone(motor.proveri_izbore(izbori("haiku", "max", "sve", "pedeset")))

    def test_nepoznati_izbori(self):
        pogresni = [
            None,
            [],
            "opus",
            {},
            {"model": "opus"},
            {**OPUS_HIGH, "cena": 0},
            {**OPUS_HIGH, "model": "gpt"},
            {**OPUS_HIGH, "nivo": "ultra"},
            {**OPUS_HIGH, "kontekst": "nista"},
            {**OPUS_HIGH, "podela": "sto"},
            {**OPUS_HIGH, "model": ["opus"]},
            {**OPUS_HIGH, "nivo": None},
            {**OPUS_HIGH, "kontekst": 1},
            {**OPUS_HIGH, "podela": {}},
        ]
        for izbor in pogresni:
            with self.subTest(izbor=izbor):
                with self.assertRaises(motor.NepoznatIzbor):
                    motor.proveri_izbore(izbor)

    def test_pogresan_krug(self):
        stanje = motor.nova_igra("1")
        for krug in (0, 2, 9, -1):
            with self.subTest(krug=krug):
                with self.assertRaises(motor.PogresanKrug):
                    motor.odigraj_potez(stanje, krug, OPUS_HIGH)

    def test_zavrsena_igra(self):
        stanje = odigraj_celu("1", sve_opus)
        for krug in (8, 9, 1):
            with self.subTest(krug=krug):
                with self.assertRaises(motor.IgraZavrsena):
                    motor.odigraj_potez(stanje, krug, OPUS_HIGH)

    def test_nepoznat_izbor_ima_prednost(self):
        zavrsena = odigraj_celu("1", sve_opus)
        with self.assertRaises(motor.NepoznatIzbor):
            motor.odigraj_potez(zavrsena, 8, {**OPUS_HIGH, "model": "gpt"})
        with self.assertRaises(motor.NepoznatIzbor):
            motor.odigraj_potez(motor.nova_igra("1"), 5, {**OPUS_HIGH, "model": "gpt"})


class IshodTests(SimpleTestCase):
    def test_uspeh_placa_jednom(self):
        seme = nadji_seme(sve_opus, lambda i: i[0] == motor.USPEH)
        novo = motor.odigraj_potez(motor.nova_igra(seme), 1, OPUS_HIGH)
        self.assertEqual(novo["istorija"][0]["ishod"], motor.USPEH)
        self.assertAlmostEqual(novo["potroseno"], 0.72, places=TACNOST)
        self.assertAlmostEqual(novo["minuti"], 5.0, places=TACNOST)
        self.assertEqual(novo["krug"], 2)

    def test_dorada_dva_puta_cena_i_minuti_odmah(self):
        seme = nadji_seme(lambda _k: izbori("haiku"), lambda i: i[0] == motor.DORADA)
        novo = motor.odigraj_potez(motor.nova_igra(seme), 1, izbori("haiku"))
        self.assertEqual(novo["istorija"][0]["ishod"], motor.DORADA)
        self.assertAlmostEqual(novo["potroseno"], 0.036, places=TACNOST)
        self.assertAlmostEqual(novo["minuti"], 5.0, places=TACNOST)
        self.assertAlmostEqual(novo["istorija"][0]["cena"], 0.036, places=TACNOST)
        self.assertAlmostEqual(novo["istorija"][0]["minuti"], 5.0, places=TACNOST)

    def test_neuspeh_na_tihom_zadatku_ne_placa_odmah(self):
        seme = nadji_seme(
            sve_opus,
            lambda i: i[:4] == [motor.USPEH] * 4 and i[4] == motor.TIHI_NEUSPEH,
        )
        stanje = motor.nova_igra(seme)
        for krug in range(1, 6):
            pre_potroseno = stanje["potroseno"]
            stanje = motor.odigraj_potez(stanje, krug, OPUS_HIGH)
        self.assertEqual(stanje["istorija"][4]["ishod"], motor.TIHI_NEUSPEH)
        self.assertAlmostEqual(stanje["potroseno"] - pre_potroseno, 4.32, places=TACNOST)

    def test_tih_neuspeh_4x_cena_2x_minuti(self):
        seme = nadji_seme(
            sve_opus,
            lambda i: i
            == [motor.USPEH] * 4 + [motor.TIHI_NEUSPEH] + [motor.USPEH] * 3,
        )
        kraj = odigraj_celu(seme, sve_opus)
        r = kraj["rezultat"]
        # 19,44 + 3 * 4,32 i 135 + 30
        self.assertAlmostEqual(r["ukupna_cena"], 32.40, places=TACNOST)
        self.assertAlmostEqual(r["ukupni_minuti"], 165.0, places=TACNOST)
        self.assertEqual(len(r["tihe_greske"]), 1)
        greska = r["tihe_greske"][0]
        self.assertEqual(greska["krug"], 5)
        self.assertEqual(greska["zadatak"], "Модел података и миграција")
        self.assertAlmostEqual(greska["dodatak_cena"], 12.96, places=TACNOST)
        self.assertAlmostEqual(greska["dodatak_minuti"], 30.0, places=TACNOST)
        self.assertTrue(r["budzet_prekoracen"])
        self.assertTrue(r["rok_prekoracen"])
        # 100 - 25 - 30 - 20
        self.assertEqual(r["poeni"], 25)
        self.assertEqual(r["ocena"], "пожар")

    def test_tihi_su_samo_krugovi_5_6_8(self):
        strategija = lambda _k: izbori("haiku", "low", "malo", "pedeset")
        kraj = odigraj_celu("3", strategija)
        for red in kraj["istorija"]:
            with self.subTest(krug=red["krug"]):
                if red["ishod"] == motor.TIHI_NEUSPEH:
                    self.assertIn(red["krug"], TIHI_KRUGOVI)
                if red["ishod"] == motor.DORADA:
                    self.assertNotIn(red["krug"], TIHI_KRUGOVI)
        self.assertIn(motor.TIHI_NEUSPEH, ishodi(kraj))
        self.assertIn(motor.DORADA, ishodi(kraj))

    def test_kontrolni_skup_ide_sam_posle_osmog(self):
        stanje = motor.nova_igra("1")
        for krug in range(1, 8):
            stanje = motor.odigraj_potez(stanje, krug, OPUS_HIGH)
            self.assertFalse(stanje["zavrsena"])
            self.assertIsNone(stanje["rezultat"])
        stanje = motor.odigraj_potez(stanje, 8, OPUS_HIGH)
        self.assertTrue(stanje["zavrsena"])
        self.assertIsNotNone(stanje["rezultat"])

    def test_prekoracenje_ne_prekida_igru(self):
        skupo = izbori("opus", "max", "sve", "pedeset")
        stanje = motor.nova_igra("1")
        stanje = motor.odigraj_potez(stanje, 1, skupo)
        stanje = motor.odigraj_potez(stanje, 2, skupo)
        stanje = motor.odigraj_potez(stanje, 3, skupo)
        self.assertGreater(stanje["potroseno"], p.BUDZET)
        self.assertFalse(stanje["zavrsena"])
        self.assertEqual(stanje["krug"], 4)


class PoeniTests(SimpleTestCase):
    def test_bez_gresaka_100(self):
        r = motor.kontrolni_skup(sirovo_stanje(potroseno=1.0, minuti=1.0))["rezultat"]
        self.assertEqual(r["poeni"], 100)
        self.assertEqual(r["ocena"], "одличан оркестратор")
        self.assertFalse(r["budzet_prekoracen"])
        self.assertFalse(r["rok_prekoracen"])

    def test_dorada_minus_5_svaka(self):
        izmene = {1: {"ishod": motor.DORADA}, 4: {"ishod": motor.DORADA}}
        r = motor.kontrolni_skup(sirovo_stanje(izmene=izmene))["rezultat"]
        self.assertEqual(r["poeni"], 90)

    def test_tih_minus_25_svaki(self):
        izmene = {5: {"ishod": motor.TIHI_NEUSPEH}, 6: {"ishod": motor.TIHI_NEUSPEH}}
        r = motor.kontrolni_skup(sirovo_stanje(izmene=izmene))["rezultat"]
        self.assertEqual(r["poeni"], 50)
        self.assertEqual([g["krug"] for g in r["tihe_greske"]], [5, 6])

    def test_kazna_budzeta_30(self):
        r = motor.kontrolni_skup(sirovo_stanje(potroseno=24.01))["rezultat"]
        self.assertTrue(r["budzet_prekoracen"])
        self.assertFalse(r["rok_prekoracen"])
        self.assertEqual(r["poeni"], 70)

    def test_kazna_roka_20(self):
        r = motor.kontrolni_skup(sirovo_stanje(minuti=150.1))["rezultat"]
        self.assertFalse(r["budzet_prekoracen"])
        self.assertTrue(r["rok_prekoracen"])
        self.assertEqual(r["poeni"], 80)

    def test_kazna_posle_dodataka(self):
        izmene = {5: {"ishod": motor.TIHI_NEUSPEH, "cena": 2.0, "minuti": 20.0}}

        # Pre dodataka je u okviru: 20 <= 24 i 140 <= 150.
        kontrola = motor.kontrolni_skup(sirovo_stanje(potroseno=20.0, minuti=140.0))["rezultat"]
        self.assertFalse(kontrola["budzet_prekoracen"])
        self.assertFalse(kontrola["rok_prekoracen"])

        r = motor.kontrolni_skup(sirovo_stanje(20.0, 140.0, izmene))["rezultat"]
        self.assertAlmostEqual(r["ukupna_cena"], 26.0, places=TACNOST)
        self.assertAlmostEqual(r["ukupni_minuti"], 160.0, places=TACNOST)
        self.assertTrue(r["budzet_prekoracen"])
        self.assertTrue(r["rok_prekoracen"])
        self.assertEqual(r["poeni"], 25)

    def test_tacno_150_bez_kazne(self):
        r = motor.kontrolni_skup(sirovo_stanje(minuti=150.0))["rezultat"]
        self.assertFalse(r["rok_prekoracen"])
        self.assertEqual(r["poeni"], 100)

    def test_tacno_150_iz_prave_partije(self):
        # Opus high: 135 min; jedna dorada na tezini 2 dodaje tacno 15.
        seme = nadji_seme(
            sve_opus,
            lambda i: i.count(motor.DORADA) == 1
            and motor.TIHI_NEUSPEH not in i
            and motor.DORADA in (i[3], i[6]),
        )
        r = odigraj_celu(seme, sve_opus)["rezultat"]
        self.assertAlmostEqual(r["ukupni_minuti"], 150.0, places=TACNOST)
        self.assertFalse(r["rok_prekoracen"])
        self.assertFalse(r["budzet_prekoracen"])
        self.assertEqual(r["poeni"], 95)

    def test_tacno_24_bez_kazne(self):
        r = motor.kontrolni_skup(sirovo_stanje(potroseno=24.0))["rezultat"]
        self.assertFalse(r["budzet_prekoracen"])

    def test_sum_zaokruzivanja_nije_prekoracenje(self):
        r = motor.kontrolni_skup(sirovo_stanje(24.0000000001, 150.0000000001))["rezultat"]
        self.assertFalse(r["budzet_prekoracen"])
        self.assertFalse(r["rok_prekoracen"])

    def test_stvarno_prekoracenje_na_devetoj_decimali(self):
        r = motor.kontrolni_skup(sirovo_stanje(24.000000001, 150.000000001))["rezultat"]
        self.assertTrue(r["budzet_prekoracen"])
        self.assertTrue(r["rok_prekoracen"])

    def test_najmanje_nula(self):
        izmene = {
            1: {"ishod": motor.DORADA},
            5: {"ishod": motor.TIHI_NEUSPEH},
            6: {"ishod": motor.TIHI_NEUSPEH},
            8: {"ishod": motor.TIHI_NEUSPEH},
        }
        r = motor.kontrolni_skup(sirovo_stanje(99.0, 999.0, izmene))["rezultat"]
        self.assertEqual(r["poeni"], 0)
        self.assertEqual(r["ocena"], "пожар")

    def test_ocene_na_granicama(self):
        slucajevi = [
            (100, "одличан оркестратор"),
            (85, "одличан оркестратор"),
            (84, "солидан"),
            (65, "солидан"),
            (64, "скуп учитељ"),
            (40, "скуп учитељ"),
            (39, "пожар"),
            (0, "пожар"),
        ]
        for poeni, ocena in slucajevi:
            with self.subTest(poeni=poeni):
                self.assertEqual(motor.oceni(poeni), ocena)

    def test_dodaci_ulaze_u_potroseno_i_minute(self):
        izmene = {5: {"ishod": motor.TIHI_NEUSPEH, "cena": 1.0, "minuti": 10.0}}
        kraj = motor.kontrolni_skup(sirovo_stanje(5.0, 50.0, izmene))
        self.assertAlmostEqual(kraj["potroseno"], kraj["rezultat"]["ukupna_cena"], places=TACNOST)
        self.assertAlmostEqual(kraj["minuti"], kraj["rezultat"]["ukupni_minuti"], places=TACNOST)
        self.assertAlmostEqual(kraj["potroseno"], 8.0, places=TACNOST)
        self.assertAlmostEqual(kraj["minuti"], 60.0, places=TACNOST)

    def test_tacno_pogodjen_limit_nije_negativna_nula(self):
        javno = motor.javni_prikaz(motor.kontrolni_skup(sirovo_stanje(24.0, 150.0)))
        for mera in (javno["budzet"], javno["rok"]):
            self.assertEqual(mera["preostalo"], 0.0)
            self.assertEqual(math.copysign(1, mera["preostalo"]), 1.0)


class LekcijeTests(SimpleTestCase):
    TIHA = ("Ако је грешка тиха, задатак остаје највишем разреду.", "4.2")
    OPUS = ("Најскупљи модел није увек најбољи избор.", "3.2")
    MAX = ("Изнад нивоа high цена расте, а квалитет не.", "3.3")
    SVE = ("Превише контекста квари резултат исто као премало.", "3.1")
    PEDESET = ("Више агената не значи јефтиније.", "5.3")

    def lekcije(self, izmene=None):
        return [(l["tekst"], l["odeljak"]) for l in motor.lekcije(sirovo_stanje(izmene=izmene))]

    def test_bez_uslova_nema_lekcija(self):
        self.assertEqual(self.lekcije(), [])

    def test_svaka_lekcija_ukljuceno(self):
        slucajevi = [
            ("tih neuspeh", {5: {"ishod": motor.TIHI_NEUSPEH}}, self.TIHA),
            ("opus na tezini 1", {2: {"izbori": izbori("opus")}}, self.OPUS),
            ("max", {7: {"izbori": izbori("haiku", "max")}}, self.MAX),
            ("sve", {7: {"izbori": izbori("haiku", kontekst="sve")}}, self.SVE),
            ("pedeset", {7: {"izbori": izbori("haiku", podela="pedeset")}}, self.PEDESET),
        ]
        for ime, izmene, ocekivana in slucajevi:
            with self.subTest(ime=ime):
                self.assertEqual(self.lekcije(izmene), [ocekivana])

    def test_svaka_lekcija_iskljuceno(self):
        slucajevi = [
            ("dorada nije tih neuspeh", {4: {"ishod": motor.DORADA}}),
            ("opus na tezini 2", {4: {"izbori": izbori("opus")}}),
            ("opus na tezini 3", {5: {"izbori": izbori("opus")}}),
            ("nivo high", {1: {"izbori": izbori("haiku", "high")}}),
            ("nivo low", {1: {"izbori": izbori("haiku", "low")}}),
            ("kontekst malo", {1: {"izbori": izbori("haiku", kontekst="malo")}}),
            ("tri agenta", {1: {"izbori": izbori("haiku", podela="tri")}}),
        ]
        for ime, izmene in slucajevi:
            with self.subTest(ime=ime):
                self.assertEqual(self.lekcije(izmene), [])

    def test_sve_lekcije_redom_iz_tabele(self):
        izmene = {
            1: {"izbori": izbori("opus", "max", "sve", "pedeset")},
            5: {"ishod": motor.TIHI_NEUSPEH},
        }
        self.assertEqual(
            self.lekcije(izmene), [self.TIHA, self.OPUS, self.MAX, self.SVE, self.PEDESET]
        )


class CistocaMotoraTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        izvor = pathlib.Path(motor.__file__).read_text(encoding="utf-8")
        cls.stablo = ast.parse(izvor)

    def uvozi(self):
        imena = set()
        for cvor in ast.walk(self.stablo):
            if isinstance(cvor, ast.Import):
                imena.update(a.name.split(".")[0] for a in cvor.names)
            elif isinstance(cvor, ast.ImportFrom) and cvor.level == 0:
                imena.add((cvor.module or "").split(".")[0])
        return imena

    def test_motor_cist(self):
        uvozi = self.uvozi()
        self.assertTrue(uvozi, "provera mora da vidi bar jedan uvoz")
        self.assertIn("random", uvozi)
        self.assertNotIn("django", uvozi)
        self.assertFalse(uvozi & {"time", "datetime", "secrets", "uuid"})

    def test_nema_brojeva_u_motoru(self):
        brojevi = [
            cvor.value
            for cvor in ast.walk(self.stablo)
            if isinstance(cvor, ast.Constant)
            and isinstance(cvor.value, (int, float))
            and not isinstance(cvor.value, bool)
        ]
        self.assertTrue(brojevi, "provera mora da vidi bar jedan broj")
        self.assertEqual([b for b in brojevi if b not in (0, 1)], [])

    def test_koristi_samo_random_random(self):
        pozivi = {
            cvor.attr
            for cvor in ast.walk(self.stablo)
            if isinstance(cvor, ast.Attribute)
            and isinstance(cvor.value, ast.Name)
            and cvor.value.id == "random"
        }
        self.assertEqual(pozivi, {"Random"})


class BalansTests(SimpleTestCase):
    SEMENA = 5000

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.srednje = {}
        for strategija in (po_tezini, sve_opus, sve_haiku_low_malo):
            zbir = sum(
                odigraj_celu(str(i), strategija)["rezultat"]["poeni"] for i in range(cls.SEMENA)
            )
            cls.srednje[strategija.__name__] = zbir / cls.SEMENA

    def test_balans_poredak_5000_semena(self):
        self.assertGreater(self.srednje["po_tezini"], self.srednje["sve_opus"])
        self.assertGreater(self.srednje["sve_opus"], self.srednje["sve_haiku_low_malo"])

    def test_balans_srednje_vrednosti(self):
        ocekivano = {"po_tezini": 72.8, "sve_opus": 68.0, "sve_haiku_low_malo": 20.8}
        for ime, vrednost in ocekivano.items():
            with self.subTest(strategija=ime):
                self.assertAlmostEqual(self.srednje[ime], vrednost, delta=1.5)
