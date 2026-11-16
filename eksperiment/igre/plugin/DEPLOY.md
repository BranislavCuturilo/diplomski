# Orkestrator: postavljanje na server

Uputstvo za administratora. Svaki korak ima komandu i ocekivani ishod; ako ishod nije takav, ne ide se dalje.
Sve komande se izvrsavaju kao root na serveru, osim ako pise drugacije.
Posle koraka 3, na pocetku svake sesije:

```
cd /opt/orkestrator/trenutno && DOMEN=$(sed -n 's/^DOMEN=//p' .env)
```

```
Internet -> web: Nginx :80/:443 (TLS, staticki fajlovi, ogranicenje brzine)
         -> app: gunicorn :8000, 4 radnika, port se NE objavljuje
         -> SQLite /data/db.sqlite3 na Docker volumenu `orkestrator_baza`
```

| Sta | Gde |
|---|---|
| izdanja koda | `/opt/orkestrator/izdanja/<verzija>/` |
| tekuce izdanje | `/opt/orkestrator/trenutno` (simbolicka veza); **sve komande se pokrecu odavde** |
| tajne i podesavanja | `/opt/orkestrator/.env` (prava 600), veza na njega u svakom izdanju |
| baza | Docker volumen `orkestrator_baza` |
| kopije baze | `/var/backups/orkestrator` (`KOPIJE_DIR`), NISU sifrovane |
| sifrovane kopije za van servera | `/var/backups/orkestrator-van-servera` (samo root) |
| sertifikat | Docker volumen `orkestrator_certbot_conf` |
| log periodicnih zadataka | `/var/log/orkestrator.log` i `journalctl -t orkestrator` |

---

## 1. Zahtevi

- Linux (Debian 12 ili Ubuntu 24.04 LTS), **2 vCPU, 2 GB RAM, 20 GB SSD**.
- Docker Engine 24 ili noviji i compose plugin 2.20 ili noviji: https://docs.docker.com/engine/install/
- Paketi: `apt install unzip curl gnupg`. Uz to `setpriv` iz paketa `util-linux` (na Debian-u i Ubuntu-u je vec instaliran): `odrzavanje.sh nedeljno` njime cita kopiju kao korisnik 10001, ne kao root.
- Domen klijenta, **samo zapis A** (IPv4). Zapis AAAA se NE dodaje ni kada server ima IPv6: verzija 1 slusa samo na IPv4, a IPv6 je kasniji korak (odeljak 13). `orkestrator.example` je rezervisano ime i ne moze se koristiti.
- Otvoreni portovi 22, 80 i 443; sve ostalo zatvoreno.
- Mesto za kopije van servera.

```
docker version && docker compose version
command -v setpriv && setpriv --version       # util-linux 2.38 (Debian 12) ili 2.39 (Ubuntu 24.04)
setpriv --reuid=65534 --regid=65534 --clear-groups --inh-caps=-all --bounding-set=-all --no-new-privs -- id -u   # 65534
timedatectl set-timezone Europe/Belgrade      # vremena u cron-u su lokalna
ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw enable
```

Docker objavljene portove otvara mimo ufw-a. Zato compose objavljuje samo 80 i 443, a port 8000 se nikad ne objavljuje.

## 2. Kod

Kod stize kao arhiva `orkestrator-<verzija>.zip`, uz kontrolni zbir `orkestrator-<verzija>.zip.sha256`. Koren arhive je direktorijum `<verzija>/`.

Kontrolni zbir je dokaz porekla samo ako stize **drugim kanalom** od arhive (npr. arhiva kroz deljeni direktorijum, a `.sha256` porukom ili procitan telefonom). Zbir poslat zajedno sa arhivom stiti samo od ostecenja pri prenosu, ne od podmetnute arhive.

```
install -d -m 0755 /opt/orkestrator/izdanja
cd /opt/orkestrator
sha256sum -c orkestrator-v1.0.0.zip.sha256              # ocekivano: "orkestrator-v1.0.0.zip: OK"
unzip -q orkestrator-v1.0.0.zip -d izdanja
ls izdanja/v1.0.0/compose.yaml                          # postoji
grep -l $'\r' izdanja/v1.0.0/deploy/* izdanja/v1.0.0/compose.yaml || echo "krajevi redova: OK"
```

Ako `grep` ispise ijedan fajl, arhiva ima Windows krajeve redova i skripte nece raditi. Arhiva se tada vraca razvijaocu.

## 3. Podesavanja (.env), tajni kljuc, direktorijum kopija

```
cd /opt/orkestrator
cp izdanja/v1.0.0/deploy/env.primer .env && chmod 600 .env
openssl rand -hex 40                                    # ovo je DJANGO_SECRET_KEY
nano .env                                               # VERZIJA, DOMEN, DJANGO_SECRET_KEY, LETSENCRYPT_EMAIL, KOPIJA_GPG_PRIMALAC
ln -s /opt/orkestrator/.env izdanja/v1.0.0/.env
ln -sfn izdanja/v1.0.0 trenutno
install -d -m 0700 -o 10001 -g 10001 /var/backups/orkestrator
install -d -m 0700 -o root -g root /var/backups/orkestrator-van-servera
```

- `/var/backups/orkestrator` je upisiv iz kontejnera `app` (korisnik 10001), pa `odrzavanje.sh` njegovim imenima ne veruje:
  - brise i bira samo obicne fajlove oblika `dnevna-YYYYMMDD-HHMMSS.sqlite3` i `nedeljna-...`; simbolicke veze i ostala imena preskace;
  - kopiju za sifrovanje otvara kao korisnik 10001, bez ikakvih ovlascenja (`setpriv --reuid=10001 --regid=10001 --clear-groups --inh-caps=-all --bounding-set=-all --no-new-privs`), ne kao root, pa proverava da je otvoren bas fajl sa tim imenom (uredjaj i inode, bez pracenja veze), obican, neprazan i korisnika 10001. Inace staje sa greskom i nista ne sifruje.
- `/var/backups/orkestrator-van-servera` je van njega i samo root-ov. Ne sme biti unutar `KOPIJE_DIR`; skripta to proverava.

`DJANGO_SECRET_KEY`:
- Kopija kljuca se odmah upisuje u menadzer lozinki klijenta, van servera.
- Kljuc ostaje isti kroz sve verzije.
- **Gubitak ili promena kljuca** brise sve sesije: igraci gube partije u toku, a moderatori su odjavljeni. Ako je kljuc procurio, zamenu radi razvijalac (`SECRET_KEY_FALLBACKS`).
- Promena kljuca menja i partiju dnevnog izazova; radi se samo odmah posle ponoci (odeljak 10a).
- Vrednosti u `.env` se pisu bez navodnika i bez znaka `$`.

`DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS` (`https://<DOMEN>`) i `DJANGO_BAZA` ne upisuju se u `.env`. Compose ih izvodi iz `DOMEN`.

## 4. Prvo pokretanje

```
cd /opt/orkestrator/trenutno
docker compose config --quiet                            # bez ispisa = ispravno
docker compose build                                    # collectstatic se izvrsava ovde, u gradnji slike
docker compose run --rm app python manage.py migrate    # prazna baza + sifarnik nepodobnih imena (migracija 0002)
docker compose run --rm app python manage.py check --deploy --fail-level WARNING
                                                        # ocekivano: "System check identified no issues (2 silenced)."
docker compose up -d
docker compose ps                                       # app: "healthy", web: "Up"
docker compose exec web nginx -t                        # "syntax is ok" i "test is successful"
```

- `(2 silenced)` je namerno: `security.W005` (HSTS bez `includeSubDomains`) i `security.W021` (bez HSTS preload). Poddomeni domena klijenta nam nisu poznati, a `includeSubDomains` bi im nametnuo https na isto vreme kao glavnom domenu. Preload je trajan upis u pregledace. **Ni jedno ni drugo se ne ukljucuje** da bi upozorenje nestalo; broj razlicit od 2 ili bilo koje drugo upozorenje javlja se nama.
- `docker compose config` bez `--quiet` ispisuje tajni kljuc. Taj ispis ne ide u tiket ni na deljen ekran.
- `collectstatic` se ne pokrece rucno: staticki fajlovi su u slici, a Nginx ih servira direktno.
- Migracija se nikad ne izvrsava pri pokretanju kontejnera, nego samo kao poseban korak, kao gore.

Do koraka 5 Nginx radi sa **privremenim samopotpisanim sertifikatom**. `docker compose logs web` tada pise `tls: UPOZORENJE`.

## 5. Sertifikat (TLS)

**Izbor: Let's Encrypt preko certbot-a, metodom webroot.**
- Sertifikat je besplatan i vazi 90 dana.
- Obnova je automatska (cron, odeljak 8).
- Privatni kljuc ne napusta server.
- Ne radi stalno nijedan dodatni kontejner: certbot se pokrece samo na zahtev (`docker compose run --rm certbot`).
- Privremeni samopotpisani sertifikat dozvoljava da se sve proveri (odeljak 7) pre nego sto DNS pokaze na server.

Ako klijent vec ima sertifikat (npr. wildcard od svog CA), koristi se on; vidi kraj ovog odeljka.

**Javno pustanje** (DNS na server) ide tek posle **nase pisane potvrde** izvestaja iz odeljka 7a i odobrenja klijenta (go/no-go). Tek tada se:

```
cd /opt/orkestrator/trenutno
DOMEN=$(sed -n 's/^DOMEN=//p' .env); EMAIL=$(sed -n 's/^LETSENCRYPT_EMAIL=//p' .env)
getent ahosts "$DOMEN"                                   # adresa ovog servera
docker compose run --rm certbot certonly --webroot -w /var/www/certbot -d "$DOMEN" \
    --email "$EMAIL" --agree-tos --no-eff-email --dry-run     # ocekivano: "The dry run was successful."
docker compose run --rm certbot certonly --webroot -w /var/www/certbot -d "$DOMEN" \
    --email "$EMAIL" --agree-tos --no-eff-email               # "Successfully received certificate."
docker compose restart web
docker compose logs web | grep 'tls:'                   # "tls: sertifikat iz /etc/letsencrypt/live/<DOMEN>"
```

Obnovu radi `odrzavanje.sh sertifikat` svaki dan (odeljak 8). Certbot obnavlja tek kada do isteka ostane manje od 30 dana. `nadzor` javlja ako do isteka ostane manje od 14 dana.

**Sopstveni sertifikat klijenta.** Umesto certbot komandi:

```
# /root/tls/fullchain.pem (sertifikat + medjusertifikati) i /root/tls/privkey.pem
docker compose run --rm --no-deps -v /root/tls:/uvoz:ro --entrypoint sh certbot -c \
  'mkdir -p "/etc/letsencrypt/live/$0" && cp /uvoz/fullchain.pem /uvoz/privkey.pem "/etc/letsencrypt/live/$0/" && chmod 600 "/etc/letsencrypt/live/$0/privkey.pem"' "$DOMEN"
docker compose restart web
```

Uz sopstveni sertifikat cron red `sertifikat` se izostavlja. Novi sertifikat se uvozi istom komandom pre isteka.

## 6. Prvi glavni moderator

```
docker compose exec app python manage.py moderator_dodaj IME --glavni    # lozinka se unosi dvaput, ne vidi se
```

- Ime i pocetna lozinka idu vlasniku naloga sigurnim putem.
- Vlasnik se prijavljuje na `https://<DOMEN>/moderator/prijava/` i pri prvoj prijavi menja lozinku.
- Ostale moderatore dodaje glavni moderator u igri (`/moderator/nalozi/`).

## 7. Provera posle postavljanja (i posle svake isporuke)

```
cd /opt/orkestrator/trenutno
PROVERA_NESIGURNO=1 bash deploy/provera.sh "$DOMEN" <IP servera>   # pre DNS-a, sa privremenim sertifikatom
bash deploy/provera.sh "$DOMEN"                                    # posle DNS-a i sertifikata
```

Ocekivano je `PROVERA ZAVRSENA: ... palo 0`. Skripta proverava:
- http daje 301;
- `/zdravlje/` daje 200 i cita bazu, bez kolacica;
- HSTS;
- kolacici sa `Secure`;
- `GET /dnevni/` daje 200 (dnevni izazov);
- statika sa Nginx-a;
- potez preko https sa CSRF;
- ceo tok partije i deljeni link `https://`;
- 415 za multipart, 413 za telo od 32 KB;
- 429 na sedmu prijavu, sa nasom dvojezicnom stranom, `Retry-After` i istim HSTS-om kao `/zdravlje/`;
- zatvorenu vezu za nepoznat Host i SNI.

Ostavlja jednu probnu partiju, jednu zapocetu dnevnu partiju u istoj sesiji (bez upisa na listu dana) i jedan deljeni link. Posle nje prijava sa iste adrese ne prolazi oko jedan minut. Ponovno pokretanje tek posle jednog minuta.

Zatim rucno:
- Pre DNS-a: sa racunara koji u `hosts` ima `<IP servera> <DOMEN>`, uz prihvatanje privremenog sertifikata.
- Posle DNS-a: na telefonu.
- Proverava se:
  - cela partija, upis imena na rang listu i deljenje;
  - deljeni link otvoren na drugom uredjaju;
  - promena jezika;
  - prijava moderatora;
  - prijava imena sa rang liste i odluka moderatora na strani „Преглед“ (odeljak 10b).

