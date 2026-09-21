from django.core.signing import TimestampSigner
from django.urls import reverse
from django.core.cache import cache
from django.core.mail import send_mail
from .models import User

def generate_elevated_signup_link(higher_role_email, email, role, request=None):
    higher_role_email = higher_role_email.lower().strip()
    email = email.lower().strip()
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

    cache.set(cache_key, {'email': email, 'role': role, "higher_role_email": higher_role_email}, timeout=86400)
    cache.set(pointer_key, {"cache_key": cache_key}, timeout=86400)
    
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

def recreate_elevated_signup_link(higher_role_email, email, role, request=None):
    higher_role_email = higher_role_email.lower().strip()
    email = email.lower().strip()
    abort_elevated_signup_link(higher_role_email, email)
    return generate_elevated_signup_link(higher_role_email, email, role, request)

def enviar_email_convite(email_destino, link_convite):
    email_destino = email_destino.lower().strip()
    assunto = "Convite para cadastro na plataforma"
    mensagem = f"Olá,\n\nVocê foi convidado para se cadastrar. Acesse o link abaixo para concluir seu registro:\n\n{link_convite}\n\nSe não foi você que solicitou, ignore este e-mail."
    remetente = "noreply@seusite.com"
    
    sent_account = send_mail(
        subject=assunto,
        message=mensagem,
        from_email=remetente,
        recipient_list=[email_destino],
        fail_silently=True,
    )

    return False if sent_account == 0 else True
