"""Configuración del esqueleto Django MVT y sus componentes internos en MongoDB."""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

# Resuelve archivos locales desde techgear_web, independientemente del directorio de ejecución.
BASE_DIR = Path(__file__).resolve().parent.parent

# Las variables del servidor tienen prioridad: load_dotenv no las reemplaza por defecto.
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    raise ImproperlyConfigured("Define DJANGO_SECRET_KEY en el entorno o en .env")

DEBUG = os.environ.get("DJANGO_DEBUG", "False").lower() == "true"
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
    if host.strip()
]
# Las futuras vistas consumirán la API mediante esta dirección base.
TECHGEAR_API_URL = os.environ.get("TECHGEAR_API_URL", "http://127.0.0.1:8001").rstrip("/")

# Componentes preparados en Clase 1. El portal aún no implementa cuentas de clientes.
# La gestión de usuarios acordada para la API no debe duplicarse usando auth.User.
INSTALLED_APPS = [
    "config.apps.MongoAdminConfig",
    "config.apps.MongoAuthConfig",
    "config.apps.MongoContentTypesConfig",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_mongodb_backend",
]

# El orden conserva sesiones antes de autenticación y mensajes, y protección CSRF en formularios.
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

# APP_DIRS permite descubrir templates/ dentro de las futuras aplicaciones de Django.
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Persistencia de los componentes internos de Django; productos y pedidos pertenecen a la API.
DATABASES = {
    "default": {
        "ENGINE": "django_mongodb_backend",
        "HOST": os.environ.get("MONGO_URI", ""),
        "NAME": os.environ.get("MONGO_DB_NAME", "techgear_shop"),
        "OPTIONS": {"serverSelectionTimeoutMS": 10000, "connectTimeoutMS": 10000},
    }
}

# Validadores del administrador nativo. No validan los futuros endpoints de FastAPI.
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es-co"
TIME_ZONE = "America/Bogota"
USE_I18N = True
# Django conserva fechas con zona horaria y las presenta según TIME_ZONE.
USE_TZ = True

STATIC_URL = "static/"

# ObjectId sustituye las claves enteras de los componentes contrib de Django.
DEFAULT_AUTO_FIELD = "django_mongodb_backend.fields.ObjectIdAutoField"
DATABASE_ROUTERS = ["django_mongodb_backend.routers.MongoRouter"]
# Estas migraciones adaptadas pertenecen a la plantilla oficial del backend MongoDB.
# Definirlas no las ejecuta; su aplicación requiere un comando explícito de migración.
MIGRATION_MODULES = {
    "admin": "mongo_migrations.admin",
    "auth": "mongo_migrations.auth",
    "contenttypes": "mongo_migrations.contenttypes",
}

if not DATABASES["default"]["HOST"].startswith(("mongodb://", "mongodb+srv://")):
    raise ImproperlyConfigured("Define MONGO_URI con una URI válida de MongoDB")
