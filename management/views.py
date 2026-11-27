from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.urls import reverse_lazy, reverse
from datetime import datetime
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.db.models import Q
from .models import *
from authentication.models import StudentProfile, User, UserRole, PersonelProfile
from authentication.service import generate_elevated_signup_link, recreate_elevated_signup_link
from django.http import HttpResponse, JsonResponse
from django.db.models import Q, ProtectedError, RestrictedError
from django.db import transaction
from .models import *
from authentication.models import UserRole, PersonelProfile, StudentProfile
from authentication.service import recreate_elevated_signup_link
from authentication.decorators import role_required
from .forms import *
from .handlers import *
from authentication.data_type import InviteDTO
from operation.models import Viagem, UsuarioDaViagem
from django.db import transaction
from authentication.forms import ChangePassword
from django.forms import inlineformset_factory

@login_required()
@role_required(allowed_roles=[UserRole.ADMIN, UserRole.MANAGER])
def home(request):

    if request.user.role == "ADMIN":
        last_municipios = request.session.get("last_metric_city", 0)
        last_gestores = request.session.get("last_metric_manager", 0)
        last_estudantes = request.session.get("last_metric_student", 0)
        total_municipios = Municipio.objects.all().all().count()
        total_gestores = PersonelProfile.objects.filter(user__role="MANAGER").all().count()
        total_estudantes = StudentProfile.objects.all().count()
        request.session[f"last_metric_city"] = total_municipios
        request.session[f"last_metric_manager"] = total_gestores
        request.session[f"last_metric_student"] = total_estudantes
        metricas = [[total_municipios, total_municipios - last_municipios], [total_gestores, total_gestores - last_gestores], [total_estudantes, total_estudantes - last_estudantes]]
    else:
        if  request.user.personel_profile.city is None:
            return render(request, 'manager/index.html')
        
        total_usuarios = UsuarioDaViagem.objects.filter(viagem__rota__linha__in=Linha.objects.filter(city=request.user.personel_profile.city).all()).all().count()
        total_onibus = Bus.objects.filter(city=request.user.personel_profile.city).all().count()
        last_usuarios = request.session.get("last_trip_user", 0)
        last_onibus = request.session.get("last_metric_bus", 0)
        operando = Viagem.objects.filter(rota__linha__in=Linha.objects.filter(city=request.user.personel_profile.city), status='em_andamento').count()
        request.session[f"last_metric_bus"] = Bus.objects.filter(city=request.user.personel_profile.city).count()
        request.session[f"last_trip_user"] = UsuarioDaViagem.objects.filter(viagem__rota__linha__in=Linha.objects.filter(city=request.user.personel_profile.city).all()).count()
        metricas = [[total_usuarios, total_usuarios - last_usuarios], [total_onibus, total_onibus - last_onibus], [operando, 0]]

    context = {
        'metricas': metricas,
        'linhas': Linha.objects.all(),
        'motoristas':PersonelProfile.objects.filter(user__role=UserRole.DRIVER).count(),
        'onibus': Bus.objects.all().count(),
        'estudantes':PersonelProfile.objects.filter(user__role=UserRole.STUDENT).count(),
        'municipios': Municipio.objects.all().count(),
        'full_name' : request.user.full_name,
        'data': timezone.now(),
    }

    return render(request, "home.html", context)

@login_required()
@role_required(allowed_roles=UserRole.ADMIN)
def gestores(request):

    context = {
    'gestores': PersonelProfile.objects.filter(user__role=UserRole.MANAGER),
    'gestores_inativos': PersonelProfile.objects.filter(user__role = UserRole.MANAGER, user__is_active=False).count(),
    'total_gestores' :PersonelProfile.objects.filter(user__role=UserRole.MANAGER).count(),
    }

    return render(request,'admin/gestores.html',context)

@login_required()
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
            'associate_city_manager_form': AssociateCityManager()
        }

        return render(request,'admin/municipios.html',context)


