import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("ORKESTRATOR_SECRET_KEY", "samo-za-lokalni-rad-orkestrator")

# DEBUG je iskljucen jer tehnicka stranica greske prikazuje lokalne promenljive, medju njima i seme.
DEBUG = False
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "igra",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
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
        "OPTIONS": {"context_processors": []},
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "OPTIONS": {"transaction_mode": "IMMEDIATE", "timeout": 20},
        # Baza u datoteci daje pravi istovremeni pristup i u testovima kroz pregledac.
        "TEST": {"NAME": BASE_DIR / "test_db.sqlite3"},
    }
}

# Sesija je u bazi: kolacic nosi samo ID sesije (pravilo 1).
SESSION_ENGINE = "django.contrib.sessions.backends.db"

LANGUAGE_CODE = "sr"
USE_I18N = False
TIME_ZONE = "Europe/Belgrade"
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
