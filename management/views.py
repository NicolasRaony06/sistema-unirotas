from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.urls import reverse_lazy, reverse
from datetime import datetime
from django.http import HttpResponse, JsonResponse
from django.db.models import Q
from .models import *
from authentication.models import UserRole, PersonelProfile
from authentication.service import generate_elevated_signup_link
from authentication.decorators import role_required
from .forms import BusForm, MunicipioForm, BusStopForm, InstitutionForm, LinhaForm, RotaForm, TrechoViagemForm
import copy
from .handlers import *

@login_required
@role_required(allowed_roles=[UserRole.ADMIN, UserRole.MANAGER])
def home(request):
    user_role = request.user.role
    if user_role == UserRole.ADMIN:
        template_name = "admin/home.html"
        
    elif user_role == UserRole.MANAGER:
        template_name = "manager/home.html"

    context = {
        'linhas': Linha.objects.all(),
        'motoristas':User.objects.filter(role=UserRole.DRIVER).count(),
        'onibus': Bus.objects.all().count(),
        'estudantes':User.objects.filter(role=UserRole.STUDENT).count(),
        'municipios': Municipio.objects.all().count(),
        'full_name' : request.user.full_name,
        'data': timezone.now(),
    }

    return render(request, template_name, context)

@login_required
@role_required(allowed_roles=UserRole.ADMIN)
def gestores(request):

    context = {
    'gestores': User.objects.filter(role=UserRole.MANAGER),
    'gestores_inativos': User.objects.filter(role = UserRole.MANAGER,is_active=False).count(),
    'total_gestores' :User.objects.filter(role=UserRole.MANAGER).count(),
    }

    return render(request,'admin/gestores.html',context)

@login_required
@role_required(allowed_roles=UserRole.ADMIN)
def municipios(request):
        
        context = {
        'linhas': Linha.objects.filter(is_active=True),
        'total_onibus' : Bus.objects.all().count(),
        'municipios_ofertados' : Municipio.objects.filter(ofertado_pelo_sistema = True),
        'municipios' : Municipio.objects.all(),
        'tot_municipios' : Municipio.objects.all().count(),
        'gestores' : User.objects.filter(role=UserRole.MANAGER),
        'gestores_ativos' : User.objects.filter(role=UserRole.MANAGER, is_active=True),
        }

        return render(request,'admin/municipios.html',context)


@login_required
@role_required(allowed_roles=UserRole.ADMIN)
def criar_municipio(request):
    if request.method == 'POST':
        form = MunicipioForm(request.POST)

        if form.is_valid():
            municipio = form.save(commit=False)
            
            if request.user.role == UserRole.ADMIN:
                municipio.ofertado_pelo_sistema = True
                municipio.save()
                return redirect('management:municipios')
        else:
            return render(request, 'admin/cadastro_municipio.html', {'erro': 'Dados inválidos'})
    else:
        form = MunicipioForm()
    return render(request, 'admin/cadastro_municipio.html', {'form': form})

@login_required
@role_required(allowed_roles=UserRole.MANAGER)
def adicionar_municipio(request):
    if request.method == 'POST':
        form = MunicipioForm(request.POST)

        if form.is_valid():
            municipio = form.save(commit=False)

            if request.user.role == UserRole.MANAGER:
                municipio.ofertado_pelo_sistema = False
                municipio.save()

                municipio_gestor = Municipio.objects.filter(gestor=request.user).first()
                municipio_gestor.municipios_relacionados.add(municipio)
                return redirect('management:localizacoes')
        else:
            return render(request, 'manager/cadastro_municipio.html', {'erro': 'Dados inválidos'})
    else:
        form = MunicipioForm()
    return render(request, 'manager/cadastro_municipio.html', {'form': form})

@login_required
@role_required(allowed_roles=UserRole.ADMIN)
def associar_gestor(request):
    if request.method == 'POST':
        codigo_ibge = request.POST.get('codigo_ibge')
        email_gestor = request.POST.get('email_gestor')
        
        municipio_buscado = Municipio.objects.filter(codigo_ibge=codigo_ibge).first()
        email_buscado = User.objects.filter(role=UserRole.MANAGER,email=email_gestor).first()

        if municipio_buscado is None or email_buscado is None:
            return HttpResponse("Dados não encontrados")
        
        atualizar_gestor(codigo_ibge=codigo_ibge,email_gestor=email_gestor)
        return redirect('management:municipios') #Poderia ser uma mensagem de sucesso
    
    return redirect('management:municipios')


