"""Datos públicos de navegación para las plantillas de la tienda."""

from . import guest_cart
from .forms import CATEGORIES


def storefront(request):
    return {
        "shop_account": getattr(request, "shop_account", None),
        "shop_auth_unavailable": getattr(request, "shop_auth_unavailable", False),
        "shop_cart_count": (
            request.session.get("cart_count", 0) if getattr(request, "shop_account", None) else 0
        )
        + guest_cart.count(request.session),
        "component_categories": CATEGORIES,
    }
