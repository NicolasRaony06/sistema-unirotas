from functools import wraps
from collections.abc import Callable, Iterable
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from .models import UserRole



def role_required(
    allowed_roles:UserRole | Iterable[UserRole],
    on_denied:Callable[[HttpRequest], HttpResponse]=lambda request: HttpResponseForbidden(
        "Acesso negado."
    ),
):
  def decorator(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
      if request.user.is_authenticated and getattr(
          request.user, "role", None
      ) in (
          allowed_roles
          if isinstance(allowed_roles, (list, tuple))
          else [allowed_roles]
      ):
        return view_func(request, *args, **kwargs)

      return on_denied(request, *args, **kwargs)

    return _wrapped_view
  return decorator