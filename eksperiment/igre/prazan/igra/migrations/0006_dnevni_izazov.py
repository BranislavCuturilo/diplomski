from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('igra', '0005_moderacija'),
    ]

    operations = [
        migrations.AddField(
            model_name='partija',
            name='dan',
            field=models.DateField(blank=True, null=True),
        ),
    ]
