"""Presentación de moneda colombiana sin convertir importes a float."""

from decimal import Decimal, InvalidOperation

from django import template
from django.utils import timezone
from django.utils.dateparse import parse_datetime

register = template.Library()


@register.filter
def cop(value):
    """Conserva centavos cuando existen y utiliza separadores locales."""
    try:
        amount = Decimal(str(value))
        if not amount.is_finite():
            return "—"
        rendered = format(amount, ",.2f")
        integer, fraction = rendered.rsplit(".", 1)
        integer = integer.replace(",", ".")
        return "$" + integer + ("," + fraction if fraction != "00" else "")
    except InvalidOperation, ValueError:
        return "—"


@register.filter
def order_date(value):
    """Presenta fechas de la API en la zona horaria configurada de la tienda."""
    try:
        parsed = parse_datetime(value)
        if parsed is None or timezone.is_naive(parsed):
            return "Fecha no disponible"
        return timezone.localtime(parsed).strftime("%d/%m/%Y · %H:%M")
    except TypeError, ValueError:
        return "Fecha no disponible"
