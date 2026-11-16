"""Pravila igre nad cistim motorom, bez servera.

Ocekivani brojevi su prepisani iz MVP.md i izracunati rucno, ne citaju se iz parametri.py:
test koji ocekivanje uzima iz koda koji proverava ne moze da padne.
"""

import ast
import copy
import hashlib
import json
import math
import pathlib
import random
import secrets
import unicodedata
from unittest import mock

from django.test import SimpleTestCase

from igra import imena, motor
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


def odigraj_celu(seme, strategija, pravila=None):
    """Cela partija; pravila je verzija upisana posle nova_igra (None: ona koju nova_igra daje)."""
    stanje = motor.nova_igra(seme)
    if pravila is not None:
        stanje["pravila"] = pravila
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


# Pravila imena, plan 10.4 i 10.7. Vrednosti su ulaz kakav stize u JSON-u (pre NFC).
PRIHVACENA_IMENA = {
    "jedno slovo": "А",
    "20 cirilicnih": "Ш" * 20,
    "ime i prezime": "Пера Перић",
    "dva razmaka u sredini": "Пера  Перић",
    "emoji": "😀",
    "20 kodnih tacaka sa emoji": "😀😀" + "Ж" * 18,
    "NFD Đorđe Šćepanović": unicodedata.normalize("NFD", "Đorđe Šćepanović"),
    # 20 znakova posle NFC, 40 pre: duzina se meri posle normalizacije.
    "NFD 20 x Š": unicodedata.normalize("NFD", "Š" * 20),
    # U+FE0F posle simbola, cifre ili interpunkcije (plan 10.4, tacka 7).
    "srce sa FE0F": "❤️",
    "taster 1": "1️⃣",
    "taster #": "#️⃣",
    "taster *": "*️⃣",
    "TM sa FE0F": "™️",
    "dva uzvika sa FE0F": "‼️",
    "copyright sa FE0F": "©️",
    "ime i srce": "Пера ❤️",
    "boja koze": "👍🏽",
    "zastava": "🇷🇸",
    # Najvise 2 uzastopna kombinujuca znaka (tacka 8).
    "Z + 2 x U+0346": "Z" + "͆" * 2,
    "dva puta po 2 kombinujuca": "Z͆͆a͓͓",
}
FE0F = "️"
# Plan 10.4, tacka 7: 269 znakova; ocekivanje je prepisano iz plana, ne cita se iz imena.py.
NEVIDLJIVI_OPSEZI = [
    (0x034F, 0x034F), (0x115F, 0x1160), (0x17B4, 0x17B5), (0x180B, 0x180F), (0x2800, 0x2800),
    (0x3164, 0x3164), (0xFE00, 0xFE0F), (0xFFA0, 0xFFA0), (0xE0100, 0xE01EF),
]
NEVIDLJIVI_ZNACI = [chr(t) for prva, poslednja in NEVIDLJIVI_OPSEZI for t in range(prva, poslednja + 1)]


def nevidljivi_polozaji(znak):
    """Znak sam, na kraju i usred imena (vec NFC)."""
    return {
        "sam": znak,
        "kraj": unicodedata.normalize("NFC", "Пера" + znak),
        "sredina": unicodedata.normalize("NFC", "Пе" + znak + "ра"),
    }
ODBIJENA_IMENA = {
    "prazno": "",
    "razmak": " ",
    "razmak na pocetku": " Пера",
    "razmak na kraju": "Пера ",
    "21 znak": "Ш" * 21,
    "novi red": "Пе\nра",
    "tab": "Пе\tра",
    "U+200B": "Пе​ра",
    "ZWJ U+200D": "Пе‍ра",
    "emoji sa ZWJ": "👩‍💻",
    "U+00A0": "Пе ра",
    "U+202E": "‮Пера",
    "U+2028": "Пе ра",
    "usamljen surogat": "\ud800",
    "pocetni U+0301": "́Пера",
    # U+FE0F posle slova, razmaka, drugog FE0F, na pocetku; i posle slova kategorije Lo/Ll (ℹ).
    "FE0F posle slova na kraju": "Пера️",
    "FE0F posle razmaka": "Пера ️",
    "FE0F sam": "️",
    "FE0F dvaput": "❤️️",
    "FE0F posle i": "ℹ️",
    "FE0F usred reci": "Пе️ра",
    "Hangul popunjivac sam": "ㅤ",
    "Hangul popunjivac usred": "fuㅤck",
    "prazan Braille": "⠀",
    "U+034F usred": "Пе͏ра",
    "Z + 3 x U+0346": "Z" + "͆" * 3,
    "taster sa jos jednim kombinujucim": "1️⃣͆",
}


def sirovo_stanje(potroseno=0.0, minuti=0.0, izmene=None, pravila=None):
    """Stanje posle 8. kruga, pred kontrolni skup; svi redovi su uspeh dok izmena ne kaze drugo.

    Bez pravila stanje nema kljuc "pravila", kao sesija pre verzija: boduje se po verziji 1.
    """
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
    stanje = {
        "seme": "s",
        "krug": 8,
        "zavrsena": False,
        "potroseno": potroseno,
        "minuti": minuti,
        "istorija": istorija,
        "rezultat": None,
    }
    if pravila is not None:
        stanje["pravila"] = pravila
    return stanje


# Srpski izvor (msgid) po kljucu, prepisan iz MVP.md i plana 12.3; ne cita se iz parametri.py.
ZADACI_SR = {
    "prevod": "Превод почетне стране",
    "sablon": "Шаблон листе и форме",
    "css": "CSS и прилагођавање телефону",
    "crud": "CRUD прикази",
    "model": "Модел података и миграција",
    "prava": "Провера права приступа",
    "testovi": "Аутоматски тестови",
    "revizija": "Безбедносна ревизија",
}
OCENE_SR = {
    "odlican": "одличан оркестратор",
    "solidan": "солидан",
    "skup": "скуп учитељ",
    "pozar": "пожар",
}
LEKCIJE_SR = {
    "tiha": "Ако је грешка тиха, задатак остаје највишем разреду.",
    "opus_lako": "Најскупљи модел није увек најбољи избор.",
    "max": "Изнад нивоа high цена расте, а квалитет не.",
    "sve": "Превише контекста квари резултат исто као премало.",
    "pedeset": "Више агената не значи јефтиније.",
}
NAPOMENA_SR = (
    "Цене и нивои размишљања су стварни подаци; вероватноће, казне и "
    "поени су измишљени параметри игре."
)


def staro_zavrseno(stanje, sa_napomenom=False):
    """Zavrsena partija kako ju je sesija cuvala pre kljuceva (plan 12.4): srpski tekst umesto kljuca."""
    staro = copy.deepcopy(stanje)
    rezultat = staro["rezultat"]
    rezultat["ocena"] = OCENE_SR[rezultat["ocena"]]
    for greska in rezultat["tihe_greske"]:
        greska["zadatak"] = ZADACI_SR[greska["zadatak"]]
    rezultat["lekcije"] = [
        {"tekst": LEKCIJE_SR[l["oznaka"]], "odeljak": l["odeljak"]} for l in rezultat["lekcije"]
    ]
    if sa_napomenom:
        rezultat["napomena"] = NAPOMENA_SR
    return staro


