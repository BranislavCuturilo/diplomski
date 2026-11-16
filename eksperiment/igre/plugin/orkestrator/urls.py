from django.urls import path

from igra import moderacija, views

urlpatterns = [
    path('', views.pocetna, name='pocetna'),
    path('potez/', views.potez, name='potez'),
    path('nova/', views.nova, name='nova'),
    path('sacuvaj/', views.sacuvaj, name='sacuvaj'),
    path('podeli/', views.podeli, name='podeli'),
    # Dnevni izazov: isti prikazi nad kljucem sesije "dnevna"; vrstu zadaje samo URLconf. Bez dnevni/nova/:
    # dnevna partija se igra jednom po sesiji i danu.
    path('dnevni/', views.dnevni, name='dnevni'),
    path('dnevni/potez/', views.potez, {'vrsta': 'dnevna'}, name='dnevni_potez'),
    path('dnevni/sacuvaj/', views.sacuvaj, {'vrsta': 'dnevna'}, name='dnevni_sacuvaj'),
    path('dnevni/podeli/', views.podeli, {'vrsta': 'dnevna'}, name='dnevni_podeli'),
    # Prijava neprikladnog imena sa rang liste (odluka 2026-11-12): jedna ruta za obe strane, jer je o redu
    # liste (glavne ili danasnje), ne o partiji.
    path('prijavi/', views.prijavi, name='prijavi'),
    # Oblik tokena proverava prikaz, ne konverter: neispravan token daje isti 404 kao istekao (plan 11.4).
    path('r/<str:token>/', views.deljeno, name='deljeno'),
    # Pravila i primer kruga: GET, samo citanje, bez sesije i partije.
    path('kako-se-igra/', views.kako_se_igra, name='kako_se_igra'),
    # Izbor jezika (plan 12.2): samo POST i samo kod iz LANGUAGES, pa Django set_language; next proverava
    # sam Django. Bez prefiksa jezika u URL-u: link za deljenje je isti za sve jezike.
    path('jezik/', views.jezik, name='jezik'),
    # Provera zdravlja za compose i spoljno pracenje (plan 15.5): GET (i HEAD), JSON, bez sesije.
    path('zdravlje/', views.zdravlje, name='zdravlje'),
    # Javna rang lista u JSON obliku za partnere: GET (i HEAD), bez sesije i kolacica, kes 60 s.
    path('api/rang-lista/', views.javna_rang_lista, name='javna_rang_lista'),
    # Moderator (plan 14.7). Svaka ruta osim prijave je pod moderator_potreban, nalozi* pod glavni_potreban.
    path('moderator/prijava/', moderacija.prijava, name='moderator_prijava'),
    path('moderator/odjava/', moderacija.odjava, name='moderator_odjava'),
    path('moderator/', moderacija.pregled, name='moderator'),
    path('moderator/rezultat/<int:broj>/', moderacija.rezultat, name='moderator_rezultat'),
    # Prijavljeno ime ostaje (samo POST): prijave se brisu, odluka ide u dnevnik.
    path('moderator/rezultat/<int:broj>/ostavi/', moderacija.ostavi, name='moderator_ostavi'),
    path('moderator/link/<int:broj>/', moderacija.link, name='moderator_link'),
    path('moderator/izvoz/glavna.csv', moderacija.izvoz_glavne, name='moderator_izvoz_glavne'),
    path('moderator/izvoz/dnevna.csv', moderacija.izvoz_dana, name='moderator_izvoz_dana'),
    path('moderator/dnevnik/', moderacija.dnevnik, name='moderator_dnevnik'),
    # Zavrsene partije po danu, poslednjih 7 dana (samo GET).
    path('moderator/statistika/', moderacija.statistika, name='moderator_statistika'),
    path('moderator/lozinka/', moderacija.lozinka, name='moderator_lozinka'),
    path('moderator/nalozi/', moderacija.spisak_naloga, name='moderator_nalozi'),
    path('moderator/nalozi/<int:broj>/', moderacija.nalog, name='moderator_nalozi_nalog'),
]
