"""Srpski tekst u bazi postaje kljuc (plan 12.4), sa povratkom.

Napred: Rezultat.ocena tekst -> kljuc; DeljeniRezultat.zavrsni: ocena i tihe_greske[].zadatak u kljuc,
lekcije[].tekst u oznaka, napomena se brise. Nazad: tacno obrnuto, napomena se vraca kao literal.
Vrednost koja je vec u ciljnom obliku se preskace.

Preslikavanja su literali, kao u 0002: kasnija izmena parametri.py ne menja istoriju. Ne nagadja:
neprepoznata vrednost baca NeprepoznatTekst sa spiskom model:id:vrednost pre ijednog upisa, a
migracija je jedna transakcija. Razvijalac odlucuje (rezultat_obrisi, deljeni_obrisi ili rucna
ispravka), pa ponovo migrate.
"""

from django.db import migrations

OCENE = {
    "одличан оркестратор": "odlican",
    "солидан": "solidan",
    "скуп учитељ": "skup",
    "пожар": "pozar",
}

ZADACI = {
    "Превод почетне стране": "prevod",
    "Шаблон листе и форме": "sablon",
    "CSS и прилагођавање телефону": "css",
    "CRUD прикази": "crud",
    "Модел података и миграција": "model",
    "Провера права приступа": "prava",
    "Аутоматски тестови": "testovi",
    "Безбедносна ревизија": "revizija",
}

LEKCIJE = {
    "Ако је грешка тиха, задатак остаје највишем разреду.": "tiha",
    "Најскупљи модел није увек најбољи избор.": "opus_lako",
    "Изнад нивоа high цена расте, а квалитет не.": "max",
    "Превише контекста квари резултат исто као премало.": "sve",
    "Више агената не значи јефтиније.": "pedeset",
}

NAPOMENA = (
    "Цене и нивои размишљања су стварни подаци; вероватноће, казне и поени "
    "су измишљени параметри игре."
)


class NeprepoznatTekst(ValueError):
    pass


def _obrnuto(preslikavanje):
    return {kljuc: tekst for tekst, kljuc in preslikavanje.items()}


class _Smer:
    """Jedan smer: izvor -> cilj; vrednost vec u cilju ostaje, sve ostalo je neprepoznato."""

    def __init__(self, napred):
        self.napred = napred
        self.ocene = OCENE if napred else _obrnuto(OCENE)
        self.zadaci = ZADACI if napred else _obrnuto(ZADACI)
        self.lekcije = LEKCIJE if napred else _obrnuto(LEKCIJE)
        self.neprepoznato = []

    def _vrednost(self, preslikavanje, vrednost, model, id_):
        if isinstance(vrednost, str) and vrednost in preslikavanje:
            return preslikavanje[vrednost]
        if isinstance(vrednost, str) and vrednost in preslikavanje.values():
            return vrednost  # vec u ciljnom obliku
        self.neprepoznato.append(f"{model}:{id_}:{vrednost!r}")
        return vrednost

    def ocena(self, vrednost, model, id_):
        return self._vrednost(self.ocene, vrednost, model, id_)

    def _lekcija(self, lekcija, id_):
        polje_izvora, polje_cilja = ("tekst", "oznaka") if self.napred else ("oznaka", "tekst")
        if isinstance(lekcija, dict) and set(lekcija) == {polje_cilja, "odeljak"}:
            vrednost = lekcija[polje_cilja]
            if isinstance(vrednost, str) and vrednost in self.lekcije.values():
                return lekcija  # vec u ciljnom obliku
        elif isinstance(lekcija, dict) and set(lekcija) == {polje_izvora, "odeljak"}:
            vrednost = lekcija[polje_izvora]
            if isinstance(vrednost, str) and vrednost in self.lekcije:
                return {polje_cilja: self.lekcije[vrednost], "odeljak": lekcija["odeljak"]}
        self.neprepoznato.append(f"DeljeniRezultat:{id_}:{lekcija!r}")
        return lekcija

    def zavrsni(self, zavrsni, id_):
        if not isinstance(zavrsni, dict):
            self.neprepoznato.append(f"DeljeniRezultat:{id_}:{zavrsni!r}")
            return zavrsni
        novo = dict(zavrsni)
        novo["ocena"] = self.ocena(zavrsni.get("ocena"), "DeljeniRezultat", id_)
        tihe = zavrsni.get("tihe_greske")
        lekcije = zavrsni.get("lekcije")
        if not isinstance(tihe, list) or not isinstance(lekcije, list):
            self.neprepoznato.append(f"DeljeniRezultat:{id_}:{zavrsni!r}")
            return zavrsni
        novo["tihe_greske"] = []
        for greska in tihe:
            if not isinstance(greska, dict):
                self.neprepoznato.append(f"DeljeniRezultat:{id_}:{greska!r}")
                novo["tihe_greske"].append(greska)
                continue
            greska = dict(greska)
            greska["zadatak"] = self._vrednost(self.zadaci, greska.get("zadatak"), "DeljeniRezultat", id_)
            novo["tihe_greske"].append(greska)
        novo["lekcije"] = [self._lekcija(lekcija, id_) for lekcija in lekcije]

        napomena = novo.pop("napomena", None)
        if napomena is not None and napomena != NAPOMENA:
            self.neprepoznato.append(f"DeljeniRezultat:{id_}:{napomena!r}")
        if not self.napred:
            novo["napomena"] = NAPOMENA  # poslednji kljuc, kao u snimku pre 0004
        return novo


def _prevedi(apps, schema_editor, napred):
    Rezultat = apps.get_model("igra", "Rezultat")
    DeljeniRezultat = apps.get_model("igra", "DeljeniRezultat")
    baza = schema_editor.connection.alias
    smer = _Smer(napred)

    # Prvo se sve izracuna u memoriji; upis tek ako je svaka vrednost prepoznata.
    rezultati = []
    for red in Rezultat.objects.using(baza).order_by("id"):
        nova = smer.ocena(red.ocena, "Rezultat", red.id)
        if nova != red.ocena:
            red.ocena = nova
            rezultati.append(red)
    deljeni = []
    for red in DeljeniRezultat.objects.using(baza).order_by("id"):
        novo = smer.zavrsni(red.zavrsni, red.id)
        if novo != red.zavrsni:
            red.zavrsni = novo
            deljeni.append(red)

    if smer.neprepoznato:
        raise NeprepoznatTekst(
            "Neprepoznata vrednost, nista nije promenjeno: " + "; ".join(smer.neprepoznato)
        )
    for red in rezultati:
        red.save(using=baza, update_fields=["ocena"])
    for red in deljeni:
        red.save(using=baza, update_fields=["zavrsni"])


def napred(apps, schema_editor):
    _prevedi(apps, schema_editor, napred=True)


def nazad(apps, schema_editor):
    _prevedi(apps, schema_editor, napred=False)


class Migration(migrations.Migration):

    dependencies = [
        ('igra', '0003_deljenirezultat'),
    ]

    operations = [
        migrations.RunPython(napred, nazad),
    ]
