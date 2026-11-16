"""Prevod kljuceva motora i tekst skripte u aktivnom jeziku (plan 12.3).

Jedino mesto van sablona koje zove gettext. Motor i parametri.py vracaju kljuceve i srpski izvor
(msgid); ovde se prevode. Formati po jeziku zive u FORMATI, nikad u .po (craft-i18n: kodovi
formata se ne prevode).
"""

from django.utils import dateformat, timezone, translation
from django.utils.translation import gettext, gettext_lazy, gettext_noop, ngettext

from . import parametri as p

# Nerazdvojni razmak: iznos i jedinica se pri prelomu reda ne razdvajaju.
NBSP = " "

# Kljuc je kod iz settings.LANGUAGES. Datum: d.m.Y na srpskom (MVP 3), Y-m-d na engleskom (J2).
FORMATI = {
    "sr": {
        "datum": "d.m.Y",
        "zarez": ",",
        "novac": "%(iznos)s" + NBSP + "$",
        "minuti": "%(iznos)s" + NBSP + "мин",
        "procenat": "%(iznos)s" + NBSP + "%",
    },
    "en": {
        "datum": "Y-m-d",
        "zarez": ".",
        "novac": "$%(iznos)s",
        "minuti": "%(iznos)s" + NBSP + "min",
        "procenat": "%(iznos)s%",
    },
}

PORUKE = {
    "osvezeno": gettext_noop("Стање је освежено."),
    "nemaIgre": gettext_noop("Партија више не постоји. Освежите страну за нову игру."),
    "neispravno": gettext_noop("Захтев није исправан. Освежите страну."),
    "server": gettext_noop("Сервер није одговорио како треба. Покушајте поново."),
    "stanje": gettext_noop("Стање игре није могло да се прочита. Освежите страну."),
    "rangSacuvano": gettext_noop("Резултат је сачуван."),
    "nepodobnoIme": gettext_noop("Ово име није дозвољено. Изаберите друго име."),
    "vecSacuvano": gettext_noop("Ова партија је већ сачувана."),
    "nijeZavrsena": gettext_noop("Партија још није завршена. Освежите страну."),
    # Isti tekst za istekao i za obrisan link (plan 14.4).
    "deljenjeIsteklo": gettext_noop("Линк за ову партију више није доступан."),
    "kopirano": gettext_noop("Линк је копиран."),
    "kopiranjeRezerva": gettext_noop("Копирање није успело. Линк је означен; копирајте га ручно."),
    "nijeProcitano": gettext_noop("Резултат није могао да се прочита."),
    "izaberite": gettext_noop("Изаберите све четири опције да видите процену."),
    # Prijava neprikladnog imena: isti tekst za novu, ponovljenu i vec pregledanu prijavu (views.prijavi).
    "prijavaPrimljena": gettext_noop("Пријава је примљена. Хвала."),
    "prijavaNijeNaListi": gettext_noop("Овај резултат више није на ранг листи. Освежите страну."),
}

PITANJE_NOVA = gettext_noop("Започети нову игру? Текућа партија се губи.")

# Sadrzaj za navigator.share (title i text); url dolazi sa servera.
DELJENJE = {
    # Translators: naziv igre (na engleskom "Orchestrator", odluka J3).
    "naslov": gettext_noop("Оркестратор"),
    "tekst": gettext_noop("Мој резултат у игри Оркестратор"),
}

# Skripta samo popunjava %(ime)s; cena i minuti stizu vec sa jedinicom iz FORMATI.
OBRASCI = {
    # Translators: %(krug)s je redni broj kruga, %(ukupno)s ukupan broj krugova.
    "krug": gettext_noop("Круг %(krug)s од %(ukupno)s"),
    "zavrsena": gettext_noop("Игра је завршена"),
    # Translators: rezultat poslednjeg kruga; %(zadatak)s je naziv zadatka.
    "rezultatKruga": gettext_noop("Круг %(krug)s: %(zadatak)s"),
    # Translators: %(cena)s je iznos sa oznakom valute, %(minuti)s broj minuta sa jedinicom.
    "procena": gettext_noop("Процена: цена %(cena)s, %(minuti)s."),
    # Translators: tiha greska na zavrsnom ekranu; %(cena)s i %(minuti)s su dodatak sa jedinicom.
    "tiha": gettext_noop("Круг %(krug)s: %(zadatak)s (додатак: %(cena)s, %(minuti)s)"),
    # Translators: odeljak zavrsnog rada uz lekciju, npr. 4.2.
    "odeljak": gettext_noop("(одељак %(odeljak)s)"),
    # Translators: %(datum)s je dan isteka linka za deljenje.
    "rok": gettext_noop("Линк важи до %(datum)s."),
}