@login_required()
@role_required(allowed_roles=UserRole.ADMIN)
def criar_municipio(request):
    if request.method == 'POST':
        form = MunicipioForm(request.POST)

        if form.is_valid():
            municipio = form.save(commit=False)

            if municipio.gestor:
                municipio.ofertado_pelo_sistema = True
            municipio.save()

            messages.success(request, "Município cadastrado com sucesso.")
            return redirect('management:municipios')
    else:
        form = MunicipioForm()
    return render(request, 'cadastro_municipio.html', {'form': form})

@login_required()
@role_required(allowed_roles=UserRole.MANAGER)
def adicionar_municipio(request):
    if request.method == 'POST':
        form = MunicipioForm(request.POST)

        if form.is_valid():
            municipio = form.save(commit=False)

            if request.user.role == UserRole.MANAGER:
                municipio.ofertado_pelo_sistema = False
                municipio.save()

                municipio_gestor = Municipio.objects.filter(gestor=request.user.personel_profile).first()
                municipio_gestor.municipios_relacionados.add(municipio)
                messages.success(request, "Município cadastrado com sucesso.")    
                return redirect('management:localizacoes')
        else:
            return render(request, 'cadastro_municipio.html', {'form': form, 'erro': 'Dados inválidos'})

    else:
        form = MunicipioForm()
    return render(request, 'cadastro_municipio.html', {'form': form})

@login_required()
@role_required(allowed_roles=UserRole.ADMIN)
def associar_gestor(request):
    if request.method == 'POST':
        form = AssociateCityManager(request.POST)
        if form.is_valid():
            city = get_object_or_404(
                Municipio,
                id=form.cleaned_data['city']
            )
            manager = get_object_or_404(
                User,
                id=form.cleaned_data['manager']
            )
            city.gestor = manager
            city.ofertado_pelo_sistema = True
            manager.personel_profile.city = city

            try:
                with transaction.atomic():
                    city.save()
                    manager.personel_profile.save()
                messages.success(request, "Gestor associado a município com sucesso.")
                return redirect('management:municipios')
            except Exception as error:
                messages.error(request, f"Erro ao associar gestor: {str(error)}")
                return redirect('management:municipios')

        messages.error(request, "Não foi possível associar gestor a município.")    
    return redirect('management:municipios')


@login_required()
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

@login_required()
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

@login_required()
@role_required(allowed_roles=UserRole.MANAGER)
def localizacoes(request):
   
    municipio_base = Municipio.objects.filter(gestor__user = request.user).first()
    
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


@login_required()
@role_required(allowed_roles=UserRole.ADMIN)
def deactive_manager(request,id):
    if request.method == 'POST':
        manager = PersonelProfile.objects.filter(user__role=UserRole.MANAGER , user__pk=id).first()
        print(manager)
        manager.user.is_active = False
        manager.user.save()
    return redirect('management:gestores')

@login_required()
@role_required(allowed_roles=UserRole.ADMIN)
def activate_manager(request,id):
    if request.method == 'POST':
        manager = PersonelProfile.objects.filter(user__role=UserRole.MANAGER, user__pk=id).first()
        manager.user.is_active = True
        manager.user.save()
    return redirect('management:gestores')

@login_required()
@role_required(allowed_roles=UserRole.MANAGER)
def invite_driver(request):
    user = request.user

    if request.method == 'POST':
        form = InviteDriverForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data.get('email')
           
            link = recreate_elevated_signup_link(
                InviteDTO(
                    higher_role_email=user.email,
                    role=UserRole.DRIVER,
                    email=email,
                    city_id = request.user.personel_profile.city,
                ),
                request=request
            )

            if link:
                request.session['qrcode_link'] = link
                messages.success(request, f'Convite enviado com sucesso para {email}.')
                return redirect("management:view_drivers")
            else:
                messages.error(request, f"Não foi possível enviar o convite para {email}.")
    else:
        form = InviteDriverForm()
    return render(request, "manager/invite_driver.html", {'form': form})

@login_required()
@role_required(allowed_roles=UserRole.MANAGER)
def view_drivers(request):
    drivers = PersonelProfile.objects.filter(
        user__role=UserRole.DRIVER, 
        city=request.user.personel_profile.city
    )

    qrcode_link = request.session.pop("qrcode_link", None)
    qrcode_img = generate_qrcode(qrcode_link) if qrcode_link else None

    context = {
        'drivers': drivers,
        'qrcode_img': qrcode_img,
        'qrcode_link': qrcode_link
    }

    return render(request, 'manager/view_drivers.html', context)

