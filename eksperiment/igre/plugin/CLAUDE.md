# Igra Orkestrator

Edukativna igra u browseru. Pravila igre: skill `projekat-domen`; standard koda: `projekat-standardi`.
`MVP.md`, ako postoji, opisuje proizvod; pravila i brojevi u njemu isti su kao u `projekat-domen`.
Radi se pluginom diplomski: agenti `diplomski:*`, slojevi 1-3 iz plugina, sloj projekta u `.claude/skills/`.
Stek: Django, SQLite, cist JavaScript, Bootstrap 5. Skill `django-mysql` se ovde ne koristi; `django-nginx-docker` vazi za `settings_prod.py`, `Dockerfile`, `compose.yaml` i `deploy/` (javna isporuka, odluka 2026-11-11).

## Raspored

Svaka faza pocinje upisom: `python "C:/poredjenje-orkestrator/plugin/config/skills/diplomski/scripts/faza.py" <ime faze>`.
Pre prvog pokretanja agenta ucitaj skill `craft-delegiranje`.

| Faza | Ko | Sta |
|---|---|---|
| planiranje | glavna sesija; `planer` samo za pun aparat | kratak plan i najvise jedan dijalog pitanja |
| implementacija | glavna sesija; talasi (`backend-senior`, `frontend-medior`, `devops`) samo za pun aparat | kod, sabloni, skripta, prevod i testovi; Docker, Nginx i DEPLOY.md |
| kontrolni skup | `qa` kada izmena menja tok kroz pregledac; `security` kada dira rizik; u istoj poruci | testovi i jedan tok kroz pregledac; bezbednosna revizija |
| poruka klijentu | glavna sesija | kratak izvestaj, odluke za potvrdu, niski nalazi |

Laki put je podrazumevan za izmenu postojece aplikacije do oko 15 datoteka; pun aparat (`planer`,
talasi, `translate`) samo za novu aplikaciju, ceo novi jezik ili vecu izmenu (skill `craft-delegiranje`).
Upit sa 3 ili vise nezavisnih zadataka ide u paralelni rezim: mapa projekta, radnici u worktree-ovima,
spajanje u glavnoj sesiji i jedna kontrola nad celinom.
Na doradu vracaju samo visoki i srednji nalazi; najvise jedna ponovna provera po upitu.

Merenje pise u `.claude/usage/`, koje git ignorise (upiti su pun tekst).
