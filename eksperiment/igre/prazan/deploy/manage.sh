#!/bin/sh
# Pokrece manage.py sa istim podesavanjima kao server. Pokrece se kao korisnik orkestrator:
#   sudo -u orkestrator /srv/orkestrator/app/deploy/manage.sh migrate
set -eu
cd /srv/orkestrator/app
set -a
. /etc/orkestrator/orkestrator.env
set +a
export DJANGO_SETTINGS_MODULE=orkestrator.settings_produkcija
exec /srv/orkestrator/venv/bin/python manage.py "$@"
