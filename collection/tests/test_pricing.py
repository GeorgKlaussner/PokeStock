from __future__ import annotations

from decimal import Decimal

from django.test import SimpleTestCase

from collection.models import CardVariant
from collection.services.pricing import select_cardmarket_price


class PriceSelectionTests(SimpleTestCase):
    def test_uses_trend_price_for_normal_cards(self):
        selection = select_cardmarket_price(
            {"updatedAt": "2024/02/03", "prices": {"trendPrice": 12.345, "averageSellPrice": 10, "lowPrice": 8}},
            CardVariant.NORMAL,
        )

        self.assertEqual(selection.value, Decimal("12.34"))
        self.assertEqual(selection.source_field, "trendPrice")
        self.assertEqual(selection.upstream_updated_at.isoformat(), "2024-02-03")

    def test_reverse_holo_prefers_reverse_holo_trend(self):
        selection = select_cardmarket_price(
            {"prices": {"trendPrice": 12, "reverseHoloTrend": 15.5, "averageSellPrice": 10, "lowPrice": 8}},
            CardVariant.REVERSE_HOLOFOIL,
        )

        self.assertEqual(selection.value, Decimal("15.50"))
        self.assertEqual(selection.source_field, "reverseHoloTrend")

    def test_falls_back_to_average_then_low(self):
        avg_selection = select_cardmarket_price({"prices": {"trendPrice": None, "averageSellPrice": 4.2, "lowPrice": 1}})
        low_selection = select_cardmarket_price({"prices": {"trendPrice": None, "averageSellPrice": None, "lowPrice": 1.5}})

        self.assertEqual(avg_selection.value, Decimal("4.20"))
        self.assertEqual(avg_selection.source_field, "averageSellPrice")
        self.assertEqual(low_selection.value, Decimal("1.50"))
        self.assertEqual(low_selection.source_field, "lowPrice")

    def test_marks_unavailable_when_all_fields_missing(self):
        selection = select_cardmarket_price({"prices": {"trendPrice": 0, "averageSellPrice": None}})

        self.assertIsNone(selection.value)
        self.assertEqual(selection.source_field, "")

    def test_keeps_legacy_average_key_as_secondary_fallback(self):
        selection = select_cardmarket_price({"prices": {"trendPrice": None, "avgSellPrice": 2.5}})

        self.assertEqual(selection.value, Decimal("2.50"))
        self.assertEqual(selection.source_field, "avgSellPrice")
