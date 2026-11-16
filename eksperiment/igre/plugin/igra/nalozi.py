"""Nalozi moderatora (plan 14.3, 14.5): ko je moderator i jedini put izmene naloga, za prikaze i za komande.

`uloga` i `moderatori` zive ovde, ne u moderacija.py: servisi (i brisanje.py) ih zovu pod bravom, a servis ne
uvozi modul prikaza. moderacija.py ih uvozi, pa je `moderacija.uloga` isti pomocnik.

Svaka radnja: transaction.atomic() (BEGIN IMMEDIATE, settings.py), ponovna provera onoga ko radi iz baze,
izmena, nepromenljiva pravila, zapis u dnevnik. Pravilo koje ne vazi baca Odbijeno, a izlazak iz atomic
ponistava sve sto je radnja do tada upisala. `ko=None` je komanda razvijaca.

Provera i hes lozinke (PBKDF2, stotine ms) idu pre brave: IMMEDIATE brava drzi celu SQLite bazu, pa bi potez
igraca za to vreme cekao i dobio "database is locked" (revizija 2026-11-11). Pod bravom radnja samo uporedi hes
u bazi sa procitanim (_isti_hes) i upise vec izracunat.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import Permission
from django.contrib.auth.password_validation import password_changed, validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.views.decorators.debug import sensitive_variables

from . import tekstovi
from .models import (
    LOZINKA_POSTAVLJENA,
    LOZINKA_PROMENJENA,
    MODERATOR_AKTIVIRAN,
    MODERATOR_DEAKTIVIRAN,
    MODERATOR_DODAT,
    ULOGA_DODELJENA,
    ULOGA_ODUZETA,
    NalogModeratora,
    ZapisDnevnika,
)

User = get_user_model()

MODERATOR = "moderator"
GLAVNI = "glavni"
MODERIRA = "moderira"
UPRAVLJA = "upravlja_nalozima"


class Odbijeno(Exception):
    """Radnja krsi pravilo; nista nije upisano.

    kod: nema_prava (onaj ko radi vise nema ulogu), ne_sebe, poslednji_glavni, nije_moderator, nije_aktivan,
    vec_aktivan, vec_glavni, nije_glavni, glavni_bez_moderira, lozinka_promenjena (hes u bazi nije onaj
    procitan pre brave).
    """

    def __init__(self, kod):
        super().__init__(kod)
        self.kod = kod


def _dozvola(kodnaziv):
    # Bez kesa ContentType-a: flush u TransactionTestCase pravi nove id-jeve tipova.
    return Permission.objects.get(
        content_type__app_label="igra", content_type__model="zapisdnevnika", codename=kodnaziv
    )


def uloga(korisnik):
    """None, "moderator" ili "glavni" (plan 14.3). Jedina provera uloge, za dekoratore i servise."""
    if not korisnik.is_authenticated or not korisnik.is_active or korisnik.is_superuser:
        # Superuser bi kroz has_perm imao svaku dozvolu; moderator nikad nije superuser.
        return None
    # RelatedObjectDoesNotExist je AttributeError: korisnik bez NalogModeratora nije moderator.
    if not hasattr(korisnik, "nalog_moderatora"):
        return None
    if not korisnik.has_perm(f"igra.{MODERIRA}"):
        return None
    return GLAVNI if korisnik.has_perm(f"igra.{UPRAVLJA}") else MODERATOR


def moderatori():
    """Jedini queryset korisnika na strani (plan 14.3): svi sa NalogModeratora, aktivni i neaktivni."""
    return User.objects.filter(nalog_moderatora__isnull=False).select_related("nalog_moderatora").order_by("username")


def aktivni_glavni():
    """Korisnici kojima uloga() vraca "glavni", istim uslovima, u jednom upitu (pravilo 1 iz 14.5)."""
    return (
        User.objects.filter(is_active=True, is_superuser=False, nalog_moderatora__isnull=False)
        .filter(user_permissions=_dozvola(MODERIRA))
        .filter(user_permissions=_dozvola(UPRAVLJA))
    )


def id_glavnih():
    """Id-jevi korisnika sa dozvolom upravlja_nalozima, aktivnih i neaktivnih (prikaz, ne provera prava)."""
    return set(_dozvola(UPRAVLJA).user_set.values_list("pk", flat=True))


def ime_zauzeto(ime):
    """Ime je zauzeto bez obzira na velika i mala slova, i za cirilicu.

    Ne username__iexact: na SQLite LIKE i LOWER razlikuju velika i mala slova van ASCII-ja ("Пера" i "пера").
    Tabela korisnika je mala (samo moderatori).
    """
    trazeno = ime.casefold()
    return any(
        postojece.casefold() == trazeno for postojece in User.objects.values_list("username", flat=True)
    )


def moderator_po_imenu(ime):
    """Moderator sa ovim imenom bez obzira na velika i mala slova, ili None (komande razvijaca)."""
    trazeno = User.normalize_username(ime).casefold()
    nadjeni = [k for k in moderatori() if k.get_username().casefold() == trazeno]
    return nadjeni[0] if len(nadjeni) == 1 else None


def proveri_ulogu(ko, potrebna, *, i_pre_promene=False):
    """Pod bravom: onaj ko radi, svez iz baze (bez starog _perm_cache), mora imati ulogu; vraca svez objekat.

    request.user je procitan pre brave, pa ga je istovremeni zahtev mozda vec deaktivirao ili mu oduzeo ulogu
    (plan 14.3, 14.5). Nalog sa obaveznom promenom lozinke radi samo promeni_svoju (i_pre_promene).
    """
    svez = User.objects.select_related("nalog_moderatora").filter(pk=ko.pk).first()
    nadjena = None if svez is None else uloga(svez)
    if nadjena is None or (potrebna == GLAVNI and nadjena != GLAVNI):
        raise Odbijeno("nema_prava")
    if svez.nalog_moderatora.mora_promeniti and not i_pre_promene:
        raise Odbijeno("nema_prava")
    return svez


def ima_aktivnog_glavnog():
    return aktivni_glavni().exists()


def _procitaj(nad):
    """Nalog nad kojim se radi, svez iz baze i kroz moderatori(): van opsega nema radnje."""
    svez = moderatori().filter(pk=nad.pk).first()
    if svez is None:
        raise Odbijeno("nije_moderator")
    return svez


def _postoji_glavni():
    # Pravilo 1: posle izmene ostaje bar jedan aktivan glavni. Proverava se posle radnji koje ga mogu
    # oboriti (dodaj bez uloge, deaktiviraj, oduzmi_ulogu); ostale ne smanjuju broj glavnih, a u stanju bez
    # glavnog ne smeju da zatvore put oporavka (moderator_lozinka, pa moderator_glavni).
    if not ima_aktivnog_glavnog():
        raise Odbijeno("poslednji_glavni")


def _glavni_je_moderator(korisnik):
    # Pravilo 3: upravlja_nalozima bez moderira je nemoguc.
    kodovi = set(korisnik.user_permissions.filter(content_type__app_label="igra").values_list("codename", flat=True))
    if UPRAVLJA in kodovi and MODERIRA not in kodovi:
        raise Odbijeno("glavni_bez_moderira")


def _zahtevaj_promenu(korisnik):
    nalog = korisnik.nalog_moderatora
    nalog.mora_promeniti = True
    nalog.save(update_fields=["mora_promeniti"])


def _upisi(radnja, ko, nad, snimak=None):
    return ZapisDnevnika.objects.upisi(radnja=radnja, ko=ko, nad=nad, snimak={} if snimak is None else snimak)


@sensitive_variables("lozinka")
def _hes(lozinka, korisnik):
    """Validatori i PBKDF2, pre brave. ValidationError ako lozinka ne prolazi validatore."""
    validate_password(lozinka, korisnik)
    return make_password(lozinka)


def _isti_hes(procitan):
    """Pod bravom: nalog svez iz baze, sa istim hesom kao procitan pre brave; inace Odbijeno.

    Lozinka je proverena i nov hes izracunat pre brave. Ako je u medjuvremenu neko promenio lozinku, radnja bi
    pregazila tu promenu, a stara lozinka bi bila proverena protiv hesa koji vise ne vazi.
    """
    svez = _procitaj(procitan)
    if svez.password != procitan.password:
        raise Odbijeno("lozinka_promenjena")
    return svez


@sensitive_variables("lozinka", "hes")
def _upisi_hes(korisnik, hes, lozinka, *polja):
    """Pod bravom samo upis vec izracunatog hesa; isto sto set_password pa save, i password_changed."""
    korisnik.password = hes
    korisnik.save(update_fields=["password", *polja])
    password_changed(lozinka, korisnik)


@sensitive_variables("lozinka", "hes")
def dodaj(ko, ime, lozinka, glavni=False):
    """Nov moderator sa pocetnom lozinkom (mora_promeniti); uz glavni i dozvola upravlja_nalozima.

    ValidationError za ime ili lozinku; Odbijeno("poslednji_glavni") ako bez uloge nastaje bez aktivnog glavnog.
    """
    glavni = bool(glavni)
    ime = User.normalize_username(ime)
    korisnik = User(username=ime, is_active=True, is_staff=False, is_superuser=False)
    hes = _hes(lozinka, korisnik)
    with transaction.atomic():
        if ko is not None:
            ko = proveri_ulogu(ko, GLAVNI)
        if ime_zauzeto(ime):
            raise ValidationError(User._meta.get_field("username").error_messages["unique"], code="unique")
        korisnik.password = hes
        korisnik.full_clean()  # UnicodeUsernameValidator i duzina imena
        korisnik.save(force_insert=True)
        password_changed(lozinka, korisnik)
        korisnik.user_permissions.add(_dozvola(MODERIRA))
        if glavni:
            korisnik.user_permissions.add(_dozvola(UPRAVLJA))
        nalog = NalogModeratora(korisnik=korisnik, mora_promeniti=True)
        nalog.full_clean()
        nalog.save(force_insert=True)
        _glavni_je_moderator(korisnik)
        _postoji_glavni()
        _upisi(MODERATOR_DODAT, ko, korisnik, {"glavni": glavni})
    return korisnik


def deaktiviraj(ko, nad):
    """Nalog vise ne moze da se prijavi; postojece sesije od sledeceg zahteva su anonimne. Uloga glavnog se oduzima."""
    with transaction.atomic():
        if ko is not None:
            ko = proveri_ulogu(ko, GLAVNI)
        nad = _procitaj(nad)
        if ko is not None and nad.pk == ko.pk:
            raise Odbijeno("ne_sebe")
        if not nad.is_active:
            raise Odbijeno("nije_aktivan")
        bio_glavni = nad.pk in id_glavnih()
        nad.is_active = False
        nad.save(update_fields=["is_active"])
        if bio_glavni:
            nad.user_permissions.remove(_dozvola(UPRAVLJA))
        _postoji_glavni()
        _upisi(MODERATOR_DEAKTIVIRAN, ko, nad, {"glavni": bio_glavni})
    return nad


@sensitive_variables("lozinka", "hes")
def aktiviraj(ko, nad, lozinka):
    """Neaktivan nalog dobija novu pocetnu lozinku i vraca se kao obican moderator."""
    procitan = _procitaj(nad)
    if procitan.is_active:
        raise Odbijeno("vec_aktivan")
    hes = _hes(lozinka, procitan)
    with transaction.atomic():
        if ko is not None:
            ko = proveri_ulogu(ko, GLAVNI)
        nad = _isti_hes(procitan)
        if nad.is_active:
            raise Odbijeno("vec_aktivan")
        nad.is_active = True
        _upisi_hes(nad, hes, lozinka, "is_active")
        # Uloga se pri deaktivaciji vec oduzima; ovde i za nalog deaktiviran mimo servisa.
        nad.user_permissions.remove(_dozvola(UPRAVLJA))
        _zahtevaj_promenu(nad)
        _glavni_je_moderator(nad)
        _upisi(MODERATOR_AKTIVIRAN, ko, nad)
    return nad


@sensitive_variables("lozinka", "hes")
def postavi_lozinku(ko, nad, lozinka):
    """Nova pocetna lozinka tudjeg naloga; promena hesa gasi sve sesije vlasnika (i njegovu partiju)."""
    if ko is not None and nad.pk == ko.pk:
        raise Odbijeno("ne_sebe")  # sopstvenu lozinku menja promeni_svoju, uz staru
    procitan = _procitaj(nad)
    hes = _hes(lozinka, procitan)
    with transaction.atomic():
        if ko is not None:
            ko = proveri_ulogu(ko, GLAVNI)
        nad = _isti_hes(procitan)
        _upisi_hes(nad, hes, lozinka)
        _zahtevaj_promenu(nad)
        _upisi(LOZINKA_POSTAVLJENA, ko, nad)
    return nad


def dodeli_ulogu(ko, nad):
    """Aktivan obican moderator postaje glavni."""
    with transaction.atomic():
        if ko is not None:
            ko = proveri_ulogu(ko, GLAVNI)
        nad = _procitaj(nad)
        sada = uloga(nad)
        if sada == GLAVNI:
            raise Odbijeno("vec_glavni")
        if sada is None:
            raise Odbijeno("nije_aktivan")
        nad.user_permissions.add(_dozvola(UPRAVLJA))
        _glavni_je_moderator(nad)
        _upisi(ULOGA_DODELJENA, ko, nad)
    return nad


def oduzmi_ulogu(ko, nad):
    """Glavni postaje obican moderator; dozvoljeno i sebi, ali ne poslednjem aktivnom glavnom."""
    with transaction.atomic():
        if ko is not None:
            ko = proveri_ulogu(ko, GLAVNI)
        nad = _procitaj(nad)
        if nad.pk not in id_glavnih():
            raise Odbijeno("nije_glavni")
        nad.user_permissions.remove(_dozvola(UPRAVLJA))
        _postoji_glavni()
        _upisi(ULOGA_ODUZETA, ko, nad)
    return nad


@sensitive_variables("stara", "nova", "hes")
def promeni_svoju(korisnik, stara, nova):
    """Moderator menja sopstvenu lozinku uz staru; skida obaveznu promenu. Vraca svez objekat.

    Prikaz posle zove update_session_auth_hash sa vracenim objektom, pa sesija (i partija) ostaje.
    ValidationError ako stara nije tacna, ako je nova ista kao stara ili ako nova ne prolazi validatore.
    """
    procitan = proveri_ulogu(korisnik, MODERATOR, i_pre_promene=True)
    # Bez settera: nadogradnju hesa ionako zamenjuje nov hes ispod.
    if not check_password(stara, procitan.password):
        raise ValidationError(tekstovi.POGRESNA_LOZINKA, code="pogresna_lozinka")
    if nova == stara:
        # Stara je tacna, pa je ovo i tekuca lozinka: obavezna promena pocetne inace ne bi nista promenila.
        raise ValidationError(tekstovi.ISTA_LOZINKA, code="ista_lozinka")
    hes = _hes(nova, procitan)
    with transaction.atomic():
        svez = proveri_ulogu(korisnik, MODERATOR, i_pre_promene=True)
        if svez.password != procitan.password:
            raise Odbijeno("lozinka_promenjena")
        _upisi_hes(svez, hes, nova)
        nalog = svez.nalog_moderatora
        nalog.mora_promeniti = False
        nalog.save(update_fields=["mora_promeniti"])
        _upisi(LOZINKA_PROMENJENA, svez, svez)
    return svez
