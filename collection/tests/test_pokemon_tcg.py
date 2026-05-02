from __future__ import annotations

import ssl
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from collection.models import SetMetadata
from collection.services.pokemon_tcg import PokemonTCGClient, build_search_query, upsert_card_metadata, upsert_set_metadata


class PokemonTCGClientTests(TestCase):
    def test_build_search_query_escapes_phrases(self):
        query = build_search_query(query='Mr. "Mime"', set_name="Base", card_number="6", rarity="Rare")

        self.assertIn('name:"Mr. \\"Mime\\""', query)
        self.assertIn('set.name:"Base"', query)
        self.assertIn('number:"6"', query)
        self.assertIn('rarity:"Rare"', query)

    def test_search_cards_uses_api_payload_data(self):
        class StubClient(PokemonTCGClient):
            def _get(self, path, params):
                self.path = path
                self.params = params
                return {"data": [{"id": "x"}]}

        client = StubClient(base_url="https://example.test", api_key="")

        data = client.search_cards(query="Pikachu", page_size=5)

        self.assertEqual(data, [{"id": "x"}])
        self.assertEqual(client.path, "/cards")
        self.assertEqual(client.params["pageSize"], "5")
        self.assertEqual(client.params["page"], "1")

    def test_api_requests_use_unverified_ssl_context(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return b'{"data": []}'

        client = PokemonTCGClient(base_url="https://example.test", api_key="")

        with patch("collection.services.pokemon_tcg.urllib.request.urlopen", return_value=Response()) as urlopen:
            payload = client.get_cards_page(query='name:"Pikachu"')

        self.assertEqual(payload, {"data": []})
        context = urlopen.call_args.kwargs["context"]
        request = urlopen.call_args.args[0]
        self.assertEqual(context.verify_mode, ssl.CERT_NONE)
        self.assertFalse(context.check_hostname)
        self.assertEqual(request.get_header("User-agent"), "PokeStock/1.0")

    def test_fetch_set_cards_paginates_until_total_count(self):
        class StubClient(PokemonTCGClient):
            def __init__(self):
                super().__init__(base_url="https://example.test", api_key="")
                self.pages = []

            def get_cards_page(self, *, query, page=1, page_size=250, order_by="number"):
                self.pages.append((query, page, page_size, order_by))
                if page == 1:
                    return {"data": [{"id": "a"}], "totalCount": 2}
                return {"data": [{"id": "b"}], "totalCount": 2}

        client = StubClient()

        cards = client.fetch_set_cards("sv3pt5", page_size=1)

        self.assertEqual(cards, [{"id": "a"}, {"id": "b"}])
        self.assertEqual(client.pages[0], ('set.id:"sv3pt5"', 1, 1, "number"))
        self.assertEqual(client.pages[1], ('set.id:"sv3pt5"', 2, 1, "number"))

    def test_fetch_sets_paginates_until_total_count(self):
        class StubClient(PokemonTCGClient):
            def __init__(self):
                super().__init__(base_url="https://example.test", api_key="")
                self.pages = []

            def get_sets_page(self, *, page=1, page_size=250, order_by="-releaseDate"):
                self.pages.append((page, page_size, order_by))
                if page == 1:
                    return {"data": [{"id": "sv1"}], "totalCount": 2}
                return {"data": [{"id": "sv2"}], "totalCount": 2}

        client = StubClient()

        sets = client.fetch_sets(page_size=1)

        self.assertEqual(sets, [{"id": "sv1"}, {"id": "sv2"}])
        self.assertEqual(client.pages[0], (1, 1, "-releaseDate"))
        self.assertEqual(client.pages[1], (2, 1, "-releaseDate"))

    def test_upserts_set_metadata(self):
        set_metadata = upsert_set_metadata(
            {
                "id": "sv3pt5",
                "name": "151",
                "series": "Scarlet & Violet",
                "printedTotal": 165,
                "total": 207,
                "releaseDate": "2023/09/22",
                "updatedAt": "2024/02/01 12:00:00",
                "images": {
                    "logo": "https://example.test/logo.png",
                    "symbol": "https://example.test/symbol.png",
                },
            }
        )

        self.assertEqual(set_metadata.external_id, "sv3pt5")
        self.assertEqual(set_metadata.name, "151")
        self.assertEqual(set_metadata.printed_total, 165)
        self.assertEqual(set_metadata.total, 207)
        self.assertEqual(set_metadata.logo_url, "https://example.test/logo.png")

    def test_upserts_card_metadata_and_price(self):
        card = upsert_card_metadata(
            {
                "id": "sv1-1",
                "name": "Sprigatito",
                "number": "1",
                "rarity": "Common",
                "updatedAt": "2024/01/02",
                "images": {"small": "https://example.test/small.png", "large": "https://example.test/large.png"},
                "set": {"id": "sv1", "name": "Scarlet & Violet", "series": "Scarlet & Violet", "releaseDate": "2023/03/31"},
                "cardmarket": {"url": "https://example.test/card", "updatedAt": "2024/02/01", "prices": {"trendPrice": 1.23}},
            }
        )

        self.assertEqual(card.external_id, "sv1-1")
        self.assertEqual(card.set_name, "Scarlet & Violet")
        self.assertEqual(card.price_value, Decimal("1.23"))
        self.assertEqual(card.price_source_field, "trendPrice")
        self.assertTrue(SetMetadata.objects.filter(external_id="sv1").exists())
