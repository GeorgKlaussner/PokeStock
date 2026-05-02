from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from collection.models import CardVariant, OwnedCard
from collection.tests.factories import card_metadata


class OwnedCardValidationTests(TestCase):
    def test_quantity_must_be_positive(self):
        owned = OwnedCard(card=card_metadata(), quantity=0)

        with self.assertRaises(ValidationError):
            owned.full_clean()

    def test_purchase_price_cannot_be_negative(self):
        owned = OwnedCard(card=card_metadata(), quantity=1, purchase_price=Decimal("-1.00"))

        with self.assertRaises(ValidationError):
            owned.full_clean()

    def test_custom_variant_requires_label(self):
        owned = OwnedCard(card=card_metadata(), quantity=1, variant=CardVariant.CUSTOM)

        with self.assertRaises(ValidationError):
            owned.full_clean()

