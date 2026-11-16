# Ispravka 0006 (nalaz qa 2026-11-11): CHECK "pravila" IN (1, 2) je poslednji u CREATE TABLE, a Django 6.0
# SQLite introspekcija (_get_column_collations) sece tekst tabele po ", " i pada (IndexError) na komadu "2".
# Padaju get_table_description, get_constraints i inspectdb, pa i buduca izmena seme koja trazi imena
# ogranicenja. 0006 je vec primenjena, pa se ne menja; ova migracija zamenjuje isti CHECK opsegom
# 1 <= pravila <= 2, koji ne sadrzi ", ".
# Opseg NIJE isti skup kao IN (1, 2) (nalaz revizije 2026-11-11): tabela nije STRICT, pa kolona cuva i
# REAL, a 1.5, '1.5' i 1.999999 su u opsegu. Ispravlja 0008; ova migracija je primenjena, pa se menja samo
# ovaj komentar.
#
# Ime ostaje igra_pravila_poznata: namera (samo poznata verzija) je ista, menja se oblik izraza.
# Zato prvo Remove pa Add; na SQLite je cela migracija jedna transakcija, pa tabela nije bez provere.
# Svaka operacija prepravlja tabelu (kopija redova); tabela ima desetine redova.
# Granice su literal, kao u 0005 i 0006: kasnija izmena parametri.PRAVILA_TEKUCA ne menja istoriju.
# Nazad: vraca IN (1, 2) iz 0006 (sa njim i kvar introspekcije); redovi i verzije ostaju netaknuti.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('igra', '0006_rezultat_pravila'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='rezultat',
            name='igra_pravila_poznata',
        ),
        migrations.AddConstraint(
            model_name='rezultat',
            constraint=models.CheckConstraint(condition=models.Q(('pravila__gte', 1), ('pravila__lte', 2)), name='igra_pravila_poznata'),
        ),
    ]
