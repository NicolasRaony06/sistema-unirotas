import random

from django.shortcuts import render, redirect

from notifications.models import NotficationsType, Notification, NotificationUser
from .forms import ConfirmPerson, LoginForm, ChangePassword, AvatarForm, ResetPasswordForm
from .models import User
from django.contrib.auth import authenticate, login, update_session_auth_hash
from django.core.cache import cache
from django.contrib.auth.decorators import login_required
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from .handlers import *
from django.utils.http import url_has_allowed_host_and_scheme
from django.http import HttpResponse
from .decorators import unloged_required
from django.contrib.auth import views as auth_views
# Create your views here.

LOGIN_THRESHOLD = 10
LOGIN_WINDOW = 300

def _attempts_key(request, email):
    ip = request.META.get("REMOTE_ADDR", "")
    return f"login_attempts_{ip}_{(email or '').lower().strip()}"

@unloged_required
def signin(request):
    if request.method == "POST":
        form_login = LoginForm(request.POST)
        print()
        if form_login.is_valid():
            data = form_login.cleaned_data
            chave = _attempts_key(request, data.get("email"))
            attempts = cache.get(chave, 0)
            if attempts >= LOGIN_THRESHOLD:
                return HttpResponse("Muitas tentativas. Aguarde alguns minutos.", status=429)

            valid_user = authenticate(
                request, 
                username=data.get("email"), 
                password=data.get("password")
            )

            if valid_user is not None:
                cache.delete(chave)
                login(request, valid_user)

                if request.POST.get("remember") != "on":
                    request.session.set_expiry(0)
                    request.session.modified = True

                next_url = request.GET.get('next')
                role = valid_user.role
                if role == "STUDENT":
                    default_redirect = 'index_aluno'
                elif role == "DRIVER":
                    default_redirect = 'lista_viagens'
                elif role == "MANAGER" or role == "ADMIN":
                    default_redirect = "management:home"
                
                if next_url and url_has_allowed_host_and_scheme(
                    url=next_url,
                    allowed_hosts={request.get_host()},
                    require_https=request.is_secure()
                ):
                    return redirect(next_url)

                return redirect(default_redirect)

            else:
                cache.set(chave, attempts + 1, timeout=LOGIN_WINDOW)
                form_login.add_error(None, "E-mail ou senha inválidos.")
    else:
        form_login = LoginForm()
        
    return render(request, "login.html", {'form_login': form_login})

@unloged_required
def signup_with_role(request, token):
    try:
        cache_data = get_invitation_data(token)
        if not cache_data.invitation_dict:
            raise ValueError("Este convite não possui os dados válidos para o cadastro.")
        if not cache_data.invitation_dict.get("email"):
            raise ValueError("Este convite não possui os dados válidos para o cadastro.")
        
        invitation_data = validate_invitation_integrity(cache_data.invitation_dict)
    except ValueError as error:
        return render(request, 'erro_convite.html', {'mensagem': str(error)})

    if User.objects.filter(email__iexact=invitation_data.email).first() is not None:
        return render(request, 'erro_convite.html', {'mensagem': 'Este email ja tem uma conta associada, por favor contate ao responsavel pelo convite e tente novamente por um novo email'})

    return handle_singup_render_based_on_role(request, invitation_data, cache_data)    

@login_required()
@require_POST
def toggle_notification(request):
    if request.method == 'POST':
        request.user.notifications = not request.user.notifications
        request.user.save()
    return redirect('authentication:settings')

from notifications import service

@login_required()
def settings(request):
    if request.user.role == "STUDENT":
        city = request.user.student_profile.city
        instituition = request.user.student_profile.institution.name
        campus = request.user.student_profile.institution.city
    elif request.user.role in ["MANAGER", "DRIVER"]:
        city = request.user.personel_profile.city
        instituition = None
    else:
        city = None
        instituition = None
    return render(request, "settings.html", {
        'notifications': request.user.notifications,
        'full_name': request.user.full_name,
        'email': request.user.email,
        'profile_picture': request.user.profile_picture,
        'city': city,
        'institution': instituition
        })

@login_required()
def my_information(request):
    if request.user.role == "STUDENT":
        city = request.user.student_profile.city
        instituition = request.user.student_profile.institution.name
        campus = request.user.student_profile.institution.city
    elif request.user.role in ["MANAGER", "DRIVER"]:
        city = request.user.personel_profile.city
        instituition = None
        campus = None
    else:
        city, instituition, campus = None, None, None
    return render(request, "my_information.html", {
        "full_name": request.user.full_name,
        "email": request.user.email,
        "city": city,
        "birth_date": request.user.birth_date,
        "institution": instituition,
        "campus": campus,
        'change_avatar_form': AvatarForm()
    })

@login_required()
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

@login_required()
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

class ResetPasswordFirst(auth_views.PasswordResetView):
    template_name='registration/password_reset_form.html'
    success_url=reverse_lazy('authentication:password_reset_done')
    form_class = ResetPasswordForm

    def form_valid(self, form):
        opts = {
            "use_https": self.request.is_secure(),
            "token_generator": self.token_generator,
            "request": self.request,
        }
        user = User.objects.filter(email=form.cleaned_data.get("email"), is_active=True).first()
        if hasattr(user, "personel_profile"):
            entity = user.personel_profile
        else:
            entity = user.student_profile
        token = opts["token_generator"].make_token(user)
        uid = get_uid(user.pk)
        link = reverse_lazy("authentication:password_reset_confirm", kwargs={"uidb64":uid, "token": token})
        link = self.request.build_absolute_uri(link)
        if user.role in [UserRole.DRIVER, UserRole.STUDENT]:
            service.send_notification(f"o usuario {user.full_name} esqueceu a senha", f"o usuario esqueceu a senha e é preciso que voce entre em contato enviando o link: {link} para o email: {user.email}", user, entity.city.gestor.user, NotficationsType.ALERT)
        else:
            service.send_notification(f"o usuario {user.full_name} esqueceu a senha", f"o usuario esqueceu a senha e é preciso que voce entre em contato enviando o link: {link} para o email: {user.email}", user, User.objects.filter(role=UserRole.ADMIN).all(), NotficationsType.ALERT)
        self.request.session["foreget_password_email"] = user.email
        form.save(**opts)

        return super().form_valid(form)

from django.core.cache import cache
class ResetDone(auth_views.PasswordResetDoneView):
    template_name='registration/password_reset_done.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        numero_formatado = [random.randint(0, 9) for i in range(0, 6)].__str__().replace(" ","").replace(",", "").replace("[", "").replace("]", "")
        context["verificador"] = numero_formatado
        email:str = self.request.session.get("foreget_password_email")
        if email:
            cache.set(f"{email.strip()}-verification_code", numero_formatado, 86400)
        else:
            return redirect("password_reset")
        return context

class ConfirmReset(auth_views.PasswordResetConfirmView):
    template_name='registration/password_reset_confirm.html'
    success_url=reverse_lazy('authentication:password_reset_complete')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form_validation"] = ConfirmPerson
        return context

    def post(self, request, *args, **kwargs):
        form = ConfirmPerson(self.request.POST)
        if form.is_valid():
            cache.delete(f"{form.cleaned_data.get('email')}-verification_code")
            return super().post(request, *args, **kwargs)
        context = self.get_context_data()
        context["form_validation"] = form
        return render(self.request, self.template_name, context)