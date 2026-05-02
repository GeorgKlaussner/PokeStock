from __future__ import annotations

import json
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Prefetch, Q
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from collection.forms import (
    CSVImportForm,
    CardSearchForm,
    CollectionFilterForm,
    OwnedCardForm,
    PhotoUploadForm,
)
from collection.models import CardCondition, CardMetadata, CardVariant, OCRJob, OwnedCard, SetMetadata
from collection.services.aggregates import summarize_collection
from collection.services.csv_io import export_owned_cards_response, import_owned_cards_csv_bytes
from collection.services.ocr import OCRClient, OCRGuess, OCRServiceError, guess_from_ocr_text
from collection.services.pokemon_tcg import PokemonTCGAPIError, PokemonTCGClient, upsert_card_metadata
from collection.services.set_progress import (
    cached_set_progresses,
    ensure_set_checklist,
    refresh_set_catalog,
    refresh_set_metadata,
    set_card_progress,
)
from collection.tasks import process_ocr_job, refresh_card_metadata, refresh_owned_card_prices


SET_CHECKLIST_PAGE_SIZE = 48
COLLECTION_PAGE_SIZE = 50


@login_required
def dashboard(request):
    summary = summarize_collection()
    recent_owned = OwnedCard.objects.select_related("card").order_by("-created_at")[:6]
    return render(
        request,
        "collection/dashboard.html",
        {"summary": summary, "recent_owned": recent_owned},
    )


@login_required
def collection_list(request):
    form = CollectionFilterForm(request.GET or None)
    owned_cards = OwnedCard.objects.select_related("card")
    if form.is_valid():
        owned_cards = _filter_owned_cards(owned_cards, form.cleaned_data)
    page_obj = _paginate_collection(request, owned_cards)
    return render(
        request,
        "collection/collection_list.html",
        {
            "form": form,
            "owned_cards": page_obj,
            "page_obj": page_obj,
            "pagination_query": _pagination_query(request),
        },
    )


@login_required
def card_detail(request, external_id: str):
    card = get_object_or_404(
        CardMetadata.objects.prefetch_related(
            Prefetch("owned_cards", queryset=OwnedCard.objects.select_related("card"))
        ),
        external_id=external_id,
    )
    return render(request, "collection/card_detail.html", {"card": card})


@login_required
def add_search(request):
    form = CardSearchForm(request.GET or None)
    candidates: list[CardMetadata] = []
    set_query = request.GET.get("set_q", "").strip()
    sets = SetMetadata.objects.all()
    if set_query:
        sets = sets.filter(
            Q(name__icontains=set_query)
            | Q(series__icontains=set_query)
            | Q(external_id__icontains=set_query)
        )
    searched = any(request.GET.get(field) for field in ("q", "set_name", "card_number", "rarity"))
    if searched and form.is_valid():
        try:
            card_data = PokemonTCGClient().search_cards(
                query=form.cleaned_data["q"],
                set_name=form.cleaned_data["set_name"],
                card_number=form.cleaned_data["card_number"],
                rarity=form.cleaned_data["rarity"],
                page_size=24,
            )
            candidates = [upsert_card_metadata(item) for item in card_data]
        except PokemonTCGAPIError as error:
            messages.error(request, str(error))
    return render(
        request,
        "collection/add_search.html",
        {
            "form": form,
            "candidates": candidates,
            "searched": searched,
            "sets": sets,
            "set_query": set_query,
            "set_count": SetMetadata.objects.count(),
        },
    )


@login_required
def add_set_cards(request, set_id: str):
    set_metadata = get_object_or_404(SetMetadata, external_id=set_id)
    try:
        ensure_set_checklist(set_id)
    except PokemonTCGAPIError as error:
        messages.error(request, str(error))
    progress, cards = set_card_progress(set_id)
    page_obj = _paginate_set_cards(request, cards)
    return render(
        request,
        "collection/add_set_cards.html",
        {"set_metadata": set_metadata, "progress": progress, "page_obj": page_obj},
    )


@login_required
def camera_add(request):
    return render(request, "collection/camera_add.html")


@login_required
@require_POST
def camera_candidates(request):
    try:
        text = _camera_text_from_request(request)
    except ValueError as error:
        return JsonResponse({"error": str(error)}, status=400)
    except OCRServiceError as error:
        return JsonResponse({"error": str(error)}, status=502)

    if not text:
        return JsonResponse({"error": "No OCR text was provided."}, status=400)

    guess = guess_from_ocr_text(text)
    if not guess.query and not guess.card_number:
        return JsonResponse({"text": text, "candidates": [], "manual_search_url": reverse("add_search")})

    try:
        card_data = _search_ocr_candidates(guess)
    except PokemonTCGAPIError as error:
        return JsonResponse({"error": str(error)}, status=502)

    candidates = [upsert_card_metadata(item) for item in card_data]
    query_params = {"q": guess.query}
    if guess.card_number:
        query_params["card_number"] = guess.card_number
    return JsonResponse(
        {
            "text": text,
            "query": guess.query,
            "card_number": guess.card_number,
            "manual_search_url": f"{reverse('add_search')}?{urlencode(query_params)}",
            "candidates": [_candidate_payload(card) for card in candidates],
        }
    )


