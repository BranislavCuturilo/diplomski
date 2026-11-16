"""Rang lista, sifarnik nepodobnih imena, deljeni rezultat (plan 10.2, 11.2), dnevnik moderatora (14.6), brojac
neuspeha prijave (15.2) i prijave neprikladnih imena sa rang liste (odluka 2026-11-12).

Stanje partije ostaje u sesiji.
"""

from functools import reduce
from operator import or_

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection, models
from django.db.models import F, Q
from django.utils import timezone

from . import imena
from . import parametri as p


class RezultatQuerySet(models.QuerySet):
    """Svaki citac liste pocinje sa glavna() ili dana(dan): dnevni red nije na glavnoj listi, obican nije na listi dana."""

    def glavna(self):
        return self.filter(dan__isnull=True)

    def dana(self, dan):
        # dan je datetime.date (Europe/Belgrade); None nije dan, glavna lista ide samo kroz glavna().
        if dan is None:
            raise ValueError("dan je obavezan; glavna lista je glavna()")
        return self.filter(dan=dan)

    def po_rangu(self):
        # Vise poena iznad; kod jednakih raniji; id razresava isti trenutak. Isti redosled kao igra_rang_idx.
        return self.order_by("-poeni", "sacuvan", "id")

    def najboljih(self):
        return self.po_rangu()[: p.RANG_MESTA]

    def imena_po_partiji(self, partije):
        """partija -> ime, samo za partije koje su sacuvane na rang listi."""
        return dict(self.filter(partija__in=partije).values_list("partija", "ime"))


def proveri_ime(vrednost):
    if not imena.ime_ispravno(vrednost):
        raise ValidationError("Ime nije ispravno.", code="neispravno_ime")


class Rezultat(models.Model):
    # Izricito: bez DEFAULT_AUTO_FIELD check daje W042.
    id = models.BigAutoField(primary_key=True)
    ime = models.CharField(max_length=p.IME_MAKS, validators=[proveri_ime])
    poeni = models.PositiveSmallIntegerField()
    # Kljuc ocene iz stanje["rezultat"] (parametri.OCENE), nikad tekst: rang lista je na jeziku
    # posmatraca (plan 12.4). Najduzi kljuc ima 7 znakova; skup kljuceva cuva igra_ocena_kljuc.
    ocena = models.CharField(max_length=32)
    # Verzija pravila po kojoj je partija bodovana (motor.za_cuvanje, plan 13.1). Bez default-a:
    # zaboravljen upis je greska, ne tiha pogresna oznaka. Skup verzija cuva igra_pravila_poznata.
    pravila = models.PositiveSmallIntegerField()
    # UTC; default, ne auto_now_add, da test moze da zada trenutak.
    sacuvan = models.DateTimeField(default=timezone.now, editable=False)
    # sha256 semena (dnevna partija: sha256 svoje oznake, motor.oznaka_partije): "tacno jednom" i na nivou baze.
    # Nikad u odgovoru.
    partija = models.CharField(max_length=64, unique=True, editable=False)
    # Dan dnevnog izazova (Europe/Belgrade, dan pocetka partije); null = obicna igra, glavna lista. Dolazi samo iz
    # stanja (motor.za_cuvanje), nikad od klijenta.
    dan = models.DateField(null=True, blank=True, editable=False)

    objects = RezultatQuerySet.as_manager()

    class Meta:
        indexes = [
            models.Index(fields=["-poeni", "sacuvan", "id"], name="igra_rang_idx"),
            # Lista dana: dana(dan).po_rangu() cita samo redove tog dana, vec u redosledu liste.
            models.Index(fields=["dan", "-poeni", "sacuvan", "id"], name="igra_dan_rang_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(poeni__gte=p.MIN_POENI) & Q(poeni__lte=p.POCETNI_POENI),
                name="igra_poeni_opseg",
            ),
            models.CheckConstraint(condition=~Q(ime=""), name="igra_ime_nije_prazno"),
            # Tekst ne moze da udje ni kroz gresku ni kroz komandu (plan 12.4).
            models.CheckConstraint(
                condition=Q(ocena__in=[kljuc for _prag, kljuc in p.OCENE]),
                name="igra_ocena_kljuc",
            ),
            # Samo poznata verzija; oznaka "staro bodovanje" zavisi od broja verzije. Nabrajanje sa OR,
            # ne pravila__in: SQLite introspekcija Django 6.0 pada na ", " u CHECK (... IN (1, 2)) na kraju
            # tabele (0007). Ni opseg >= i <= (0007): tabela nije STRICT, pa kolona cuva i REAL, a 1.5 je
            # u opsegu (0008). Jednakost sa svakom verzijom odbija necele vrednosti, kao IN iz 0006.
            models.CheckConstraint(
                condition=reduce(or_, (Q(pravila=v) for v in range(p.PRAVILA_STARA, p.PRAVILA_TEKUCA + 1))),
                name="igra_pravila_poznata",
            ),
        ]


