from __future__ import annotations

from django.db import migrations


CARDMARKET_URL_OVERRIDES = {
    "sv3pt5-1": "https://www.cardmarket.com/en/Pokemon/Products/Singles/151/Bulbasaur-V1-MEW001",
    "sv3pt5-4": "https://www.cardmarket.com/en/Pokemon/Products/Singles/151/Charmander-V1-MEW004",
}


def correct_known_cardmarket_mappings(apps, schema_editor):
    CardMetadata = apps.get_model("collection", "CardMetadata")

    for external_id, url in CARDMARKET_URL_OVERRIDES.items():
        for card in CardMetadata.objects.filter(external_id=external_id):
            payload = card.latest_price_payload or {}
            card.latest_price_payload = {**payload, "prices": {}}
            card.cardmarket_url = url
            card.price_value = None
            card.price_source_field = ""
            card.price_upstream_updated_at = None
            card.save(
                update_fields=[
                    "latest_price_payload",
                    "cardmarket_url",
                    "price_value",
                    "price_source_field",
                    "price_upstream_updated_at",
                    "updated_at",
                ]
            )


class Migration(migrations.Migration):

    dependencies = [
        ("collection", "0004_reprice_cardmetadata_average_sell"),
    ]

    operations = [
        migrations.RunPython(correct_known_cardmarket_mappings, migrations.RunPython.noop),
    ]
