#!/usr/bin/env bash
# Orkestrator: provera posle postavljanja i posle svake isporuke (plan 15.11, DEPLOY.md korak 7).
# Spolja, preko mreze, kao igrac. Treba samo bash i curl; radi sa servera ili sa bilo kog racunara.
#
#   bash deploy/provera.sh DOMEN [IP]
#     IP                    adresa servera kada DNS jos ne pokazuje na njega (curl --resolve)
#     PROVERA_NESIGURNO=1   prihvata samopotpisani sertifikat (lokalna proba, pre Let's Encrypt-a)
#
# Sve provere se izvrse i svaka se oznaci (OK ili PAO); izlaz je 1 ako je ijedna pala.
# Namerne posledice na produkciji: jedna sesija, jedna odigrana partija i u istoj sesiji jedna zapoceta (neodigrana,
# nesacuvana) dnevna partija; jedan deljeni link (istice za 30 dana,
# moderator ga moze obrisati); sedam odbijenih zahteva na prijavu (bez imena i lozinke, CSRF 403 pa 429), pa sa
# ove adrese prijava moderatora ne prolazi oko jedan minut. Ponovno pokretanje tek posle jednog minuta.

set -uo pipefail

DOMEN=${1:?upotreba: bash deploy/provera.sh DOMEN [IP]}
IP=${2:-}
OSNOVA="https://$DOMEN"

RADNI=$(mktemp -d)
trap 'rm -rf "$RADNI"' EXIT
JAR="$RADNI/kolacici"
Z="$RADNI/zaglavlja"
T="$RADNI/telo"

CURL=(curl -sS --max-time 15 --proto =http,https)
if [ "${PROVERA_NESIGURNO:-0}" = 1 ]; then CURL+=(-k); fi
if [ -n "$IP" ]; then CURL+=(--resolve "$DOMEN:80:$IP" --resolve "$DOMEN:443:$IP"); fi

UKUPNO=0
PALO=0
provera() { UKUPNO=$((UKUPNO + 1)); echo "PROVERA $UKUPNO: $1"; }
ok() { echo "  OK   $1"; }
pao() { PALO=$((PALO + 1)); echo "  PAO  $1"; }

# Zahtev: zaglavlja u $Z (bez CR), telo u $T, na izlaz samo HTTP kod (000 ako veza nije uspela).
zahtev() {
    local kod izlaz=0
    : >"$Z"
    : >"$T"
    # Neuspeh curl-a je ocekivan (444 zatvara vezu); njegov izlazni kod se cuva u $RADNI/izlaz za proveru 11.
    kod=$("${CURL[@]}" -D "$Z" -o "$T" -w '%{http_code}' "$@" 2>/dev/null) || izlaz=$?
    echo "$izlaz" >"$RADNI/izlaz"
    tr -d '\r' <"$Z" >"$Z.cist" && mv "$Z.cist" "$Z"
    echo "${kod:-000}"
}
# Odgovor nije stigao, a veza JE uspostavljena: curl 52 (prazan odgovor) ili 56 (veza prekinuta) za 444,
# 35 za odbijen TLS. Kod 7 (veza odbijena) ili 28 (isteklo vreme) znaci da server nije ni dostupan.
zatvoreno() {
    # $1 HTTP kod, ostali argumenti: prihvatljivi izlazni kodovi curl-a.
    local kod=$1 izlaz prihvatljiv
    shift
    izlaz=$(cat "$RADNI/izlaz")
    [ "$kod" = 000 ] || return 1
    for prihvatljiv in "$@"; do
        if [ "$izlaz" = "$prihvatljiv" ]; then return 0; fi
    done
    return 1
}
zaglavlje() { grep -i "^$1:" "$Z" | head -n 1; }
# Set-Cookie za ispis pri padu: ime i atributi ostaju, vrednost kolacica (kljuc sesije, CSRF) ne ide u izlaz.
bez_vrednosti() { sed -E 's/^([^:]*: *[^=;]*=)[^;]*/\1***/'; }
csrf() { awk '$6 == "csrftoken" { print $7 }' "$JAR"; }
post_json() {
    # $1 putanja, $2 telo; sa sesijom i CSRF tokenom, kao igra.js.
    zahtev -b "$JAR" -c "$JAR" -X POST -H "Content-Type: application/json" -H "X-CSRFToken: $(csrf)" \
        -H "Origin: $OSNOVA" -H "Referer: $OSNOVA/" --data-binary "$2" "$OSNOVA$1"
}

