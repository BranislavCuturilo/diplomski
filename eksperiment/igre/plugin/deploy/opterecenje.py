"""Proba opterecenja Orkestratora (plan 15.2 i 15.11, T2). Samo standardna biblioteka: radi u slici app.

Dva nacina:
  igra      Igraci igraju cele partije: GET /, 8 x POST /potez/ (CSRF), POST /sacuvaj/, POST /podeli/, GET /;
            uz to GET /zdravlje/ oko jednom u sekundi. Gadja gunicorn DIREKTNO (http://app:8000) u odvojenom
            compose projektu (deploy/proba-opterecenja.sh): meri aplikaciju i SQLite. Kroz Nginx bi sve islo
            sa jedne adrese, pa bi ogranicenje brzine vratilo 429 i proba ne bi merila aplikaciju.
  zdravlje  Kratak nalet GET /zdravlje/ kroz Nginx (https://web): potvrdjuje da ogranicenje brzine vraca 429.
            Samo cita bazu, ne pravi sesiju ni red.

Tempo je otvoren: zahtev se salje u zakazanom trenutku bez obzira na to da li su prethodni zavrseni, a vreme
odgovora se meri od zakazanog trenutka (ukljucuje i cekanje kada aplikacija ne prati tempo).
Ne ispisuje kolacice, tokene ni linkove. Izlaz: tabela, presude i red `REZULTAT {json}`; kod 0 samo uz prolaz.

  python deploy/opterecenje.py --nacin igra --cilj http://app:8000 --host DOMEN [--zs 50] [--trajanje 300]
  python deploy/opterecenje.py --nacin zdravlje --cilj https://web --host DOMEN --nesigurno --zs 40 --trajanje 3
"""

import argparse
import http.client
import http.cookies
import json
import math
import random
import ssl
import sys
import threading
import time
from collections import Counter, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

IZBORI = {
    "model": ("haiku", "sonnet", "opus"),
    "nivo": ("low", "high", "max"),
    "kontekst": ("malo", "taman", "sve"),
    "podela": ("sam", "tri", "pedeset"),
}
KRUGOVA = 8
ZDRAVLJE_SVAKI = 50  # svaki pedeseti zakazani zahtev, oko 1 u sekundi pri 50 z/s
NAJVISE_NA_CEKANJU = 1000  # vise zakazanih a nezavrsenih zahteva znaci da aplikacija ne prati tempo


class _HttpsSaSni(http.client.HTTPSConnection):
    """Veza na adresu (npr. web ili IP), a TLS SNI je domen: Nginx tudji SNI odbija (ssl_reject_handshake)."""

    def __init__(self, adresa, port, sni, kontekst, timeout):
        super().__init__(adresa, port, context=kontekst, timeout=timeout)
        self._sni = sni

    def connect(self):
        http.client.HTTPConnection.connect(self)
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self._sni)


class Klijent:
    def __init__(self, cilj, host, nesigurno, timeout):
        delovi = urlsplit(cilj)
        self.https = delovi.scheme == "https"
        self.adresa = delovi.hostname
        self.port = delovi.port or (443 if self.https else 80)
        self.host = host
        self.poreklo = f"https://{host}"
        self.timeout = timeout
        self.kontekst = None
        if self.https:
            self.kontekst = ssl.create_default_context()
            if nesigurno:
                self.kontekst.check_hostname = False
                self.kontekst.verify_mode = ssl.CERT_NONE

    def posalji(self, metoda, putanja, kolacici, telo=None, csrf=False):
        """(status, Set-Cookie vrednosti, telo). Nova veza po zahtevu: gunicorn sync ionako zatvara vezu."""
        zaglavlja = {
            "Host": self.host,
            # Kao iza Nginx-a; bez ovoga settings_prod preusmerava na https (301). Nginx ga ionako prepisuje.
            "X-Forwarded-Proto": "https",
            "Connection": "close",
            "User-Agent": "orkestrator-proba-opterecenja",
        }
        if kolacici:
            zaglavlja["Cookie"] = "; ".join(f"{ime}={vrednost}" for ime, vrednost in kolacici.items())
        if metoda == "POST":
            zaglavlja["Origin"] = self.poreklo
            zaglavlja["Content-Type"] = "application/json"
        if csrf:
            zaglavlja["X-CSRFToken"] = kolacici.get("csrftoken", "")
        if self.https:
            veza = _HttpsSaSni(self.adresa, self.port, self.host, self.kontekst, self.timeout)
        else:
            veza = http.client.HTTPConnection(self.adresa, self.port, timeout=self.timeout)
        try:
            veza.request(metoda, putanja, body=telo, headers=zaglavlja)
            odgovor = veza.getresponse()
            sadrzaj = odgovor.read()
            return odgovor.status, odgovor.headers.get_all("Set-Cookie") or [], sadrzaj
        finally:
            veza.close()


