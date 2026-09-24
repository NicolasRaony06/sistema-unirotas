from django.shortcuts import render, redirect, get_object_or_404
from .forms import UserRegistrationForm, StudentProfileForm, LoginForm, ChangePassword, AvatarForm, PersonelProfileForm
from .models import StudentProfile, User, UserRole
from django.contrib.auth import authenticate, login, update_session_auth_hash
from django.core.signing import TimestampSigner, BadSignature
from django.core.cache import cache
from django.db import transaction
from django.contrib.auth.decorators import login_required
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
# Create your views here.

def birth_date_do(user):
    """Le a data de nascimento do perfil do usuario.

    Por enquanto ``birth_date`` vive nos perfis (StudentProfile /
    PersonelProfile) como placeholder; quando o campo voltar para o
    ``User`` basta trocar aqui por ``user.birth_date``.
    """
    perfil = getattr(user, "student_profile", None)
    if perfil is None:
        perfil = getattr(user, "personel_profile", None)
    return perfil.birth_date if perfil else None

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
                        birth_date=data.get("birth_date"),
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
    signer = TimestampSigner()

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
    higher = User.objects.filter(email__iexact=higher_role_email).first()

    pointer_key = f"invitation_pointer_{higher_role_email}_{email}"

    if not higher:
        return render(request, 'erro_convite.html', {'mensagem': 'Este convite não é válido.'})
    if  not higher.can_invite(role):
            return render(request, 'erro_convite.html', {'mensagem': 'Este convite não é válido.'})

    if request.method == "POST":
        post = request.POST.copy()
        post["email"] = email
        signup_form = UserRegistrationForm(post)
        personel_form = PersonelProfileForm(post)

        if signup_form.is_valid() and personel_form.is_valid():
            try:
                with transaction.atomic():
                    user = signup_form.save(commit=False)
                    user.role = role

                    user.save()

                    # birth_date hoje mora no PersonelProfile (placeholder);
                    # quando city/management liberar, volta para o User.
                    personel_form.instance.user = user
                    personel_form.save()

                    cache.delete(cache_key)
                    cache.delete(pointer_key)
                    return redirect("authentication:login")
            except Exception:
                return render(request, 'signup_role.html', {"form_account": signup_form, 'personel_account':personel_form, 'error': 'ocorreu um erro an cadastrar a conta, por favor tente novamente mais tarde'})
    else:
        signup_form = UserRegistrationForm()
        personel_form = PersonelProfileForm()
    return render(request, 'signup_role.html', {"form_account": signup_form, 'personel_account':personel_form})

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
        "birth_date": birth_date_do(request.user),
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
                form.add_error("new_password2", "A senha tem que atender a todos os requisitos, se o erro persistir, cheque sua senha atual")
                return render(request, "change_password.html", {"form": form, "error": "não foi possivel mudar a senha no momento, tente novamente mais tarde"})
    else:
        form = ChangePassword(user=request.user)
    return render(request, "change_password.html", {"form": form}) 
