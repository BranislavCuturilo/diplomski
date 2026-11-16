# syntax=docker/dockerfile:1
# Orkestrator, isporuka (plan 15.3). Dve slike iz jednog fajla:
#   app  - Django + gunicorn, proces bez root-a, statika skupljena u gradnji;
#   web  - Nginx sa istom statikom, kopiranom iz faze app (nema deljenog volumena koji bi zastareo).
# Migracija NIJE u CMD (django-nginx-docker, pravilo 3): poseban korak isporuke, DEPLOY.md.
# Fiksni digest: nova bazna slika je svesna izmena ovih redova (proverene 2026-11-11 na Docker Hub-u).
ARG PYTHON_SLIKA=python:3.14.10-slim@sha256:9aaa474097d094040649f2162a627c0049b408f52138d980916788d80f04802f
ARG NGINX_SLIKA=nginx:1.30.6-alpine@sha256:583b7f2fce1cdb8da5ad5c39ebd3c33b98b87d493190e548bdee1fa8c619c311

# ---------------------------------------------------------------- app
FROM ${PYTHON_SLIKA} AS app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Korisnik 10001 je vlasnik samo /data (baza) i /kopije; kod ostaje root-ov i samo za citanje.
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --home-dir /nonexistent --no-create-home --shell /usr/sbin/nologin app \
 && install -d -o app -g app -m 0750 /data /kopije

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .

# Modul podesavanja je u slici, ne zavisi od administratora (plan 15.3).
ENV DJANGO_SETTINGS_MODULE=orkestrator.settings_prod

# collectstatic u gradnji. settings_prod trazi okruzenje bez rezerve, pa ovde dobija probne vrednosti
# SAMO za ovaj RUN; nijedna ne ostaje u slici kao ENV. Pravi kljuc dolazi iz .env pri pokretanju.
RUN DJANGO_SECRET_KEY=samo-za-collectstatic-u-gradnji-nije-tajna-0123456789abcdefghijk \
    DJANGO_ALLOWED_HOSTS=localhost \
    DJANGO_CSRF_TRUSTED_ORIGINS=https://localhost \
    DJANGO_BAZA=/tmp/gradnja.sqlite3 \
    DJANGO_HSTS_SEKUNDI=3600 \
    DOMEN=localhost \
    python manage.py collectstatic --noinput \
 && rm -f /tmp/gradnja.sqlite3* \
 && python -m compileall -q /app

USER app
EXPOSE 8000
CMD ["gunicorn", "--config", "/app/deploy/gunicorn.conf.py", "orkestrator.wsgi:application"]

# ---------------------------------------------------------------- web
FROM ${NGINX_SLIKA} AS web

# openssl: privremeni samopotpisani sertifikat dok Let's Encrypt ne izda pravi (DEPLOY.md, 4).
RUN apk add --no-cache openssl

# Sablon se renderuje pri pokretanju; zamenjuju se SAMO DOMEN i DJANGO_HSTS_SEKUNDI (HSTS strane 429 prijave),
# pa Nginx promenljive ($host, $scheme, ...) ostaju netaknute. Obe vrednosti pre toga proverava
# 15-provera-okruzenja.sh (ispod): envsubst ih upisuje doslovno, pa bi navodnik ili novi red ubacio direktivu.
# Koren kontejnera je samo za citanje (compose.yaml), pa rezultat ide u tmpfs /var/run, a /etc/nginx/nginx.conf
# je veza na njega: `nginx -t`, `-s reload` i `-s reopen` rade bez -c. Ako renderovanje ne uspe, veza ostaje
# prazna i Nginx NE krece (nikad ne radi sa podrazumevanom konfiguracijom slike).
ENV NGINX_ENVSUBST_FILTER=^(DOMEN|DJANGO_HSTS_SEKUNDI)$ \
    NGINX_ENVSUBST_OUTPUT_DIR=/var/run
COPY deploy/nginx.conf /etc/nginx/templates/nginx.conf.template
COPY deploy/robots.txt /srv/robots.txt
COPY --from=app /app/staticfiles /srv/static