## 7a. Proba pre javnog pustanja (pre DNS-a)

Radi se na serveru, posle odeljaka 1-4 i 6, dok DNS jos NE pokazuje na server. Nginx radi sa privremenim sertifikatom. Izlaz se salje nama. **DNS se menja tek posle nase pisane potvrde** i odobrenja klijenta.

**Proba opterecenja** (`deploy/proba-opterecenja.sh`, oko 7 minuta):
- Scenario iz plana 15.2: igraci igraju cele partije pri oko 50 zahteva u sekundi, 5 minuta. Partija je `GET /`, 8 poteza sa CSRF-om, `sacuvaj`, `podeli` i ponovo `GET /`; uz to `/zdravlje/` jednom u sekundi.
- **Produkciona baza se ne dira.**
  - Skripta podize odvojen compose projekat `orkestrator-proba`: ista slika, ali svoj prazan volumen `orkestrator-proba_baza`, svoja mreza i bez portova.
  - Opterecenje gadja njegov gunicorn direktno, pa se meri aplikacija i SQLite. Kroz Nginx bi svi zahtevi dolazili sa jedne adrese i dobili 429.
  - Na kraju, i posle neuspeha, proba se gasi, a njen volumen brise po tacnom imenu.
- Kroz produkcioni Nginx ide samo kratak nalet `GET /zdravlje/` (samo citanje, bez sesije). On potvrdjuje da ogranicenje brzine vraca 429.
- Ne pokrece se dok igraci igraju: zauzima isti procesor.

**Sve komande odjednom.** Izvestaj ide u jedan fajl. IPv4 i IPv6 adrese su u njemu maskirane, a tokeni deljenih linkova zamenjeni sa `/r/-`:

```
cd /opt/orkestrator/trenutno && DOMEN=$(sed -n 's/^DOMEN=//p' .env) && VERZIJA=$(sed -n 's/^VERZIJA=//p' .env)
IP=<javni IPv4 servera>
maskiraj() {
  sed -E 's/([0-9]{1,3}\.){3}[0-9]{1,3}/x.x.x.x/g
          s/([0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4}/ipv6/g
          s/[0-9A-Fa-f:]*::[0-9A-Fa-f:]*/ipv6/g
          s#/r/[A-Za-z0-9_-]{8,}#/r/-#g'
}
env_imena() { cut -d= -f1 | grep .; }      # samo imena promenljivih, nikad vrednosti
{
  echo "== 1. verzije i server"
  date -u; uname -sr; grep PRETTY_NAME /etc/os-release; nproc; free -m | sed -n 2p
  df -h / /var/lib/docker /var/backups/orkestrator
  docker version --format 'Docker {{.Server.Version}}'; docker compose version
  docker image ls --format '{{.Repository}}:{{.Tag}} {{.ID}} {{.CreatedAt}}' | grep '^orkestrator-'
  docker compose images
  echo "== 2. docker compose ps"; docker compose ps
  echo "== 3. check --deploy"; docker compose run --rm app python manage.py check --deploy --fail-level WARNING
  echo "== 4. nginx -t"; docker compose exec -T web nginx -t
  echo "== 5. provera.sh"; PROVERA_NESIGURNO=1 bash deploy/provera.sh "$DOMEN" "$IP"
  echo "== 6. proba opterecenja"; bash deploy/proba-opterecenja.sh
  echo "== 7. proba prijave: spora prijava + obicne"
  docker compose run --rm --no-deps -T app python deploy/proba-prijave.py --cilj web --host "$DOMEN" --nesigurno
  echo "== 8. kopija i proba povratka"; bash deploy/odrzavanje.sh kopija && bash deploy/odrzavanje.sh proba-povratka
  echo "== 9. slike i kontejneri: okruzenje (samo imena) i sadrzaj"
  for s in app web; do
    echo "-- slika orkestrator-$s:$VERZIJA, Config.Env"
    docker image inspect "orkestrator-$s:$VERZIJA" --format '{{range .Config.Env}}{{println .}}{{end}}' | env_imena
    echo "-- slika orkestrator-$s:$VERZIJA, baze, .env i testovi (ocekivano samo 'kraj pretrage')"
    docker run --rm --network none --user 0 --entrypoint sh "orkestrator-$s:$VERZIJA" -c \
      'find / -xdev \( -name "*.sqlite3*" -o -name "*.sqlite" -o -name "*.db" -o -name ".env" -o -name ".env.*" -o -path "*/igra/tests" \) -print 2>/dev/null | head -n 20; echo "kraj pretrage"'
  done
  echo "-- kontejner web, Config.Env"
  docker inspect "$(docker compose ps -q web)" --format '{{range .Config.Env}}{{println .}}{{end}}' | env_imena
  echo "== 10. kontejneri: korisnik, koren samo za citanje, port 8000, portovi domacina"
  docker compose exec -T app id
  for s in app web; do echo "-- $s:"; docker compose exec -T "$s" sh -c 'touch /proba-upisa 2>&1; echo "izlaz $?"'; done
  curl -sS -m 5 -o /dev/null "http://$IP:8000/"; echo "curl na $IP:8000, izlaz $?"
  ss -ltnH | awk '{ print $4 }' \
    | sed -E 's/^0\.0\.0\.0:/svi-ipv4:/; s/^\[::\]:/svi-ipv6:/; s/^\*:/svi-oba:/; s/^(127\.[0-9.]+|\[::1\])(%[A-Za-z0-9]+)?:/lokalno:/' \
    | sort -u
  echo "== 11. logovi bez tajni: broj redova sa /r/<token>, sessionid, csrftoken ili password"
  docker compose exec -T web sh -c "grep -ciE '/r/[^-]|sessionid|csrftoken|password' /var/log/nginx/pristup/pristup.log || true"
  docker compose logs --no-color app web | grep -ciE '/r/[^-]|sessionid|csrftoken|password' || true
  echo "== 12. log app, poslednjih 200 redova"; docker compose logs --no-color --tail 200 app
  echo "== 13. log web, poslednjih 200 redova"; docker compose logs --no-color --tail 200 web
} 2>&1 | maskiraj > /root/orkestrator-pre-pustanja.txt
grep -c 'DJANGO_SECRET_KEY\|BEGIN .*PRIVATE KEY' /root/orkestrator-pre-pustanja.txt   # mora biti 0
( kljuc=$(sed -n 's/^DJANGO_SECRET_KEY=//p' /opt/orkestrator/.env | tr -d '\r')
  [ -n "$kljuc" ] || { echo "kljuc nije procitan iz .env"; exit 1; }
  grep -cFf <(printf '%s\n' "$kljuc") /root/orkestrator-pre-pustanja.txt )             # mora biti 0
```

