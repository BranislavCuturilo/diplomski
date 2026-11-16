---
name: django-ssr-bootstrap
description: >
  Spoj Django sablona koje iscrtava server i Bootstrap 5: greske formi, poruke,
  CSRF, prenos podataka u JavaScript. Ucitaj kada projekat koristi Django sablone
  I Bootstrap, pre izmene sablona sa formom ili skriptom. Okidaci: "greska forme
  se ne vidi", "poruka posle cuvanja", "CSRF failed", "podaci u JS".
---

# django-ssr-bootstrap

## Tri pravila koja se nikad ne preskacu

1. **Greska Django forme mora dobiti Bootstrap klase.** `{{ form.as_p }}` daje
   gresku koju Bootstrap ne stilizuje. Svako polje: `.form-control` +
   `.is-invalid` kada `field.errors`, i `.invalid-feedback` odmah ispod polja.
   Jedan zajednicki include (`_field.html`), ne rucno po formi.

2. **Podaci iz Django-a u JavaScript idu kroz `json_script`**, nikad
   `var x = {{ data|safe }}`: `|safe` iz korisnickog unosa = XSS.
   ```django
   {{ notes|json_script:"notes-data" }}
   <script>const notes = JSON.parse(document.getElementById("notes-data").textContent);</script>
   ```

3. **Svaki `<form method="post">` ima `{% csrf_token %}`**, i svaki `fetch` POST
   salje zaglavlje `X-CSRFToken` procitano iz kolacica. Bez toga 403 bez jasne poruke.

## Ostalo

- Django `messages` → Bootstrap `.alert`: mapiranje `MESSAGE_TAGS = {messages.ERROR: "danger"}`;
  Django kaze `error`, Bootstrap ocekuje `danger`.
- Brisanje ide kroz POST formu (modal sa potvrdom), nikad kroz link.
- **`fetch` cita odgovor kao tekst, pa tek onda kao JSON.** 403 i 500 su HTML strane, pa
  `r.json()` puca i na ekran ne stigne nista: "kliknem i nista se ne desi". Za svaki odgovor
  koji nije OK ili nije JSON prikazi poruku.
  *Poreklo: sistem brain, stvaran projekat, isti kvar u dva modula.*
- **`json_script` dobija Python objekat, nikad `json.dumps`.** Dvostruko kodiranje ne prijavljuje
  gresku: `JSON.parse` vrati string, a prvi poziv metode pukne. Testom parsiraj stvarni `<script>`
  sa renderovane strane i zahtevaj `dict` ili `list`; context to ne vidi.
  *Poreklo: sistem brain, stranica je iscrtala kontrole i nista drugo.*
- **Broj koji sablon ispisuje kao PODATAK ide kroz `{% localize off %}` ili `|unlocalize`.** Pod
  srpskim jezikom `{{ x }}` daje `1,5`, pa `data-` atribut, URL ili `var x = {{ x }}` nose pogresnu
  vrednost ili sintaksnu gresku. Test prvo mora da dokaze da je jezik stvarno aktivan.
  *Poreklo: sistem brain, kvar se ponovio na dva mesta; zarez proveren 2026-11-09 na Django 6.0.*
