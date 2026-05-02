from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from collection.models import CardCondition, CardVariant


@dataclass(frozen=True)
class PriceSelection:
    value: Decimal | None
    source_field: str
    currency: str = "EUR"
    upstream_updated_at: date | None = None


CONDITION_VALUE_FACTORS = {
    CardCondition.MINT: Decimal("1.00"),
    CardCondition.NEAR_MINT: Decimal("1.00"),
    CardCondition.EXCELLENT: Decimal("0.85"),
    CardCondition.GOOD: Decimal("0.70"),
    CardCondition.LIGHT_PLAYED: Decimal("0.60"),
    CardCondition.PLAYED: Decimal("0.45"),
    CardCondition.POOR: Decimal("0.25"),
    CardCondition.UNKNOWN: Decimal("0.75"),
}
NON_ENGLISH_LANGUAGE_FACTOR = Decimal("0.90")


def adjust_owned_price_value(
    value: Decimal | None,
    *,
    language: str = "en",
    condition: str = CardCondition.NEAR_MINT,
) -> Decimal | None:
    if value is None:
        return None
    adjusted_value = value * _condition_factor(condition)
    adjusted_value *= _language_factor(language, "")
    return adjusted_value.quantize(Decimal("0.01"))


def select_cardmarket_price(
    cardmarket: dict[str, Any],
    variant: str = CardVariant.NORMAL,
    *,
    language: str = "en",
    condition: str = CardCondition.NEAR_MINT,
) -> PriceSelection:
    prices = cardmarket.get("prices") or {}
    upstream_updated_at = _parse_upstream_date(cardmarket.get("updatedAt"))
    selection = _select_variant_price(prices, variant, upstream_updated_at)
    language_selection = _select_language_price(prices, variant, language, upstream_updated_at)
    if _should_use_language_price(selection, language_selection):
        selection = language_selection

    if selection.value is None:
        return selection

    adjusted_value = selection.value * _condition_factor(condition)
    adjusted_value *= _language_factor(language, selection.source_field)
    return PriceSelection(
        value=adjusted_value.quantize(Decimal("0.01")),
        source_field=selection.source_field,
        upstream_updated_at=selection.upstream_updated_at,
    )


def _select_variant_price(prices: dict[str, Any], variant: str, upstream_updated_at: date | None) -> PriceSelection:
    fields = [
        "averageSellPrice",
        "avgSellPrice",
        "avg7",
        "avg30",
        "avg1",
        "trendPrice",
        "lowPriceExPlus",
        "lowPrice",
    ]
    if variant == CardVariant.REVERSE_HOLOFOIL:
        fields = [
            "reverseHoloSell",
            "reverseHoloAvg7",
            "reverseHoloAvg30",
            "reverseHoloAvg1",
            "reverseHoloTrend",
            "reverseHoloLow",
            *fields,
        ]

    for field in fields:
        value = _decimal_or_none(prices.get(field))
        if value is not None:
            return PriceSelection(value=value, source_field=field, upstream_updated_at=upstream_updated_at)

    return PriceSelection(value=None, source_field="", upstream_updated_at=upstream_updated_at)


def _select_language_price(
    prices: dict[str, Any],
    variant: str,
    language: str,
    upstream_updated_at: date | None,
) -> PriceSelection:
    if variant == CardVariant.REVERSE_HOLOFOIL or not _is_german_language(language):
        return PriceSelection(value=None, source_field="", upstream_updated_at=upstream_updated_at)

    value = _decimal_or_none(prices.get("germanProLow"))
    if value is None:
        return PriceSelection(value=None, source_field="", upstream_updated_at=upstream_updated_at)
    return PriceSelection(value=value, source_field="germanProLow", upstream_updated_at=upstream_updated_at)


def _should_use_language_price(selection: PriceSelection, language_selection: PriceSelection) -> bool:
    if language_selection.value is None:
        return False
    if selection.value is None:
        return True
    return language_selection.value < selection.value


def _condition_factor(condition: str) -> Decimal:
    return CONDITION_VALUE_FACTORS.get(condition, CONDITION_VALUE_FACTORS[CardCondition.UNKNOWN])


def _language_factor(language: str, source_field: str) -> Decimal:
    if _is_default_market_language(language) or source_field == "germanProLow":
        return Decimal("1.00")
    return NON_ENGLISH_LANGUAGE_FACTOR


def _is_default_market_language(language: str) -> bool:
    normalized = _normalized_language(language)
    return not normalized or normalized in {"en", "eng", "english"}


def _is_german_language(language: str) -> bool:
    return _normalized_language(language) in {"de", "deu", "ger", "german"}


def _normalized_language(language: str) -> str:
    return language.strip().lower().split("-", maxsplit=1)[0]


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
