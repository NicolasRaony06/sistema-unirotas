from .models import Municipio
def cadastrar_municipio(codigo_ibge,**dados_restantes):
    municipio, criado = Municipio.objects.get_or_create(codigo_ibge=codigo_ibge,defaults= dados_restantes)

    return municipio, criado