@login_required
def add_owned_card(request, external_id: str):
    card = CardMetadata.objects.filter(external_id=external_id).first()
    if card is None:
        try:
            card = upsert_card_metadata(PokemonTCGClient().get_card(external_id))
        except PokemonTCGAPIError as error:
            messages.error(request, str(error))
            return redirect("add_search")

    if request.method == "POST":
        form = OwnedCardForm(request.POST)
        if form.is_valid():
            owned_card = form.save(commit=False)
            owned_card.card = card
            owned_card.save()
            messages.success(request, "Card added to your collection.")
            return redirect("card_detail", external_id=card.external_id)
    else:
        form = OwnedCardForm()

    return render(
        request,
        "collection/add_owned.html",
        {
            "card": card,
            "form": form,
            "page_title": f"Add {card.name}",
            "submit_label": "Add to collection",
            "back_url": reverse("add_search"),
        },
    )


@login_required
def edit_owned_card(request, owned_id: int):
    owned_card = get_object_or_404(OwnedCard.objects.select_related("card"), id=owned_id)
    next_url = _safe_url(request.POST.get("next", "") or request.GET.get("next", ""))

    if request.method == "POST":
        form = OwnedCardForm(request.POST, instance=owned_card)
        if form.is_valid():
            form.save()
            messages.success(request, "Card details updated.")
            return redirect(next_url or reverse("card_detail", args=[owned_card.card.external_id]))
    else:
        form = OwnedCardForm(instance=owned_card)

    return render(
        request,
        "collection/add_owned.html",
        {
            "card": owned_card.card,
            "form": form,
            "next_url": next_url,
            "page_title": f"Edit {owned_card.card.name}",
            "submit_label": "Save changes",
            "back_url": next_url or reverse("card_detail", args=[owned_card.card.external_id]),
        },
    )


@login_required
@require_POST
def delete_owned_card(request, owned_id: int):
    owned_card = get_object_or_404(OwnedCard.objects.select_related("card"), id=owned_id)
    card = owned_card.card
    next_url = _safe_url(request.POST.get("next", ""))
    owned_card.delete()
    messages.success(request, f"Removed {card.name} from your collection.")
    return redirect(next_url or reverse("card_detail", args=[card.external_id]))


@login_required
@require_POST
def quick_add_card(request, external_id: str):
    card = CardMetadata.objects.filter(external_id=external_id).first()
    if card is None:
        try:
            card = upsert_card_metadata(PokemonTCGClient().get_card(external_id))
        except PokemonTCGAPIError as error:
            messages.error(request, str(error))
            return redirect("camera_add")

    owned_card = OwnedCard.objects.filter(
        card=card,
        variant=CardVariant.NORMAL,
        variant_custom="",
        language="en",
        condition=CardCondition.NEAR_MINT,
        purchase_price__isnull=True,
        purchase_date__isnull=True,
        notes="",
    ).first()
    if owned_card is None:
        owned_card = OwnedCard(
            card=card,
            variant=CardVariant.NORMAL,
            language="en",
            condition=CardCondition.NEAR_MINT,
            quantity=1,
        )
        owned_card.full_clean()
        owned_card.save()
    else:
        owned_card.quantity += 1
        owned_card.full_clean()
        owned_card.save(update_fields=["quantity", "updated_at"])
    messages.success(request, f"Added {card.name} to your collection.")
    return redirect("card_detail", external_id=card.external_id)


@login_required
def refresh_card(request, external_id: str):
    card = get_object_or_404(CardMetadata, external_id=external_id)
    if request.method == "POST":
        refresh_card_metadata.delay(card.id)
        messages.info(request, "Price refresh queued.")
    return redirect("card_detail", external_id=card.external_id)


@login_required
def refresh_collection(request):
    if request.method == "POST":
        refresh_owned_card_prices.delay()
        messages.info(request, "Collection price refresh queued.")
    return redirect("dashboard")


@login_required
def export_csv(request):
    return export_owned_cards_response()


@login_required
def import_csv(request):
    result = None
    if request.method == "POST":
        form = CSVImportForm(request.POST, request.FILES)
        if form.is_valid():
            result = import_owned_cards_csv_bytes(request.FILES["csv_file"].read())
            if result.created_count:
                messages.success(request, f"Imported {result.created_count} owned card rows.")
            if result.has_issues:
                messages.warning(request, f"{len(result.issues)} rows need review.")
    else:
        form = CSVImportForm()
    return render(request, "collection/import_csv.html", {"form": form, "result": result})


@login_required
def sets_index(request):
    return render(
        request,
        "collection/sets_index.html",
        {"sets": cached_set_progresses(owned_only=True)},
    )


@login_required
def set_detail(request, set_id: str):
    try:
        ensure_set_checklist(set_id)
    except PokemonTCGAPIError as error:
        messages.error(request, str(error))
    progress, cards = set_card_progress(set_id)
    if progress is None:
        return HttpResponseBadRequest("Unknown set.")
    page_obj = _paginate_set_cards(request, cards)
    return render(
        request,
        "collection/set_detail.html",
        {"progress": progress, "page_obj": page_obj},
    )


