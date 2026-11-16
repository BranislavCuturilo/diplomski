import json
import re
import secrets
import unicodedata
from datetime import date, datetime, time, timedelta
from datetime import timezone as datetime_timezone

from django.conf import settings
from django.core.exceptions import RequestDataTooBig, ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpResponseBadRequest, JsonResponse, UnreadablePostError
from django.http.request import RawPostDataException
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.cache import patch_vary_headers
from django.utils.crypto import salted_hmac
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST, require_safe
from django.views.i18n import set_language

from . import motor
from . import parametri as p
from . import tekstovi
from .models import (
    LINK_OBRISAN,
    REZULTAT_OBRISAN,
    DeljeniRezultat,
    NepodobnoIme,
    PrijavaImena,
    Rezultat,
    ZapisDnevnika,
    ZavrsenaPartija,
    proveri_ime,
)

MAKS_VELICINA_TELA = 2 * 1024
KLJUCEVI_ZAHTEVA = {"krug", "izbori"}
KLJUCEVI_CUVANJA = {"ime"}
KLJUCEVI_PRIJAVE = {"red"}
# Oblik secrets.token_urlsafe(DELJENJE_TOKEN_BAJTOVA); proverava se sa fullmatch, jer "$" propusta zavrsni "\n".
OBLIK_TOKENA = re.compile(rf"[A-Za-z0-9_-]{{{p.DELJENJE_TOKEN_DUZINA}}}")
# Oblik javne oznake reda (_oznaka_reda): mala heksadecimalna slova; i ovde fullmatch.
OBLIK_OZNAKE_REDA = re.compile(rf"[0-9a-f]{{{p.PRIJAVA_OZNAKA_DUZINA}}}")
# Brojevi iz parametri za {% blocktranslate count %} u sablonu igre (plan 12.5).
BROJEVI = {"rang_mesta": p.RANG_MESTA, "ime_maks": p.IME_MAKS}
# Vrsta partije -> kljuc sesije. Vrstu zadaje samo URLconf (kwargs u path), nikad klijent.
SESIJA = {"obicna": "igra", "dnevna": "dnevna"}
# Imena ruta po vrsti; "strana" je GET strana igre te vrste. Dnevna nema "nova" (jednom po sesiji i danu).
# "prijavi" je ista ruta na obe strane: prijava imena je o redu liste, ne o partiji.
RUTE = {
    "obicna": {
        "potez": "potez", "sacuvaj": "sacuvaj", "podeli": "podeli", "prijavi": "prijavi", "strana": "pocetna",
    },
    "dnevna": {
        "potez": "dnevni_potez", "sacuvaj": "dnevni_sacuvaj", "podeli": "dnevni_podeli", "prijavi": "prijavi",
        "strana": "dnevni",
    },
}
# Kontekst salted_hmac: seme dana zavisi od SECRET_KEY, pa se iz datuma ne izracunava.
SO_DNEVNOG_SEMENA = "igra.dnevni_izazov"
# Konteksti salted_hmac za prijavu imena: javna oznaka reda i trag sesije u tabeli prijava. Razliciti, pa se jedno
# iz drugog ne izvodi; oba zavise od SECRET_KEY.
SO_OZNAKE_REDA = "igra.prijava_imena.red"
SO_SESIJE_PRIJAVE = "igra.prijava_imena.sesija"


def _nova_igra():
    return motor.nova_igra(secrets.token_hex(16))


def _danas():
    """Danasnji dan u TIME_ZONE (Europe/Belgrade); jedino mesto koje cita dan, testovi ga zamenjuju."""
    return timezone.localdate()


def _dnevno_seme(dan):
    # Isto za sve igrace istog dana; tajno jer zavisi od SECRET_KEY. Nikad u HTML, JSON ni kolacic.
    return salted_hmac(SO_DNEVNOG_SEMENA, dan.isoformat(), algorithm="sha256").hexdigest()


def _nova_dnevna(dan):
    # oznaka: 128 bita iz OS izvora, jedinstvena po partiji; iz nje je hes partije (motor.oznaka_partije).
    return motor.nova_igra(_dnevno_seme(dan), dan=dan.isoformat(), oznaka=secrets.token_hex(16))


def _datum_dana(dan):
    """datetime.date u formatu aktivnog jezika. Podne u TIME_ZONE: localtime u tekstovi.datum ne pomera dan."""
    return tekstovi.datum(timezone.make_aware(datetime.combine(dan, time(12))))


def _stanje(request, vrsta="obicna"):
    """Stanje iz sesije; stara zavrsena partija dobija kljuceve umesto teksta (plan 12.4).

    Sesiju ne upisuje: nadogradjeno stanje se upisuje samo tamo gde prikaz ionako pise sesiju.
    """
    return motor.nadogradi(request.session.get(SESIJA[vrsta]))


