from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from igra import servis


@require_GET
@never_cache
def pocetna(request):
    partija = servis.nadji_partiju(request.session)
    if partija is None:
        return render(request, "igra/pocetak.html", servis.kontekst_pocetka())
    if servis.je_zavrsena(partija):
        return redirect("kraj")
    return render(request, "igra/igra.html", servis.kontekst_igre(partija))


@require_POST
def nova(request):
    servis.nova_partija(request.session)
    return redirect("pocetna")


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
    return render(request, "igra/kraj.html", servis.kontekst_kraja(partija))


def _greska(greska, kod):
    return _json({"greska": str(greska)}, status=kod)


def _json(podaci, status=200):
    return JsonResponse(podaci, status=status, json_dumps_params={"ensure_ascii": False})
