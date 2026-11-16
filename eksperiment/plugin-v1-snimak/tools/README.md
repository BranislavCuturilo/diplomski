# Alati koji stede tokene

Nacelo: **sve sto skripta moze tacno da izracuna, racuna skripta.** Agent koji cita
500 redova izlaza testova da bi nasao 2 pala trosi tokene i moze da pogresi u
brojanju. Skripta to radi besplatno, a agentu ostaje samo odluka sta da uradi.

| Alat | Umesto da agent... | Agent dobija |
|---|---|---|
| `test_summary.py` | cita ceo izlaz pytest-a | jedan red: "142 proslo, 2 palo" + samo pale testove |
| `find_unscoped_pk.py` | cita svaki views.py trazeci IDOR | spisak `fajl:red` gde se objekat cita po pk bez `for_user` |
| `check_migrations.py` | cita svaku migraciju | spisak rizicnih operacija (NOT NULL na punoj tabeli, brisanje kolone, RunPython bez reverse) |

Agenti ih pozivaju preko alata Bash, punom putanjom:

```
python "${CLAUDE_PLUGIN_ROOT}/tools/test_summary.py"
```

U telu agenta i skilla Claude Code `${CLAUDE_PLUGIN_ROOT}` zamenjuje stvarnom putanjom
pri ucitavanju; u samom Bash okruzenju ta promenljiva NE postoji, pa se ne pise kao `$CLAUDE_PLUGIN_ROOT`.
Pozivi stoje u postupku agenata `qa`, `backend-*` i `security`.
