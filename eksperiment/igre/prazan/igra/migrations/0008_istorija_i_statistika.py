"""Partija pamti igraca (hes kolacica), vreme zavrsetka i poene.

Postojece zavrsene partije dobijaju poene po svom bodovanju, a za vreme zavrsetka vreme pocetka
(partija traje nekoliko minuta). Igrac im ostaje prazan, pa ne ulaze ni u ciju istoriju, ali ulaze
u statistiku moderatora.
"""

from django.db import migrations, models
from django.db.models import Count


def popuni_zavrsene(apps, schema_editor):
    # Cista pravila (bez Django-a); racunaju poene isto kao server.
    from igra import parametri as p
    from igra import pravila

    Partija = apps.get_model("igra", "Partija")
    zavrsene = Partija.objects.annotate(broj=Count("potezi")).filter(broj__gte=p.BROJ_KRUGOVA)
    for partija in zavrsene.iterator():
        potezi = [
            pravila.Izbori(potez.model, potez.nivo, potez.kontekst, potez.podela)
            for potez in partija.potezi.order_by("krug")
        ]
        rezultat = pravila.konacni_rezultat(partija.seme, potezi, partija.bodovanje)
        Partija.objects.filter(pk=partija.pk).update(zavrsena=partija.napravljena, poeni=rezultat.poeni)


class Migration(migrations.Migration):

    dependencies = [
        ("igra", "0007_prijava_imena"),
    ]

    operations = [
        migrations.AddField(
            model_name="partija",
            name="igrac",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="partija",
            name="zavrsena",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="partija",
            name="poeni",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name="partija",
            index=models.Index(fields=["igrac", "-zavrsena"], name="partije_igraca"),
        ),
        migrations.AddIndex(
            model_name="partija",
            index=models.Index(fields=["zavrsena"], name="zavrsene_partije"),
        ),
        migrations.RunPython(popuni_zavrsene, migrations.RunPython.noop),
    ]
