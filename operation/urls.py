from .views import *
from django.urls import path

urlpatterns = [
    path('viagens/', lista_viagens, name='lista_viagens'),
    path('viagens/concluir/<int:viagem_id>', concluir_viagem, name='concluir_viagem'),
    path('viagens/comecar/<int:viagem_id>', comecar_viagem, name='comecar_viagem'),
    path('viagem/<int:viagem_id>/alunos/', lista_alunos, name='lista_alunos'),
    path('viagem/<int:viagem_id>/moderadores/', lista_moderadores, name='lista_moderadores'),
    path('usuario-viagem/<int:usuario_viagem_id>/definir-moderador/', definir_moderador, name='definir_moderador'),
]