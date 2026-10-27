"""Configuración exclusiva del sitio publicado; la configuración local no cambia."""
import json
from django.core.exceptions import ImproperlyConfigured
from .settings import *  # noqa: F403

CONFIG_FILE = Path.home() / '.agrokodit-produccion.json'
try:
    configuracion = json.loads(CONFIG_FILE.read_text())
except (OSError, ValueError) as exc:
    raise ImproperlyConfigured('Falta configurar PythonAnywhere. Ejecuta: python scripts/configurar_pythonanywhere.py --host TU_DOMINIO') from exc

SECRET_KEY = configuracion.get('secret_key', '')
ALLOWED_HOSTS = configuracion.get('hosts', [])
if len(SECRET_KEY) < 50 or not ALLOWED_HOSTS or not all(isinstance(h, str) and '*' not in h and '/' not in h and h for h in ALLOWED_HOSTS):
    raise ImproperlyConfigured('La configuración privada de PythonAnywhere no es válida.')
DEBUG = False
CSRF_TRUSTED_ORIGINS = ['https://' + host for host in ALLOWED_HOSTS]
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SECURE_HSTS_SECONDS = 31536000
REQUIRE_DEMO_PASSWORD = True
