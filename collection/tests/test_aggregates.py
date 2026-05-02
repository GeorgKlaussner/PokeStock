from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from collection.models import CardCondition, CardVariant
from collection.services.aggregates import summarize_collection
from collection.tests.factories import card_metadata, owned_card


class AggregateTests(TestCase):
    def test_summarizes_collection_values_and_missing_prices(self):
        priced = card_metadata(
            external_id="base1-4",
            name="Charizard",
            set_name="Base",
            latest_price_payload={"prices": {"trendPrice": 100}},
            price_value=Decimal("100.00"),
        )
        missing = card_metadata(
            external_id="base1-5",
            name="Missing",
            set_name="Base",
            latest_price_payload={},
            price_value=None,
        )
        stale = card_metadata(
            external_id="neo1-1",
            name="Stale",
            set_name="Neo",
            latest_price_payload={"prices": {"trendPrice": 5}},
            price_value=Decimal("5.00"),
            api_synced_at=timezone.now() - timedelta(days=3),
        )
        owned_card(card=priced, quantity=2)
        owned_card(card=missing, quantity=3)
        owned_card(card=stale, quantity=1)

        summary = summarize_collection()

        self.assertEqual(summary.total_value, Decimal("205.00"))
        self.assertEqual(summary.total_quantity, 6)
        self.assertEqual(summary.missing_price_count, 3)
        self.assertEqual(summary.stale_price_count, 1)
        self.assertEqual(summary.value_by_set[0].set_name, "Base")

    def test_reverse_holo_owned_value_uses_reverse_holo_price(self):
        card = card_metadata(
            latest_price_payload={"prices": {"trendPrice": 2.0, "reverseHoloTrend": 7.5}},
            price_value=Decimal("2.00"),
        )
        owned = owned_card(card=card, variant=CardVariant.REVERSE_HOLOFOIL, quantity=2)

        self.assertEqual(owned.unit_value, Decimal("7.50"))
        self.assertEqual(owned.row_value, Decimal("15.00"))

    def test_owned_value_accounts_for_language_and_condition(self):
        card = card_metadata(
            latest_price_payload={"prices": {"averageSellPrice": 10, "germanProLow": 6.5}},
            price_value=Decimal("10.00"),
        )
        owned = owned_card(card=card, language="de", condition=CardCondition.GOOD, quantity=2)

        self.assertEqual(owned.unit_value, Decimal("4.55"))
        self.assertEqual(owned.row_value, Decimal("9.10"))
