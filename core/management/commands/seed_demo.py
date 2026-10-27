from django.core.management.base import BaseCommand

from core.models import User

DEMO = [
    ("admin", "Ana", "Administradora", User.Rol.ADMIN),
    ("jefe", "Jorge", "Jefe de Cuadrilla", User.Rol.JEFE),
    ("trabajador", "Tomás", "Trabajador", User.Rol.TRABAJADOR),
]


class Command(BaseCommand):
    help = "Crea usuarios de demostración (solo desarrollo)."

    def add_arguments(self, parser):
        parser.add_argument("--password", default="AgroKODIT2026!")

    def handle(self, *args, **o):
        for username, nombre, apellido, rol in DEMO:
            u, creado = User.objects.get_or_create(username=username, defaults=dict(first_name=nombre, last_name=apellido, rol=rol))
            if creado:
                u.set_password(o["password"]); u.save()
            self.stdout.write(f"{'creado' if creado else 'ya existe'}: {username} ({rol})")
