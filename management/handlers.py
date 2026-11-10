from .models import Municipio
from authentication.models import PersonelProfile


def atualizar_gestor(codigo_ibge,email_gestor=None):
    municipio = Municipio.objects.filter(codigo_ibge=codigo_ibge).first()
    if not municipio:
        return None
    
    if email_gestor :
        #se houver gestor antes o personel_profile dele perde também a referencia a cidade
        if municipio.gestor:
            municipio.gestor.city = None
            municipio.gestor.save()

        gestor = PersonelProfile.objects.filter(user__email=email_gestor).first()
        municipio.gestor = gestor
        gestor.city = municipio
        gestor.save()
    else:
        gestor = municipio.gestor
        municipio.gestor = None
        gestor.city = None
        gestor.save()       
    municipio.save()

    return municipio

def can_manage_model(manager_city, model_instance):
    '''Receives the manager city and a model instance. Returns true or false if the model can be manageble.'''
    related_cities = manager_city.municipios_relacionados.filter(
        ofertado_pelo_sistema=False
    ).values_list('id', flat=True)

    return model_instance.city.id in related_cities or model_instance.city == manager_city

