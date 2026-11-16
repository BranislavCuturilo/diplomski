"""Engleski katalog prevoda bez GNU gettext alata.

Izvorni tekst igre je srpski (cirilica) i on je msgid. Ovaj modul skuplja sve poruke iz sablona i
Python koda, dopunjuje `locale/en/LC_MESSAGES/django.po` i pravi `django.mo` uz pomoc biblioteke
polib. Pokrece se sa `python manage.py prevodi`; `--provera` samo proverava, bez izmena.
"""

import ast
import re
from pathlib import Path

from django.utils.translation.template import templatize

APLIKACIJA = Path(__file__).resolve().parent
PO = APLIKACIJA / "locale" / "en" / "LC_MESSAGES" / "django.po"
MO = PO.with_suffix(".mo")
SABLONI = APLIKACIJA / "templates"
PREVODIVE_FUNKCIJE = {"_", "N_", "gettext", "gettext_noop", "gettext_lazy"}
POZIV_U_SABLONU = re.compile(
    r"(n?)gettext\(u'((?:[^'\\]|\\.)*)'(?:, u'((?:[^'\\]|\\.)*)', count)?\)"
)
ZAMENA = re.compile(r"%\(\w+\)s")
METAPODACI = {
    "Project-Id-Version": "orkestrator",
    "Language": "en",
    "MIME-Version": "1.0",
    "Content-Type": "text/plain; charset=UTF-8",
    "Content-Transfer-Encoding": "8bit",
    "Plural-Forms": "nplurals=2; plural=(n != 1);",
}


def _iz_sablona():
    poruke = {}
    for sablon in sorted(SABLONI.rglob("*.html")):
        izvor = templatize(sablon.read_text(encoding="utf-8"), origin=str(sablon))
        for mnozina, jednina, plural in POZIV_U_SABLONU.findall(izvor):
            jednina = ast.literal_eval(f"'{jednina}'")
            poruke[jednina] = ast.literal_eval(f"'{plural}'") if mnozina else None
    return poruke


def _iz_koda():
    poruke = {}
    for datoteka in sorted(APLIKACIJA.glob("*.py")):
        stablo = ast.parse(datoteka.read_text(encoding="utf-8"))
        for cvor in ast.walk(stablo):
            if (
                isinstance(cvor, ast.Call)
                and isinstance(cvor.func, ast.Name)
                and cvor.func.id in PREVODIVE_FUNKCIJE
                and cvor.args
                and isinstance(cvor.args[0], ast.Constant)
                and isinstance(cvor.args[0].value, str)
            ):
                poruke[cvor.args[0].value] = None
    return poruke


def izvuci_poruke():
    """Sve poruke za prevod: {msgid: msgid_plural ili None}."""
    return {**_iz_koda(), **_iz_sablona()}


def _prevodi_unosa(unos):
    return list(unos.msgstr_plural.values()) if unos.msgid_plural else [unos.msgstr]


def _zamene(tekst):
    return sorted(ZAMENA.findall(tekst))


def problemi(po, poruke):
    """Spisak problema u katalogu; prazan spisak znaci da je prevod potpun."""
    nadjeno = []
    unosi = {unos.msgid: unos for unos in po if not unos.obsolete}
    for msgid, plural in poruke.items():
        unos = unosi.get(msgid)
        if unos is None:
            nadjeno.append(f"nema prevoda: {msgid!r}")
            continue
        if (unos.msgid_plural or None) != plural:
            nadjeno.append(f"mnozina se razlikuje: {msgid!r}")
        if "fuzzy" in unos.flags:
            nadjeno.append(f"nesiguran prevod (fuzzy): {msgid!r}")
        for prevod in _prevodi_unosa(unos):
            if not prevod.strip():
                nadjeno.append(f"prazan prevod: {msgid!r}")
            elif _zamene(prevod) != _zamene(msgid):
                nadjeno.append(f"zamene se razlikuju: {msgid!r}")
    for msgid in sorted(set(unosi) - set(poruke)):
        nadjeno.append(f"visak u katalogu: {msgid!r}")
    return nadjeno


def mo_je_azuran(po):
    import polib

    if not MO.exists():
        return False
    ocekivano = {(u.msgid, tuple(_prevodi_unosa(u))) for u in po.translated_entries()}
    postojece = {(u.msgid, tuple(_prevodi_unosa(u))) for u in polib.mofile(str(MO)) if u.msgid}
    return ocekivano == postojece


def ucitaj_po():
    import polib

    if PO.exists():
        return polib.pofile(str(PO), wrapwidth=0)
    po = polib.POFile(wrapwidth=0)
    po.metadata = dict(METAPODACI)
    return po


def osvezi(po, poruke):
    """Dodaje nove poruke sa praznim prevodom i brise one kojih vise nema u kodu."""
    import polib

    postojece = {unos.msgid: unos for unos in po}
    for msgid, plural in poruke.items():
        if msgid in postojece:
            continue
        unos = polib.POEntry(msgid=msgid, msgstr="")
        if plural is not None:
            unos.msgid_plural = plural
            unos.msgstr_plural = {0: "", 1: ""}
        if ZAMENA.search(msgid):
            unos.flags.append("python-format")
        po.append(unos)
    for unos in list(po):
        if unos.msgid not in poruke:
            po.remove(unos)
    PO.parent.mkdir(parents=True, exist_ok=True)
    po.save(str(PO))
    po.save_as_mofile(str(MO))
