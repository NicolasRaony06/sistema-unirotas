from .models import Municipio
from authentication.models import User


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

def can_manage_model(manager_city, model_instance):
    '''Receives the manager city and a model instance. Returns true or false if the model can be manageble.'''
    related_cities = manager_city.municipios_relacionados.filter(
        ofertado_pelo_sistema=False
    ).values_list('id', flat=True)

    return model_instance.city.id in related_cities or model_instance.city == manager_city

