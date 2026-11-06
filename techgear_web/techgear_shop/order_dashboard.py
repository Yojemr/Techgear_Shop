"""Gestión de pedidos: Django presenta y FastAPI autoriza cada operación."""

import secrets

from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from .dashboard import _api_failure, admin_required
from .forms import OrderActionForm, OrderFilterForm
from .services.api import ApiClient, ApiError

ACTIONS = {
    "confirmed": [("preparing", "Aceptar y preparar"), ("cancelled", "Rechazar pedido")],
    "preparing": [("shipped", "Marcar enviado"), ("cancelled", "Rechazar pedido")],
    "shipped": [("delivered", "Marcar entregado")],
    "delivered": [("returned", "Registrar devolución")],
}


@never_cache
@require_GET
@admin_required
def order_list(request):
    form = OrderFilterForm(request.GET)
    orders, error, code, page = [], "", 200, 1
    if form.is_valid():
        page = form.cleaned_data["page"] or 1
        try:
            orders = ApiClient().managed_orders(
                request.session["access_token"], state=form.cleaned_data["state"], page=page
            )
        except ApiError as exc:
            if exc.status_code in (401, 403):
                return _api_failure(request, exc)
            error, code = str(exc), 503
    else:
        code = 400
    return render(
        request,
        "techgear_shop/dashboard/orders.html",
        {
            "filter_form": form,
            "orders": orders[:20],
            "has_next": len(orders) > 20,
            "page": page,
            "previous_page": page - 1,
            "next_page": page + 1,
            "state": request.GET.get("state", ""),
            "error_message": error,
        },
        status=code,
    )


@never_cache
@require_http_methods(["GET", "POST"])
@admin_required
def order_detail(request, order_id):
    client, token = ApiClient(), request.session["access_token"]
    try:
        order = client.order(order_id, token)
    except ApiError as exc:
        return _api_failure(request, exc)
    form = OrderActionForm(request.POST if request.method == "POST" else None)
    code = 200
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            if data["action"] == "notify":
                client.notify_order(order_id, data["message"], data["request_id"], token)
            else:
                client.update_order(
                    order_id, data["action"], data["expected_status"], data["message"], token
                )
        except ApiError as exc:
            if exc.status_code in (401, 403, 404):
                return _api_failure(request, exc)
            form.add_error(None, str(exc))
            code = 409 if exc.status_code == 409 else 503
        else:
            messages.success(
                request,
                "Pedido actualizado. La novedad está disponible en Mis pedidos del cliente.",
            )
            return redirect("shop:managed_order_detail", order_id=order_id)
    elif request.method == "POST":
        code = 400
    return render(
        request,
        "techgear_shop/dashboard/order_detail.html",
        {
            "order": order,
            "form": form,
            "actions": ACTIONS.get(order.status, []),
            # Se conserva al mostrar errores para que repetir una notificación sea idempotente.
            "request_id": request.POST.get("request_id", secrets.token_hex(12)),
        },
        status=code,
    )