- Poslednji red trazi **vrednost** tajnog kljuca iz `.env`, ne njegovo ime. Vrednost se ne ispisuje i ne ide u argumente komande (`printf` je ugradjen u bash).
- Deo 7 trosi 4 od 6 prijava u minuti sa adrese kontejnera. Zato je posle probe opterecenja, vise minuta posle `provera.sh`.
- Deo 10 `touch` mora pasti sa `Read-only file system`. Port 8000 mora biti odbijen (izlaz 7) ili bez odgovora (izlaz 28).

**Prolaz** (svih trinaest, inace nema javnog pustanja):

| Deo izvestaja | Prolaz |
|---|---|
| 2. `docker compose ps` | `app` je `healthy`, `web` je `Up` |
| 3. `check --deploy` | `System check identified no issues (2 silenced)` (odeljak 4) |
| 4. `nginx -t` | `syntax is ok` i `test is successful` |
| 5. `provera.sh` | `palo 0` |
| 6. proba opterecenja, deo `igra` | sve `PROLAZ`: ostvareno bar 45 z/s; p95 ispod 300 ms; 0 odgovora 5xx; 0 odgovora 429; svi odgovori 200; svaki link `https://<DOMEN>/r/` |
| 6. log probe i Nginx | `database is locked: 0`, bez ERROR/Traceback redova; `log bez tokena, sessionid i password: PROLAZ`; nalet kroz Nginx ima i 200 i 429, bez 5xx; na kraju `PROBA PROSLA` |
| 7. proba prijave | sve tri obicne prijave `403` (nijedna `429`) dok spora drzi vezu; `PROBA PRIJAVE PROSLA` |
| 8. kopija i proba povratka | `integrity_check: ok`, `KORAK KRAJ: uspesno` dvaput |
| 9. slike | `Config.Env` slika i kontejnera `web` bez `DJANGO_SECRET_KEY`; pretraga obe slike ispisuje samo `kraj pretrage` |
| 10. korisnik i koren | `uid=10001(app) gid=10001(app)`; oba `touch` sa `Read-only file system` i `izlaz 1` |
| 10. port 8000 | `izlaz 7` ili `izlaz 28`, nikad `izlaz 0` |
| 10. `ss` | slusaju samo `svi-ipv4:80`, `svi-ipv4:443`, port 22 i `lokalno:*`; nema `svi-ipv6:80/443` ni `svi-oba:80/443` ni drugih portova |
| 11. logovi | oba broja `0` |

**Rucno, sa racunara (ne sa servera)**, uz rucnu proveru iz odeljka 7:
- **Adresa igraca u logu (IPv4).** Na racunaru `curl -4 -s https://ifconfig.me` daje njegovu javnu adresu `<A>`. Posle rucne provere, na serveru: `docker compose exec -T web grep -c '^<A> ' /var/log/nginx/pristup/pristup.log`. Mora biti vece od 0. Ako je 0, a u logu su adrese `172.x.x.x`, ogranicenje brzine broji mrezni prolaz Docker-a umesto igraca, i to se javlja nama.
- **IPv6 se ne prima.** Samo ako server ima IPv6 adresu `<IPv6>`: sa racunara koji ima IPv6, `curl -6 -k -m 5 "https://[<IPv6>]/zdravlje/"; echo "izlaz $?"`. Mora biti izlaz 7 (odbijeno) ili 28. Izlaz 0 znaci da Nginx prima IPv6, i to se javlja nama.
- **Spolja na port 8000:** `curl -m 5 http://<IP servera>:8000/; echo "izlaz $?"` mora dati 7 ili 28.

**Preporuka (nije uslov prolaza):** skener ranjivosti slika, npr. `trivy image orkestrator-app:$VERZIJA` i `trivy image orkestrator-web:$VERZIJA`, ili `docker scout cves`. Nalazi `CRITICAL` ili `HIGH` sa dostupnom ispravkom se salju nama.

**Sta nam se salje** (sigurnim putem, ne javnim tiketom):
1. fajl `/root/orkestrator-pre-pustanja.txt`, ceo;
2. ishodi oba `grep -c` iz poslednja dva reda (oba moraju biti `0`);
3. ishod rucne provere iz odeljka 7 i rucnih proba iznad, kratko: sta je provereno i sta nije radilo.

**Nikad se ne salju:** `.env`, ispis `docker compose config`, kopije baze i kljucevi.

**Posle nase potvrde i odobrenja klijenta:**
1. DNS na server.
2. Sertifikat (odeljak 5).
3. `bash deploy/provera.sh "$DOMEN"` bez `PROVERA_NESIGURNO`.
4. Rucna provera na telefonu.

Taj kratki ispis provere salje se nama jos jednom.

**Tragovi u produkcionoj bazi.**
- `provera.sh` ostavlja jednu sesiju i jedan deljeni link probne partije, a na rang listu ne upisuje nista.
- Link istice za 30 dana. Moderator ga moze obrisati ranije.
- Proba opterecenja ne ostavlja nista.

## 8. Periodicni zadaci

```
cat >/etc/cron.d/orkestrator <<'CRON'
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
# MAILTO=admin@klijent    # ako server salje postu, svaki ispis zadatka stize na ovu adresu
5 0 * * *     root bash /opt/orkestrator/trenutno/deploy/odrzavanje.sh logovi     >>/var/log/orkestrator.log 2>&1
30 3 * * *    root bash /opt/orkestrator/trenutno/deploy/odrzavanje.sh kopija     >>/var/log/orkestrator.log 2>&1
10 4 * * *    root bash /opt/orkestrator/trenutno/deploy/odrzavanje.sh ciscenje   >>/var/log/orkestrator.log 2>&1
40 4 * * 0    root bash /opt/orkestrator/trenutno/deploy/odrzavanje.sh nedeljno   >>/var/log/orkestrator.log 2>&1
15 5 * * *    root bash /opt/orkestrator/trenutno/deploy/odrzavanje.sh sertifikat >>/var/log/orkestrator.log 2>&1
*/15 * * * *  root bash /opt/orkestrator/trenutno/deploy/odrzavanje.sh nadzor     >>/var/log/orkestrator.log 2>&1
CRON
cat >/etc/logrotate.d/orkestrator <<'LR'
/var/log/orkestrator.log {
    weekly
    rotate 8
    compress
    missingok
    notifempty
}
LR
```

