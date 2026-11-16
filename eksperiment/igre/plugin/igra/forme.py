"""Forme moderatorskih strana (plan 14.2, 14.5, 14.7). Imena polja su ugovor sa sablonima (14.9).

Ovde zivi i brojac neuspeha: prijava, potvrda sopstvenom lozinkom i stara lozinka pri promeni dele isti kljuc
po imenu onoga ko se prijavljuje ili radi (plan 14.2). Brojac je u bazi (PokusajPrijave), pa je zajednicki svim
procesima servera (plan 15.2, odluka P2).
"""

import hashlib
import math
import time
import unicodedata

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, SetPasswordMixin
from django.contrib.auth.hashers import check_password
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError
from django.views.decorators.debug import sensitive_variables

from . import nalozi, tekstovi
from .models import PokusajPrijave

User = get_user_model()


# ---------- brojac neuspeha ----------
# Sat je time.time(): isti sat cita i upisuje svaki proces, a testovi ga pomeraju patch-om "time.time".


def _kljuc(ime):
    # Po imenu, ne po IP-u, i za nepostojece ime, pa ne odaje da li nalog postoji. Isti oblik kao UsernameField
    # (NFKC, bez razmaka na krajevima), bez razlike velikih i malih slova: "Pera" i "pera" dele brojac.
    oblik = unicodedata.normalize("NFKC", ime).strip().casefold()
    return hashlib.sha256(oblik.encode("utf-8")).hexdigest()


def rezervisi_pokusaj(ime):
    """Broji pokusaj PRE provere lozinke. Vraca None (provera sme) ili minute do kraja blokade, navise.

    Brojanje i citanje rednog broja su jedna naredba u bazi (PokusajPrijave.objects.rezervisi), pa svaki
    istovremeni zahtev, i iz drugog procesa, dobija svoj redni broj, a proveru prolazi najvise PRIJAVA_POKUSAJA
    njih (get pa set posle provere pustao je 38 od 40, revizija 2026-11-11). Zato se ovo zove samo kada provera
    zaista sledi: red u bazi tada kosta napadaca jedan PBKDF2. Posle provere uspeh brise brojac
    (obrisi_neuspehe), a neuspeh pomera rok (zabelezi_neuspeh). Zove se van transaction.atomic(): brojac se
    upisuje pre provere lozinke, a PBKDF2 ne sme da drzi bravu baze.
    """
    broj, istice = PokusajPrijave.objects.rezervisi(_kljuc(ime), time.time(), settings.PRIJAVA_BLOKADA_SEKUNDI)
    if broj <= settings.PRIJAVA_POKUSAJA:
        return None
    # Blokiran pokusaj se broji, ali rok ne pomera: blokada traje od poslednjeg neuspeha. Sat se cita ponovo posle
    # upisa: tudji neuspeh upisan izmedju prvog citanja sata i upisa pomera kraj iza tog trenutka + rok, pa bi poruka
    # rekla "16 minuta".
    return max(1, math.ceil((istice - time.time()) / 60))


def zabelezi_neuspeh(ime):
    """Posle neuspele provere (pokusaj je vec izbrojan): rok PRIJAVA_BLOKADA_SEKUNDI tece od ovog neuspeha.

    Samo postojeci red: ako ga je istovremeni uspeh obrisao, neuspeh ga ne vraca.
    """
    istice = time.time() + settings.PRIJAVA_BLOKADA_SEKUNDI
    PokusajPrijave.objects.filter(kljuc=_kljuc(ime)).update(istice=istice)


def obrisi_neuspehe(ime):
    PokusajPrijave.objects.filter(kljuc=_kljuc(ime)).delete()


@sensitive_variables("lozinka")
def _proveri_sopstvenu(korisnik, lozinka):
    """Lozinka onoga ko radi; pokusaj ide kroz brojac prijave, pre provere. Baca ValidationError."""
    ime = korisnik.get_username()
    minuta = rezervisi_pokusaj(ime)
    if minuta is not None:
        # Blokiran: lozinka se ne proverava, pa ni ispravna ne prolazi.
        raise ValidationError(tekstovi.blokada(minuta), code="blokirano")
    # Bez settera, ne korisnik.check_password: nadogradnja hesa bi upisala nov hes, a nov hes menja hes sesije
    # i odjavljuje onoga ko radi, usred radnje (revizija 2026-11-11).
    if not check_password(lozinka, korisnik.password):
        zabelezi_neuspeh(ime)
        raise ValidationError(tekstovi.POGRESNA_LOZINKA, code="pogresna_lozinka")
    obrisi_neuspehe(ime)


def _polje_lozinke(oznaka, autocomplete):
    return forms.CharField(
        label=oznaka, strip=False, widget=forms.PasswordInput(attrs={"autocomplete": autocomplete})
    )


# ---------- forme ----------


