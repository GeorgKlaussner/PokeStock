from __future__ import annotations

from django import forms

from collection.models import CardCondition, CardVariant, OCRJob, OwnedCard


class CardSearchForm(forms.Form):
    q = forms.CharField(label="Card name", required=False, max_length=120)
    set_name = forms.CharField(label="Set", required=False, max_length=120)
    card_number = forms.CharField(label="Number", required=False, max_length=40)
    rarity = forms.CharField(label="Rarity", required=False, max_length=80)

    def clean(self) -> dict[str, str]:
        cleaned = super().clean()
        if not any(cleaned.get(field) for field in ("q", "set_name", "card_number", "rarity")):
            raise forms.ValidationError("Enter at least one search field.")
        return cleaned


class OwnedCardForm(forms.ModelForm):
    class Meta:
        model = OwnedCard
        fields = [
            "variant",
            "variant_custom",
            "language",
            "condition",
            "quantity",
            "purchase_price",
            "purchase_date",
            "notes",
        ]
        widgets = {
            "purchase_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }


class CollectionFilterForm(forms.Form):
    q = forms.CharField(label="Name", required=False, max_length=120)
    set_name = forms.CharField(label="Set", required=False, max_length=120)
    rarity = forms.CharField(label="Rarity", required=False, max_length=80)
    condition = forms.ChoiceField(label="Condition", required=False, choices=[("", "Any"), *CardCondition.choices])
    language = forms.CharField(label="Language", required=False, max_length=16)
    variant = forms.ChoiceField(label="Variant", required=False, choices=[("", "Any"), *CardVariant.choices])
    missing_price = forms.ChoiceField(
        label="Price",
        required=False,
        choices=[("", "Any"), ("missing", "Missing"), ("available", "Available")],
    )
    min_quantity = forms.IntegerField(label="Minimum quantity", required=False, min_value=1)


class CSVImportForm(forms.Form):
    csv_file = forms.FileField(label="CSV file")


class PhotoUploadForm(forms.ModelForm):
    class Meta:
        model = OCRJob
        fields = ["image"]
        widgets = {
            "image": forms.ClearableFileInput(attrs={"accept": "image/*", "capture": "environment"}),
        }