def _dan_stanja(stanje):
    # Dan dnevne partije kao date; None za obicnu ili bez stanja.
    dan = None if stanje is None else motor.dan_partije(stanje)
    return None if dan is None else date.fromisoformat(dan)


def _lista(vrsta, stanje):
    """Lista uz odgovor prikaza: glavna za obicnu igru; za dnevnu lista dana partije (posle ponoci jucerasnja,
    jer tamo ide i njen red), bez stanja danasnja."""
    if vrsta == "obicna":
        return Rezultat.objects.glavna()
    return Rezultat.objects.dana(_dan_stanja(stanje) or _danas())


def _podrzan_jezik(kod):
    # Tacno kljuc iz LANGUAGES ("sr", "en"); "EN", "en-us", "de" i None nisu.
    return kod in dict(settings.LANGUAGES)


def _jezik_upita(request):
    """?jezik= na deljenoj strani (J1): samo kod iz LANGUAGES, inace None (zanemaruje se, ne ispisuje)."""
    jezik = request.GET.get("jezik")
    return jezik if _podrzan_jezik(jezik) else None


def _json_telo(request):
    """Jedino mesto koje cita telo JSON zahteva; necitljivo ili preveliko telo baca ValueError."""
    try:
        telo = request.body
    except (RequestDataTooBig, RawPostDataException, UnreadablePostError) as greska:
        # RawPostDataException: multipart telo je vec potrosila CSRF provera.
        raise ValueError("telo nije citljivo") from greska
    if len(telo) > MAKS_VELICINA_TELA:
        raise ValueError("telo je preveliko")
    return json.loads(telo)  # JSONDecodeError i UnicodeDecodeError su ValueError


def _procitaj_zahtev(request):
    """Telo poteza; sve sto nije po ugovoru baca ValueError."""
    podaci = _json_telo(request)
    if not isinstance(podaci, dict) or set(podaci) != KLJUCEVI_ZAHTEVA:
        raise ValueError("pogresan oblik zahteva")
    if type(podaci["krug"]) is not int:  # bool je podklasa int-a, isinstance bi ga pustio
        raise ValueError("krug nije ceo broj")
    return podaci["krug"], podaci["izbori"]


def _procitaj_ime(request):
    """Telo cuvanja, tacno {"ime": str}; vraca NFC oblik.

    ValueError za oblik zahteva, ValidationError za ime koje ne prolazi pravila 10.4.
    """
    podaci = _json_telo(request)
    if not isinstance(podaci, dict) or set(podaci) != KLJUCEVI_CUVANJA:
        raise ValueError("pogresan oblik zahteva")  # i poeni ili ocena u zahtevu (P7)
    ime = podaci["ime"]
    if type(ime) is not str:
        raise ValueError("ime nije tekst")
    ime = unicodedata.normalize("NFC", ime)
    proveri_ime(ime)
    return ime


def _procitaj_prijavu(request):
    """Telo prijave imena, tacno {"red": javna oznaka reda}; sve drugo baca ValueError."""
    podaci = _json_telo(request)
    if not isinstance(podaci, dict) or set(podaci) != KLJUCEVI_PRIJAVE:
        raise ValueError("pogresan oblik zahteva")
    oznaka = podaci["red"]
    if type(oznaka) is not str or OBLIK_OZNAKE_REDA.fullmatch(oznaka) is None:
        raise ValueError("oznaka reda nije ispravna")
    return oznaka


def _oznaka_reda(red):
    """Javna oznaka reda rang liste, jedino cime klijent imenuje red (prijava imena).

    HMAC partije: ista za svakog posmatraca i svaki zahtev, a iz nje se ne izvodi ni id, ni partija, ni seme.
    """
    return salted_hmac(SO_OZNAKE_REDA, red.partija, algorithm="sha256").hexdigest()[: p.PRIJAVA_OZNAKA_DUZINA]


def _red_na_listama(oznaka, danas):
    """Red sa ovom oznakom medju redovima koje igraci vide (glavna lista i lista danas), inace None.

    Prijaviti se moze samo ime koje je na ekranu: red ispod RANG_MESTA ili sa liste ranijeg dana se ne nalazi.
    """
    for lista in (Rezultat.objects.glavna(), Rezultat.objects.dana(danas)):
        for red in lista.najboljih():
            if _oznaka_reda(red) == oznaka:
                return red
    return None


def _sesija_prijave(request):
    """Trag sesije u tabeli prijava: HMAC kljuca sesije, pa se iz prijave ne dobija nicija sesija."""
    return salted_hmac(SO_SESIJE_PRIJAVE, request.session.session_key, algorithm="sha256").hexdigest()


def _odbijen_potez(greska, stanje):
    return JsonResponse({"greska": greska, "stanje": motor.javni_prikaz(stanje)}, status=409)


