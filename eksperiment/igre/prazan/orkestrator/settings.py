"""Podesavanja za lokalni rad i testove. Javni server koristi settings_produkcija.py, koji ovo nasledjuje."""

import os
from pathlib import Path

from django.utils.csp import CSP

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("ORKESTRATOR_SECRET_KEY", "samo-za-lokalni-rad-orkestrator")

# DEBUG je iskljucen jer tehnicka stranica greske prikazuje lokalne promenljive, medju njima i seme.
DEBUG = False
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]

INSTALLED_APPS = [
    # Nalozi postoje samo za moderatore; igraci i dalje igraju bez naloga.
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "igra",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "igra.jezik.JezikMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "orkestrator.urls"
WSGI_APPLICATION = "orkestrator.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": ["igra.jezik.kontekst"]},
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        # WAL: citanje ne ceka upis, pa vise procesa servera radi nad istom datotekom.
        "OPTIONS": {
            "transaction_mode": "IMMEDIATE",
            "timeout": 20,
            "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
        },
        # Baza u datoteci daje pravi istovremeni pristup i u testovima kroz pregledac.
        "TEST": {"NAME": BASE_DIR / "test_db.sqlite3"},
    }
}

# Sesija je u bazi: kolacic nosi samo ID sesije (pravilo 1).
SESSION_ENGINE = "django.contrib.sessions.backends.db"

# Lozinke moderatora: Django ih cuva samo kao hes (PBKDF2), nikad kao tekst.
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_URL = "moderator_prijava"

# Izvorni tekst je srpski (cirilica); engleski prevod je u igra/locale/en.
LANGUAGE_CODE = "sr"
LANGUAGES = [("sr", "Srpski"), ("en", "English")]
USE_I18N = True
# Izbor jezika se pamti godinu dana; kolacic nosi samo oznaku jezika.
LANGUAGE_COOKIE_NAME = "jezik"
LANGUAGE_COOKIE_AGE = 365 * 24 * 60 * 60
TIME_ZONE = "Europe/Belgrade"
USE_TZ = True

STATIC_URL = "static/"
# Lokalno staticke datoteke sluzi Django (DEBUG je iskljucen); na javnom serveru to radi nginx.
SLUZI_STATICKE = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Stranice ucitavaju samo svoje skripte, stilove i slova. Jedini izuzetak su style atributi
# (sirina merila, prsten rezultata), koje sablon pise sa serverske vrednosti.
SECURE_CSP = {
    "default-src": [CSP.SELF],
    "script-src": [CSP.SELF],
    "style-src": [CSP.SELF, CSP.UNSAFE_INLINE],
    "img-src": [CSP.SELF, "data:"],
    "font-src": [CSP.SELF],
    "connect-src": [CSP.SELF],
    "object-src": [CSP.NONE],
    "base-uri": [CSP.NONE],
    "form-action": [CSP.SELF],
    "frame-ancestors": [CSP.NONE],
}
X_FRAME_OPTIONS = "DENY"
