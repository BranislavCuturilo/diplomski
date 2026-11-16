"""Stranice moderatora. Svaka zahteva prijavljenog moderatora; igraci ih ne vide i ne trebaju."""

from functools import wraps

from django.contrib.auth import authenticate, login, logout
from django.http import Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_noop as N_
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from igra import moderacija, servis
from igra.models import Dogadjaj, Partija, Rezultat

# Poruka posle uspesne radnje stize kao kljuc u adresi, nikad kao slobodan tekst.
PORUKE = {
    "rezultat": N_("Резултат је обрисан."),
    "link": N_("Линк је обрисан."),
    "zadrzan": N_("Резултат је задржан."),
    "dodat": N_("Модератор је додат."),
    "iskljucen": N_("Модератор је искључен."),
    "ukljucen": N_("Модератор је поново укључен."),
}


def samo_moderator(pogled):
    @wraps(pogled)
    def omotac(request, *args, **kwargs):
        if not moderacija.je_moderator(request.user):
            if request.method == "GET":
                return redirect("moderator_prijava")
            return HttpResponseForbidden(_("Потребна је пријава модератора."))
        return pogled(request, *args, **kwargs)

    return never_cache(omotac)


def _prikazi(request, sablon, kontekst=None, status=200):
    poruka = PORUKE.get(request.GET.get("poruka", ""))
    return render(
        request,
        sablon,
        {
            "moderator": request.user,
            "poruka": _(poruka) if poruka else None,
            # Broj u meniju: moderator sa svake stranice vidi da ima prijavljenih imena za pregled.
            "broj_prijava": moderacija.otvorene_prijave().count(),
            **(kontekst or {}),
        },
        status=status,
    )


def _sa_porukom(ime_adrese, kljuc):
    return redirect(f"{reverse(ime_adrese)}?poruka={kljuc}")


# Prijava i odjava


@never_cache
@require_http_methods(["GET", "POST"])
def prijava(request):
    if moderacija.je_moderator(request.user):
        return redirect("moderator_rezultati")
    if request.method == "GET":
        return render(request, "igra/moderator/prijava.html")

    ime = request.POST.get("ime", "")
    lozinka = request.POST.get("lozinka", "")
    if moderacija.prijava_zakljucana(ime):
        greska, status = _("Превише неуспелих покушаја. Покушај поново за 15 минута."), 429
    else:
        korisnik = authenticate(request, username=ime.strip(), password=lozinka)
        if korisnik is not None and moderacija.je_moderator(korisnik):
            moderacija.ponisti_promasaje(ime)
            # login menja kljuc sesije, a partija_id ostaje: moderator moze i da igra.
            login(request, korisnik)
            return redirect("moderator_rezultati")
        moderacija.zabelezi_promasaj(ime)
        # Ista poruka za nepostojece ime, pogresnu lozinku i nalog koji nije moderator.
        greska, status = _("Погрешно име или лозинка."), 400
    kontekst = {"greska": greska, "uneto_ime": ime, "dalje_jezika": reverse("moderator_prijava")}
    return render(request, "igra/moderator/prijava.html", kontekst, status=status)


@require_POST
def odjava(request):
    partija_id = request.session.get(servis.KLJUC_SESIJE)
    logout(request)
    if partija_id is not None:
        # Odjava brise sesiju; partija koju je moderator igrao ostaje njegova.
        request.session[servis.KLJUC_SESIJE] = partija_id
    return redirect("pocetna")


# Rezultati i linkovi


@require_GET
@samo_moderator
def rezultati(request):
    strana = moderacija.strana(Rezultat.objects.select_related("partija"), request.GET.get("strana"))
    return _prikazi(
        request,
        "igra/moderator/rezultati.html",
        {
            "strana": strana,
            "redovi": [moderacija.red_rezultata(r) for r in strana],
            "odeljak": "rezultati",
            "danas": servis.danas().isoformat(),
        },
    )


@require_GET
@samo_moderator
def izvoz(request):
    """CSV rang liste: ?lista=glavna (podrazumevano) ili ?lista=dnevna&dan=GGGG-MM-DD (bez dana: danas)."""
    lista = request.GET.get("lista", "glavna")
    if lista == "glavna":
        dan, ime = None, "rang-lista.csv"
    elif lista == "dnevna":
        try:
            dan = moderacija.procitaj_dan(request.GET.get("dan", "").strip())
        except servis.NeispravanZahtev as greska:
            return HttpResponse(greska.args[0][0], status=400, content_type="text/plain; charset=utf-8")
        ime = f"rang-lista-dana-{dan.isoformat()}.csv"
    else:
        return HttpResponse(_("Непозната листа."), status=400, content_type="text/plain; charset=utf-8")
    odgovor = HttpResponse(moderacija.csv_rang_liste(dan), content_type="text/csv; charset=utf-8")
    odgovor["Content-Disposition"] = f'attachment; filename="{ime}"'
    return odgovor


@require_GET
@samo_moderator
def linkovi(request):
    upit = Partija.objects.filter(kod__isnull=False).select_related("rezultat").order_by("-napravljena", "-pk")
    strana = moderacija.strana(upit, request.GET.get("strana"))
    return _prikazi(
        request,
        "igra/moderator/linkovi.html",
        {"strana": strana, "redovi": [moderacija.red_linka(p) for p in strana], "odeljak": "linkovi"},
    )