def upamti_kolacice(kolacici, set_cookie):
    for red in set_cookie:
        kolac = http.cookies.SimpleCookie()
        kolac.load(red)
        for ime, morsel in kolac.items():
            kolacici[ime] = morsel.value


class Merenje:
    def __init__(self):
        self.brava = threading.Lock()
        self.vremena = defaultdict(list)  # kljuc zahteva -> ms
        self.statusi = defaultdict(Counter)  # kljuc zahteva -> status -> broj
        self.greske_veze = Counter()  # vrsta izuzetka -> broj
        self.neocekivano = Counter()  # "kljuc status" -> broj
        self.partija_zavrseno = 0
        self.link_los = 0

    def zapisi(self, kljuc, status, ms, ocekivan):
        with self.brava:
            self.vremena[kljuc].append(ms)
            self.statusi[kljuc][status] += 1
            if status not in ocekivan:
                self.neocekivano[f"{kljuc} {status}"] += 1

    def greska(self, kljuc, izuzetak, ms):
        with self.brava:
            self.vremena[kljuc].append(ms)
            self.greske_veze[f"{kljuc} {type(izuzetak).__name__}"] += 1


def procenat(sortirano, p):
    if not sortirano:
        return 0.0
    # Najblizi rang: najmanja vrednost od koje je bar p% merenja manje ili jednako.
    indeks = max(0, min(len(sortirano) - 1, math.ceil(p / 100 * len(sortirano)) - 1))
    return sortirano[indeks]


class Partija:
    """Jedan igrac, korak po korak; sledeci korak tek kada je prethodni zavrsen (isti kolacici)."""

    def __init__(self, broj, klijent, merenje):
        self.broj = broj
        self.klijent = klijent
        self.merenje = merenje
        self.kolacici = {}
        self.korak = 0
        self.gotova = False

    def _potez(self, krug):
        izbori = {grupa: random.choice(opcije) for grupa, opcije in IZBORI.items()}
        return json.dumps({"krug": krug, "izbori": izbori}).encode()

    def sledeci(self, zakazano):
        k = self.korak
        if k == 0 or k == KRUGOVA + 3:
            kljuc, metoda, putanja, telo, csrf = "GET /", "GET", "/", None, False
        elif k <= KRUGOVA:
            kljuc, metoda, putanja, telo, csrf = "POST /potez/", "POST", "/potez/", self._potez(k), True
        elif k == KRUGOVA + 1:
            ime = f"Proba {self.broj % 100000}"
            kljuc, metoda, putanja, telo, csrf = "POST /sacuvaj/", "POST", "/sacuvaj/", json.dumps({"ime": ime}).encode(), True
        else:
            kljuc, metoda, putanja, telo, csrf = "POST /podeli/", "POST", "/podeli/", b"", True
        try:
            status, set_cookie, sadrzaj = self.klijent.posalji(metoda, putanja, self.kolacici, telo, csrf)
        except (OSError, http.client.HTTPException) as izuzetak:
            self.merenje.greska(kljuc, izuzetak, (time.monotonic() - zakazano) * 1000)
            self.gotova = True  # bez odgovora partija ne moze dalje; nova partija ce zauzeti njeno mesto
            return
        ms = (time.monotonic() - zakazano) * 1000
        self.merenje.zapisi(kljuc, status, ms, {200})
        upamti_kolacice(self.kolacici, set_cookie)
        if status != 200:
            self.gotova = True
            return
        if kljuc == "POST /podeli/":
            url = json.loads(sadrzaj).get("url", "")
            if not url.startswith(f"https://{self.klijent.host}/r/"):
                with self.merenje.brava:
                    self.merenje.link_los += 1
        self.korak += 1
        if self.korak > KRUGOVA + 3:
            self.gotova = True
            with self.merenje.brava:
                self.merenje.partija_zavrseno += 1