@login_required()
@role_required(allowed_roles=UserRole.MANAGER)
def edit_driver(request, id):
    pass

@login_required()
@role_required(allowed_roles=UserRole.MANAGER)
def deactivate_driver(request, id):
    if request.method == 'POST':
        driver_profile = get_object_or_404(
            PersonelProfile,
            id=id,
            user__role=UserRole.DRIVER,
            city=request.user.personel_profile.city
        )

        if driver_profile.city != request.user.personel_profile.city:
            return HttpResponseForbidden("Acesso negado.")

        driver_user = driver_profile.user
        if driver_user.is_active:
            driver_user.is_active = False
            driver_user.save()
            #messages.success(request, f"Motorista {driver_user.full_name} desativado com sucesso.")
    return redirect('management:view_drivers')

@login_required()
@role_required(allowed_roles=UserRole.MANAGER)
def activate_driver(request, id):
    if request.method == 'POST':
        driver_profile = get_object_or_404(
            PersonelProfile,
            id=id,
            user__role=UserRole.DRIVER,
            city=request.user.personel_profile.city
        )

        if driver_profile.city != request.user.personel_profile.city:
            return HttpResponseForbidden("Acesso negado.")

        driver_user = driver_profile.user
        if not driver_user.is_active:
            driver_user.is_active = True
            driver_user.save()
            #messages.success(request, f"Motorista {driver_user.full_name} ativado com sucesso.")
    return redirect('management:view_drivers')

@login_required()
@role_required(allowed_roles=UserRole.MANAGER)
def delete_driver(request, id):
    if request.method == 'POST':
        driver = get_object_or_404(
            User,
            id=id
        )
        try:
            driver.delete()
            messages.success(request, "Motorista deletado com sucesso.")
        except (ProtectedError, RestrictedError):
            messages.error(request, "Não foi possível excluir: existem registros vinculados a este motorista.")

    return redirect('management:view_drivers')

@login_required
@role_required(allowed_roles=UserRole.MANAGER)
def register_bus(request):
    if not request.user.personel_profile.city.ofertado_pelo_sistema:
        messages.error(request, "Não é possível cadastrar ônibus para um Município não ativo.")
        return redirect('management:view_buses')

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

        #messages.error(request, "Ocorreu um erro ao tentar cadastrar o ônibus. Tente novamente.")
    else:
        form = BusForm()
    return render(request, "manager/register_bus.html", {'form': form})

@login_required()
@role_required(allowed_roles=UserRole.MANAGER)
def view_buses(request):
    buses = Bus.objects.filter(city=request.user.personel_profile.city)
    return render(request, "manager/view_buses.html", {'buses': buses})

@login_required()
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
        #messages.error(request, f"Erro ao tentar alterar ônibus {bus.name}")
    else:
        form = BusForm(instance=bus)
    return render(request, 'manager/edit_bus.html', {'form': form})

@login_required()
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
            #messages.success(request, f"Ônibus {bus.name} desativado com sucesso.")
    return redirect('management:view_buses')

@login_required()
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
            #messages.success(request, f"Ônibus {bus.name} ativado com sucesso.")
    return redirect('management:view_buses')

@login_required()
@role_required(allowed_roles=UserRole.MANAGER)
def delete_bus(request, id):
    if request.method == 'POST':
        bus = get_object_or_404(
            Bus,
            id=id,
            city=request.user.personel_profile.city
        )
        try:
            bus.delete()
            messages.success(request, "Ônibus deletado com sucesso.")
        except (ProtectedError, RestrictedError):
            messages.error(request, "Não foi possível excluir: existem registros vinculados a este ônibus.")

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

@login_required()
@role_required(allowed_roles=UserRole.MANAGER)
def view_bus_stops(request):
    city = request.user.personel_profile.city

    # related_cities = []
    # filter_ocult_related_cities = request.GET.get('ocult_related_cities')
    # if not filter_ocult_related_cities: 
    #     

    related_cities = city.municipios_relacionados.all()

    bus_stops = BusStop.objects.filter(
        Q(city__in=related_cities)
    ).select_related('city').distinct()

    return render(request, 'manager/view_bus_stops.html', {'bus_stops': bus_stops})