# Pokrece ga entrypoint Nginx slike pre 20-envsubst-on-templates.sh (redosled po imenu; entrypoint ima set -e,
# pa izlaz 1 zaustavlja kontejner pre renderovanja). Vrednosti se ne skracuju i ne ispisuju; ista pravila kao
# settings_prod.py, jer `up --no-deps web` ne ceka proveru u Django-u.
COPY <<'PROVERA' /docker-entrypoint.d/15-provera-okruzenja.sh
#!/bin/sh
set -eu
pukni() {
    echo "provera okruzenja: GRESKA: $1 Nginx ne krece (.env, DEPLOY.md 3 i 11)." >&2
    exit 1
}
hsts=${DJANGO_HSTS_SEKUNDI-}
case $hsts in
    "" | *[!0123456789]*) pukni "DJANGO_HSTS_SEKUNDI mora biti ceo broj sekundi, samo cifre, bez razmaka i navodnika." ;;
esac
case $hsts in
    0*) pukni "DJANGO_HSTS_SEKUNDI mora biti veci od 0 i bez vodece nule (Nginx salje niz doslovno, Django kao broj)." ;;
esac
domen=${DOMEN-}
case $domen in
    "" | *[!abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-]*)
        pukni "DOMEN sme da sadrzi samo slova a-z, cifre, tacku i crticu (ime hosta, bez https:// i kose crte)." ;;
    -* | .* | *. | *..* | *.-* | *-.*)
        pukni "DOMEN nije ispravno ime hosta (deo imena ne sme biti prazan ni poceti ili zavrsiti crticom)." ;;
esac
echo "provera okruzenja: DOMEN i DJANGO_HSTS_SEKUNDI su ispravni"
PROVERA

# Let's Encrypt sertifikat ako postoji, inace samopotpisan.
COPY <<'SKRIPTA' /docker-entrypoint.d/25-tls-sertifikat.sh
#!/bin/sh
set -eu
tls=/etc/nginx/tls
le="/etc/letsencrypt/live/${DOMEN}"
mkdir -p "$tls"
if [ -s "$le/fullchain.pem" ] && [ -s "$le/privkey.pem" ]; then
    ln -sf "$le/fullchain.pem" "$tls/fullchain.pem"
    ln -sf "$le/privkey.pem" "$tls/privkey.pem"
    echo "tls: sertifikat iz $le"
else
    if [ ! -s "$tls/samopotpisan.pem" ]; then
        openssl req -x509 -newkey rsa:2048 -nodes -days 30 -subj "/CN=${DOMEN}" \
            -addext "subjectAltName=DNS:${DOMEN}" \
            -keyout "$tls/samopotpisan.key" -out "$tls/samopotpisan.pem" 2>/dev/null
    fi
    ln -sf "$tls/samopotpisan.pem" "$tls/fullchain.pem"
    ln -sf "$tls/samopotpisan.key" "$tls/privkey.pem"
    echo "tls: UPOZORENJE: nema sertifikata u $le, radi PRIVREMENI SAMOPOTPISANI (DEPLOY.md, korak 4)" >&2
fi
SKRIPTA

# CRLF iz Windows git-a bi slomio #!/bin/sh; skripte moraju biti izvrsne, inace ih entrypoint preskace.
# default.conf se ne koristi (nginx.conf ga ne ukljucuje); bez njega 10-listen-on-ipv6 ne pokusava upis.
RUN sed -i 's/\r$//' /docker-entrypoint.d/15-provera-okruzenja.sh /docker-entrypoint.d/25-tls-sertifikat.sh \
 && chmod 0755 /docker-entrypoint.d/15-provera-okruzenja.sh /docker-entrypoint.d/25-tls-sertifikat.sh \
 && rm -f /etc/nginx/conf.d/default.conf \
 && ln -sfn /var/run/nginx.conf /etc/nginx/nginx.conf \
 && install -d /var/www/certbot /var/log/nginx/pristup /etc/nginx/tls
