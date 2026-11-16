from django.conf import settings
from django.db import models


class Partija(models.Model):
    """Cuva samo seme. Stanje se uvek racuna iz semena i poteza."""

    seme = models.CharField(max_length=32)
    napravljena = models.DateTimeField(auto_now_add=True)
    # Nasumican kod za javni link rezultata. Nastaje tek kada je partija zavrsena.
    kod = models.CharField(max_length=32, unique=True, null=True, blank=True)
    # Verzija bodovanja (parametri.BODOVANJA) vazeca kada je partija pocela. Ne menja se kasnije,
    # pa stari zavrsni ekrani i podeljeni linkovi i dalje pokazuju iste poene.
    bodovanje = models.PositiveSmallIntegerField(default=2)
    # Dan dnevnog izazova (po beogradskom vremenu) ili prazno za obicnu igru. Rezultat dnevne partije
    # ostaje na listi dana u kome je partija poceta, i kada se sacuva posle ponoci.
    dan = models.DateField(null=True, blank=True)
    # Hes kolacica igrac (servis.hes_igraca): ko je igrao, bez naloga. Sam kolacic se ne cuva, pa se
    # iz baze ne moze preuzeti tudja istorija partija. Prazno: partija pre ove izmene.
    igrac = models.CharField(max_length=64, blank=True, default="")
    # Upisuju se sa poslednjim potezom, u istoj transakciji. Poeni su po bodovanju partije, pa se
    # posle ne menjaju; istorija igraca i statistika moderatora ih citaju bez ponovnog racuna.
    zavrsena = models.DateTimeField(null=True, blank=True)
    poeni = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["igrac", "-zavrsena"], name="partije_igraca"),
            models.Index(fields=["zavrsena"], name="zavrsene_partije"),
        ]


class Rezultat(models.Model):
    """Sacuvan rezultat zavrsene partije. Jedna partija ima najvise jedan rezultat."""

    partija = models.OneToOneField(Partija, on_delete=models.CASCADE, related_name="rezultat")
    ime = models.CharField(max_length=30)
    poeni = models.PositiveSmallIntegerField()
    ocena = models.CharField(max_length=40)
    sacuvan = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-poeni", "sacuvan", "pk"]
        indexes = [models.Index(fields=["-poeni", "sacuvan"], name="rang_lista")]


class PrijavaImena(models.Model):
    """Igrac je prijavio ime sa rang liste kao neprikladno. Jedan rezultat ima najvise jednu prijavu.

    Ne pamti se ko prijavljuje (igraci su bez naloga), pa ponovljena prijava istog rezultata ne pravi
    novi red. Kada moderator obrise rezultat, prijava nestaje sa njim.
    """

    rezultat = models.OneToOneField(Rezultat, on_delete=models.CASCADE, related_name="prijava_imena")
    podneta = models.DateTimeField(auto_now_add=True)
    # Moderator je pregledao ime i zadrzao rezultat. Takav rezultat se vise ne moze prijaviti.
    resena = models.BooleanField(default=False)

    class Meta:
        ordering = ["podneta", "pk"]


class Dogadjaj(models.Model):
    """Dnevnik moderacije: ko je sta uradio i kada. Upis se nikad ne menja ni ne brise.

    Uz brisanje se pamti i sta je obrisano (ime, poeni, kod), jer samog rezultata ili linka vise nema.
    """

    OBRISAN_REZULTAT = "rezultat"
    OBRISAN_LINK = "link"
    # Moderator je pregledao prijavljeno ime i rezultat je ostao na rang listi.
    ZADRZAN_REZULTAT = "zadrzan"
    DODAT_MODERATOR = "dodat"
    ISKLJUCEN_MODERATOR = "iskljucen"
    UKLJUCEN_MODERATOR = "ukljucen"

    vreme = models.DateTimeField(auto_now_add=True)
    # Prazno: moderatora je napravio razvijalac komandom.
    moderator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, related_name="+"
    )
    vrsta = models.CharField(max_length=20)
    partija = models.ForeignKey(Partija, on_delete=models.PROTECT, null=True, related_name="dogadjaji")
    ime_igraca = models.CharField(max_length=30, blank=True)
    poeni = models.PositiveSmallIntegerField(null=True)
    kod = models.CharField(max_length=32, blank=True)
    nalog = models.CharField(max_length=150, blank=True)

    class Meta:
        ordering = ["-vreme", "-pk"]
        permissions = [("moderira", "Moze da brise rezultate i linkove i dodaje moderatore")]
        indexes = [models.Index(fields=["partija", "vrsta"], name="dogadjaj_partije")]


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
