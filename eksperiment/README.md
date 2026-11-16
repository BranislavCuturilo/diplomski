# Eksperiment: prazan Claude Code prema pluginu `diplomski`

Svi dokazi za poglavlje 7 rada. Eksperiment je radjen od 9. do 13. novembra 2026. u folderu
`C:\poredjenje-orkestrator`; 15. novembra je prebacen ovde, a stari folder je obrisan.
Opis toka i svi brojevi: `../Zapazanja iz poredjenja.docx`.

## Pokretanje igara

Iz Git Bash-a (Windows) ili terminala (Linux, macOS), iz ovog foldera:

```
./pokreni.sh            # obe igre: prazna sesija na http://127.0.0.1:8001/, plugin na http://127.0.0.1:8002/
./pokreni.sh prazan     # samo jedna igra
./pokreni.sh plugin
```

Treba samo Python 3.12 ili noviji. Skript sam pravi `venv` u folderu igre, instalira pakete, primenjuje
migracije i pravi nalog moderatora `demo` (lozinka `Orkestrator-2026!`, prijava na `/moderator/prijava/`;
igra sa pluginom trazi novu lozinku pri prvoj prijavi). Prvo pokretanje traje minut-dva, svako sledece
nekoliko sekundi. Baza iz eksperimenta se pre prvog pokretanja cuva kao `db.sqlite3.original`.
Zaustavljanje: Ctrl+C.

## Sadrzaj

| Folder ili fajl | Sta je |
|---|---|
| `pokreni.sh` | pokretanje obe igre bez znanja Django-a |
| `igre/prazan/` | igra koju je napravio prazan Claude Code, stanje posle runde 7 |
| `igre/plugin/` | igra koju je napravio Claude Code sa pluginom, stanje posle runde 7 (bez kopija `worktree` radnika) |
| `igre/pre-stila/` | obe igre posle izrade, a pre faze stila (runda 1) |
| `plugin-v1-snimak/` | plugin kakav je bio u rundama 1-3 (koren repoa je verzija posle runde 7) |
| `rezultati/` | izvestaji `poredjenje.py` i `izvestaj_faza.py`, nezavisne provere po funkcionalnosti |
| `upiti/` | 13 upita, isti tekst na obe strane |
| `manifest.json`, `provera.json`, `POKRETANJE.md` | postavka eksperimenta, verzije plugina, uputstvo za pokretanje |
| `provere/` | skripte nezavisnih provera i merenja, pisane posle svake izrade |

## Stare putanje

Zapisi i skripte i dalje navode `C:\poredjenje-orkestrator`, jer su tako napravljeni. Nove putanje:

| Bilo | Sada |
|---|---|
| `C:\poredjenje-orkestrator\prazan\projekat` | `eksperiment\igre\prazan` |
| `C:\poredjenje-orkestrator\plugin\projekat` | `eksperiment\igre\plugin` |
| `C:\poredjenje-orkestrator\rezultati` | `eksperiment\rezultati` |
| `C:\poredjenje-orkestrator\plugin\config\skills\diplomski` | koren ovog repoa (bio je identican) |

Skripte iz `provere/` treba prepraviti na nove putanje pre ponovnog pokretanja; za one koje koriste
pregledac u `venv` igre treba i `pip install -r requirements-razvoj.txt` i `python -m playwright install chromium`.

Nije sacuvano: transkripti sesija, git istorija igre sa pluginom, `venv` obe strane, podaci Cursor-a i
pristupni podaci naloga. Brojevi iz transkripata su vec u `rezultati/` i u `../Zapazanja iz poredjenja.docx`,
ali se iz ovog foldera ne mogu ponovo izracunati.
