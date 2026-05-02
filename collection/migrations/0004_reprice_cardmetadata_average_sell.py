from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import migrations


PRICE_FIELDS = [
    "averageSellPrice",
    "avgSellPrice",
    "avg7",
    "avg30",
    "avg1",
    "trendPrice",
    "lowPriceExPlus",
    "lowPrice",
]


def reprice_card_metadata(apps, schema_editor):
    CardMetadata = apps.get_model("collection", "CardMetadata")

    for card in CardMetadata.objects.exclude(latest_price_payload={}):
        cardmarket = card.latest_price_payload or {}
        prices = cardmarket.get("prices") or {}
        value = None
        source_field = ""

        for field in PRICE_FIELDS:
            value = decimal_or_none(prices.get(field))
            if value is not None:
                source_field = field
                break

        card.price_value = value
        card.price_source_field = source_field
        card.price_upstream_updated_at = parse_upstream_date(cardmarket.get("updatedAt"))
        card.save(update_fields=["price_value", "price_source_field", "price_upstream_updated_at", "updated_at"])


def decimal_or_none(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if amount <= 0:
        return None
    return amount.quantize(Decimal("0.01"))


def parse_upstream_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value.replace("/", "-"))
    except ValueError:
        return None


class Migration(migrations.Migration):

    dependencies = [
        ("collection", "0003_setmetadata_checklist_refresh_queued_at"),
    ]

    operations = [
        migrations.RunPython(reprice_card_metadata, migrations.RunPython.noop),
    ]
