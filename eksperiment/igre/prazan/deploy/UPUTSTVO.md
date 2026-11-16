# Orkestrator: postavljanje na server

Uputstvo za administratora koji postavlja igru na **https://orkestrator.example**. Komande su za
Ubuntu 24.04 LTS i pokrecu se kao korisnik sa `sudo`. Ako je domen drugaciji, zameni
`orkestrator.example` svuda: u ovom uputstvu, u `deploy/nginx/orkestrator.conf` i u
`ORKESTRATOR_DOMEN`.

## Kako je sastavljeno

```
igrac --HTTPS--> nginx :443 --unix socket--> gunicorn (3 procesa) --> Django --> SQLite datoteka
                  |
                  +-- /static/ sluzi sam, iz /srv/orkestrator/static
```

| Sta | Gde |
|---|---|
| kod | `/srv/orkestrator/app` (vlasnik root, servis ga samo cita) |
| Python okruzenje | `/srv/orkestrator/venv` |
| staticke datoteke | `/srv/orkestrator/static` |
| baza | `/var/lib/orkestrator/db.sqlite3` (jedina datoteka koju servis menja) |
| rezervne kopije | `/var/backups/orkestrator` (svake noci, cuva se poslednjih 14) |
| tajna podesavanja | `/etc/orkestrator/orkestrator.env` |
| dnevnik aplikacije | `journalctl -u orkestrator` |
| dnevnik pristupa | `/var/log/nginx/access.log` |

## 1. Server

- Ubuntu 24.04 LTS ili Debian 13. Potreban je **Python 3.12 ili noviji** (Django 6), pa Debian 12 ne odgovara.
- 1 procesor i 1 GB RAM su dovoljni; 2 procesora i 2 GB daju rezervu. Disk: 10 GB.
- DNS: zapis A (i AAAA, ako server ima IPv6) za `orkestrator.example` pokazuje na server.
- Spolja otvoreni samo portovi 22, 80 i 443:

```sh
sudo apt update
sudo apt install -y python3 python3-venv nginx certbot sqlite3 rsync
sudo ufw allow OpenSSH && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp && sudo ufw enable
```

## 2. Korisnik i folderi

Servis radi kao poseban korisnik `orkestrator`, bez lozinke i bez prijave. Nginx (korisnik `www-data`)
dobija pristup socketu i statickim datotekama kroz grupu `orkestrator`.

```sh
sudo adduser --system --group --home /srv/orkestrator orkestrator
sudo usermod -aG orkestrator www-data
sudo install -d -o orkestrator -g orkestrator -m 750 /var/lib/orkestrator /var/backups/orkestrator
sudo install -d -o orkestrator -g orkestrator -m 755 /srv/orkestrator/static
sudo install -d -o root -g orkestrator -m 750 /srv/orkestrator/app /etc/orkestrator
```

## 3. Kod i Python paketi

Kopiraj ceo folder projekta na server (npr. u `~/orkestrator`), pa ga prebaci na mesto. Lokalna
baza i testne datoteke se ne prenose: server pocinje sa praznom bazom.

```sh
sudo rsync -a --delete \
  --exclude 'db.sqlite3*' --exclude 'test_db.sqlite3*' --exclude '__pycache__' \
  ~/orkestrator/ /srv/orkestrator/app/
sudo chown -R root:orkestrator /srv/orkestrator/app
sudo chmod -R u=rwX,g=rX,o= /srv/orkestrator/app
sudo chmod 750 /srv/orkestrator/app/deploy/manage.sh

sudo python3 -m venv /srv/orkestrator/venv
sudo /srv/orkestrator/venv/bin/pip install -r /srv/orkestrator/app/requirements.txt
sudo /srv/orkestrator/venv/bin/python -m compileall -q /srv/orkestrator/app
```

## 4. Tajna podesavanja

```sh
sudo install -o root -g orkestrator -m 640 /srv/orkestrator/app/deploy/orkestrator.env.primer /etc/orkestrator/orkestrator.env
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
sudo nano /etc/orkestrator/orkestrator.env
```

Odstampani niz upisi posle `ORKESTRATOR_SECRET_KEY=`. Kljuc se ne salje nikome i ne cuva se u kodu.
Bez njega, ili sa prekratkim kljucem, server namerno ne krece.

## 5. Baza, staticke datoteke i prvi moderator

