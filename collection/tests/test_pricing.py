from __future__ import annotations

from decimal import Decimal

from django.test import SimpleTestCase

from collection.models import CardCondition, CardVariant
from collection.services.pricing import adjust_owned_price_value, select_cardmarket_price


class PriceSelectionTests(SimpleTestCase):
    def test_uses_average_sell_price_for_normal_cards(self):
        selection = select_cardmarket_price(
            {"updatedAt": "2024/02/03", "prices": {"trendPrice": 12.345, "averageSellPrice": 10, "lowPrice": 8}},
            CardVariant.NORMAL,
        )

        self.assertEqual(selection.value, Decimal("10.00"))
        self.assertEqual(selection.source_field, "averageSellPrice")
        self.assertEqual(selection.upstream_updated_at.isoformat(), "2024-02-03")

    def test_reverse_holo_prefers_reverse_holo_average_sell_price(self):
        selection = select_cardmarket_price(
            {"prices": {"trendPrice": 12, "reverseHoloSell": 14.5, "reverseHoloTrend": 15.5, "averageSellPrice": 10}},
            CardVariant.REVERSE_HOLOFOIL,
        )

        self.assertEqual(selection.value, Decimal("14.50"))
        self.assertEqual(selection.source_field, "reverseHoloSell")

    def test_falls_back_to_trend_then_low_when_average_is_missing(self):
        trend_selection = select_cardmarket_price({"prices": {"trendPrice": 4.2, "averageSellPrice": None, "lowPrice": 1}})
        low_selection = select_cardmarket_price({"prices": {"trendPrice": None, "averageSellPrice": None, "lowPrice": 1.5}})

        self.assertEqual(trend_selection.value, Decimal("4.20"))
        self.assertEqual(trend_selection.source_field, "trendPrice")
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

    def test_adjusts_for_condition(self):
        selection = select_cardmarket_price(
            {"prices": {"averageSellPrice": 10}},
            condition=CardCondition.GOOD,
        )

        self.assertEqual(selection.value, Decimal("7.00"))
        self.assertEqual(selection.source_field, "averageSellPrice")

    def test_uses_german_language_price_when_lower(self):
        selection = select_cardmarket_price(
            {"prices": {"averageSellPrice": 10, "germanProLow": 6.5}},
            language="de",
        )

        self.assertEqual(selection.value, Decimal("6.50"))
        self.assertEqual(selection.source_field, "germanProLow")

    def test_applies_language_discount_when_specific_language_price_is_unavailable(self):
        selection = select_cardmarket_price(
            {"prices": {"averageSellPrice": 10}},
            language="ja",
        )

        self.assertEqual(selection.value, Decimal("9.00"))
        self.assertEqual(selection.source_field, "averageSellPrice")

    def test_adjusts_cached_card_price_without_payload(self):
        value = adjust_owned_price_value(Decimal("10.00"), language="ja", condition=CardCondition.EXCELLENT)

        self.assertEqual(value, Decimal("7.65"))
