from unittest import mock

from igra.pravila import Izbori

HIGH_OPUS = Izbori("opus", "high", "taman", "sam")
HIGH_HAIKU = Izbori("haiku", "high", "taman", "sam")
SVE_OPUS = [HIGH_OPUS] * 8


def neuspesni_krugovi(*krugovi):
    """Zamenjuje kocku: navedeni krugovi su neuspesni, svi ostali uspesni."""
    return mock.patch(
        "igra.pravila.uspeh_kruga",
        side_effect=lambda seme, krug, sansa: krug not in krugovi,
    )
