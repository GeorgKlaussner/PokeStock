from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from typing import Any

from django.conf import settings
from django.utils import timezone

from collection.models import CardMetadata, SetMetadata
from collection.services.pricing import select_cardmarket_price


class PokemonTCGAPIError(Exception):
    pass


class PokemonTCGClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None) -> None:
        self.base_url = (base_url or settings.POKEMONTCG_API_BASE_URL).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.POKEMONTCG_API_KEY
        self.ssl_context = ssl._create_unverified_context()

    def search_cards(
        self,
        *,
        query: str = "",
        set_name: str = "",
        card_number: str = "",
        rarity: str = "",
        page_size: int = 20,
        page: int = 1,
    ) -> list[dict[str, Any]]:
        search_query = build_search_query(
            query=query,
            set_name=set_name,
            card_number=card_number,
            rarity=rarity,
        )
        params = {"pageSize": str(page_size), "page": str(page), "orderBy": "set.releaseDate,number"}
        if search_query:
            params["q"] = search_query
        payload = self._get("/cards", params)
        return payload.get("data", [])

    def get_card(self, external_id: str) -> dict[str, Any]:
        payload = self._get(f"/cards/{urllib.parse.quote(external_id)}", {})
        return payload["data"]

    def get_sets_page(
        self,
        *,
        page: int = 1,
        page_size: int = 250,
        order_by: str = "-releaseDate",
    ) -> dict[str, Any]:
        return self._get(
            "/sets",
            {
                "page": str(page),
                "pageSize": str(page_size),
                "orderBy": order_by,
            },
        )

    def fetch_sets(self, *, page_size: int = 250) -> list[dict[str, Any]]:
        sets: list[dict[str, Any]] = []
        page = 1
        while True:
            payload = self.get_sets_page(page=page, page_size=page_size)
            page_sets = payload.get("data", [])
            sets.extend(page_sets)
            total_count = int(payload.get("totalCount") or len(sets))
            if not page_sets or len(sets) >= total_count:
                return sets
            page += 1

    def get_cards_page(
        self,
        *,
        query: str,
        page: int = 1,
        page_size: int = 250,
        order_by: str = "number",
    ) -> dict[str, Any]:
        return self._get(
            "/cards",
            {
                "q": query,
                "page": str(page),
                "pageSize": str(page_size),
                "orderBy": order_by,
            },
        )

    def fetch_set_cards(self, set_id: str, *, page_size: int = 250) -> list[dict[str, Any]]:
        query = f'set.id:"{_lucene_phrase(set_id)}"'
        cards: list[dict[str, Any]] = []
        page = 1
        while True:
            payload = self.get_cards_page(query=query, page=page, page_size=page_size)
            page_cards = payload.get("data", [])
            cards.extend(page_cards)
            total_count = int(payload.get("totalCount") or len(cards))
            if not page_cards or len(cards) >= total_count:
                return cards
            page += 1

    def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(url)
        request.add_header("User-Agent", "PokeStock/1.0")
        if self.api_key:
            request.add_header("X-Api-Key", self.api_key)
        try:
            with urllib.request.urlopen(request, timeout=20, context=self.ssl_context) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            raise PokemonTCGAPIError(f"PokemonTCG API returned HTTP {error.code}") from error
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            raise PokemonTCGAPIError(f"PokemonTCG API request failed: {error}") from error


def build_search_query(*, query: str = "", set_name: str = "", card_number: str = "", rarity: str = "") -> str:
    terms: list[str] = []
    if query.strip():
        terms.append(f'name:"{_lucene_phrase(query.strip())}"')
    if set_name.strip():
        terms.append(f'set.name:"{_lucene_phrase(set_name.strip())}"')
    if card_number.strip():
        terms.append(f'number:"{_lucene_phrase(card_number.strip())}"')
    if rarity.strip():
        terms.append(f'rarity:"{_lucene_phrase(rarity.strip())}"')
    return " ".join(terms)


def _lucene_phrase(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def upsert_set_metadata(set_data: dict[str, Any]) -> SetMetadata | None:
    external_id = set_data.get("id", "")
    if not external_id:
        return None

    images = set_data.get("images") or {}
    set_metadata, _ = SetMetadata.objects.update_or_create(
        external_id=external_id,
        defaults={
            "name": set_data.get("name", ""),
            "series": set_data.get("series", ""),
            "printed_total": int(set_data.get("printedTotal") or 0),
            "total": int(set_data.get("total") or 0),
            "release_date": _parse_date(set_data.get("releaseDate")),
            "symbol_url": images.get("symbol", ""),
            "logo_url": images.get("logo", ""),
            "api_updated_at": set_data.get("updatedAt", ""),
            "api_synced_at": timezone.now(),
            "last_sync_error": "",
            "last_sync_attempt_at": timezone.now(),
        },
    )
    return set_metadata


def upsert_card_metadata(card_data: dict[str, Any], *, variant_for_price: str = "") -> CardMetadata:
    external_id = card_data["id"]
    set_data = card_data.get("set") or {}
    images = card_data.get("images") or {}
    cardmarket = card_data.get("cardmarket") or {}
    price = select_cardmarket_price(cardmarket, variant_for_price)
    release_date = _parse_date(set_data.get("releaseDate"))
    upsert_set_metadata(set_data)

    card, _ = CardMetadata.objects.update_or_create(
        external_id=external_id,
        defaults={
            "name": card_data.get("name", ""),
            "set_id": set_data.get("id", ""),
            "set_name": set_data.get("name", ""),
            "set_series": set_data.get("series", ""),
            "card_number": card_data.get("number", ""),
            "rarity": card_data.get("rarity", ""),
            "image_small_url": images.get("small", ""),
            "image_large_url": images.get("large", ""),
            "release_date": release_date,
            "cardmarket_url": cardmarket.get("url", ""),
            "latest_price_payload": cardmarket,
            "api_updated_at": card_data.get("updatedAt", ""),
            "api_synced_at": timezone.now(),
            "price_value": price.value,
            "price_source_field": price.source_field,
            "price_currency": price.currency,
            "price_upstream_updated_at": price.upstream_updated_at,
            "last_sync_error": "",
            "last_sync_attempt_at": timezone.now(),
        },
    )
    return card


def mark_sync_error(card: CardMetadata, message: str) -> None:
    card.last_sync_attempt_at = timezone.now()
    card.last_sync_error = message
    card.save(update_fields=["last_sync_attempt_at", "last_sync_error", "updated_at"])


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value.replace("/", "-"))
    except ValueError:
        return None
