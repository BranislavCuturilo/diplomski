#!/usr/bin/env bash
# Pokrece igru Orkestrator iz eksperimenta, bez znanja Django-a.
#
#   ./pokreni.sh            obe igre: prazna sesija na :8001, plugin na :8002
#   ./pokreni.sh prazan     samo igra koju je napravio prazan Claude Code
#   ./pokreni.sh plugin     samo igra koju je napravio Claude Code sa pluginom
#
# Prvo pokretanje pravi venv i instalira pakete (minut-dva po igri); svako sledece samo pokrece.
# Treba samo Python 3.12 ili noviji. Na Windows-u se pokrece iz Git Bash-a.
# Zaustavljanje: Ctrl+C.
set -euo pipefail

cd "$(dirname "$0")"
KOREN="$(pwd)"

# Nalog za ulaz u deo za moderatora (/moderator/prijava/). Samo za lokalni pregled.
DEMO_IME="demo"
DEMO_LOZINKA="Orkestrator-2026!"

korak() { echo "[orkestrator] $*"; }

nadji_python() {
    local p
    for p in python3 python py; do
        if command -v "$p" >/dev/null 2>&1 \
            && "$p" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
            echo "$p"
            return 0
        fi
    done
    echo "[orkestrator] GRESKA: treba Python 3.12 ili noviji (Django 6.0). Instaliraj ga sa python.org." >&2
    exit 1
}

python_iz_venv() {
    # Windows venv ima Scripts/python.exe, Linux i macOS bin/python.
    if [ -x "$1/Scripts/python.exe" ]; then echo "$1/Scripts/python.exe"; else echo "$1/bin/python"; fi
}

demo_moderator() {
    local strana="$1" vpy="$2"
    # Svaka igra pravi moderatora kroz svoj servis, isti koji koristi i njena komanda (bez upita za lozinku).
    if [ "$strana" = "prazan" ]; then
        "$vpy" manage.py shell -c "
from django.contrib.auth import get_user_model
from igra import moderacija
if not get_user_model().objects.filter(username='$DEMO_IME').exists():
    moderacija.dodaj_moderatora(None, '$DEMO_IME', '$DEMO_LOZINKA', '$DEMO_LOZINKA')
    print('[orkestrator] napravljen moderator $DEMO_IME')
"
    else
        "$vpy" manage.py shell -c "
from igra import nalozi
if not nalozi.ime_zauzeto('$DEMO_IME'):
    nalozi.dodaj(None, '$DEMO_IME', '$DEMO_LOZINKA', glavni=True)
    print('[orkestrator] napravljen glavni moderator $DEMO_IME')
"
    fi
}

pripremi() {
    local strana="$1"
    local dir="$KOREN/igre/$strana"
    local venv="$dir/.venv"
    [ -f "$dir/manage.py" ] || { echo "[orkestrator] GRESKA: nema igre u $dir" >&2; exit 1; }

    if [ ! -d "$venv" ]; then
        korak "$strana: pravim venv (prvo pokretanje)"
        "$PY" -m venv "$venv"
    fi
    local vpy
    vpy="$(python_iz_venv "$venv")"

    korak "$strana: instaliram pakete iz requirements.txt"
    "$vpy" -m pip install --disable-pip-version-check --quiet -r "$dir/requirements.txt"

    # Baza je stanje iz eksperimenta; original se cuva netaknut pre prvog pokretanja.
    if [ -f "$dir/db.sqlite3" ] && [ ! -f "$dir/db.sqlite3.original" ]; then
        korak "$strana: cuvam originalnu bazu iz eksperimenta kao db.sqlite3.original"
        cp "$dir/db.sqlite3" "$dir/db.sqlite3.original"
    fi

    korak "$strana: primenjujem migracije"
    (cd "$dir" && "$vpy" manage.py migrate --noinput)

    korak "$strana: proveravam nalog moderatora"
    (cd "$dir" && demo_moderator "$strana" "$vpy")
}

pokreni() {
    local strana="$1" port="$2"
    local dir="$KOREN/igre/$strana"
    local vpy
    vpy="$(python_iz_venv "$dir/.venv")"
    korak "$strana: server na http://127.0.0.1:$port/"
    (cd "$dir" && exec "$vpy" manage.py runserver "127.0.0.1:$port" --noreload)
}

uputstvo() {
    echo
    echo "================================================================"
    if [ "$1" != "plugin" ]; then echo "  Prazna sesija:   http://127.0.0.1:8001/"; fi
    if [ "$1" != "prazan" ]; then echo "  Sa pluginom:     http://127.0.0.1:8002/"; fi
    echo
    echo "  Moderator:       <adresa>/moderator/prijava/"
    echo "                   ime: $DEMO_IME   lozinka: $DEMO_LOZINKA"
    if [ "$1" != "prazan" ]; then
        echo "                   (igra sa pluginom trazi novu lozinku pri prvoj prijavi)"
    fi
    echo
    echo "  Zaustavljanje:   Ctrl+C"
    echo "================================================================"
    echo
}

IZBOR="${1:-obe}"
case "$IZBOR" in
    prazan|plugin|obe) ;;
    *) echo "Upotreba: ./pokreni.sh [prazan|plugin]" >&2; exit 2 ;;
esac

PY="$(nadji_python)"
korak "Python: $("$PY" --version 2>&1)"

case "$IZBOR" in
    prazan) pripremi prazan; uputstvo prazan; pokreni prazan 8001 ;;
    plugin) pripremi plugin; uputstvo plugin; pokreni plugin 8002 ;;
    obe)
        pripremi prazan
        pripremi plugin
        uputstvo obe
        # Obe igre rade istovremeno; Ctrl+C gasi obe.
        trap 'kill 0' INT TERM EXIT
        pokreni prazan 8001 &
        pokreni plugin 8002 &
        wait
        ;;
esac
