from __future__ import annotations

from decimal import Decimal

from django.utils import timezone

from collection.models import DEFAULT_OWNED_CARD_LANGUAGE, CardMetadata, OwnedCard, SetMetadata


def card_metadata(**overrides) -> CardMetadata:
    defaults = {
        "external_id": "base1-1",
        "name": "Bulbasaur",
        "set_id": "base1",
        "set_name": "Base",
        "set_series": "Base",
        "card_number": "44",
        "rarity": "Common",
        "latest_price_payload": {
            "updatedAt": "2024/01/01",
            "prices": {"trendPrice": 3.25, "reverseHoloTrend": 4.5, "averageSellPrice": 3.0, "lowPrice": 2.0},
        },
        "price_value": Decimal("3.00"),
        "price_source_field": "averageSellPrice",
        "price_currency": "EUR",
        "api_synced_at": timezone.now(),
    }
    defaults.update(overrides)
    return CardMetadata.objects.create(**defaults)


def set_metadata(**overrides) -> SetMetadata:
    defaults = {
        "external_id": "base1",
        "name": "Base",
        "series": "Base",
        "printed_total": 102,
        "total": 102,
        "logo_url": "https://example.test/logo.png",
        "symbol_url": "https://example.test/symbol.png",
        "api_synced_at": timezone.now(),
    }
    defaults.update(overrides)
    return SetMetadata.objects.create(**defaults)


def owned_card(**overrides) -> OwnedCard:
    card = overrides.pop("card", None) or card_metadata()
    defaults = {
        "card": card,
        "quantity": 1,
        "variant": "normal",
        "condition": "near_mint",
        "language": DEFAULT_OWNED_CARD_LANGUAGE,
    }
    defaults.update(overrides)
    return OwnedCard.objects.create(**defaults)
