from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from django.db.models import Count, Min, Sum

from collection.models import CardMetadata, OwnedCard, SetMetadata
from collection.services.pokemon_tcg import PokemonTCGClient, upsert_card_metadata, upsert_set_metadata


@dataclass(frozen=True)
class SetProgress:
    set_id: str
    set_name: str
    set_series: str
    total_cards: int
    owned_cards: int
    owned_quantity: int
    missing_cards: int
    completion_percent: int
    cached_cards: int
    checklist_complete: bool
    release_date: date | None = None
    logo_url: str = ""


@dataclass(frozen=True)
class SetCardProgress:
    card: CardMetadata
    owned_quantity: int

    @property
    def is_owned(self) -> bool:
        return self.owned_quantity > 0


def cached_set_progresses(*, owned_only: bool = False) -> list[SetProgress]:
    owned_set_ids = set(
        OwnedCard.objects.exclude(card__set_id="")
        .values_list("card__set_id", flat=True)
        .distinct()
    )
    if owned_only:
        set_ids = owned_set_ids
    else:
        catalog_ids = set(SetMetadata.objects.values_list("external_id", flat=True))
        card_ids = set(
            CardMetadata.objects.exclude(set_id="")
            .values_list("set_id", flat=True)
            .distinct()
        )
        set_ids = catalog_ids | card_ids
    progresses = list(_build_set_progresses(set_ids).values())
    progresses.sort(key=lambda item: item.set_name)
    progresses.sort(key=lambda item: item.release_date or date.min, reverse=True)
    return progresses


def set_progress(set_id: str) -> SetProgress | None:
    return _build_set_progresses([set_id]).get(set_id)


def _build_set_progresses(set_ids: Iterable[str]) -> dict[str, SetProgress]:
    normalized_set_ids = list(dict.fromkeys(set_id for set_id in set_ids if set_id))
    if not normalized_set_ids:
        return {}

    set_metadatas = {
        item.external_id: item
        for item in SetMetadata.objects.filter(external_id__in=normalized_set_ids)
    }
    cached_cards_by_set = _cached_card_counts_by_set(normalized_set_ids)
    representatives_by_set = _representative_cards_by_set(normalized_set_ids)
    owned_totals_by_set = _owned_totals_by_set(normalized_set_ids)

    progresses: dict[str, SetProgress] = {}
    for set_id in normalized_set_ids:
        set_metadata = set_metadatas.get(set_id)
        owned_totals = owned_totals_by_set.get(set_id, (0, 0))
        progress = _build_set_progress(
            set_id,
            cached_cards_by_set.get(set_id, 0),
            set_metadata,
            representatives_by_set.get(set_id),
            owned_card_count=owned_totals[0],
            owned_quantity=owned_totals[1],
        )
        if progress is not None:
            progresses[set_id] = progress
    return progresses


def _build_set_progress(
    set_id: str,
    cached_cards: int,
    set_metadata: SetMetadata | None,
    representative: CardMetadata | None,
    *,
    owned_card_count: int,
    owned_quantity: int,
) -> SetProgress | None:
    if cached_cards == 0 and set_metadata is None:
        return None

    catalog_total = (set_metadata.total or set_metadata.printed_total) if set_metadata else 0
    total_cards = catalog_total or cached_cards
    missing_cards = max(total_cards - owned_card_count, 0)
    completion_percent = round((owned_card_count / total_cards) * 100) if total_cards else 0
    return SetProgress(
        set_id=set_id,
        set_name=(set_metadata.name if set_metadata else "")
        or (representative.set_name if representative else "")
        or set_id,
        set_series=(set_metadata.series if set_metadata else "")
        or (representative.set_series if representative else ""),
        total_cards=total_cards,
        owned_cards=owned_card_count,
        owned_quantity=owned_quantity,
        missing_cards=missing_cards,
        completion_percent=completion_percent,
        cached_cards=cached_cards,
        checklist_complete=bool(set_metadata and catalog_total and cached_cards >= catalog_total),
        release_date=set_metadata.release_date
        if set_metadata
        else (representative.release_date if representative else None),
        logo_url=set_metadata.logo_url if set_metadata else "",
    )


def set_card_progress(set_id: str) -> tuple[SetProgress | None, list[SetCardProgress]]:
    set_metadata = SetMetadata.objects.filter(external_id=set_id).first()
    owned_quantities = _owned_quantities(set_id)
    cards = sorted(
        CardMetadata.objects.filter(set_id=set_id),
        key=lambda card: (_card_number_sort_key(card.card_number), card.name),
    )
    progress = _build_set_progress(
        set_id,
        len(cards),
        set_metadata,
        cards[0] if cards else None,
        owned_card_count=sum(1 for card in cards if owned_quantities.get(card.id, 0) > 0),
        owned_quantity=sum(owned_quantities.values()),
    )
    if progress is None:
        return None, []

    return progress, [
        SetCardProgress(card=card, owned_quantity=owned_quantities.get(card.id, 0))
        for card in cards
    ]


def refresh_set_metadata(set_id: str) -> int:
    cards = PokemonTCGClient().fetch_set_cards(set_id)
    for card_data in cards:
        upsert_card_metadata(card_data)
    return len(cards)


def refresh_set_catalog() -> int:
    sets = PokemonTCGClient().fetch_sets()
    for set_data in sets:
        upsert_set_metadata(set_data)
    return len(sets)


def ensure_set_checklist(set_id: str) -> int:
    progress = set_progress(set_id)
    if progress is None:
        return 0
    if progress.checklist_complete:
        return progress.cached_cards
    return refresh_set_metadata(set_id)


def _owned_quantities(set_id: str) -> dict[int, int]:
    return _owned_quantities_by_set([set_id]).get(set_id, {})


def _cached_card_counts_by_set(set_ids: Iterable[str]) -> dict[str, int]:
    rows = (
        CardMetadata.objects.filter(set_id__in=set_ids)
        .values("set_id")
        .annotate(cached_cards=Count("id"))
    )
    return {row["set_id"]: row["cached_cards"] for row in rows}


def _representative_cards_by_set(set_ids: Iterable[str]) -> dict[str, CardMetadata]:
    representative_ids = (
        CardMetadata.objects.filter(set_id__in=set_ids)
        .values("set_id")
        .annotate(card_id=Min("id"))
        .values_list("card_id", flat=True)
    )
    cards = CardMetadata.objects.filter(id__in=representative_ids).only(
        "set_id",
        "set_name",
        "set_series",
        "release_date",
    )
    return {card.set_id: card for card in cards}


def _owned_totals_by_set(set_ids: Iterable[str]) -> dict[str, tuple[int, int]]:
    rows = (
        OwnedCard.objects.filter(card__set_id__in=set_ids)
        .values("card__set_id")
        .annotate(owned_cards=Count("card_id", distinct=True), owned_quantity=Sum("quantity"))
    )
    return {
        row["card__set_id"]: (row["owned_cards"] or 0, row["owned_quantity"] or 0)
        for row in rows
    }


def _owned_quantities_by_set(set_ids: Iterable[str]) -> dict[str, dict[int, int]]:
    rows = (
        OwnedCard.objects.filter(card__set_id__in=set_ids)
        .values("card__set_id", "card_id")
        .annotate(quantity=Sum("quantity"))
    )
    quantities: dict[str, dict[int, int]] = defaultdict(dict)
    for row in rows:
        quantities[row["card__set_id"]][row["card_id"]] = row["quantity"] or 0
    return quantities


def _card_number_sort_key(value: str) -> tuple[int, int | str]:
    if value.isdecimal():
        return (0, int(value))
    return (1, value)
