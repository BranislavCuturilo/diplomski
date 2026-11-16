---
name: projekat-odluke
nivo: 3
preovladjuje: [projekat-standardi, projekat-domen]
description: >
  Odluke korisnika za slucajeve u kojima se dva projektna skilla suprotstavljaju:
  kada agent naidje na sukob, stane i pita, a odgovor se upisuje ovde sa datumom i
  razlogom, pa sledeca sesija ne pita ponovo. Ucitaj zajedno sa projekat-standardi.
  Preovladjuje nad nivoom 2. Okidaci: "dva skilla kazu razlicito", "sukob pravila".
---

# projekat-odluke (nivo 3)

Svaka odluka nastaje kada agent naidje na sukob, stane i pita. Format:
datum, sukob, odluka, ko je odlucio. Odluka se ne menja bez novog pitanja.

Zasad nema odluka.

## Sablon za novu odluku

```
## <datum> · <kratak naziv>
- Sukob: <skill A> kaze ..., <skill B> kaze ...
- Odluka: ...
- Odlucio: ...
```