| Zadatak | Sta radi |
|---|---|
| `logovi` | rotira pristupni log Nginx-a; cuva se 14 dana, IP adrese ne duze |
| `kopija` | kopija baze (`baza_kopija`: VACUUM INTO pa `integrity_check`); ostaje 7 dnevnih |
| `ciscenje` | `clearsessions` i `deljeni_ocisti`; bez njih tabela sesija raste 10-30 MB dnevno |
| `nedeljno` | `dnevnik_ocisti` (365 dana); nedeljna kopija (4); sifrovana kopija za van servera (4) |
| `sertifikat` | `certbot renew` i `nginx -s reload` |
| `nadzor` | disk ispod 80%, `app` zdrav, sertifikat nije samopotpisan i vazi jos 14 dana, kopija mladja od 26 sati |

Odmah posle upisa svaki zadatak se jednom pokrece rucno. Ishod mora biti `KORAK KRAJ: uspesno`:

```
cd /opt/orkestrator/trenutno
for z in kopija ciscenje logovi nadzor; do bash deploy/odrzavanje.sh $z; done
```

`nedeljno` trazi gpg kljuc (odeljak 9), a `sertifikat` trazi sertifikat (odeljak 5).

Provera da su se zadaci izvrsili (sledeceg dana):

```
grep -E 'KRAJ|NEUSPEH|NALAZ' /var/log/orkestrator.log | tail -n 20
journalctl -t orkestrator --since yesterday -p warning   # prazno = nema neuspeha ni nalaza
ls -lt /var/backups/orkestrator | head
```

Svaki neuspeh ima oznaku koraka (`KORAK 2/5: ...`), pa se vidi gde je stao.

## 9. Kopije baze i povratak

Kopija sadrzi sesije (seme partija u toku) i heseve lozinki moderatora.
- **Kopije na serveru NISU sifrovane.** Stite ih samo prava pristupa: direktorijum `0700`, fajlovi `0600`. Root na serveru, i svako ko dobije kontrolu nad kontejnerom `app`, moze da ih procita.
- Van servera ide samo sifrovana kopija.

| Fajl | Koliko |
|---|---|
| `/var/backups/orkestrator/dnevna-<vreme>.sqlite3` | 7 |
| `/var/backups/orkestrator/nedeljna-<vreme>.sqlite3` (tvrda veza na dnevnu, bez duplog prostora) | 4 |
| `/var/backups/orkestrator-van-servera/nedeljna-<vreme>.sqlite3.gpg` | 4 |

Direktorijum sifrovanih kopija je van `KOPIJE_DIR` i samo root-ov: kontejner u njega ne moze da upise ni da podmetne vezu. Druga putanja se zadaje u `.env` kao `KOPIJE_VAN_SERVERA_DIR` (nikad unutar `KOPIJE_DIR`).

**Sifrovanje.**
- Klijent pravi par kljuceva NA SVOM racunaru: `gpg --full-generate-key`, pa `gpg --export --armor <ID> > kopije.asc`. Na svom racunaru zapisuje i pun otisak kljuca: `gpg --fingerprint <ID>` (40 heksa znakova).
- Na server ide samo javni kljuc:
  ```
  gpg --show-keys --with-fingerprint kopije.asc      # otisak se uporedjuje sa zapisanim, znak po znak
  gpg --import kopije.asc
  ```
- U `.env` se upisuje **pun otisak**, bez razmaka: `KOPIJA_GPG_PRIMALAC=0123456789ABCDEF0123456789ABCDEF01234567`. ID ni adresa se ne prihvataju: drugi kljuc sa istom adresom bi prosao. `odrzavanje.sh nedeljno` pada ako vrednost nije otisak.
- Privatni kljuc se cuva na dva mesta van servera. Bez njega se kopija ne moze procitati.

**Van servera.** Alat klijenta (rsync, rclone ili servis za kopije) nedeljom posle 04:40 prenosi `/var/backups/orkestrator-van-servera/`. Primer:

```
rsync -a /var/backups/orkestrator-van-servera/ kopije@drugi-server:orkestrator/
```

**Mesecna proba povratka** (ne dira radnu bazu):

```
cd /opt/orkestrator/trenutno
bash deploy/odrzavanje.sh proba-povratka                       # najnovija dnevna; ili ime fajla kao argument
```

- Ocekivano je `integrity_check: ok` i `System check identified no issues`.
- `migrate --check` mora proci bez izlaza 1.
- Brojevi redova kopije i radne baze treba da budu bliski: razlikuju se samo upisi posle kopije.
- Jednom u tromesecju isto se radi sa kopijom van servera:
  1. Na racunaru klijenta se kopija desifruje i salje **direktno u odrediste**. Na serveru nastaje sa pravima 0600 (umask 077) i vlasnikom 10001, a desifrovana kopija nigde ne ostaje kao privremeni fajl:
     ```
     gpg -d <fajl>.gpg | ssh root@<server> 'umask 077 && cat > /var/backups/orkestrator/proba.sqlite3 && chown 10001:10001 /var/backups/orkestrator/proba.sqlite3'
     ```
  2. Na serveru:
     ```
     ls -l /var/backups/orkestrator/proba.sqlite3                  # -rw------- 10001 10001
     cd /opt/orkestrator/trenutno && bash deploy/odrzavanje.sh proba-povratka proba.sqlite3
     ```
  3. **Desifrovana kopija se brise odmah posle probe** (sadrzi sesije i heseve lozinki bez sifrovanja):
     - na serveru: `shred -u /var/backups/orkestrator/proba.sqlite3`;
     - na racunaru klijenta: ako je ipak desifrovana u fajl (npr. `gpg -d ... > proba.sqlite3`), i taj fajl: `shred -u proba.sqlite3`, ili brisanje pa praznjenje korpe.

**Povratak kopije** (gube se upisi posle kopije):

```
cd /opt/orkestrator/trenutno
K=dnevna-YYYYMMDD-HHMMSS.sqlite3                                # izabrana kopija
bash deploy/odrzavanje.sh proba-povratka "$K"                   # mora zavrsiti "KORAK KRAJ: uspesno"
docker compose stop web app                                     # prekid pocinje
docker compose run --rm app python manage.py baza_kopija "/kopije/pre-povratka-$(date +%Y%m%d-%H%M%S).sqlite3"
docker compose run --rm app sh -c 'rm -f /data/db.sqlite3-wal /data/db.sqlite3-shm && cp "/kopije/$0" /data/db.sqlite3' "$K"
docker compose run --rm app python manage.py migrate --check    # izlaz 1: kopija je starija od koda, vidi odeljak 10
docker compose up -d --no-build
bash deploy/provera.sh "$DOMEN"
```

