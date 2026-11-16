"""Svi brojevi i tekstovi igre. Izvor: .claude/skills/projekat-domen/references/parametri.md.

Kljucevi su latinicom, tekst za ekran je srpski izvor (msgid) cirilicom; prevodi ga samo
igra/tekstovi.py (plan 12.3). Promena broja trazi odobrenje korisnika.
"""


def gettext_noop(tekst):
    """Oznaka teksta za makemessages (ime je kljucna rec koju vec trazi); bez uvoza Django-a."""
    return tekst


KRUGOVA = 8
BUDZET = 24
ROK = 150
POCETNI_POENI = 100
MIN_POENI = 0

# Verzija pravila bodovanja (plan 13.1): partija se boduje po pravilima sa svog pocetka (B2-B).
# Stanje bez kljuca "pravila" je verzija PRAVILA_STARA. KAZNE[1] ostaje dok postoji takva sesija.
# Poznate verzije su PRAVILA_STARA..PRAVILA_TEKUCA, bez rupa: nova verzija je PRAVILA_TEKUCA + 1, a
# PRAVILA_STARA je prva i ne menja se. Granice cita CHECK igra_pravila_poznata (models.py), ne
# kljuceve KAZNE: red rang liste ostaje i kad KAZNE izgubi verziju (poeni se ne preracunavaju).
PRAVILA_STARA = 1
PRAVILA_TEKUCA = 2

# Kazne u poenima po verziji pravila; kljuc je broj verzije, nikad se ne prenumerise.
# Budzet: budzet_po_koraku za svaki zapocet korak od budzet_korak_procenata prekoracenja, najvise
# budzet_maks. Verzija 1 je ista formula: svako prekoracenje daje bar jedan korak, a najvise 30.
KAZNE = {
    # do 2026-11-11
    1: {"dorada": 5, "tiha": 25, "rok": 20, "budzet_po_koraku": 30, "budzet_korak_procenata": 10, "budzet_maks": 30},
    # zahtev klijenta 2026-11-11
    2: {"dorada": 5, "tiha": 35, "rok": 20, "budzet_po_koraku": 10, "budzet_korak_procenata": 10, "budzet_maks": 50},
}
PROCENAT = 100

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
# Najvise zavrsenih partija u istoriji pregledaca (sesija, bez modela).
ISTORIJA_MAKS = 10
# Nano-dolar: budzet se poredi u celim brojevima na DECIMALA_POREDJENJA decimala (B3-A).
JEDINICA_POREDJENJA = 10 ** DECIMALA_POREDJENJA

# Tezina zadatka na kojoj Opus pali lekciju "opus_lako".
TEZINA_LAKA = 1

# Rang lista (MVP 3): najduze ime u znakovima (kodnim tackama posle NFC) i broj prikazanih mesta.
IME_MAKS = 20
RANG_MESTA = 10
# Najvise uzastopnih kombinujucih znakova (kategorija M) u imenu posle NFC; nagomilani (Zalgo) crtaju
# preko susednih redova liste. Dva pokrivaju taster cifre (U+FE0F U+20E3).
IME_MAKS_KOMBINUJUCIH = 2

# Prijava neprikladnog imena sa rang liste (odluka 2026-11-12). Javna oznaka reda je HMAC partije skracen na
# PRIJAVA_OZNAKA_DUZINA heksadecimalnih cifara (128 bita). Po rezultatu se belezi najvise PRIJAVA_NAJVISE prijava:
# moderatoru je dovoljno "mnogo", a tabela prijava ne raste bez granice.
PRIJAVA_OZNAKA_DUZINA = 32
PRIJAVA_NAJVISE = 100

# Deljenje rezultata (MVP 3): link vazi DELJENJE_DANA od nastanka. Token je
# secrets.token_urlsafe(DELJENJE_TOKEN_BAJTOVA), 128 bita, sto daje DELJENJE_TOKEN_DUZINA znakova base64url.
DELJENJE_DANA = 30
DELJENJE_TOKEN_BAJTOVA = 16
DELJENJE_TOKEN_DUZINA = 22

# kljuc ide u JSON i bazu; naziv je srpski izvor za prevod (plan 12.3).
ZADACI = [
    {"kljuc": "prevod", "naziv": gettext_noop("Превод почетне стране"), "tezina": 1, "tih": False},
    {"kljuc": "sablon", "naziv": gettext_noop("Шаблон листе и форме"), "tezina": 1, "tih": False},
    {"kljuc": "css", "naziv": gettext_noop("CSS и прилагођавање телефону"), "tezina": 1, "tih": False},
    {"kljuc": "crud", "naziv": gettext_noop("CRUD прикази"), "tezina": 2, "tih": False},
    {"kljuc": "model", "naziv": gettext_noop("Модел података и миграција"), "tezina": 3, "tih": True},
    {"kljuc": "prava", "naziv": gettext_noop("Провера права приступа"), "tezina": 3, "tih": True},
    {"kljuc": "testovi", "naziv": gettext_noop("Аутоматски тестови"), "tezina": 2, "tih": False},
    {"kljuc": "revizija", "naziv": gettext_noop("Безбедносна ревизија"), "tezina": 3, "tih": True},
]

BAZA = {
    1: {"tokeni": 100000, "minuti": 5},
    2: {"tokeni": 300000, "minuti": 15},
    3: {"tokeni": 600000, "minuti": 30},
}

