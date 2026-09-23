from .views import *
from django.urls import path

app_name = 'management'

urlpatterns = [
    path('home/',home, name='home'),
    path('cadastrar-municipio/',criar_municipio,name='criar-municipio '),
    path('invite_driver/', invite_driver, name="invite_driver")
]