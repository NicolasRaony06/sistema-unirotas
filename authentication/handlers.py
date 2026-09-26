from .models import User
from django.core.signing import TimestampSigner, BadSignature
from django.core.cache import cache

def get_invitation_data(token):
    signer = TimestampSigner()

    try:
        email = signer.unsign(token)
    except (BadSignature, ValueError):
        raise ValueError("Este convite expirou ou já foi utilizado.")
    cache_key = f"invitation_{token}"

    invitation_data = cache.get(cache_key)
    return email, invitation_data, cache_key

def validate_invitation_integraty(invitation_data):
    role = invitation_data.get("role")
    higher_role_email = invitation_data.get("higher_role_email")
    higher_obj = User.objects.filter(email__iexact=higher_role_email).first()

    if not higher_obj:
        raise ValueError("Este convite expirou ou já foi utilizado.")
    if  not higher_obj.can_invite(role):
        raise ValueError("Este convite expirou ou já foi utilizado.")
    return role, higher_role_email, higher_obj
