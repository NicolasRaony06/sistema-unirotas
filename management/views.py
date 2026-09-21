from django.http import HttpResponse, JsonResponse
from .models import *
from authentication.models import UserRole
from .handlers import cadastrar_municipio
# Create your views here.

def municipio(request):
    if request.user.role == UserRole.ADMIN:
        nome = request.GET.get('nome')
        cod_ibge = request.GET.get('codigo_ibge')
        e_ofertado = True
        cadastrar_municipio(nome=nome,codigo_ibge=cod_ibge,ofertado_pelo_sistema=e_ofertado)
    elif request.user.role == UserRole.MANAGER:
        nome = request.GET.get('nome')
        cod_ibge = request.GET.get('codigo_ibge')
        e_ofertado = False
        cadastrar_municipio(nome=nome,codigo_ibge=cod_ibge,ofertado_pelo_sistema=e_ofertado)
    else:
        return HttpResponse("Você não tem permissão para cadastrar município.", status=403)
    
    return HttpResponse(f"Municipio criado com sucesso por: {request.user.role}")


