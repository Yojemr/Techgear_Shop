"""Expone la aplicación Django para servidores compatibles con ASGI."""

import os

from django.core.asgi import get_asgi_application

# Conserva una configuración ya seleccionada por el proceso que inicia Django.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_asgi_application()
