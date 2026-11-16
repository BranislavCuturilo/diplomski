# Spoljni efekti u testovima

## Spisak koji se proverava za svaki nov spoljni servis

| Servis | U test podesavanjima |
|---|---|
| skladiste fajlova (S3, FTP, mrezni disk) | lokalni privremeni folder |
| mejl | memorijski backend |
| SMS, push, chat | lazni klijent koji samo belezi |
| HTTP API treceg lica | mock + zastita koja baca gresku na pravi poziv |
| red poruka, zadaci u pozadini | sinhrono izvrsavanje u istom procesu |

## Kako se proverava da je zastita aktivna

Jedan test koji namerno pokusa pravi poziv i ocekuje gresku zastite.
Ako taj test prodje bez greske, zastita ne radi.

## Podprocesi

Test koji pokrece skriptu kao novi proces: novi proces NE nasledjuje mock-ove
iz testa. Zastita mora biti u konfiguraciji (promenljiva okruzenja), ne u kodu testa.
