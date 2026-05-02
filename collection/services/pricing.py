from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from collection.models import CardVariant


@dataclass(frozen=True)
class PriceSelection:
    value: Decimal | None
    source_field: str
    currency: str = "EUR"
    upstream_updated_at: date | None = None


def select_cardmarket_price(cardmarket: dict[str, Any], variant: str = CardVariant.NORMAL) -> PriceSelection:
    prices = cardmarket.get("prices") or {}
    fields = ["trendPrice", "averageSellPrice", "avgSellPrice", "lowPrice"]
    if variant == CardVariant.REVERSE_HOLOFOIL:
        fields = ["reverseHoloTrend", *fields]

    for field in fields:
        value = _decimal_or_none(prices.get(field))
        if value is not None:
            return PriceSelection(
                value=value,
                source_field=field,
                upstream_updated_at=_parse_upstream_date(cardmarket.get("updatedAt")),
            )

    return PriceSelection(
        value=None,
        source_field="",
        upstream_updated_at=_parse_upstream_date(cardmarket.get("updatedAt")),
    )


def _decimal_or_none(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if amount <= 0:
        return None
    return amount.quantize(Decimal("0.01"))


def _parse_upstream_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value.replace("/", "-")
    try:
        return date.fromisoformat(normalized)
    except ValueError:
        return None
