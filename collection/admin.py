from django.contrib import admin

from collection.models import CardMetadata, OCRJob, OwnedCard, SetMetadata


@admin.register(CardMetadata)
class CardMetadataAdmin(admin.ModelAdmin):
    list_display = ("name", "set_name", "card_number", "rarity", "price_value", "price_source_field", "api_synced_at")
    list_filter = ("set_name", "rarity", "price_source_field")
    search_fields = ("external_id", "name", "set_name", "card_number")
    readonly_fields = ("created_at", "updated_at")


@admin.register(SetMetadata)
class SetMetadataAdmin(admin.ModelAdmin):
    list_display = ("name", "series", "printed_total", "total", "release_date", "api_synced_at")
    list_filter = ("series",)
    search_fields = ("external_id", "name", "series")
    readonly_fields = ("created_at", "updated_at")


@admin.register(OwnedCard)
class OwnedCardAdmin(admin.ModelAdmin):
    list_display = ("card", "variant", "language", "condition", "quantity", "row_value", "updated_at")
    list_filter = ("variant", "condition", "language")
    search_fields = ("card__name", "card__set_name", "card__card_number")
    autocomplete_fields = ("card",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(OCRJob)
class OCRJobAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "created_at", "updated_at")
    list_filter = ("status",)
    readonly_fields = ("created_at", "updated_at", "raw_text", "candidate_ids", "error")
