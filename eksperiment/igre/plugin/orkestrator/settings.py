"""Podesavanja projekta Orkestrator za lokalni rad i testove; server koristi settings_prod.py (plan 15.4)."""

import os
from pathlib import Path

from django.utils.csp import CSP

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY',
    'django-insecure--xhkguc*&h^0o$g1ixurcmh!&19*5rb#u&-$gcgc%hn3(yw9ka',
)

DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1']

INSTALLED_APPS = [
    # Nalozi samo za moderatore (plan 14.2); bez admina, bez messages i bez context processora auth.
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'django.contrib.sessions',
    'django.contrib.staticfiles',
    'igra',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # Zaglavlje Content-Security-Policy iz SECURE_CSP na svaki odgovor, i lokalno i u testovima (plan 15.4).
    'django.middleware.csp.ContentSecurityPolicyMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    # request.user je lenj: igra i deljena strana ga ne citaju, pa ni sesiju ne diraju (plan 14.2).
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    # Posle sesije, pre CommonMiddleware (redosled iz Django dokumentacije); jezik iz kolacica,
    # inace iz Accept-Language, inace LANGUAGE_CODE (plan 12.2).
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'orkestrator.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
            ],
        },
    },
]

WSGI_APPLICATION = 'orkestrator.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        'OPTIONS': {
            # Brava pre prvog citanja: bez nje dve transakcije procitaju isto stanje sesije.
            'transaction_mode': 'IMMEDIATE',
            # WAL: citaoci i pisac se ne blokiraju, pa vise procesa servera radi bez "database is locked" (plan
            # 15.2). Trajno je u datoteci baze; pored nje nastaju db.sqlite3-wal i -shm, pa direktorijum baze mora
            # biti upisiv. Baza u memoriji (testovi) ostaje u rezimu "memory".
            'init_command': 'PRAGMA journal_mode=WAL',
            # Sekunde cekanja na tudju bravu pre "database is locked"; ocekivano cekanje je do 2 ms (plan 15.2).
            'timeout': 5,
        },
    }
}

# Izricito baza: sesija u potpisanom kolacicu bila bi citljiva klijentu (seme, ishodi).
SESSION_ENGINE = 'django.contrib.sessions.backends.db'

# DEBUG ostaje True (statika pod runserver-om), pa tehnicka strana ne sme da ispise promenljive okvira.
DEFAULT_EXCEPTION_REPORTER_FILTER = 'orkestrator.greske.FilterBezPromenljivih'

# Skripta cita CSRF token iz kolacica.
CSRF_COOKIE_HTTPONLY = False

# Izricito, iako su podrazumevane vrednosti iste: sesija nosi i prijavu moderatora (plan 14.2).
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
# Lokalni http; True u settings_prod.
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Bezbednosna zaglavlja, i lokalno (plan 15.4). Izricito, iako su prva cetiri podrazumevana u Django-u 6.0.
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'  # deljeno ga zamenjuje sa no-referrer (token je u URL-u)
SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'
# Sabloni nemaju ugradjenu skriptu ni style=; json_script nije izvrsna skripta, a igra.js menja stil kroz CSSOM.
# data: je za SVG u Bootstrap CSS-u. Tehnicka strana Django-a (DEBUG) ima ugradjen stil, pa lokalno izgleda gola.
SECURE_CSP = {
    'default-src': [CSP.SELF],
    'script-src': [CSP.SELF],
    'style-src': [CSP.SELF],
    'img-src': [CSP.SELF, 'data:'],
    'object-src': [CSP.NONE],
    'base-uri': [CSP.NONE],
    'form-action': [CSP.SELF],
    'frame-ancestors': [CSP.NONE],
}

# Telo zahteva: JSON igre je najvise 2 KB (views.MAKS_VELICINA_TELA), forme moderatora imaju po nekoliko polja.
# Vece telo je RequestDataTooBig, pa 400 (plan 15.4).
DATA_UPLOAD_MAX_MEMORY_SIZE = 16 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 50

# Moderator (plan 14.2). Hes lozinke ostaje podrazumevani PBKDF2-SHA256.
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 12},
    },
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LOGIN_URL = 'moderator_prijava'

# Izricito. LocMem radi po procesu; aplikacija ga ne koristi. Brojac neuspeha prijave je u bazi (model
# PokusajPrijave, odluka P2), zajednicki svim procesima: kes po procesu pustao bi 5 pokusaja po radniku.
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    },
}

# Posle prijave sesija (i partija u istom pregledacu) traje ovoliko od poslednjeg upisa, do odjave.
MODERATOR_SESIJA_SEKUNDI = 8 * 3600
# Neuspesi prijave ili potvrde sopstvenom lozinkom za isto ime, pa blokada (plan 14.2).
PRIJAVA_POKUSAJA = 5
PRIJAVA_BLOKADA_SEKUNDI = 900
# Dnevnik moderatora; mora biti duzi od SESSION_COOKIE_AGE (14 dana), jer cuva i hes partije (plan 14.4).
DNEVNIK_DANA = 365

LANGUAGE_CODE = 'sr'  # rezervni jezik

# Nazivi na svom jeziku i bez gettext_lazy: ne prevode se (plan 12.2).
LANGUAGES = [('sr', 'Српски'), ('en', 'English')]

LOCALE_PATHS = [BASE_DIR / 'locale']

# Kolacic jezika (ime ostaje podrazumevano django_language). Bez LANGUAGE_COOKIE_AGE kolacic traje
# do zatvaranja pregledaca, a izbor mora da se pamti (MVP 6).
LANGUAGE_COOKIE_AGE = 365 * 24 * 60 * 60
LANGUAGE_COOKIE_SAMESITE = 'Lax'
# Skripta kolacic jezika ne cita.
LANGUAGE_COOKIE_HTTPONLY = True
# Lokalni http; True u settings_prod.
LANGUAGE_COOKIE_SECURE = False

# Baza cuva UTC (USE_TZ); datum rang liste se prikazuje u ovoj zoni (plan 10.5, R1).
TIME_ZONE = 'Europe/Belgrade'

USE_I18N = True

USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