- Brisanje `-wal` i `-shm` je obavezno: stari dnevnik bi se primenio na vracenu bazu.
- `pre-povratka-*` se ne brise automatski. Brise se rucno kada je povratak potvrdjen.

## 10. Nova verzija i povratak na prethodnu

Nova verzija donosi kratak prekid, 1-2 minuta. Najavljuje se i radi u satu najmanjeg saobracaja.

```
cd /opt/orkestrator
sha256sum -c orkestrator-v1.1.0.zip.sha256 && unzip -q orkestrator-v1.1.0.zip -d izdanja
ln -s /opt/orkestrator/.env izdanja/v1.1.0/.env
nano .env                                                       # VERZIJA=v1.1.0 (zapisati staru)
ln -sfn izdanja/v1.1.0 trenutno && cd /opt/orkestrator/trenutno
docker compose build                                            # stara verzija i dalje radi
docker compose stop app                                         # prekid pocinje
docker compose run --rm app python manage.py baza_kopija "/kopije/pre-v1.1.0-$(date +%Y%m%d-%H%M%S).sqlite3"
docker compose run --rm app python manage.py migrate            # zapisati: "No migrations to apply" ili "Applying ..."
docker compose up -d --no-build
bash deploy/provera.sh "$DOMEN"
```

**Povratak na prethodnu verziju:**

```
docker image ls orkestrator-app                                 # slika stare oznake MORA postojati
cd /opt/orkestrator && nano .env                                # VERZIJA=<stara>
ln -sfn izdanja/<stara> trenutno && cd /opt/orkestrator/trenutno
docker compose up -d --no-build
bash deploy/provera.sh "$DOMEN"
```

- Ako je `migrate` u isporuci ispisao `Applying ...`, pre `up -d` se vraca kopija `pre-<nova verzija>-*` po odeljku 9. Upisi posle isporuke se gube.
- `--no-build` je obavezan: bez njega compose bi pod starom oznakom izgradio TEKUCI kod.
- Cuvaju se bar dva poslednja izdanja i njihove slike.

### 10a. Verzija sa dnevnim izazovom (migracija 0013)

Prva verzija sa dnevnim izazovom (`/dnevni/`) donosi migraciju `igra.0013_rezultat_dan`: novo polje `dan` u tabeli rezultata i jedan indeks. Postojeci rezultati dobijaju prazno `dan` i ostaju na glavnoj listi. Isporuka ide po odeljku 10, uz ovo:

- **Isporuku odobrava klijent.** Migracija na produkcionoj bazi je tacka bez povratka bez kopije.
- `migrate` se pokrece **samo ako je `baza_kopija` uspela**, zato su vezani sa `&&`:

```
docker compose stop app                                         # prekid pocinje
K="pre-<nova verzija>-$(date +%Y%m%d-%H%M%S).sqlite3"
docker compose run --rm app python manage.py baza_kopija "/kopije/$K" \
  && docker compose run --rm app python manage.py migrate      # ocekivano: "Applying igra.0013_rezultat_dan... OK"
ls -l "/var/backups/orkestrator/$K"                             # kopija postoji i nije prazna; ime se zapisuje
docker compose up -d --no-build
docker compose exec web nginx -t                                # nove lokacije /dnevni/ u Nginx-u
bash deploy/provera.sh "$DOMEN"                                 # palo 0, ukljucujuci "GET /dnevni/ daje 200"
```

- Ako `baza_kopija` ne zavrsi uspesno, `migrate` se ne pokrece i dalje se ne ide. Ili se uzrok otkloni (najcesce mesto na disku) pa se kopija ponovi, ili se vraca prethodna verzija po odeljku 10; baza tada nije menjana, pa se kopija ne vraca. Ishod se javlja nama.
- **Povratak na prethodnu verziju brise dnevne redove.** Jedini povratak je kopija `pre-<nova verzija>-*` po odeljku 9: gube se svi rezultati dnevnog izazova i svi ostali upisi posle isporuke. `migrate igra 0012` (migracija unazad) se **ne koristi**: brise kolonu `dan`, a dnevni redovi bi ostali i presli na glavnu listu.

**Partija dana zavisi od `DJANGO_SECRET_KEY`.** Seme partije dana se racuna iz datuma i tajnog kljuca. Promena kljuca usred dana daje dve razlicite partije istog dana: igraci od pre i posle promene ne igraju istu partiju, a lista dana ih poredi. Zato:
- zamena kljuca (odeljak 3, samo razvijalac) radi se **odmah posle ponoci** (Europe/Belgrade), pre nego sto iko pocne partiju novog dana;
- `SECRET_KEY_FALLBACKS` cuva sesije, ali NE cuva partiju dana: seme se uvek racuna iz novog kljuca.

### 10b. Verzija sa prijavom imena (migracija 0014)

Prva verzija u kojoj igrac prijavljuje neprikladno ime sa rang liste (`/prijavi/`), a moderator na strani „Преглед“ odlucuje, donosi migraciju `igra.0014_prijava_imena`:

- nova prazna tabela prijava (`igra_prijavaimena`);
- tabela dnevnika (`igra_zapisdnevnika`) se **prepravlja**, da primi novu radnju „одбачена пријава имена“. Zapisi se kopiraju netaknuti, a ista migracija ponovo pravi oba okidaca koji cuvaju dnevnik od izmene.

Isporuka ide po odeljku 10, uz ovo:

- **Isporuku odobrava klijent.** Migracija na produkcionoj bazi je tacka bez povratka bez kopije.
- `migrate` se pokrece **samo ako je `baza_kopija` uspela** (vezani sa `&&`), a broj zapisa dnevnika i okidaci se proveravaju pre `up -d`:

```
docker compose stop app                                         # prekid pocinje
docker compose run --rm app python manage.py shell -v 0 -c "from igra.models import ZapisDnevnika; print(ZapisDnevnika.objects.count())"   # zapisati broj
K="pre-<nova verzija>-$(date +%Y%m%d-%H%M%S).sqlite3"
docker compose run --rm app python manage.py baza_kopija "/kopije/$K" \
  && docker compose run --rm app python manage.py migrate      # ocekivano: "Applying igra.0014_prijava_imena... OK"
ls -l "/var/backups/orkestrator/$K"                             # kopija postoji i nije prazna; ime se zapisuje
docker compose run --rm app python manage.py shell -v 0 -c "from igra.models import ZapisDnevnika; print(ZapisDnevnika.objects.count())"   # isti broj kao pre
docker compose run --rm app python manage.py shell -v 0 -c "from django.db import connection; k = connection.cursor(); k.execute(\"SELECT name FROM sqlite_master WHERE type = 'trigger' ORDER BY name\"); print([r[0] for r in k.fetchall()])"
                                                                # ocekivano: ['igra_zapis_bez_izmene', 'igra_zapis_bez_zamene']
docker compose up -d --no-build
docker compose exec web nginx -t                                # /prijavi/ u lokaciji sa /sacuvaj/ i /podeli/
bash deploy/provera.sh "$DOMEN"                                 # palo 0
```