Sve komande aplikacije idu kroz `deploy/manage.sh`, koji ucitava ista podesavanja kao servis:

```sh
M="sudo -u orkestrator /srv/orkestrator/app/deploy/manage.sh"
$M migrate
$M createcachetable
$M collectstatic --noinput
$M check --deploy
$M moderator <ime>
```

- `check --deploy` mora da zavrsi sa `System check identified no issues`.
- `moderator <ime>` pravi prvog moderatora; lozinka (bar 10 znakova) se unosi dva puta i ne vidi se.
  Ostale moderatore taj moderator dodaje na sajtu, na `/moderator/nalozi/`.

## 6. Servis i nocno odrzavanje

```sh
sudo cp /srv/orkestrator/app/deploy/systemd/orkestrator.service \
        /srv/orkestrator/app/deploy/systemd/orkestrator-odrzavanje.service \
        /srv/orkestrator/app/deploy/systemd/orkestrator-odrzavanje.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now orkestrator orkestrator-odrzavanje.timer
sudo systemctl status orkestrator
```

Status mora biti `active (running)`, a socket `/run/orkestrator/gunicorn.sock` mora postojati.
Odrzavanje se pokrece svake noci oko 04:15: brise istekle sesije i napustene nezavrsene partije
(starije od 15 dana), pa pravi rezervnu kopiju baze.

## 7. HTTPS sertifikat i nginx

Prvi sertifikat se uzima dok nginx ne zauzima port 80, a obnavljanje posle toga ide kroz nginx,
bez zaustavljanja sajta:

```sh
sudo install -d /var/www/certbot
sudo systemctl stop nginx
sudo certbot certonly --standalone -d orkestrator.example -m <email administratora> --agree-tos
sudo certbot reconfigure --cert-name orkestrator.example --webroot -w /var/www/certbot \
     --deploy-hook "systemctl reload nginx"
```

Ako `certbot reconfigure` ne postoji (certbot stariji od 2.3), preskoci ga, pa posle koraka niže
pokreni: `sudo certbot certonly --webroot -w /var/www/certbot -d orkestrator.example --force-renewal --deploy-hook "systemctl reload nginx"`.

```sh
sudo cp /srv/orkestrator/app/deploy/nginx/orkestrator.conf /etc/nginx/sites-available/orkestrator
sudo cp /srv/orkestrator/app/deploy/nginx/orkestrator_proxy.conf /etc/nginx/orkestrator_proxy.conf
sudo ln -s /etc/nginx/sites-available/orkestrator /etc/nginx/sites-enabled/orkestrator
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl start nginx
sudo certbot renew --dry-run
```

Podrazumevani sajt (`default`) se uklanja jer nasa konfiguracija vec ima podrazumevani server: on
odbija zahteve za bilo koji drugi naziv osim `orkestrator.example`.

## 8. Provera posle postavljanja

```sh
curl -sI http://orkestrator.example/     # 301 na https://orkestrator.example/
curl -sI https://orkestrator.example/    # 200, sa strict-transport-security i content-security-policy
sudo systemctl start orkestrator-odrzavanje && ls -l /var/backups/orkestrator   # prva kopija
systemctl list-timers orkestrator-odrzavanje
```

U pregledacu:
1. Odigraj celu partiju do zavrsnog ekrana, sacuvaj ime i otvori link za deljenje u drugom pregledacu.
2. Prijavi se na `https://orkestrator.example/moderator/` i obrisi taj probni rezultat i link;
   brisanje se vidi u dnevniku moderacije.

## Svakodnevni rad

**Dnevnici.** Greske aplikacije: `journalctl -u orkestrator --since today`. Pristup i odbijeni
zahtevi (kod 429): `/var/log/nginx/access.log`.

**Nova verzija igre.** Razvijalac dostavlja ceo folder projekta. Tada:

```sh
sudo systemctl start orkestrator-odrzavanje     # sveza kopija baze pre izmene
# korak 3: rsync, chown, chmod, pip install, compileall (isti redosled)
M="sudo -u orkestrator /srv/orkestrator/app/deploy/manage.sh"
$M migrate
$M collectstatic --noinput
sudo systemctl reload orkestrator               # procesi se menjaju bez prekida igre
```