echo "Provera https://$DOMEN/ ${IP:+(adresa $IP)}"

provera "http daje 301 na https"
odgovor=$("${CURL[@]}" -o /dev/null -w '%{http_code} %{redirect_url}' "http://$DOMEN/zdravlje/" 2>/dev/null)
if [ "$odgovor" = "301 https://$DOMEN/zdravlje/" ]; then ok "$odgovor"; else pao "dobijeno: $odgovor"; fi

provera "/zdravlje/ daje 200 i {\"ok\": true}, bez Set-Cookie (aplikacija radi i cita bazu)"
kod=$(zahtev "$OSNOVA/zdravlje/")
if [ "$kod" = 200 ] && grep -q '"ok": *true' "$T" && [ -z "$(zaglavlje set-cookie)" ]; then
    ok "200 $(cat "$T")"
else
    pao "kod $kod, telo: $(head -c 200 "$T" 2>/dev/null), $(zaglavlje set-cookie | bez_vrednosti)"
fi

provera "HSTS je prisutan"
hsts=$(zaglavlje strict-transport-security)
if [ -n "$hsts" ]; then ok "$hsts"; else pao "nema Strict-Transport-Security"; fi

provera "GET / daje 200 i kolacice sessionid i csrftoken sa Secure"
kod=$(zahtev -c "$JAR" "$OSNOVA/")
sesija=$(grep -i '^set-cookie: *sessionid=' "$Z")
zastita=$(grep -i '^set-cookie: *csrftoken=' "$Z")
if [ "$kod" = 200 ] && grep -qi '; *secure' <<<"$sesija" && grep -qi '; *secure' <<<"$zastita"; then
    ok "200, oba kolacica Secure"
else
    pao "kod $kod; sessionid: $(bez_vrednosti <<<"${sesija:-nema}"); csrftoken: $(bez_vrednosti <<<"${zastita:-nema}")"
fi

provera "GET /dnevni/ daje 200 (dnevni izazov, ista sesija)"
kod=$(zahtev -b "$JAR" -c "$JAR" "$OSNOVA/dnevni/")
if [ "$kod" = 200 ]; then ok "200"; else pao "kod $kod, $(head -c 200 "$T" 2>/dev/null)"; fi

provera "/static/ stize sa Nginx-a, bez gunicorn-a; igra.js no-cache, Bootstrap godinu dana"
kod=$(zahtev "$OSNOVA/static/igra/igra.js")
kes=$(zaglavlje cache-control)
# Django dodaje Cross-Origin-Opener-Policy i X-Frame-Options na svaki odgovor; Nginx statika ih nema.
django=$(grep -iE '^(cross-origin-opener-policy|x-frame-options):' "$Z")
if [ "$kod" = 200 ] && grep -qi 'no-cache' <<<"$kes" && [ -z "$django" ]; then
    ok "igra.js 200, $kes"
else
    pao "igra.js kod $kod, ${kes:-bez Cache-Control}, ${django:+zaglavlja Django-a: $django}"
fi
kod=$(zahtev "$OSNOVA/static/igra/bootstrap-5.3.8.min.css")
kes=$(zaglavlje cache-control)
if [ "$kod" = 200 ] && grep -q 'max-age=31536000' <<<"$kes"; then ok "bootstrap 200, $kes"; else pao "bootstrap kod $kod, ${kes:-bez Cache-Control}"; fi

provera "POST /potez/ preko https sa CSRF daje 200"
POTEZ='{"krug": %d, "izbori": {"model": "sonnet", "nivo": "high", "kontekst": "taman", "podela": "sam"}}'
# shellcheck disable=SC2059  # POTEZ je namerno format
kod=$(post_json /potez/ "$(printf "$POTEZ" 1)")
if [ "$kod" = 200 ]; then ok "krug 1: 200"; else pao "krug 1: kod $kod, $(head -c 200 "$T" 2>/dev/null)"; fi

provera "partija do kraja, pa podeli vraca https:// link koji radi"
kodovi=""
for krug in 2 3 4 5 6 7 8; do
    # shellcheck disable=SC2059  # POTEZ je namerno format
    kodovi="$kodovi $(post_json /potez/ "$(printf "$POTEZ" "$krug")")"
