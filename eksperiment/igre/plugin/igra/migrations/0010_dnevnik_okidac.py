# Plan 14.6: dnevnik moderatora je nepromenljiv i u bazi, ne samo u ZapisDnevnika.save(). QuerySet.update(),
# sirov SQL i ljuska zaobilaze save() (stack-django pravilo 2), pa UPDATE zaustavlja okidac.
# Okidaca na DELETE nema: blokirao bi flush u test_tok i komandu dnevnik_ocisti (365 dana, plan 14.4).
# Prepravka tabele igra_zapisdnevnika (kasniji AlterField na SQLite) brise okidac; to hvata test_okidac_postoji.
# Lista sa jednom naredbom: izvrsava se cela, bez deljenja po ";" unutar BEGIN ... END.
# Nazad: okidac nestaje; zapisi ostaju netaknuti.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('igra', '0009_moderator'),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                "CREATE TRIGGER igra_zapis_bez_izmene BEFORE UPDATE ON igra_zapisdnevnika "
                "BEGIN SELECT RAISE(ABORT, 'dnevnik se ne menja'); END;"
            ],
            reverse_sql=["DROP TRIGGER IF EXISTS igra_zapis_bez_izmene;"],
        ),
    ]