def _sacuvana_partija(stanje):
    """Partija tekuce igre ako je sacuvana na rang listi, inace None.

    Oznaka "sacuvan" je id reda. Posle povratka migracije isti id moze da pripadne tudjoj partiji;
    takva oznaka se racuna kao da je nema (revizija N1). Oznaka obrisanog reda i dalje vazi:
    partija se ne cuva ponovo, samo nema mesto na listi.
    """
    broj = None if stanje is None else motor.sacuvani_red(stanje)
    if broj is None:
        return None
    partija = motor.oznaka_partije(stanje)
    if Rezultat.objects.filter(id=broj).exclude(partija=partija).exists():
        return None
    return partija


def _javni_rang(stanje, redovi):
    """Drugi izlaz ka klijentu: bela lista, red po red. Bez id-a, partije, trenutka upisa, broja verzije i dana.

    redovi je Rezultat.objects.glavna() ili .dana(dan), nikad ceo model (liste se ne mesaju).
    "red" je javna oznaka reda (_oznaka_reda), kojom skripta prijavljuje ime; nije id.
    """
    moja = _sacuvana_partija(stanje)
    lista = []
    moj = None
    for indeks, red in enumerate(redovi.najboljih()):
        if moja is not None and red.partija == moja:  # sopstveni red po partiji, ne po id-u iz sesije
            moj = indeks
        lista.append(
            {
                "ime": red.ime,
                "poeni": red.poeni,
                "ocena": red.ocena,  # kljuc; tekst bira skripta po jeziku posmatraca
                "datum": tekstovi.datum(red.sacuvan),
                # Bool, ne broj verzije: skripti ne treba znanje o verzijama (plan 13.3, N1-A).
                "stara_pravila": red.pravila != p.PRAVILA_TEKUCA,
                "red": _oznaka_reda(red),
            }
        )
    return {"lista": lista, "sacuvano": moja is not None, "moj": moj}


def _odbijeno_cuvanje(greska, stanje, vrsta):
    return JsonResponse({"greska": greska, "rang": _javni_rang(stanje, _lista(vrsta, stanje))}, status=409)


def _odgovor_deljenja(request, red):
    """Telo podeli 200: samo link i dan isteka. Bez id-a, partije i trenutka."""
    return {
        # Sema i host iz zahteva; get_host() proverava ALLOWED_HOSTS (plan 11.7).
        "url": request.build_absolute_uri(reverse("deljeno", args=[red.token])),
        "istice": tekstovi.datum(red.istice),
    }


def _odbijeno_deljenje(greska):
    return JsonResponse({"greska": greska}, status=409)


def _javni_deljeni(red):
    """Treci izlaz ka klijentu (plan 11.4): tacno tri kljuca, polje po polje; zavrsni opet kroz belu listu."""
    # Bez FK: ime se pojavi i kad je partija sacuvana posle deljenja, a nestane kad komanda obrise red.
    ime = Rezultat.objects.filter(partija=red.partija).values_list("ime", flat=True).first()
    return {
        "zavrsni": motor.deljeni_prikaz(red.zavrsni),
        "ime": ime,
        "datum": tekstovi.datum(red.nastao),  # D1: dan nastanka linka
    }


def _novi_deljeni(snimak, partija, sada):
    """Upisuje red za partiju; ako ga je istovremeni zahtev vec upisao, vraca taj red."""
    red = DeljeniRezultat(
        # 128 bita iz OS izvora; seme, partija i id nisu ulaz, pa se iz tokena ne izvode.
        token=secrets.token_urlsafe(p.DELJENJE_TOKEN_BAJTOVA),
        partija=partija,
        zavrsni=snimak,
        nastao=sada,
        istice=sada + timedelta(days=p.DELJENJE_DANA),
    )
    red.full_clean(validate_unique=False)  # jedinstvenost tokena i partije proverava baza, ispod
    try:
        with transaction.atomic():  # savepoint: posle IntegrityError spoljna transakcija radi dalje
            red.save()
    except IntegrityError:
        postojeci = DeljeniRezultat.objects.filter(partija=partija).first()
        if postojeci is None:
            raise  # nije dvostruko deljenje iste partije (npr. sudar tokena): pravi kvar, ne guta se
        return postojeci
    return red


def _upisi_istoriju(request, vrsta, novo):
    """Istorija pregledaca (plan: sesija, bez modela): zavrsena partija se upisuje na pocetak liste, najvise
    ISTORIJA_MAKS stavki. Zove se pod bravom potez-a, posle upisa partije u sesiju; partija nije zavrsena = nista.

    Samo ono sto je vec javno na zavrsnom ekranu (kroz javni_prikaz): bez semena, oznake, hesa i sanse.
    """
    if not novo["zavrsena"]:
        return
    zavrsni = motor.javni_prikaz(novo)["zavrsni"]
    stavka = {
        "vrsta": vrsta,
        "kraj": timezone.now().astimezone(datetime_timezone.utc).isoformat(),
        "poeni": zavrsni["poeni"],
        "ocena": zavrsni["ocena"],
        "cena": zavrsni["ukupna_cena"],
        "minuti": zavrsni["ukupni_minuti"],
    }
    dan = motor.dan_partije(novo)
    if vrsta == "dnevna" and dan is not None:
        stavka["dan"] = dan
    prethodna = request.session.get("istorija")
    prethodna = prethodna if isinstance(prethodna, list) else []
    request.session["istorija"] = [stavka, *prethodna][: p.ISTORIJA_MAKS]