class NepodobnoImeQuerySet(models.QuerySet):
    def sadrzi(self, ime):
        return self.filter(kljuc=imena.kljuc_imena(ime)).exists()


class NepodobnoIme(models.Model):
    """Sifarnik; nikad ne ide klijentu. Menja se samo kroz management komande."""

    id = models.BigAutoField(primary_key=True)
    # Vec normalizovano kroz imena.kljuc_imena.
    kljuc = models.CharField(max_length=100, unique=True)

    objects = NepodobnoImeQuerySet.as_manager()

    class Meta:
        constraints = [
            models.CheckConstraint(condition=~Q(kljuc=""), name="igra_nepodobno_nije_prazno"),
        ]


class DeljeniRezultatQuerySet(models.QuerySet):
    # Granica je ista kao u DeljeniRezultat.istekao: u trenutku `istice` link vise ne vazi.
    def vazeci(self, sada):
        return self.filter(istice__gt=sada)

    def istekli(self, sada):
        return self.filter(istice__lte=sada)


class DeljeniRezultat(models.Model):
    """Snimak zavrsnog ekrana iza nasumicnog tokena (plan 11.2); nezavisan od rang liste."""

    id = models.BigAutoField(primary_key=True)
    # Jedino sto ide u URL; secrets u views, nezavisno od semena, partije i id-a.
    token = models.CharField(max_length=p.DELJENJE_TOKEN_DUZINA, unique=True, editable=False)
    # sha256 semena, isto kao Rezultat.partija: jednom po partiji i na nivou baze. Nikad u odgovoru.
    partija = models.CharField(max_length=64, unique=True, editable=False)
    # Snimak motor.za_deljenje; pri citanju ponovo prolazi belu listu motor.deljeni_prikaz.
    zavrsni = models.JSONField()
    # UTC; default, ne auto_now_add, da test moze da zada trenutak.
    nastao = models.DateTimeField(default=timezone.now, editable=False)
    # nastao + DELJENJE_DANA; racuna prikaz podeli.
    istice = models.DateTimeField(editable=False)

    objects = DeljeniRezultatQuerySet.as_manager()

    def istekao(self, sada):
        return sada >= self.istice

    class Meta:
        indexes = [models.Index(fields=["istice"], name="igra_deljeno_istice_idx")]
        constraints = [
            models.CheckConstraint(
                condition=Q(istice__gt=F("nastao")), name="igra_deljeno_istice_posle"
            ),
            models.CheckConstraint(condition=~Q(token=""), name="igra_deljeno_token_nije_prazan"),
        ]


# Radnje dnevnika moderatora (plan 14.6); baza cuva kljuc, tekst bira tekstovi.radnja po jeziku posmatraca.
REZULTAT_OBRISAN = "rezultat_obrisan"
LINK_OBRISAN = "link_obrisan"
MODERATOR_DODAT = "moderator_dodat"
MODERATOR_DEAKTIVIRAN = "moderator_deaktiviran"
MODERATOR_AKTIVIRAN = "moderator_aktiviran"
LOZINKA_POSTAVLJENA = "lozinka_postavljena"
LOZINKA_PROMENJENA = "lozinka_promenjena"
ULOGA_DODELJENA = "uloga_dodeljena"
ULOGA_ODUZETA = "uloga_oduzeta"
# Moderator je pregledao prijavljeno ime i ostavio rezultat na listi (brisanje.odbaci_prijave).
PRIJAVA_ODBACENA = "prijava_odbacena"
BRISANJA = (REZULTAT_OBRISAN, LINK_OBRISAN)
# Radnje nad redom rezultata ili linka: nose id reda, partiju i snimak reda.
RADNJE_NAD_REDOM = BRISANJA + (PRIJAVA_ODBACENA,)
RADNJE_NAD_NALOGOM = (
    MODERATOR_DODAT,
    MODERATOR_DEAKTIVIRAN,
    MODERATOR_AKTIVIRAN,
    LOZINKA_POSTAVLJENA,
    LOZINKA_PROMENJENA,
    ULOGA_DODELJENA,
    ULOGA_ODUZETA,
)
RADNJE = RADNJE_NAD_REDOM + RADNJE_NAD_NALOGOM