@login_required()
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
        #messages.error(request, "Não foi possível alterar a parada")
    else:
        form = BusStopForm(instance=bus_stop, city=city)
    return render(request, 'manager/edit_bus_stop.html', {'form': form})

@login_required()
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
            print('shgfhjsajkf')
            bus_stop.is_active = True
            bus_stop.save()
            messages.success(request, f"Parada {bus_stop.name} ativada com sucesso.")
    return redirect('management:view_bus_stops')

    #return redirect(f"{base_url}?ocult_related_cities={request.GET.get('ocult_related_cities', 'False')}")

@login_required
@role_required(allowed_roles=UserRole.MANAGER)
def invite_student(request):
    user = request.user
    institutions_id = user.personel_profile.city.municipios_relacionados.values_list(
        'institutions', 
        flat=True
    )

    if request.method == 'POST':
        form = InviteStudentForm(request.POST, institutions_id=institutions_id)
        if form.is_valid():
            email = form.cleaned_data.get('email')
           
            link = recreate_elevated_signup_link(
                InviteDTO(
                    higher_role_email=user.email,
                    role=UserRole.STUDENT,
                    email=email,
                    city_id = request.user.personel_profile.city,
                    institution_id = Institution.objects.filter(pk=form.cleaned_data.get('institution')).first()
                ),
                request=request
            )

            if link:
                request.session['qrcode_link'] = link
                messages.success(request, f'Convite enviado com sucesso para {email}.')
                return redirect("management:view_students")
            else:
                messages.error(request, f"Não foi possível enviar o convite para {email}.")
    else:
        form = InviteStudentForm(institutions_id=institutions_id)
    return render(request, "manager/invite_student.html", {'form': form})

@login_required
@role_required(allowed_roles=UserRole.MANAGER)
def view_students(request):
    students = StudentProfile.objects.filter(city=request.user.personel_profile.city)

    qrcode_link = request.session.pop("qrcode_link", None)
    qrcode_img = generate_qrcode(qrcode_link) if qrcode_link else None

    context = {
            'students': students,
            'qrcode_img': qrcode_img,
            'qrcode_link': qrcode_link
        }

    return render(request, 'manager/view_students.html', context)

@login_required()
@role_required(allowed_roles=UserRole.MANAGER)
def register_institution(request):
    city = request.user.personel_profile.city
    if request.method == 'POST':
        form = InstitutionForm(request.POST, city=city)
        if form.is_valid():
            form.save()
            messages.success(request, "Instituição cadastrada com sucesso.")
            return redirect("management:view_institutions")
        #messages.error(request, "Não foi possível cadastrar instituição.")
    else:
        form = InstitutionForm(city=city)
    return render(request, 'manager/register_institution.html', {'form': form})

@login_required()
@role_required(allowed_roles=UserRole.MANAGER)
def view_institutions(request):
    city = request.user.personel_profile.city

    # related_cities = []
    # filter_ocult_related_cities = request.GET.get('ocult_related_cities')
    # if not filter_ocult_related_cities: 
    #     related_cities = city.municipios_relacionados.all()

    related_cities = city.municipios_relacionados.all()

    institutions = Institution.objects.filter(
        Q(city__in=related_cities)
    ).select_related('city').distinct()
    
    return render(request, 'manager/view_institutions.html', {'institutions': institutions})

@login_required()
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
            #messages.success(request, f"Instituição {institution.name} desativada com sucesso.")

    # base_url = reverse('management:view_institutions')
    # return redirect(f"{base_url}?ocult_related_cities={request.GET.get('ocult_related_cities', 'False')}")

    return redirect('management:view_institutions')

@login_required()
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
    base_url = reverse('management:view_institutions')
    return redirect(f"{base_url}?ocult_related_cities={request.GET.get('ocult_related_cities', 'False')}")

@login_required()
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
        #messages.error(request, "Não foi possível alterar a instituição.")
    else:
        form = InstitutionForm(instance=institution, city=city)
    return render(request, 'manager/edit_institution.html', {'form': form})

