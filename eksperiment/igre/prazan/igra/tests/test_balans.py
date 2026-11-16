from fractions import Fraction

from django.test import SimpleTestCase

from igra import parametri as p
from igra import pravila
from igra.pravila import Izbori

BROJ_SEMENA = 5000

PO_TEZINI = {
    1: Izbori("haiku", "high", "taman", "sam"),
    2: Izbori("sonnet", "high", "taman", "3_agenta"),
    3: Izbori("opus", "high", "taman", "sam"),
}


def po_tezini():
    return [PO_TEZINI[z.tezina] for z in p.ZADACI]


def sve_opus():
    return [Izbori("opus", "high", "taman", "sam")] * p.BROJ_KRUGOVA


def sve_haiku():
    return [Izbori("haiku", "low", "malo", "sam")] * p.BROJ_KRUGOVA


def srednji_poeni(potezi):
    ukupno = sum(pravila.konacni_rezultat(str(i), potezi).poeni for i in range(BROJ_SEMENA))
    return Fraction(ukupno, BROJ_SEMENA)


class BalansTest(SimpleTestCase):
    def test_poredak_strategija(self):
        tezina = srednji_poeni(po_tezini())
        opus = srednji_poeni(sve_opus())
        haiku = srednji_poeni(sve_haiku())
        poruka = f"po tezini={float(tezina):.2f}, opus={float(opus):.2f}, haiku={float(haiku):.2f}"
        print(f"\nBalans: {poruka}")
        self.assertGreater(tezina, opus, poruka)
        self.assertGreater(opus, haiku, poruka)
