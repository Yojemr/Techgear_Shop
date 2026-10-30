"""Configuración de Django MVT, sesiones en MongoDB y consumo de FastAPI."""

import os
from pathlib import Path
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
# Las variables del proceso prevalecen sobre el archivo privado local.
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
TECHGEAR_API_URL = os.environ.get("TECHGEAR_API_URL", "http://127.0.0.1:8001").rstrip("/")
TECHGEAR_API_TIMEOUT = 8.0
api_url = urlsplit(TECHGEAR_API_URL)
# Fuera de loopback las credenciales solo deben viajar por HTTPS.
if (
    api_url.scheme not in ("http", "https")
    or not api_url.hostname
    or api_url.username
    or api_url.password
    or api_url.query
    or api_url.fragment
    or (api_url.scheme == "http" and api_url.hostname not in ("localhost", "127.0.0.1", "::1"))
):
    raise ImproperlyConfigured("TECHGEAR_API_URL debe ser HTTPS o HTTP local sin credenciales.")

INSTALLED_APPS = [
    "config.apps.MongoAdminConfig",
    "config.apps.MongoAuthConfig",
    "config.apps.MongoContentTypesConfig",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "techgear_shop.apps.TechgearShopConfig",
    "django_mongodb_backend",
]
# La sesión y los mensajes deben existir antes de validar la identidad de la API.
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "techgear_shop.middleware.ApiSessionMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
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
                "techgear_shop.context_processors.storefront",
            ],
        },
    },
]
WSGI_APPLICATION = "config.wsgi.application"

# MongoDB también almacena django_session; las cuentas comerciales siguen en FastAPI.
DATABASES = {
    "default": {
        "ENGINE": "django_mongodb_backend",
        "HOST": os.environ.get("MONGO_URI", ""),
        "NAME": os.environ.get("MONGO_DB_NAME", "techgear_shop"),
        "OPTIONS": {"serverSelectionTimeoutMS": 10000, "connectTimeoutMS": 10000},
    }
}
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_NAME = "techgear_session"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_AGE = 1800
CSRF_COOKIE_NAME = "techgear_csrf"
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = not DEBUG

# Estos validadores solo corresponden al administrador nativo, no al login de la tienda.
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "es-co"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django_mongodb_backend.fields.ObjectIdAutoField"
DATABASE_ROUTERS = ["django_mongodb_backend.routers.MongoRouter"]
# La configuración no ejecuta migraciones: la preparación se realiza mediante comando explícito.
MIGRATION_MODULES = {
    "admin": "mongo_migrations.admin",
    "auth": "mongo_migrations.auth",
    "contenttypes": "mongo_migrations.contenttypes",
}
if not DATABASES["default"]["HOST"].startswith(("mongodb://", "mongodb+srv://")):
    raise ImproperlyConfigured("Define MONGO_URI con una URI válida de MongoDB")
