# Django testovi

- **`TransactionTestCase` brise (flush) sve tabele** posle svakog testa. Na pogresnoj
  bazi to je brisanje produkcije; vidi craft-testing pravilo 1. Koristi `TestCase`
  osim kad test mora da vidi commit.
- **`settings_test.py` izricito gasi:** `STORAGES` (fajlovi u temp folder),
  `EMAIL_BACKEND` (locmem je podrazumevan samo u test runner-u, ne u skriptama),
  `CELERY_TASK_ALWAYS_EAGER = True`, i API klijente.
- **`setUpTestData` deli objekte izmedju testova klase**; test koji ih menja u
  memoriji (ne u bazi) moze da utice na sledeci. Menjaj kopiju ili `refresh_from_db()`.
- **Test ovlascenja ima DVA korisnika.** Za svaki endpoint sa pk-om:
  vlasnik 200, drugi 404, neprijavljen redirect na login.
- **`assertContains(response, text)`** proverava i status 200; `assertIn(text, response.content)` ne.
- Brojanje upita: `with self.assertNumQueries(n):` na listama, da N+1 padne u testu.