@require_GET
@samo_moderator
def prijavljena_imena(request):
    """Imena koja su igraci prijavili, a o kojima moderator jos nije odlucio."""
    strana = moderacija.strana(moderacija.otvorene_prijave(), request.GET.get("strana"))
    return _prikazi(
        request,
        "igra/moderator/prijavljena_imena.html",
        {"strana": strana, "redovi": [moderacija.red_prijave(stavka) for stavka in strana], "odeljak": "prijave"},
    )


@require_POST
@samo_moderator
def zadrzi_rezultat(request, pk):
    try:
        moderacija.zadrzi_rezultat(request.user, pk)
    except moderacija.NijePronadjeno:
        raise Http404(_("Пријава не постоји или је већ решена.")) from None
    return _sa_porukom("moderator_prijavljena_imena", "zadrzan")


@require_http_methods(["GET", "POST"])
@samo_moderator
def obrisi_rezultat(request, pk):
    """GET pita za potvrdu, tek POST brise. Sa ?odakle=prijave moderator se vraca na prijavljena imena."""
    iz_prijava = request.GET.get("odakle") == "prijave"
    try:
        if request.method == "POST":
            moderacija.obrisi_rezultat(request.user, pk)
            return _sa_porukom("moderator_prijavljena_imena" if iz_prijava else "moderator_rezultati", "rezultat")
        rezultat = moderacija.rezultat_za_brisanje(pk)
    except moderacija.NijePronadjeno:
        raise Http404(_("Резултат не постоји или је већ обрисан.")) from None
    return _prikazi(
        request,
        "igra/moderator/potvrda.html",
        {
            "vrsta": "rezultat",
            "red": moderacija.red_rezultata(rezultat),
            "odeljak": "prijave" if iz_prijava else "rezultati",
            "iz_prijava": iz_prijava,
        },
    )


@require_http_methods(["GET", "POST"])
@samo_moderator
def obrisi_link(request, kod):
    try:
        if request.method == "POST":
            moderacija.obrisi_link(request.user, kod)
            return _sa_porukom("moderator_linkovi", "link")
        partija = moderacija.partija_za_brisanje_linka(kod)
    except moderacija.NijePronadjeno:
        raise Http404(_("Линк не постоји или је већ обрисан.")) from None
    return _prikazi(
        request,
        "igra/moderator/potvrda.html",
        {"vrsta": "link", "red": moderacija.red_linka(partija), "odeljak": "linkovi"},
    )


# Dnevnik i nalozi


@require_GET
@samo_moderator
def dnevnik(request):
    strana = moderacija.strana(Dogadjaj.objects.select_related("moderator"), request.GET.get("strana"))
    return _prikazi(
        request,
        "igra/moderator/dnevnik.html",
        {"strana": strana, "redovi": [moderacija.red_dnevnika(d) for d in strana], "odeljak": "dnevnik"},
    )


@require_GET
@samo_moderator
def statistika(request):
    return _prikazi(
        request,
        "igra/moderator/statistika.html",
        {"statistika": moderacija.statistika(), "odeljak": "statistika"},
    )


def _kontekst_naloga(request, **dodatak):
    # I posle neuspelog POST-a promena jezika vraca na spisak naloga.
    return {
        "nalozi": moderacija.moderatori(),
        "odeljak": "nalozi",
        "dalje_jezika": reverse("moderator_nalozi"),
        **dodatak,
    }


@require_http_methods(["GET", "POST"])
@samo_moderator
def nalozi(request):
    if request.method == "GET":
        return _prikazi(request, "igra/moderator/nalozi.html", _kontekst_naloga(request))
    try:
        moderacija.dodaj_moderatora(
            request.user,
            request.POST.get("ime"),
            request.POST.get("lozinka"),
            request.POST.get("lozinka_ponovo"),
        )
    except servis.NeispravanZahtev as greska:
        kontekst = _kontekst_naloga(request, greske=greska.args[0], uneto_ime=request.POST.get("ime", ""))
        return _prikazi(request, "igra/moderator/nalozi.html", kontekst, status=400)
    return _sa_porukom("moderator_nalozi", "dodat")


def _aktivnost(request, pk, aktivan):
    try:
        dogadjaj = moderacija.promeni_aktivnost(request.user, pk, aktivan)
    except moderacija.NijePronadjeno:
        raise Http404(_("Модератор не постоји.")) from None
    except servis.NeispravanZahtev as greska:
        return _prikazi(request, "igra/moderator/nalozi.html", _kontekst_naloga(request, greske=greska.args[0]), 400)
    if dogadjaj is None:
        return redirect("moderator_nalozi")
    return _sa_porukom("moderator_nalozi", "ukljucen" if aktivan else "iskljucen")


@require_POST
@samo_moderator
def iskljuci(request, pk):
    return _aktivnost(request, pk, False)


@require_POST
@samo_moderator
def ukljuci(request, pk):
    return _aktivnost(request, pk, True)
