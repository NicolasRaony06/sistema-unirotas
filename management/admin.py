from django.contrib import admin
from .models import *

@admin.register(Municipio)
class MunicipioAdmin(admin.ModelAdmin):
    ...

@admin.register(Bus)
class BusAdmin(admin.ModelAdmin):
    ...

@admin.register(BusStop)
class BusStopAdmin(admin.ModelAdmin):
    ...

@admin.register(Institution)
class InstitutionAdmin(admin.ModelAdmin):
    ...
# Register your models here.
