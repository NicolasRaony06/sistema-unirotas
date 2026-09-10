from django.shortcuts import render, redirect
from .forms import UserRegistrationForm, StudentProfileForm, LoginForm
from .models import StudentProfile
from django.contrib.auth import authenticate, login

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