class ParametriTests(SimpleTestCase):
    def test_redosled_zadataka(self):
        ocekivano = [
            ("prevod", "Превод почетне стране", 1, False),
            ("sablon", "Шаблон листе и форме", 1, False),
            ("css", "CSS и прилагођавање телефону", 1, False),
            ("crud", "CRUD прикази", 2, False),
            ("model", "Модел података и миграција", 3, True),
            ("prava", "Провера права приступа", 3, True),
            ("testovi", "Аутоматски тестови", 2, False),
            ("revizija", "Безбедносна ревизија", 3, True),
        ]
        dobijeno = [(z["kljuc"], z["naziv"], z["tezina"], z["tih"]) for z in p.ZADACI]
        self.assertEqual(dobijeno, ocekivano)

    def test_ocene_kljucevi_i_izvor(self):
        self.assertEqual(p.OCENE, [(85, "odlican"), (65, "solidan"), (40, "skup"), (0, "pozar")])
        self.assertEqual(p.NAZIVI_OCENA, OCENE_SR)

    def test_lekcije_kljucevi_tekst_odeljak(self):
        self.assertEqual(
            {kljuc: (l["tekst"], l["odeljak"]) for kljuc, l in p.LEKCIJE.items()},
            {
                "tiha": (LEKCIJE_SR["tiha"], "4.2"),
                "opus_lako": (LEKCIJE_SR["opus_lako"], "3.2"),
                "max": (LEKCIJE_SR["max"], "3.3"),
                "sve": (LEKCIJE_SR["sve"], "3.1"),
                "pedeset": (LEKCIJE_SR["pedeset"], "5.3"),
            },
        )
        # Redosled iz tabele MVP 3 je redosled na zavrsnom ekranu.
        self.assertEqual(list(p.LEKCIJE), ["tiha", "opus_lako", "max", "sve", "pedeset"])

    def test_parametri_cist(self):
        # Plan 12.3: tekst je oznacen lokalnom gettext_noop, bez uvoza Django-a.
        def uvozi(izvor):
            imena = set()
            for cvor in ast.walk(ast.parse(izvor)):
                if isinstance(cvor, ast.Import):
                    imena.update(a.name.split(".")[0] for a in cvor.names)
                elif isinstance(cvor, ast.ImportFrom):
                    imena.add((cvor.module or "").split(".")[0])
            return imena

        # Kontrola: detektor vidi uvoz Django-a u oba oblika.
        self.assertEqual(uvozi("from django.utils.translation import gettext_noop"), {"django"})
        self.assertEqual(uvozi("import django.utils.translation as t"), {"django"})
        stablo = ast.parse(pathlib.Path(p.__file__).read_text(encoding="utf-8"))
        self.assertEqual(uvozi(pathlib.Path(p.__file__).read_text(encoding="utf-8")), set())
        lokalne = [c.name for c in stablo.body if isinstance(c, ast.FunctionDef)]
        self.assertIn("gettext_noop", lokalne)
        self.assertEqual(p.gettext_noop("тест"), "тест")

    def test_osnovne_konstante(self):
        self.assertEqual(
            (p.KRUGOVA, p.BUDZET, p.ROK, p.POCETNI_POENI, p.MIN_POENI), (8, 24, 150, 100, 0)
        )

    def test_kazne_po_verziji(self):
        # Plan 13.1: verzija 1 do 2026-11-11, verzija 2 zahtev klijenta 2026-11-11.
        self.assertEqual(
            p.KAZNE,
            {
                1: {"dorada": 5, "tiha": 25, "rok": 20,
                    "budzet_po_koraku": 30, "budzet_korak_procenata": 10, "budzet_maks": 30},
                2: {"dorada": 5, "tiha": 35, "rok": 20,
                    "budzet_po_koraku": 10, "budzet_korak_procenata": 10, "budzet_maks": 50},
            },
        )
        self.assertEqual((p.PRAVILA_STARA, p.PRAVILA_TEKUCA), (1, 2))
        self.assertEqual((p.PROCENAT, p.JEDINICA_POREDJENJA), (100, 1000000000))
        # Kazne se citaju samo po verziji; stare konstante bi se tiho primenile na obe verzije.
        for ime in ("KAZNA_DORADA", "KAZNA_TIHA", "KAZNA_BUDZET", "KAZNA_ROK"):
            with self.subTest(ime=ime):
                self.assertFalse(hasattr(p, ime))

    def test_kazne_tacno_za_poznate_verzije(self):
        # Revizija 2026-11-11: CHECK igra_pravila_poznata prihvata PRAVILA_STARA..PRAVILA_TEKUCA, ne kljuceve
        # KAZNE. Verzija sa kaznama van granica pada pri cuvanju (IntegrityError); poznata verzija bez kazni
        # rusi motor.kontrolni_skup za svoju partiju (KeyError). Namerno brisanje KAZNE[1] menja ovaj test, ne granice.
        self.assertEqual(sorted(p.KAZNE), list(range(p.PRAVILA_STARA, p.PRAVILA_TEKUCA + 1)))

    def test_kazne_budzeta_konacne(self):
        # tekstovi._moguce_kazne_budzeta korakuje od budzet_po_koraku do budzet_maks: korak <= 0 je
        # beskonacna petlja na svakoj strani (pocetna, deljeno). Motor deli procenat sa budzet_korak_procenata.
        self.assertIn(p.PRAVILA_TEKUCA, p.KAZNE)
        for verzija, kazne in p.KAZNE.items():
            with self.subTest(verzija=verzija):
                self.assertGreater(kazne["budzet_po_koraku"], 0)
                self.assertGreater(kazne["budzet_korak_procenata"], 0)
                self.assertGreaterEqual(kazne["budzet_maks"], 0)

    def test_napomena_doslovno(self):
        self.assertEqual(
            p.NAPOMENA,
            "Цене и нивои размишљања су стварни подаци; вероватноће, казне и "
            "поени су измишљени параметри игре.",
        )

    def test_statusi_kljucevi(self):
        # Pravilo 1: uspeh i tih neuspeh nose isti kljuc; tekst je srpski izvor za prevod.
        self.assertEqual(p.STATUS_GOTOVO, "gotovo")
        self.assertEqual(p.STATUS_DORADA, "dorada")
        self.assertEqual(
            p.NAZIVI_STATUSA, {"gotovo": "готово", "dorada": "враћено на дораду"}
        )

    def test_konstante_rang(self):
        self.assertEqual((p.IME_MAKS, p.RANG_MESTA, p.IME_MAKS_KOMBINUJUCIH), (20, 10, 2))

    def test_konstante_deljenje(self):
        # MVP 3: 30 dana; plan 11.2: 16 bajtova (128 bita) daju 22 znaka base64url.
        self.assertEqual(
            (p.DELJENJE_DANA, p.DELJENJE_TOKEN_BAJTOVA, p.DELJENJE_TOKEN_DUZINA), (30, 16, 22)
        )
        duzine = {len(secrets.token_urlsafe(16)) for _ in range(200)}
        self.assertEqual(duzine, {p.DELJENJE_TOKEN_DUZINA})


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
        self.assertEqual(greska["zadatak"], "model")
        self.assertAlmostEqual(greska["dodatak_cena"], 12.96, places=TACNOST)
        self.assertAlmostEqual(greska["dodatak_minuti"], 30.0, places=TACNOST)
        self.assertTrue(r["budzet_prekoracen"])
        self.assertTrue(r["rok_prekoracen"])
        # Pravila 2: 32,40 $ je 35 % preko budzeta, 4 zapoceta koraka; 100 - 35 - 40 - 20
        self.assertEqual((r["budzet_procenat"], r["kazna_budzet"]), (35, 40))
        self.assertEqual(r["poeni"], 5)
        self.assertEqual(r["ocena"], "pozar")

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
        self.assertEqual(r["ocena"], "odlican")
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
        self.assertEqual(r["ocena"], "pozar")

    def test_ocene_na_granicama(self):
        # Motor vraca kljuc ocene (plan 12.3); tekst je u NAZIVI_OCENA i prevodi ga tekstovi.py.
        slucajevi = [
            (100, "odlican"),
            (85, "odlican"),
            (84, "solidan"),
            (65, "solidan"),
            (64, "skup"),
            (40, "skup"),
            (39, "pozar"),
            (0, "pozar"),
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


# Plan 13.1: (opis, ukupna cena, procenat, kazna pravila 1, kazna pravila 2); prepisano iz plana.
GRANICE_BUDZETA = [
    ("tacno 24", 24.0, 0, 0, 0),
    ("24,000000001", 24.000000001, 1, 30, 10),
    ("0,01 %", 24.0024, 1, 30, 10),
    ("tacno 10 %", 26.40, 10, 30, 10),
    ("10,01 %", 26.4024, 11, 30, 20),
    ("tacno 20 %", 28.80, 20, 30, 20),
    ("tacno 40 %", 33.60, 40, 30, 40),
    ("41 %", 33.84, 41, 30, 50),
    ("200 %", 72.0, 200, 30, 50),
]
SEME_JEDNA_TIHA = [motor.USPEH] * 4 + [motor.TIHI_NEUSPEH] + [motor.USPEH] * 3
NOVI_KLJUCEVI_REZULTATA = {"budzet_procenat", "kazna_budzet"}


def bez_verzije(stanje):
    """Stanje kakvo je sesija cuvala pre verzija: bez "pravila" i bez novih kljuceva rezultata."""
    staro = {k: copy.deepcopy(v) for k, v in stanje.items() if k != "pravila"}
    if staro["rezultat"] is not None:
        staro["rezultat"] = {
            k: v for k, v in staro["rezultat"].items() if k not in NOVI_KLJUCEVI_REZULTATA
        }
    return staro


class PravilaTests(SimpleTestCase):
    """Verzije pravila bodovanja (plan 13.1, 13.7 T-M)."""

    def rezultat(self, potroseno=0.0, minuti=0.0, izmene=None, pravila=None):
        return motor.kontrolni_skup(sirovo_stanje(potroseno, minuti, izmene, pravila))["rezultat"]

    def test_granice_budzeta_obe_verzije(self):
        for opis, cena, procenat, kazna_v1, kazna_v2 in GRANICE_BUDZETA:
            for pravila, kazna in ((1, kazna_v1), (2, kazna_v2)):
                with self.subTest(opis=opis, pravila=pravila):
                    r = self.rezultat(potroseno=cena, pravila=pravila)
                    self.assertEqual(r["budzet_prekoracen"], procenat > 0)
                    self.assertEqual((r["budzet_procenat"], r["kazna_budzet"]), (procenat, kazna))
                    self.assertEqual(r["poeni"], 100 - kazna)
        # Pravila 1: svako prekoracenje je tacno 30, kao pre verzija.
        self.assertEqual({g[3] for g in GRANICE_BUDZETA}, {0, 30})

    def test_bez_kljuca_je_verzija_1(self):
        r = self.rezultat(potroseno=33.84)
        self.assertEqual((r["budzet_procenat"], r["kazna_budzet"], r["poeni"]), (41, 30, 70))

    def test_28_80_u_dva_redosleda_tacno_20(self):
        # Cene partije "po tezini" sa doradom na tezini 1 i tihom greskom na tezini 3, pa dodatak.
        haiku = motor.racun(1, izbori("haiku"))["cena"]
        sonnet = motor.racun(2, izbori("sonnet", podela="tri"))["cena"]
        opus = motor.racun(3, izbori("opus"))["cena"]
        delovi = [haiku * 2, haiku, haiku, sonnet, opus, opus, sonnet, opus, opus * 3]
        napred = 0.0
        for deo in delovi:
            napred += deo
        nazad = 0.0
        for deo in reversed(delovi):
            nazad += deo
        # Kontrola: redosled zaista menja zbir, a racun u decimalnim brojevima bi dao 21 % i jos korak.
        self.assertNotEqual(napred, nazad)
        self.assertEqual(
            max(math.ceil((z - 24) / 24 * 100) for z in (napred, nazad)), 21
        )
        for opis, zbir in (("napred", napred), ("nazad", nazad)):
            with self.subTest(redosled=opis):
                r = self.rezultat(potroseno=zbir, pravila=2)
                self.assertEqual((r["budzet_procenat"], r["kazna_budzet"]), (20, 20))

    def test_prava_partija_po_tezini_28_80(self):
        seme = nadji_seme(
            po_tezini,
            lambda i: i.count(motor.TIHI_NEUSPEH) == 1
            and i.count(motor.DORADA) == 1
            and motor.DORADA in i[:3],
        )
        r = odigraj_celu(seme, po_tezini, pravila=2)["rezultat"]
        self.assertAlmostEqual(r["ukupna_cena"], 28.80, places=TACNOST)
        self.assertEqual((r["budzet_procenat"], r["kazna_budzet"]), (20, 20))
        self.assertFalse(r["rok_prekoracen"])
        # 100 - 5 - 35 - 20
        self.assertEqual(r["poeni"], 40)
        v1 = odigraj_celu(seme, po_tezini, pravila=1)["rezultat"]
        # 100 - 5 - 25 - 30
        self.assertEqual((v1["budzet_procenat"], v1["kazna_budzet"], v1["poeni"]), (20, 30, 40))

    def test_tiha_dorada_rok_po_verziji(self):
        dve_tihe = {5: {"ishod": motor.TIHI_NEUSPEH}, 6: {"ishod": motor.TIHI_NEUSPEH}}
        for pravila, poeni in ((1, 50), (2, 30)):
            with self.subTest(pravila=pravila):
                r = self.rezultat(izmene=dve_tihe, pravila=pravila)
                self.assertEqual(r["poeni"], poeni)
                self.assertEqual((r["budzet_procenat"], r["kazna_budzet"]), (0, 0))
        # Dorada -5 i rok -20 su isti u obe verzije.
        dorada = {1: {"ishod": motor.DORADA}}
        for pravila in (1, 2):
            with self.subTest(pravila=pravila, dorada_i_rok=True):
                self.assertEqual(self.rezultat(minuti=150.1, izmene=dorada, pravila=pravila)["poeni"], 75)

    def test_nova_igra_tekuca_pravila(self):
        stanje = motor.nova_igra("1")
        self.assertEqual(stanje["pravila"], 2)
        self.assertEqual(motor.pravila(stanje), 2)
        self.assertEqual(motor.pravila(bez_verzije(stanje)), 1)
        kraj = odigraj_celu("1", sve_opus)
        self.assertEqual(kraj["pravila"], 2)
        self.assertEqual(json.loads(json.dumps(kraj)), kraj)

    def test_kontrolni_skup_bira_skup_po_stanju(self):
        seme = nadji_seme(sve_opus, lambda i: i == SEME_JEDNA_TIHA)
        # Partija zapoceta pre verzija (sesija bez kljuca) igra se do kraja po verziji 1.
        stara = bez_verzije(motor.nova_igra(seme))
        for krug in KRUGOVI:
            stara = motor.odigraj_potez(stara, krug, OPUS_HIGH)
        rezultati = {
            "pravila 1": odigraj_celu(seme, sve_opus, pravila=1)["rezultat"],
            "pravila 2": odigraj_celu(seme, sve_opus, pravila=2)["rezultat"],
            "bez kljuca": stara["rezultat"],
        }
        # 32,40 $ je 35 %. Pravila 1: 100 - 25 - 30 - 20; pravila 2: 100 - 35 - 40 - 20.
        ocekivano = {"pravila 1": (25, 30), "pravila 2": (5, 40), "bez kljuca": (25, 30)}
        for opis, (poeni, kazna) in ocekivano.items():
            with self.subTest(opis=opis):
                r = rezultati[opis]
                self.assertEqual((r["poeni"], r["budzet_procenat"], r["kazna_budzet"]), (poeni, 35, kazna))
        self.assertNotIn("pravila", stara)

    def test_za_cuvanje_vraca_verziju(self):
        for pravila in (1, 2):
            with self.subTest(pravila=pravila):
                stanje = odigraj_celu("1", sve_opus, pravila=pravila)
                self.assertEqual(motor.za_cuvanje(stanje)["pravila"], pravila)
        # Stara zavrsena sesija sacuvana posle isporuke: red verzije 1.
        self.assertEqual(motor.za_cuvanje(bez_verzije(odigraj_celu("1", sve_opus)))["pravila"], 1)

    def test_javni_zavrsni_stari_rezultat_null(self):
        seme = nadji_seme(sve_opus, lambda i: i == SEME_JEDNA_TIHA)
        novo = odigraj_celu(seme, sve_opus)
        snimak = motor.za_deljenje(novo)
        self.assertEqual((snimak["budzet_procenat"], snimak["kazna_budzet"]), (35, 40))
        # Snimak iz baze pre 2026-11-11 nema nove kljuceve: prikaz ih daje kao null, bez greske.
        stari = json.loads(json.dumps({k: v for k, v in snimak.items() if k not in NOVI_KLJUCEVI_REZULTATA}))
        prikaz = motor.deljeni_prikaz(stari)
        self.assertEqual(set(prikaz), set(snimak))
        self.assertEqual({k: prikaz[k] for k in NOVI_KLJUCEVI_REZULTATA}, {"budzet_procenat": None, "kazna_budzet": None})
        self.assertEqual({k: v for k, v in prikaz.items() if k not in NOVI_KLJUCEVI_REZULTATA}, stari)
        # Isto i za staru zavrsenu sesiju.
        javni = motor.javni_prikaz(motor.nadogradi(bez_verzije(novo)))["zavrsni"]
        self.assertIsNone(javni["budzet_procenat"])
        self.assertIsNone(javni["kazna_budzet"])
        self.assertTrue(javni["budzet_prekoracen"])

    def test_za_deljenje_jednak_javnom_obe_verzije(self):
        for pravila in (1, 2):
            for strategija in (sve_opus, po_tezini, sve_haiku_low_malo):
                stanje = odigraj_celu("seme-deljenje-pravila", strategija, pravila)
                with self.subTest(pravila=pravila, strategija=strategija.__name__):
                    javni = motor.javni_prikaz(stanje)["zavrsni"]
                    self.assertEqual(motor.za_deljenje(stanje), javni)
                    self.assertNotIn("pravila", javni)
                    self.assertIsInstance(javni["budzet_procenat"], int)
                    self.assertIsInstance(javni["kazna_budzet"], int)


class LekcijeTests(SimpleTestCase):
    # Motor vraca oznaku lekcije i odeljak (plan 12.3); tekst je u parametri.LEKCIJE.
    TIHA = ("tiha", "4.2")
    OPUS = ("opus_lako", "3.2")
    MAX = ("max", "3.3")
    SVE = ("sve", "3.1")
    PEDESET = ("pedeset", "5.3")

    def lekcije(self, izmene=None):
        dobijeno = motor.lekcije(sirovo_stanje(izmene=izmene))
        for l in dobijeno:
            self.assertEqual(set(l), {"oznaka", "odeljak"})
        return [(l["oznaka"], l["odeljak"]) for l in dobijeno]

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


class ImenaTests(SimpleTestCase):
    """Pravila imena i kljuc za sifarnik, bez servera (plan 10.4)."""

    def kljucevi(self, ulazi):
        return {ulaz: imena.kljuc_imena(ulaz) for ulaz in ulazi}

    def proveri_kljuc(self, ulazi, ocekivano):
        self.assertEqual(self.kljucevi(ulazi), {ulaz: ocekivano for ulaz in ulazi})

    def test_ime_ispravno_tabela(self):
        # Pozivalac (prikaz) radi NFC pre provere; ovde isto.
        for opis, ime in PRIHVACENA_IMENA.items():
            with self.subTest(prihvaceno=opis):
                self.assertTrue(imena.ime_ispravno(unicodedata.normalize("NFC", ime)))
        for opis, ime in ODBIJENA_IMENA.items():
            with self.subTest(odbijeno=opis):
                self.assertFalse(imena.ime_ispravno(unicodedata.normalize("NFC", ime)))

    def test_s_iz_svih_pisama(self):
        self.proveri_kljuc(["Ш", "ш", "Š", "š", "S", "s"], "s")

    def test_digrafi(self):
        self.proveri_kljuc(["Љ", "љ", "Lj", "LJ", "lj", "ǉ", "Ǉ"], "lj")
        self.proveri_kljuc(["Њ", "њ", "Nj", "nj", "ǌ"], "nj")
        self.proveri_kljuc(["Џ", "џ", "Dž", "DŽ", "dž", "ǆ", "ǅ"], "dz")
        self.proveri_kljuc(["Ђ", "ђ", "Đ", "đ", "Dj", "dj"], "dj")

    def test_c_i_z(self):
        self.proveri_kljuc(["Ћ", "ћ", "Ч", "ч", "Ц", "ц", "ć", "Ć", "č", "Č", "c"], "c")
        self.proveri_kljuc(["Ж", "ж", "ž", "Ž", "З", "з", "z"], "z")

    def test_cela_azbuka(self):
        self.assertEqual(
            imena.kljuc_imena("АБВГДЂЕЖЗИЈКЛЉМНЊОПРСТЋУФХЦЧЏШ"),
            "abvgddjezzijklljmnnjoprstcufhccdzs",
        )
        self.assertEqual(imena.kljuc_imena("й"), "i")

    def test_razmaci_i_interpunkcija(self):
        self.assertEqual(imena.kljuc_imena("П е-р.а"), "pera")
        self.assertEqual(imena.kljuc_imena("Пера Перић"), "peraperic")
        self.assertEqual(imena.kljuc_imena("P E\tR　A!"), "pera")
        self.assertEqual(imena.kljuc_imena("Пера 2"), "pera2")

    def test_nfkd_oblici(self):
        self.assertEqual(imena.kljuc_imena("ＰＥＲＡ"), "pera")
        self.assertEqual(imena.kljuc_imena("ß"), "ss")
        self.assertEqual(imena.kljuc_imena("ﬁ"), "fi")
        nfd = unicodedata.normalize("NFD", "Šćepan")
        self.assertEqual(imena.kljuc_imena(nfd), imena.kljuc_imena("Šćepan"))
        self.assertEqual(imena.kljuc_imena(nfd), "scepan")

    def test_samo_simboli_prazan_kljuc(self):
        for ime in ("😀", "!?", "- . -", "👩‍💻", ""):
            with self.subTest(ime=ime):
                self.assertEqual(imena.kljuc_imena(ime), "")

    def test_idempotentno(self):
        ulazi = ["Пера Перић", "ЏЕЈН Đurđević", "ＰＥＲＡ", "Ljubiša", "ß-ǆ", "П е-р.а"]
        for ulaz in ulazi:
            with self.subTest(ulaz=ulaz):
                kljuc = imena.kljuc_imena(ulaz)
                self.assertTrue(kljuc)
                self.assertEqual(imena.kljuc_imena(kljuc), kljuc)

    def test_nevidljivi_spisak(self):
        self.assertEqual(len(NEVIDLJIVI_ZNACI), 269)
        self.assertEqual(imena.NEVIDLJIVI, frozenset(NEVIDLJIVI_ZNACI))

    def test_nevidljivi_odbijeni_svuda(self):
        # Svaki od 269, i U+FE0F: posle slova (kraj, sredina) i na pocetku se odbija.
        prosli = [
            (f"U+{ord(z):04X}", polozaj)
            for z in NEVIDLJIVI_ZNACI
            for polozaj, ime in nevidljivi_polozaji(z).items()
            if imena.ime_ispravno(ime)
        ]
        self.assertEqual(prosli, [])
        # Kontrola: isto ime bez nevidljivog prolazi.
        self.assertTrue(imena.ime_ispravno("Пера"))

    def test_kljuc_izbacuje_nevidljive(self):
        # Nezavisno od ime_ispravno: ranije sacuvan red ili rec u komandi ne zaobilazi sifarnik.
        odstupa = [
            f"U+{ord(z):04X}" for z in NEVIDLJIVI_ZNACI if imena.kljuc_imena("fu" + z + "ck") != "fuck"
        ]
        self.assertEqual(odstupa, [])
        self.assertEqual(imena.kljuc_imena("Пера ❤️"), "pera")
        self.assertEqual(imena.kljuc_imena("ㅤ⠀"), "")

    def test_selektor_emoji_samo_posle_simbola_cifre_interpunkcije(self):
        for ispred in ("❤", "1", "#", "*", "™", "‼", "©", "✌"):
            with self.subTest(ispred=ispred):
                self.assertIn(unicodedata.category(ispred)[0], "SNP")
                self.assertTrue(imena.ime_ispravno(ispred + FE0F))
        for ispred in ("ℹ", "П", "a", " ", "͆"):
            with self.subTest(ispred=ispred):
                self.assertFalse(imena.ime_ispravno("x" + ispred + FE0F))

    def test_kombinujuci_najvise_2_uzastopna(self):
        self.assertTrue(imena.ime_ispravno("Z" + "͆" * 2))
        self.assertFalse(imena.ime_ispravno("Z" + "͆" * 3))
        self.assertFalse(imena.ime_ispravno("Z" + "͆" * 19))
        # Brojac se vraca na nulu posle osnovnog znaka.
        self.assertTrue(imena.ime_ispravno("Z͆͆a͆͆b͆͆"))
        # Me (U+20E3) se broji kao M: FE0F + 20E3 su 2, treci je visak.
        self.assertTrue(imena.ime_ispravno("1️⃣"))
        self.assertFalse(imena.ime_ispravno("1️⃣͆"))
        # NFD dijakritici posle NFC nisu kombinujuci.
        self.assertTrue(imena.ime_ispravno(unicodedata.normalize("NFC", unicodedata.normalize("NFD", "Šćepanović"))))

    def test_imena_cist(self):
        stablo = ast.parse(pathlib.Path(imena.__file__).read_text(encoding="utf-8"))
        uvozi = set()
        for cvor in ast.walk(stablo):
            if isinstance(cvor, ast.Import):
                uvozi.update(a.name.split(".")[0] for a in cvor.names)
            elif isinstance(cvor, ast.ImportFrom) and cvor.level == 0:
                uvozi.add((cvor.module or "").split(".")[0])
        self.assertIn("unicodedata", uvozi, "provera mora da vidi bar jedan uvoz")
        self.assertEqual(uvozi, {"unicodedata"})


class RangMotorTests(SimpleTestCase):
    """Cuvanje rezultata u cistom motoru (plan 10.2)."""

    def test_za_cuvanje_iz_rezultata(self):
        seme = nadji_seme(
            sve_opus, lambda i: i == [motor.USPEH] * 4 + [motor.TIHI_NEUSPEH] + [motor.USPEH] * 3
        )
        stanje = odigraj_celu(seme, sve_opus)
        self.assertEqual(motor.za_cuvanje(stanje), {"poeni": 5, "ocena": "pozar", "pravila": 2})
        # Ocena se prenosi iz stanja, ne racuna se ponovo: par namerno nije uskladjen.
        izmenjeno = copy.deepcopy(stanje)
        izmenjeno["rezultat"]["poeni"] = 66
        izmenjeno["rezultat"]["ocena"] = "ocena-iz-stanja"
        self.assertEqual(
            motor.za_cuvanje(izmenjeno), {"poeni": 66, "ocena": "ocena-iz-stanja", "pravila": 2}
        )

    def test_za_cuvanje_nezavrsena(self):
        stanje = motor.nova_igra("1")
        with self.assertRaises(motor.IgraNijeZavrsena):
            motor.za_cuvanje(stanje)
        for krug in range(1, 8):
            stanje = motor.odigraj_potez(stanje, krug, OPUS_HIGH)
            with self.subTest(krug=krug), self.assertRaises(motor.IgraNijeZavrsena):
                motor.za_cuvanje(stanje)

    def test_za_cuvanje_vec_sacuvano(self):
        stanje = odigraj_celu("1", sve_opus)
        self.assertIsNone(motor.sacuvani_red(stanje))
        self.assertEqual(set(motor.za_cuvanje(stanje)), {"poeni", "ocena", "pravila"})
        for broj in (7, 0):
            with self.subTest(broj=broj):
                oznaceno = motor.oznaci_sacuvano(stanje, broj)
                self.assertEqual(motor.sacuvani_red(oznaceno), broj)
                with self.assertRaises(motor.VecSacuvano):
                    motor.za_cuvanje(oznaceno)

    def test_oznaci_sacuvano_ne_menja_ulaz(self):
        stanje = odigraj_celu("1", sve_opus)
        pre = copy.deepcopy(stanje)
        novo = motor.oznaci_sacuvano(stanje, 5)
        self.assertEqual(stanje, pre)
        self.assertNotIn("sacuvan", stanje)
        self.assertIsNot(novo, stanje)
        self.assertIsNot(novo["rezultat"], stanje["rezultat"])
        self.assertEqual({k: v for k, v in novo.items() if k != "sacuvan"}, pre)
        self.assertEqual(novo["sacuvan"], 5)
        self.assertEqual(json.loads(json.dumps(novo)), novo)

    def test_oznaka_partije_stabilna_bez_semena(self):
        seme = "seme-oznaka-3f9a"
        prva = motor.oznaka_partije(motor.nova_igra(seme))
        self.assertEqual(prva, motor.oznaka_partije(odigraj_celu(seme, sve_opus)))
        self.assertEqual(prva, hashlib.sha256(seme.encode("utf-8")).hexdigest())
        self.assertRegex(prva, r"^[0-9a-f]{64}$")
        self.assertNotIn(seme, prva)
        self.assertNotEqual(prva, motor.oznaka_partije(motor.nova_igra(seme + "x")))


class DeljenjeMotorTests(SimpleTestCase):
    """Snimak za deljeni link u cistom motoru (plan 11.2)."""

    # Kljucevi koji nikad ne smeju u snimak ni na deljenu stranu (plan 11.5).
    SKRIVENI = {"seme", "izbori", "ishod", "tih", "partija", "sansa", "tezina", "istorija"}

    def kljucevi(self, objekat):
        if isinstance(objekat, dict):
            for kljuc, vrednost in objekat.items():
                yield kljuc
                yield from self.kljucevi(vrednost)
        elif isinstance(objekat, list):
            for vrednost in objekat:
                yield from self.kljucevi(vrednost)

    def najduza(self):
        """Partija sa tihim greskama i lekcijama: snimak ima obe ugnezdene liste."""
        strategija = lambda krug: izbori("opus" if krug == 1 else "haiku", "max", "sve", "pedeset")
        # Dugacko prepoznatljivo seme: pretraga po vrednosti ne pogadja slucajno.
        stanje = next(
            s for s in (odigraj_celu(f"tajno-seme-deljenje-x9q-{i}", strategija) for i in range(2000))
            if ishodi(s).count(motor.TIHI_NEUSPEH) >= 2
        )
        self.assertGreaterEqual(len(stanje["rezultat"]["tihe_greske"]), 2)
        self.assertGreaterEqual(len(stanje["rezultat"]["lekcije"]), 2)
        return stanje

    def test_za_deljenje_nezavrsena(self):
        stanje = motor.nova_igra("1")
        with self.assertRaises(motor.IgraNijeZavrsena):
            motor.za_deljenje(stanje)
        for krug in range(1, 8):
            stanje = motor.odigraj_potez(stanje, krug, OPUS_HIGH)
            with self.subTest(krug=krug), self.assertRaises(motor.IgraNijeZavrsena):
                motor.za_deljenje(stanje)
        # Kontrola: posle 8. kruga snimak postoji.
        stanje = motor.odigraj_potez(stanje, 8, OPUS_HIGH)
        self.assertEqual(motor.za_deljenje(stanje)["poeni"], stanje["rezultat"]["poeni"])

    def test_deljeni_prikaz_jednak_javnom(self):
        provereno = 0
        for seme in [str(i) for i in range(40)] + ["seme-deljenje-a", "seme-deljenje-b"]:
            for strategija in (sve_opus, po_tezini, sve_haiku_low_malo):
                stanje = odigraj_celu(seme, strategija)
                javni = motor.javni_prikaz(stanje)["zavrsni"]
                snimak = motor.za_deljenje(stanje)
                # JSONField cuva i vraca snimak kroz JSON; prikaz iz baze mora biti isti.
                iz_baze = json.loads(json.dumps(snimak))
                with self.subTest(seme=seme, strategija=strategija.__name__):
                    self.assertEqual(snimak, javni)
                    self.assertEqual(motor.deljeni_prikaz(iz_baze), javni)
                    # Dvostruko zaokruzivanje ne menja vrednost (plan 11.2).
                    self.assertEqual(motor.deljeni_prikaz(motor.deljeni_prikaz(iz_baze)), javni)
                provereno += bool(javni["tihe_greske"]) and bool(javni["lekcije"])
        self.assertGreater(provereno, 0, "bar jedna partija mora imati tihe greske i lekcije")

    def test_deljeni_prikaz_bela_lista(self):
        stanje = self.najduza()
        cist = motor.za_deljenje(stanje)
        prljav = copy.deepcopy(cist)
        dodatak = {"seme": stanje["seme"], "izbori": OPUS_HIGH, "ishod": motor.TIHI_NEUSPEH,
                   "tih": True, "partija": motor.oznaka_partije(stanje), "istorija": stanje["istorija"],
                   "sansa": 55, "tezina": 3}
        prljav.update(dodatak)
        for stavka in prljav["tihe_greske"] + prljav["lekcije"]:
            stavka.update(dodatak)
        # Kontrola: detektor vidi ubacene kljuceve u ulazu na svakom nivou.
        self.assertEqual(set(self.kljucevi(prljav)) & self.SKRIVENI, self.SKRIVENI)
        izlaz = motor.deljeni_prikaz(prljav)
        self.assertEqual(izlaz, cist)
        self.assertEqual(set(self.kljucevi(izlaz)) & self.SKRIVENI, set())
        self.assertNotIn(stanje["seme"], json.dumps(izlaz, ensure_ascii=False))

    def test_za_deljenje_bez_oznaka_i_bez_reference(self):
        stanje = motor.oznaci_podeljeno(motor.oznaci_sacuvano(self.najduza(), 3), 4)
        pre = copy.deepcopy(stanje)
        snimak = motor.za_deljenje(stanje)
        self.assertEqual(set(snimak), set(motor.javni_prikaz(stanje)["zavrsni"]))
        self.assertNotIn("sacuvan", snimak)
        self.assertNotIn("podeljeno", snimak)
        # Izmena snimka ne dira stanje: snimak nije pogled na stanje["rezultat"].
        snimak["tihe_greske"].clear()
        snimak["lekcije"][0]["oznaka"] = "x"
        self.assertEqual(stanje, pre)

    def test_oznaci_podeljeno_ne_menja_ulaz(self):
        stanje = odigraj_celu("1", sve_opus)
        pre = copy.deepcopy(stanje)
        novo = motor.oznaci_podeljeno(stanje, 9)
        self.assertEqual(stanje, pre)
        self.assertNotIn("podeljeno", stanje)
        self.assertIsNot(novo, stanje)
        self.assertIsNot(novo["rezultat"], stanje["rezultat"])
        self.assertEqual({k: v for k, v in novo.items() if k != "podeljeno"}, pre)
        self.assertEqual(novo["podeljeno"], 9)
        self.assertEqual(json.loads(json.dumps(novo)), novo)

    def test_podeljeni_red_bez_kljuca(self):
        stanje = odigraj_celu("1", sve_opus)
        self.assertNotIn("podeljeno", stanje)
        self.assertIsNone(motor.podeljeni_red(stanje))
        self.assertIsNone(motor.podeljeni_red(motor.nova_igra("1")))
        for broj in (5, 0):
            with self.subTest(broj=broj):
                self.assertEqual(motor.podeljeni_red(motor.oznaci_podeljeno(stanje, broj)), broj)
        # Oznaka deljenja i oznaka cuvanja su odvojene.
        self.assertIsNone(motor.podeljeni_red(motor.oznaci_sacuvano(stanje, 5)))
        self.assertIsNone(motor.sacuvani_red(motor.oznaci_podeljeno(stanje, 5)))


class NadogradnjaTests(SimpleTestCase):
    """motor.nadogradi: zavrsena partija iz sesije pre kljuceva (plan 12.4)."""

    def partije(self):
        """Zavrsene partije sa tihim greskama, svih pet lekcija i svim ocenama."""
        def najduza(krug):
            return izbori("opus" if krug == 1 else "haiku", "max", "sve", "pedeset")

        stanja = [odigraj_celu(str(i), strategija) for i in range(30)
                  for strategija in (sve_opus, po_tezini, sve_haiku_low_malo, najduza)]
        # Kontrola: uzorak pokriva svaku ocenu, tihu gresku i svaku lekciju.
        self.assertEqual({s["rezultat"]["ocena"] for s in stanja}, set(OCENE_SR))
        self.assertTrue(any(s["rezultat"]["tihe_greske"] for s in stanja))
        self.assertEqual(
            {l["oznaka"] for s in stanja for l in s["rezultat"]["lekcije"]}, set(LEKCIJE_SR)
        )
        return stanja

    def test_staro_zavrseno_daje_isto_sto_i_novo(self):
        for rb, novo in enumerate(self.partije()):
            staro = staro_zavrseno(novo)
            with self.subTest(partija=rb):
                # Kontrola: staro stanje se zaista razlikuje od novog.
                self.assertNotEqual(staro, novo)
                self.assertEqual(motor.nadogradi(staro), novo)
                self.assertEqual(motor.javni_prikaz(motor.nadogradi(staro)), motor.javni_prikaz(novo))

    def test_stara_napomena_ne_izlazi(self):
        novo = odigraj_celu("1", sve_opus)
        nadogradjeno = motor.nadogradi(staro_zavrseno(novo, sa_napomenom=True))
        self.assertEqual(motor.javni_prikaz(nadogradjeno), motor.javni_prikaz(novo))
        self.assertEqual(motor.za_deljenje(nadogradjeno), motor.za_deljenje(novo))
        self.assertEqual(motor.za_cuvanje(nadogradjeno), motor.za_cuvanje(novo))

    def test_idempotentno(self):
        for rb, novo in enumerate(self.partije()[:20]):
            with self.subTest(partija=rb):
                jednom = motor.nadogradi(staro_zavrseno(novo))
                self.assertEqual(motor.nadogradi(jednom), jednom)
                self.assertEqual(motor.nadogradi(novo), novo)

    def test_ulaz_netaknut(self):
        staro = staro_zavrseno(odigraj_celu("3", lambda k: izbori("haiku", "max", "sve", "pedeset")))
        pre = copy.deepcopy(staro)
        novo = motor.nadogradi(staro)
        self.assertEqual(staro, pre)
        self.assertIsNot(novo, staro)
        self.assertIsNot(novo["rezultat"], staro["rezultat"])

    def test_oznake_cuvanja_i_deljenja_ostaju(self):
        staro = motor.oznaci_podeljeno(motor.oznaci_sacuvano(staro_zavrseno(odigraj_celu("5", po_tezini)), 7), 9)
        novo = motor.nadogradi(staro)
        self.assertEqual((motor.sacuvani_red(novo), motor.podeljeni_red(novo)), (7, 9))
        self.assertEqual(novo["seme"], "5")

    def test_nezavrseno_i_prazno_nepromenjeno(self):
        self.assertIsNone(motor.nadogradi(None))
        stanje = motor.nova_igra("7")
        for krug in range(1, 8):
            stanje = motor.odigraj_potez(stanje, krug, OPUS_HIGH)
            with self.subTest(krug=krug):
                pre = copy.deepcopy(stanje)
                self.assertEqual(motor.nadogradi(stanje), pre)
                self.assertEqual(stanje, pre)

    def test_nezavrseno_bez_verzije_dobija_1(self):
        stanje = bez_verzije(motor.nova_igra("7"))
        for krug in range(1, 8):
            with self.subTest(krug=krug):
                pre = copy.deepcopy(stanje)
                novo = motor.nadogradi(stanje)
                self.assertEqual(stanje, pre)
                self.assertNotIn("pravila", stanje)
                self.assertIsNot(novo, stanje)
                self.assertEqual(novo, {**pre, "pravila": 1})
                self.assertEqual(motor.nadogradi(novo), novo)
            stanje = motor.odigraj_potez(stanje, krug, OPUS_HIGH)

    def test_zavrseno_bez_verzije_dobija_1_bez_novih_kljuceva(self):
        seme = nadji_seme(sve_opus, lambda i: i == SEME_JEDNA_TIHA)
        v1 = odigraj_celu(seme, sve_opus, pravila=1)
        staro = staro_zavrseno(bez_verzije(v1))
        # Poeni se ne preracunavaju: vrednost koju nijedna verzija ne daje ostaje.
        staro["rezultat"]["poeni"] = 66
        pre = copy.deepcopy(staro)
        novo = motor.nadogradi(staro)
        self.assertEqual(staro, pre)
        self.assertEqual(novo["pravila"], 1)
        self.assertEqual(novo["rezultat"]["poeni"], 66)
        self.assertEqual(novo["rezultat"]["ocena"], "solidan")
        self.assertEqual(set(novo["rezultat"]) & NOVI_KLJUCEVI_REZULTATA, set())
        ocekivano = bez_verzije(v1)
        ocekivano["pravila"] = 1
        ocekivano["rezultat"].update(poeni=66, ocena="solidan")
        self.assertEqual(novo, ocekivano)
        self.assertEqual(motor.nadogradi(novo), novo)
        self.assertEqual(motor.za_cuvanje(novo), {"poeni": 66, "ocena": "solidan", "pravila": 1})


class BalansTests(SimpleTestCase):
    SEMENA = 5000
    VERZIJE = (1, 2)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.srednje = {}
        for pravila in cls.VERZIJE:
            for strategija in (po_tezini, sve_opus, sve_haiku_low_malo):
                zbir = sum(
                    odigraj_celu(str(i), strategija, pravila)["rezultat"]["poeni"]
                    for i in range(cls.SEMENA)
                )
                cls.srednje[pravila, strategija.__name__] = zbir / cls.SEMENA

    def test_balans_poredak_5000_semena(self):
        for pravila in self.VERZIJE:
            with self.subTest(pravila=pravila):
                self.assertGreater(self.srednje[pravila, "po_tezini"], self.srednje[pravila, "sve_opus"])
                self.assertGreater(
                    self.srednje[pravila, "sve_opus"], self.srednje[pravila, "sve_haiku_low_malo"]
                )

    def test_balans_srednje_vrednosti(self):
        # Pravila 1: parametri.md (2026-11-08). Pravila 2: simulacija talasa 1 plana 13 (2026-11-11),
        # semena 0..4999: 71,64 / 61,15 / 3,38.
        ocekivano = {
            (1, "po_tezini"): 72.8, (1, "sve_opus"): 68.0, (1, "sve_haiku_low_malo"): 20.8,
            (2, "po_tezini"): 71.6, (2, "sve_opus"): 61.2, (2, "sve_haiku_low_malo"): 3.4,
        }
        for (pravila, ime), vrednost in ocekivano.items():
            with self.subTest(pravila=pravila, strategija=ime):
                self.assertAlmostEqual(self.srednje[pravila, ime], vrednost, delta=1.5)


class DnevniMotorTests(SimpleTestCase):
    """Dnevni izazov u cistom motoru (plan dnevnog izazova): dan, oznaka i hes partije."""

    SEME = "seme-dana-motor"
    OZNAKA = "oznaka-partije-motor-0001"
    STARI_KLJUCEVI = {"seme", "krug", "zavrsena", "potroseno", "minuti", "istorija", "rezultat", "pravila"}

    def dnevna(self, oznaka=None, seme=None):
        return motor.nova_igra(seme or self.SEME, dan="2026-11-12", oznaka=oznaka or self.OZNAKA)

    def test_obicna_partija_nema_kljuceve_dnevne(self):
        # Obicno stanje je tacno kao pre dnevnog izazova: ni "dan" ni "oznaka", ni kao None.
        stanje = motor.nova_igra(self.SEME)
        self.assertEqual(set(stanje), self.STARI_KLJUCEVI)
        self.assertIsNone(motor.dan_partije(stanje))
        self.assertEqual(set(odigraj_celu(self.SEME, sve_opus)), self.STARI_KLJUCEVI)

    def test_dnevna_partija_nosi_dan_i_oznaku_i_ostaje_json(self):
        stanje = self.dnevna()
        self.assertEqual(set(stanje), self.STARI_KLJUCEVI | {"dan", "oznaka"})
        self.assertEqual(stanje["dan"], "2026-11-12")
        self.assertEqual(motor.dan_partije(stanje), "2026-11-12")
        self.assertEqual(json.loads(json.dumps(stanje)), stanje)
        # Dan bez oznake i oznaka bez dana: svaki kljuc nastaje sam za sebe.
        self.assertEqual(set(motor.nova_igra("x", dan="2026-11-12")), self.STARI_KLJUCEVI | {"dan"})
        self.assertEqual(set(motor.nova_igra("x", oznaka="o")), self.STARI_KLJUCEVI | {"oznaka"})

    def test_potezi_cuvaju_dan_i_oznaku_a_ishod_zavisi_samo_od_semena(self):
        # Ishod je funkcija semena i izbora: oznaka i dan ga ne menjaju.
        a = self.dnevna(oznaka="a" * 32)
        b = self.dnevna(oznaka="b" * 32)
        obicna = motor.nova_igra(self.SEME)
        for krug in KRUGOVI:
            a = motor.odigraj_potez(a, krug, po_tezini(krug))
            b = motor.odigraj_potez(b, krug, po_tezini(krug))
            obicna = motor.odigraj_potez(obicna, krug, po_tezini(krug))
        self.assertEqual(a["dan"], "2026-11-12")
        self.assertEqual(a["oznaka"], "a" * 32)
        self.assertEqual(ishodi(a), ishodi(b))
        self.assertEqual(ishodi(a), ishodi(obicna))
        self.assertEqual(a["rezultat"]["poeni"], obicna["rezultat"]["poeni"])
        self.assertGreater(len(ishodi(a)), 0)

    def test_oznaka_partije_dnevne_je_hes_oznake_a_ne_semena(self):
        stanje = self.dnevna()
        hes = motor.oznaka_partije(stanje)
        self.assertEqual(hes, hashlib.sha256(self.OZNAKA.encode("utf-8")).hexdigest())
        self.assertNotEqual(hes, hashlib.sha256(self.SEME.encode("utf-8")).hexdigest())
        self.assertEqual(hes, motor.oznaka_partije(motor.odigraj_potez(stanje, 1, OPUS_HIGH)))

    def test_dva_igraca_istog_semena_imaju_razlicit_hes(self):
        # Glavni nalaz plana: sa hesom semena svi igraci dana dele isti Rezultat.partija.
        prvi = self.dnevna(oznaka="1" * 32)
        drugi = self.dnevna(oznaka="2" * 32)
        self.assertEqual(prvi["seme"], drugi["seme"])
        self.assertNotEqual(motor.oznaka_partije(prvi), motor.oznaka_partije(drugi))
        # Kontrola: obicna partija i dalje hesira seme, pa dva igraca istog semena dele hes.
        self.assertEqual(
            motor.oznaka_partije(motor.nova_igra(self.SEME)), motor.oznaka_partije(motor.nova_igra(self.SEME))
        )

    def test_za_cuvanje_dnevne_nosi_dan_a_obicne_tri_kljuca(self):
        dnevna = self.dnevna()
        for krug in KRUGOVI:
            dnevna = motor.odigraj_potez(dnevna, krug, OPUS_HIGH)
        podaci = motor.za_cuvanje(dnevna)
        self.assertEqual(set(podaci), {"poeni", "ocena", "pravila", "dan"})
        self.assertEqual(podaci["dan"], "2026-11-12")
        self.assertEqual(set(motor.za_cuvanje(odigraj_celu(self.SEME, sve_opus))), {"poeni", "ocena", "pravila"})

    def test_za_cuvanje_dnevne_trazi_zavrsenu_i_nesacuvanu(self):
        nezavrsena = motor.odigraj_potez(self.dnevna(), 1, OPUS_HIGH)
        with self.assertRaises(motor.IgraNijeZavrsena):
            motor.za_cuvanje(nezavrsena)
        zavrsena = self.dnevna()
        for krug in KRUGOVI:
            zavrsena = motor.odigraj_potez(zavrsena, krug, OPUS_HIGH)
        with self.assertRaises(motor.VecSacuvano):
            motor.za_cuvanje(motor.oznaci_sacuvano(zavrsena, 3))

    def test_javni_prikaz_dnevne_ne_odaje_dan_ni_oznaku(self):
        dnevna = self.dnevna()
        for krug in KRUGOVI:
            dnevna = motor.odigraj_potez(dnevna, krug, OPUS_HIGH)
        obicna = odigraj_celu(self.SEME, sve_opus)
        prikaz = motor.javni_prikaz(dnevna)
        self.assertEqual(set(prikaz), set(motor.javni_prikaz(obicna)))
        tekst = json.dumps(prikaz)
        for tajna in (self.SEME, self.OZNAKA, "2026-11-12", motor.oznaka_partije(dnevna)):
            self.assertNotIn(tajna, tekst)
        # Kontrola: tajne postoje u stanju, pa je provera nalazi tamo gde sme da budu.
        sirovo = json.dumps(dnevna)
        for tajna in (self.SEME, self.OZNAKA, "2026-11-12"):
            self.assertIn(tajna, sirovo)
        self.assertEqual(motor.deljeni_prikaz(motor.za_deljenje(dnevna)), motor.za_deljenje(obicna))

    def test_nadogradi_cuva_dan_i_oznaku(self):
        stanje = self.dnevna()
        self.assertEqual(motor.nadogradi(stanje)["dan"], "2026-11-12")
        self.assertEqual(motor.nadogradi(stanje)["oznaka"], self.OZNAKA)
