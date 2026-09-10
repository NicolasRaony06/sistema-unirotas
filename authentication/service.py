from django.core.signing import Signer
from django.urls import reverse
from django.core.cache import cache
from django.core.mail import send_mail

def generate_elevated_signup_link(higher_role_email, email, role, request=None):
    signer = Signer()
    token = signer.sign(email)

    cache_key = f"invitation_{token}"
    pointer_key = f"invitation_pointer_{higher_role_email}_{email}"

    cache.set(cache_key, {'email': email, 'role': role, "higher_role_email": higher_role_email}, timeout=86400)
    cache.set(pointer_key, {"cache_key": cache_key}, timeout=86400)

    relative_url = reverse('elevated_signup', kwargs={'token': token})
    absolute_url = request.build_absolute_uri(relative_url) if request else relative_url

    enviar_email_convite(email, absolute_url)
    
    return absolute_url

def abort_elevated_signup_link(higher_role_email, email):
    signer = Signer()
    token = signer.sign(email)

    cache_key = f"invitation_{token}"
    pointer_key = f"invitation_pointer_{higher_role_email}_{email}"

    cache.delete(cache_key)
    cache.delete(pointer_key)

def recreate_elevated_signup_link(higher_role_email, email, role, request=None):
    abort_elevated_signup_link(higher_role_email, email)
    return generate_elevated_signup_link(higher_role_email, email, role, request)

def enviar_email_convite(email_destino, link_convite):
    assunto = "Convite para cadastro na plataforma"
    mensagem = f"Olá,\n\nVocê foi convidado para se cadastrar. Acesse o link abaixo para concluir seu registro:\n\n{link_convite}\n\nSe não foi você que solicitou, ignore este e-mail."
    remetente = "noreply@seusite.com"
    
    send_mail(
        subject=assunto,
        message=mensagem,
        from_email=remetente,
        recipient_list=[email_destino],
        fail_silently=False, # Se True, abafa erros de envio; False dispara exceção se falhar
    )

