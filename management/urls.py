from .views import *
from django.urls import path

app_name = 'management'

urlpatterns = [
    path('invite_driver/', invite_driver, name="invite_driver"),
    path('view_drivers/', view_drivers, name="view_drivers"),
    path('edit_driver/<int:id>', edit_driver, name="edit_driver"),
    path('deactivate_driver/<int:id>', deactivate_driver, name="deactivate_driver"),
    path('activate_driver/<int:id>', activate_driver, name="activate_driver"),
    path('register_bus/', register_bus, name="register_bus"),
    path('view_buses/', view_buses, name="view_buses"),
    path('edit_bus/<int:id>', edit_bus, name="edit_bus"),
    path('deactivate_bus/<int:id>', deactivate_bus, name="deactivate_bus"),
    path('activate_bus/<int:id>', activate_bus, name="activate_bus"),
    path('register_bus_stop/', register_bus_stop, name="register_bus_stop"),
    path('view_bus_stops/', view_bus_stops, name="view_bus_stops"),
    path('deactivate_bus_stop/<int:id>', deactivate_bus_stop, name="deactivate_bus_stop"),
    path('activate_bus_stop/<int:id>', activate_bus_stop, name="activate_bus_stop"),    
    path('edit_bus_stop/<int:id>', edit_bus_stop, name="edit_bus_stop"),
    path('register_institution/', register_institution, name="register_institution"),
    path('view_institutions/', view_institutions, name="view_institutions"),
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