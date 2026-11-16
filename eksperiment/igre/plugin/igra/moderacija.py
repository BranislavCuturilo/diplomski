"""Moderatorske strane (plan 14.3, 14.7, ugovor 14.9): obicne forme sa POST i preusmerenjem, bez skripte.

Svaka ruta osim prijave stoji pod moderator_potreban; rute nalozi* pod glavni_potreban (403). Brisanje, i odluka
da prijavljeno ime ostaje, ide samo kroz brisanje.py, radnje nad nalozima samo kroz nalozi.py; oba ponovo
proveravaju ulogu pod bravom.
`uloga` i `moderatori` su iz nalozi.py (jedan pomocnik). Datume formatira prikaz (tekstovi), sablon ih ispisuje.
Nijedan prikaz ne salje partiju, seme, token ni id reda dnevnika.
"""

import csv
import re
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from functools import wraps

from django.conf import settings
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import ValidationError
from django.db.models import Count, Min, Q
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseNotFound, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from . import brisanje, forme, nalozi, tekstovi, views
from . import parametri as p
from .models import LINK_OBRISAN, MODERATOR_DEAKTIVIRAN, MODERATOR_DODAT, RADNJE_NAD_REDOM, REZULTAT_OBRISAN
from .models import DeljeniRezultat, Rezultat, ZapisDnevnika
from .models import ZavrsenaPartija
from .nalozi import GLAVNI, moderatori, uloga
from .views import OBLIK_TOKENA

PREGLED_REDOVA = 50
DNEVNIK_REDOVA = 100
PORUKE_PREGLEDA = ("obrisano", "vec_obrisano", "ostavljeno", "vec_reseno")
# Najveci id koji SQLite INTEGER prima; veci broj iz URL-a dao bi OverflowError (500), ovako isti 404.
NAJVECI_ID = 2**63 - 1
# Nalepljen link: token je deo posle /r/; inace se ceo unos uzima kao token.
TOKEN_IZ_LINKA = re.compile(r"/r/([^/?#]*)")
NAJDUZI_UNOS_LINKA = 2048
RADNJE_NALOGA = ("deaktiviraj", "aktiviraj", "lozinka", "dodeli_ulogu", "oduzmi_ulogu")
# Sablon ume da kaze ne_sebe i poslednji_glavni; ostali kodovi Odbijeno, i ovaj, daju opstu poruku.
ODBIJENO_NEDOZVOLJENO = "nije_dozvoljeno"


# ---------- zajednicko ----------


def _kontekst(request, **dodatno):
    """Kontekst svih strana (ugovor 14.9): glavni (bool) i ja (ime prijavljenog moderatora ili None)."""
    nadjena = uloga(request.user)
    return {"glavni": nadjena == GLAVNI, "ja": request.user.get_username() if nadjena else None, **dodatno}


def _zabranjeno(request):
    # Isto telo za svaku rutu nalozi* i svaki id; id se jos ne cita (plan 14.3). Sablon na jeziku korisnika.
    return render(request, "igra/moderator/zabranjeno.html", _kontekst(request), status=403)


def _nema():
    # Isti prazan 404 za svaki nepostojeci id. Ne Http404: uz DEBUG = True Django prikazuje spisak ruta.
    return HttpResponseNotFound()


def _ponovo(request):
    # Uloga se promenila izmedju dekoratora i brave (Odbijeno nema_prava): GET iste strane, dekorator odlucuje.
    return redirect(request.path)


def moderator_potreban(prikaz=None, *, i_pre_promene=False):
    """1. nije moderator: 302 na prijavu (GET i POST); 2. mora_promeniti: 302 na lozinku.

    i_pre_promene propusta nalog sa obaveznom promenom (samo lozinka i odjava).
    """

    def dekorator(prikaz):
        @wraps(prikaz)
        def omotac(request, *args, **kwargs):
            if uloga(request.user) is None:
                return redirect_to_login(request.get_full_path())
            if request.user.nalog_moderatora.mora_promeniti and not i_pre_promene:
                return redirect("moderator_lozinka")
            return prikaz(request, *args, **kwargs)

        return omotac

    return dekorator if prikaz is None else dekorator(prikaz)