def _istorija_za_prikaz(request):
    """Redovi odeljka "Моје партије" u jeziku posmatraca; pokvarena stavka se preskace."""
    sirova = request.session.get("istorija")
    redovi = []
    for stavka in sirova if isinstance(sirova, list) else []:
        try:
            dnevna = stavka["vrsta"] == "dnevna"
            red = {
                "dnevna": dnevna,
                "datum": tekstovi.datum(datetime.fromisoformat(stavka["kraj"])),
                "poeni": int(stavka["poeni"]),
                "ocena": tekstovi.ocena(stavka["ocena"]),
                "cena": tekstovi.novac(stavka["cena"]),
                "minuti": tekstovi.minuti(stavka["minuti"]),
                "dan": _datum_dana(date.fromisoformat(stavka["dan"])) if dnevna and stavka.get("dan") else None,
            }
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
        redovi.append(red)
    return redovi


def _kontekst_igre(vrsta, stanje, rang):
    """Kontekst sablona igre za obe strane; sablon i skripta adrese citaju odavde, ne iz imena ruta."""
    return {
        "vrsta": vrsta,
        "adrese": {kljuc: reverse(ime) for kljuc, ime in RUTE[vrsta].items()},
        "stanje": motor.javni_prikaz(stanje),
        "opcije": tekstovi.opcije(motor.javne_opcije()),
        "rang": rang,
        "tekstovi": tekstovi.za_skriptu(),
        "brojevi": BROJEVI,
    }


# Statistika moderatora (moderacija.statistika): danas i STATISTIKA_DANA - 1 prethodnih dana. Stariji redovi se ne
# prikazuju, pa ih upis zavrsene partije brise usput.
STATISTIKA_DANA = 7


def _zabelezi_zavrsenu(vrsta, novo):
    """Partija koju je ovaj potez zavrsio ide u statistiku: jedan red, dan zavrsetka, vrsta i poeni.

    Zove je samo potez, pod bravom i posle upisa novog stanja u sesiju; nezavrsen potez ne upisuje nista. Zavrsena
    partija ne prima nov potez (409), pa jedna partija daje tacno jedan red. Dan je danasnji (Europe/Belgrade), i za
    dnevnu partiju koja je pocela pre ponoci.
    """
    if not novo["zavrsena"]:
        return
    danas = _danas()
    ZavrsenaPartija.objects.pre(danas - timedelta(days=STATISTIKA_DANA - 1)).delete()
    red = ZavrsenaPartija(dan=danas, vrsta=vrsta, poeni=novo["rezultat"]["poeni"])
    red.full_clean()  # save() ne zove full_clean (stack-django pravilo 1)
    red.save(force_insert=True)


@require_GET
@ensure_csrf_cookie
@never_cache
def pocetna(request):
    stanje = _stanje(request)
    if stanje is None:  # P4: bez uvodnog ekrana, GET sam pravi igru
        stanje = _nova_igra()
        request.session["igra"] = stanje
    danas = _danas()
    dnevna = _stanje(request, "dnevna")
    if _dan_stanja(dnevna) != danas:
        dnevna = None  # "moj" na listi dana samo za danasnju dnevnu partiju
    kontekst = _kontekst_igre("obicna", stanje, _javni_rang(stanje, Rezultat.objects.glavna()))
    kontekst["rang_dana"] = _javni_rang(dnevna, Rezultat.objects.dana(danas))
    kontekst["istorija"] = _istorija_za_prikaz(request)
    return render(request, "igra/igra.html", kontekst)


@require_GET
@ensure_csrf_cookie
@never_cache
def dnevni(request):
    """Dnevni izazov: ista partija za sve igrace dana, jednom po sesiji i danu (bez "nova").

    Nema dnevne partije, ili je od ranijeg dana: nova partija danas (nezavrsena jucerasnja se gubi). Inace ista
    partija, tekuca ili zavrsena.
    """
    danas = _danas()
    # BEGIN IMMEDIATE (settings.py), kao nova: provera i upis nove partije su nedeljivi sa potezom iste sesije, a
    # sesija se upisuje ovde, pod bravom, pa SessionMiddleware posle ne vraca staru kopiju "igra" preko poteza
    # obicne igre iz druge kartice.
    with transaction.atomic():
        stanje = _stanje(request, "dnevna")
        if _dan_stanja(stanje) != danas:
            stanje = _nova_dnevna(danas)
            request.session["dnevna"] = stanje
            # Bez vazece sesije novi kljuc jos niko ne zna, pa nema trke: upis i kolacic ostaju middleware-u.
            if request.session.session_key is not None:
                request.session.save()
                request.session.modified = False  # inace SessionMiddleware upisuje jos jednom, van brave
    kontekst = _kontekst_igre("dnevna", stanje, _javni_rang(stanje, Rezultat.objects.dana(danas)))
    kontekst["dnevni"] = {"datum": _datum_dana(danas)}
    kontekst["istorija"] = _istorija_za_prikaz(request)
    return render(request, "igra/igra.html", kontekst)


