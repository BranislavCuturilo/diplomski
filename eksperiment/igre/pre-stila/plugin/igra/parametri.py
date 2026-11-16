"""Svi brojevi i tekstovi igre. Izvor: .claude/skills/projekat-domen/references/parametri.md.

Kljucevi su latinicom, tekst za ekran cirilicom. Promena broja trazi odobrenje korisnika.
"""

KRUGOVA = 8
BUDZET = 24
ROK = 150
POCETNI_POENI = 100
MIN_POENI = 0

KAZNA_DORADA = 5
KAZNA_TIHA = 25
KAZNA_BUDZET = 30
KAZNA_ROK = 20

MNOZILAC_DORADE = 2
DODATAK_TIHA_CENA = 3
DODATAK_TIHA_MINUTI = 1

SANSA_MIN = 5
SANSA_MAX = 99
KOCKA_MIN = 1
KOCKA_MAX = 100
TOKENA_PO_MILION = 1000000

DECIMALA_POREDJENJA = 9
DECIMALA_JAVNIH = 4

# Tezina zadatka na kojoj Opus pali lekciju "opus_lako".
TEZINA_LAKA = 1

ZADACI = [
    {"naziv": "Превод почетне стране", "tezina": 1, "tih": False},
    {"naziv": "Шаблон листе и форме", "tezina": 1, "tih": False},
    {"naziv": "CSS и прилагођавање телефону", "tezina": 1, "tih": False},
    {"naziv": "CRUD прикази", "tezina": 2, "tih": False},
    {"naziv": "Модел података и миграција", "tezina": 3, "tih": True},
    {"naziv": "Провера права приступа", "tezina": 3, "tih": True},
    {"naziv": "Аутоматски тестови", "tezina": 2, "tih": False},
    {"naziv": "Безбедносна ревизија", "tezina": 3, "tih": True},
]

BAZA = {
    1: {"tokeni": 100000, "minuti": 5},
    2: {"tokeni": 300000, "minuti": 15},
    3: {"tokeni": 600000, "minuti": 30},
}

MODELI = {
    "haiku": {
        "naziv": "Haiku",
        "opis": "најјефтинији и најбржи",
        "cena": 0.18,
        "brzina": 0.5,
        "sansa": {1: 90, 2: 65, 3: 30},
    },
    "sonnet": {
        "naziv": "Sonnet",
        "opis": "средњи по цени и брзини",
        "cena": 3.60,
        "brzina": 0.8,
        "sansa": {1: 95, 2: 85, 3: 60},
    },
    "opus": {
        "naziv": "Opus",
        "opis": "најскупљи и најспорији, најпоузданији",
        "cena": 7.20,
        "brzina": 1.0,
        "sansa": {1: 97, 2: 92, 3: 85},
    },
}

NIVOI = {
    "low": {
        "naziv": "low",
        "opis": "кратко размишљање: јефтино и брзо, слабије на захтевнијем послу",
        "tokeni": 0.33,
        "brzina": 0.6,
        "bonus": {1: 0, 2: -15, 3: -25},
    },
    "high": {
        "naziv": "high",
        "opis": "пажљиво размишљање: уобичајен избор",
        "tokeni": 1,
        "brzina": 1,
        "bonus": {1: 0, 2: 0, 3: 0},
    },
    "max": {
        "naziv": "max",
        "opis": "најдуже размишљање: знатно скупље и спорије",
        "tokeni": 2.9,
        "brzina": 1.6,
        "bonus": {1: 1, 2: 1, 3: 1},
    },
}

KONTEKSTI = {
    "malo": {
        "naziv": "мало",
        "opis": "само најнужније: јефтиније, али агент може да промаши",
        "tokeni": 0.6,
        "bonus": {1: 0, 2: -15, 3: -25},
    },
    "taman": {
        "naziv": "таман",
        "opis": "оно што задатку треба",
        "tokeni": 1,
        "bonus": {1: 0, 2: 0, 3: 0},
    },
    "sve": {
        "naziv": "све",
        "opis": "цео пројекат: скупље и расплинуто",
        "tokeni": 1.8,
        "bonus": {1: -10, 2: -10, 3: -10},
    },
}

PODELE = {
    "sam": {
        "naziv": "сам",
        "opis": "један агент ради редом",
        "tokeni": 1,
        "brzina": 1,
        "bonus": 0,
    },
    "tri": {
        "naziv": "3 агента",
        "opis": "три агента упоредо: брже, нешто скупље",
        "tokeni": 1.3,
        "brzina": 0.5,
        "bonus": 0,
    },
    "pedeset": {
        "naziv": "50 агената",
        "opis": "педесет агената: много скупље, а усклађивање траје",
        "tokeni": 3.6,
        "brzina": 2.1,
        "bonus": -10,
    },
}

OCENE = [
    (85, "одличан оркестратор"),
    (65, "солидан"),
    (40, "скуп учитељ"),
    (0, "пожар"),
]

STATUS_GOTOVO = "готово"
STATUS_DORADA = "враћено на дораду"
NAPOMENA = (
    "Цене и нивои размишљања су стварни подаци; вероватноће, казне и поени "
    "су измишљени параметри игре."
)

LEKCIJE = {
    "tiha": {"tekst": "Ако је грешка тиха, задатак остаје највишем разреду.", "odeljak": "4.2"},
    "opus_lako": {"tekst": "Најскупљи модел није увек најбољи избор.", "odeljak": "3.2"},
    "max": {"tekst": "Изнад нивоа high цена расте, а квалитет не.", "odeljak": "3.3"},
    "sve": {"tekst": "Превише контекста квари резултат исто као премало.", "odeljak": "3.1"},
    "pedeset": {"tekst": "Више агената не значи јефтиније.", "odeljak": "5.3"},
}