class PrijavaForma(AuthenticationForm):
    """Polja username i password. Ista poruka za svaki neuspeh; nalog bez uloge se ne prijavljuje."""

    error_messages = {
        "invalid_login": tekstovi.PRIJAVA_NEUSPESNA,
        "inactive": tekstovi.PRIJAVA_NEUSPESNA,
    }
    # Minuti do kraja blokade posle is_valid(), ili None; prikaz ih daje sablonu (blokirano).
    blokirano = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = tekstovi.POLJA["korisnicko_ime"]
        self.fields["password"].label = tekstovi.POLJA["lozinka"]

    def clean(self):
        ime = self.cleaned_data.get("username")
        if ime is None or not self.cleaned_data.get("password"):
            # AuthenticationForm tada ne zove authenticate: nema provere, pa ni pokusaja ni reda u bazi.
            return super().clean()
        self.blokirano = rezervisi_pokusaj(ime)
        if self.blokirano is not None:
            # Blokirano: authenticate se ne zove, pa ni ispravna lozinka ne prolazi.
            raise ValidationError(tekstovi.blokada(self.blokirano), code="blokirano")
        try:
            podaci = super().clean()
        except ValidationError:
            # Pogresno ime, pogresna lozinka, neaktivan nalog i nalog bez uloge (confirm_login_allowed).
            zabelezi_neuspeh(ime)
            raise
        obrisi_neuspehe(ime)
        return podaci

    def confirm_login_allowed(self, user):
        # Neaktivan nalog authenticate vec vraca kao None; ovde i superuser, korisnik bez dozvole i bez naloga.
        if nalozi.uloga(user) is None:
            raise self.get_invalid_login_error()


class PotvrdaForma(forms.Form):
    """Potvrda sopstvenom lozinkom za radnje glavnog nad nalozima (plan 14.5): polje moja_lozinka."""

    moja_lozinka = _polje_lozinke(tekstovi.POLJA["moja_lozinka"], "current-password")

    def __init__(self, ko, *args, **kwargs):
        self.ko = ko
        super().__init__(*args, **kwargs)

    @sensitive_variables("lozinka")
    def clean_moja_lozinka(self):
        lozinka = self.cleaned_data["moja_lozinka"]
        _proveri_sopstvenu(self.ko, lozinka)
        return lozinka


class LozinkaNalogaForma(SetPasswordMixin, PotvrdaForma):
    """Nova lozinka tudjeg naloga (radnje aktiviraj i lozinka): lozinka1, lozinka2, moja_lozinka."""

    lozinka1, lozinka2 = SetPasswordMixin.create_password_fields(
        label1=tekstovi.POLJA["nova_lozinka"], label2=tekstovi.POLJA["lozinka_ponovo"]
    )
    field_order = ["lozinka1", "lozinka2", "moja_lozinka"]

    def __init__(self, ko, nad, *args, **kwargs):
        self.nad = nad
        super().__init__(ko, *args, **kwargs)

    def clean(self):
        super().clean()
        self.validate_passwords("lozinka1", "lozinka2")
        # Validatori u odnosu na vlasnika naloga (slicnost sa imenom), ne na onoga ko radi.
        self.validate_password_for_user(self.nad, "lozinka1")
        return self.cleaned_data


class DodajForma(SetPasswordMixin, PotvrdaForma):
    """Nov moderator: ime, lozinka1, lozinka2, glavni, moja_lozinka."""

    ime = forms.CharField(
        label=tekstovi.POLJA["korisnicko_ime"],
        max_length=User._meta.get_field("username").max_length,
        validators=[UnicodeUsernameValidator()],
    )
    lozinka1, lozinka2 = SetPasswordMixin.create_password_fields(
        label1=tekstovi.POLJA["lozinka"], label2=tekstovi.POLJA["lozinka_ponovo"]
    )
    glavni = forms.BooleanField(label=tekstovi.POLJA["glavni"], required=False)
    field_order = ["ime", "lozinka1", "lozinka2", "glavni", "moja_lozinka"]

    def clean_ime(self):
        ime = User.normalize_username(self.cleaned_data["ime"])
        if nalozi.ime_zauzeto(ime):
            raise ValidationError(User._meta.get_field("username").error_messages["unique"], code="unique")
        return ime

    def clean(self):
        super().clean()
        self.validate_passwords("lozinka1", "lozinka2")
        ime = self.cleaned_data.get("ime")
        if ime:
            self.validate_password_for_user(User(username=ime), "lozinka1")
        return self.cleaned_data


class PromenaLozinkeForma(PasswordChangeForm):
    """Sopstvena lozinka (Django imena polja); pogresna stara lozinka ulazi u brojac prijave."""

    @sensitive_variables("lozinka")
    def clean_old_password(self):
        lozinka = self.cleaned_data["old_password"]
        _proveri_sopstvenu(self.user, lozinka)
        return lozinka
