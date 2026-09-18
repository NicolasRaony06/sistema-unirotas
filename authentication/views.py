from django.shortcuts import render, redirect, get_object_or_404
from .forms import UserRegistrationForm, StudentProfileForm, LoginForm, ChangePassword
from .models import StudentProfile, User
from django.contrib.auth import authenticate, login
from django.core.signing import Signer, BadSignature
from django.core.cache import cache
from django.db import transaction
from django.contrib.auth.decorators import login_required
from django.urls import reverse_lazy

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
                print("erro: ", e)
                return render(request, 'signup.html', {'form_student': form_student, 'form_account': form_account, 'error': 'ocorreu um erro an cadastrar a conta, por favor tente novamente mais tarde'})
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
            user = authenticate(request, username=data.get("email"), password=data.get("password"))
            if user is not None:
                login(request, user)
                return redirect("authentication:settings") #temp ate fazer as outras partes
            else:
                form_login.add_error(None, "E-mail ou senha inválidos.")
    else:
        form_login = LoginForm()
    return render(request, "login.html", {'form_login': form_login})

def signup_with_role(request, token):
    signer = Signer()

    try:
        email = signer.unsign(token)
    except (BadSignature, ValueError):
        return render(request, 'erro_convite.html', {'mensagem': 'Link inválido ou adulterado.'})

    cache_key = f"invitation_{token}"
    pointer_key = f"invitation_pointer_{higher_role_email}_{email}"

    invitation_data = cache.get(cache_key)
    
    if not invitation_data:
        return render(request, 'erro_convite.html', {'mensagem': 'Este convite expirou ou já foi utilizado.'})

    role = invitation_data.get("role")
    higher_role_email = invitation_data.get("higher_role_email")
    higher = User.objects.filter(email__iexact=higher_role_email).first()

    if not higher:
        return render(request, 'erro_convite.html', {'mensagem': 'Este convite não é válido.'})
    if  not higher.can_invite(role):
            return render(request, 'erro_convite.html', {'mensagem': 'Este convite não é válido.'})

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

                    cache.delete(cache_key)
                    cache.delete(pointer_key)
                    return redirect("authentication:login")
            except Exception:
                return render(request, 'signup_role.html', {"form_account": signup_form, 'error': 'ocorreu um erro an cadastrar a conta, por favor tente novamente mais tarde'})
    else:
        signup_form = UserRegistrationForm()

    return render(request, 'signup_role.html', {"form_account": signup_form})

@login_required(login_url=reverse_lazy('authentication:login'))
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
    })

@login_required(login_url=reverse_lazy('authentication:login'))
def change_avatar(request):
    if request.method == "POST":
        profile_picture = request.FILES.get('profile_picture')
        if profile_picture:
            request.user.profile_picture = profile_picture
            request.user.save()
    return redirect("authentication:my_information")

@login_required(login_url=reverse_lazy('authentication:login'))
def change_password(request):
    if request.method == "POST":
        form = ChangePassword(request.POST)
        if form.is_valid():
            if request.user.check_password(form.cleaned_data.get("password")):
                request.user.set_password(form.cleaned_data.get("new_password1"))
                return redirect("authentication:my_information")
            else:
                return render(request, "change_password.html", {"form": form, "error": "não foi possivel mudar a senha no momento, tente novamente mais tarde"})
    else:
        form = ChangePassword()
    return render(request, "change_password.html", {"form": form}) 
