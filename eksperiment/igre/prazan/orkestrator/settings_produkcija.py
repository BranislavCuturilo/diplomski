"""Podesavanja za javni server (https://orkestrator.example).

Ukljucuju se sa DJANGO_SETTINGS_MODULE=orkestrator.settings_produkcija. Sve sto se razlikuje
od servera do servera dolazi iz promenljivih okruzenja (deploy/orkestrator.env.primer).
Ispred Djanga stoji nginx: on drzi HTTPS, sluzi staticke datoteke i prosledjuje ostalo gunicornu.
"""

import os

from django.core.exceptions import ImproperlyConfigured

from .settings import *  # noqa: F403
from .settings import DATABASES


def _okruzenje(ime, podrazumevano=None):
    vrednost = os.environ.get(ime, podrazumevano)
    if not vrednost:
        raise ImproperlyConfigured(f"Nedostaje promenljiva okruzenja {ime} (vidi deploy/UPUTSTVO.md).")
    return vrednost


SECRET_KEY = _okruzenje("ORKESTRATOR_SECRET_KEY")
if len(SECRET_KEY) < 50 or len(set(SECRET_KEY)) < 5:
    raise ImproperlyConfigured(
        "ORKESTRATOR_SECRET_KEY mora imati bar 50 nasumicnih znakova (vidi deploy/UPUTSTVO.md)."
    )

DEBUG = False
DOMEN = _okruzenje("ORKESTRATOR_DOMEN", "orkestrator.example")
ALLOWED_HOSTS = [DOMEN]
CSRF_TRUSTED_ORIGINS = [f"https://{DOMEN}"]

DATABASES["default"]["NAME"] = _okruzenje("ORKESTRATOR_BAZA", "/var/lib/orkestrator/db.sqlite3")

# Nginx sluzi STATIC_ROOT; imena datoteka nose hes sadrzaja, pa smeju da se kesiraju godinu dana.
SLUZI_STATICKE = False
STATIC_ROOT = _okruzenje("ORKESTRATOR_STATIC", "/srv/orkestrator/static")
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"},
}

# Kes deli vise gunicorn procesa i prezivljava restart; u njemu se broje promasene prijave moderatora.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "kes",
        "OPTIONS": {"MAX_ENTRIES": 20000},
    }
}

# HTTPS. Nginx uvek prepisuje X-Forwarded-Proto, pa mu se ovde sme verovati.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
LANGUAGE_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
# Pregledac godinu dana otvara sajt samo preko HTTPS-a. Poddomeni i "preload" lista se namerno
# ne ukljucuju (W005, W021): oba vaze za ceo domen i tesko se povlace, pa o njima odlucuje
# vlasnik domena, ne ova igra.
SECURE_HSTS_SECONDS = int(os.environ.get("ORKESTRATOR_HSTS_SEKUNDI", 365 * 24 * 60 * 60))
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SILENCED_SYSTEM_CHECKS = ["security.W005", "security.W021"]

# Greske idu na standardni izlaz, a odatle u systemd dnevnik (journalctl -u orkestrator).
# Tehnicka stranica greske se nikad ne prikazuje (DEBUG = False), pa seme ne izlazi ni pri padu.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"kratko": {"format": "{levelname} {name}: {message}", "style": "{"}},
    "handlers": {"izlaz": {"class": "logging.StreamHandler", "formatter": "kratko"}},
    "loggers": {
        "django": {"handlers": ["izlaz"], "level": "WARNING"},
        # 4xx odgovori su obicni (pogresan krug, nepostojeci link) i ne pune dnevnik.
        "django.request": {"handlers": ["izlaz"], "level": "ERROR", "propagate": False},
    },
}