Ako su se promenili `requirements.txt` ili `deploy/gunicorn.conf.py`, umesto `reload` pokreni
`sudo systemctl restart orkestrator` (prekid od 1 do 2 sekunde). Ako su se promenile datoteke u
`deploy/systemd` ili `deploy/nginx`, ponovo ih kopiraj kao u koracima 6 i 7.

**Bezbednosne ispravke Djanga.** `requirements.txt` dozvoljava sve ispravke serije 6.0. Kada Django
objavi novu 6.0.x verziju:

```sh
sudo /srv/orkestrator/venv/bin/pip install --upgrade -r /srv/orkestrator/app/requirements.txt
sudo systemctl restart orkestrator
```

Ubuntu pakete (nginx, Python, OpenSSL) azurira `unattended-upgrades`, koji je na Ubuntuu ukljucen.

**Rezervne kopije.** Nocna kopija ostaje na istom disku, pa ne stiti od gubitka servera. Folder
`/var/backups/orkestrator` treba svakog dana preneti na drugo mesto, postojecim sistemom za kopije.
Kopije sadrze imena igraca i heseve lozinki moderatora, pa se cuvaju kao poverljive.

**Vracanje kopije.**

```sh
sudo systemctl stop orkestrator
sudo -u orkestrator sh -c 'cd /var/lib/orkestrator && mkdir -p pokvarena && mv db.sqlite3* pokvarena/'
sudo -u orkestrator cp /var/backups/orkestrator/orkestrator-GGGGMMDD-SSMMSS.sqlite3 /var/lib/orkestrator/db.sqlite3
sudo systemctl start orkestrator
```

Partije i rezultati nastali posle te kopije se gube.

**Zaboravljena lozinka moderatora.** Drugi moderator iskljuci stari nalog i napravi novi na sajtu.
Ako nijedan moderator ne moze da se prijavi: `$M moderator <novo ime>`.

**Promena tajnog kljuca** (npr. ako je procurio): upisi novi u `/etc/orkestrator/orkestrator.env`,
pa `sudo systemctl restart orkestrator`. Svi moderatori se odjavljuju, a igraci gube partiju koja je
bila u toku. Sacuvani rezultati i linkovi za deljenje ostaju.

**Javna rang lista za partnere.** Partneri preuzimaju rang listu sa
`https://orkestrator.example/api/rang-lista/` (JSON, bez prijave, sa bilo kog sajta). Odgovor se
kesira 60 sekundi, a nginx dozvoljava najvise 2 zahteva u sekundi sa jedne adrese (rezerva 20).
Provera: `curl -s https://orkestrator.example/api/rang-lista/ | head -c 300`.

**Verzija sa istorijom partija i statistikom.** `$M migrate` jednom racuna poene svih postojecih
zavrsenih partija (za statistiku moderatora). Na velikoj bazi to traje nekoliko sekundi do minuta;
igra za to vreme radi. Promenjen je i `deploy/nginx/orkestrator.conf`, pa ga ponovo kopiraj (korak 7)
i pokreni `sudo nginx -t && sudo systemctl reload nginx`.

## Kapacitet i ogranicenja

- Test opterecenja (3 procesa nad jednom SQLite bazom, igraci bez pauze izmedju poteza): oko 550
  celih partija u minuti, oko 130 zahteva u sekundi, bez ijedne greske. Nekoliko hiljada igraca
  dnevno je vise od 100 puta manje od toga.
- Svaki igrac ima ogranicenje u nginxu: najvise 10 izmena (POST) u sekundi sa iste adrese, uz rezervu
  od 50, i najvise 10 pokusaja prijave moderatora u minuti. Igrac to nikad ne dostigne; zaustavlja
  skripte koje bi masovno pravile partije. Odgovor je tada 429.
- Ako ispred servera stavite CDN ili proxy (npr. Cloudflare), nginx vise ne vidi pravu adresu
  igraca, pa bi ogranicenje vazilo za sve igrace zajedno. Tada u nginx dodajte `real_ip` podesavanja
  tog servisa, ili javite razvijacu.
- Baza je jedna SQLite datoteka, pa igra radi na jednom serveru. Za vise servera ili desetine hiljada
  igraca dnevno treba preci na PostgreSQL; to je izmena koda.
- HSTS: posle prve posete pregledac godinu dana otvara sajt samo preko HTTPS-a. Sertifikat zato ne
  sme da istekne (`certbot renew --dry-run` proverava obnavljanje).