- Ako se broj zapisa dnevnika razlikuje ili nedostaje bilo koji od dva okidaca: `up -d` se **ne pokrece**, vraca se kopija `pre-<nova verzija>-*` po odeljku 9 i prethodna verzija po odeljku 10. Ishod se javlja nama.
- Ako `baza_kopija` ne zavrsi uspesno, vazi isto sto i u odeljku 10a: `migrate` se ne pokrece, baza nije menjana.
- **Povratak na prethodnu verziju brise prijave i odluke o njima.** Jedini povratak je kopija `pre-<nova verzija>-*` po odeljku 9. `migrate igra 0013` (migracija unazad) se **ne koristi**: brise tabelu prijava i sve zapise dnevnika „одбачена пријава имена“.
- Rucna provera posle isporuke: na rang listi „Пријави неприкладно име“, pa prijavljen moderator na strani „Преглед“ vidi ime u odeljku „Пријављена имена“ i bira „Остави“ ili „Обриши“; odluka je u dnevniku.

Oznaka reda kojom pregledac prijavljuje ime zavisi od `DJANGO_SECRET_KEY`. Posle zamene kljuca strana ucitana pre zamene dobija poruku da rezultat vise nije na listi, dok je igrac ne osvezi; prijave i odluke ostaju.

## 11. HSTS

Prvih 14 dana `DJANGO_HSTS_SEKUNDI=3600` (sat vremena). Posle 14 dana rada bez problema sa sertifikatom, **i tek uz odobrenje klijenta**.

Pre podizanja mora proci proba obnove sertifikata. Posle godine HSTS-a istekao sertifikat zakljucava igrace napolje, pa obnova mora raditi pre izmene:

```
cd /opt/orkestrator/trenutno
docker compose run --rm certbot renew --dry-run                 # "Congratulations, all simulated renewals succeeded"
grep -E 'sertifikat KORAK KRAJ|NEUSPEH: odrzavanje sertifikat' /var/log/orkestrator.log | tail -n 3   # poslednja tri: KRAJ, bez NEUSPEH
```

Uz sopstveni sertifikat klijenta (odeljak 5) umesto `renew --dry-run` se proverava da do isteka ima bar 30 dana i da je zakazano sledece uvozenje: `docker compose exec -T web openssl x509 -enddate -noout -in /etc/nginx/tls/fullchain.pem`.

Tek onda:

```
cd /opt/orkestrator && nano .env                                # DJANGO_HSTS_SEKUNDI=31536000 (samo cifre, bez razmaka; 0 i vodeca nula se ne prihvataju)
cd trenutno && docker compose up -d --no-build
curl -sI "https://$DOMEN/zdravlje/" | grep -i strict-transport-security    # max-age=31536000 (Django)
docker compose exec -T web grep -o 'Strict-Transport-Security "max-age=[0-9]*' /etc/nginx/nginx.conf
                                                                           # Strict-Transport-Security "max-age=31536000 (Nginx, strana 429)
bash deploy/provera.sh "$DOMEN"                                            # palo 0; poredi HSTS strane 429 i /zdravlje/
```

- Ista vrednost ide i u Nginx (samo za stranu 429 prijave, koju Django ne vidi). `up -d` zato ponovo pravi i `app` i `web`.
- Neispravna vrednost (razmak, navodnik, slovo, 0, vodeca nula kao 03600) zaustavlja oba kontejnera. `app` javlja `ImproperlyConfigured: DJANGO_HSTS_SEKUNDI ...`, a `web` (`docker compose logs web`) javlja `provera okruzenja: GRESKA: ...`. Isto vazi za `DOMEN` u `web`.

**Zasto se ne vraca.**
- Pregledac koji je video zaglavlje godinu dana odbija http za domen.
- Takav pregledac ne dozvoljava ni da se preskoci greska sertifikata.
- Smanjenje vrednosti stize tek pri sledecoj uspesnoj https poseti. Ako sertifikat istekne, igraci ne mogu da udju dok se ne popravi.
- Ne koriste se `includeSubDomains` ni preload.

## 12. Pracenje i logovi

- **Spoljna provera** (servis koji klijent bira): `https://<DOMEN>/zdravlje/` na 1-5 minuta. Ocekuje se 200 i `"ok": true`. Nikad `/`, jer svaki takav poziv pravi sesiju u bazi.
- **Uzbuna** (odluka klijenta ko je dobija):
  - neuspeh periodicnog zadatka;
  - `NALAZ` iz `nadzor` (disk 80%, `app` nije zdrav, sertifikat istice za 14 dana ili je samopotpisan, nema sveze kopije);
  - pad spoljne provere.
  - Izvor je `journalctl -t orkestrator -p warning` ili `MAILTO` u cron-u.
- **Logovi:**

| Sta | Komanda | Cuva se |
|---|---|---|
| greske aplikacije i gunicorn-a (bez tokena, lozinke i tela zahteva; isti filter za oba) | `docker compose logs --since 1h app` | 5 x 10 MB |
| greske Nginx-a | `docker compose logs --since 1h web` | 5 x 10 MB |
| pristupni log (token maskiran kao `/r/-/`) | `docker compose exec web tail -n 50 /var/log/nginx/pristup/pristup.log` | 14 dana |
| periodicni zadaci | `/var/log/orkestrator.log`, `journalctl -t orkestrator` | 8 nedelja |

- Odbijeni zahtevi danas: `docker compose exec web grep -c '" 429 ' /var/log/nginx/pristup/pristup.log`.
- Broj sesija u bazi:

```
docker compose exec -T app python manage.py shell -c "from django.contrib.sessions.models import Session; print(Session.objects.count())"
```

Ocekuje se do oko 140.000. Stalan rast se javlja razvijaocu. Jedna adresa moze da napravi najvise oko 86.400 novih sesija dnevno (`GET /` i `POST /nova/`, po 30 u minuti); `clearsessions` ih brise tek kad isteknu, posle 14 dana.

## 13. Posebni slucajevi

**CDN ili balanser ispred servera.** Bez ovoga ogranicenje brzine broji adresu CDN-a, pa svi igraci dele isti brojac i dobijaju 429.
- U `deploy/nginx.conf` se otkljucavaju redovi `set_real_ip_from` (opsezi koje objavljuje dobavljac, nikad `0.0.0.0/0`) i `real_ip_header`. Zatim:

