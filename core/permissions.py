from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def role_required(*roles):
    """Exige sesión iniciada y que el rol del usuario esté permitido (RBAC en servidor)."""
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(request, *args, **kwargs):
            if request.user.rol not in roles:
                from .models import AuditLog
                AuditLog.objects.create(usuario=request.user, accion="ACCESO_DENEGADO", detalle=request.path[:200])
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapped
    return decorator