@login_required
@role_required(allowed_roles=UserRole.ADMIN)
def homologar_mun(request,id):
    if request.method == 'POST':
        #codigo_ibge = request.GET.get('codigo_ibge')
        municipio_buscado = Municipio.objects.filter(id=id).first()
        if municipio_buscado is None:
            return HttpResponse("Municipio não encontrado")
        municipio_buscado.ofertado_pelo_sistema = True
        municipio_buscado.save()
        return redirect('management:municipios')
    
    return redirect('management:municipios')

@login_required
@role_required(allowed_roles=UserRole.ADMIN)
def desabilitar_mun(request,id):
    if request.method == 'POST':
        #codigo_ibge = request.GET.get('codigo_ibge')
        municipio_buscado = Municipio.objects.filter(id=id).first()
        if municipio_buscado is None:
            return HttpResponse("Municipio não encontrado")
        municipio_buscado.ofertado_pelo_sistema = False
        municipio_buscado.save()
        #mun = desabilitar_municipio(codigo_ibge=codigo_ibge)
        # return HttpResponse(f"Municipio {municipio_buscado} desabilitado")
        return redirect('management:municipios')
    
    return redirect('management:municipios')

@login_required
@role_required(allowed_roles=UserRole.MANAGER)
def localizacoes(request):
   
    municipio_base = Municipio.objects.filter(gestor = request.user).first()
    
    if not municipio_base: 
        return render(request, 'manager/localizacoes.html', {
            'total_municipios': 0,
        })
    else:
        tot_municipios = municipio_base.municipios_relacionados.exclude(municipios_relacionados=municipio_base.pk).count() 
        municipios = municipio_base.municipios_relacionados.exclude(municipios_relacionados=municipio_base.pk)
        return render(request, 'manager/localizacoes.html', {
                    
                    'municipio': municipio_base,
                    'total_municipios': tot_municipios,
                    'municipios': municipios,
                })


@login_required
@role_required(allowed_roles=UserRole.ADMIN)
def deactive_manager(request,id):
    if request.method == 'POST':
        manager = User.objects.filter(role=UserRole.MANAGER ,id=id).first()
        manager.is_active = False
        manager.save()
    return redirect('management:gestores')

@login_required
@role_required(allowed_roles=UserRole.ADMIN)
def activate_manager(request,id):
    if request.method == 'POST':
        manager = User.objects.filter(role=UserRole.MANAGER, id=id).first()
        manager.is_active = True
        manager.save()
    return redirect('management:gestores')

@login_required(login_url=reverse_lazy('authentication:login'))
@role_required(allowed_roles=UserRole.MANAGER)
def invite_driver(request):
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        confirm_email = request.POST.get('confirm_email', '').strip()

        if not email == confirm_email:
            messages.error(request, "Os emails informados não são iguais.")
            return render(request, "manager/invite_driver.html")

        link = generate_elevated_signup_link(
            higher_role_email=request.user.email,
            email=email,
            role=UserRole.DRIVER,
            request=request
        )

        if link:
            messages.success(request, f'Convite enviado com sucesso para {email}.')
            return render(request, "manager/invite_driver.html")
        else:
            messages.error(request, f"Não foi possível enviar o convite para {email}.")

    return render(request, "manager/invite_driver.html")

@login_required
@role_required(allowed_roles=UserRole.MANAGER)
def view_drivers(request):
    drivers = PersonelProfile.objects.filter(
        user__role=UserRole.DRIVER, 
        city=request.user.personel_profile.city
    )

    return render(request, 'manager/view_drivers.html', {'drivers': drivers})

@login_required
@role_required(allowed_roles=UserRole.MANAGER)
def edit_driver(request, id):
    pass

@login_required
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

@login_required
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

@login_required
@role_required(allowed_roles=UserRole.MANAGER)
def register_bus(request):
    if not request.user.personel_profile.city.ofertado_pelo_sistema:
        messages.error(request, "Não é possível cadastrar ônibus para um Município não ativo.")
        return redirect('management:home')

    if request.method == 'POST':
        form = BusForm(request.POST, request.FILES)
        if form.is_valid():
            bus = form.save(commit=False)
           # bus.city = request.user.personel_profile.city
           # bus.save()
            city =  request.user.personel_profile.city
            bus.city = city
            bus.save()

            return redirect('management:view_buses')

        messages.error(request, "Ocorreu um erro ao tentar cadastrar o ônibus. Tente novamente.")
    else:
        form = BusForm()
    return render(request, "manager/register_bus.html", {'form': form})