@require_POST
def potez(request, vrsta="obicna"):
    # P5: oblik zahteva se proverava pre citanja stanja, pa 400 ima prednost nad 409.
    try:
        krug, izbori = _procitaj_zahtev(request)
        motor.proveri_izbore(izbori)
    except ValueError:  # ukljucuje motor.NepoznatIzbor
        return JsonResponse({"greska": "neispravan_zahtev"}, status=400)

    # BEGIN IMMEDIATE (settings.py) uzima bravu pre prvog citanja sesije, pa je citanje-racun-upis nedeljivo.
    with transaction.atomic():
        # Dnevna partija posle ponoci igra dalje po svom danu; potez nikad ne pravi partiju.
        stanje = _stanje(request, vrsta)
        if stanje is None:
            return JsonResponse({"greska": "nema_igre", "stanje": None}, status=409)

        try:
            novo = motor.odigraj_potez(stanje, krug, izbori)
        except motor.IgraZavrsena:
            return _odbijen_potez("igra_zavrsena", stanje)
        except motor.PogresanKrug:
            return _odbijen_potez("pogresan_krug", stanje)

        request.session[SESIJA[vrsta]] = novo
        _upisi_istoriju(request, vrsta, novo)
        _zabelezi_zavrsenu(vrsta, novo)
        request.session.save()
        request.session.modified = False  # inace SessionMiddleware upisuje jos jednom, van brave
    return JsonResponse(motor.javni_prikaz(novo))


@require_POST
def nova(request):
    # P3: i usred igre; polja forme se ne citaju, pa klijent ne moze da zada seme.
    with transaction.atomic():
        request.session["igra"] = _nova_igra()
        # Bez vazece sesije novi kljuc jos niko ne zna, pa nema trke: upis i kolacic ostaju middleware-u.
        if request.session.session_key is not None:
            request.session.save()
            request.session.modified = False  # inace SessionMiddleware upisuje jos jednom, van brave
    return redirect("pocetna")


@require_POST
def jezik(request):
    """Izbor jezika (plan 12.2): Django set_language, ali samo za kod iz LANGUAGES; CSRF ostaje.

    set_language sam prihvata svaki kod za koji postoji neki gettext katalog (de, sr-x1, dugacak en-...),
    upisuje ga u kolacic, a za next zove translate_url sa sirovim kodom, pa svaki nov kod trajno ostaje u
    kesu prevoda Django-a, bez gornje granice (bezbednosna revizija 2026-11-11).
    """
    if not _podrzan_jezik(request.POST.get("language")):  # isto polje i isti .get kao set_language
        return HttpResponseBadRequest()  # bez kolacica, bez ponavljanja vrednosti, set_language se ne zove
    return set_language(request)


