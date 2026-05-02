from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from collection.models import OwnedCard
from collection.services.csv_io import import_owned_cards_csv_bytes
from collection.tests.factories import card_metadata


class CSVImportTests(TestCase):
    def test_imports_by_card_id(self):
        card_metadata(external_id="sv1-10", name="Pikachu", set_name="Scarlet & Violet", card_number="10")
        csv_content = (
            "card_id,name,set_name,card_number,variant,language,condition,quantity,purchase_price,purchase_date,notes\n"
            "sv1-10,,,,normal,en,near_mint,2,1.25,2024-04-01,starter\n"
        )

        result = import_owned_cards_csv_bytes(csv_content.encode())

        self.assertEqual(result.created_count, 1)
        self.assertFalse(result.has_issues)
        self.assertEqual(OwnedCard.objects.get().quantity, 2)

    def test_imports_by_card_id_fetches_missing_metadata(self):
        csv_content = (
            "card_id,name,set_name,card_number,variant,language,condition,quantity,purchase_price,purchase_date,notes\n"
            "sv1-99,,,,normal,en,near_mint,1,,,\n"
        )
        payload = {
            "id": "sv1-99",
            "name": "Fetched",
            "number": "99",
            "set": {"id": "sv1", "name": "Scarlet & Violet"},
            "cardmarket": {"prices": {"trendPrice": 2.0}},
        }

        with patch("collection.services.csv_io.PokemonTCGClient.get_card", return_value=payload):
            result = import_owned_cards_csv_bytes(csv_content.encode())

        self.assertEqual(result.created_count, 1)
        self.assertEqual(OwnedCard.objects.get().card.name, "Fetched")

    def test_imports_by_exact_name_set_and_number(self):
        card_metadata(external_id="sv1-25", name="Miraidon", set_name="Scarlet & Violet", card_number="25")
        csv_content = (
            "card_id,name,set_name,card_number,variant,language,condition,quantity,purchase_price,purchase_date,notes\n"
            ",Miraidon,Scarlet & Violet,25,holofoil,en,excellent,1,,,\n"
        )

        result = import_owned_cards_csv_bytes(csv_content.encode())

        self.assertEqual(result.created_count, 1)
        self.assertEqual(OwnedCard.objects.get().variant, "holofoil")

    def test_ambiguous_rows_require_review(self):
        card_metadata(external_id="a-1", name="Eevee", set_name="Promo", card_number="1")
        card_metadata(external_id="b-1", name="Eevee", set_name="Promo", card_number="1")
        csv_content = (
            "card_id,name,set_name,card_number,variant,language,condition,quantity,purchase_price,purchase_date,notes\n"
            ",Eevee,Promo,1,normal,en,near_mint,1,,,\n"
        )

        result = import_owned_cards_csv_bytes(csv_content.encode())

        self.assertEqual(result.created_count, 0)
        self.assertEqual(len(result.issues), 1)
        self.assertIn("Ambiguous", result.issues[0].message)