# Natpis prekidaca zvuka (isti msgid kao u sablonu igra.html); skripta ga menja po stanju.
ZVUK = {
    "ukljucen": gettext_noop("Звук: укључен"),
    "iskljucen": gettext_noop("Звук: искључен"),
}


# Vreme uz datum u dnevniku moderatora: 24 sata na oba jezika, pa nije u FORMATI.
VREME = "H:i"

# Moderatorske strane (plan 14.7). Ostali tekst tih strana, i naziv radnje dnevnika po kljucu, je u sablonima;
# greske Django formi (validatori lozinke i imena) dolaze iz Django kataloga.
# Oznake polja: isti msgid kao oznaka= u sablonima (jedna stavka kataloga); lenje, jer se forme prave pri
# uvozu, a jezik bira zahtev.
POLJA = {
    "korisnicko_ime": gettext_lazy("Корисничко име"),
    "lozinka": gettext_lazy("Лозинка"),
    "nova_lozinka": gettext_lazy("Нова лозинка"),
    "lozinka_ponovo": gettext_lazy("Лозинка поново"),
    "glavni": gettext_lazy("Главни модератор"),
    "moja_lozinka": gettext_lazy("Ваша лозинка"),
}

# Ista poruka za pogresno ime, pogresnu lozinku, neaktivan nalog i nalog bez uloge (plan 14.2).
PRIJAVA_NEUSPESNA = gettext_lazy("Погрешно корисничко име или лозинка.")
# Potvrda sopstvenom lozinkom (plan 14.5).
POGRESNA_LOZINKA = gettext_lazy("Погрешна лозинка.")
# Promena sopstvene lozinke, i obavezna promena pocetne (revizija 2026-11-11).
ISTA_LOZINKA = gettext_lazy("Нова лозинка мора да се разликује од старе.")


def _format():
    # Aktivni jezik svodi na kod iz LANGUAGES ("en-us" -> "en"); nepodrzan jezik baca LookupError.
    return FORMATI[translation.get_supported_language_variant(translation.get_language())]


def datum(trenutak):
    """Dan u TIME_ZONE (Europe/Belgrade), u formatu aktivnog jezika."""
    return dateformat.format(timezone.localtime(trenutak), _format()["datum"])


def datum_vreme(trenutak):
    """Dan i vreme u TIME_ZONE (Europe/Belgrade): 10.11.2026 14:05 na srpskom, 2026-11-10 14:05 na engleskom."""
    return dateformat.format(timezone.localtime(trenutak), f"{_format()['datum']} {VREME}")


def _iznos(vrednost, decimale, obrazac):
    # Isto kao iznos() u igra.js: zarez po jeziku, -0 se ne ispisuje, obrazac iz FORMATI.
    tekst = f"{float(vrednost):.{decimale}f}"
    if float(tekst) == 0:
        tekst = f"{0:.{decimale}f}"
    predznak = ""
    if tekst.startswith("-"):
        predznak, tekst = "-", tekst[1:]
    # replace, ne %: obrazac "procenat" nosi i goli znak % (skripta ga isto samo zamenjuje).
    return predznak + _format()[obrazac].replace("%(iznos)s", tekst.replace(".", _format()["zarez"]))


def novac(vrednost, decimale=2):
    """Iznos u dolarima u formatu aktivnog jezika; podrazumevano kao na zavrsnom ekranu (2 decimale)."""
    return _iznos(vrednost, decimale, "novac")


def minuti(vrednost, decimale=1):
    """Minuti sa jedinicom u formatu aktivnog jezika; podrazumevano kao na zavrsnom ekranu (1 decimala)."""
    return _iznos(vrednost, decimale, "minuti")


def ocena(kljuc):
    """Naziv ocene u aktivnom jeziku (kljuc iz parametri.OCENE)."""
    return gettext(p.NAZIVI_OCENA[kljuc])


def blokada(minuta):
    """Poruka blokade posle previse neuspeha za potvrdu sopstvenom lozinkom (forme).

    Isti msgid i mnozina kao blocktranslate u moderator/prijava.html, pa je u katalogu jedna stavka.
    """
    return ngettext(
        # Translators: %(n)s je broj minuta do kraja blokade.
        "Превише неуспешних покушаја. Покушајте поново за %(n)s минут.",
        "Превише неуспешних покушаја. Покушајте поново за %(n)s минута.",
        minuta,
    ) % {"n": minuta}


