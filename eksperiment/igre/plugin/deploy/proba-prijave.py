"""Proba prijave kroz Nginx (revizija S1, DEPLOY.md 7a). Samo standardna biblioteka: radi u slici app.

Jedna spora prijava (POST sa telom od 1 bajta na 3 s) drzi vezu, a za to vreme stizu tri obicne prijave, dve u
istoj sekundi. Obicne ne smeju dobiti 429: Nginx ogranicava stopu prijava na celom sajtu, ne broj istovremenih
veza, pa spor klijent ne drzi zajednicko mesto. Obicne prijave nemaju CSRF token, pa ocekivano dobijaju 403 od
Django-a (lozinka se ne proverava, PBKDF2 se ne trosi). Sa iste adrese trosi 4 od 6 prijava u minuti: pokrece se
bar minut posle provera.sh.

  python deploy/proba-prijave.py --cilj web --host DOMEN [--nesigurno]

Spora veza prolazi samo ako je Nginx drzi dok klijent salje i posle prekida slanja je zatvori (bez odgovora ili
sa 408). Odgovor aplikacije na nepotpun zahtev (npr. 403 od Django-a bez Nginx-a ispred) je PAD.

Izlaz: kod svake obicne prijave, ishod spore veze i presuda; kod 0 samo uz prolaz. Ne ispisuje kolacice.
"""

import argparse
import http.client
import select
import socket
import ssl
import sys
import threading
import time

PUTANJA = "/moderator/prijava/"
DUZINA_TELA = 4000  # ispod client_max_body_size 4k za prijavu
KORAK_SPORE = 3  # s izmedju dva bajta; client_body_timeout prijave je 5 s
TRAJANJE_SPORE = 21  # s


def kontekst(nesigurno):
    k = ssl.create_default_context()
    if nesigurno:
        k.check_hostname = False
        k.verify_mode = ssl.CERT_NONE
    return k


def tls_veza(args):
    sirova = socket.create_connection((args.cilj, args.port), timeout=30)
    return kontekst(args.nesigurno).wrap_socket(sirova, server_hostname=args.host)


def procitaj_odgovor(veza, rok):
    """Prvi red odgovora; "zatvorena bez odgovora", "prekinuta" ili "NIJE zatvorena za N s"."""
    veza.settimeout(rok)
    try:
        red = veza.recv(200).split(b"\r\n", 1)[0].decode("ascii", "replace")
    except TimeoutError:
        return f"NIJE zatvorena za {rok} s"
    except OSError:
        return "prekinuta"
    return red or "zatvorena bez odgovora"


def rani_odgovor(veza):
    """Socket je citljiv dok klijent salje: odgovor, zatvaranje, ili samo TLS poruka (npr. TLS 1.3 session ticket,
    tada None)."""
    veza.setblocking(False)
    try:
        podaci = veza.recv(200)
    except ssl.SSLWantReadError:
        return None
    except OSError:
        return "prekinuta"
    finally:
        veza.settimeout(30)
    return podaci.split(b"\r\n", 1)[0].decode("ascii", "replace") or "zatvorena bez odgovora"


