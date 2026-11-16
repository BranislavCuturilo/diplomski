#!/usr/bin/env bash
# Orkestrator: periodicni zadaci na domacinu (plan 15.6). Cron: /etc/cron.d/orkestrator (DEPLOY.md, 8).
#
#   bash deploy/odrzavanje.sh kopija             svaki dan 03:30  kopija baze (VACUUM INTO), 7 dnevnih
#   bash deploy/odrzavanje.sh ciscenje           svaki dan 04:10  clearsessions, pa deljeni_ocisti
#   bash deploy/odrzavanje.sh nedeljno           nedelja 04:40    dnevnik_ocisti; nedeljna kopija (4); sifrovana za van servera
#   bash deploy/odrzavanje.sh logovi             svaki dan 00:05  rotacija pristupnog loga Nginx-a, cuva se 14 dana
#   bash deploy/odrzavanje.sh sertifikat         svaki dan 05:15  obnova Let's Encrypt sertifikata
#   bash deploy/odrzavanje.sh nadzor             na 15 minuta     disk 80%, zdravlje, sertifikat 14 dana, starost kopije
#   bash deploy/odrzavanje.sh proba-povratka [KOPIJA]   mesecno, rucno: provera kopije iz KOPIJE_DIR
#
# Svaki korak pise oznaku pre izvrsavanja. Svaki neuspeh je fatalan: izlaz razlicit od 0 i poruka u log domacina
# (journalctl -t orkestrator). Jedini izuzetak je `nadzor`: proveri sve, pa padne ako je bilo nalaza.
# Kopija baze ide SAMO kroz baza_kopija (VACUUM INTO); fajl baze se nikad ne kopira dok aplikacija radi.

set -Eeuo pipefail
umask 077
# Izlaz alata (stat %F, df, sort) bez prevoda i sa ASCII poretkom: cron moze imati npr. LANG=sr_RS.UTF-8, a skripta
# poredi tekst "regular file" i imena po bajtovima. Poruke ove skripte su ionako na srpskom latinicom.
export LC_ALL=C

KOREN=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$KOREN"
ZADATAK=${1:-}

zapisi() {
    # Poruka u log domacina. Bez syslog-a (npr. minimalan sistem) ishod ostaje u izlazu i izlaznom kodu.
    logger -t orkestrator -p "user.$1" -- "$2" 2>/dev/null || true  # ocekivano: logger ponekad nije dostupan
}

korak() {
    echo "$(date '+%F %T') $ZADATAK KORAK $1: $2"
}

pukni() {
    echo "$(date '+%F %T') $ZADATAK: $1" >&2
    return 1
}

neuspeh() {
    local izlaz=$? red=$1
    # U podljusci ($(...)) samo izlaz; poruku pise glavna ljuska, jednom.
    if [ "$BASHPID" != "$$" ]; then exit "$izlaz"; fi
    local poruka="NEUSPEH: odrzavanje $ZADATAK, izlaz $izlaz, red $red"
    echo "$(date '+%F %T') $poruka" >&2
    zapisi err "$poruka"
    exit "$izlaz"
}
trap 'neuspeh $LINENO' ERR

iz_env() {
    # Vrednost iz .env bez izvrsavanja fajla (u njemu je i tajni kljuc); $2 ako je nema.
    local vrednost
    vrednost=$(sed -n "s/^$1=//p" .env | tail -n 1)
    vrednost=${vrednost%$'\r'}
    printf '%s' "${vrednost:-$2}"
}

KOPIJE_DIR=$(iz_env KOPIJE_DIR /var/backups/orkestrator)
# Sifrovane kopije: van KOPIJE_DIR i samo root-ove. KOPIJE_DIR je upisiv za korisnika 10001 iz kontejnera, pa
# root ovde ne veruje nijednom imenu koje nije sam proverio (revizija N2).
VAN_SERVERA_DIR=$(iz_env KOPIJE_VAN_SERVERA_DIR /var/backups/orkestrator-van-servera)

# Jedini oblici imena koje skripta dira: <vrsta>-YYYYMMDD-HHMMSS.sqlite3[.gpg]. Sve ostalo u direktorijumu se
# preskace (npr. "dnevna-0 .env" ili simbolicka veza koju je napravio kontejner).
VREME='[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9][0-9][0-9]'

