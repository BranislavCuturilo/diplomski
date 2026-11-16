# Plan 13.1 i 13.7: verzija pravila bodovanja na redu rang liste.
#
# Postojeci redovi su bodovani po verziji 1 (pre 2026-11-11), pa dobijaju 1. default=1 sluzi samo
# ovom upisu (preserve_default=False): model nema default, pa zaboravljen upis pada, a ne dobija
# tiho pogresnu verziju. SQLite i NOT NULL kolonu sa default-om dodaje prepravkom tabele, kao i
# AlterField u postupku u tri koraka; tabela ima desetine redova.
# Spisak verzija u CHECK-u je literal, kao u 0005: kasnija izmena parametri.KAZNE ne menja istoriju.
# Nazad: kolona nestaje; ponovni migrate oznacava sve redove kao 1, i redove verzije 2 (plan 13.9).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('igra', '0005_rezultat_igra_ocena_kljuc'),
    ]

    operations = [
        migrations.AddField(
            model_name='rezultat',
            name='pravila',
            field=models.PositiveSmallIntegerField(default=1),
            preserve_default=False,
        ),
        migrations.AddConstraint(
            model_name='rezultat',
            constraint=models.CheckConstraint(condition=models.Q(('pravila__in', [1, 2])), name='igra_pravila_poznata'),
        ),
    ]