@login_required()
@role_required(allowed_roles=[UserRole.MANAGER, UserRole.ADMIN])
def retirar_municipio(request, id):
    if request.method == 'POST':
        if request.user.role == UserRole.MANAGER:
            municipio_pai = Municipio.objects.filter(gestor= request.user.personel_profile).first()
            municipio_listado = Municipio.objects.filter(id=id).first()
            municipio_pai.municipios_relacionados.remove(municipio_listado)
        else:
            Municipio.objects.filter(id=id).first().delete()
            return redirect('management:municipios')
    return redirect('management:localizacoes')

@login_required()
@role_required(allowed_roles=UserRole.MANAGER)
def inativar_linha(request, id):
    if request.method == 'POST':
        linha = Linha.objects.filter(id=id).first()
        if linha.city != request.user.personel_profile.city:
            return HttpResponseForbidden("Acesso negado.")

        if  linha.is_active:
            linha.is_active = False
            linha.save()
    return redirect('management:linhas')

@login_required()
@role_required(allowed_roles=UserRole.MANAGER)
def ativar_linha(request, id):
    if request.method == 'POST':
        linha = Linha.objects.filter(id=id).first()
        if linha.city != request.user.personel_profile.city:
            return HttpResponseForbidden("Acesso negado.")
        
        if  linha.is_active == False:
            linha.is_active = True
            linha.save()
    return redirect('management:linhas')

@login_required()
@role_required(allowed_roles=UserRole.MANAGER)
def criar_linha(request):
    list_forms = []
    if request.method == 'POST':
        linha_form = LinhaForm(request.POST,prefix='linha')
        rota_form = RotaForm(request.POST,prefix='Ida')
        rota_voltaform = RotaForm(request.POST,prefix='Volta')

        if not linha_form.is_valid():
            print("ERROS DO FORMULÁRIO:", linha_form.errors)
        
        if (linha_form.is_valid() and rota_form.is_valid()) and (not rota_voltaform.has_changed() or rota_voltaform.is_valid()):

            with transaction.atomic():
                linha = linha_form.save(commit=False)
                linha.city = request.user.personel_profile.city
                linha.save()
                linha_form.save_m2m()

                Ida = rota_form.save(commit=False)
                Ida.linha = linha
                Ida.save()

                if rota_voltaform.has_changed():
                    Volta = rota_voltaform.save(commit=False)
                    Volta.linha = linha
                    Volta.save()

            ordens = request.POST.getlist('trecho_ordem')
            inicios = request.POST.getlist('trecho_parada_inicio')
            fins = request.POST.getlist('trecho_parada_fim')
            distancias = request.POST.getlist('trecho_distancia_km')

            if not ordens or not inicios or not fins or not distancias:
                pass

            for ordem, inicio, fim, distancia in zip(ordens, inicios, fins, distancias):

                trecho = TrechoViagem.objects.create(
                    rota=Ida,
                    ordem=ordem,
                    parada_inicio_id=inicio,
                    parada_fim_id=fim,
                    distancia_km=distancia,
                )

                
                if Volta is not None:
                        t_existentes = TrechoViagem.objects.filter(rota=Volta)
                        for t in t_existentes:
                            t.ordem += 1
                            t.save()
                        trecho_volta = trecho
                        trecho_volta.pk = None
                        trecho_volta.id = None
                        trecho_volta.rota = Volta
                        trecho_volta.inverter()

            return redirect('management:linhas')
    else:
        linha_form = LinhaForm(prefix='linha')
        rota_form = RotaForm(prefix='Ida')
        rota_voltaform = RotaForm(prefix='Volta')

    cidades_relacionadas = []
    cidades_relacionadas = request.user.personel_profile.city.municipios_relacionados.all()
    motoristas = PersonelProfile.objects.filter(user__role=UserRole.DRIVER, city=request.user.personel_profile.city, user__is_active=True,)
    instituicoes = Institution.objects.filter(city__in=cidades_relacionadas)
    onibus = Bus.objects.filter(city=request.user.personel_profile.city)
    paradas = BusStop.objects.filter(city__in=cidades_relacionadas)
    contexto = {'linha_form': linha_form,'rota_form':rota_form,'instituicoes':instituicoes,'rota_voltaform':rota_voltaform,'motoristas':motoristas,'onibus':onibus,'paradas':paradas}
    return render(request, 'manager/criar_linha.html', contexto)




