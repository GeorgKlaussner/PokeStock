from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("collection", "0002_setmetadata"),
    ]

    operations = [
        migrations.AddField(
            model_name="setmetadata",
            name="checklist_refresh_queued_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
