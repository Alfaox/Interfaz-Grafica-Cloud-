from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from .models import AuditLog


def _ip(request):
    return request.META.get("REMOTE_ADDR") if request else None


@receiver(user_logged_in)
def on_login(sender, request, user, **kw):
    AuditLog.objects.create(usuario=user, accion="LOGIN", ip=_ip(request))


@receiver(user_logged_out)
def on_logout(sender, request, user, **kw):
    if user:
        AuditLog.objects.create(usuario=user, accion="LOGOUT", ip=_ip(request))


@receiver(user_login_failed)
def on_fail(sender, credentials, request=None, **kw):
    AuditLog.objects.create(accion="LOGIN_FALLIDO", detalle=str(credentials.get("username", ""))[:150], ip=_ip(request))
