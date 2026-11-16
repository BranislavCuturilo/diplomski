from django.conf import settings
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST, require_safe

from igra import servis


@require_GET
@never_cache
def pocetna(request):
    partija = servis.nadji_partiju(request.session)
    if partija is not None and not servis.je_zavrsena(partija):
        return render(request, "igra/igra.html", servis.kontekst_igre(partija))
    # Bez partije ili posle zavrsene: pocetni ekran sa rang listom i partijama ovog igraca.
    igrac = servis.hes_igraca(request.COOKIES.get(servis.KOLACIC_IGRACA))
    return render(request, "igra/pocetak.html", servis.kontekst_pocetka(request.session, igrac))


def _kljuc_igraca(request):
    """Kljuc iz kolacica, ili nov ako ga nema ili nije ispravan."""
    kljuc = request.COOKIES.get(servis.KOLACIC_IGRACA)
    return kljuc if servis.ispravan_kljuc_igraca(kljuc) else servis.novi_kljuc_igraca()


def _zapamti_igraca(odgovor, kljuc):
    # Svaka nova partija produzava kolacic, pa istorija traje godinu dana od poslednje igre.
    odgovor.set_cookie(
        servis.KOLACIC_IGRACA,
        kljuc,
        max_age=servis.TRAJANJE_KOLACICA_IGRACA,
        samesite="Lax",
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
    )
    return odgovor


@require_POST
def nova(request):
    kljuc = _kljuc_igraca(request)
    servis.nova_partija(request.session, servis.hes_igraca(kljuc))
    return _zapamti_igraca(redirect("pocetna"), kljuc)


@require_POST
def dnevna(request):
    kljuc = _kljuc_igraca(request)
    try:
        servis.nova_dnevna_partija(request.session, servis.hes_igraca(kljuc))
    except servis.SukobStanja:
        pass  # Vec odigrano danas: pocetni ekran pokazuje rang listu dana.
    return _zapamti_igraca(redirect("pocetna"), kljuc)


@require_GET
def kako_se_igra(request):
    # Ne cita i ne menja sesiju: stranica je ista za svakoga, i tokom partije.
    return render(request, "igra/kako_se_igra.html", servis.kontekst_pravila())


@require_safe
def javna_rang_lista(request):
    """Rang lista u JSON obliku za partnere. Javna: bez kolacica, sa bilo kog sajta (CORS)."""
    odgovor = _json(servis.javna_rang_lista())
    odgovor["Access-Control-Allow-Origin"] = "*"
    # Minut kesa stiti server od partnera koji cesto proveravaju; lista se ionako retko menja.
    odgovor["Cache-Control"] = "public, max-age=60"
    return odgovor


@require_POST
def potez(request):
    try:
        krug, izbori = servis.procitaj_zahtev(request.body)
        odgovor = servis.odigraj_potez(request.session, krug, izbori)
    except servis.NeispravanZahtev as greska:
        return _greska(greska, 400)
    except servis.SukobStanja as greska:
        return _greska(greska, 409)
    return _json(odgovor)


@require_GET
@never_cache
def kraj(request):
    partija = servis.nadji_partiju(request.session)
    if partija is None or not servis.je_zavrsena(partija):
        return redirect("pocetna")
    return _prikazi_kraj(request, partija)


def _prikazi_kraj(request, partija, status=200, **dodatak):
    kontekst = servis.kontekst_kraja(partija)
    if kontekst["kod"]:
        kontekst["link_deljenja"] = request.build_absolute_uri(reverse("podeljeno", args=[kontekst["kod"]]))
    # I posle neuspelog cuvanja imena (POST), promena jezika vraca na zavrsni ekran.
    kontekst["dalje_jezika"] = reverse("kraj")
    return render(request, "igra/kraj.html", {**kontekst, **dodatak}, status=status)


@require_POST
def sacuvaj(request):
    ime = request.POST.get("ime")
    try:
        rezultat = servis.sacuvaj_rezultat(request.session, ime)
    except servis.NeispravanZahtev as greska:
        return _kraj_sa_greskom(request, greska, 400, ime)
    except servis.SukobStanja as greska:
        return _kraj_sa_greskom(request, greska, 409, ime)
    lista = "dnevna-lista" if rezultat.partija.dan else "rang-lista"
    return redirect(reverse("pocetna") + "#" + lista)


@require_GET
@never_cache
def podeljeno(request, kod):
    # Ne cita i ne menja sesiju: link otvara samo rezultat, bez nastavka igre.
    partija = servis.nadji_podeljenu(kod)
    if partija is None:
        raise Http404("Резултат не постоји.")
    return render(request, "igra/podeljeno.html", servis.kontekst_podeljenog(partija))


@require_http_methods(["GET", "POST"])
@never_cache
def prijavi_ime(request, pk):
    """Prijava neprikladnog imena sa rang liste: GET pita za potvrdu, tek POST prijavljuje.

    Ne cita i ne menja sesiju, jer ime moze da prijavi svako ko vidi rang listu.
    """
    if request.method == "POST":
        if servis.prijavi_ime(pk) is None:
            raise Http404("Резултат није на ранг листи.")
        # Ista adresa posle prijave pokazuje da ime ceka pregled moderatora.
        return redirect("prijavi_ime", pk)
    rezultat = servis.nadji_za_prijavu(pk)
    if rezultat is None:
        raise Http404("Резултат није на ранг листи.")
    return render(request, "igra/prijava_imena.html", servis.kontekst_prijave_imena(rezultat))


def _kraj_sa_greskom(request, greska, kod, ime):
    partija = servis.nadji_partiju(request.session)
    if partija is None or not servis.je_zavrsena(partija):
        return HttpResponse(str(greska), status=kod, content_type="text/plain; charset=utf-8")
    return _prikazi_kraj(request, partija, status=kod, greska=str(greska), uneto_ime=ime or "")


def _greska(greska, kod):
    return _json({"greska": str(greska)}, status=kod)


def _json(podaci, status=200):
    return JsonResponse(podaci, status=status, json_dumps_params={"ensure_ascii": False})
