"""Rutas del esqueleto Django; el administrador nativo requiere sus migraciones."""

from django.contrib import admin
from django.urls import path

# Las páginas del catálogo, las cuentas y el carrito se incorporarán en sus aplicaciones MVT.
urlpatterns = [
    path("admin/", admin.site.urls),
]
