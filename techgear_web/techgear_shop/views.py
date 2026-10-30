"""Vistas MVT: coordinan formularios, API y plantillas sin modificar inventario."""

import time
from datetime import timedelta

from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .forms import CatalogFilterForm, LoginForm
from .services.api import ApiClient, ApiError


@require_GET
@never_cache
def catalog(request):
    """La búsqueda consulta FastAPI; el orden visual conserva importes Decimal."""
    form = CatalogFilterForm(request.GET)
    products = []
    error_message = ""
    status = 200
    if form.is_valid():
        try:
            products = ApiClient().products(
                search=form.cleaned_data["q"], category=form.cleaned_data["category"]
            )
            order = form.cleaned_data["sort"]
            if order in ("price_asc", "price_desc"):
                products.sort(key=lambda item: item.price, reverse=order == "price_desc")
        except ApiError as error:
            error_message = str(error)
            status = 503
    else:
        status = 400
    return render(
        request,
        "techgear_shop/catalog.html",
        {
            "products": products,
            "filter_form": form,
            "error_message": error_message,
            "selected_category": request.GET.get("category", ""),
            "search_query": request.GET.get("q", ""),
            "sort_order": request.GET.get("sort", ""),
            "has_filters": bool(request.GET.get("q") or request.GET.get("category")),
        },
        status=status,
    )


@require_GET
@never_cache
def product_detail(request, product_id):
    """Presenta la ficha de un componente activo; ninguna visita reserva existencias."""
    try:
        product = ApiClient().product(product_id)
    except ApiError as error:
        return render(
            request,
            "techgear_shop/error.html",
            {
                "error_title": "Componente no encontrado"
                if error.status_code == 404
                else "No pudimos cargar el componente",
                "error_message": str(error),
            },
            status=404 if error.status_code == 404 else 503,
        )
    return render(request, "techgear_shop/product_detail.html", {"product": product})


def _safe_next(request):
    """Solo acepta retornos al mismo sitio, evitando redirecciones externas tras el login."""
    target = request.POST.get("next", request.GET.get("next", ""))
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return target
    return reverse("shop:catalog")


@require_http_methods(["GET", "POST"])
@never_cache
@sensitive_post_parameters("password")
@sensitive_variables("grant", "password")
def login_view(request):
    if request.shop_account:
        return redirect("shop:catalog")
    form = LoginForm(request.POST if request.method == "POST" else None)
    target = _safe_next(request)
    if request.method == "POST" and form.is_valid():
        try:
            client = ApiClient()
            grant = client.login(form.cleaned_data["email"], form.cleaned_data["password"])
            # El perfil debe validarse antes de considerar autenticada la sesión.
            client.profile(grant.access_token)
        except ApiError as error:
            form.add_error(None, str(error))
        else:
            # flush elimina cualquier sesión previa y evita conservar un identificador fijado.
            request.session.flush()
            request.session["access_token"] = grant.access_token
            request.session["auth_expires_at"] = int(time.time()) + grant.expires_in
            # Usar fecha absoluta impide alargar el JWT al modificar la sesión más adelante.
            request.session.set_expiry(timezone.now() + timedelta(seconds=grant.expires_in))
            return redirect(target)
    return render(
        request,
        "techgear_shop/login.html",
        {
            "form": form,
            "next": target,
        },
    )


@require_POST
@never_cache
def logout_view(request):
    """Cierra esta sesión del servidor; el token de la API conserva su vencimiento original."""
    request.session.flush()
    return redirect("shop:login")


@require_GET
def health(request):
    """Comprobación web ligera; no consulta la API ni MongoDB."""
    return HttpResponse("ok", content_type="text/plain")
