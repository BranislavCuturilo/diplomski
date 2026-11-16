# Hookovi

Skill kaze agentu STA da radi. Hook obezbedjuje da se to DOGODI, bez obzira da li
je model zapamtio pravilo. Hook se izvrsava deterministicki, bez modela, i ne kosta tokene.

## Rade samo u projektu sa markerom

Plugin u maticnom folderu vazi za SVE projekte. Zato svaka komanda iz `hooks.json` ide kroz
`pokreni.py`: ako projekat nema `.claude/diplomski-projekat`, izlazi sa 0, bez ispisa i bez
upisa. To odlucuje samo `projekat.py`, jedna provera umesto po jedne u svakom hooku.

`pokreni.py` ulaz cita kao UTF-8 i tako ga predaje hooku. Na Windows-u je `sys.stdin` cp1252,
pa bi slovo sa kvacicom srusilo `json.load`, a hookovi taj izuzetak gutaju: hook bi cutke prestao da radi.

| Hook | Dogadjaj | Radi | Zasto postoji |
|---|---|---|---|
| `scripts/sync.py --pull` | SessionStart | `git pull --ff-only`; bez remote-a ne radi nista | pravila sa drugog racunara |
| `log_prompt.py` | UserPromptSubmit | jedan red po upitu u `.claude/usage/prompts.jsonl` (vreme, sesija, faza, duzina, tekst); **nikad ne blokira** | sirovina za odeljak 7.6 |
| `prompt_router.py` | UserPromptSubmit | predlaze skillove i agente po recima upita | model ne zna koji skill postoji dok ga ne pozove |
| `require_skill.py` | PreToolUse Edit/Write | **odbija** izmenu dok skill za tu vrstu fajla nije ucitan | podsetnici se ignorisu kao pozadinska buka; odbijanje ne |
| `git_guard.py` | PreToolUse Bash/PowerShell | **odbija** force push, push na main, `git add -A`, `reset --hard` lokalno | craft-git pravila 1 i zamka sa `add -A` |
| `log_usage.py` | PostToolUse Agent/Skill | belezi koji agent/skill je pozvan i `totalTokens` (agent u pozadini ga nema, pa je `null`) | sirovina za `scripts/usage_report.py` |
| `verify_before_stop.py` | Stop | **odbija jednom** kraj rada ako je bilo izmena koda a testovi nisu pokrenuti; cita i transkripte podagenata, testovi vaze i kroz PowerShell | "trebalo bi da radi" nije dokaz |
| `scripts/sync.py` | SessionEnd | commit putanja pravila u repou plugina; bez remote-a ostaje lokalan | izmene pravila se ne gube |

`log_prompt.py` preskace poruke koje alat salje kao upit, a korisnik ih nije napisao
(`<task-notification>`).

## Kako `require_skill.py` zna da je skill ucitan

Cita transkript, ne zaglavlje agenta. U podagentu je `transcript_path` transkript roditelja, pa
cita svoj: `<sesija>/subagents/agent-<id>.jsonl`. Skill iz zaglavlja agenta tamo stoji kao red
`<command-name>skill</command-name>`. Podagent nema alat Skill, pa za njega vazi i `Read` datoteke
`SKILL.md`; poruka odbijanja navodi tacnu putanju. Ako transkript ne moze da se procita, ne odbija.

## Kako hook odbija

Na PreToolUse hook vraca JSON:

```json
{"hookSpecificOutput": {"hookEventName": "PreToolUse",
  "permissionDecision": "deny", "permissionDecisionReason": "..."}}
```

Razlog se vraca modelu, pa agent zna sta da uradi (npr. "ucitaj stack-django").

## Pravilo za nove hookove

Hook koji samo PODSECA vredi malo: posle trece poruke model ga ne cita.
Hook vredi kada **odbija** ili kada **belezi** nesto sto se kasnije meri.
