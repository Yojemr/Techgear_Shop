"""Expone la aplicación Django para servidores compatibles con WSGI."""

import os

from django.core.wsgi import get_wsgi_application

# Conserva una configuración ya seleccionada por el proceso que inicia Django.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()
