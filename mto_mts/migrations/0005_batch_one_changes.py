"""Batch 1 of the 11-Aug review changes.

- MtoMtsChange.comment       — reason captured at edit time (Change 8)
- MtoMtsItem.last_edited_by_dept — drives cell colour + (S)/(O) tag (11, 12)
- MtoMtsItem.segment         — for segment slicers when Excel adds the col (15)
- MtoMtsUpload.lock_at       — when to auto-lock this upload (14)
- MtoMtsUpload.locked_at     — when the lock actually happened
- MtoMtsUpload.status.LOCKED — new status value
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("mto_mts", "0004_email_log"),
    ]

    operations = [
        migrations.AddField(
            model_name="mtomtschange",
            name="comment",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="mtomtsitem",
            name="last_edited_by_dept",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="mtomtsitem",
            name="segment",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="mtomtsupload",
            name="lock_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="mtomtsupload",
            name="locked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="mtomtsupload",
            name="status",
            field=models.CharField(
                choices=[
                    ("processing", "Processing"),
                    ("active", "Active"),
                    ("locked", "Locked"),
                    ("failed", "Failed"),
                    ("superseded", "Superseded"),
                ],
                default="processing",
                max_length=16,
            ),
        ),
    ]