def _jedna_od(polje, vrednosti):
    # Nabrajanje sa OR, ne __in: ", " u CHECK lomi SQLite introspekciju Django 6.0 (vidi igra_pravila_poznata).
    return reduce(or_, (Q(**{polje: vrednost}) for vrednost in vrednosti))


class ZapisQuerySet(models.QuerySet):
    def najnoviji(self):
        # id razresava isti trenutak.
        return self.order_by("-kada", "-id")

    def obrisana(self, radnja, partija):
        """Da li je red ove partije obrisan (plan 14.4); ne zavisi od id-a reda, pa ni od brojaca tabele."""
        return self.filter(radnja=radnja, partija=partija).exists()

    def obrisan_red(self, radnja, broj):
        """Da li dnevnik ima brisanje reda sa ovim id-om (potvrda brisanja: "vec obrisano")."""
        return self.filter(radnja=radnja, red=broj).exists()

    def prijava_odbacena(self, partija):
        """Da li je moderator vec ostavio ime ove partije; po partiji, ne po id-u reda, kao obrisana()."""
        return self.filter(radnja=PRIJAVA_ODBACENA, partija=partija).exists()

    def upisi(self, **polja):
        """Jedini upis u dnevnik: save() ne zove full_clean (stack-django pravilo 1), pa ga zove ovde."""
        zapis = self.model(**polja)
        zapis.full_clean()
        zapis.save(force_insert=True)
        return zapis


