from __future__ import annotations

from decimal import Decimal

from django import template

register = template.Library()


@register.filter
def money(value: Decimal | None, currency: str = "EUR") -> str:
    if value is None:
        return "Unavailable"
    return f"{value:,.2f} {currency}"

