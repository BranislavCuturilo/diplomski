# Pokretanje poredjenja

Isti rezim dozvola i isti model na obe strane. Radi se kroz Claude ekstenziju u Cursor-u.

## 1. Prijava, jednom po strani

```
& "C:\poredjenje-orkestrator\prazan\prijava.cmd"
& "C:\poredjenje-orkestrator\plugin\prijava.cmd"
```

## 2. Dokaz da su strane ciste, pre prvog upita

```
python "C:\posao\diplomski\scripts\poredjenje.py" provera "C:\poredjenje-orkestrator"
```

Mora da se zavrsi sa `SVE PROVERE PROSLE`. Dokaz ostaje u `provera.json`.

## 3. Cursor

Svaku stranu otvori SAMO njenim launcherom, da bi prozor dobio okruzenje strane:

```
& "C:\poredjenje-orkestrator\prazan\otvori.cmd"
& "C:\poredjenje-orkestrator\plugin\otvori.cmd"
```

Koristi Claude ekstenziju u tim prozorima. Cursor AI ne koristi.

## 4. Start, u oba prozora u isto vreme

Jedna sesija po strani.

1. Nalepi tacno tekst iz `UPIT.txt`: agent pravi `plan.md`.
2. Odmah proveri da rad ide u pravi folder: `python "C:\posao\diplomski\scripts\poredjenje.py" trag "C:\poredjenje-orkestrator"`. Svaka strana mora da ima transkript, a maticni folder 0.
3. Kada je plan gotov, nalepi tacno tekst iz `UPIT-izrada.txt`: agent gradi igru.
4. Kada je izrada gotova, u istoj sesiji nalepi tacno tekst iz `UPIT-stil.txt`: agent doradjuje izgled.

## 5. Runda 2: nove funkcionalnosti

Svaki od upita `UPIT-4-rang.txt`, `UPIT-5-deljenje.txt` i `UPIT-6-jezik.txt` ide redom, u NOVOJ sesiji
(novi razgovor u panelu istog prozora), na obe strane u isto vreme. Sledeci upit tek kada obe strane zavrse.
Odmah posle svakog upita pokreni `trag`. Ako agent trazi potvrdu plana, odgovori "Potvrdjeno."

## 6. Runda 3: zahtevi u kojima greska skupo kosta

Isto kao runda 2, redom: `UPIT-7-bodovanje.txt`, `UPIT-8-moderator.txt`, `UPIT-9-javno.txt`.

## 7. Runda 4: plugin v2

`UPIT-10-izazov.txt` u NOVOJ sesiji na obe strane, sa istim modelom i nivoom izabranim u panelu
(Sonnet 5.5, medium). Plugin je pre ove runde izmenjen (v2); to pise u `manifest.json` (`plugin_v2`).

## 8. Runda 5: plugin v2.2

`UPIT-11-csv.txt` u NOVOJ sesiji na obe strane, Opus 5.5 na NAJNIZEM nivou izabranom u panelu, isto na
obe strane. Plugin v2.2 je u `manifest.json` (`plugin_v2_2`).

## 9. Runda 6: plugin v2.3

`UPIT-12-prijava.txt` u NOVOJ sesiji na obe strane, Fable 5.2 na NAJVISEM nivou izabranom u panelu, isto
na obe strane. Plugin v2.3 je u `manifest.json` (`plugin_v2_3`).

## Pravila za coveka tokom izrade

- Odgovaraj samo kada agent pita; isto pitanje dobija isti odgovor na obe strane.
- Dozvole za komande odobravaj podjednako brzo na obe strane.
- Plan ne doradjuj sam. Ne pomazi, ne ispravljaj i ne pozuruj. Svaka poruka osim dva propisana upita broji se kao podpitanje.
- Kada agent kaze da je gotovo, ne doradjuj posle toga.

## Posle izrade

```
python "C:\posao\diplomski\scripts\poredjenje.py" slepo "C:\poredjenje-orkestrator"
```

Popuni `ocena/ocena.json` gledajuci samo foldere `ocena/X` i `ocena/Y`; `ocena/kljuc.json` ne otvaraj.

```
python "C:\posao\diplomski\scripts\poredjenje.py" izvestaj "C:\poredjenje-orkestrator"
```

Rezultat: `rezultati/poredjenje.md` i `.json`.
