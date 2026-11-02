from django.contrib import admin
from .models import *

class  RotaInline(admin.TabularInline):
    model = Rota
    extra = 0

class TrechoInline(admin.TabularInline):
    model = TrechoViagem
    extra = 0

@admin.register(Municipio)
class MunicipioAdmin(admin.ModelAdmin):
    search_fields = ['nome']
    list_display = ['nome','codigo_ibge','ofertado_pelo_sistema']
    list_filter = ['gestor']
    ordering = ['nome']

@admin.register(Bus)
class BusAdmin(admin.ModelAdmin):
    list_display = ['name','license_plate','is_active']

@admin.register(BusStop)
class BusStopAdmin(admin.ModelAdmin):
    search_fields = ['name']
    ordering = ['name']
    list_display = ['name','city','is_active']

@admin.register(Institution)
class InstitutionAdmin(admin.ModelAdmin):
    search_fields = ['name']
    ordering = ['name']
    list_display = ['name','city','is_active']

# Register your models here.
@admin.register(Linha)
class LinhaAdmin(admin.ModelAdmin):
    search_fields = ['nome']
    ordering = ['nome']
    list_display = ['nome','city','horario_inicio','horario_fim','is_active']
    inlines = [
        RotaInline
    ]    
@admin.register(Rota)
class RotaAdmin(admin.ModelAdmin):
    list_display = ['nome','linha','direcao']
        
    inlines = [TrechoInline]

@admin.register(TrechoViagem)
class TrechoViagemAdmin(admin.ModelAdmin):
    list_display = ['parada_inicio','parada_fim','ordem','distancia_km']
    ordering = ['ordem']