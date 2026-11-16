from django.urls import path

from igra import views

urlpatterns = [
    path("", views.pocetna, name="pocetna"),
    path("nova/", views.nova, name="nova"),
    path("api/potez/", views.potez, name="potez"),
    path("kraj/", views.kraj, name="kraj"),
]