def glavni_potreban(prikaz):
    """moderator_potreban, pa 3. uloga nije glavni: 403 (plan 14.3)."""

    @moderator_potreban
    @wraps(prikaz)
    def omotac(request, *args, **kwargs):
        if uloga(request.user) != GLAVNI:
            return _zabranjeno(request)
        return prikaz(request, *args, **kwargs)

    return omotac


# ---------- opis redova za sablon (bela lista) ----------


def _rezultati(danas):
    """Isti skup za obe liste i za potvrdu brisanja rezultata (plan 14.3, uslov 2): glavna lista i lista danas.

    Starije dnevne redove brise samo komanda rezultat_obrisi (odluka 7 dnevnog izazova).
    """
    return Rezultat.objects.glavna() | Rezultat.objects.dana(danas)


def _prijavljeni(danas):
    """Rezultati sa bar jednom prijavom imena, u istom opsegu kao brisanje (_rezultati).

    Najvise prijava prvo, kod jednakih starija prva prijava; svaki red nosi broj_prijava i prva_prijava.
    """
    return (
        _rezultati(danas)
        .annotate(broj_prijava=Count("prijave"), prva_prijava=Min("prijave__kada"))
        .filter(broj_prijava__gt=0)
        .order_by("-broj_prijava", "prva_prijava", "id")
    )


def _lista_reda(red):
    # Lista kojoj red pripada: glavna ili lista njegovog dana.
    return Rezultat.objects.glavna() if red.dan is None else Rezultat.objects.dana(red.dan)


def _deljeni(sada):
    """Isti queryset za listu, pretragu i potvrdu brisanja linka: samo vazeci, najnoviji prvi."""
    return DeljeniRezultat.objects.vazeci(sada).order_by("-nastao", "-id")


def _opis_rezultata(red, mesto, danas):
    return {
        "id": red.id,
        "mesto": mesto,
        "ime": red.ime,
        "poeni": red.poeni,
        "ocena": tekstovi.ocena(red.ocena),
        "datum": tekstovi.datum(red.sacuvan),
        # Javno: medju RANG_MESTA na listi koja je na ekranu igraca (glavna ili danasnja; ranijih dana nema).
        "javno": mesto <= p.RANG_MESTA and (red.dan is None or red.dan == danas),
        # Dan dnevnog izazova u formatu jezika, None za glavnu listu.
        "dan": None if red.dan is None else views._datum_dana(red.dan),
    }


def _mesto(red):
    # Broj redova iznad na listi reda (isti redosled kao po_rangu: poeni, sacuvan, id) + 1; liste se ne mesaju.
    iznad = Q(poeni__gt=red.poeni) | Q(poeni=red.poeni, sacuvan__lt=red.sacuvan) | Q(
        poeni=red.poeni, sacuvan=red.sacuvan, id__lt=red.id
    )
    return _lista_reda(red).filter(iznad).count() + 1


def _opis_prijavljenog(red, mesto, danas):
    # Red iz _prijavljeni: opis rezultata, broj prijava (najvise PRIJAVA_NAJVISE) i trenutak prve. Bez traga sesije.
    return {
        **_opis_rezultata(red, mesto, danas),
        "prijava": red.broj_prijava,
        "prva_prijava": tekstovi.datum_vreme(red.prva_prijava),
    }


def _opis_linka(red, imena):
    # Bez tokena i partije.
    return {
        "id": red.id,
        "ime": imena.get(red.partija),
        "poeni": red.zavrsni["poeni"],
        "ocena": tekstovi.ocena(red.zavrsni["ocena"]),
        "nastao": tekstovi.datum(red.nastao),
        "istice": tekstovi.datum(red.istice),
    }


def _opis_naloga(korisnik, glavni_ids, ja):
    return {
        "id": korisnik.pk,
        "ime": korisnik.get_username(),
        "aktivan": korisnik.is_active,
        "glavni": korisnik.pk in glavni_ids,
        "poslednja_prijava": None if korisnik.last_login is None else tekstovi.datum_vreme(korisnik.last_login),
        "mora_promeniti": korisnik.nalog_moderatora.mora_promeniti,
        "ja": korisnik.pk == ja.pk,
    }


