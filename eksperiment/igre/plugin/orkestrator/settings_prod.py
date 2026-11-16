"""Podesavanja servera (plan 15.4): sve iz settings.py, a ovde samo ono sto trazi HTTPS iza Nginx-a ili server.

Vrednosti stizu iz okruzenja (ugovor 15.12, deploy/env.primer). Obavezna promenljiva koja nedostaje zaustavlja
pokretanje greskom koja je imenuje: server bez kljuca, hosta ili baze ne sme da krene sa tihom zamenom.
"""

import os

from django.core.exceptions import ImproperlyConfigured

from .settings import *  # noqa: F403
from .settings import BASE_DIR, DATABASES


def _nije_postavljena(ime):
    return ImproperlyConfigured(f"Promenljiva okruzenja {ime} nije postavljena (deploy/env.primer).")


def _obavezno(ime):
    vrednost = os.environ.get(ime, "").strip()
    if not vrednost:
        raise _nije_postavljena(ime)
    return vrednost


def _spisak(ime, obavezno):
    """Vrednosti odvojene zarezom, bez praznih; obavezan spisak ne sme ostati prazan (npr. samo " , ")."""
    spisak = [deo.strip() for deo in os.environ.get(ime, "").split(",") if deo.strip()]
    if obavezno and not spisak:
        raise _nije_postavljena(ime)
    return spisak


DEBUG = False

# Bez rezerve. Ne menja se izmedju verzija: nov kljuc gasi sve sesije, a s njima partije u toku i prijave.
SECRET_KEY = _obavezno("DJANGO_SECRET_KEY")

# Npr. "orkestrator.example". Nepoznat Host zaustavlja vec Nginx (444); ovo je druga linija.
ALLOWED_HOSTS = _spisak("DJANGO_ALLOWED_HOSTS", obavezno=True)
# Poreklo sa semom (django-nginx-docker, pravilo 2). Gunicorn ne pokrece system check, pa se sema proverava ovde.
CSRF_TRUSTED_ORIGINS = _spisak("DJANGO_CSRF_TRUSTED_ORIGINS", obavezno=False)
for _poreklo in CSRF_TRUSTED_ORIGINS:
    if not _poreklo.startswith("https://"):
        raise ImproperlyConfigured(f"DJANGO_CSRF_TRUSTED_ORIGINS: {_poreklo!r} mora poceti sa https://.")

# Baza van slike, na imenovanom volumenu (/data/db.sqlite3); direktorijum mora biti upisiv zbog -wal i -shm.
DATABASES = {"default": {**DATABASES["default"], "NAME": _obavezno("DJANGO_BAZA")}}

# Nginx radi TLS i uvek PREPISUJE X-Forwarded-Proto (django-nginx-docker, pravilo 1); bez ovoga petlja 301.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# Druga linija iza Nginx-a (on vec daje 301 sa :80). Host iz zahteva, USE_X_FORWARDED_HOST ostaje False (plan 15.7).
SECURE_SSL_REDIRECT = True

# Imena kolacica se ne menjaju: igra.js cita csrftoken.
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
LANGUAGE_COOKIE_SECURE = True

# HSTS u dva koraka (plan 15.4): prvo 3600, posle 14 dana bez problema 31536000 (odobrava klijent, bez povratka).
# Isti niz cita i Nginx (strana 429 prijave; deploy/nginx.conf i provera u Dockerfile-u, 15-provera-okruzenja.sh),
# pa se ne skracuje: obe strane prihvataju samo ASCII cifre, bez razmaka i bez vodece nule (Nginx salje niz
# doslovno, pa bi 03600 dalo drugo zaglavlje nego Django), a time i samo vrednost vecu od 0 (0 gasi HSTS).
_hsts = os.environ.get("DJANGO_HSTS_SEKUNDI", "3600")
if not (_hsts.isascii() and _hsts.isdigit() and not _hsts.startswith("0")):
    raise ImproperlyConfigured(
        f"DJANGO_HSTS_SEKUNDI mora biti ceo broj sekundi veci od 0, samo cifre, bez razmaka i vodece nule, "
        f"ne {_hsts!r}."
    )
SECURE_HSTS_SECONDS = int(_hsts)
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SILENCED_SYSTEM_CHECKS = [
    # W005: poddomeni domena klijenta nisu poznati; includeSubDomains bi im nametnuo HTTPS na godinu dana.
    "security.W005",
    # W021: preload je trajan upis u pregledace i trazi posebnu odluku klijenta (plan 15.13).
    "security.W021",
]

# Nginx servira ovaj direktorijum (collectstatic u build fazi slike); u slici je to /app/staticfiles.
STATIC_ROOT = BASE_DIR / "staticfiles"

# stdout, odakle ga cita docker logs. Bez ADMINS i bez mejla: "django" ovde dobija samo stdout, pa Django-ov
# mail_admins nestaje. django.request samo greske (500), ne 404; FilterLoga cisti token, seme i kljuc sesije.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"bez_tajni": {"()": "orkestrator.greske.FilterLoga"}},
    "formatters": {"kratko": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {
        "stdout": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "filters": ["bez_tajni"],
            "formatter": "kratko",
        },
    },
    "root": {"handlers": ["stdout"], "level": "WARNING"},
    "loggers": {
        "django": {"handlers": ["stdout"], "level": "WARNING", "propagate": False},
        "django.request": {"handlers": ["stdout"], "level": "ERROR", "propagate": False},
        "django.security": {"handlers": ["stdout"], "level": "WARNING", "propagate": False},
    },
}
