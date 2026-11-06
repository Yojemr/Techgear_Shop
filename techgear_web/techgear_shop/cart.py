"""Vistas del carrito y pedidos: cada escritura se valida y ejecuta en FastAPI."""

from decimal import Decimal
from functools import wraps
from urllib.parse import urlencode

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from . import guest_cart
from .forms import CartQuantityForm, CheckoutForm
from .models import Cart
from .services.api import ApiClient, ApiError


def _json_request(request):
    return "application/json" in request.headers.get("Accept", "")


def account_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if request.shop_auth_unavailable:
            return _failure(request, ApiError(503, "No pudimos verificar tu sesión."))
        if not request.shop_account:
            if _json_request(request):
                return JsonResponse(
                    {
                        "error": "Inicia sesión para usar el carrito.",
                        "login_url": reverse("shop:login"),
                    },
                    status=401,
                )
            return redirect(reverse("shop:login") + "?" + urlencode({"next": reverse("shop:cart")}))
        return view(request, *args, **kwargs)

    return wrapped


def _failure(request, error):
    if _json_request(request):
        return JsonResponse({"error": str(error)}, status=error.status_code)
    messages.error(request, str(error))
    return redirect("shop:cart")


def _cart_response(request, cart=None, *, notice=""):
    client = ApiClient()
    if request.shop_account:
        cart = cart if cart is not None else client.cart(request.session["access_token"])
        pending = guest_cart.snapshot(request.session, client)
    else:
        cart = guest_cart.snapshot(request.session, client)
        pending = Cart(None, [], Decimal("0.00"))
    request.session["cart_count"] = cart.count if request.shop_account else 0
    context = {
        "cart": cart,
        "pending_cart": pending,
        "cart_notice": notice,
        "cart_dom_id": "panel" if _json_request(request) else "page",
    }
    if _json_request(request):
        try:
            stocks = {item.id: item.stock for item in client.products()}
        except ApiError:
            stocks = {}
        return JsonResponse(
            {
                "stocks": stocks,
                "html": render_to_string(
                    "techgear_shop/_cart_content.html", context, request=request
                ),
                "count": cart.count + pending.count,
            }
        )
    if notice:
        messages.success(request, notice)
        return redirect("shop:cart")
    return render(request, "techgear_shop/cart.html", context)


def _cart_page_error(request, error):
    if _json_request(request):
        return _failure(request, error)
    return render(
        request,
        "techgear_shop/error.html",
        {
            "error_title": "No pudimos cargar el carrito",
            "error_message": str(error),
        },
        status=503,
    )


@require_GET
@never_cache
def cart_view(request):
    if request.shop_auth_unavailable:
        return _cart_page_error(request, ApiError(503, "No pudimos verificar tu sesión."))
    try:
        return _cart_response(request)
    except ApiError as error:
        return _cart_page_error(request, error)


@require_POST
@never_cache
def cart_item(request, product_id, action):
    if request.shop_auth_unavailable:
        return _failure(request, ApiError(503, "No pudimos verificar tu sesión."))
    form = CartQuantityForm(request.POST)
    if not form.is_valid():
        return _failure(request, ApiError(422, "Elige una cantidad entre 0 y 99."))
    client = ApiClient()
    try:
        if not request.shop_account or request.POST.get("bucket") == "pending":
            guest_cart.change(
                request.session,
                client,
                product_id,
                form.cleaned_data["quantity"],
                add=action == "agregar",
            )
            return _cart_response(
                request, notice="Selección actualizada. Aún no reserva inventario."
            )
        cart = client.change_cart(
            product_id,
            form.cleaned_data["quantity"],
            request.session["access_token"],
            add=action == "agregar",
        )
        return _cart_response(request, cart, notice="Carrito actualizado.")
    except ApiError as error:
        return _failure(request, error)


@require_POST
@never_cache
def cart_clear(request):
    if request.shop_auth_unavailable:
        return _failure(request, ApiError(503, "No pudimos verificar tu sesión."))
    try:
        cart = (
            ApiClient().clear_cart(request.session["access_token"])
            if request.shop_account
            else None
        )
        guest_cart.clear(request.session)
        return _cart_response(request, cart, notice="Carrito vacío.")
    except ApiError as error:
        return _failure(request, error)


@require_POST
@never_cache
@account_required
def reserve_selection(request):
    try:
        cart = guest_cart.reserve(request.session, ApiClient(), request.session["access_token"])
        return _cart_response(request, cart, notice="Tus productos están reservados.")
    except ApiError as error:
        return _failure(request, error)


@require_POST
@never_cache
@account_required
def cart_heartbeat(request):
    try:
        result = ApiClient().heartbeat(request.session["access_token"])
    except ApiError as error:
        return _failure(request, error)
    request.session["cart_count"] = result["count"]
    return JsonResponse({"count": result["count"] + guest_cart.count(request.session)})


@require_POST
@never_cache
@account_required
def checkout(request):
    if guest_cart.selection(request.session):
        # Reservar es un paso explícito y distinto de confirmar: permite revisar el total vigente.
        messages.info(
            request, "Reserva los productos pendientes y revisa el total antes de confirmar."
        )
        return redirect("shop:cart")
    form = CheckoutForm(request.POST)
    if not form.is_valid():
        return _failure(request, ApiError(422, "Actualiza el carrito antes de confirmar."))
    try:
        order = ApiClient().checkout(
            form.cleaned_data["version"],
            form.cleaned_data["expected_total"],
            request.session["access_token"],
        )
    except ApiError as error:
        messages.error(
            request, str(error) + " Si la conexión falló, revisa Mis pedidos antes de repetir."
        )
        return redirect("shop:cart")
    request.session["cart_count"] = 0
    messages.success(request, "Pedido confirmado. No se ha realizado ningún cobro.")
    return redirect("shop:order_detail", order_id=order.id)


@require_GET
@never_cache
@account_required
def order_list(request):
    try:
        # El endpoint actual permite lectura global al admin; la tienda muestra solo sus pedidos.
        orders = ApiClient().orders(request.session["access_token"])
    except ApiError as error:
        return render(
            request,
            "techgear_shop/error.html",
            {
                "error_title": "No pudimos cargar los pedidos",
                "error_message": str(error),
            },
            status=503,
        )
    return render(request, "techgear_shop/orders.html", {"orders": orders})


@require_GET
@never_cache
@account_required
def order_detail(request, order_id):
    try:
        order = ApiClient().order(order_id, request.session["access_token"])
    except ApiError as error:
        return render(
            request,
            "techgear_shop/error.html",
            {
                "error_title": "No pudimos mostrar el pedido",
                "error_eyebrow": "CONSULTA DE PEDIDOS",
                "error_back_url": reverse("shop:orders"),
                "error_back_label": "Ir a Mis pedidos",
                "error_message": str(error),
            },
            status=404 if error.status_code == 404 else 503,
        )
    return render(request, "techgear_shop/order_detail.html", {"order": order})
