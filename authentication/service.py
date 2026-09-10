from django.core.signing import Signer
from django.urls import reverse
from django.core.cache import cache

def generate_elevated_signup_link(email, role, request=None):
    signer = Signer()
    token = signer.sign(email)

    cache_key = f"invitation_{token}"
    cache.set(cache_key, {'email': email, 'role': role}, timeout=86400)

    relative_url = reverse('elevated_signup', kwargs={'token': token})
    
    if request:
        return request.build_absolute_uri(relative_url)
        
    return relative_url
