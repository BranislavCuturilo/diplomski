from django.urls import path

from igra import views

urlpatterns = [
    path('', views.pocetna, name='pocetna'),
    path('potez/', views.potez, name='potez'),
    path('nova/', views.nova, name='nova'),
]