done
kod=$(post_json /podeli/ "")
link=$(grep -o '"url": *"[^"]*"' "$T" | sed 's/^"url": *"//; s/"$//')
case "$link" in
    "https://$DOMEN/r/"*)
        kod_linka=$(zahtev "$link")
        if [ "$kod_linka" = 200 ]; then ok "podeli $kod, link https://$DOMEN/r/... daje 200"; else pao "link daje $kod_linka"; fi
        ;;
    *) pao "potezi 2-8:$kodovi; podeli kod $kod, link: ${link:-nema}" ;;
esac

provera "multipart daje 415"
kod=$(zahtev -b "$JAR" -H "X-CSRFToken: $(csrf)" -H "Origin: $OSNOVA" -F "a=b" "$OSNOVA/potez/")
if [ "$kod" = 415 ]; then ok 415; else pao "kod $kod"; fi

provera "telo od 32 KB daje 413"
head -c 32768 /dev/zero | tr '\0' 'a' >"$RADNI/veliko"
kod=$(zahtev -b "$JAR" -X POST -H "Content-Type: application/json" -H "X-CSRFToken: $(csrf)" \
    -H "Origin: $OSNOVA" --data-binary "@$RADNI/veliko" "$OSNOVA/potez/")
if [ "$kod" = 413 ]; then ok 413; else pao "kod $kod"; fi

provera "sedma prijava u minuti sa iste adrese daje 429, sa nasom dvojezicnom stranom"
kodovi=""
for _ in 1 2 3 4 5 6 7; do
    kodovi="$kodovi $(zahtev -X POST --data-binary 'username=&password=' "$OSNOVA/moderator/prijava/")"
done
read -r -a niz <<<"$kodovi"
# Telo i zaglavlja su od sedmog (poslednjeg) zahteva. HSTS strane 429 salje Nginx, a /zdravlje/ Django (provera 3):
# ista vrednost iz .env, pa se zaglavlja porede doslovno.
hsts_429=$(zaglavlje strict-transport-security)
if [ "${niz[6]:-}" = 429 ] && [ "${niz[0]:-}" != 429 ] && grep -q 'Too many sign-in attempts' "$T" \
    && [ -n "$(zaglavlje retry-after)" ] && [ -n "$hsts" ] && [ "${hsts_429,,}" = "${hsts,,}" ]; then
    ok "kodovi:$kodovi; strana 429 je nasa, $(zaglavlje retry-after); HSTS isti kao /zdravlje/"
elif [ "${niz[6]:-}" = 429 ] && [ "${niz[0]:-}" != 429 ] && grep -q 'Too many sign-in attempts' "$T"; then
    pao "kodovi:$kodovi, strana 429 je nasa, ali Retry-After ili HSTS ne odgovara: 429 [${hsts_429:-nema}], /zdravlje/ [${hsts:-nema}]"
elif [ "${niz[6]:-}" = 429 ] && [ "${niz[0]:-}" != 429 ]; then
    pao "kodovi:$kodovi, ali 429 nije nasa strana (error_page @prijava_429): $(head -c 200 "$T" 2>/dev/null)"
else
    pao "kodovi:$kodovi (ocekivano: prvih sest nije 429, sedmi 429; ako je provera pokrenuta pre manje od minut, ponoviti)"
fi

provera "nepoznat Host i nepoznat SNI: veza se zatvara bez odgovora (444)"
kod=$(zahtev -H "Host: nepoznat.invalid" "http://$DOMEN/")
if zatvoreno "$kod" 52 56; then ok "http, tudji Host: zatvoreno"; else pao "http, tudji Host: kod $kod, curl $(cat "$RADNI/izlaz")"; fi
kod=$(zahtev --http1.1 -H "Host: nepoznat.invalid" "$OSNOVA/")
if zatvoreno "$kod" 52 56; then ok "https, tudji Host: zatvoreno"; else pao "https, tudji Host: kod $kod, curl $(cat "$RADNI/izlaz")"; fi
adresa=${IP:-$(getent ahostsv4 "$DOMEN" 2>/dev/null | awk 'NR == 1 { print $1 }')}
if [ -n "$adresa" ]; then
    kod=$(zahtev --resolve "nepoznat.invalid:443:$adresa" "https://nepoznat.invalid/")
    if zatvoreno "$kod" 35; then ok "https, tudji SNI: TLS odbijen"; else pao "https, tudji SNI: kod $kod, curl $(cat "$RADNI/izlaz")"; fi
else
    pao "https, tudji SNI: NIJE PROVERENO, adresa za $DOMEN nije poznata (zadati IP kao drugi argument)"
fi

echo
echo "PROVERA ZAVRSENA: $UKUPNO provera, palo $PALO"
[ "$PALO" -eq 0 ]
