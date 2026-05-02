from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from collection.models import CardMetadata, SetMetadata
from collection.services.set_progress import cached_set_progresses, ensure_set_checklist, refresh_set_catalog, refresh_set_metadata, set_card_progress
from collection.tests.factories import card_metadata, owned_card, set_metadata


class SetProgressTests(TestCase):
    def test_calculates_cached_set_progress(self):
        owned = card_metadata(external_id="sv1-1", set_id="sv1", set_name="Scarlet & Violet", card_number="1")
        card_metadata(external_id="sv1-2", set_id="sv1", set_name="Scarlet & Violet", card_number="2")
        owned_card(card=owned, quantity=2)

        progress, cards = set_card_progress("sv1")

        self.assertIsNotNone(progress)
        self.assertEqual(progress.total_cards, 2)
        self.assertEqual(progress.owned_cards, 1)
        self.assertEqual(progress.owned_quantity, 2)
        self.assertEqual(progress.missing_cards, 1)
        self.assertEqual(progress.completion_percent, 50)
        self.assertTrue(cards[0].is_owned)
        self.assertFalse(cards[1].is_owned)

    def test_uses_official_set_total_when_catalog_exists(self):
        set_metadata(external_id="sv3pt5", name="151", total=207)
        owned = card_metadata(external_id="sv3pt5-6", set_id="sv3pt5", set_name="151", card_number="6")
        owned_card(card=owned)

        progress, cards = set_card_progress("sv3pt5")

        self.assertEqual(progress.total_cards, 207)
        self.assertEqual(progress.cached_cards, 1)
        self.assertEqual(progress.owned_cards, 1)
        self.assertEqual(progress.missing_cards, 206)
        self.assertEqual(progress.completion_percent, 0)
        self.assertFalse(progress.checklist_complete)
        self.assertEqual(len(cards), 1)

    def test_lists_cached_sets(self):
        card_metadata(external_id="sv1-1", set_id="sv1", set_name="Scarlet & Violet")
        card_metadata(external_id="sv2-1", set_id="sv2", set_name="Paldea Evolved")

        progress = cached_set_progresses()

        self.assertEqual([item.set_id for item in progress], ["sv2", "sv1"])

    def test_lists_catalog_sets_without_cached_cards(self):
        set_metadata(external_id="sv1", name="Scarlet & Violet", total=258)

        progress = cached_set_progresses()

        self.assertEqual(len(progress), 1)
        self.assertEqual(progress[0].set_id, "sv1")
        self.assertEqual(progress[0].total_cards, 258)
        self.assertEqual(progress[0].cached_cards, 0)

    def test_owned_only_progress_excludes_sets_without_owned_cards(self):
        owned = card_metadata(external_id="sv1-1", set_id="sv1", set_name="Scarlet & Violet")
        card_metadata(external_id="sv2-1", set_id="sv2", set_name="Paldea Evolved")
        set_metadata(external_id="sv3", name="Obsidian Flames", total=230)
        owned_card(card=owned)

        progress = cached_set_progresses(owned_only=True)

        self.assertEqual([item.set_id for item in progress], ["sv1"])

    def test_refresh_set_catalog_upserts_sets(self):
        payload = [
            {
                "id": "sv3pt5",
                "name": "151",
                "series": "Scarlet & Violet",
                "printedTotal": 165,
                "total": 207,
                "releaseDate": "2023/09/22",
                "images": {"logo": "https://example.test/logo.png", "symbol": "https://example.test/symbol.png"},
            }
        ]

        with patch("collection.services.set_progress.PokemonTCGClient.fetch_sets", return_value=payload):
            count = refresh_set_catalog()

        self.assertEqual(count, 1)
        self.assertEqual(SetMetadata.objects.get(external_id="sv3pt5").total, 207)

    def test_refresh_set_metadata_upserts_fetched_cards(self):
        payload = [
            {
                "id": "sv1-1",
                "name": "Sprigatito",
                "number": "1",
                "set": {"id": "sv1", "name": "Scarlet & Violet"},
                "cardmarket": {"prices": {"trendPrice": 1.0}},
            }
        ]

        with patch("collection.services.set_progress.PokemonTCGClient.fetch_set_cards", return_value=payload):
            count = refresh_set_metadata("sv1")

        self.assertEqual(count, 1)
        self.assertTrue(CardMetadata.objects.filter(external_id="sv1-1").exists())

    def test_ensure_set_checklist_fetches_when_incomplete(self):
        set_metadata(external_id="sv1", name="Scarlet & Violet", total=2)
        payload = [
            {
                "id": "sv1-1",
                "name": "Sprigatito",
                "number": "1",
                "set": {"id": "sv1", "name": "Scarlet & Violet", "total": 2},
                "cardmarket": {"prices": {"trendPrice": 1.0}},
            },
            {
                "id": "sv1-2",
                "name": "Fuecoco",
                "number": "2",
                "set": {"id": "sv1", "name": "Scarlet & Violet", "total": 2},
                "cardmarket": {"prices": {"trendPrice": 1.0}},
            },
        ]

        with patch("collection.services.set_progress.PokemonTCGClient.fetch_set_cards", return_value=payload):
            count = ensure_set_checklist("sv1")

        self.assertEqual(count, 2)
        self.assertEqual(CardMetadata.objects.filter(set_id="sv1").count(), 2)

    def test_ensure_set_checklist_fetches_when_catalog_missing(self):
        card_metadata(external_id="sv1-1", set_id="sv1", set_name="Scarlet & Violet", card_number="1")
        payload = [
            {
                "id": "sv1-1",
                "name": "Sprigatito",
                "number": "1",
                "set": {"id": "sv1", "name": "Scarlet & Violet", "total": 2},
                "cardmarket": {"prices": {"trendPrice": 1.0}},
            },
            {
                "id": "sv1-2",
                "name": "Fuecoco",
                "number": "2",
                "set": {"id": "sv1", "name": "Scarlet & Violet", "total": 2},
                "cardmarket": {"prices": {"trendPrice": 1.0}},
            },
        ]

        with patch("collection.services.set_progress.PokemonTCGClient.fetch_set_cards", return_value=payload):
            count = ensure_set_checklist("sv1")

        self.assertEqual(count, 2)
        self.assertEqual(SetMetadata.objects.get(external_id="sv1").total, 2)
