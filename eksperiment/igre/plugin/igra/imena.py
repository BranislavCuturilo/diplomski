"""Ime za rang listu: pravila (plan 10.4) i kljuc za poredjenje sa sifarnikom. Bez Django-a."""

import unicodedata

from . import parametri as p

RAZMAK = " "

# Cc kontrolni, Cf nevidljivi (ZWJ, smer teksta), Cs usamljen surogat, Co privatni, Cn nedodeljeni,
# Zl i Zp prelom reda i pasusa. Od Zs je dozvoljen samo RAZMAK (provera ispod).
ZABRANJENE_KATEGORIJE = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})

# Znakovi koji se ne crtaju, a ZABRANJENE_KATEGORIJE ih ne hvataju (R2): Default_Ignorable_Code_Point
# van kategorija C*, jer ih Python vidi kao slovo (Lo) ili kombinujuci znak (Mn), i U+2800 (So), koji
# nije Default_Ignorable, ali se crta prazno. Ime od njih izgleda prazno, a Hangul popunjivac (Lo)
# usred reci ostajao je u kljucu, pa je zaobilazio sifarnik.
NEVIDLJIVI = frozenset(
    chr(tacka)
    for prva, poslednja in (
        (0x034F, 0x034F),  # kombinujuci spojnik grafema (Mn)
        (0x115F, 0x1160),  # Hangul popunjivaci (Lo)
        (0x17B4, 0x17B5),  # kmerski nevidljivi samoglasnici (Mn)
        (0x180B, 0x180F),  # mongolski selektori varijante (Mn; U+180E je Cf)
        (0x2800, 0x2800),  # prazan Braille (So)
        (0x3164, 0x3164),  # Hangul popunjivac (Lo)
        (0xFE00, 0xFE0F),  # selektori varijante (Mn)
        (0xFFA0, 0xFFA0),  # Hangul popunjivac pola sirine (Lo)
        (0xE0100, 0xE01EF),  # dopunski selektori varijante (Mn)
    )
    for tacka in range(prva, poslednja + 1)
)

# Izuzetak iz NEVIDLJIVI samo u ime_ispravno (odluka 2026-11-10, opcija b): U+FE0F trazi emoji prikaz
# znaka ispred sebe i nose ga cesti emoji (srce U+2764, U+270C, U+2122, taster cifre 1 U+FE0F U+20E3),
# pa prolazi samo posle simbola, cifre ili interpunkcije (# i *). Posle slova, kombinujuceg znaka (i
# drugog U+FE0F), razmaka ili na pocetku ne crta nista: odbija se kao ostali NEVIDLJIVI (R2). Razmak
# bi jos i zaobisao pravilo o razmaku na kraju imena. Iz kljuca se izbacuje kao ostali.
SELEKTOR_EMOJI = chr(0xFE0F)
ISPRED_SELEKTORA_EMOJI = ("S", "N", "P")  # pocetak Unicode kategorije znaka odmah pred U+FE0F

# Posle NFKD i skidanja dijakritika ostaju samo slova bez rastavljanja: srpska azbuka i latinicno đ.
PRESLOVLJAVANJE = str.maketrans(
    {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "ђ": "dj", "е": "e", "ж": "z",
        "з": "z", "и": "i", "ј": "j", "к": "k", "л": "l", "љ": "lj", "м": "m", "н": "n",
        "њ": "nj", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "ћ": "c", "у": "u",
        "ф": "f", "х": "h", "ц": "c", "ч": "c", "џ": "dz", "ш": "s",
        "đ": "dj",
    }
)


def ime_ispravno(ime):
    """Pravila 3-5 iz plana 10.4, NEVIDLJIVI i Zalgo; ime je vec NFC, tip proverava pozivalac."""
    if not ime or len(ime) > p.IME_MAKS:
        return False
    prvi, poslednji = ime[0], ime[-1]
    if prvi.isspace() or poslednji.isspace():
        return False
    if unicodedata.category(prvi).startswith("M"):
        return False
    uzastopnih_m = 0
    prethodna = ""  # kategorija prethodnog znaka; prazna na pocetku, pa U+FE0F tamo ne prolazi
    for znak in ime:
        kategorija = unicodedata.category(znak)
        if kategorija in ZABRANJENE_KATEGORIJE:
            return False
        if kategorija == "Zs" and znak != RAZMAK:
            return False
        if znak == SELEKTOR_EMOJI:
            if not prethodna.startswith(ISPRED_SELEKTORA_EMOJI):
                return False
        elif znak in NEVIDLJIVI:
            return False
        uzastopnih_m = uzastopnih_m + 1 if kategorija.startswith("M") else 0
        if uzastopnih_m > p.IME_MAKS_KOMBINUJUCIH:
            return False
        prethodna = kategorija
    return True


def kljuc_imena(ime):
    """Normalizacija za sifarnik; koraci redom iz plana 10.4, korak 2 skida i NEVIDLJIVI."""
    s = unicodedata.normalize("NFKD", unicodedata.normalize("NFKD", ime).casefold())
    # NEVIDLJIVI i za ime koje nije proslo ime_ispravno (komanda, raniji red), pa sifarnik ne zavisi od
    # redosleda poziva. Posle NFKD, jer od U+3164 i U+FFA0 tek tada nastaje U+1160.
    s = "".join(znak for znak in s if unicodedata.category(znak) != "Mn" and znak not in NEVIDLJIVI)
    s = s.translate(PRESLOVLJAVANJE)
    return "".join(znak for znak in s if unicodedata.category(znak).startswith(("L", "N")))
