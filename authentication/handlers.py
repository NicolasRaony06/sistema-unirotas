from .models import User, UserRole, StudentProfile, PersonelProfile
from .forms import StudentProfileForm, UserRegistrationForm
from django.shortcuts import render, redirect
from django.core.signing import TimestampSigner, BadSignature
from django.core.cache import cache
from django.conf import settings
from .data_type import InviteDTO, CacheDTO
from django.db import transaction

def get_invitation_data(token):
    signer = TimestampSigner()

    try:
        email = signer.unsign(token, max_age=getattr(settings, "INVITE_TTL_SECONDS", 86400))
    except (BadSignature, ValueError):
        raise ValueError("Convite inválido.")
    cache_key = f"invitation_{token}"

    invitation_data = cache.get(cache_key)
    
    return CacheDTO(invitation_data, cache_key)

def validate_invitation_integrity(cache_dict):
    invitation_data = InviteDTO(cache_dict.get("higher_role_email"),
                                cache_dict.get("role"),
                                cache_dict.get("email"),
                                cache_dict.get("city_id"),
                                cache_dict.get("institution_id"))

    higher_obj = User.objects.filter(email__iexact=invitation_data.higher_role_email).first()

    if not higher_obj:
        raise ValueError("Este convite não é válido pois foi adulterado.")
    if  not higher_obj.can_invite(invitation_data.role):
        raise ValueError("Este convite não é válido pois foi adulterado.")
    if invitation_data.role == UserRole.STUDENT:
        extend_validation(invitation_data)
    return invitation_data

def extend_validation(invitation_data:InviteDTO):
    if invitation_data.institution_id is None:
        raise ValueError("este convite não é valido pois para o cadastro do estudante é necessario informar uma instituição valida")

def validate_student_informations(data:InviteDTO):
    institution_validation = False
    if data.institution_id:
        institution_validation = all((data.institution_id, data.institution_id >= 1)) #depois checar existencia
    return institution_validation

def handle_student_signup(request, invitation_data:InviteDTO):
    if not validate_student_informations(invitation_data):
        raise ValueError("campos de isntituição invalidos, ao criar um convite para estudante deve ser inserido os campos instituicionais do aluno.")
    if request.method == 'POST':
        form_student = StudentProfileForm(request.POST)
        form_account = UserRegistrationForm(request.POST)
        if form_student.is_valid() and form_account.is_valid():
            try:
                with transaction.atomic():
                    user = form_account.save(commit=False)
                    user.email = invitation_data.email
                    user.save()
                    data = form_student.cleaned_data
                    StudentProfile.objects.create(
                        user=user,
                        course=data.get("course"),
                        period=data.get("period"),
                        institution_id=invitation_data.institution_id,
                        city_id=invitation_data.city_id
                    )
                return redirect("authentication:login"), True
            except Exception as e:
                return render(request, 'signup.html', {'form_student': form_student, "form_account": form_account}), False
    else:
        form_student = StudentProfileForm()
        form_account = UserRegistrationForm()
    return render(request, 'signup.html', {'form_student': form_student, "form_account": form_account}), False
    

def handle_manager_driver_signup(request, invitation_data):
    if request.method == "POST":
        signup_form = UserRegistrationForm(request.POST)
        if signup_form.is_valid():
            try:
                with transaction.atomic():
                    user = signup_form.save(commit=False)
                    user.email = invitation_data.email
                    user.role = invitation_data.role
                    user.save()
                    PersonelProfile.objects.create(user=user, city_id=invitation_data.city_id)
                    return redirect("authentication:login"), True
            except Exception as e:
                return render(request, 'signup_role.html', {"form_account": signup_form, 'error': 'ocorreu um erro an cadastrar a conta, por favor tente novamente mais tarde'}), False
    else:
        signup_form = UserRegistrationForm()
    return render(request, 'signup_role.html', {"form_account": signup_form}), False

def handle_singup_render_based_on_role(request, invitation_data, cache_data):
    rend, status = None, False

    if invitation_data.role == UserRole.STUDENT:
        rend, status = handle_student_signup(request, invitation_data)
    elif invitation_data.role in (UserRole.MANAGER, UserRole.DRIVER):
        rend, status = handle_manager_driver_signup(request, invitation_data)

    if request.method == "POST":
        if status:
            cache.delete(cache_data.cache_key)
            pointer_key = f"invitation_pointer_{invitation_data.higher_role_email}_{invitation_data.email}"
            cache.delete(pointer_key)
    return rend