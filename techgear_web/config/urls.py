"""El catálogo es la entrada del sitio; el administrador nativo conserva su ruta."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("", include("techgear_shop.urls")),
    path("admin/", admin.site.urls),
]
