from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import TextIO

from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponse

from collection.models import DEFAULT_OWNED_CARD_LANGUAGE, CardCondition, CardMetadata, CardVariant, OwnedCard
from collection.services.pokemon_tcg import PokemonTCGAPIError, PokemonTCGClient, upsert_card_metadata


EXPORT_FIELDS = [
    "card_id",
    "name",
    "set_name",
    "card_number",
    "variant",
    "variant_custom",
    "language",
    "condition",
    "quantity",
    "purchase_price",
    "purchase_date",
    "notes",
]


@dataclass
class ImportIssue:
    row_number: int
    message: str
    row: dict[str, str]


@dataclass
class ImportResult:
    created_count: int = 0
    issues: list[ImportIssue] = field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        return bool(self.issues)


def export_owned_cards_response() -> HttpResponse:
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="pokestock-collection.csv"'
    writer = csv.DictWriter(response, fieldnames=EXPORT_FIELDS)
    writer.writeheader()
    for owned in OwnedCard.objects.select_related("card").order_by("card__set_name", "card__card_number"):
        writer.writerow(
            {
                "card_id": owned.card.external_id,
                "name": owned.card.name,
                "set_name": owned.card.set_name,
                "card_number": owned.card.card_number,
                "variant": owned.variant,
                "variant_custom": owned.variant_custom,
                "language": owned.language,
                "condition": owned.condition,
                "quantity": owned.quantity,
                "purchase_price": owned.purchase_price or "",
                "purchase_date": owned.purchase_date.isoformat() if owned.purchase_date else "",
                "notes": owned.notes,
            }
        )
    return response


def import_owned_cards_csv(file_obj: TextIO | io.StringIO) -> ImportResult:
    reader = csv.DictReader(file_obj)
    result = ImportResult()
    if not reader.fieldnames:
        result.issues.append(ImportIssue(1, "CSV file has no header row.", {}))
        return result

    with transaction.atomic():
        for row_number, row in enumerate(reader, start=2):
            normalized = {key: (value or "").strip() for key, value in row.items()}
            card = _match_card(normalized)
            if card is None:
                result.issues.append(ImportIssue(row_number, "No matching card found.", normalized))
                continue
            if isinstance(card, list):
                result.issues.append(ImportIssue(row_number, "Ambiguous card match; add card_id to this row.", normalized))
                continue

            try:
                owned = _owned_from_row(card, normalized)
                owned.full_clean()
                owned.save()
            except (ValidationError, ValueError) as error:
                result.issues.append(ImportIssue(row_number, str(error), normalized))
                continue
            result.created_count += 1

    return result


def import_owned_cards_csv_bytes(content: bytes) -> ImportResult:
    text = content.decode("utf-8-sig")
    return import_owned_cards_csv(io.StringIO(text))


def _match_card(row: dict[str, str]) -> CardMetadata | list[CardMetadata] | None:
    card_id = row.get("card_id", "")
    if card_id:
        existing = CardMetadata.objects.filter(external_id=card_id).first()
        if existing is not None:
            return existing
        try:
            return upsert_card_metadata(PokemonTCGClient().get_card(card_id))
        except PokemonTCGAPIError:
            return None

    name = row.get("name", "")
    set_name = row.get("set_name", "")
    card_number = row.get("card_number", "")
    if not (name and set_name and card_number):
        return None

    matches = list(
        CardMetadata.objects.filter(
            name__iexact=name,
            set_name__iexact=set_name,
            card_number__iexact=card_number,
        )
    )
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        return matches
    return None


def _owned_from_row(card: CardMetadata, row: dict[str, str]) -> OwnedCard:
    variant = row.get("variant") or CardVariant.NORMAL
    condition = row.get("condition") or CardCondition.NEAR_MINT
    if variant not in CardVariant.values:
        raise ValueError(f"Unsupported variant: {variant}")
    if condition not in CardCondition.values:
        raise ValueError(f"Unsupported condition: {condition}")

    return OwnedCard(
        card=card,
        variant=variant,
        variant_custom=row.get("variant_custom", ""),
        language=row.get("language") or DEFAULT_OWNED_CARD_LANGUAGE,
        condition=condition,
        quantity=_parse_int(row.get("quantity") or "1"),
        purchase_price=_parse_decimal(row.get("purchase_price")),
        purchase_date=_parse_date(row.get("purchase_date")),
        notes=row.get("notes", ""),
    )


def _parse_int(value: str) -> int:
    try:
        return int(value)
    except ValueError as error:
        raise ValueError(f"Invalid quantity: {value}") from error


def _parse_decimal(value: str | None) -> Decimal | None:
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"Invalid purchase price: {value}") from error


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"Invalid purchase date: {value}") from error
