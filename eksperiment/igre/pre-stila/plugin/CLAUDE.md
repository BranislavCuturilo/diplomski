# Igra Orkestrator

Edukativna igra u browseru. Pravila igre: skill `projekat-domen`; standard koda: `projekat-standardi`.
`MVP.md`, ako postoji, opisuje proizvod; pravila i brojevi u njemu isti su kao u `projekat-domen`.
Radi se pluginom diplomski: agenti `diplomski:*`, slojevi 1-3 iz plugina, sloj projekta u `.claude/skills/`.
Stek: Django, SQLite, cist JavaScript, Bootstrap 5. Skillovi `django-mysql` i `django-nginx-docker` se ovde ne koriste.

## Raspored

Svaka faza pocinje upisom: `python "C:/poredjenje-orkestrator/plugin/config/skills/diplomski/scripts/faza.py" <ime faze>`.
Pre prvog pokretanja agenta ucitaj skill `craft-delegiranje`.

| Faza | Ko | Sta |
|---|---|---|
| planiranje | `planer` | plan i pitanja |
| delegiranje | glavna sesija | deli plan na talase |
| implementacija | `backend-senior`; `frontend-medior` | motor, parametri i prikazi; sablon i skripta |
| kontrolni skup | `qa`; `security`, u jednoj poruci | testovi i pregledac; bezbednosna revizija |
| poruka klijentu | glavna sesija | kratak izvestaj |

Kontrolni skup rade podagenti, svaki u svom kontekstu, pa nova sesija nije potrebna.
Nalaz koji trazi ispravku vraca fazu na `implementacija`, pa ponovo `kontrolni skup`.

Merenje pise u `.claude/usage/`, koje git ignorise (upiti su pun tekst).
