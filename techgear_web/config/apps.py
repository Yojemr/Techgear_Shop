"""Adapta los componentes contrib de Django para usar claves ObjectId."""

from django.contrib.admin.apps import AdminConfig
from django.contrib.auth.apps import AuthConfig
from django.contrib.contenttypes.apps import ContentTypesConfig


class MongoAdminConfig(AdminConfig):
    """Configuración del administrador nativo preparada para MongoDB."""

    default_auto_field = "django_mongodb_backend.fields.ObjectIdAutoField"


class MongoAuthConfig(AuthConfig):
    """Configuración de autenticación nativa compatible con ObjectId."""

    default_auto_field = "django_mongodb_backend.fields.ObjectIdAutoField"


class MongoContentTypesConfig(ContentTypesConfig):
    """Identificadores de tipos de contenido compatibles con MongoDB."""

    default_auto_field = "django_mongodb_backend.fields.ObjectIdAutoField"
