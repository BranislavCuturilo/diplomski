from django.contrib.staticfiles.views import serve
from django.urls import include, path, re_path

urlpatterns = [
    path("", include("igra.urls")),
    # Lokalna igra radi sa DEBUG = False, pa staticke datoteke sluzi ova putanja.
    re_path(r"^static/(?P<path>.*)$", serve, {"insecure": True}),
]
