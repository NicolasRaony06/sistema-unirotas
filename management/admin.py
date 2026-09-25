from django.contrib import admin
from .models import *

@admin.register(Municipio)
class MunicipioAdmin(admin.ModelAdmin):
    ...

@admin.register(Bus)
class BusAdmin(admin.ModelAdmin):
    ...
# Register your models here.
