"""Rutas de la interfaz del catálogo y de la sesión web."""

from django.urls import path

from . import dashboard, views

app_name = "shop"
urlpatterns = [
    path("", views.catalog, name="catalog"),
    path("ingresar/", views.login_view, name="login"),
    path("salir/", views.logout_view, name="logout"),
    path("componentes/<str:product_id>/", views.product_detail, name="product_detail"),
    path("gestion/productos/", dashboard.product_list, name="product_list"),
    path("gestion/productos/nuevo/", dashboard.product_form, name="product_create"),
    path("gestion/productos/<str:product_id>/editar/", dashboard.product_form, name="product_edit"),
    path(
        "gestion/productos/<str:product_id>/desactivar/",
        dashboard.product_delete,
        name="product_delete",
    ),
    path("salud/", views.health, name="health"),
]
