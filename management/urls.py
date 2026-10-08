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
    path('deactivate_institution/<int:id>', deactivate_institution, name="deactivate_institution"),
    path('activate_institution/<int:id>', activate_institution, name="activate_institution"), 
    path('edit_institution/<int:id>', edit_institution, name="edit_institution"),
    path('home/',home, name='home'),
    path('gestores/',gestores,name='gestores'),
    path('municipios/',municipios,name='municipios'),
    #path('convidar-gestor/',convidar_gestor,name='convidar-gestor')
    path('criar-municipio/',criar_municipio,name='criar-municipio'),
    path('associar-gestor/',associar_gestor, name='associar-gestor'),
    path('homologar-municipio/<int:id>',homologar_mun,name='homologar-municipio'),
    path('desabilitar-municipio/<int:id>',desabilitar_mun,name='desabilitar-municipio'),
    path('localizacoes/',localizacoes,name='localizacoes'),
    path('deactive-manager/<int:id>',deactive_manager,name='deactive-manager'),
    path('active-manager/<int:id>',activate_manager,name='active-manager'),
    path('retirar-municipio/<int:id>',retirar_municipio,name='retirar-municipio'),
    # path('adicionar-municipio',adicionar_municipio,name='adicionar-municipio'),
]