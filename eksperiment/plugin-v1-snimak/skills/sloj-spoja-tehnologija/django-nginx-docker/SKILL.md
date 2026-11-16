---
name: django-nginx-docker
description: >
  Django iza Nginx-a, u Docker-u, sa TLS sertifikatom: podesavanja koja se
  pokvare tek na serveru. Ucitaj PRE izmene settings za produkciju, Dockerfile,
  docker-compose, nginx.conf ili deploy skripte. Okidaci: "deploy", "na serveru
  ne radi", "CSRF na produkciji", "redirect petlja", "staticki fajlovi 404".
---

# django-nginx-docker

## Tri pravila koja se nikad ne preskacu

1. **Iza Nginx-a sa TLS-om Django ne zna da je veza HTTPS.** Bez ovoga
   `SECURE_SSL_REDIRECT` pravi beskonacnu petlju preusmeravanja:
   ```python
   SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
   ```
   ```nginx
   proxy_set_header X-Forwarded-Proto $scheme;
   ```

2. **Django 4.0+: `CSRF_TRUSTED_ORIGINS` trazi semu**: `"https://beleske.rs"`, ne
   `"beleske.rs"`. Bez toga svaki POST na produkciji vraca 403, a lokalno radi.

3. **Migracije se ne pokrecu u `CMD` kontejnera.** Vise replika = vise
   istovremenih migracija. Migracija je poseban korak isporuke, jednom, pre
   pokretanja nove verzije.

## Ostalo

- `collectstatic` u build fazi slike; Nginx servira `STATIC_ROOT` direktno, ne kroz Django.
- `DEBUG = False` zahteva `ALLOWED_HOSTS`; vrednost iz promenljive okruzenja, ne iz koda.
- Tajne (`SECRET_KEY`, lozinka baze) u `.env` van git-a; `docker-compose` ih cita kroz `env_file`.
- Zdravstvena provera kontejnera gadja endpoint koji dira bazu, ne samo staticku stranu.