kopije() {
    # $1 direktorijum, $2 vrsta (dnevna|nedeljna), $3 nastavak (.sqlite3 ili .sqlite3.gpg), ostalo: dodatni uslovi
    # za find. Samo obicni fajlovi (find -type f ne prati veze), imena odvojena sa \0, od najnovije.
    local dir=$1 vrsta=$2 nastavak=$3
    shift 3
    find "$dir" -mindepth 1 -maxdepth 1 -type f -name "$vrsta-$VREME$nastavak" "$@" -print0 | sort -rz
}

ukloni_starije() {
    # $1 direktorijum, $2 vrsta, $3 nastavak, $4 koliko najnovijih ostaje. Ime nosi vreme, pa je abecedni red i
    # vremenski. rm brise samo ime (i vezu, nikad njen cilj).
    kopije "$1" "$2" "$3" | tail -zn "+$(($4 + 1))" | xargs -0r rm -f --
}

najnovija() {
    # Najnovija kopija vrste $1 u KOPIJE_DIR; $2 (opciono) najveca starost u minutima. Prazno ako je nema.
    local starost=()
    if [ -n "${2:-}" ]; then starost=(-mmin "-$2"); fi
    # sed cita ceo ulaz (head bi mogao da prekine sort, pa pipefail javlja 141).
    kopije "$KOPIJE_DIR" "$1" .sqlite3 "${starost[@]}" | sed -zn 1p | tr -d '\0'
}

