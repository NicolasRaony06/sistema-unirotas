from django.shortcuts import render, redirect
from .forms import UserRegistrationForm, StudentProfileForm
from .models import User, StudentProfile
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

