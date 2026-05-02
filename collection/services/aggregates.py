from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Prefetch, QuerySet

from collection.models import CardMetadata, OwnedCard


@dataclass(frozen=True)
class SetValue:
    set_name: str
    value: Decimal
    owned_count: int


@dataclass(frozen=True)
class CollectionSummary:
    total_value: Decimal
    total_quantity: int
    owned_rows: int
    missing_price_count: int
    stale_price_count: int
    value_by_set: list[SetValue]


def summarize_collection(queryset: QuerySet[OwnedCard] | None = None) -> CollectionSummary:
    owned_cards = list((queryset or OwnedCard.objects.all()).select_related("card"))
    total_value = Decimal("0.00")
    total_quantity = 0
    missing_price_count = 0
    stale_card_ids: set[int] = set()
    set_values: dict[str, Decimal] = {}
    set_counts: dict[str, int] = {}

    for owned in owned_cards:
        total_quantity += owned.quantity
        set_name = owned.card.set_name or "Unknown set"
        set_counts[set_name] = set_counts.get(set_name, 0) + owned.quantity
        if owned.card.is_price_stale:
            stale_card_ids.add(owned.card_id)
        if owned.row_value is None:
            missing_price_count += owned.quantity
            continue
        total_value += owned.row_value
        set_values[set_name] = set_values.get(set_name, Decimal("0.00")) + owned.row_value

    value_by_set = [
        SetValue(set_name=set_name, value=value, owned_count=set_counts.get(set_name, 0))
        for set_name, value in set_values.items()
    ]
    value_by_set.sort(key=lambda item: item.value, reverse=True)

    return CollectionSummary(
        total_value=total_value,
        total_quantity=total_quantity,
        owned_rows=len(owned_cards),
        missing_price_count=missing_price_count,
        stale_price_count=len(stale_card_ids),
        value_by_set=value_by_set,
    )


def cards_with_owned_records() -> QuerySet[CardMetadata]:
    return CardMetadata.objects.filter(owned_cards__isnull=False).prefetch_related(
        Prefetch("owned_cards", queryset=OwnedCard.objects.order_by("variant", "condition"))
    ).distinct()