class ZapisDnevnika(models.Model):
    """Ko je sta obrisao ili promenio i kada (plan 14.6). Nepromenljiv: save() i okidac 0010 odbijaju izmenu,
    okidac 0011 zamenu (INSERT sa id-jem postojeceg zapisa).

    `partija` (sha256 semena) sluzi samo garanciji iz 14.4 i tome da se ime koje je moderator ostavio ne prijavljuje
    ponovo; nikad ne ide u odgovor, sablon ni ispis.
    Token linka se ne cuva ni kao hes: dnevnik citaju svi moderatori.
    """

    id = models.BigAutoField(primary_key=True)
    # UTC; default, ne auto_now_add, da test moze da zada trenutak.
    kada = models.DateTimeField(default=timezone.now, editable=False)
    radnja = models.CharField(max_length=24, choices=[(r, r) for r in RADNJE])
    # null = komanda razvijaca. PROTECT: korisnik se nikad ne brise.
    ko = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    nad = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    # Id reda nad kojim je radnja, bez FK: obrisan red vise ne postoji.
    red = models.PositiveBigIntegerField(null=True, blank=True)
    partija = models.CharField(max_length=64, null=True, blank=True)
    # {ime, poeni, ocena, datum} za radnje nad redom, uz "dan" (ISO) za dnevni red; {"glavni": bool} za dodat i
    # deaktiviran; {} inace.
    snimak = models.JSONField(default=dict, blank=True)

    objects = ZapisQuerySet.as_manager()

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("dnevnik se ne menja")
        super().save(*args, **kwargs)

    class Meta:
        # Dodeljuju se direktno korisniku (user_permissions), bez grupa: flush brise grupe (plan 14.3).
        permissions = [
            ("moderira", "Brise rezultate i linkove i cita dnevnik"),
            ("upravlja_nalozima", "Upravlja nalozima moderatora"),
        ]
        # Bez add/change/delete/view: dnevnik se ne menja, a uloge nose samo dve dozvole iznad.
        default_permissions = ()
        indexes = [
            models.Index(fields=["-kada"], name="igra_dnevnik_kada_idx"),
            models.Index(fields=["radnja", "partija"], name="igra_dnevnik_partija_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=_jedna_od("radnja", RADNJE), name="igra_dnevnik_radnja_poznata"),
            # Radnja nad redom (brisanje, odbacena prijava) nosi id reda i partiju; radnja nad nalogom nijedno.
            models.CheckConstraint(
                condition=(
                    (_jedna_od("radnja", RADNJE_NAD_REDOM) & Q(red__isnull=False) & Q(partija__isnull=False))
                    | (~_jedna_od("radnja", RADNJE_NAD_REDOM) & Q(red__isnull=True) & Q(partija__isnull=True))
                ),
                name="igra_dnevnik_red_partija",
            ),
            # Radnja nad nalogom zna nad kim je; brisanje nije nad nalogom.
            models.CheckConstraint(
                condition=(
                    (_jedna_od("radnja", RADNJE_NAD_NALOGOM) & Q(nad__isnull=False))
                    | (~_jedna_od("radnja", RADNJE_NAD_NALOGOM) & Q(nad__isnull=True))
                ),
                name="igra_dnevnik_nalog_nad",
            ),
        ]


class NalogModeratora(models.Model):
    """Korisnik sa ovim redom i dozvolom igra.moderira je moderator (plan 14.3)."""

    # PROTECT: korisnik se nikad ne brise ni ne preimenuje.
    korisnik = models.OneToOneField(
        settings.AUTH_USER_MODEL, primary_key=True, on_delete=models.PROTECT, related_name="nalog_moderatora"
    )
    # Pocetnu lozinku (od glavnog ili komande) vlasnik menja pre svake druge strane.
    mora_promeniti = models.BooleanField(default=True)

    class Meta:
        default_permissions = ()


class PokusajPrijaveQuerySet(models.QuerySet):
    def rezervisi(self, kljuc, sada, rok):
        """Broji pokusaj jednom naredbom i vraca (redni broj u prozoru, kraj prozora).

        Upis i citanje su jedna naredba, pa i istovremeni zahtevi iz razlicitih procesa dobijaju svaki svoj redni
        broj: SQLite izvrsava jednu naredbu pisanja u jednom trenutku. Istekao red pocinje nov prozor (1, sada + rok);
        inace broj raste, a kraj prozora ostaje (blokiran pokusaj ga ne pomera). Usput brise istekle redove, pa tabela
        drzi samo pokusaje iz poslednjih `rok` sekundi.
        """
        self.filter(istice__lte=sada).delete()
        tabela = connection.ops.quote_name(self.model._meta.db_table)
        with connection.cursor() as kursor:
            # Sve desne strane SET citaju stari red, pa oba CASE vide isti istice.
            kursor.execute(
                f"INSERT INTO {tabela} (kljuc, broj, istice) VALUES (%s, 1, %s) "
                "ON CONFLICT (kljuc) DO UPDATE SET "
                "broj = CASE WHEN istice <= %s THEN 1 ELSE broj + 1 END, "
                "istice = CASE WHEN istice <= %s THEN excluded.istice ELSE istice END "
                "RETURNING broj, istice",
                [kljuc, sada + rok, sada, sada],
            )
            return kursor.fetchone()


class PokusajPrijave(models.Model):
    """Brojac neuspeha prijave po imenu, zajednicki svim procesima servera (plan 15.2, odluka P2).

    Pise ga samo igra/forme.py: rezervacija pre provere lozinke, neuspeh pomera kraj prozora, uspeh brise red.
    Ime se ne cuva, samo kljuc.
    """

    # sha256 normalizovanog imena (forme._kljuc), i za ime koje ne postoji; ime se ne cuva kao tekst.
    kljuc = models.CharField(max_length=64, primary_key=True)
    # Rezervisani pokusaji u tekucem prozoru, i blokirani; prvih PRIJAVA_POKUSAJA sme do provere lozinke.
    broj = models.PositiveIntegerField()
    # Kraj prozora u Unix sekundama, kao time.time() (sat koji testovi pomeraju); posle njega red kao da ne postoji.
    istice = models.FloatField()

    objects = PokusajPrijaveQuerySet.as_manager()

    class Meta:
        # Tabela nije za ljude: bez add/change/delete/view dozvola.
        default_permissions = ()
        indexes = [models.Index(fields=["istice"], name="igra_pokusaj_istice_idx")]
        constraints = [
            # Red nastaje tek prvim pokusajem; INSERT ... ON CONFLICT zaobilazi full_clean, pa pravilo cuva baza.
            models.CheckConstraint(condition=Q(broj__gte=1), name="igra_pokusaj_broj_pozitivan"),
        ]


class PrijavaImenaQuerySet(models.QuerySet):
    def minulih_dana(self, danas):
        """Prijave dnevnih redova ranijih dana: te liste vise nisu na ekranu, pa ni u pregledu moderatora."""
        return self.filter(rezultat__dan__lt=danas)


class PrijavaImena(models.Model):
    """Prijava neprikladnog imena sa rang liste (odluka 2026-11-12): jedna po rezultatu i sesiji igraca.

    Upisuje je samo views.prijavi; brise je brisanje.py, kada moderator obrise rezultat ili ostavi ime. O imenu
    odlucuje moderator: prijava sama nista ne sakriva. Nikad ne ide klijentu.
    """

    id = models.BigAutoField(primary_key=True)
    # CASCADE: prijava vazi samo dok red postoji, a brisanje reda vec stoji u dnevniku. Bez svog indeksa: upite po
    # rezultatu sluzi indeks ogranicenja igra_prijava_jednom_po_sesiji (rezultat je prva kolona).
    rezultat = models.ForeignKey(Rezultat, on_delete=models.CASCADE, related_name="prijave", db_index=False)
    # HMAC kljuca sesije (views._sesija_prijave), i na nivou baze "jednom po sesiji i redu". Kljuc sesije se ne cuva.
    sesija = models.CharField(max_length=64, editable=False)
    # UTC; default, ne auto_now_add, da test moze da zada trenutak.
    kada = models.DateTimeField(default=timezone.now, editable=False)

    objects = PrijavaImenaQuerySet.as_manager()

    class Meta:
        # Tabela nije za ljude: bez add/change/delete/view dozvola.
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(fields=["rezultat", "sesija"], name="igra_prijava_jednom_po_sesiji"),
            models.CheckConstraint(condition=~Q(sesija=""), name="igra_prijava_sesija_nije_prazna"),
        ]