@login_required()
@role_required(allowed_roles=UserRole.MANAGER)
def linhas(request):
    context = {
        'linhas': Linha.objects.all(),

    }
    return render(request,'manager/linhas.html',context)




@login_required()
@role_required(allowed_roles=UserRole.MANAGER)
def excluir_trecho(request, id):
    if request.method == 'POST':
        trecho = get_object_or_404(TrechoViagem,id=id)
        linha = trecho.rota.linha
        if linha.city != request.user.personel_profile.city:
            return HttpResponseForbidden("Acesso negado.")
        
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

@login_required()
@role_required(UserRole.ADMIN)
def invite_manager(request):
    user = request.user

    if request.method == 'POST':
        form = InviteManagerForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data.get('email')
            role=UserRole.MANAGER

           
            link = recreate_elevated_signup_link(
                InviteDTO(
                    higher_role_email=user.email,
                    role=role,
                    email=email,
                    city_id = None
                ),
                request=request
            )

            print(link)

            if link:
                messages.success(request, f'Convite enviado com sucesso para {email}.')
                return redirect("management:home")
            else:
                messages.error(request, f"Não foi possível enviar o convite para {email}.")
    else:
        form = InviteManagerForm()
    return render(request, "admin/invite_manager.html", {'form': form})

@login_required()
@role_required(UserRole.ADMIN)
def edit_manager(request, manager_id):
    manager = get_object_or_404(PersonelProfile, pk=manager_id, user__role=UserRole.MANAGER)
    old_city = Municipio.objects.filter(gestor=manager).first()
    if request.method == "POST":
        form = EditManager(request.POST, instance=manager)
        if form.is_valid():
            with transaction.atomic():
                new_city = form.cleaned_data.get("city")
                if old_city != new_city and old_city:
                    old_city.gestor = None
                    old_city.save()
                if new_city:
                    new_city.gestor = manager
                    new_city.save()
                form.save()
            return redirect("management:gestores")
        return render(request, "admin/edit_manager", {"form": form})
    else:
        form = EditManager(instance=manager)
    return render(request, "admin/edit_manager.html", {"form": form})

@login_required()
@role_required(UserRole.ADMIN)
def detail_manager(request,manager_id):
    manager = get_object_or_404(PersonelProfile, id=manager_id, user__role=UserRole.MANAGER)
    if request.method == 'POST':
        form = ManagerForm(request.POST,instance=manager.user)
        form2 = EditManager(request.POST,instance=manager)
        if form.is_valid():
            form.save()
            return redirect("management:gestores")
    else:
        form = ManagerForm(instance=manager.user)
        form2 = EditManager(instance=manager)

    return render(request,"admin/detail_manager.html",{'form':form,'form2':form2,'manager':manager})

@login_required()
@role_required(allowed_roles=[UserRole.ADMIN, UserRole.MANAGER])
def configuracoes(request):
    form = ManagerForm(instance=request.user)
    form2 = ChangePassword(user=request.user)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "senha":
            form2 = ChangePassword(request.POST, user=request.user)

            if form2.is_valid():
                senha_atual = form2.cleaned_data["password"]

                if request.user.check_password(senha_atual):
                    nova_senha = form2.cleaned_data["new_password1"]
                    request.user.set_password(nova_senha)
                    request.user.save()

                    update_session_auth_hash(request, request.user)
                    messages.success(request, "Senha alterada com sucesso.")
                    return redirect("management:configuracoes")

                form2.add_error("password", "A senha atual está incorreta.")

        elif action == "config":
            form = ManagerForm(
                request.POST,
                request.FILES,
                instance=request.user
            )

            if form.is_valid():
                form.save()
                messages.success(request, "Dados atualizados com sucesso.")
                return redirect("management:configuracoes")

    return render(
        request,
        "configuracoes.html",
        {
            "form": form,
            "form2": form2,
        }
    )
# @login_required()
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