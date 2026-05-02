from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from collection.models import OwnedCard
from collection.tests.factories import card_metadata, set_metadata


class ManualAddFlowTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username="admin", password="password")
        self.client.force_login(self.user)

    def test_search_caches_candidates(self):
        payload = {
            "id": "sv1-10",
            "name": "Pikachu",
            "number": "10",
            "set": {"id": "sv1", "name": "Scarlet & Violet"},
            "cardmarket": {"prices": {"trendPrice": 1.5}},
        }

        with patch("collection.views.PokemonTCGClient.search_cards", return_value=[payload]):
            response = self.client.get(reverse("add_search"), {"q": "Pikachu"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pikachu")

    def test_add_search_lists_all_synced_sets(self):
        for index in range(85):
            set_metadata(external_id=f"set{index}", name=f"Set {index}", total=10)

        response = self.client.get(reverse("add_search"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Set 0")
        self.assertContains(response, "Set 84")

    def test_add_search_filters_sets_by_external_id(self):
        set_metadata(external_id="sv3pt5", name="151", series="Scarlet & Violet", total=207)

        response = self.client.get(reverse("add_search"), {"set_q": "sv3pt5"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "151")

    def test_add_owned_card_creates_row(self):
        card = card_metadata(external_id="sv1-10", name="Pikachu")

        response = self.client.post(
            reverse("add_owned_card", args=[card.external_id]),
            {
                "variant": "normal",
                "variant_custom": "",
                "language": "en",
                "condition": "near_mint",
                "quantity": "2",
                "purchase_price": "",
                "purchase_date": "",
                "notes": "",
            },
        )

        self.assertRedirects(response, reverse("card_detail", args=[card.external_id]))
        self.assertEqual(OwnedCard.objects.get().quantity, 2)

    def test_edit_owned_card_updates_quantity(self):
        card = card_metadata(external_id="sv1-10", name="Pikachu")
        owned = OwnedCard.objects.create(card=card, quantity=1)

        response = self.client.post(
            reverse("edit_owned_card", args=[owned.id]),
            {
                "variant": "normal",
                "variant_custom": "",
                "language": "en",
                "condition": "near_mint",
                "quantity": "4",
                "purchase_price": "",
                "purchase_date": "",
                "notes": "",
            },
        )

        self.assertRedirects(response, reverse("card_detail", args=[card.external_id]))
        owned.refresh_from_db()
        self.assertEqual(owned.quantity, 4)

    def test_delete_owned_card_removes_row(self):
        card = card_metadata(external_id="sv1-10", name="Pikachu")
        owned = OwnedCard.objects.create(card=card, quantity=1)

        response = self.client.post(reverse("delete_owned_card", args=[owned.id]))

        self.assertRedirects(response, reverse("card_detail", args=[card.external_id]))
        self.assertFalse(OwnedCard.objects.filter(id=owned.id).exists())

    def test_collection_list_renders_owned_card_actions(self):
        card = card_metadata(external_id="sv1-10", name="Pikachu")
        owned = OwnedCard.objects.create(card=card, quantity=1)

        response = self.client.get(reverse("collection_list"))

        self.assertContains(response, reverse("edit_owned_card", args=[owned.id]))
        self.assertContains(response, reverse("delete_owned_card", args=[owned.id]))

    def test_set_pages_render_owned_and_missing_cards(self):
        set_metadata(external_id="sv1", name="Scarlet & Violet", total=2)
        owned_card_metadata = card_metadata(
            external_id="sv1-1",
            name="Sprigatito",
            set_id="sv1",
            set_name="Scarlet & Violet",
            card_number="1",
        )
        card_metadata(
            external_id="sv1-2",
            name="Fuecoco",
            set_id="sv1",
            set_name="Scarlet & Violet",
            card_number="2",
        )
        OwnedCard.objects.create(card=owned_card_metadata, quantity=1)

        index_response = self.client.get(reverse("sets_index"))
        detail_response = self.client.get(reverse("set_detail", args=["sv1"]))

        self.assertContains(index_response, "Scarlet &amp; Violet")
        self.assertContains(index_response, "1 / 2 owned")
        self.assertContains(detail_response, "Sprigatito")
        self.assertContains(detail_response, "is-missing")
        self.assertContains(detail_response, "<details class=\"set-card", html=False)

    def test_sets_index_only_lists_sets_with_owned_cards(self):
        owned_card_metadata = card_metadata(
            external_id="sv1-1",
            name="Sprigatito",
            set_id="sv1",
            set_name="Scarlet & Violet",
            card_number="1",
        )
        card_metadata(
            external_id="sv2-1",
            name="Pikachu",
            set_id="sv2",
            set_name="Paldea Evolved",
            card_number="1",
        )
        set_metadata(external_id="sv3", name="Obsidian Flames", total=230)
        OwnedCard.objects.create(card=owned_card_metadata, quantity=1)

        response = self.client.get(reverse("sets_index"))

        self.assertContains(response, "Scarlet &amp; Violet")
        self.assertNotContains(response, "Paldea Evolved")
        self.assertNotContains(response, "Obsidian Flames")

    def test_set_detail_paginates_cards(self):
        set_metadata(external_id="sv1", name="Scarlet & Violet", total=50)
        first_card = None
        for index in range(1, 51):
            card = card_metadata(
                external_id=f"sv1-{index}",
                name=f"Card {index}",
                set_id="sv1",
                set_name="Scarlet & Violet",
                card_number=str(index),
            )
            first_card = first_card or card
        OwnedCard.objects.create(card=first_card, quantity=1)

        first_page = self.client.get(reverse("set_detail", args=["sv1"]))
        second_page = self.client.get(reverse("set_detail", args=["sv1"]), {"page": 2})

        self.assertContains(first_page, "Page 1 of 2")
        self.assertContains(first_page, "Card 48")
        self.assertNotContains(first_page, "Card 49")
        self.assertContains(second_page, "Page 2 of 2")
        self.assertContains(second_page, "Card 49")

    def test_set_detail_uses_official_total_for_incomplete_checklist(self):
        set_metadata(external_id="sv3pt5", name="151", total=207)
        card = card_metadata(
            external_id="sv3pt5-6",
            name="Charizard ex",
            set_id="sv3pt5",
            set_name="151",
            card_number="6",
        )
        OwnedCard.objects.create(card=card, quantity=1)

        with patch("collection.views.ensure_set_checklist", return_value=1):
            response = self.client.get(reverse("set_detail", args=["sv3pt5"]))

        self.assertContains(response, "1 of 207 cards owned")
        self.assertContains(response, "0% complete")