# Vrsta zavrsene partije u statistici moderatora; isti kljucevi kao views.SESIJA.
OBICNA = "obicna"
DNEVNA = "dnevna"
VRSTE_PARTIJE = (OBICNA, DNEVNA)


class ZavrsenaPartijaQuerySet(models.QuerySet):
    def pre(self, dan):
        """Redovi pre ovog dana: statistika ih vise ne prikazuje (views._zabelezi_zavrsenu ih brise usput)."""
        return self.filter(dan__lt=dan)

    def po_danu(self, prvi, poslednji):
        """Jedan upit: dan -> ukupno, obicnih, dnevnih i prosek poena, za dane od prvi do poslednji ukljucivo.

        Dan bez partija nema red; prikaz ga dopunjuje nulom.
        """
        return {
            red["dan"]: red
            for red in self.filter(dan__gte=prvi, dan__lte=poslednji)
            .values("dan")
            .annotate(
                ukupno=models.Count("id"),
                obicnih=models.Count("id", filter=Q(vrsta=OBICNA)),
                dnevnih=models.Count("id", filter=Q(vrsta=DNEVNA)),
                prosek=models.Avg("poeni"),
            )
            .order_by()
        }


class ZavrsenaPartija(models.Model):
    """Partija koja je stigla do zavrsnog ekrana, obicna ili dnevna (statistika moderatora, zahtev 2026-11-12).

    Upisuje je samo views.potez, u istoj transakciji sa potezom koji zavrsava partiju, pa je jedna partija tacno
    jedan red. Samo ono sto statistika broji: bez imena, sesije, semena, oznake i hesa partije.
    """

    id = models.BigAutoField(primary_key=True)
    # Lokalni dan zavrsetka (Europe/Belgrade, views._danas); za dnevnu partiju posle ponoci dan zavrsetka, ne pocetka.
    dan = models.DateField(editable=False)
    vrsta = models.CharField(max_length=6, choices=[(v, v) for v in VRSTE_PARTIJE], editable=False)
    poeni = models.PositiveSmallIntegerField(editable=False)

    objects = ZavrsenaPartijaQuerySet.as_manager()

    class Meta:
        # Tabela nije za ljude: bez add/change/delete/view dozvola.
        default_permissions = ()
        indexes = [models.Index(fields=["dan"], name="igra_zavrsena_dan_idx")]
        constraints = [
            # Nabrajanje sa OR, ne __in (vidi igra_pravila_poznata).
            models.CheckConstraint(condition=_jedna_od("vrsta", VRSTE_PARTIJE), name="igra_zavrsena_vrsta_poznata"),
            models.CheckConstraint(
                condition=Q(poeni__gte=p.MIN_POENI) & Q(poeni__lte=p.POCETNI_POENI),
                name="igra_zavrsena_poeni_opseg",
            ),
        ]
