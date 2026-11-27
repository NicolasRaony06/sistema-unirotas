<<<<<<< HEAD
from .models import Municipio
from authentication.models import PersonelProfile
=======
import qrcode
import io
import base64
from django.contrib import messages

# from .models import Municipio
# from authentication.models import User
>>>>>>> 9840d49107438175e7a2701bfe1c39c90150a7e0


# def atualizar_gestor(codigo_ibge,email_gestor=None):
#     municipio = Municipio.objects.filter(codigo_ibge=codigo_ibge).first()
#     if not municipio:
#         return None
    
<<<<<<< HEAD
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
=======
#     if email_gestor :
#         #se houver gestor antes o personel_profile dele perde também a referencia a cidade
#         if municipio.gestor:
#             municipio.gestor.personel_profile.city = None
#             municipio.gestor.personel_profile.save()

#         gestor = User.objects.filter(email=email_gestor).first()
#         municipio.gestor = gestor
#         gestor.personel_profile.city = municipio
#         gestor.personel_profile.save()
#     else:
#         gestor = municipio.gestor
#         municipio.gestor = None
#         gestor.personel_profile.city = None
#         gestor.personel_profile.save()       
#     municipio.save()
>>>>>>> 9840d49107438175e7a2701bfe1c39c90150a7e0

#     return municipio

def can_manage_model(manager_city, model_instance):
    '''Receives the manager city and a model instance. Returns true or false if the model can be manageble.'''
    related_cities = manager_city.municipios_relacionados.filter(
        ofertado_pelo_sistema=False
    ).values_list('id', flat=True)

    return model_instance.city.id in related_cities or model_instance.city == manager_city

def generate_qrcode(link):
    if not link:
        return None
            
    qr = qrcode.make(link)

    with io.BytesIO() as buffer:
        qr.save(buffer, format='png')
        img_str = base64.b64encode(buffer.getvalue()).decode("utf-8")

    return f"data:image/png;base64,{img_str}"