@require_POST
def sacuvaj(request, vrsta="obicna"):
    # Kao P5: ime i sifarnik se proveravaju pre citanja sesije, pa 400 ima prednost nad 409.
    try:
        ime = _procitaj_ime(request)
    except ValidationError:
        return JsonResponse({"greska": "neispravno_ime"}, status=400)  # bez ponavljanja imena
    except ValueError:
        return JsonResponse({"greska": "neispravan_zahtev"}, status=400)

    # BEGIN IMMEDIATE (settings.py): brava pre prvog upita. Red i oznaka "sacuvano" se
    # upisuju u istoj transakciji, pa drugi zahtev iste sesije ceka i cita vec oznaceno stanje.
    with transaction.atomic():
        # Sifarnik pod bravom: nepodobno_dodaj ne moze da prodje izmedju provere i upisa reda.
        if NepodobnoIme.objects.sadrzi(ime):
            # Isto telo za svaku stavku: ni ime ni stavka sifarnika ne idu klijentu.
            return JsonResponse({"greska": "nepodobno_ime"}, status=400)

        stanje = _stanje(request, vrsta)
        if stanje is None:
            return _odbijeno_cuvanje("nema_igre", None, vrsta)

        if motor.sacuvani_red(stanje) is not None and _sacuvana_partija(stanje) is None:
            # Oznaka pokazuje na red druge partije (povratak migracije, revizija N1): racuna se kao
            # izgubljena, isto kao u _javni_rang. "Tacno jednom" i dalje cuva jedinstveni Rezultat.partija.
            # Kopija bez oznake je samo u memoriji; sesija se upisuje tek posle upisa reda.
            stanje = motor.oznaci_sacuvano(stanje, None)

        try:
            podaci = motor.za_cuvanje(stanje)
        except motor.IgraNijeZavrsena:
            return _odbijeno_cuvanje("igra_nije_zavrsena", stanje, vrsta)
        except motor.VecSacuvano:
            return _odbijeno_cuvanje("vec_sacuvano", stanje, vrsta)

        partija = motor.oznaka_partije(stanje)
        # Rezultat ove partije je obrisao moderator ili komanda (plan 14.4): partija se ne cuva ponovo, ni bez
        # oznake u sesiji, ni kada posle prepravke tabele id obrisanog reda pripadne drugoj partiji.
        if ZapisDnevnika.objects.obrisana(REZULTAT_OBRISAN, partija):
            return _odbijeno_cuvanje("vec_sacuvano", stanje, vrsta)

        # Dan dolazi samo iz stanja dnevne partije (dan pocetka, i posle ponoci); obicna ga nema, pa ide na glavnu.
        dan = podaci.pop("dan", None)
        rezultat = Rezultat(
            ime=ime, **podaci, dan=None if dan is None else date.fromisoformat(dan), partija=partija
        )
        rezultat.full_clean(validate_unique=False)  # jedinstvenost partije proverava baza, ispod
        try:
            with transaction.atomic():  # savepoint: posle IntegrityError spoljna transakcija radi dalje
                rezultat.save()
        except IntegrityError:
            if not Rezultat.objects.filter(partija=rezultat.partija).exists():
                raise  # nije dvostruko cuvanje iste partije: pravi kvar, ne 409
            return _odbijeno_cuvanje("vec_sacuvano", stanje, vrsta)

        novo = motor.oznaci_sacuvano(stanje, rezultat.id)
        request.session[SESIJA[vrsta]] = novo
        # Stanje je procitano iz sesije, pa kljuc postoji; bez njega upis i kolacic ostaju middleware-u.
        if request.session.session_key is not None:
            request.session.save()
            request.session.modified = False  # inace SessionMiddleware upisuje jos jednom, van brave
        telo = {"rang": _javni_rang(novo, _lista(vrsta, novo))}
    return JsonResponse(telo)


@require_POST
def podeli(request, vrsta="obicna"):
    # Telo se ne cita (kao nova): klijent nista ne zadaje, pa nema 400.
    sada = timezone.now()
    # BEGIN IMMEDIATE (settings.py): brava pre prvog citanja sesije. Red i oznaka "podeljeno" se
    # upisuju u istoj transakciji, pa drugi zahtev iste sesije ceka, cita oznaku i dobija isti link.
    with transaction.atomic():
        stanje = _stanje(request, vrsta)
        if stanje is None:
            return _odbijeno_deljenje("nema_igre")

        try:
            snimak = motor.za_deljenje(stanje)
        except motor.IgraNijeZavrsena:
            return _odbijeno_deljenje("igra_nije_zavrsena")

        partija = motor.oznaka_partije(stanje)
        broj = motor.podeljeni_red(stanje)
        # Red se trazi po partiji tekuce igre (jedinstven indeks), nikad po id-u iz oznake: posle povratka
        # migracije isti id moze da pripadne tudjoj partiji, a tudji link ne sme da izadje (revizija N1).
        red = DeljeniRezultat.objects.filter(partija=partija).first()
        if red is None:
            if broj is not None and not DeljeniRezultat.objects.filter(id=broj).exists():
                # Oznaka postoji, a njen red je obrisan: jednom po partiji, novi link se ne pravi.
                return _odbijeno_deljenje("deljenje_isteklo")
            if ZapisDnevnika.objects.obrisana(LINK_OBRISAN, partija):
                # Link ove partije je obrisao moderator ili komanda (plan 14.4): ni bez oznake u sesiji, ni kada
                # id obrisanog reda posle prepravke tabele pripadne drugoj partiji.
                return _odbijeno_deljenje("deljenje_isteklo")
            # Bez oznake, ili oznaka pokazuje na red druge partije (racuna se kao izgubljena): nov link.
            red = _novi_deljeni(snimak, partija, sada)
        if red.istekao(sada):
            return _odbijeno_deljenje("deljenje_isteklo")

        if broj != red.id:  # ponovni klik sa ispravnom oznakom ne upisuje sesiju
            request.session[SESIJA[vrsta]] = motor.oznaci_podeljeno(stanje, red.id)
            # Stanje je procitano iz sesije, pa kljuc postoji; bez njega upis i kolacic ostaju middleware-u.
            if request.session.session_key is not None:
                request.session.save()
                request.session.modified = False  # inace SessionMiddleware upisuje jos jednom, van brave
        telo = _odgovor_deljenja(request, red)
    return JsonResponse(telo)


