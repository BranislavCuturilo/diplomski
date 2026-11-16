from django.conf import settings
from django.contrib.staticfiles.views import serve
from django.urls import include, path, re_path

urlpatterns = [
    path("", include("igra.urls")),
]

if settings.SLUZI_STATICKE:
    # Lokalna igra radi sa DEBUG = False, pa staticke datoteke sluzi ova putanja.
    # Na javnom serveru ih sluzi nginx iz STATIC_ROOT (settings_produkcija.py).
    urlpatterns.append(re_path(r"^static/(?P<path>.*)$", serve, {"insecure": True}))
