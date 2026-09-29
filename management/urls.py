from .views import *
from django.urls import path

app_name = 'management'

urlpatterns = [
    path('invite_driver/', invite_driver, name="invite_driver"),
    path('view_drivers/', view_drivers, name="view_drivers"),
    path('edit_driver/<int:id>', edit_driver, name="edit_driver"),
    path('remove_driver/<int:id>', remove_driver, name="remove_driver"),
    path('register_bus/', register_bus, name="register_bus"),
    path('home/',home, name='home-admin'),
    path('municipios/',municipios,name='municipios'),
    path('gestores/',gestores,name='gestores'),
    path('criar-municipio/',criar_municipio,name='criar-municipio'),
    path('associar-gestor/',associar_gestor, name='associar-gestor'),
    path('homologar-municipio/',homologar_mun,name='homologar-municipio'),
    path('desabilitar-municipio/',desabilitar_mun,name='desabilitar-municipio'),
    path('listagem/',listar_municipios),
    path('home-manager/',home_manager, name='home-manager'),
]