@require_POST
def prijavi(request):
    """Prijava neprikladnog imena sa rang liste (odluka 2026-11-12): telo je samo javna oznaka reda.

    Prijava nista ne sakriva i nista ne brise: o imenu odlucuje moderator (moderacija.pregled). Odgovor 200 je isti
    za novu prijavu, za ponovljenu iz iste sesije, za ime koje je moderator vec ostavio i za red koji je dostigao
    PRIJAVA_NAJVISE, pa ne odaje ni tudje prijave ni odluku moderatora.
    """
    # Kao P5: oblik zahteva se proverava pre citanja sesije, pa 400 ima prednost nad 409.
    try:
        oznaka = _procitaj_prijavu(request)
    except ValueError:
        return JsonResponse({"greska": "neispravan_zahtev"}, status=400)

    # BEGIN IMMEDIATE (settings.py): brava pre prvog citanja, pa su provere i upis prijave nedeljivi i sa odlukom
    # moderatora (brisanje.odbaci_prijave) i sa drugim zahtevom iste sesije.
    with transaction.atomic():
        # Samo sesija koja ima partiju (pravi je svaka strana igre). Posle citanja sesije session_key je None za
        # izmisljen sessionid, pa svaki takav zahtev ne vazi kao nov igrac.
        bez_partije = all(request.session.get(kljuc) is None for kljuc in SESIJA.values())
        if bez_partije or request.session.session_key is None:
            return JsonResponse({"greska": "nema_igre"}, status=409)

        danas = _danas()
        red = _red_na_listama(oznaka, danas)
        if red is None:
            return JsonResponse({"greska": "nije_na_listi"}, status=409)

        # Usput: lista ranijeg dana vise nije ni na ekranu ni u pregledu moderatora, pa njene prijave ne ostaju.
        PrijavaImena.objects.minulih_dana(danas).delete()

        sesija = _sesija_prijave(request)
        prijave = PrijavaImena.objects.filter(rezultat=red)
        zabelezi = not (
            # Moderator je ovo ime vec pregledao i ostavio: ne vraca se medju prijavljena.
            ZapisDnevnika.objects.prijava_odbacena(red.partija)
            or prijave.filter(sesija=sesija).exists()
            or prijave.count() >= p.PRIJAVA_NAJVISE
        )
        if zabelezi:
            prijava = PrijavaImena(rezultat=red, sesija=sesija)
            prijava.full_clean()
            prijava.save()
    return JsonResponse({"primljeno": True})


@require_safe
@never_cache
def zdravlje(request):
    """Provera zdravlja (plan 15.5): jedno citanje tabele igre, pa 200 {"ok": true}.

    Bez request.session i bez CSRF tokena, pa ne pravi red u django_session ni kolacic: provera na 30 s bi inace
    pravila 2.880 sesija dnevno. Baza koja ne radi ili nije migrirana daje izuzetak, pa 500. GET, i HEAD za
    spoljne provere koje salju samo HEAD.
    """
    Rezultat.objects.exists()
    return JsonResponse({"ok": True})


def _javni_red_api(mesto, red):
    """Red javne rang liste za partnere: bela lista. Bez id-a, oznake reda, partije, dana i prijava."""
    return {
        "mesto": mesto,
        "ime": red.ime,
        "poeni": red.poeni,
        "ocena": red.ocena,  # kljuc, ne tekst: isti u svakom jeziku
        "datum": timezone.localtime(red.sacuvan).date().isoformat(),  # masinski oblik, ne zavisi od jezika
        "staro_bodovanje": red.pravila != p.PRAVILA_TEKUCA,
    }


@require_safe
def javna_rang_lista(request):
    """Javna rang lista u JSON obliku za partnere (zahtev klijenta): bez kljuca, naloga, sesije i kolacica.

    Obrazac prikaza zdravlje: ne cita request.session i ne trazi CSRF token. Liste idu samo kroz glavna() i
    dana(_danas()), 10 najboljih kao na strani. Odgovor je isti za svaki jezik pregledaca, pa nema prevoda.
    Kes 60 s: moderatorsko brisanje se na ovoj adresi vidi najkasnije posle 60 s. CORS otvoren, jer partner
    moze da cita iz pregledaca; odgovor ne nosi nista licno, pa je `*` bezbedan.
    """
    dan = _danas()
    glavna = Rezultat.objects.glavna().najboljih()
    danas = Rezultat.objects.dana(dan).najboljih()
    odgovor = JsonResponse(
        {
            "verzija": 1,
            "glavna": [_javni_red_api(mesto, red) for mesto, red in enumerate(glavna, start=1)],
            "danas": {
                "dan": dan.isoformat(),
                "redovi": [_javni_red_api(mesto, red) for mesto, red in enumerate(danas, start=1)],
            },
        }
    )
    odgovor["Access-Control-Allow-Origin"] = "*"
    odgovor["Cache-Control"] = "public, max-age=60"
    return odgovor


