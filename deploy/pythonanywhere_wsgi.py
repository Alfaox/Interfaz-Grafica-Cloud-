# Copia este contenido al archivo WSGI que abre la pestaña Web de PythonAnywhere.
import os
from pathlib import Path
import sys

proyecto = str(Path.home() / 'agrokodit')
if proyecto not in sys.path:
    sys.path.insert(0, proyecto)
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pythonanywhere'
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
