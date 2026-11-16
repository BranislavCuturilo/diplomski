---
name: craft-code
description: >
  Disciplina pisanja koda nezavisna od jezika. Ucitaj PRE pisanja, menjanja ili
  pregleda bilo kog koda. Pokriva gde logika zivi, sta se ne menja "usput",
  kako se greska prijavljuje i kada se postojece koristi umesto novog.
  Okidaci: "napisi funkciju", "dodaj", "refaktorisi", "zasto je ovo ovako",
  "pregledaj kod", metoda koja stalno raste.
---

# craft-code

Samo ono sto model ne radi sam od sebe. Opste dobre prakse (citljiva imena,
kratke funkcije) se ovde NE ponavljaju.

## Tri pravila koja se nikad ne preskacu

1. **Pre novog: pretrazi postojece.** Pre nego sto napises helper, `grep` po imenu
   glagola i imenice (`format_date`, `date_format`, `fmt_date`). Model po default-u
   pise novi helper jer je to brze od citanja. Druga kopija je druga verzija baga.
   *Poreklo: tri razlicite funkcije za formatiranje datuma u istom projektu, svaka sa drugom greskom.*

2. **Ne menjaj ono sto nije trazeno.** Preformatiranje, preimenovanje i "sitna
   poboljsanja" u istom diffu kriju stvarnu izmenu od recenzenta. Ako vidis nesto
   lose van zadatka: zapisi u izvestaj, ne diraj.

3. **Greska se ne guta.** `except: pass`, `catch {}` i `|| true` bez komentara su
   zabranjeni. Ako je ocekivano da nesto ne uspe, pise se ZASTO, u istom redu.

## Gde logika zivi

| Logika | Mesto |
|---|---|
| upis u vise redova, redosled koraka koji ne sme da se polovicno izvrsi | servisni sloj, u transakciji |
| pravilo o jednom objektu (stanje, granice polja) | model |
| sta korisnik vidi i sme | sloj upita / menadzer (vidi craft-security) |
| formatiranje za prikaz | sloj prikaza, nikad model |

## Kada je duplikat ispravan

Dve slicne funkcije koje se menjaju iz RAZLICITIH razloga ostaju odvojene.
Izdvaja se tek kod treceg pojavljivanja istog razloga.

## Izvestaj agenta

Na kraju rada: izmenjene datoteke, sta je pokrenuto (testovi) i sa kojim
ishodom, sta NIJE uradjeno i zasto, otvorena pitanja. Bez "trebalo bi da radi":
ili je pokrenuto i proslo, ili pise da nije pokrenuto.
