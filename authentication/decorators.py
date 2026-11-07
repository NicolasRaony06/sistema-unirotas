from functools import wraps
from collections.abc import Callable, Iterable
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from .models import UserRole
from django.shortcuts import redirect

def unloged_required(view_func):
    @wraps(view_func)
    def _wrapped_view(req, *args, **kwargs):
        if not req.user.is_authenticated:
            return view_func(req, *args, **kwargs)
        
        role = req.user.role
        if role == "STUDENT":
            default_redirect = 'index_aluno'
        elif role == "DRIVER":
            default_redirect = 'lista_viagens'
        elif role == "MANAGER" or role == "ADMIN":
            default_redirect = "management:home"
        return redirect(default_redirect)
    return _wrapped_view

            
def role_required(

    allowed_roles:UserRole | Iterable[UserRole],
    on_denied:Callable[[HttpRequest], HttpResponse]=lambda request, *args, **kwargs: HttpResponseForbidden("Acesso negado."),
):
    roles = allowed_roles if isinstance(allowed_roles, Iterable) else [allowed_roles]

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if request.user.is_authenticated and getattr(request.user, "role", None) in roles:
                return view_func(request, *args, **kwargs)

            return on_denied(request)

        return _wrapped_view

    return decorator