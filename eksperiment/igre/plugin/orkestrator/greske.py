"""Tehnicka strana Django-a bez promenljivih okvira (inace ispisuje seme i istoriju partije) i filter loga servera."""

import logging
import re

from django.views.debug import SafeExceptionReporterFilter


class FilterBezPromenljivih(SafeExceptionReporterFilter):
    def is_active(self, request):
        # Osnovna klasa vraca `not DEBUG`, pa uz DEBUG = True (settings.py) sensitive_post_parameters ne bi
        # sakrio nista i lozinka iz POST-a bi stajala na tehnickoj strani (revizija 2026-11-11).
        return True

    def get_traceback_frame_variables(self, request, tb_frame):
        return []


# Token deljenog linka u putanji: /r/<token>/ postaje /r/-/. Oblik se ne proverava, pa ni neispravan token ne
# ostaje u logu.
_PUTANJA_DELJENOG = re.compile(r"/r/[^/\s'\"?#]+")
# Samostalan niz od 32 do 64 mala slova i cifre: seme partije (32 heksa znaka), kljuc sesije (32) i hes partije
# (64). Imena iz koda (sa _) i obican tekst ovom obliku ne odgovaraju.
_DUGI_NIZ = re.compile(r"\b[0-9a-z]{32,64}\b")


def _ocisti(tekst):
    return _DUGI_NIZ.sub("[skriveno]", _PUTANJA_DELJENOG.sub("/r/-", tekst))


class FilterLoga(logging.Filter):
    """Zapis loga servera bez tokena linka, semena i kljuca sesije (plan 15.4, settings_prod.LOGGING).

    Lozinka, telo zahteva i kolacici ne idu u log jer ih nijedan zapis ne nosi kao tekst: Django log greske nosi
    samo putanju i trag poziva (bez promenljivih), a objekat zahteva se ovde uklanja. Ovaj filter cisti tekst koji
    ipak ide: poruku, trag izuzetka i trag steka.
    """

    def filter(self, record):
        try:
            poruka = record.getMessage()
        except (TypeError, ValueError):
            # Pogresan poziv loga (argumenti ne odgovaraju formatu): sablon ostaje, argumenti ne idu ni u stderr.
            poruka = f"{record.msg} [argumenti izostavljeni: ne odgovaraju formatu]"
        record.msg, record.args = _ocisti(poruka), None
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = _ocisti(record.exc_text)
        if record.stack_info:
            record.stack_info = _ocisti(record.stack_info)
        # django.request i django.security prilazu ceo zahtev (POST, kolacici); nijedan formater ga ne treba.
        record.request = None
        return True
