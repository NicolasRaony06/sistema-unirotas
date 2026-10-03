from django.core.signing import TimestampSigner
from django.urls import reverse
from django.core.cache import cache
from django.core.mail import send_mail
from smtplib import SMTPException
from .models import User
from django.conf import settings
from .data_type import InviteDTO

def generate_elevated_signup_link(invite: InviteDTO, request=None):
    ttl_horas = getattr(settings, "INVITE_TTL_SECONDS", 86400)
    higher_role_email = invite.higher_role_email.lower().strip()
    email = invite.email.lower().strip()
    role = invite.role
    city_id = invite.city_id
    institution_id = invite.institution_id
    if User.objects.filter(email=email).first() is not None:
        return None # não irei dar raise agora, decisão de projeto

    signer = TimestampSigner()
    token = signer.sign(email)

    higher = User.objects.filter(email__iexact=higher_role_email).first()
    if not higher:
        return None

    if not higher.can_invite(role):
        return None

    cache_key = f"invitation_{token}"
    pointer_key = f"invitation_pointer_{higher_role_email}_{email}"

    relative_url = reverse('authentication:elevated_signup', kwargs={'token': token})
    absolute_url = request.build_absolute_uri(relative_url) if request else relative_url
    
    sent = enviar_email_convite(email, absolute_url)
    if not sent:
        return None

    cache.set(cache_key, {'email': email, 'role': role, "higher_role_email": higher_role_email, "city_id": city_id, "institution_id": institution_id}, timeout=ttl_horas)
    cache.set(pointer_key, {"cache_key": cache_key}, timeout=ttl_horas)
    
    return absolute_url

def abort_elevated_signup_link(higher_role_email, email):
    higher_role_email = higher_role_email.lower().strip()
    email = email.lower().strip()
    pointer_key = f"invitation_pointer_{higher_role_email}_{email}"
    cache_data = cache.get(pointer_key)
    if not cache_data:
        return
    cache_key = cache_data.get("cache_key")
    if not cache_key:
        return
    cache.delete(cache_key)
    cache.delete(pointer_key)

def recreate_elevated_signup_link(invite: InviteDTO, request=None):
    higher_role_email = invite.higher_role_email.lower().strip()
    email = invite.email.lower().strip()
    abort_elevated_signup_link(higher_role_email, email)
    return generate_elevated_signup_link(invite, request)

def enviar_email_convite(email_destino, link_convite):
    email_destino = email_destino.lower().strip()
    ttl_horas = getattr(settings, "INVITE_TTL_SECONDS", 86400) // 3600

    assunto = "Convite para cadastro na plataforma"
    mensagem = (
        f"Olá,\n\n"
        f"Você foi convidado para se cadastrar no sistema UniRota. "
        f"Acesse o link abaixo para concluir seu registro:\n\n"
        f"{link_convite}\n\n"
        f"Atenção: este convite é válido por {ttl_horas} horas.\n\n"
        f"Se não foi você quem solicitou, ignore este e-mail."
    )
    remetente = settings.DEFAULT_FROM_EMAIL
    try:
        sent = send_mail(
            subject=assunto,
            message=mensagem,
            from_email=remetente,
            recipient_list=[email_destino],
            fail_silently=False,
        )
        return sent != 0
    except SMTPException:
        return False
    except Exception:
        return False