def opcije(javne):
    """Isti oblik kao motor.javne_opcije; naziv i opis u aktivnom jeziku (Haiku, low... ostaju isti)."""
    return {
        grupa: [
            {"kljuc": o["kljuc"], "naziv": gettext(o["naziv"]), "opis": gettext(o["opis"])}
            for o in lista
        ]
        for grupa, lista in javne.items()
    }


def _poruke():
    poruke = {kljuc: gettext(tekst) for kljuc, tekst in PORUKE.items()}
    # Brojeve u porukama ubacuje server, pa skripti mnozina ne treba (plan 12.3). Komentar za
    # prevodioca stoji u redu iznad teksta: xgettext ga inace odbacuje na kraju reda sa kodom.
    poruke["rangVanListe"] = ngettext(
        # Translators: %(n)s je broj mesta na rang listi.
        "Резултат је сачуван, али није међу %(n)s најбољим.",
        "Резултат је сачуван, али није међу %(n)s најбољих.",
        p.RANG_MESTA,
    ) % {"n": p.RANG_MESTA}
    poruke["neispravnoIme"] = ngettext(
        # Translators: %(n)s je najveci broj znakova imena.
        "Име мора имати од 1 до %(n)s знака, без размака на почетку и крају и без невидљивих знакова.",
        "Име мора имати од 1 до %(n)s знакова, без размака на почетку и крају и без невидљивих знакова.",
        p.IME_MAKS,
    ) % {"n": p.IME_MAKS}
    return poruke


def _moguce_kazne_budzeta():
    """Svaka kazna budzeta koju motor moze da da po nekoj verziji iz parametri.KAZNE (plan 13.4)."""
    kazne = set()
    for kazna in p.KAZNE.values():
        iznos = kazna["budzet_po_koraku"]
        while iznos < kazna["budzet_maks"]:
            kazne.add(iznos)
            iznos += kazna["budzet_po_koraku"]
        kazne.add(kazna["budzet_maks"])
    return sorted(kazne)


def _budzet_kazne():
    """Kazna -> recenica o prekoracenju budzeta (plan 13.4, B4-B).

    Oblik mnozine bira server po kazni; %(procenat)s ostaje skripti, koja ga popunjava procentom iz
    FORMATI. Kazna van mape: skripta ostaje na recenici bez iznosa.
    """
    return {
        str(kazna): ngettext(
            # Translators: %(procenat)s je prekoracenje budzeta u procentima, vec sa znakom %; %(kazna)s je
            # broj izgubljenih poena.
            "Буџет је прекорачен за %(procenat)s (−%(kazna)s поен).",
            "Буџет је прекорачен за %(procenat)s (−%(kazna)s поена).",
            kazna,
        ) % {"kazna": kazna, "procenat": "%(procenat)s"}
        for kazna in _moguce_kazne_budzeta()
    }


def za_skriptu():
    """Sav tekst skripte u aktivnom jeziku (json_script "tekstovi").

    Nosi uvek sve zadatke, ocene i lekcije, pa ne zavisi od stanja i ne otkriva nista o partiji.
    """
    format_jezika = _format()
    return {
        "zadaci": {z["kljuc"]: gettext(z["naziv"]) for z in p.ZADACI},
        "status": {kljuc: gettext(tekst) for kljuc, tekst in p.NAZIVI_STATUSA.items()},
        "ocene": {kljuc: gettext(tekst) for kljuc, tekst in p.NAZIVI_OCENA.items()},
        "lekcije": {kljuc: gettext(lekcija["tekst"]) for kljuc, lekcija in p.LEKCIJE.items()},
        "napomena": gettext(p.NAPOMENA),
        "poruke": _poruke(),
        "pitanjeNova": gettext(PITANJE_NOVA),
        "deljenje": {kljuc: gettext(tekst) for kljuc, tekst in DELJENJE.items()},
        "obrasci": {kljuc: gettext(tekst) for kljuc, tekst in OBRASCI.items()},
        "zvuk": {kljuc: gettext(tekst) for kljuc, tekst in ZVUK.items()},
        "budzetKazne": _budzet_kazne(),
        "format": {
            "zarez": format_jezika["zarez"],
            "novac": format_jezika["novac"],
            "minuti": format_jezika["minuti"],
            "procenat": format_jezika["procenat"],
        },
    }


def procenat(vrednost):
    """Ceo procenat sa znakom % u formatu aktivnog jezika."""
    return _iznos(vrednost, 0, "procenat")
