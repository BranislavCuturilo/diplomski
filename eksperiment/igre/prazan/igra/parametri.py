"""Svi brojevi i tekstovi igre. Sadrzi tajne podatke: nikad se ne salje klijentu direktno."""

from dataclasses import dataclass
from decimal import Decimal

# N_ samo oznacava tekst za prevod i vraca ga nepromenjenog; prevodi se tek pri prikazu (servis.py).
from django.utils.translation import gettext_noop as N_


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
KAZNA_ROK = 20


@dataclass(frozen=True)
class Bodovanje:
    """Kazne koje su se menjale izmenom klijenta. Partija pamti verziju sa kojom je pocela."""

    tihi_poeni: int
    # Kazna za svaki zapoceti korak prekoracenja budzeta; bez koraka je kazna fiksna.
    kazna_budzet: int
    korak_budzeta_procenata: int | None
    kazna_budzet_max: int


BODOVANJA = {
    # Prvo izdanje: tiha greska -25, svako prekoracenje budzeta -30.
    1: Bodovanje(tihi_poeni=25, kazna_budzet=30, korak_budzeta_procenata=None, kazna_budzet_max=30),
    # Izmena klijenta: tiha greska -35, budzet -10 za svakih zapocetih 10 % prekoracenja, najvise -50.
    2: Bodovanje(tihi_poeni=35, kazna_budzet=10, korak_budzeta_procenata=10, kazna_budzet_max=50),
}
BODOVANJE_TEKUCE = 2

SANSA_MIN = 5
SANSA_MAX = 99
KOCKA_MAX = 100

TOKENA_PO_JEDINICI_CENE = D("1000000")

STATUS_GOTOVO = N_("готово")
STATUS_DORADA = N_("враћено на дораду")


@dataclass(frozen=True)
class Zadatak:
    krug: int
    naziv: str
    tezina: int
    tih: bool


ZADACI = (
    Zadatak(1, N_("Превод почетне стране"), 1, False),
    Zadatak(2, N_("Шаблон листе и форме"), 1, False),
    Zadatak(3, N_("CSS и прилагођавање телефону"), 1, False),
    Zadatak(4, N_("CRUD прикази"), 2, False),
    Zadatak(5, N_("Модел података и миграција"), 3, True),
    Zadatak(6, N_("Провера права приступа"), 3, True),
    Zadatak(7, N_("Аутоматски тестови"), 2, False),
    Zadatak(8, N_("Безбедносна ревизија"), 3, True),
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
    "malo": Kontekst(N_("мало"), D("0.6"), {1: 0, 2: -15, 3: -25}),
    "taman": Kontekst(N_("таман"), D("1"), {1: 0, 2: 0, 3: 0}),
    "sve": Kontekst(N_("све"), D("1.8"), {1: -10, 2: -10, 3: -10}),
}

PODELE = {
    "sam": Podela(N_("сам"), D("1"), D("1"), 0),
    "3_agenta": Podela(N_("3 агента"), D("1.3"), D("0.5"), 0),
    "50_agenata": Podela(N_("50 агената"), D("3.6"), D("2.1"), -10),
}

# Od najvise granice ka najnizoj: vazi prva ocena cija je granica dostignuta.
OCENE = (
    (85, N_("одличан оркестратор")),
    (65, N_("солидан")),
    (40, N_("скуп учитељ")),
    (0, N_("пожар")),
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
    Lekcija(N_("Ако је грешка тиха, задатак остаје највишем разреду."), "4.2"),
    Lekcija(N_("Најскупљи модел није увек најбољи избор."), "3.2", "model", "opus", 1),
    Lekcija(N_("Изнад нивоа high цена расте, а квалитет не."), "3.3", "nivo", "max"),
    Lekcija(N_("Превише контекста квари резултат исто као премало."), "3.1", "kontekst", "sve"),
    Lekcija(N_("Више агената не значи јефтиније."), "5.3", "podela", "50_agenata"),
)

DUZINA_IMENA_MAX = 30
BROJ_NA_RANG_LISTI = 10
# Igrac na pocetnom ekranu vidi ovoliko svojih poslednjih zavrsenih partija.
BROJ_U_ISTORIJI = 10
# Statistika moderatora: danas i dani pre njega.
DANA_STATISTIKE = 7

# Primer jednog kruga na stranici „Kako se igra“. Zadatak je izmisljen i nije medju osam zadataka
# igre, pa primer ne otkriva tezinu nijednog pravog zadatka.
PRIMER_ZADATAK = N_("Страница „О нама“")
PRIMER_TEZINA = 2
PRIMER_IZBORI = ("sonnet", "high", "taman", "3_agenta")

NAPOMENA_O_PARAMETRIMA = N_(
    "Цене и нивои размишљања су стварни подаци; "
    "вероватноће, казне и поени су измишљени параметри игре."
)
