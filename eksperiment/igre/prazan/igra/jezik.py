"""Izbor jezika: igrac bira srpski ili engleski, a izbor se pamti u kolacicu.

Jezik citaocevog pregledaca (Accept-Language) se namerno ne koristi: dok igrac ne izabere
drugacije, igra je na srpskom.
"""

from django.conf import settings
from django.http import Http404, HttpResponseRedirect
from django.urls import reverse
from django.utils import translation
from django.utils.cache import patch_vary_headers
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

JEZICI = dict(settings.LANGUAGES)
OZNAKA_ZA_HTML = {"sr": "sr-Cyrl", "en": "en"}


def izabrani_jezik(request):
    jezik = request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME)
    return jezik if jezik in JEZICI else settings.LANGUAGE_CODE


class JezikMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        jezik = izabrani_jezik(request)
        translation.activate(jezik)
        request.LANGUAGE_CODE = jezik
        try:
            odgovor = self.get_response(request)
        finally:
            translation.deactivate()
        patch_vary_headers(odgovor, ("Cookie",))
        odgovor.headers.setdefault("Content-Language", jezik)
        return odgovor


@require_GET
@never_cache
def promeni_jezik(request, jezik):
    """Obican link, bez forme: radi i na podeljenoj stranici, koja nema nijednu formu."""
    if jezik not in JEZICI:
        raise Http404
    dalje = request.GET.get("dalje", "")
    if not url_has_allowed_host_and_scheme(
        dalje, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        dalje = reverse("pocetna")
    odgovor = HttpResponseRedirect(dalje)
    odgovor.set_cookie(
        settings.LANGUAGE_COOKIE_NAME,
        jezik,
        max_age=settings.LANGUAGE_COOKIE_AGE,
        samesite="Lax",
        httponly=True,
        secure=settings.LANGUAGE_COOKIE_SECURE,
    )
    return odgovor


def kontekst(request):
    """Podaci za birac jezika u zaglavlju svake stranice.

    Posle POST zahteva (npr. greska pri cuvanju imena) povratak ide na pocetnu, jer se POST
    ne ponavlja; pogled moze da posalje svoj `dalje_jezika` i tako ovo zameni.
    """
    tekuci = translation.get_language()
    dalje = request.get_full_path() if request.method == "GET" else reverse("pocetna")
    return {
        "jezik_html": OZNAKA_ZA_HTML.get(tekuci, tekuci),
        "izbor_jezika": [
            {
                "kod": kod,
                "oznaka": kod.upper(),
                "naziv": naziv,
                "adresa": reverse("jezik", args=[kod]),
                "tekuci": kod == tekuci,
            }
            for kod, naziv in settings.LANGUAGES
        ],
        "dalje_jezika": dalje,
    }