@login_required
@role_required(allowed_roles=UserRole.MANAGER)
def view_buses(request):
    buses = Bus.objects.filter(city=request.user.personel_profile.city)
    return render(request, "manager/view_buses.html", {'buses': buses})

@login_required
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
    return render(request, 'manager/edit_bus.html', {'form': form})

@login_required
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

@login_required
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
@role_required(allowed_roles=UserRole.MANAGER)
def register_bus_stop(request):
    if request.method == 'POST':
        form = BusStopForm(request.POST,city=request.user.personel_profile.city)
        if form.is_valid():
            form.save()
            messages.success(request, f"Parada de ônibus foi cadastrada com sucesso.")
            return redirect('management:view_bus_stops')
        messages.error(request, "Não foi possível cadastrar a parada de ônibus.")
    else:
        form = BusStopForm(city=request.user.personel_profile.city)
    return render(request, "manager/register_bus_stop.html", {'form': form})

@login_required
@role_required(allowed_roles=UserRole.MANAGER)
def view_bus_stops(request):
    city = request.user.personel_profile.city

    related_cities = []
    filter_ocult_related_cities = request.GET.get('ocult_related_cities')
    if not filter_ocult_related_cities: 
        related_cities = city.municipios_relacionados.all()

    bus_stops = BusStop.objects.filter(
        Q(city__in=related_cities)
    ).select_related('city').distinct()

    return render(request, 'manager/view_bus_stops.html', {'bus_stops': bus_stops})

@login_required
@role_required(allowed_roles=UserRole.MANAGER)
def edit_bus_stop(request, id):
    city = request.user.personel_profile.city
    bus_stop = get_object_or_404(
        BusStop,
        id=id
    )

    if not can_manage_model(city, bus_stop):
        messages.error(request, f"Não é possível alterar a parada {bus_stop.name}, pois ela pertence a um outro município ofertado pelo sistema.")
        return redirect('management:view_bus_stops')
    
    if request.method == 'POST':
        form = BusStopForm(request.POST, instance=bus_stop, city=city)
        if form.is_valid():
            form.save()
            messages.success(request, "Parada alterada com sucesso.")
            return redirect("management:view_bus_stops")
        messages.error(request, "Não foi possível alterar a parada")
    else:
        form = BusStopForm(instance=bus_stop, city=city)
    return render(request, 'manager/edit_bus_stop.html', {'form': form})

@login_required
@role_required(allowed_roles=UserRole.MANAGER)
def deactivate_bus_stop(request, id):
    if request.method == 'POST':
        city = request.user.personel_profile.city
        bus_stop = get_object_or_404(
            BusStop,
            id=id
        )

        if not can_manage_model(city, bus_stop):
            messages.error(request, f"Não é possível desativar a parada {bus_stop.name}, pois ela pertence a um outro município ofertado pelo sistema.")
            return redirect('management:view_bus_stops')

        if bus_stop.is_active:
            bus_stop.is_active = False
            bus_stop.save()
            messages.success(request, f"Parada {bus_stop.name} desativada com sucesso.")
    return redirect('management:view_bus_stops')

@login_required
@role_required(allowed_roles=UserRole.MANAGER)
def activate_bus_stop(request, id):
    if request.method == 'POST':
        city = request.user.personel_profile.city
        bus_stop = get_object_or_404(
            BusStop,
            id=id
        )

        if not can_manage_model(city, bus_stop):
            messages.error(request, f"Não é possível ativar a parada {bus_stop.name}, pois ela pertence a um outro município ofertado pelo sistema.")
            return redirect('management:view_bus_stops')

        if not bus_stop.is_active:
            bus_stop.is_active = True
            bus_stop.save()
            messages.success(request, f"Parada {bus_stop.name} ativada com sucesso.")
    return redirect('management:view_bus_stops')


@login_required
@role_required(allowed_roles=UserRole.MANAGER)
def register_institution(request):
    city = request.user.personel_profile.city
    if request.method == 'POST':
        form = InstitutionForm(request.POST, city=city)
        if form.is_valid():
            form.save()
            messages.success(request, "Instituição cadastrada com sucesso.")
            return redirect("management:view_institutions")
        messages.error(request, "Não foi possível cadastrar instituição.")
    else:
        form = InstitutionForm(city=city)
    return render(request, 'manager/register_institution.html', {'form': form})

