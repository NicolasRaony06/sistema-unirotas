from .models import User
from django.core.signing import TimestampSigner, BadSignature
from django.core.cache import cache
from django.conf import settings

def get_invitation_data(token):
    signer = TimestampSigner()

    try:
        email = signer.unsign(token, max_age=getattr(settings, "INVITE_TTL_SECONDS", 86400))
    except (BadSignature, ValueError):
        raise ValueError("Convite inválido.")
    cache_key = f"invitation_{token}"

    invitation_data = cache.get(cache_key)
    return email, invitation_data, cache_key

def validate_invitation_integrity(invitation_data):
    role = invitation_data.get("role")
    higher_role_email = invitation_data.get("higher_role_email")
    city_id = invitation_data.get("city_id")
    higher_obj = User.objects.filter(email__iexact=higher_role_email).first()

    if not higher_obj:
        raise ValueError("Este convite não é válido pois foi adulterado.")
    if  not higher_obj.can_invite(role):
        raise ValueError("Este convite não é válido pois foi adulterado.")
    return role, higher_role_email, city_id, higher_obj