```
docker compose build web && docker compose up -d --no-build web
```

- CDN mora da prosledjuje `Host` i da do servera ide preko https.
- Izmena se javlja razvijaocu, da udje u sledecu verziju.

**IPv6 (kasniji korak, ne u verziji 1).** Verzija 1 objavljuje 80 i 443 samo na IPv4 (`0.0.0.0` u `compose.yaml`), a DNS ima samo zapis A.
- Zasto: bez IPv6 u Docker mrezi IPv6 veza prolazi kroz `docker-proxy`, pa Nginx vidi adresu mreznog prolaza, ne igraca. Svi IPv6 igraci bi tada delili isti brojac ogranicenja brzine i zajedno dobijali 429.
- Uvodi ga razvijalac, kao novu verziju:
  1. `enable_ipv6` i IPv6 podmreza za compose mrezu (i `ip6tables` u Docker daemon-u), da Nginx vidi pravu IPv6 adresu;
  2. kljuc ogranicenja brzine po mrezi `/64` za IPv6 (jedan korisnik obicno ima celu `/64`), a ne po adresi;
  3. objava portova i na `[::]`, provera iz odeljka 7a sa IPv6 klijenta (`$remote_addr` u logu je adresa klijenta);
  4. tek onda zapis AAAA.
- Administrator do tada **ne dodaje zapis AAAA** i ne menja `ports:`.

**Moderator je blokiran.**
- Posle 5 neuspesnih prijava za isto ime blokada traje 15 minuta, zajednicka svim procesima.
- Nginx dodatno pusta 6 prijava u minuti po adresi (sedma dobija 429 sa nasom stranom „Previse pokusaja prijave“) i najvise 3 istovremene prijave po adresi. Na celom sajtu prolaze 2 prijave u sekundi; visak ceka do 2,5 s, a tek preko toga dobija 429.
- Otkljucavanje je cekanje.
- Zaboravljenu lozinku postavlja glavni moderator u igri (`/moderator/nalozi/`) ili:

```
docker compose exec app python manage.py moderator_lozinka IME
```

**Kompromitovan nalog moderatora:**

```
docker compose exec app python manage.py moderator_deaktiviraj IME     # nalog odmah prestaje da radi
docker compose exec app python manage.py moderatori                    # pregled naloga i uloga
```

Zatim se u `/moderator/dnevnik/` pregleda sta je nalog obrisao. Ako je lozinka koriscena i drugde, menja se i tamo.

## 14. Sta se nikad ne radi

- **Kopija baze kopiranjem fajla dok aplikacija radi** (`cp`, `docker cp`, `rsync` volumena). Bez `-wal` dnevnika takva kopija nije dosledna. Kopija ide samo kroz `baza_kopija` (`odrzavanje.sh kopija`), koja radi `VACUUM INTO` i proverava rezultat.
- **Gubitak ili promena `DJANGO_SECRET_KEY`.** Brise sve sesije i partije u toku. Kljuc ima kopiju van servera.
- `docker compose down -v`, `docker volume rm` / `prune`, `docker system prune --volumes`: brisu bazu i sertifikat.
- `docker image prune -a`: brise slike prethodne verzije, pa povratak (odeljak 10) nije moguc.
- Objavljivanje porta 8000 ili `ports:` za `app`.
- `migrate` bez kopije neposredno pre nje; `migrate` koji nije vezan sa `&&` za uspelu `baza_kopija` (odeljak 10a).
- Migracija unazad (`migrate igra 0012`) posle verzije sa dnevnim izazovom: povratak je samo kopija `pre-*` (odeljak 10a).
- Migracija unazad (`migrate igra 0013`) posle verzije sa prijavom imena: brise prijave i zapise dnevnika o odbacenim prijavama; povratak je samo kopija `pre-*` (odeljak 10b).
- Promena `DJANGO_SECRET_KEY` usred dana: dve razlicite partije dnevnog izazova istog dana.
- `docker compose up` pri povratku bez `--no-build`.
- `DJANGO_HSTS_SEKUNDI=31536000` pre odobrenja klijenta; HSTS preload.
- Zdravstvena provera na `/`.
- Proba opterecenja na bilo koji nacin osim `deploy/proba-opterecenja.sh`, ili dok igraci igraju. Rucni `deploy/opterecenje.py --nacin igra` prema produkcionom `app` puni pravu bazu sesijama i rang listu probnim imenima.
- `$` ili navodnici u `.env`; ispis `docker compose config` bez `--quiet` u tiket.

## 15. Javna rang lista za partnere

Adresa: `https://orkestrator.example/api/rang-lista/`. Bez kljuca i bez naloga; metode GET i HEAD (ostale daju 405).

```json
{"verzija": 1,
 "glavna": [{"mesto": 1, "ime": "Pera", "poeni": 87, "ocena": "odlican", "datum": "2026-11-12", "staro_bodovanje": false}],
 "danas": {"dan": "2026-11-12", "redovi": [ ...isti oblik reda... ]}}
```

- `glavna`: 10 najboljih rezultata obicne igre; `danas.redovi`: 10 najboljih dnevnog izazova za `danas.dan` (po Europe/Belgrade; posle ponoci je lista prazna). Vise poena iznad, kod jednakih ranije sacuvan iznad.
- `datum` je ISO (`GGGG-MM-DD`) i ne zavisi od jezika. `staro_bodovanje` je `true` za rezultat po ranijim pravilima bodovanja (pre 2026-11-11).
- `ime` je tekst koji je igrac uneo, onako kako je sacuvan (JSON ga escape-uje); partner je odgovoran za bezbedan prikaz.
- `ocena` je kljuc, ne prevedeni tekst:

| Kljuc | Poeni | Srpski | English |
|---|---|---|---|
| `odlican` | 85 i vise | одличан оркестратор | excellent orchestrator |
| `solidan` | 65 do 84 | солидан | solid |
| `skup` | 40 do 64 | скуп учитељ | costly lesson |
| `pozar` | ispod 40 | пожар | disaster |

- Osvezavanje: odgovor se kesira 60 s (`Cache-Control: public, max-age=60`), pa nema smisla pitati cesce. Rezultat koji moderator obrise nestaje sa ove adrese najkasnije posle 60 s.
- Ogranicenje brzine: oko 1 zahtev u sekundi po IP adresi, uz nalet do 10; visak dobija `429 Too Many Requests`. Na 429 sacekati i ponoviti.
- `Access-Control-Allow-Origin: *`: moze se citati i iz pregledaca. Odgovor ne postavlja kolacice.
- Telo nikad ne nosi identifikator, oznaku reda, partiju, link za deljenje ni podatke o prijavama.
