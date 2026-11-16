#!/usr/bin/env bash
# Orkestrator: proba opterecenja pre javnog pustanja (plan 15.2 i 15.11, T2; DEPLOY.md, odeljak 7a).
# Na serveru, iz /opt/orkestrator/trenutno, posle `docker compose up -d` (web mora da radi).
#
#   bash deploy/proba-opterecenja.sh [TRAJANJE_SEKUNDI] [ZAHTEVA_U_SEKUNDI]      podrazumevano 300 i 50
#
# Produkciona baza se NE dira. Proba podize ODVOJEN compose projekat `orkestrator-proba`: isti kod i ista slika,
# ali svoj prazan volumen baze (orkestrator-proba_baza), svoju mrezu i bez objavljenih portova. Igraci gadjaju
# njegov gunicorn direktno (app:8000), pa se meri aplikacija i SQLite, a ne Nginx-ovo ogranicenje po adresi.
# Na kraju, i posle neuspeha, proba se gasi, a njen volumen brise po TACNOM imenu (nikad `down -v`).
# Zasto ne kopija produkcione baze ni `flush`: proba bi upisivala u istu bazu ili bi brisanje moglo da pogodi
# pravu. Pre javnog pustanja produkciona baza je ionako prazna, pa prazna probna baza nije manje verna.
#
# Kroz Nginx ide samo kratak nalet GET /zdravlje/ (samo citanje, bez sesije), da potvrdi da 429 radi.
# Svaki korak pise oznaku pre izvrsavanja; izlaz 0 samo kada sve prodje.

set -Eeuo pipefail
umask 077

KOREN=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$KOREN"

PROBA=orkestrator-proba
VOLUMEN=${PROBA}_baza
TRAJANJE=${1:-300}
ZS=${2:-50}
RADNI=$(mktemp -d)

korak() {
    echo "$(date '+%F %T') proba KORAK $1: $2"
}

pukni() {
    echo "$(date '+%F %T') proba: $1" >&2
    return 1
}

pocisti() {
    local izlaz=$?
    korak CISCENJE "gasenje projekta $PROBA i brisanje volumena $VOLUMEN (produkcija ostaje)"
    # Neuspeh ciscenja ne sme da sakrije ishod probe; ispisuje se i ostavlja tacnu komandu.
    docker compose -p "$PROBA" down --remove-orphans >/dev/null 2>&1 \
        || echo "UPOZORENJE: rucno: docker compose -p $PROBA down" >&2
    docker volume rm "$VOLUMEN" >/dev/null 2>&1 \
        || echo "UPOZORENJE: volumen $VOLUMEN nije obrisan; rucno: docker volume rm $VOLUMEN" >&2
    rm -rf "$RADNI"
    if [ "$izlaz" -eq 0 ]; then
        korak KRAJ "PROBA PROSLA"
    else
        echo "$(date '+%F %T') proba KORAK KRAJ: PROBA NIJE PROSLA (izlaz $izlaz)" >&2
    fi
    exit "$izlaz"
}
trap pocisti EXIT

proba() { docker compose -p "$PROBA" "$@"; }

DOMEN=$(sed -n 's/^DOMEN=//p' .env | tail -n 1)
DOMEN=${DOMEN%$'\r'}
[ -n "$DOMEN" ] || pukni "DOMEN nije postavljen u .env"
[ "$PROBA" != orkestrator ] || pukni "projekat probe ne sme biti produkcioni"

korak 0/7 "okruzenje: $(docker version --format 'Docker {{.Server.Version}}'), $(docker compose version --short), $(nproc) CPU, $(free -m | awk '/^Mem:/ { print $2 }') MB RAM"
docker image ls --format '{{.Repository}}:{{.Tag}} {{.ID}} {{.CreatedAt}}' | grep '^orkestrator-' \
    || pukni "nema slika orkestrator-* (prvo docker compose build)"

korak 1/7 "zaostala proba se uklanja (samo projekat $PROBA)"
docker compose -p "$PROBA" down --remove-orphans
if docker volume inspect "$VOLUMEN" >/dev/null 2>&1; then docker volume rm "$VOLUMEN"; fi

korak 2/7 "migrate u prazan volumen $VOLUMEN"
proba run --rm --no-deps -T app python manage.py migrate --noinput

korak 3/7 "pokretanje gunicorn-a probe (bez portova) i cekanje healthcheck-a"
proba up -d --no-build app
stanje=""
for _ in $(seq 1 30); do
    stanje=$(docker inspect --format '{{.State.Health.Status}}' "$(proba ps -q app)")
    if [ "$stanje" = healthy ]; then break; fi
    sleep 3
done
[ "$stanje" = healthy ] || pukni "app probe nije zdrav posle 90 s: $stanje"

korak 4/7 "opterecenje: $ZS z/s, $TRAJANJE s, cele partije direktno na app:8000 probe"
if proba run --rm --no-deps -T app python deploy/opterecenje.py --nacin igra --cilj http://app:8000 \
    --host "$DOMEN" --zs "$ZS" --trajanje "$TRAJANJE"; then
    igra=0
else
    igra=$?
fi

korak 5/7 "log app probe: 'database is locked' i greske (Django ERROR, gunicorn [ERROR]/[CRITICAL], Traceback)"
proba logs --no-color app >"$RADNI/log"
zakljucano=$(grep -c 'database is locked' "$RADNI/log" || true)  # grep -c izlazi sa 1 kada je broj 0
GRESKA_U_LOGU=' ERROR |\[ERROR\]|\[CRITICAL\]|Traceback'
greske=$(grep -cE "$GRESKA_U_LOGU" "$RADNI/log" || true)          # isto
# Log ne sme da nosi token deljenog linka (samo /r/-), kolacic sesije ni lozinku (plan 15.4). Redovi se ne ispisuju.
TAJNA_U_LOGU='/r/[^-]|sessionid|password'
tajne=$(grep -ciE "$TAJNA_U_LOGU" "$RADNI/log" || true)            # isto
echo "database is locked: $zakljucano; ERROR/Traceback redova: $greske; redova sa /r/<token>, sessionid ili password: $tajne"
if [ "$greske" -gt 0 ]; then
    grep -E "$GRESKA_U_LOGU" "$RADNI/log" | cut -c 1-200 | sort | uniq -c | sort -rn | sed -n 1,10p
fi

korak 6/7 "kratak nalet kroz Nginx (produkcioni web, samo GET /zdravlje/): ocekuje se 429"
if docker compose run --rm --no-deps -T app python deploy/opterecenje.py --nacin zdravlje --cilj https://web \
    --host "$DOMEN" --nesigurno --zs 40 --trajanje 3; then
    nginx=0
else
    nginx=$?
fi

korak 7/7 "presuda"
echo "opterecenje: $([ "$igra" -eq 0 ] && echo PROLAZ || echo PAD)"
echo "database is locked = 0 i bez gresaka u logu: $([ "$zakljucano" -eq 0 ] && [ "$greske" -eq 0 ] && echo PROLAZ || echo PAD)"
echo "log bez tokena, sessionid i password: $([ "$tajne" -eq 0 ] && echo PROLAZ || echo PAD)"
echo "429 kroz Nginx: $([ "$nginx" -eq 0 ] && echo PROLAZ || echo PAD)"
[ "$igra" -eq 0 ] && [ "$zakljucano" -eq 0 ] && [ "$greske" -eq 0 ] && [ "$tajne" -eq 0 ] && [ "$nginx" -eq 0 ] \
    || pukni "bar jedna presuda je PAD"
