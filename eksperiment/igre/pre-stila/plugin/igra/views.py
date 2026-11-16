import json
import secrets

from django.core.exceptions import RequestDataTooBig
from django.db import transaction
from django.http import JsonResponse, UnreadablePostError
from django.http.request import RawPostDataException
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from . import motor

MAKS_VELICINA_TELA = 2 * 1024
KLJUCEVI_ZAHTEVA = {"krug", "izbori"}


def _nova_igra():
    return motor.nova_igra(secrets.token_hex(16))


def _procitaj_zahtev(request):
    """Jedino mesto koje cita telo poteza; sve sto nije po ugovoru baca ValueError."""
    try:
        telo = request.body
    except (RequestDataTooBig, RawPostDataException, UnreadablePostError) as greska:
        # RawPostDataException: multipart telo je vec potrosila CSRF provera.
        raise ValueError("telo nije citljivo") from greska
    if len(telo) > MAKS_VELICINA_TELA:
        raise ValueError("telo je preveliko")
    podaci = json.loads(telo)  # JSONDecodeError i UnicodeDecodeError su ValueError
    if not isinstance(podaci, dict) or set(podaci) != KLJUCEVI_ZAHTEVA:
        raise ValueError("pogresan oblik zahteva")
    if type(podaci["krug"]) is not int:  # bool je podklasa int-a, isinstance bi ga pustio
        raise ValueError("krug nije ceo broj")
    return podaci["krug"], podaci["izbori"]


def _odbijen_potez(greska, stanje):
    return JsonResponse({"greska": greska, "stanje": motor.javni_prikaz(stanje)}, status=409)


@require_GET
@ensure_csrf_cookie
@never_cache
def pocetna(request):
    stanje = request.session.get("igra")
    if stanje is None:  # P4: bez uvodnog ekrana, GET sam pravi igru
        stanje = _nova_igra()
        request.session["igra"] = stanje
    kontekst = {"stanje": motor.javni_prikaz(stanje), "opcije": motor.javne_opcije()}
    return render(request, "igra/igra.html", kontekst)


@require_POST
def potez(request):
    # P5: oblik zahteva se proverava pre citanja stanja, pa 400 ima prednost nad 409.
    try:
        krug, izbori = _procitaj_zahtev(request)
        motor.proveri_izbore(izbori)
    except ValueError:  # ukljucuje motor.NepoznatIzbor
        return JsonResponse({"greska": "neispravan_zahtev"}, status=400)

    # BEGIN IMMEDIATE (settings.py) uzima bravu pre prvog citanja sesije, pa je citanje-racun-upis nedeljivo.
    with transaction.atomic():
        stanje = request.session.get("igra")
        if stanje is None:
            return JsonResponse({"greska": "nema_igre", "stanje": None}, status=409)

        try:
            novo = motor.odigraj_potez(stanje, krug, izbori)
        except motor.IgraZavrsena:
            return _odbijen_potez("igra_zavrsena", stanje)
        except motor.PogresanKrug:
            return _odbijen_potez("pogresan_krug", stanje)

        request.session["igra"] = novo
        request.session.save()
        request.session.modified = False  # inace SessionMiddleware upisuje jos jednom, van brave
    return JsonResponse(motor.javni_prikaz(novo))


@require_POST
def nova(request):
    # P3: i usred igre; polja forme se ne citaju, pa klijent ne moze da zada seme.
    with transaction.atomic():
        request.session["igra"] = _nova_igra()
        # Bez vazece sesije novi kljuc jos niko ne zna, pa nema trke: upis i kolacic ostaju middleware-u.
        if request.session.session_key is not None:
            request.session.save()
            request.session.modified = False  # inace SessionMiddleware upisuje jos jednom, van brave
    return redirect("pocetna")
