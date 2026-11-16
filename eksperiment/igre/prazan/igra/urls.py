from django.urls import path

from igra import jezik, moderator, views

urlpatterns = [
    path("moderator/", moderator.rezultati, name="moderator_rezultati"),
    path("moderator/prijava/", moderator.prijava, name="moderator_prijava"),
    path("moderator/odjava/", moderator.odjava, name="moderator_odjava"),
    path("moderator/izvoz/", moderator.izvoz, name="moderator_izvoz"),
    path("moderator/linkovi/", moderator.linkovi, name="moderator_linkovi"),
    path("moderator/prijavljena-imena/", moderator.prijavljena_imena, name="moderator_prijavljena_imena"),
    path("moderator/rezultat/<int:pk>/zadrzi/", moderator.zadrzi_rezultat, name="moderator_zadrzi_rezultat"),
    path("moderator/rezultat/<int:pk>/obrisi/", moderator.obrisi_rezultat, name="moderator_obrisi_rezultat"),
    path("moderator/link/<str:kod>/obrisi/", moderator.obrisi_link, name="moderator_obrisi_link"),
    path("moderator/dnevnik/", moderator.dnevnik, name="moderator_dnevnik"),
    path("moderator/statistika/", moderator.statistika, name="moderator_statistika"),
    path("moderator/nalozi/", moderator.nalozi, name="moderator_nalozi"),
    path("moderator/nalozi/<int:pk>/iskljuci/", moderator.iskljuci, name="moderator_iskljuci"),
    path("moderator/nalozi/<int:pk>/ukljuci/", moderator.ukljuci, name="moderator_ukljuci"),
    path("", views.pocetna, name="pocetna"),
    path("nova/", views.nova, name="nova"),
    path("dnevna/", views.dnevna, name="dnevna"),
    path("api/potez/", views.potez, name="potez"),
    path("api/rang-lista/", views.javna_rang_lista, name="javna_rang_lista"),
    path("kako-se-igra/", views.kako_se_igra, name="kako_se_igra"),
    path("kraj/", views.kraj, name="kraj"),
    path("rezultat/", views.sacuvaj, name="sacuvaj"),
    path("rezultat/<int:pk>/prijavi/", views.prijavi_ime, name="prijavi_ime"),
    path("partija/<str:kod>/", views.podeljeno, name="podeljeno"),
    path("jezik/<str:jezik>/", jezik.promeni_jezik, name="jezik"),
]