@login_required
@role_required(allowed_roles=UserRole.MANAGER)
def view_institutions(request):
    city = request.user.personel_profile.city

    related_cities = []
    filter_ocult_related_cities = request.GET.get('ocult_related_cities')
    if not filter_ocult_related_cities: 
        related_cities = city.municipios_relacionados.all()

    institutions = Institution.objects.filter(
        Q(city__in=related_cities)
    ).select_related('city').distinct()
    
    return render(request, 'manager/view_institutions.html', {'institutions': institutions})

@login_required
@role_required(allowed_roles=UserRole.MANAGER)
def deactivate_institution(request, id):
    if request.method == 'POST':
        city = request.user.personel_profile.city

        institution = get_object_or_404(
            Institution,
            id=id
        )

        if not can_manage_model(city, institution):
            messages.error(request, f"Não é possível desativar a instituição {institution.name}, pois ela pertence a um outro município ofertado pelo sistema.")
            return redirect('management:view_institutions')
        
        if institution.is_active:
            institution.is_active = False
            institution.save()
            messages.success(request, f"Instituição {institution.name} desativada com sucesso.")

    return redirect('management:view_institutions')

@login_required
@role_required(allowed_roles=UserRole.MANAGER)
def activate_institution(request, id):
    if request.method == 'POST':
        city = request.user.personel_profile.city

        institution = get_object_or_404(
            Institution,
            id=id
        )

        if not can_manage_model(city, institution):
            messages.error(request, f"Não é possível ativar a instituição {institution.name}, pois ela pertence a um outro município ofertado pelo sistema.")
            return redirect('management:view_institutions')

        if not institution.is_active:
            institution.is_active = True
            institution.save()
            messages.success(request, f"Instituição {institution.name} ativada com sucesso.")
    return redirect('management:view_institutions')

@login_required
@role_required(allowed_roles=UserRole.MANAGER)
def inativar_linha(request, id):
    if request.method == 'POST':
        linha = Linha.objects.filter(id=id).first()
        if  linha.is_active:
            linha.is_active = False
            linha.save()
    return redirect('management:linhas')

@login_required
@role_required(allowed_roles=UserRole.MANAGER)
def ativar_linha(request, id):
    if request.method == 'POST':
        linha = Linha.objects.filter(id=id).first()
        if  linha.is_active == False:
            linha.is_active = True
            linha.save()
    return redirect('management:linhas')

@login_required
@role_required(allowed_roles=UserRole.MANAGER)
def edit_institution(request, id):
    city = request.user.personel_profile.city
    institution = get_object_or_404(
        Institution,
        id=id
    )

    if not can_manage_model(city, institution):
        messages.error(request, f"Não é possível alterar a instituição {institution.name}, pois ela pertence a um outro município ofertado pelo sistema.")
        return redirect('management:view_institutions')

    if request.method == 'POST':
        form = InstitutionForm(request.POST, instance=institution, city=city)
        if form.is_valid():
            form.save()
            messages.success(request, "Instituição alterada com sucesso.")
            return redirect('management:view_institutions')
        messages.error(request, "Não foi possível alterar a instituição.")
    else:
        form = InstitutionForm(instance=institution, city=city)
    return render(request, 'manager/edit_institution.html', {'form': form})

@login_required
@role_required(allowed_roles=UserRole.MANAGER)
def retirar_municipio(request,id):
    if request.method == 'POST':
        municipio_pai = Municipio.objects.filter(gestor= request.user).first()
        municipio_listado = Municipio.objects.filter(id=id).first()
        municipio_pai.municipios_relacionados.remove(municipio_listado)
    return redirect('management:localizacoes')

@login_required
@role_required(allowed_roles=UserRole.MANAGER)
def criar_linha(request):
    if request.method == 'POST':
        form = LinhaForm(request.POST)
        if not form.is_valid():
            print("ERROS DO FORMULÁRIO:", form.errors)
        if form.is_valid():
            a = form.save(commit=False)
            a.city = request.user.personel_profile.city
            a.save()
            form.save_m2m()
           #  return redirect('management:view_institutions')
            return redirect('management:criar-rota',linha_id=a.id)
    else:
        form = LinhaForm()

    cidades_relacionadas = []
    cidades_relacionadas = request.user.personel_profile.city.municipios_relacionados.all()
    motoristas = User.objects.filter(role=UserRole.DRIVER,personel_profile__city=request.user.personel_profile.city,is_active=True,)
    instituicoes = Institution.objects.filter(city__in=cidades_relacionadas)
    contexto = {'form': form,'instituicoes':instituicoes,'motoristas':motoristas}
    
    return render(request, 'manager/criar_linha.html', contexto)