def zdravlje(klijent, merenje, zakazano, ocekivan):
    kljuc = "GET /zdravlje/"
    try:
        status, set_cookie, sadrzaj = klijent.posalji("GET", "/zdravlje/", {})
    except (OSError, http.client.HTTPException) as izuzetak:
        merenje.greska(kljuc, izuzetak, (time.monotonic() - zakazano) * 1000)
        return
    merenje.zapisi(kljuc, status, (time.monotonic() - zakazano) * 1000, ocekivan)
    if status == 200 and (set_cookie or json.loads(sadrzaj).get("ok") is not True):
        with merenje.brava:
            merenje.neocekivano[f"{kljuc} 200 sa kolacicem ili bez ok"] += 1


def pokreni(args):
    klijent = Klijent(args.cilj, args.host, args.nesigurno, args.timeout)
    merenje = Merenje()
    spremne = deque()
    brava = threading.Lock()
    na_cekanju = [0]
    brojac_partija = [0]
    prekinuto = ""

    def zavrsi(posao, *argumenti):
        # ThreadPoolExecutor bi izuzetak iz niti progutao; ovde se broji i ide u presudu.
        try:
            posao(*argumenti)
        except Exception as izuzetak:
            with merenje.brava:
                merenje.greske_veze[f"interno {type(izuzetak).__name__}: {izuzetak}"[:120]] += 1
        finally:
            with brava:
                na_cekanju[0] -= 1

    def korak_partije(partija, zakazano):
        partija.sledeci(zakazano)
        if not partija.gotova:
            with brava:
                spremne.append(partija)

    ocekivan_zdravlje = {200} if args.nacin == "igra" else {200, 429}
    pocetak = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.niti) as izvrsilac:
        i = 0
        while True:
            zakazano = pocetak + i / args.zs
            if zakazano - pocetak >= args.trajanje:
                break
            cekaj = zakazano - time.monotonic()
            if cekaj > 0:
                time.sleep(cekaj)
            with brava:
                if na_cekanju[0] > NAJVISE_NA_CEKANJU:
                    prekinuto = f"vise od {NAJVISE_NA_CEKANJU} zahteva na cekanju posle {zakazano - pocetak:.0f} s"
            if prekinuto:
                izvrsilac.shutdown(wait=True, cancel_futures=True)  # zakazano a nezapoceto se ne salje
                break
            with brava:
                na_cekanju[0] += 1
            if args.nacin == "zdravlje" or i % ZDRAVLJE_SVAKI == ZDRAVLJE_SVAKI - 1:
                izvrsilac.submit(zavrsi, zdravlje, klijent, merenje, zakazano, ocekivan_zdravlje)
            else:
                with brava:
                    partija = spremne.popleft() if spremne else None
                    if partija is None:
                        brojac_partija[0] += 1
                        partija = Partija(brojac_partija[0], klijent, merenje)
                izvrsilac.submit(zavrsi, korak_partije, partija, zakazano)
            i += 1
    trajalo = time.monotonic() - pocetak
    return merenje, trajalo, brojac_partija[0], prekinuto


