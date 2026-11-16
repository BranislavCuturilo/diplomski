"""Podesavanja projekta Orkestrator; igra radi lokalno (plan, odeljak 3)."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY',
    'django-insecure--xhkguc*&h^0o$g1ixurcmh!&19*5rb#u&-$gcgc%hn3(yw9ka',
)

DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1']

INSTALLED_APPS = [
    'django.contrib.sessions',
    'django.contrib.staticfiles',
    'igra',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
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
        # Brava pre prvog citanja: bez nje dve transakcije procitaju isto stanje sesije.
        'OPTIONS': {'transaction_mode': 'IMMEDIATE'},
    }
}

# Izricito baza: sesija u potpisanom kolacicu bila bi citljiva klijentu (seme, ishodi).
SESSION_ENGINE = 'django.contrib.sessions.backends.db'

# DEBUG ostaje True (statika pod runserver-om), pa tehnicka strana ne sme da ispise promenljive okvira.
DEFAULT_EXCEPTION_REPORTER_FILTER = 'orkestrator.greske.FilterBezPromenljivih'

# Skripta cita CSRF token iz kolacica.
CSRF_COOKIE_HTTPONLY = False

LANGUAGE_CODE = 'sr'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
