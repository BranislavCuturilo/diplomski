from django.db import models


class Partija(models.Model):
    """Cuva samo seme. Stanje se uvek racuna iz semena i poteza."""

    seme = models.CharField(max_length=32)
    napravljena = models.DateTimeField(auto_now_add=True)


class Potez(models.Model):
    partija = models.ForeignKey(Partija, on_delete=models.CASCADE, related_name="potezi")
    krug = models.PositiveSmallIntegerField()
    model = models.CharField(max_length=20)
    nivo = models.CharField(max_length=20)
    kontekst = models.CharField(max_length=20)
    podela = models.CharField(max_length=20)

    class Meta:
        ordering = ["krug"]
        constraints = [
            models.UniqueConstraint(fields=["partija", "krug"], name="jedan_potez_po_krugu"),
        ]
