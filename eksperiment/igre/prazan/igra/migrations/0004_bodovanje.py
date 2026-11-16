from django.db import migrations, models


class Migration(migrations.Migration):
    """Izmena klijenta u bodovanju. Partije koje vec postoje (zavrsene, sacuvane, podeljene ili
    zapocete) zadrzavaju prvo bodovanje; tek nove partije dobijaju drugo."""

    dependencies = [
        ("igra", "0003_kod_deljenja"),
    ]

    operations = [
        migrations.AddField(
            model_name="partija",
            name="bodovanje",
            field=models.PositiveSmallIntegerField(default=1),
        ),
        migrations.AlterField(
            model_name="partija",
            name="bodovanje",
            field=models.PositiveSmallIntegerField(default=2),
        ),
    ]
