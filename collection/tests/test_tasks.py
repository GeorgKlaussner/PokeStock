from __future__ import annotations

import tempfile
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from collection.models import CardMetadata, OCRJob
from collection.tasks import process_ocr_job, refresh_card_metadata, refresh_owned_card_prices
from collection.tests.factories import card_metadata, owned_card


class TaskTests(TestCase):
    def test_refresh_owned_card_prices_refreshes_distinct_cards(self):
        first = card_metadata(external_id="a-1")
        second = card_metadata(external_id="b-1", name="Second")
        owned_card(card=first)
        owned_card(card=first, quantity=2)
        owned_card(card=second)

        with patch("collection.tasks.refresh_card_metadata") as refresh:
            count = refresh_owned_card_prices()

        self.assertEqual(count, 2)
        self.assertEqual(refresh.call_count, 2)

    def test_refresh_card_metadata_records_api_data(self):
        card = card_metadata(external_id="sv1-99")
        payload = {
            "id": "sv1-99",
            "name": "Updated",
            "number": "99",
            "set": {"id": "sv1", "name": "Scarlet & Violet"},
            "cardmarket": {"prices": {"trendPrice": 2.5}},
        }

        with patch("collection.tasks.PokemonTCGClient.get_card", return_value=payload):
            result = refresh_card_metadata(card.id)

        card.refresh_from_db()
        self.assertEqual(result, "ok")
        self.assertEqual(card.name, "Updated")

    def test_process_ocr_job_stores_candidates(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                job = OCRJob.objects.create(image=SimpleUploadedFile("card.jpg", b"image-bytes", content_type="image/jpeg"))
                payload = {
                    "id": "sv1-25",
                    "name": "Miraidon",
                    "number": "25",
                    "set": {"id": "sv1", "name": "Scarlet & Violet"},
                    "cardmarket": {"prices": {"trendPrice": 3}},
                }

                with patch("collection.tasks.OCRClient.extract_text", return_value="Miraidon\n25/198"):
                    with patch("collection.tasks.PokemonTCGClient.search_cards", return_value=[payload]):
                        result = process_ocr_job(job.id)

                job.refresh_from_db()
                self.assertEqual(result, "ok")
                self.assertEqual(job.status, OCRJob.Status.COMPLETE)
                self.assertEqual(job.candidate_ids, ["sv1-25"])
                self.assertTrue(CardMetadata.objects.filter(external_id="sv1-25").exists())

