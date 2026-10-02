from django.contrib import admin
from operation.models import Viagem, UsuarioDaViagem, Linha

# Register your models here.

admin.site.register(Viagem)
admin.site.register(UsuarioDaViagem)
admin.site.register(Linha)

