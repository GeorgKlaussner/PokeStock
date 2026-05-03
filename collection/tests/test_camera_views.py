from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from collection.models import CardCondition, CardVariant, OCRJob, OwnedCard
from collection.tests.factories import card_metadata


class CameraAddTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username="admin", password="password")
        self.client.force_login(self.user)

    def test_camera_page_renders_capture_flow(self):
        response = self.client.get(reverse("camera_add"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'capture="environment"')
        self.assertContains(response, "camera_add.js")
        self.assertContains(response, "multilingual OCR")
        self.assertNotContains(response, "tesseract.js")

    def test_camera_candidates_accepts_text_without_storing_image(self):
        payload = {
            "id": "sv1-25",
            "name": "Miraidon",
            "number": "25",
            "set": {"id": "sv1", "name": "Scarlet & Violet"},
            "images": {"small": "https://example.test/card.png"},
            "cardmarket": {"prices": {"trendPrice": 3}},
        }

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                with patch("collection.views.PokemonTCGClient.search_cards", return_value=[payload]) as search:
                    response = self.client.post(
                        reverse("camera_candidates"),
                        data=json.dumps({"text": "Miraidon\n25/198"}),
                        content_type="application/json",
                    )

                data = response.json()

                self.assertEqual(response.status_code, 200)
                self.assertEqual(data["candidates"][0]["external_id"], "sv1-25")
                self.assertEqual(OCRJob.objects.count(), 0)
                self.assertEqual(list(Path(media_root).rglob("*")), [])
                search.assert_called_once()

    def test_camera_candidates_falls_back_to_card_number_for_translated_names(self):
        payload = {
            "id": "sv1-25",
            "name": "Miraidon",
            "number": "25",
            "set": {"id": "sv1", "name": "Scarlet & Violet"},
            "cardmarket": {"prices": {"trendPrice": 3}},
        }

        with patch("collection.views.PokemonTCGClient.search_cards", side_effect=[[], [payload]]) as search:
            response = self.client.post(
                reverse("camera_candidates"),
                data=json.dumps({"text": "ミライドン\n25/198"}),
                content_type="application/json",
            )

        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["candidates"][0]["external_id"], "sv1-25")
        self.assertEqual(search.call_count, 2)
        self.assertEqual(search.call_args.kwargs["card_number"], "25")

    def test_camera_candidates_accepts_image_without_storing_image(self):
        payload = {
            "id": "sv1-25",
            "name": "Miraidon",
            "number": "25",
            "set": {"id": "sv1", "name": "Scarlet & Violet"},
            "images": {"small": "https://example.test/card.png"},
            "cardmarket": {"prices": {"trendPrice": 3}},
        }

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                with patch("collection.views.OCRClient.extract_text_bytes", return_value="Miraidon\n25/198") as ocr:
                    with patch("collection.views.PokemonTCGClient.search_cards", return_value=[payload]):
                        response = self.client.post(
                            reverse("camera_candidates"),
                            data={
                                "image": SimpleUploadedFile(
                                    "card.jpg",
                                    b"image-bytes",
                                    content_type="image/jpeg",
                                )
                            },
                        )

                data = response.json()

                self.assertEqual(response.status_code, 200)
                self.assertEqual(data["text"], "Miraidon\n25/198")
                self.assertEqual(data["candidates"][0]["external_id"], "sv1-25")
                self.assertEqual(OCRJob.objects.count(), 0)
                self.assertEqual(list(Path(media_root).rglob("*")), [])
                ocr.assert_called_once_with(b"image-bytes")

    def test_quick_add_uses_default_owned_card_details(self):
        card = card_metadata(external_id="sv1-25", name="Miraidon")

        response = self.client.post(reverse("quick_add_card", args=[card.external_id]))

        self.assertRedirects(response, reverse("card_detail", args=[card.external_id]))
        owned = OwnedCard.objects.get()
        self.assertEqual(owned.card, card)
        self.assertEqual(owned.quantity, 1)
        self.assertEqual(owned.variant, CardVariant.NORMAL)
        self.assertEqual(owned.language, "de")
        self.assertEqual(owned.condition, CardCondition.NEAR_MINT)

    def test_quick_add_increments_existing_default_owned_card(self):
        card = card_metadata(external_id="sv1-25", name="Miraidon")
        OwnedCard.objects.create(
            card=card,
            variant=CardVariant.NORMAL,
            language="de",
            condition=CardCondition.NEAR_MINT,
            quantity=2,
        )

        response = self.client.post(reverse("quick_add_card", args=[card.external_id]))

        self.assertRedirects(response, reverse("card_detail", args=[card.external_id]))
        owned = OwnedCard.objects.get()
        self.assertEqual(owned.quantity, 3)
