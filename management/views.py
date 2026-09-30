from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.urls import reverse_lazy
from datetime import datetime
from django.http import HttpResponse, JsonResponse
from .models import *
from authentication.models import UserRole, PersonelProfile
from authentication.service import generate_elevated_signup_link
from authentication.decorators import role_required
from .forms import BusForm, MunicipioForm
from .handlers import cadastrar_municipio
from .handlers import *
# Create your views here.
@login_required
def home(request):
    municipios = Municipio.objects.count()
    estudantes = User.objects.filter(role=UserRole.STUDENT).count()
    return render(request,'home.html',{
        'estudantes':estudantes,
        'municipios': municipios,
        'full_name' : request.user.full_name,
        'data': datetime.now(),
        'role': request.user.role,
        'profile_picture': request.user.profile_picture
    })
@login_required
def home_manager(request):
    municipios = Municipio.objects.count()
    estudantes = User.objects.filter(role=UserRole.STUDENT).count()
    return render(request,'home_manager.html',{
        'estudantes':estudantes,
        'municipios': municipios,
        'full_name' : request.user.full_name,
        'data': datetime.now(),
        'role': request.user.role,
        'profile_picture': request.user.profile_picture
    })

@login_required
def gestores(request):
    gestores = User.objects.filter(role=UserRole.MANAGER)
    gestores_inativos = User.objects.filter(role = UserRole.MANAGER,is_active=False).count()
    total_gestores = User.objects.filter(role=UserRole.MANAGER).count() 
    return render(request,'gestores.html',{
        'gestores': gestores,
        'gestores_inativos': gestores_inativos,
        'total_gestores': total_gestores,
        'full_name' : request.user.full_name,
        'role': request.user.role,
        'profile_picture': request.user.profile_picture
    })


@login_required
def municipios(request):
        municipios = Municipio.objects.all()
        tot_municipios = Municipio.objects.all().count()
        gestores = User.objects.filter(role=UserRole.MANAGER)
        return render(request,'municipios.html',{
        'tot_municipios': tot_municipios,
        'municipios': municipios,
        'gestores':gestores,
        'full_name' : request.user.full_name,
        'role': request.user.role,
        'profile_picture': request.user.profile_picture
    })



@login_required
def criar_municipio(request):
    if request.method == 'POST':
        form = MunicipioForm(request.POST)

        if form.is_valid():
            nome = form.cleaned_data['nome']
            cod_ibge =form.cleaned_data['codigo_ibge']
            #gestor =form.cleaned_data['gestor']

            if request.user.role == UserRole.ADMIN:
                e_ofertado = True
                #form.save()
                cadastrar_municipio(nome=nome,codigo_ibge=cod_ibge,ofertado_pelo_sistema=e_ofertado)#''',gestor=gestor'''
                return redirect('management:municipios')

            '''def home_manager(request):
                return render(request,'home_manager.html',{
                    'full_name' : request.user.full_name,
                    'data': datetime.now(),
                    'role': request.user.role,
                    'profile_picture': request.user.profile_picture
                })
            '''
            '''elif request.user.role == UserRole.MANAGER:
                e_ofertado = False
                municipio_base = request.user.municipio.first()

                if municipio_base is None:
                    return HttpResponse("Você não esta associado a nenhum municipio")
                else:
                    municipio_criado, *_ = cadastrar_municipio(nome=nome,codigo_ibge=cod_ibge,ofertado_pelo_sistema=e_ofertado)
                    municipio_base.municipios_relacionados.add(municipio_criado)
                    return redirect('management:home-manager')'''
        else:
            return render(request, 'cadastro_municipio.html', {'erro': 'Dados inválidos'})
    else:
        form = MunicipioForm()
    return render(request, 'cadastro_municipio.html', {'form': form})

@login_required
def associar_gestor(request):
    if request.user.role == UserRole.ADMIN:
        if request.method == 'POST':
            codigo_ibge = request.POST.get('codigo_ibge')
            email_gestor = request.POST.get('email_gestor')

            municipio_buscado = Municipio.objects.filter(codigo_ibge=codigo_ibge).first()
            email_buscado = User.objects.filter(role=UserRole.MANAGER,email=email_gestor).first()

            if municipio_buscado is None or email_buscado is None:
                return HttpResponse("Dados não encontrados")
            atualizar_gestor(codigo_ibge=codigo_ibge,email_gestor=email_gestor)
            return redirect('management:municipios') #Poderia ser uma mensagem de sucesso
        
    return render(request,'test.html')

@login_required(login_url=reverse_lazy('authentication:login'))
@role_required(allowed_roles=UserRole.MANAGER)
def invite_driver(request):
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

@login_required(login_url=reverse_lazy('authentication:login'))
@role_required(allowed_roles=UserRole.MANAGER)
def view_drivers(request):
    drivers = PersonelProfile.objects.filter(
        user__role=UserRole.DRIVER, 
        city=request.user.personel_profile.city
    )
    return render(request, 'view_drivers.html', {'drivers': drivers})

@login_required(login_url=reverse_lazy('authentication:login'))
@role_required(allowed_roles=UserRole.MANAGER)
def edit_driver(request, id):
    pass

