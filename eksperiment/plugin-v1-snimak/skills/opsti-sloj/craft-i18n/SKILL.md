---
name: craft-i18n
description: >
  Kako se prevodi aplikacija a da prevod ne polomi poruke: mnozina, mesta za
  vrednosti, sta se nikad ne prevodi. Ucitaj PRE prevoda, dodavanja jezika ili
  pisanja teksta koji ce se prevoditi. Okidaci: "prevedi", "prevod", "engleska
  verzija", "dodaj jezik", ".po", "i18n", "mnozina", "msgid", "prevod puca".
---

# craft-i18n

## Tri pravila koja se nikad ne preskacu

1. **Recenica se ne sklapa od prevedenih delova.** `_("Obrisano") + " " + n + " " + _("stavki")`
   je neprevodivo: drugi jezik ima drugi red reci. Cela recenica je jedna poruka
   sa imenovanim mestom: `_("Obrisano %(n)s stavki")`.

2. **Mnozina ide kroz funkciju za mnozinu** (`ngettext`). Srpski ima tri oblika
   (1 stavka, 2 stavke, 5 stavki), engleski dva. Nikad `if n == 1`.

3. **Mesto za vrednost se prepisuje tacno.** `%(n)s` u prevodu mora ostati
   `%(n)s`, ne `%(broj)s` ni `% (n)s`. Provera kataloga (`msgfmt --check`)
   mora proci pre isporuke.

## Sta se nikad ne prevodi

Kodovi formata datuma, imena polja u JSON-u, URL putanje, CSS klase, kljucevi
podesavanja, tekst koji ide u log (logovi ostaju na jednom jeziku radi pretrage).

## Za prevodioca (agent)

Prevodi samo `msgstr`. `msgid` se nikad ne menja. Oznaka `fuzzy` znaci da
prevod nije potvrdjen: pregledaj ga, ne ostavljaj ga.
