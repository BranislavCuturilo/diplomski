"""Svi brojevi i tekstovi igre. Sadrzi tajne podatke: nikad se ne salje klijentu direktno."""

from dataclasses import dataclass
from decimal import Decimal


def D(vrednost):
    return Decimal(vrednost)


BROJ_KRUGOVA = 8
BUDZET = D("24")
ROK = D("150")

POCETNI_POENI = 100
MIN_POENI = 0
DORADA_PUTA = 2
DORADA_POENI = 5
TIHI_DODATAK_CENE_PUTA = 3
TIHI_DODATAK_MINUTA_PUTA = 1
TIHI_POENI = 25
KAZNA_BUDZET = 30
KAZNA_ROK = 20

SANSA_MIN = 5
SANSA_MAX = 99
KOCKA_MAX = 100

TOKENA_PO_JEDINICI_CENE = D("1000000")

STATUS_GOTOVO = "готово"
STATUS_DORADA = "враћено на дораду"


@dataclass(frozen=True)
class Zadatak:
    krug: int
    naziv: str
    tezina: int
    tih: bool


ZADACI = (
    Zadatak(1, "Превод почетне стране", 1, False),
    Zadatak(2, "Шаблон листе и форме", 1, False),
    Zadatak(3, "CSS и прилагођавање телефону", 1, False),
    Zadatak(4, "CRUD прикази", 2, False),
    Zadatak(5, "Модел података и миграција", 3, True),
    Zadatak(6, "Провера права приступа", 3, True),
    Zadatak(7, "Аутоматски тестови", 2, False),
    Zadatak(8, "Безбедносна ревизија", 3, True),
)

BAZA_TOKENA = {1: D("100000"), 2: D("300000"), 3: D("600000")}
BAZA_MINUTA = {1: D("5"), 2: D("15"), 3: D("30")}


@dataclass(frozen=True)
class Model:
    naziv: str
    cena: Decimal
    brzina: Decimal
    sansa: dict


@dataclass(frozen=True)
class Nivo:
    naziv: str
    tokeni: Decimal
    brzina: Decimal
    bonus: dict


@dataclass(frozen=True)
class Kontekst:
    naziv: str
    tokeni: Decimal
    bonus: dict


@dataclass(frozen=True)
class Podela:
    naziv: str
    tokeni: Decimal
    brzina: Decimal
    bonus: int


MODELI = {
    "haiku": Model("Haiku", D("0.18"), D("0.5"), {1: 90, 2: 65, 3: 30}),
    "sonnet": Model("Sonnet", D("3.60"), D("0.8"), {1: 95, 2: 85, 3: 60}),
    "opus": Model("Opus", D("7.20"), D("1.0"), {1: 97, 2: 92, 3: 85}),
}

NIVOI = {
    "low": Nivo("low", D("0.33"), D("0.6"), {1: 0, 2: -15, 3: -25}),
    "high": Nivo("high", D("1"), D("1"), {1: 0, 2: 0, 3: 0}),
    "max": Nivo("max", D("2.9"), D("1.6"), {1: 1, 2: 1, 3: 1}),
}

KONTEKSTI = {
    "malo": Kontekst("мало", D("0.6"), {1: 0, 2: -15, 3: -25}),
    "taman": Kontekst("таман", D("1"), {1: 0, 2: 0, 3: 0}),
    "sve": Kontekst("све", D("1.8"), {1: -10, 2: -10, 3: -10}),
}

PODELE = {
    "sam": Podela("сам", D("1"), D("1"), 0),
    "3_agenta": Podela("3 агента", D("1.3"), D("0.5"), 0),
    "50_agenata": Podela("50 агената", D("3.6"), D("2.1"), -10),
}

# Od najvise granice ka najnizoj: vazi prva ocena cija je granica dostignuta.
OCENE = (
    (85, "одличан оркестратор"),
    (65, "солидан"),
    (40, "скуп учитељ"),
    (0, "пожар"),
)


@dataclass(frozen=True)
class Lekcija:
    tekst: str
    odeljak: str
    # Bez polja: uslov je tihi neuspeh. Sa poljem: izbor je napravljen bar jednom.
    polje: str | None = None
    vrednost: str | None = None
    tezina: int | None = None


LEKCIJE = (
    Lekcija("Ако је грешка тиха, задатак остаје највишем разреду.", "4.2"),
    Lekcija("Најскупљи модел није увек најбољи избор.", "3.2", "model", "opus", 1),
    Lekcija("Изнад нивоа high цена расте, а квалитет не.", "3.3", "nivo", "max"),
    Lekcija("Превише контекста квари резултат исто као премало.", "3.1", "kontekst", "sve"),
    Lekcija("Више агената не значи јефтиније.", "5.3", "podela", "50_agenata"),
)

NAPOMENA_O_PARAMETRIMA = (
    "Цене и нивои размишљања су стварни подаци; "
    "вероватноће, казне и поени су измишљени параметри игре."
)
