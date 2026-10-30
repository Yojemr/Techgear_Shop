"""Presentación de moneda colombiana sin convertir importes a float."""

from decimal import Decimal, InvalidOperation

from django import template

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