@login_required
@require_POST
def refresh_set(request, set_id: str):
    if not (
        SetMetadata.objects.filter(external_id=set_id).exists()
        or CardMetadata.objects.filter(set_id=set_id).exists()
    ):
        return HttpResponseBadRequest("Unknown set.")
    try:
        count = refresh_set_metadata(set_id)
    except PokemonTCGAPIError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, f"Refreshed {count} cards for this set.")
    return redirect("set_detail", set_id=set_id)


@login_required
@require_POST
def refresh_set_catalog_view(request):
    try:
        count = refresh_set_catalog()
    except PokemonTCGAPIError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, f"Refreshed {count} PokemonTCG sets.")
    return redirect(_safe_next(request, "sets_index"))


@login_required
def ocr_upload(request):
    if request.method == "POST":
        form = PhotoUploadForm(request.POST, request.FILES)
        if form.is_valid():
            job = form.save()
            process_ocr_job.delay(job.id)
            messages.info(request, "OCR processing queued.")
            return redirect("ocr_detail", job_id=job.id)
    else:
        form = PhotoUploadForm()
    return render(request, "collection/ocr_upload.html", {"form": form})


@login_required
def ocr_detail(request, job_id: int):
    job = get_object_or_404(OCRJob, id=job_id)
    candidates = []
    if job.candidate_ids:
        by_id = CardMetadata.objects.in_bulk(job.candidate_ids, field_name="external_id")
        candidates = [by_id[external_id] for external_id in job.candidate_ids if external_id in by_id]
    return render(request, "collection/ocr_detail.html", {"job": job, "candidates": candidates})


def _filter_owned_cards(queryset, cleaned_data: dict):
    if cleaned_data.get("q"):
        queryset = queryset.filter(card__name__icontains=cleaned_data["q"])
    if cleaned_data.get("set_name"):
        queryset = queryset.filter(card__set_name__icontains=cleaned_data["set_name"])
    if cleaned_data.get("rarity"):
        queryset = queryset.filter(card__rarity__iexact=cleaned_data["rarity"])
    if cleaned_data.get("condition"):
        queryset = queryset.filter(condition=cleaned_data["condition"])
    if cleaned_data.get("language"):
        queryset = queryset.filter(language__iexact=cleaned_data["language"])
    if cleaned_data.get("variant"):
        queryset = queryset.filter(variant=cleaned_data["variant"])
    if cleaned_data.get("missing_price") == "missing":
        queryset = queryset.filter(card__price_value__isnull=True)
    if cleaned_data.get("missing_price") == "available":
        queryset = queryset.filter(card__price_value__isnull=False)
    if cleaned_data.get("min_quantity"):
        queryset = queryset.filter(quantity__gte=cleaned_data["min_quantity"])
    return queryset


def _camera_text_from_request(request) -> str:
    content_type = request.headers.get("Content-Type", "")
    if content_type.startswith("application/json"):
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("Invalid request body.") from error
        return str(payload.get("text", "")).strip()

    image = request.FILES.get("image")
    if image is None:
        raise ValueError("No image was provided.")
    return OCRClient().extract_text_bytes(image.read()).strip()


def _search_ocr_candidates(guess: OCRGuess) -> list[dict]:
    if not guess.query and not guess.card_number:
        return []

    client = PokemonTCGClient()
    candidates = client.search_cards(
        query=guess.query,
        card_number=guess.card_number,
        page_size=8,
    )
    if not candidates and guess.query and guess.card_number:
        candidates = client.search_cards(card_number=guess.card_number, page_size=8)
    return candidates


def _candidate_payload(card: CardMetadata) -> dict[str, str | None]:
    return {
        "external_id": card.external_id,
        "name": card.name,
        "set_name": card.set_name,
        "card_number": card.card_number,
        "rarity": card.rarity,
        "image_url": card.image_small_url,
        "price": str(card.price_value) if card.price_value is not None else None,
        "currency": card.price_currency,
        "quick_add_url": reverse("quick_add_card", args=[card.external_id]),
        "edit_url": reverse("add_owned_card", args=[card.external_id]),
        "detail_url": reverse("card_detail", args=[card.external_id]),
    }


def _safe_next(request, fallback_name: str) -> str:
    return _safe_url(request.POST.get("next", "")) or reverse(fallback_name)


def _safe_url(value: str) -> str:
    if value.startswith("/") and not value.startswith("//"):
        return value
    return ""


def _paginate_set_cards(request, cards):
    paginator = Paginator(cards, SET_CHECKLIST_PAGE_SIZE)
    return paginator.get_page(request.GET.get("page"))


def _paginate_collection(request, owned_cards):
    paginator = Paginator(owned_cards, COLLECTION_PAGE_SIZE)
    return paginator.get_page(request.GET.get("page"))


def _pagination_query(request) -> str:
    query = request.GET.copy()
    query.pop("page", None)
    return query.urlencode()