@login_required(login_url=reverse_lazy('authentication:login'))
@role_required(allowed_roles=UserRole.MANAGER)
def deactivate_driver(request, id):
    if request.method == 'POST':
        driver_profile = get_object_or_404(
            PersonelProfile,
            id=id,
            user__role=UserRole.DRIVER,
            city=request.user.personel_profile.city
        )
        driver_user = driver_profile.user
        if driver_user.is_active:
            driver_user.is_active = False
            driver_user.save()
            messages.success(request, f"Motorista {driver_user.full_name} desativado com sucesso.")
    return redirect('management:view_drivers')

@login_required(login_url=reverse_lazy('authentication:login'))
@role_required(allowed_roles=UserRole.MANAGER)
def activate_driver(request, id):
    if request.method == 'POST':
        driver_profile = get_object_or_404(
            PersonelProfile,
            id=id,
            user__role=UserRole.DRIVER,
            city=request.user.personel_profile.city
        )
        driver_user = driver_profile.user
        if not driver_user.is_active:
            driver_user.is_active = True
            driver_user.save()
            messages.success(request, f"Motorista {driver_user.full_name} ativado com sucesso.")
    return redirect('management:view_drivers')

@login_required(login_url=reverse_lazy('authentication:login'))
@role_required(allowed_roles=UserRole.MANAGER)
def register_bus(request):
    if not request.user.personel_profile.city.ofertado_pelo_sistema:
        messages.error(request, "Não é possível cadastrar ônibus para um Município não ativo.")
        return redirect('management:home-manager')

    if request.method == 'POST':
        form = BusForm(request.POST, request.FILES)
        if form.is_valid():
            bus = form.save(commit=False)
            bus.city = request.user.personel_profile.city
            bus.save()
            return redirect('management:home-manager')

        messages.error(request, "Ocorreu um erro ao tentar cadastrar o ônibus. Tente novamente.")
    else:
        form = BusForm()
    return render(request, "register_bus.html", {'form': form})

@login_required(login_url=reverse_lazy('authentication:login'))
@role_required(allowed_roles=UserRole.MANAGER)
def view_buses(request):
    buses = Bus.objects.filter(city=request.user.personel_profile.city)
    return render(request, "view_buses.html", {'buses': buses})

@login_required(login_url=reverse_lazy('authentication:login'))
@role_required(allowed_roles=UserRole.MANAGER)
def edit_bus(request, id):
    bus = get_object_or_404(
        Bus,
        id=id,
        city=request.user.personel_profile.city
    )
    if request.method == 'POST':
        form = BusForm(request.POST, request.FILES, instance=bus)
        if form.is_valid():
            form.save()
            messages.success(request, f"Ônibus {bus.name} alterado com sucesso.")
            return redirect("management:view_buses")
        messages.error(request, f"Erro ao tentar alterar ônibus {bus.name}")
    else:
        form = BusForm(instance=bus)
    return render(request, 'edit_bus.html', {'form': form})

@login_required(login_url=reverse_lazy('authentication:login'))
@role_required(allowed_roles=UserRole.MANAGER)
def deactivate_bus(request, id):
    if request.method == 'POST':
        bus = get_object_or_404(
            Bus,
            id=id,
            city=request.user.personel_profile.city
        )

        if bus.is_active:
            bus.is_active = False
            bus.save()
            messages.success(request, f"Ônibus {bus.name} desativado com sucesso.")
    return redirect('management:view_buses')

@login_required(login_url=reverse_lazy('authentication:login'))
@role_required(allowed_roles=UserRole.MANAGER)
def activate_bus(request, id):
    if request.method == 'POST':
        bus = get_object_or_404(
            Bus,
            id=id,
            city=request.user.personel_profile.city
        )

        if not bus.is_active:
            bus.is_active = True
            bus.save()
            messages.success(request, f"Ônibus {bus.name} ativado com sucesso.")
    return redirect('management:view_buses')

@login_required
def homologar_mun(request):
    if request.user.role == UserRole.ADMIN:
        codigo_ibge = request.GET.get('codigo_ibge')
        municipio_buscado = Municipio.objects.filter(codigo_ibge=codigo_ibge).first()
        if municipio_buscado is None:
            return HttpResponse("Municipio não encontrado")
        mun = homologar_municipio(codigo_ibge=codigo_ibge)
        return HttpResponse(f"Municipio {mun} homologado")
    return HttpResponse("Sem permissão para realizar essa terefa")

@login_required
def desabilitar_mun(request):
    if request.user.role == UserRole.ADMIN:
        codigo_ibge = request.GET.get('codigo_ibge')
        municipio_buscado = Municipio.objects.filter(codigo_ibge=codigo_ibge).first()
        if municipio_buscado is None:
            return HttpResponse("Municipio não encontrado")
        mun = desabilitar_municipio(codigo_ibge=codigo_ibge)
        return HttpResponse(f"Municipio {mun} desabilitado")
    return HttpResponse("Sem permissão para realizar essa terefa")

@login_required
def listar_municipios(request):
    if request.user.role != UserRole.ADMIN:
        return HttpResponse("Sem permissão para realizar essa tarefa", status=403)

    municipios = list(Municipio.objects.values('nome', 'codigo_ibge', 'ofertado_pelo_sistema', 'gestor__email'))
    return JsonResponse(municipios, safe=False, json_dumps_params={'ensure_ascii': False})
