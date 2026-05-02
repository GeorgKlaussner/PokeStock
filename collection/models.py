from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.utils import timezone


class CardVariant(models.TextChoices):
    NORMAL = "normal", "Normal"
    HOLOFOIL = "holofoil", "Holofoil"
    REVERSE_HOLOFOIL = "reverse_holofoil", "Reverse holofoil"
    FIRST_EDITION_NORMAL = "first_edition_normal", "First edition normal"
    FIRST_EDITION_HOLOFOIL = "first_edition_holofoil", "First edition holofoil"
    UNKNOWN = "unknown", "Unknown"
    CUSTOM = "custom", "Custom"


class CardCondition(models.TextChoices):
    MINT = "mint", "Mint"
    NEAR_MINT = "near_mint", "Near Mint"
    EXCELLENT = "excellent", "Excellent"
    GOOD = "good", "Good"
    LIGHT_PLAYED = "light_played", "Light Played"
    PLAYED = "played", "Played"
    POOR = "poor", "Poor"
    UNKNOWN = "unknown", "Unknown"


language_validator = RegexValidator(
    regex=r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})?$",
    message="Use a short language code such as en, de, or pt-BR.",
)


class CardMetadata(models.Model):
    external_id = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    set_id = models.CharField(max_length=64, blank=True)
    set_name = models.CharField(max_length=255, blank=True)
    set_series = models.CharField(max_length=255, blank=True)
    card_number = models.CharField(max_length=64, blank=True)
    rarity = models.CharField(max_length=128, blank=True)
    image_small_url = models.URLField(blank=True)
    image_large_url = models.URLField(blank=True)
    release_date = models.DateField(null=True, blank=True)
    cardmarket_url = models.URLField(blank=True)
    latest_price_payload = models.JSONField(default=dict, blank=True)
    api_updated_at = models.CharField(max_length=64, blank=True)
    api_synced_at = models.DateTimeField(null=True, blank=True)
    price_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    price_source_field = models.CharField(max_length=64, blank=True)
    price_currency = models.CharField(max_length=3, default="EUR")
    price_upstream_updated_at = models.DateField(null=True, blank=True)
    last_sync_error = models.TextField(blank=True)
    last_sync_attempt_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["set_name", "card_number", "name"]
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["set_name", "card_number"]),
            models.Index(fields=["set_id"]),
        ]

    def __str__(self) -> str:
        label = self.name
        if self.set_name or self.card_number:
            label += f" ({self.set_name} #{self.card_number})"
        return label

    @property
    def has_price(self) -> bool:
        return self.price_value is not None

    @property
    def is_price_stale(self) -> bool:
        if self.api_synced_at is None:
            return True
        cutoff = timezone.now() - timedelta(days=settings.PRICE_STALE_AFTER_DAYS)
        return self.api_synced_at < cutoff


class SetMetadata(models.Model):
    external_id = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    series = models.CharField(max_length=255, blank=True)
    printed_total = models.PositiveIntegerField(default=0)
    total = models.PositiveIntegerField(default=0)
    release_date = models.DateField(null=True, blank=True)
    symbol_url = models.URLField(blank=True)
    logo_url = models.URLField(blank=True)
    api_updated_at = models.CharField(max_length=64, blank=True)
    api_synced_at = models.DateTimeField(null=True, blank=True)
    checklist_refresh_queued_at = models.DateTimeField(null=True, blank=True)
    last_sync_error = models.TextField(blank=True)
    last_sync_attempt_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-release_date", "name"]
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["series"]),
            models.Index(fields=["release_date"]),
        ]

    def __str__(self) -> str:
        return self.name


class OwnedCard(models.Model):
    card = models.ForeignKey(CardMetadata, on_delete=models.CASCADE, related_name="owned_cards")
    variant = models.CharField(max_length=32, choices=CardVariant.choices, default=CardVariant.NORMAL)
    variant_custom = models.CharField(max_length=80, blank=True)
    language = models.CharField(max_length=16, default="en", validators=[language_validator])
    condition = models.CharField(max_length=32, choices=CardCondition.choices, default=CardCondition.NEAR_MINT)
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    purchase_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["card__set_name", "card__card_number", "card__name", "variant", "condition"]
        indexes = [
            models.Index(fields=["variant"]),
            models.Index(fields=["condition"]),
            models.Index(fields=["language"]),
        ]

    def __str__(self) -> str:
        return f"{self.quantity}x {self.card.name} ({self.get_variant_display()})"

    def clean(self) -> None:
        errors: dict[str, str] = {}
        if self.quantity < 1:
            errors["quantity"] = "Quantity must be at least 1."
        if self.purchase_price is not None and self.purchase_price < Decimal("0"):
            errors["purchase_price"] = "Purchase price cannot be negative."
        if self.variant == CardVariant.CUSTOM and not self.variant_custom.strip():
            errors["variant_custom"] = "Describe the custom variant."
        if errors:
            raise ValidationError(errors)

    @property
    def unit_value(self) -> Decimal | None:
        from collection.services.pricing import adjust_owned_price_value, select_cardmarket_price

        if self.card.latest_price_payload:
            return select_cardmarket_price(
                self.card.latest_price_payload,
                self.variant,
                language=self.language,
                condition=self.condition,
            ).value
        return adjust_owned_price_value(
            self.card.price_value,
            language=self.language,
            condition=self.condition,
        )

    @property
    def row_value(self) -> Decimal | None:
        if self.unit_value is None:
            return None
        return self.unit_value * self.quantity


class OCRJob(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        COMPLETE = "complete", "Complete"
        FAILED = "failed", "Failed"

    image = models.FileField(upload_to="ocr_uploads/%Y/%m/%d/")
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING)
    raw_text = models.TextField(blank=True)
    candidate_ids = models.JSONField(default=list, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"OCR job {self.pk} ({self.status})"