def izvestaj(args, merenje, trajalo, partija_pocelo, prekinuto):
    sva = sorted(ms for lista in merenje.vremena.values() for ms in lista)
    ukupno = len(sva)
    svi_statusi = Counter()
    for statusi in merenje.statusi.values():
        svi_statusi.update(statusi)
    pet_xx = sum(broj for status, broj in svi_statusi.items() if status >= 500)
    p = {f"p{n}": round(procenat(sva, n), 1) for n in (50, 95, 99)}
    ostvareno = ukupno / trajalo if trajalo else 0.0

    print(f"\nNacin {args.nacin}, cilj {args.cilj}, Host {args.host}, zadato {args.zs} z/s, {args.trajanje} s")
    print(f"{'zahtev':<16}{'broj':>8}{'p50 ms':>9}{'p95 ms':>9}{'p99 ms':>9}  statusi")
    for kljuc in sorted(merenje.vremena):
        lista = sorted(merenje.vremena[kljuc])
        statusi = ", ".join(f"{s}: {b}" for s, b in sorted(merenje.statusi[kljuc].items()))
        print(
            f"{kljuc:<16}{len(lista):>8}{procenat(lista, 50):>9.1f}{procenat(lista, 95):>9.1f}"
            f"{procenat(lista, 99):>9.1f}  {statusi}"
        )
    print(f"{'ukupno':<16}{ukupno:>8}{p['p50']:>9.1f}{p['p95']:>9.1f}{p['p99']:>9.1f}")
    print(f"ostvareno {ostvareno:.1f} z/s za {trajalo:.1f} s")
    if args.nacin == "igra":
        print(f"partija zapoceto {partija_pocelo}, zavrseno do podeli {merenje.partija_zavrseno}")
    for opis, broj in sorted(merenje.greske_veze.items()):
        print(f"greska veze: {opis}: {broj}")
    for opis, broj in sorted(merenje.neocekivano.items()):
        print(f"neocekivan odgovor: {opis}: {broj}")

    presude = []
    if args.nacin == "igra":
        presude = [
            ("bez gresaka veze", not merenje.greske_veze),
            ("0 odgovora 5xx", pet_xx == 0),
            ("0 odgovora 429 (direktno na aplikaciju)", svi_statusi[429] == 0),
            ("svi odgovori 200", not merenje.neocekivano),
            (f"p95 < {args.p95_ms} ms", p["p95"] < args.p95_ms),
            ("ostvareno bar 90% zadatog tempa", ostvareno >= 0.9 * args.zs),
            ("bar jedna partija do kraja", merenje.partija_zavrseno > 0),
            ("svaki link je https://<Host>/r/", merenje.link_los == 0),
            ("tempo nije prekinut", not prekinuto),
        ]
    else:
        presude = [
            ("bez gresaka veze", not merenje.greske_veze),
            ("0 odgovora 5xx", pet_xx == 0),
            ("bar jedan 200 (Nginx propusta)", svi_statusi[200] > 0),
            ("bar jedan 429 (ogranicenje brzine radi)", svi_statusi[429] > 0),
            ("samo 200 i 429", not merenje.neocekivano),
        ]
    if prekinuto:
        print(f"PREKINUTO: {prekinuto}")
    for opis, prosao in presude:
        print(f"  {'PROLAZ' if prosao else 'PAD   '} {opis}")
    prolaz = all(prosao for _, prosao in presude)
    rezultat = {
        "nacin": args.nacin,
        "zadato_zs": args.zs,
        "trajanje_s": args.trajanje,
        "ostvareno_zs": round(ostvareno, 1),
        "zahteva": ukupno,
        **{k + "_ms": v for k, v in p.items()},
        "statusi": {str(s): b for s, b in sorted(svi_statusi.items())},
        "greske_veze": sum(merenje.greske_veze.values()),
        "neocekivano": sum(merenje.neocekivano.values()),
        "partija_zavrseno": merenje.partija_zavrseno,
        "prolaz": prolaz,
    }
    print("REZULTAT " + json.dumps(rezultat, ensure_ascii=False))
    return prolaz


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--nacin", choices=("igra", "zdravlje"), default="igra")
    parser.add_argument("--cilj", required=True, help="http://app:8000 (igra) ili https://web (zdravlje)")
    parser.add_argument("--host", required=True, help="domen iz .env (DOMEN): Host, SNI i Origin")
    parser.add_argument("--zs", type=float, default=50.0, help="zahteva u sekundi (plan 15.2: 50)")
    parser.add_argument("--trajanje", type=float, default=300.0, help="sekundi (plan 15.11: 5 minuta)")
    parser.add_argument("--niti", type=int, default=64)
    parser.add_argument("--timeout", type=float, default=30.0, help="sekundi po zahtevu (gunicorn timeout 30)")
    parser.add_argument("--p95-ms", type=float, default=300.0, help="granica p95 (plan 15.11: 300 ms)")
    parser.add_argument("--nesigurno", action="store_true", help="prihvata samopotpisani sertifikat")
    args = parser.parse_args()
    merenje, trajalo, partija_pocelo, prekinuto = pokreni(args)
    sys.exit(0 if izvestaj(args, merenje, trajalo, partija_pocelo, prekinuto) else 1)


if __name__ == "__main__":
    main()
