"""Identidad web basada en el JWT de la API, sin cuentas comerciales duplicadas."""

import time

from django.contrib import messages

from .services.api import ApiClient, ApiError


class ApiSessionMiddleware:
    """Vence sesiones localmente y consulta el perfil vigente cuando hay un token."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.shop_account = None
        request.shop_auth_unavailable = False
        token = request.session.get("access_token")
        if token:
            expires_at = request.session.get("auth_expires_at", 0)
            if not isinstance(expires_at, (int, float)) or expires_at <= time.time():
                request.session.flush()
                messages.info(request, "Tu sesión venció. Inicia sesión de nuevo.")
            else:
                try:
                    request.shop_account = ApiClient().profile(token)
                except ApiError as error:
                    if error.status_code in (401, 403):
                        request.session.flush()
                        messages.info(request, "Tu sesión ya no es válida. Ingresa de nuevo.")
                    else:
                        # Una caída temporal no debe borrar la sesión ni otorgar un rol sin validar.
                        request.shop_auth_unavailable = True
        return self.get_response(request)
