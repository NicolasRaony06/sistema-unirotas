from django.shortcuts import render, redirect
from django.contrib import messages
from datetime import datetime
from django.http import HttpResponse, JsonResponse
from .models import *
from authentication.models import UserRole, PersonelProfile
from authentication.service import generate_elevated_signup_link
from .forms import BusForm
from .handlers import cadastrar_municipio
# Create your views here.

def home(request):
    return render(request,'home.html',{
        'full_name' : request.user.full_name,
        'data': datetime.now(),
        'role': request.user.role,
    })

def criar_municipio(request):
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

#TODO adicionar login e keven decorador
def invite_driver(request):
    #TODO alterar por decorator de keven
    if request.user.role != UserRole.MANAGER:
        messages.error(request, "Você precisa estar logado como um gestor para ter acesso.")
        return redirect('management:home')

    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        confirm_email = request.POST.get('confirm_email', '').strip()

        if not email == confirm_email:
            messages.error(request, "Os emails informados não são iguais.")
            return render(request, "invite_driver.html")

        link = generate_elevated_signup_link(
            higher_role_email=request.user.email,
            email=email,
            role=UserRole.DRIVER,
            request=request
        )

        if link:
            messages.success(request, f'Convite enviado com sucesso para {email}.')
            return render(request, "invite_driver.html")
        else:
            messages.error(request, f"Não foi possível enviar o convite para {email}.")

    return render(request, "invite_driver.html")

#TODO adicionar login e keven decorador
def register_bus(request):
    if request.user.role != UserRole.MANAGER:
        messages.error(request, "Você precisa estar logado como um gestor para ter acesso.")
        return redirect('management:home')
    
    if request.method == 'POST':
        form = BusForm(request.POST)
        if form.is_valid():
            bus = form.save(commit=False)
            bus.city = request.user.personel_profile.city
            bus.save()
            return redirect('management:home')
        
        messages.error(request, "Ocorreu um erro ao tentar cadastrar o ônibus. Tente novamente.")
    else:
        form = BusForm()
    return render(request, "register_bus.html", {'form': form})