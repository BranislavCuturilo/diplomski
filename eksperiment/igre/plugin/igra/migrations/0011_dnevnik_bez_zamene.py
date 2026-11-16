# Revizija 2026-11-11: sirov INSERT OR REPLACE sa id-jem postojeceg zapisa brise stari red i upisuje nov, a
# okidac 0010 (BEFORE UPDATE) to ne vidi: zamena nije UPDATE. Ovaj okidac odbija INSERT ciji id vec postoji, pre
# provere ogranicenja, pa ni REPLACE ni IGNORE ne prolaze.
# Obican upis (ORM, bez id-a: NEW.id nije id postojeceg reda) prolazi. Okidaca na DELETE i dalje nema, pa flush u
# test_tok i komanda dnevnik_ocisti rade. Prepravka tabele brise i ovaj okidac; hvata je test_okidac_postoji.
# Lista sa jednom naredbom: izvrsava se cela, bez deljenja po ";" unutar BEGIN ... END.
# Nazad: okidac nestaje; zapisi ostaju netaknuti.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('igra', '0010_dnevnik_okidac'),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                "CREATE TRIGGER igra_zapis_bez_zamene BEFORE INSERT ON igra_zapisdnevnika "
                "WHEN EXISTS (SELECT 1 FROM igra_zapisdnevnika WHERE id = NEW.id) "
                "BEGIN SELECT RAISE(ABORT, 'dnevnik se ne menja'); END;"
            ],
            reverse_sql=["DROP TRIGGER IF EXISTS igra_zapis_bez_zamene;"],
        ),
    ]
