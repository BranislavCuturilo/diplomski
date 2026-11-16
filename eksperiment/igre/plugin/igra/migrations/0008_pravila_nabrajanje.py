# Ispravka 0007 (nalaz revizije 2026-11-11): opseg "pravila" >= 1 AND "pravila" <= 2 nije isti skup kao
# IN (1, 2) iz 0006. Tabela nije STRICT, pa kolona INTEGER afiniteta cuva i REAL: sirov INSERT 1.5, '1.5',
# 1.999999 i ORM update(pravila=Value(1.5)) ili F("pravila") + 0.5 prolaze opseg, a IN ih odbija. Kroz
# aplikaciju nedostizno, ali sa takvim redom "migrate igra 0006" pada.
# 0007 je primenjena na pravu bazu, pa se ne menja; ova migracija pise CHECK nabrajanjem
# ("pravila" = 1 OR "pravila" = 2): odbija isto sto i IN iz 0006 (i 0, 3, NULL kroz NOT NULL), a '1' i '2.0'
# afinitet pretvara u INTEGER pre provere, kao i do sada. Bez ", " u tekstu, pa introspekcija SQLite-a
# Django 6.0 (_get_column_collations) radi, kao posle 0007.
#
# Ime ostaje igra_pravila_poznata; prvo Remove pa Add, kao u 0007. Na SQLite je cela migracija jedna
# transakcija, pa tabela nije bez provere. Svaka operacija prepravlja tabelu (kopija redova); tabela ima
# desetine redova. Red sa necelom verzijom bi pao na kopiji (IntegrityError) i migracija se ne bi primenila;
# aplikacija takav red ne upisuje.
# Verzije su literal, kao u 0005-0007: kasnija izmena parametri.PRAVILA_TEKUCA ne menja istoriju.
# Nazad: vraca opseg iz 0007; redovi i verzije ostaju netaknuti.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('igra', '0007_pravila_opseg'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='rezultat',
            name='igra_pravila_poznata',
        ),
        migrations.AddConstraint(
            model_name='rezultat',
            constraint=models.CheckConstraint(condition=models.Q(('pravila', 1), ('pravila', 2), _connector='OR'), name='igra_pravila_poznata'),
        ),
    ]
