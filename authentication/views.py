from django.shortcuts import render, redirect
from .forms import UserRegistrationForm, StudentProfileForm, LoginForm
from .models import StudentProfile, User, UserRole
from django.contrib.auth import authenticate, login
from django.core.signing import Signer, BadSignature
from django.core.cache import cache
# Create your views here.

def signup(request):
    if request.method == 'POST':
        form_student = StudentProfileForm(request.POST)
        form_account = UserRegistrationForm(request.POST)
        if form_student.is_valid() and form_account.is_valid():
            user = form_account.save()
            data = form_student.cleaned_data
            student = StudentProfile(
                user=user,
                course=data.get("course"),
                period=data.get("period"),
                )
            student.save()
            return redirect("login")
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
                return redirect("home") #temp ate fazer as outras partes
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
    invitation_data = cache.get(cache_key)
    
    if not invitation_data:
        return render(request, 'erro_convite.html', {'mensagem': 'Este convite expirou ou já foi utilizado.'})

    role = invitation_data.get("role")
    higher_role_email = invitation_data.get("higher_role_email")

    if higher_role_email:
        higher = User.objects.filter(email=higher_role_email).first()
        if higher:
            if (higher.role == UserRole.ADMIN and role == UserRole.DRIVER) or (higher.role == UserRole.MANAGER and role == UserRole.ADMIN):
                return render(request, 'erro_convite.html', {'mensagem': 'Este convite não é válido.'})

    if request.method == "POST":
        signup_form = UserRegistrationForm(request.POST)
        if signup_form.is_valid():
            user = signup_form.save(commit=False)
            user.email = email
            user.role = role

            user.save()

            cache.delete(cache_key)
            return redirect("login")
    else:
        signup_form = UserRegistrationForm(initial={'email': email})

    return render(request, 'signup.html', {"form_account": signup_form})