van_servera_dir() {
    # Direktorijum sifrovanih kopija: ne sme biti veza, ni unutar KOPIJE_DIR; vlasnik root, 0700.
    local van kopije
    if [ -L "$VAN_SERVERA_DIR" ]; then pukni "$VAN_SERVERA_DIR je simbolicka veza"; fi
    install -d -m 0700 -o root -g root "$VAN_SERVERA_DIR"
    van=$(realpath -e -- "$VAN_SERVERA_DIR")
    kopije=$(realpath -e -- "$KOPIJE_DIR")
    case "$van/" in
        "$kopije"/*) pukni "KOPIJE_VAN_SERVERA_DIR ($van) ne sme biti unutar KOPIJE_DIR ($kopije)" ;;
    esac
    [ "$(stat -c '%u %a' -- "$van")" = "0 700" ] || pukni "$van mora imati vlasnika root i prava 700"
}

# Citanje kopije za sifrovanje; radi kao korisnik 10001 (setpriv u zadatak_nedeljno), $1 je putanja kopije.
# Izlaz 65: ne otvara se; 66: otvoreno nije fajl sa tim imenom (stat imena BEZ -L, pa je veza uvek razlika);
# 67: prazan fajl (stat: "regular empty file"); 64: nije obican fajl korisnika 10001. LC_ALL=C nasledjuje od
# skripte (stat %F bez prevoda). Tek posle provera bajtovi idu na izlaz (gpg).
CITAJ_KOPIJU=$(cat <<'SH'
exec 3<"$1" || exit 65
otvoreno=$(stat -L -c '%d:%i %F %u' /proc/self/fd/3) || exit 65
ime=$(stat -c '%d:%i %F %u' -- "$1") || exit 66
[ "$otvoreno" = "$ime" ] || exit 66
case ${otvoreno#* } in
    "regular file 10001") ;;
    "regular empty file 10001") exit 67 ;;
    *) exit 64 ;;
esac
exec cat <&3
SH
)

# ---------------------------------------------------------------------------------------------- zadaci

zadatak_kopija() {
    local ime
    ime="dnevna-$(date +%Y%m%d-%H%M%S).sqlite3"
    korak 1/3 "kopija baze u $KOPIJE_DIR/$ime (baza_kopija: VACUUM INTO, pa integrity_check)"
    docker compose exec -T app python manage.py baza_kopija "/kopije/$ime"
    korak 2/3 "kopija postoji na domacinu i nije prazna"
    [ -s "$KOPIJE_DIR/$ime" ] || pukni "nema $KOPIJE_DIR/$ime posle baza_kopija"
    korak 3/3 "ostaje 7 najnovijih dnevnih kopija"
    ukloni_starije "$KOPIJE_DIR" dnevna .sqlite3 7
}

zadatak_ciscenje() {
    korak 1/2 "clearsessions (istekle sesije)"
    docker compose exec -T app python manage.py clearsessions
    korak 2/2 "deljeni_ocisti (istekli deljeni linkovi)"
    docker compose exec -T app python manage.py deljeni_ocisti
}

zadatak_nedeljno() {
    local primalac dnevna nedeljna izlaz
    primalac=$(iz_env KOPIJA_GPG_PRIMALAC "")
    korak 1/5 "dnevnik_ocisti (zapisi stariji od 365 dana)"
    docker compose exec -T app python manage.py dnevnik_ocisti
    korak 2/5 "nedeljna kopija = najnovija dnevna, najvise 26 sati stara"
    dnevna=$(najnovija dnevna 1560)
    [ -n "$dnevna" ] || pukni "nema dnevne kopije mladje od 26 sati u $KOPIJE_DIR (radi li cron za kopija?)"
    dnevna=$(basename -- "$dnevna")
    nedeljna="nedeljna-${dnevna#dnevna-}"
    # Tvrda veza: brisanje dnevne posle 7 dana ne brise nedeljnu, a ne zauzima dupli prostor.
    # -P: ako je IZVOR u meduvremenu zamenjen vezom, nastaje veza na vezu, nikad na njen cilj (provera u koraku 4
    # je odbija). -T: ODREDISTE je uvek ime fajla; unapred podmetnuta veza nedeljna-<vreme>.sqlite3 na
    # direktorijum se zamenjuje (-f), a tvrda veza ne zavrsi u tom direktorijumu.
    ln -fPT -- "$KOPIJE_DIR/$dnevna" "$KOPIJE_DIR/$nedeljna"
    korak 3/5 "ostaju 4 najnovije nedeljne kopije"
    ukloni_starije "$KOPIJE_DIR" nedeljna .sqlite3 4
    korak 4/5 "sifrovana kopija za van servera: $VAN_SERVERA_DIR/$nedeljna.gpg"
    # Pun otisak kljuca (40 heksa znakova, 64 za v5), ne ID ni adresa: drugi kljuc sa istom adresom ne prolazi.
    [[ $primalac =~ ^([0-9A-Fa-f]{40}|[0-9A-Fa-f]{64})$ ]] \
        || pukni "KOPIJA_GPG_PRIMALAC mora biti pun otisak kljuca, 40 heksa znakova (DEPLOY.md, 9)"
    van_servera_dir
    command -v setpriv >/dev/null || pukni "nema setpriv (paket util-linux); kopija se cita samo kao korisnik 10001"
    # Kontejner app (korisnik 10001) moze da preimenuje ili zameni ime kopije i posle ln (revizija N2). Zato:
    # - kopiju OTVARA korisnik 10001 (setpriv), ne root: veza na fajl van KOPIJE_DIR (npr. ziva baza u
    #   /var/lib/docker, koji 10001 ne moze ni da prodje) ili na uredjaj ne otvara se sa pravima root-a;
    # - otvara se jednom (fd 3), pa se uredjaj:inode otvorenog fajla poredi sa imenom BEZ pracenja veze: veza ili
    #   ime zamenjeno posle otvaranja daju razliku i glasan pad; uz to obican fajl i vlasnik 10001;
    # - gpg (root) cita samo tok bajtova i pise privremeni fajl u VAN_SERVERA_DIR, koji postaje pravi tek posle
    #   uspeha oba dela; pri padu se brise. timeout: podmetnuta imenovana cev bi inace zauvek blokirala otvaranje.
    # setpriv uz to brise nasledljiva i ogranicavajuca ovlascenja i zabranjuje nove privilegije (setuid programi),
    # odbrana u dubinu: proces koji cita kopiju nema nijedno root ovlascenje ni put nazad do njih.
    izlaz=0
    privremeni="$VAN_SERVERA_DIR/.$nedeljna.gpg.novo"
    # shellcheck disable=SC2016  # $1..$4 su argumenti unutrasnjeg bash-a
    timeout 1800 bash -c '
        set -o pipefail
        setpriv --reuid=10001 --regid=10001 --clear-groups --inh-caps=-all --bounding-set=-all --no-new-privs \
            -- bash -c "$4" citaj "$1" \
            | gpg --batch --yes --trust-model always --recipient "$2" --output "$3" --encrypt
    ' sifruj "$KOPIJE_DIR/$nedeljna" "$primalac" "$privremeni" "$CITAJ_KOPIJU" || izlaz=$?
    if [ "$izlaz" -ne 0 ]; then rm -f -- "$privremeni"; fi
    case $izlaz in
        0) mv -f -- "$privremeni" "$VAN_SERVERA_DIR/$nedeljna.gpg" ;;
        64) pukni "$KOPIJE_DIR/$nedeljna nije obican fajl korisnika 10001; ne sifruje se" ;;
        65) pukni "$KOPIJE_DIR/$nedeljna ne moze da se otvori kao korisnik 10001" ;;
        66) pukni "$KOPIJE_DIR/$nedeljna: otvoreni fajl nije fajl sa tim imenom (veza ili zamena posle ln); ne sifruje se" ;;
        67) pukni "$KOPIJE_DIR/$nedeljna je prazan (0 bajtova); prazna kopija se ne sifruje (proveriti dnevnu kopiju)" ;;
        124) pukni "sifrovanje nije zavrseno za 30 minuta" ;;
        *) pukni "citanje ili gpg nije uspeo (izlaz $izlaz)" ;;
    esac
    korak 5/5 "ostaju 4 najnovije sifrovane; prenos van servera radi alat klijenta (DEPLOY.md, 9)"
    ukloni_starije "$VAN_SERVERA_DIR" nedeljna .sqlite3.gpg 4
}

zadatak_logovi() {
    korak 1/3 "rotacija pristupnog loga Nginx-a (pristup.log -> pristup-<vreme>.log), nginx -s reopen"
    # shellcheck disable=SC2016  # $(date) se izvrsava u kontejneru
    docker compose exec -T web sh -c \
        'cd /var/log/nginx/pristup && if [ -s pristup.log ]; then mv pristup.log "pristup-$(date +%Y%m%d-%H%M%S).log"; fi && nginx -s reopen'
    korak 2/3 "sazimanje rotiranih logova starijih od sat vremena"
    docker compose exec -T web find /var/log/nginx/pristup -name 'pristup-*.log' -mmin +60 -exec gzip -9 {} +
    korak 3/3 "brisanje logova starijih od 14 dana (plan 15.4)"
    docker compose exec -T web find /var/log/nginx/pristup -name 'pristup-*.log.gz' -mtime +13 -delete
}

zadatak_sertifikat() {
    korak 1/2 "certbot renew (obnavlja tek kad do isteka ostane manje od 30 dana)"
    docker compose run --rm -T certbot renew --quiet
    korak 2/2 "Nginx ponovo cita sertifikat, bez prekida veza"
    docker compose exec -T web nginx -s reload
}

zadatak_nadzor() {
    local nalaza=0 putanja zauzeto id stanje veza docker_podaci
    javi() {
        nalaza=$((nalaza + 1))
        echo "  NALAZ: $1" >&2
        zapisi warning "nadzor: $1"
    }

    korak 1/4 "zauzetost diska, granica 80% (Docker podaci i kopije)"
    # Posebna dodela: neuspeh unutar liste `for` ne bi zaustavio zadatak.
    docker_podaci=$(docker info --format '{{.DockerRootDir}}')
    for putanja in "$docker_podaci" "$KOPIJE_DIR"; do
        zauzeto=$(df -P "$putanja" | awk 'NR == 2 { sub("%", "", $5); print $5 }')
        if [ "$zauzeto" -ge 80 ]; then javi "disk sa $putanja zauzet $zauzeto%"; fi
    done

    korak 2/4 "zdravlje aplikacije (healthcheck kontejnera app, /zdravlje/ cita bazu)"
    id=$(docker compose ps -q app)
    if [ -z "$id" ]; then
        javi "kontejner app ne radi"
    else
        stanje=$(docker inspect --format '{{.State.Health.Status}}' "$id")
        if [ "$stanje" != healthy ]; then javi "app nije zdrav: $stanje"; fi
    fi

    korak 3/4 "sertifikat: nije samopotpisan i vazi jos bar 14 dana"
    if ! veza=$(docker compose exec -T web readlink /etc/nginx/tls/fullchain.pem); then
        javi "kontejner web ne odgovara"
    else
        case "$veza" in
            *samopotpisan*) javi "Nginx radi sa PRIVREMENIM samopotpisanim sertifikatom (DEPLOY.md, 4)" ;;
        esac
        if ! docker compose exec -T web openssl x509 -checkend 1209600 -noout -in /etc/nginx/tls/fullchain.pem >/dev/null; then
            javi "sertifikat istice za manje od 14 dana"
        fi
    fi

    korak 4/4 "najnovija dnevna kopija nije starija od 26 sati"
    if [ -z "$(najnovija dnevna 1560)" ]; then javi "nema dnevne kopije mladje od 26 sati u $KOPIJE_DIR"; fi

    [ "$nalaza" -eq 0 ] || pukni "nadzor: $nalaza nalaza"
}

PY_REDOVI=$(cat <<'PY'
import sqlite3
import sys

putanja, nacin = sys.argv[1], sys.argv[2]
veza = sqlite3.connect(f"file:{putanja}?{nacin}", uri=True)
nalaz = [red[0] for red in veza.execute("PRAGMA integrity_check")]
print("integrity_check:", ", ".join(nalaz))
tabele = [
    red[0]
    for red in veza.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
]
for tabela in tabele:
    broj = veza.execute(f'SELECT COUNT(*) FROM "{tabela}"').fetchone()[0]
    print(f"  {tabela}: {broj}")
sys.exit(0 if nalaz == ["ok"] else 1)
PY
)

zadatak_proba_povratka() {
    local kopija=${1:-}
    korak 1/4 "izbor kopije (ime fajla u $KOPIJE_DIR; bez argumenta najnovija dnevna)"
    if [ -z "$kopija" ]; then kopija=$(najnovija dnevna); fi
    [ -n "$kopija" ] || pukni "nema nijedne dnevne kopije u $KOPIJE_DIR"
    kopija=$(basename -- "$kopija")
    [ -s "$KOPIJE_DIR/$kopija" ] || pukni "nema $KOPIJE_DIR/$kopija (kopija mora biti u KOPIJE_DIR)"
    echo "kopija: $KOPIJE_DIR/$kopija"

    korak 2/4 "integrity_check i broj redova po tabeli u kopiji (samo citanje)"
    docker compose run --rm --no-deps -T app python -c "$PY_REDOVI" "/kopije/$kopija" "mode=ro&immutable=1"

    korak 3/4 "Django check i migrate --check nad privremenim primerkom kopije (/tmp kontejnera)"
    # shellcheck disable=SC2016  # $1 se izvrsava u kontejneru
    docker compose run --rm --no-deps -T -e DJANGO_BAZA=/tmp/proba.sqlite3 app sh -c \
        'cp "/kopije/$1" /tmp/proba.sqlite3 && python manage.py check && python manage.py migrate --check' \
        sh "$kopija"

    korak 4/4 "broj redova u radnoj bazi, za poredjenje (samo citanje)"
    docker compose exec -T app python -c "$PY_REDOVI" /data/db.sqlite3 "mode=ro"
    echo "Uporediti brojeve iz koraka 2 i 4: razlika je samo ono sto je upisano posle kopije."
}

# ---------------------------------------------------------------------------------------------- ulaz

korak POCETAK "koren $KOREN"
case "$ZADATAK" in
    kopija) zadatak_kopija ;;
    ciscenje) zadatak_ciscenje ;;
    nedeljno) zadatak_nedeljno ;;
    logovi) zadatak_logovi ;;
    sertifikat) zadatak_sertifikat ;;
    nadzor) zadatak_nadzor ;;
    proba-povratka) zadatak_proba_povratka "${2:-}" ;;
    *)
        echo "upotreba: bash $0 kopija|ciscenje|nedeljno|logovi|sertifikat|nadzor|proba-povratka [KOPIJA]" >&2
        exit 2
        ;;
esac
korak KRAJ "uspesno"
zapisi info "odrzavanje $ZADATAK: uspesno"
