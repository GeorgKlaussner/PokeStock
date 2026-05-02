from __future__ import annotations

from celery import shared_task
from collection.models import CardMetadata, OCRJob, OwnedCard
from collection.services.ocr import OCRClient, guess_from_ocr_text
from collection.services.pokemon_tcg import PokemonTCGAPIError, PokemonTCGClient, mark_sync_error, upsert_card_metadata


@shared_task
def refresh_card_metadata(card_id: int) -> str:
    card = CardMetadata.objects.get(id=card_id)
    client = PokemonTCGClient()
    try:
        data = client.get_card(card.external_id)
    except PokemonTCGAPIError as error:
        mark_sync_error(card, str(error))
        return "failed"
    upsert_card_metadata(data)
    return "ok"


@shared_task
def refresh_owned_card_prices() -> int:
    card_ids = (
        OwnedCard.objects.order_by()
        .values_list("card_id", flat=True)
        .distinct()
    )
    refreshed = 0
    for card_id in card_ids.iterator():
        refresh_card_metadata(card_id)
        refreshed += 1
    return refreshed


@shared_task
def process_ocr_job(job_id: int) -> str:
    job = OCRJob.objects.get(id=job_id)
    job.status = OCRJob.Status.PROCESSING
    job.error = ""
    job.save(update_fields=["status", "error", "updated_at"])

    try:
        raw_text = OCRClient().extract_text(job.image.path)
        guess = guess_from_ocr_text(raw_text)
        candidates = _search_ocr_candidates(guess.query, guess.card_number)
    except Exception as error:
        job.status = OCRJob.Status.FAILED
        job.error = str(error)
        job.save(update_fields=["status", "error", "updated_at"])
        return "failed"

    candidate_ids = []
    for card_data in candidates:
        card = upsert_card_metadata(card_data)
        candidate_ids.append(card.external_id)

    job.status = OCRJob.Status.COMPLETE
    job.raw_text = raw_text
    job.candidate_ids = candidate_ids
    job.save(update_fields=["status", "raw_text", "candidate_ids", "updated_at"])
    return "ok"


def _search_ocr_candidates(query: str, card_number: str) -> list[dict]:
    if not query and not card_number:
        return []
    client = PokemonTCGClient()
    candidates = client.search_cards(query=query, card_number=card_number, page_size=8)
    if not candidates and query and card_number:
        candidates = client.search_cards(card_number=card_number, page_size=8)
    return candidates
