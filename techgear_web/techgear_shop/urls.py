"""Rutas de la interfaz del catálogo y de la sesión web."""

from django.urls import path

from . import cart, dashboard, order_dashboard, views

app_name = "shop"
urlpatterns = [
    path("", views.catalog, name="catalog"),
    path("ingresar/", views.login_view, name="login"),
    path("registro/", views.register_view, name="register"),
    path("salir/", views.logout_view, name="logout"),
    path("componentes/<slug:product_slug>/", views.product_detail, name="product_detail"),
    path("gestion/pedidos/", order_dashboard.order_list, name="managed_orders"),
    path(
        "gestion/pedidos/<str:order_id>/", order_dashboard.order_detail, name="managed_order_detail"
    ),
    path("gestion/productos/", dashboard.product_list, name="product_list"),
    path("gestion/productos/nuevo/", dashboard.product_form, name="product_create"),
    path("gestion/productos/<str:product_id>/editar/", dashboard.product_form, name="product_edit"),
    path(
        "gestion/productos/<str:product_id>/desactivar/",
        dashboard.product_delete,
        name="product_delete",
    ),
    path("carrito/", cart.cart_view, name="cart"),
    path(
        "carrito/agregar/<str:product_id>/", cart.cart_item, {"action": "agregar"}, name="cart_add"
    ),
    path(
        "carrito/cantidad/<str:product_id>/",
        cart.cart_item,
        {"action": "cantidad"},
        name="cart_quantity",
    ),
    path("carrito/vaciar/", cart.cart_clear, name="cart_clear"),
    path("carrito/presencia/", cart.cart_heartbeat, name="cart_heartbeat"),
    path("carrito/reservar/", cart.reserve_selection, name="cart_reserve"),
    path("carrito/confirmar/", cart.checkout, name="checkout"),
    path("pedidos/", cart.order_list, name="orders"),
    path("pedidos/<str:order_id>/", cart.order_detail, name="order_detail"),
    path("salud/", views.health, name="health"),
]
