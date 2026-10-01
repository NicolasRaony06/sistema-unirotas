from django.shortcuts import render, redirect
from .forms import UserRegistrationForm, StudentProfileForm, LoginForm, ChangePassword, AvatarForm
from .models import StudentProfile, User, PersonelProfile
from django.contrib.auth import authenticate, login, update_session_auth_hash
from django.core.cache import cache
from django.db import transaction
from django.contrib.auth.decorators import login_required
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from .handlers import *
from django.utils.http import url_has_allowed_host_and_scheme
# Create your views here.

def signup(request):
    if request.method == 'POST':
        form_student = StudentProfileForm(request.POST)
        form_account = UserRegistrationForm(request.POST)
        if form_student.is_valid() and form_account.is_valid():
            try:
                with transaction.atomic():
                    user = form_account.save()
                    data = form_student.cleaned_data
                    student = StudentProfile.objects.create(
                        user=user,
                        course=data.get("course"),
                        period=data.get("period"),
                    )
                return redirect("authentication:login")
            except Exception as e:
                form_account.add_error(None, "Ocorreu um erro ao cadastrar a conta. Tente novamente.")
                # pos mvp: enviar mensagem pro email caso o usuario ja esteja com email cadastrado e tentando cadastrar novamente
    else:
        form_student = StudentProfileForm()
        form_account = UserRegistrationForm()
    return render(request, 'signup.html', {'form_student': form_student, "form_account": form_account})

def signin(request):
    if request.method == "POST":
        form_login = LoginForm(request.POST)
        if form_login.is_valid():
            data = form_login.cleaned_data
            valid_user = authenticate(
                request, 
                username=data.get("email"), 
                password=data.get("password")
            )
            
            if valid_user is not None:
                login(request, valid_user)

                next_url = request.GET.get('next')
                default_redirect = 'authentication:settings'

                if next_url and url_has_allowed_host_and_scheme(
                    url=next_url,
                    allowed_hosts={request.get_host()},
                    require_https=request.is_secure()
                ):
                    return redirect(next_url)

                return redirect(default_redirect)
            else:
                form_login.add_error(None, "E-mail ou senha inválidos.")
    else:
        form_login = LoginForm()
        
    return render(request, "login.html", {'form_login': form_login})

def signup_with_role(request, token):
    try:
        email, invitation_data, cache_key = get_invitation_data(token)
        if not email or not invitation_data:
            raise ValueError("Este convite não possui os dados válidos para o cadastro.")
        role, higher_role_email, city_id, higher_obj = validate_invitation_integrity(invitation_data)
    except ValueError as error:
        return render(request, 'erro_convite.html', {'mensagem': str(error)})
    
    if User.objects.filter(email=email).first() is not None:
        return render(request, 'erro_convite.html', {'mensagem': 'Este email ja tem uma conta associada, por favor contate ao responsavel pelo convite e tente novamente por um novo email'})
    
    pointer_key = f"invitation_pointer_{higher_role_email}_{email}"

    if request.method == "POST":
        post = request.POST.copy()
        post["email"] = email
        signup_form = UserRegistrationForm(post)

        if signup_form.is_valid():
            try:
                with transaction.atomic():
                    user = signup_form.save(commit=False)
                    user.role = role
                    user.save()
                    PersonelProfile.objects.create(user=user, city_id=city_id)
                    cache.delete(cache_key)
                    cache.delete(pointer_key)
                    return redirect("authentication:login")
            except Exception:
                return render(request, 'signup_role.html', {"form_account": signup_form, 'error': 'ocorreu um erro an cadastrar a conta, por favor tente novamente mais tarde'})
    else:
        signup_form = UserRegistrationForm()
    return render(request, 'signup_role.html', {"form_account": signup_form})

@login_required(login_url=reverse_lazy('authentication:login'))
@require_POST
def toggle_notification(request):
    if request.method == 'POST':
        request.user.notifications = not request.user.notifications
        request.user.save()
    return redirect('authentication:settings')

@login_required(login_url=reverse_lazy('authentication:login'))
def settings(request):
    return render(request, "settings.html", {
        'notifications': request.user.notifications,
        'full_name': request.user.full_name,
        'email': request.user.email,
        'profile_picture': request.user.profile_picture
        #'city': request.user.city,
        #'institution': request.user.institution
        })

@login_required(login_url=reverse_lazy('authentication:login'))
def my_information(request):
    return render(request, "my_information.html", {
        "full_name": request.user.full_name,
        "email": request.user.email,
        #"city",
        "birth_date": request.user.birth_date,
        #"institution": request.user.institution,
        #"campus": request.user.institution.campus,
        'change_avatar_form': AvatarForm()
    })

@login_required(login_url=reverse_lazy('authentication:login'))
@require_POST
def change_avatar(request):
    form = AvatarForm(request.POST, request.FILES)
    if form.is_valid():
        new_picture = form.cleaned_data["profile_picture"]
        old_picture = request.user.profile_picture if request.user.profile_picture else None
        request.user.profile_picture = new_picture
        request.user.save()
        if old_picture:
            old_picture.delete(save=False)
    return redirect("authentication:my_information")

@login_required(login_url=reverse_lazy('authentication:login'))
def change_password(request):
    if request.method == "POST":
        form = ChangePassword(request.POST, user=request.user)
        if form.is_valid():
            if request.user.check_password(form.cleaned_data.get("password")):
                request.user.set_password(form.cleaned_data.get("new_password1"))
                request.user.save()
                update_session_auth_hash(request, request.user)
                return redirect("authentication:my_information")
            else:
                form.add_error("password", "senha inválida, por favor digite sua senha atual a este campo")
                return render(request, "change_password.html", {"form": form})
    else:
        form = ChangePassword(user=request.user)
    return render(request, "change_password.html", {"form": form}) 
