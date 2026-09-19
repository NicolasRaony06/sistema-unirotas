from django.contrib import admin
from .models import *

@admin.register(Municipio)
class MunicipioAdmin(admin.ModelAdmin):
    ...
# Register your models here.