def _opis_snimka(zapis):
    if zapis.radnja in RADNJE_NAD_REDOM:
        snimak = zapis.snimak
        opis = {
            "ime": snimak["ime"],
            "poeni": snimak["poeni"],
            "ocena": tekstovi.ocena(snimak["ocena"]),
            "datum": tekstovi.datum(datetime.fromisoformat(snimak["datum"])),
        }
        # Samo zapis dnevnog reda nosi "dan" (brisanje._snimak), pa i opis; sablon ga prikazuje kao oznaku.
        if "dan" in snimak:
            opis["dan"] = views._datum_dana(date.fromisoformat(snimak["dan"]))
        return opis
    if zapis.radnja in (MODERATOR_DODAT, MODERATOR_DEAKTIVIRAN):
        return {"glavni": bool(zapis.snimak.get("glavni"))}
    return None


def _opis_zapisa(zapis):
    # Bela lista (plan 14.7): nikad partija ni red. radnja je kljuc; tekst bira sablon.
    return {
        "kada": tekstovi.datum_vreme(zapis.kada),
        "ko": None if zapis.ko is None else zapis.ko.get_username(),
        "radnja": zapis.radnja,
        "nad": None if zapis.nad is None else zapis.nad.get_username(),
        "snimak": _opis_snimka(zapis),
    }


# ---------- prijava i odjava ----------