@login_required
@role_required(allowed_roles=UserRole.MANAGER)
def criar_rota(request,linha_id):
    if request.method == 'POST':
        form = RotaForm(request.POST,prefix='Ida')
        form2 = RotaForm(request.POST,prefix='Volta')
        if form.is_valid() :
            Ida = form.save(commit=False)
            linha = get_object_or_404(Linha,id=linha_id)
            Ida.linha = linha
            Ida.save()
        if form2.has_changed() and form2.is_valid():
            Volta = form2.save(commit=False)
            Volta.linha = linha
            Volta.save()
        return redirect('management:criar-trecho',rota_id=Ida.id)
    else:
        form = RotaForm(prefix='Ida')
        form2 = RotaForm(prefix='Volta')

    onibus = Bus.objects.filter(city=request.user.personel_profile.city)
    return render(request,'manager/criar_rota.html',{'form':form, 'form2': form2,'onibus':onibus})

@login_required
@role_required(allowed_roles=UserRole.MANAGER)
def linhas(request):
    context = {
        'linhas': Linha.objects.all(),

    }
    return render(request,'manager/linhas.html',context)


@login_required
@role_required(allowed_roles=UserRole.MANAGER)
def criar_trecho(request,rota_id):
    if request.method == 'POST':
        form = TrechoViagemForm(request.POST)
        if form.is_valid():
            trecho = form.save(commit=False)
            rota = get_object_or_404(Rota, id=rota_id)
            trecho.rota = rota
            trecho.save()

            linha = rota.linha
            rota_volta = Rota.objects.filter(linha=linha, direcao="VOLTA").first()

            if rota_volta is not None:
                trecho_volta = trecho
                trecho_volta.pk = None
                trecho_volta.id = None
                trecho_volta.rota = rota_volta
                trecho_volta.save()

    # if request.method == 'POST':
    #     form = TrechoViagemForm(request.POST)
    #     if form.is_valid():
    #         trecho = form.save(commit=False)
    #         rota = get_object_or_404(Rota,id=rota_id)
    #         trecho.rota = rota
    #         trecho.save()


    #         trecho.pk = None
    #         trecho.id = None

    #         linha = rota.linha
    #         rota_volta = Rota.objects.filter(linha=linha,direcao="VOLTA").first()
    #         if rota_volta is not None:
    #             trecho2 = form.save(commit=False)
    #             trecho2.rota = rota_volta
    #             trecho2.save()
          
            return redirect('management:criar-trecho',rota_id=rota.id)
    else:
        form = TrechoViagemForm()
    trechos = TrechoViagem.objects.filter(rota__id=rota_id)
    cidades_relacionadas = []
    cidades_relacionadas = request.user.personel_profile.city.municipios_relacionados.all()
    paradas = BusStop.objects.filter(city__in=cidades_relacionadas)
    return render(request,'manager/criar_trecho.html',{'form':form,'trechos':trechos,'paradas':paradas})

@login_required
@role_required(allowed_roles=UserRole.MANAGER)
def excluir_trecho(request,id):
    if request.method == 'POST':
        trecho = get_object_or_404(TrechoViagem,id=id)
        linha = trecho.rota.linha
        trecho_exclude = TrechoViagem.objects.filter(
        rota__linha=linha,
        parada_inicio=trecho.parada_inicio,
        parada_fim=trecho.parada_fim,
        ordem=trecho.ordem,
        distancia_km=trecho.distancia_km,
    )
        trecho_exclude.delete()
        id = trecho.rota.id
    return redirect('management:criar-trecho',rota_id=id)
    #return render(request,'manager/criar_trecho.html')


# @login_required
# def adicionar_municipio(request):
#     if request.method == 'POST':
#         form = MunicipioForm(request.POST)

#         if form.is_valid():
#             municipio = form.save(commit=False)
                
#             if request.user.role == UserRole.MANAGER:
#                 municipio.ofertado_pelo_sistema = False
#                 municipio_pai = Municipio.objects.filter(gestor=request.user).first()
#                 municipio_pai.municipios_relacionados.add(municipio)
#                 municipio.save()
#     return redirect('management:view_buses')