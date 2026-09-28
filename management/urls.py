from .views import *
from django.urls import path

app_name = 'management'

urlpatterns = [
    path('home/',home, name='home-admin'),
    path('municipios/',municipios,name='municipios'),
    path('gestores/',gestores,name='gestores'),
    path('criar-municipio/',criar_municipio,name='criar-municipio'),
    path('associar-gestor/',associar_gestor, name='associar-gestor'),
    path('homologar-municipio/',homologar_mun,name='homologar-municipio'),
    path('desabilitar-municipio/',desabilitar_mun,name='desabilitar-municipio'),
    path('listagem/',listar_municipios),

    #path('home-manager/',home_manager, name='home-manager'),
]