@require_GET
@never_cache
def deljeno(request, token):
    # Samo citanje (plan 11.4): bez ensure_csrf_cookie i bez request.session, pa strana ne pravi
    # sesiju ni CSRF kolacic i ne menja igru posetioca.
    # J1: ?jezik= vazi samo za ovaj odgovor, bez kolacica i upisa; inace jezik iz LocaleMiddleware.
    jezik = _jezik_upita(request) or translation.get_language()
    with translation.override(jezik):
        red = None
        if OBLIK_TOKENA.fullmatch(token):
            red = DeljeniRezultat.objects.vazeci(timezone.now()).filter(token=token).first()
        if red is None:
            # Istekao, nepostojeci i neispravan token daju isti 404, pa link ne odaje da li je postojao.
            # Ne Http404: uz DEBUG = True Django bi prikazao tehnicku stranu sa spiskom ruta.
            kontekst = {"deljeno": None, "dana": p.DELJENJE_DANA, "tekstovi": tekstovi.za_skriptu()}
            odgovor = render(request, "igra/deljeno.html", kontekst, status=404)
        else:
            kontekst = {"deljeno": _javni_deljeni(red), "tekstovi": tekstovi.za_skriptu()}
            odgovor = render(request, "igra/deljeno.html", kontekst)
    # Izricito: LocaleMiddleware posle override-a upisuje samo ako zaglavlja nema, i to jezik zahteva.
    odgovor["Content-Language"] = jezik
    # Jezik zavisi i od kolacica jezika (plan 12.2); sesija se i dalje ne cita.
    patch_vary_headers(odgovor, ("Cookie",))
    # Token je u URL-u: ne odlazi kao Referer (zamenjuje same-origin iz SecurityMiddleware) i ne indeksira se.
    odgovor["Referrer-Policy"] = "no-referrer"
    odgovor["X-Robots-Tag"] = "noindex, nofollow"
    return odgovor


# Primer jednog kruga na strani "Kako se igra": prvi zadatak i jedan izbor. Brojeve racuna motor.
PRIMER_KRUG = 1
PRIMER_IZBORI = {"model": "sonnet", "nivo": "high", "kontekst": "taman", "podela": "sam"}


def _kontekst_pravila():
    """Sve sto strana "Kako se igra" prikazuje; samo javno: nikad sansa, oznaka tihog zadatka ni seme."""
    kazne = p.KAZNE[p.PRAVILA_TEKUCA]
    opcije = tekstovi.opcije(motor.javne_opcije())
    zadatak = p.ZADACI[PRIMER_KRUG - 1]
    r = motor.racun(zadatak["tezina"], PRIMER_IZBORI)  # "sansa" iz r se ne cita
    cena = round(r["cena"], p.DECIMALA_JAVNIH)
    minuti = round(r["minuti"], p.DECIMALA_JAVNIH)
    dorada_cena = round(r["cena"] * p.MNOZILAC_DORADE, p.DECIMALA_JAVNIH)
    dorada_minuti = round(r["minuti"] * p.MNOZILAC_DORADE, p.DECIMALA_JAVNIH)
    izabrano = {
        grupa: next(o["naziv"] for o in opcije[grupa] if o["kljuc"] == kljuc)
        for grupa, kljuc in PRIMER_IZBORI.items()
    }
    ocene = []
    gore = p.POCETNI_POENI
    for prag, kljuc in p.OCENE:
        ocene.append({"poeni": f"{prag}–{gore}", "naziv": tekstovi.ocena(kljuc)})
        gore = prag - 1
    return {
        "krugova": p.KRUGOVA,
        "budzet": tekstovi.novac(p.BUDZET, 0),
        "rok": tekstovi.minuti(p.ROK, 0),
        "opcije": opcije,
        "statusi": {kljuc: translation.gettext(tekst) for kljuc, tekst in p.NAZIVI_STATUSA.items()},
        "mnozilac": p.MNOZILAC_DORADE,
        "kazna_dorada": kazne["dorada"],
        "kazna_tiha": kazne["tiha"],
        "kazna_budzet": kazne["budzet_po_koraku"],
        "budzet_korak": tekstovi.procenat(kazne["budzet_korak_procenata"]),
        "budzet_maks": kazne["budzet_maks"],
        "kazna_rok": kazne["rok"],
        "pocetni_poeni": p.POCETNI_POENI,
        "ocene": ocene,
        "napomena": translation.gettext(p.NAPOMENA),
        "primer": {
            "zadatak": translation.gettext(zadatak["naziv"]),
            "izabrano": izabrano,
            "cena": tekstovi.novac(cena, 3),
            "minuti": tekstovi.minuti(minuti, 1),
            "dorada_cena": tekstovi.novac(dorada_cena, 3),
            "dorada_minuti": tekstovi.minuti(dorada_minuti, 1),
        },
    }


@require_GET
@never_cache
def kako_se_igra(request):
    # Samo citanje, kao deljeno: ne cita i ne pise request.session i ne pravi partiju. Izbor jezika je ista
    # forma kao na igri (kolacic jezika, ne sesija); CSRF kolacic je jedini kolacic koji strana postavlja.
    return render(request, "igra/kako.html", _kontekst_pravila())