def _sledeca(request):
    """next iz forme ili upita: samo putanja na ovom sajtu (pocinje sa "/"); inace prazno.

    Ime rute ili relativna adresa ("foo") se ne prihvata: redirect() bi je pokusao kao ime rute i posle uspesne
    prijave dao NoReverseMatch, 500 (revizija 2026-11-11).
    """
    sledeca = request.POST.get("next") or request.GET.get("next") or ""
    if sledeca.startswith("/") and url_has_allowed_host_and_scheme(
        sledeca, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return sledeca
    return ""


@sensitive_post_parameters("password")
@never_cache
@require_http_methods(["GET", "POST"])
def prijava(request):
    sledeca = _sledeca(request)
    blokirano = None
    if request.method == "POST":
        # Brojac pokusaja je u formi: pokusaj se rezervise pre authenticate (forme.rezervisi_pokusaj).
        forma = forme.PrijavaForma(request, data=request.POST)
        if forma.is_valid():
            # cycle_key: nov kljuc, isti podaci, pa partija u toku ostaje; rotate_token: nov CSRF kolacic.
            login(request, forma.get_user())
            request.session.set_expiry(settings.MODERATOR_SESIJA_SEKUNDI)
            return HttpResponseRedirect(sledeca) if sledeca else redirect("moderator")
        blokirano = forma.blokirano
        if blokirano is not None:
            # Poruka blokade stoji jednom (blokirano u sablonu), forma je prazna.
            forma = forme.PrijavaForma(request)
    else:
        forma = forme.PrijavaForma(request)
    kontekst = _kontekst(request, form=forma, next=sledeca, blokirano=blokirano)
    return render(request, "igra/moderator/prijava.html", kontekst)


@never_cache
@moderator_potreban(i_pre_promene=True)
@require_POST
def odjava(request):
    # logout() brise sesiju, a s njom i partije; obe (obicna i dnevna) i istorija pregledaca se prenose u novu sesiju
    # (plan 14.2).
    partije = {kljuc: request.session.get(kljuc) for kljuc in (*views.SESIJA.values(), "istorija")}
    logout(request)
    for kljuc, stanje in partije.items():
        if stanje is not None:
            request.session[kljuc] = stanje
    return redirect("moderator_prijava")


# ---------- pregled i brisanje ----------


def _token_iz_unosa(unos):
    unos = unos.strip()
    if len(unos) > NAJDUZI_UNOS_LINKA:
        return None
    nadjen = TOKEN_IZ_LINKA.search(unos)
    token = nadjen.group(1) if nadjen else unos
    return token if OBLIK_TOKENA.fullmatch(token) else None


@never_cache
@moderator_potreban
@require_http_methods(["GET", "POST"])
def pregled(request):
    sada = timezone.now()
    # Nepoznata vrednost se ignorise; sablon dobija samo poznat kod.
    poruka = request.GET.get("poruka")
    if poruka not in PORUKE_PREGLEDA:
        poruka = None

    linkovi = list(_deljeni(sada)[:PREGLED_REDOVA])
    pronadjen_red = None
    if request.method == "POST":
        # Pretraga linka: POST, da token ne ostane u URL-u ni u logu. Istekao, nepostojeci i neispravan isto.
        token = _token_iz_unosa(request.POST.get("token", ""))
        if token is not None:
            pronadjen_red = _deljeni(sada).filter(token=token).first()
    imena = Rezultat.objects.imena_po_partiji(
        [red.partija for red in linkovi] + ([pronadjen_red.partija] if pronadjen_red else [])
    )
    if request.method != "POST":
        pronadjen = None  # pretrage nije bilo
    elif pronadjen_red is None:
        pronadjen = False  # trazen, nije nadjen
    else:
        pronadjen = _opis_linka(pronadjen_red, imena)

    danas = views._danas()
    glavna = list(Rezultat.objects.glavna().po_rangu()[:PREGLED_REDOVA])
    dana = list(Rezultat.objects.dana(danas).po_rangu()[:PREGLED_REDOVA])
    # Mesto prijavljenog reda je vec u dve liste iznad; svoj upit trazi samo red ispod PREGLED_REDOVA.
    mesta = {red.id: mesto for lista in (glavna, dana) for mesto, red in enumerate(lista, start=1)}
    kontekst = _kontekst(
        request,
        prijavljeni=[
            _opis_prijavljenog(red, mesta.get(red.id) or _mesto(red), danas)
            for red in _prijavljeni(danas)[:PREGLED_REDOVA]
        ],
        rezultati=[_opis_rezultata(red, mesto, danas) for mesto, red in enumerate(glavna, start=1)],
        rezultati_dana=[_opis_rezultata(red, mesto, danas) for mesto, red in enumerate(dana, start=1)],
        deljeni=[_opis_linka(red, imena) for red in linkovi],
        pronadjen=pronadjen,
        poruka=poruka,
    )
    return render(request, "igra/moderator/pregled.html", kontekst)


# ---------- izvoz rang liste (CSV za Excel) ----------

# Znak kojim Excel pocinje formulu (CSV injection) dobija apostrof ispred sebe: na pocetku celije i posle
# zareza, jer Excel sa zarezom kao separatorom deli "x,=1+1" na dve celije.
FORMULA_U_CELIJI = re.compile(r"(^|,)(\s*)(?=[=+\-@\t\r])")


def _celija(vrednost):
    return FORMULA_U_CELIJI.sub(lambda nadjeno: nadjeno.group(1) + nadjeno.group(2) + "'", str(vrednost))


def _csv(redovi, ime_datoteke):
    """Cela lista, bez granice PREGLED_REDOVA. UTF-8 sa BOM i ';': Excel sa srpskim podesavanjima otvara ga dvoklikom."""
    odgovor = HttpResponse(content_type="text/csv; charset=utf-8")
    odgovor["Content-Disposition"] = f'attachment; filename="{ime_datoteke}"'
    odgovor.write("\ufeff")
    pisac = csv.writer(odgovor, delimiter=";", lineterminator="\r\n")
    pisac.writerow([gettext("Место"), gettext("Име"), gettext("Поени"), gettext("Оцена"), gettext("Сачуван")])
    for mesto, red in enumerate(redovi.iterator(), start=1):
        pisac.writerow(
            [mesto, _celija(red.ime), red.poeni, _celija(tekstovi.ocena(red.ocena)), tekstovi.datum_vreme(red.sacuvan)]
        )
    return odgovor


@never_cache
@moderator_potreban
@require_GET
def izvoz_glavne(request):
    return _csv(Rezultat.objects.glavna().po_rangu(), "rang-lista.csv")


@never_cache
@moderator_potreban
@require_GET
def izvoz_dana(request):
    danas = views._danas()
    return _csv(Rezultat.objects.dana(danas).po_rangu(), f"dnevni-izazov-{danas.isoformat()}.csv")


def _vec_obrisano_ili_nema(radnja, broj):
    # Reda nema: ako ga je dnevnik zabelezio kao obrisan, poruka; inace isti 404 kao za nepostojeci id.
    if ZapisDnevnika.objects.obrisan_red(radnja, broj):
        return redirect(reverse("moderator") + "?poruka=vec_obrisano")
    return _nema()


def _potvrda(request, broj, vrsta, red, radnja, obrisi, opis, ruta):
    """GET prikazuje snimak i ne menja nista; POST brise kroz servis, pa PRG na pregled."""
    if red is None:
        return _vec_obrisano_ili_nema(radnja, broj)
    if request.method == "POST":
        try:
            obrisi([red.id], ko=request.user)
        except brisanje.NemaReda:
            # Obrisan izmedju citanja i brave (drugi moderator).
            return _vec_obrisano_ili_nema(radnja, broj)
        except nalozi.Odbijeno:
            return _ponovo(request)
        return redirect(reverse("moderator") + "?poruka=obrisano")
    kontekst = _kontekst(request, vrsta=vrsta, red=opis(red), akcija=reverse(ruta, args=[red.id]))
    return render(request, "igra/moderator/potvrda.html", kontekst)


@never_cache
@moderator_potreban
@require_http_methods(["GET", "POST"])
def rezultat(request, broj):
    danas = views._danas()
    red = None if broj > NAJVECI_ID else _rezultati(danas).filter(pk=broj).first()
    return _potvrda(
        request, broj, "rezultat", red, REZULTAT_OBRISAN, brisanje.obrisi_rezultate,
        lambda r: _opis_rezultata(r, _mesto(r), danas), "moderator_rezultat",
    )


@never_cache
@moderator_potreban
@require_POST
def ostavi(request, broj):
    """Prijavljeno ime ostaje: prijave se brisu, a odluka ide u dnevnik (brisanje.odbaci_prijave); PRG na pregled.

    Opseg je isti kao za brisanje rezultata (_rezultati). Bez strane potvrde: nista javno se ne menja, a rezultat
    se i posle ove odluke moze obrisati sa pregleda.
    """
    red = None if broj > NAJVECI_ID else _rezultati(views._danas()).filter(pk=broj).first()
    if red is None:
        return _vec_obrisano_ili_nema(REZULTAT_OBRISAN, broj)
    try:
        brisanje.odbaci_prijave([red.id], ko=request.user)
    except brisanje.NemaReda:
        # Obrisan izmedju citanja i brave (drugi moderator).
        return _vec_obrisano_ili_nema(REZULTAT_OBRISAN, broj)
    except brisanje.NemaPrijava:
        # Drugi moderator je vec odlucio, ili prijave nije ni bilo: nista se ne upisuje.
        return redirect(reverse("moderator") + "?poruka=vec_reseno")
    except nalozi.Odbijeno:
        # Uloga se promenila izmedju dekoratora i brave. Ruta je samo POST, pa odlucuje dekorator pregleda.
        return redirect("moderator")
    return redirect(reverse("moderator") + "?poruka=ostavljeno")


@never_cache
@moderator_potreban
@require_http_methods(["GET", "POST"])
def link(request, broj):
    red = None if broj > NAJVECI_ID else _deljeni(timezone.now()).filter(pk=broj).first()
    return _potvrda(
        request, broj, "link", red, LINK_OBRISAN, brisanje.obrisi_deljene,
        lambda r: _opis_linka(r, Rezultat.objects.imena_po_partiji([r.partija])), "moderator_link",
    )


@never_cache
@moderator_potreban
@require_GET
def dnevnik(request):
    zapisi = ZapisDnevnika.objects.najnoviji().select_related("ko", "nad")[:DNEVNIK_REDOVA]
    kontekst = _kontekst(request, zapisi=[_opis_zapisa(zapis) for zapis in zapisi])
    return render(request, "igra/moderator/dnevnik.html", kontekst)


# ---------- statistika ----------

# Prosek bez partija; nije rec, pa se ne prevodi.
BEZ_PROSEKA = "—"
JEDNA_DECIMALA = Decimal("0.1")


def _prosek(vrednost):
    """Prosek poena sa jednom decimalom (pola navise) i decimalnim zarezom jezika (tekstovi.FORMATI)."""
    if vrednost is None:
        return BEZ_PROSEKA
    # str(), ne Decimal(float): 72.25 ostaje 72.25, pa ide na 72.3, a ne na binarnu vrednost ispod nje.
    zaokruzeno = Decimal(str(vrednost)).quantize(JEDNA_DECIMALA, rounding=ROUND_HALF_UP)
    return str(zaokruzeno).replace(".", tekstovi._format()["zarez"])


def _opis_dana(dan, red):
    # red je iz ZavrsenaPartija.objects.po_danu, ili None za dan bez partija.
    return {
        "datum": views._datum_dana(dan),
        "ukupno": red["ukupno"] if red else 0,
        "obicnih": red["obicnih"] if red else 0,
        "dnevnih": red["dnevnih"] if red else 0,
        "prosek": _prosek(red["prosek"] if red else None),
    }


@never_cache
@moderator_potreban
@require_GET
def statistika(request):
    """Zavrsene partije po danu (views._zabelezi_zavrsenu): danas i STATISTIKA_DANA - 1 prethodnih, najnoviji prvi.

    Brojevi su iz jednog upita (ZavrsenaPartija.objects.po_danu); dan bez partija dobija 0 i "—".
    """
    danas = views._danas()
    dani = [danas - timedelta(days=pomak) for pomak in range(views.STATISTIKA_DANA)]
    po_danu = ZavrsenaPartija.objects.po_danu(dani[-1], danas)
    kontekst = _kontekst(request, dani=[_opis_dana(dan, po_danu.get(dan)) for dan in dani])
    return render(request, "igra/moderator/statistika.html", kontekst)


# ---------- lozinka i nalozi ----------


@sensitive_post_parameters("old_password", "new_password1", "new_password2")
@never_cache
@moderator_potreban(i_pre_promene=True)
@require_http_methods(["GET", "POST"])
def lozinka(request):
    if request.method == "POST":
        forma = forme.PromenaLozinkeForma(request.user, data=request.POST)
        if forma.is_valid():
            try:
                korisnik = nalozi.promeni_svoju(
                    request.user, forma.cleaned_data["old_password"], forma.cleaned_data["new_password1"]
                )
            except nalozi.Odbijeno:
                # nema_prava, ili lozinka_promenjena: druga promena je stigla izmedju citanja i brave.
                return _ponovo(request)
            except ValidationError as greska:
                forma.add_error(None, ValidationError(greska.messages))
            else:
                # Nov hes u sesiji: sesija (i partija) ostaje, ostale sesije ovog naloga su ugasene.
                update_session_auth_hash(request, korisnik)
                return redirect("moderator")
    else:
        forma = forme.PromenaLozinkeForma(request.user)
    obavezna = request.user.nalog_moderatora.mora_promeniti
    return render(request, "igra/moderator/lozinka.html", _kontekst(request, form=forma, obavezna=obavezna))


@sensitive_post_parameters("lozinka1", "lozinka2", "moja_lozinka")
@never_cache
@glavni_potreban
@require_http_methods(["GET", "POST"])
def spisak_naloga(request):
    odbijeno = None
    if request.method == "POST":
        forma = forme.DodajForma(request.user, data=request.POST)
        if forma.is_valid():
            podaci = forma.cleaned_data
            try:
                nalozi.dodaj(request.user, podaci["ime"], podaci["lozinka1"], glavni=podaci["glavni"])
            except nalozi.Odbijeno as greska:
                if greska.kod == "nema_prava":
                    return _ponovo(request)
                odbijeno = greska.kod
            except ValidationError as greska:
                # Npr. isto ime upisano izmedju forme i brave.
                forma.add_error(None, ValidationError(greska.messages))
            else:
                return redirect("moderator_nalozi")
    else:
        forma = forme.DodajForma(request.user)
    glavni_ids = nalozi.id_glavnih()
    kontekst = _kontekst(
        request,
        nalozi=[_opis_naloga(k, glavni_ids, request.user) for k in moderatori()],
        forma=forma,
        odbijeno=odbijeno,
    )
    return render(request, "igra/moderator/nalozi.html", kontekst)


def _dozvoljene_radnje(ja, nad, glavni_ids, broj_glavnih):
    """Radnje koje strana nudi u ovom stanju; servis ih i dalje proverava (plan 14.7)."""
    radnje = []
    if not nad.is_active:
        return ["aktiviraj"]
    sebe = nad.pk == ja.pk
    if not sebe:
        radnje += ["deaktiviraj", "lozinka"]  # sopstveni nalog: nema deaktivacije, lozinka ide uz staru
    if nad.pk not in glavni_ids:
        radnje.append("dodeli_ulogu")
    elif broj_glavnih > 1:
        radnje.append("oduzmi_ulogu")  # ne nudi se poslednjem aktivnom glavnom
    return radnje


def _forma_radnje(radnja, ko, nad, data=None):
    # auto_id po radnji: vise formi na strani ima polje moja_lozinka.
    auto_id = f"id_{radnja}_%s"
    if radnja in ("aktiviraj", "lozinka"):
        return forme.LozinkaNalogaForma(ko, nad, data=data, auto_id=auto_id)
    return forme.PotvrdaForma(ko, data=data, auto_id=auto_id)


def _izvrsi(radnja, ko, nad, podaci):
    if radnja == "deaktiviraj":
        nalozi.deaktiviraj(ko, nad)
    elif radnja == "aktiviraj":
        nalozi.aktiviraj(ko, nad, podaci["lozinka1"])
    elif radnja == "lozinka":
        nalozi.postavi_lozinku(ko, nad, podaci["lozinka1"])
    elif radnja == "dodeli_ulogu":
        nalozi.dodeli_ulogu(ko, nad)
    else:
        nalozi.oduzmi_ulogu(ko, nad)


def _stanje_naloga(request, broj):
    nad = moderatori().filter(pk=broj).first()
    glavni_ids = nalozi.id_glavnih()
    if nad is None:
        return None, glavni_ids, []
    radnje = _dozvoljene_radnje(request.user, nad, glavni_ids, nalozi.aktivni_glavni().count())
    return nad, glavni_ids, radnje


@sensitive_post_parameters("lozinka1", "lozinka2", "moja_lozinka")
@never_cache
@glavni_potreban
@require_http_methods(["GET", "POST"])
def nalog(request, broj):
    # Uloga glavni je vec proverena (dekorator), pa id van moderatori() daje 404 tek sada (plan 14.3).
    if broj > NAJVECI_ID:
        return _nema()
    nad, glavni_ids, radnje = _stanje_naloga(request, broj)
    if nad is None:
        return _nema()
    forme_radnji = {radnja: _forma_radnje(radnja, request.user, nad) for radnja in radnje}
    odbijeno = None

    if request.method == "POST":
        radnja = request.POST.get("radnja")
        if radnja not in RADNJE_NALOGA:
            return HttpResponseBadRequest()
        if radnja not in radnje:
            # Strana je zastarela (stanje se promenilo) ili radnja nije ponudjena: nista se ne radi.
            odbijeno = ODBIJENO_NEDOZVOLJENO
        else:
            forma = _forma_radnje(radnja, request.user, nad, data=request.POST)
            forme_radnji[radnja] = forma
            if forma.is_valid():
                try:
                    _izvrsi(radnja, request.user, nad, forma.cleaned_data)
                except nalozi.Odbijeno as greska:
                    if greska.kod == "nema_prava":
                        return _ponovo(request)
                    odbijeno = greska.kod
                    # Stanje se mozda promenilo pod bravom: strana pokazuje tekuce radnje.
                    nad, glavni_ids, radnje = _stanje_naloga(request, broj)
                    if nad is None:
                        return _nema()
                    forme_radnji = {r: _forma_radnje(r, request.user, nad) for r in radnje}
                except ValidationError as greska:
                    forma.add_error(None, ValidationError(greska.messages))
                else:
                    if radnja == "oduzmi_ulogu" and nad.pk == request.user.pk:
                        return redirect("moderator")  # vise nije glavni; strana naloga bi dala 403
                    return redirect("moderator_nalozi_nalog", broj=nad.pk)

    kontekst = _kontekst(
        request,
        nalog=_opis_naloga(nad, glavni_ids, request.user),
        radnje=radnje,
        forme=forme_radnji,
        odbijeno=odbijeno,
    )
    return render(request, "igra/moderator/nalog.html", kontekst)
