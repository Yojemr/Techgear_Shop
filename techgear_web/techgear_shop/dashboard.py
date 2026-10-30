"""Vistas administrativas MVT: los cambios se persisten únicamente mediante FastAPI."""

from functools import wraps
from urllib.parse import urlencode

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from .forms import DashboardFilterForm, ProductForm
from .services.api import ApiClient, ApiError


def admin_required(view):
    """Comprueba el perfil fresco que el middleware obtuvo de FastAPI, no datos del POST."""

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if request.shop_auth_unavailable:
            return _error_page(request, 503, "No pudimos verificar tu sesión. Intenta de nuevo.")
        if request.shop_account is None:
            query = urlencode({"next": request.get_full_path()})
            return redirect(f"{reverse('shop:login')}?{query}")
        if request.shop_account["role"] != "admin":
            return _error_page(
                request, 403, "Esta sección está disponible solo para administradores."
            )
        return view(request, *args, **kwargs)

    return wrapped


def _error_page(request, status, message):
    return render(
        request,
        "techgear_shop/error.html",
        {"error_title": "No pudimos completar la operación", "error_message": message},
        status=status,
    )


def _api_failure(request, error):
    """Un token rechazado se elimina; una caída temporal no borra la sesión del usuario."""
    if error.status_code == 401:
        request.session.flush()
        messages.info(request, "Tu sesión venció. Inicia sesión de nuevo.")
        query = urlencode({"next": request.path})
        return redirect(f"{reverse('shop:login')}?{query}")
    status = error.status_code if error.status_code in (403, 404) else 503
    return _error_page(request, status, str(error))


@never_cache
@require_GET
@admin_required
def product_list(request):
    """Presenta activos e inactivos; filtrar y consultar no cambia inventario."""
    form = DashboardFilterForm(request.GET)
    products = []
    error_message = ""
    status = 200
    if form.is_valid():
        try:
            products = ApiClient().products(
                token=request.session["access_token"],
                search=form.cleaned_data["q"],
                category=form.cleaned_data["category"],
            )
        except ApiError as error:
            if error.status_code in (401, 403):
                return _api_failure(request, error)
            error_message, status = str(error), 503
        state = form.cleaned_data["state"]
        if state:
            products = [p for p in products if p.active == (state == "active")]
        order = form.cleaned_data["sort"]
        if order:
            products.sort(key=lambda p: p.price, reverse=order == "price_desc")
    else:
        status = 400
    return render(
        request,
        "techgear_shop/dashboard/products.html",
        {
            "filter_form": form,
            "products": products,
            "error_message": error_message,
            "active_count": sum(p.active for p in products),
            "inactive_count": sum(not p.active for p in products),
            "empty_stock_count": sum(p.active and p.stock == 0 for p in products),
        },
        status=status,
    )


@never_cache
@require_http_methods(["GET", "POST"])
@admin_required
def product_form(request, product_id=None):
    """Recibe formularios con CSRF y traduce la acción a POST o PUT autenticado."""
    # El formato parcial conserva exactamente los mismos controles de rol y CSRF.
    modal = product_id is not None and request.GET.get("modal") == "1"
    client = ApiClient()
    product = None
    token = request.session["access_token"]
    if product_id:
        try:
            product = client.managed_product(product_id, token)
        except ApiError as error:
            return _api_failure(request, error)
    form = ProductForm(
        request.POST if request.method == "POST" else None,
        initial=ProductForm.initial_for(product) if product else None,
        prefix="product" if modal else None,
    )
    if request.method == "POST" and form.is_valid():
        try:
            client.save_product(form.payload(), token, identifier=product_id)
        except ApiError as error:
            if error.status_code == 409:
                form.add_error("sku", str(error))
            elif error.status_code in (400, 422):
                form.add_error(None, "Revisa los datos: la API no pudo validarlos.")
            else:
                return _api_failure(request, error)
        else:
            messages.success(request, "Producto actualizado." if product else "Producto creado.")
            if modal:
                return JsonResponse({"saved": True})
            # Redirección tras POST: recargar la tabla no repite la escritura.
            return redirect("shop:product_list")
    if modal:
        # Solo HTML de una plantilla escapada; el JWT nunca se entrega al navegador.
        html = render_to_string(
            "techgear_shop/dashboard/_product_modal_content.html",
            {"form": form, "product": product, "modal": True},
            request=request,
        )
        return JsonResponse(
            {"saved": False, "html": html},
            status=422 if request.method == "POST" else 200,
        )
    return render(
        request,
        "techgear_shop/dashboard/product_form.html",
        {"form": form, "product": product},
    )


@never_cache
@require_http_methods(["GET", "POST"])
@admin_required
def product_delete(request, product_id):
    """GET solo muestra confirmación; únicamente POST con CSRF envía DELETE a la API."""
    client = ApiClient()
    token = request.session["access_token"]
    try:
        product = client.managed_product(product_id, token)
        if request.method == "POST":
            if not product.active:
                messages.info(request, "Este producto ya está inactivo.")
            else:
                client.deactivate_product(product_id, token)
                messages.success(request, "Producto desactivado. Ya no aparece en el catálogo.")
            return redirect("shop:product_list")
    except ApiError as error:
        return _api_failure(request, error)
    return render(request, "techgear_shop/dashboard/product_delete.html", {"product": product})
