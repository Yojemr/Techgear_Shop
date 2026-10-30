"""Datos públicos de navegación para las plantillas de la tienda."""

from .forms import CATEGORIES


def storefront(request):
    return {
        "shop_account": getattr(request, "shop_account", None),
        "shop_auth_unavailable": getattr(request, "shop_auth_unavailable", False),
        "component_categories": CATEGORIES,
    }