# Nazivi modela i nivoa (Haiku, low...) isti su na oba jezika i nisu oznaceni za prevod (MVP 6).
MODELI = {
    "haiku": {
        "naziv": "Haiku",
        "opis": gettext_noop("најјефтинији и најбржи"),
        "cena": 0.18,
        "brzina": 0.5,
        "sansa": {1: 90, 2: 65, 3: 30},
    },
    "sonnet": {
        "naziv": "Sonnet",
        "opis": gettext_noop("средњи по цени и брзини"),
        "cena": 3.60,
        "brzina": 0.8,
        "sansa": {1: 95, 2: 85, 3: 60},
    },
    "opus": {
        "naziv": "Opus",
        "opis": gettext_noop("најскупљи и најспорији, најпоузданији"),
        "cena": 7.20,
        "brzina": 1.0,
        "sansa": {1: 97, 2: 92, 3: 85},
    },
}

NIVOI = {
    "low": {
        "naziv": "low",
        "opis": gettext_noop("кратко размишљање: јефтино и брзо, слабије на захтевнијем послу"),
        "tokeni": 0.33,
        "brzina": 0.6,
        "bonus": {1: 0, 2: -15, 3: -25},
    },
    "high": {
        "naziv": "high",
        "opis": gettext_noop("пажљиво размишљање: уобичајен избор"),
        "tokeni": 1,
        "brzina": 1,
        "bonus": {1: 0, 2: 0, 3: 0},
    },
    "max": {
        "naziv": "max",
        "opis": gettext_noop("најдуже размишљање: знатно скупље и спорије"),
        "tokeni": 2.9,
        "brzina": 1.6,
        "bonus": {1: 1, 2: 1, 3: 1},
    },
}

KONTEKSTI = {
    "malo": {
        # Translators: kontekst koji agent dobija: malo, samo najnuzniji delovi projekta.
        "naziv": gettext_noop("мало"),
        "opis": gettext_noop("само најнужније: јефтиније, али агент може да промаши"),
        "tokeni": 0.6,
        "bonus": {1: 0, 2: -15, 3: -25},
    },
    "taman": {
        # Translators: kontekst koji agent dobija: taman, upravo koliko zadatku treba.
        "naziv": gettext_noop("таман"),
        "opis": gettext_noop("оно што задатку треба"),
        "tokeni": 1,
        "bonus": {1: 0, 2: 0, 3: 0},
    },
    "sve": {
        # Translators: kontekst koji agent dobija: sve, ceo projekat.
        "naziv": gettext_noop("све"),
        "opis": gettext_noop("цео пројекат: скупље и расплинуто"),
        "tokeni": 1.8,
        "bonus": {1: -10, 2: -10, 3: -10},
    },
}

PODELE = {
    "sam": {
        # Translators: podela posla: jedan agent radi sam.
        "naziv": gettext_noop("сам"),
        "opis": gettext_noop("један агент ради редом"),
        "tokeni": 1,
        "brzina": 1,
        "bonus": 0,
    },
    "tri": {
        # Translators: podela posla: tri agenta rade uporedo.
        "naziv": gettext_noop("3 агента"),
        "opis": gettext_noop("три агента упоредо: брже, нешто скупље"),
        "tokeni": 1.3,
        "brzina": 0.5,
        "bonus": 0,
    },
    "pedeset": {
        # Translators: podela posla: pedeset agenata rade uporedo.
        "naziv": gettext_noop("50 агената"),
        "opis": gettext_noop("педесет агената: много скупље, а усклађивање траје"),
        "tokeni": 3.6,
        "brzina": 2.1,
        "bonus": -10,
    },
}

# (prag poena, kljuc ocene); kljuc ide u JSON i bazu (CheckConstraint igra_ocena_kljuc).
OCENE = [
    (85, "odlican"),
    (65, "solidan"),
    (40, "skup"),
    (0, "pozar"),
]

NAZIVI_OCENA = {
    "odlican": gettext_noop("одличан оркестратор"),
    "solidan": gettext_noop("солидан"),
    # Translators: ocena: igrac je skupo platio lekciju (doslovno "skup ucitelj").
    "skup": gettext_noop("скуп учитељ"),
    # Translators: najlosija ocena (doslovno "pozar").
    "pozar": gettext_noop("пожар"),
}

# Uspeh i tih neuspeh nose isti kljuc STATUS_GOTOVO (pravilo 1).
STATUS_GOTOVO = "gotovo"
STATUS_DORADA = "dorada"

NAZIVI_STATUSA = {
    # Translators: status kruga: zadatak je zavrsen.
    STATUS_GOTOVO: gettext_noop("готово"),
    STATUS_DORADA: gettext_noop("враћено на дораду"),
}

NAPOMENA = gettext_noop(
    "Цене и нивои размишљања су стварни подаци; вероватноће, казне и поени "
    "су измишљени параметри игре."
)

# Kljuc lekcije ide u JSON i bazu kao "oznaka"; tekst je srpski izvor za prevod.
LEKCIJE = {
    "tiha": {"tekst": gettext_noop("Ако је грешка тиха, задатак остаје највишем разреду."), "odeljak": "4.2"},
    "opus_lako": {"tekst": gettext_noop("Најскупљи модел није увек најбољи избор."), "odeljak": "3.2"},
    "max": {"tekst": gettext_noop("Изнад нивоа high цена расте, а квалитет не."), "odeljak": "3.3"},
    "sve": {"tekst": gettext_noop("Превише контекста квари резултат исто као премало."), "odeljak": "3.1"},
    "pedeset": {"tekst": gettext_noop("Више агената не значи јефтиније."), "odeljak": "5.3"},
}