def obicna_prijava(args, ime, ishodi):
    # Sirov HTTP preko TLS-a: SNI mora biti domen, a veza ide na --cilj (http.client bi poslao SNI "web").
    telo = b"username=&password="
    try:
        with tls_veza(args) as veza:
            veza.sendall(
                (
                    f"POST {PUTANJA} HTTP/1.1\r\nHost: {args.host}\r\nConnection: close\r\n"
                    f"Content-Type: application/x-www-form-urlencoded\r\nContent-Length: {len(telo)}\r\n\r\n"
                ).encode("ascii")
                + telo
            )
            odgovor = http.client.HTTPResponse(veza)
            odgovor.begin()
            status = odgovor.status
    except (OSError, http.client.HTTPException) as greska:
        status = f"greska veze: {type(greska).__name__}"
    ishodi[ime] = status
    print(f"  {time.strftime('%H:%M:%S')} {ime}: {status}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cilj", required=True, help="adresa Nginx-a: web (iz compose mreze) ili IP servera")
    parser.add_argument("--host", required=True, help="DOMEN (Host i TLS SNI)")
    parser.add_argument("--port", type=int, default=443)
    parser.add_argument("--nesigurno", action="store_true", help="prihvata privremeni samopotpisani sertifikat")
    args = parser.parse_args()

    print(f"Spora prijava: Content-Length {DUZINA_TELA}, 1 bajt na {KORAK_SPORE} s, {TRAJANJE_SPORE} s", flush=True)
    spora = tls_veza(args)
    spora.sendall(
        (
            f"POST {PUTANJA} HTTP/1.1\r\nHost: {args.host}\r\n"
            f"Content-Type: application/x-www-form-urlencoded\r\nContent-Length: {DUZINA_TELA}\r\n\r\n"
        ).encode("ascii")
    )
    pocetak = time.monotonic()
    ishodi = {}
    zakazano = {2: ("obicna 1", "obicna 2"), 11: ("obicna 3",)}  # sekunda od pocetka -> prijave u istom trenutku
    niti = []
    poslato = 0
    # Dok klijent salje na 3 s (rok je 5 s), Nginx ne sme ni da odgovori ni da zatvori vezu: zahtev bez celog
    # tela ostaje u Nginx-u. Odgovor ili zatvaranje u ovoj fazi je PAD (npr. Django odmah vrati 403 bez tela).
    rano = None
    while time.monotonic() - pocetak < TRAJANJE_SPORE:
        sekunda = int(time.monotonic() - pocetak)
        for ime in zakazano.pop(sekunda, ()):
            nit = threading.Thread(target=obicna_prijava, args=(args, ime, ishodi))
            nit.start()
            niti.append(nit)
        if rano is None and select.select([spora], [], [], 0)[0]:
            rano = rani_odgovor(spora)
        if rano is None and time.monotonic() - pocetak >= poslato * KORAK_SPORE:
            try:
                spora.sendall(b"a")
                poslato += 1
            except OSError as greska:
                rano = procitaj_odgovor(spora, 1) or f"prekinuta ({type(greska).__name__})"
        time.sleep(0.2)
    for nit in niti:
        nit.join()

    if rano is not None:
        ishod_spore = f"ODGOVOR ILI ZATVARANJE PRE KRAJA TELA, dok je klijent jos slao: {rano}"
        spora_zatvorena = False
    else:
        # Sada se prekida slanje: Nginx zatvara vezu posle client_body_timeout (5 s). Prolaz samo za zatvorenu vezu
        # ili 408 Nginx-a; svaki drugi status je odgovor aplikacije na nepotpun zahtev.
        print(f"Spora veza: poslato {poslato} bajtova tela; slanje prestaje, ceka se da je Nginx zatvori", flush=True)
        odgovor = procitaj_odgovor(spora, 15)
        if odgovor in ("zatvorena bez odgovora", "prekinuta"):
            ishod_spore, spora_zatvorena = odgovor, True
        elif odgovor.split(" ")[1:2] == ["408"]:
            ishod_spore, spora_zatvorena = f"Nginx 408 ({odgovor})", True
        elif odgovor == "NIJE zatvorena za 15 s":
            ishod_spore, spora_zatvorena = odgovor, False
        else:
            ishod_spore, spora_zatvorena = f"ODGOVOR APLIKACIJE ({odgovor}) na nepotpun zahtev", False
    spora.close()
    print(f"Spora veza posle {time.monotonic() - pocetak:.0f} s: {ishod_spore}", flush=True)

    obicne = [ishodi.get(ime) for ime in ("obicna 1", "obicna 2", "obicna 3")]
    bez_429 = all(status == 403 for status in obicne)
    print(f"obicne prijave dok spora drzi vezu: {obicne} (ocekivano 403, nikad 429): {'PROLAZ' if bez_429 else 'PAD'}")
    print(f"spora veza zatvorena bez odgovora aplikacije (zatvorena ili 408): {'PROLAZ' if spora_zatvorena else 'PAD'}")
    print("PROBA PRIJAVE PROSLA" if bez_429 and spora_zatvorena else "PROBA PRIJAVE PALA")
    return 0 if bez_429 and spora_zatvorena else 1


if __name__ == "__main__":
    sys.exit(main())
