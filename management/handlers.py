from .models import Municipio
from authentication.models import User
def cadastrar_municipio(codigo_ibge,**dados_restantes): #se existir mostra se nÃo, cria
    municipio, criado = Municipio.objects.get_or_create(codigo_ibge=codigo_ibge,defaults=dados_restantes)

    return municipio, criado

def homologar_municipio(codigo_ibge):
    municipio = Municipio.objects.filter(codigo_ibge=codigo_ibge).first()
    if not municipio:
        return None
    
    municipio.ofertado_pelo_sistema = True
    municipio.save()
    return municipio

def desabilitar_municipio(codigo_ibge):
    municipio = Municipio.objects.filter(codigo_ibge=codigo_ibge).first()
    if not municipio:
        return None
    
    municipio.ofertado_pelo_sistema = False
    municipio.save()
    return municipio

def atualizar_gestor(codigo_ibge,email_gestor=None):
    municipio = Municipio.objects.filter(codigo_ibge=codigo_ibge).first()
    if not municipio:
        return None
    
    if email_gestor :
        gestor = User.objects.filter(email=email_gestor).first()
        municipio.gestor = gestor
    else:
        municipio.gestor = None
    municipio.save()

    return municipio
