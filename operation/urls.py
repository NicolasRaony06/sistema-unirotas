from .views import *
from django.urls import path

urlpatterns = [
    path('viagens/', lista_viagens, name='lista_viagens'),
    path('viagens/concluir/<int:viagem_id>', concluir_viagem, name='concluir_viagem'),
    path('viagens/comecar/<int:viagem_id>', comecar_viagem, name='comecar_viagem')
]