from django.db import migrations, models


def copy_refresh_runs(apps, schema_editor):
    """Seeds the log with the refreshes that already happened."""
    RefreshRun = apps.get_model("nongrn", "RefreshRun")
    ActivityLog = apps.get_model("nongrn", "ActivityLog")
    rows = []
    for r in RefreshRun.objects.exclude(status="running"):
        who, _, why = (r.triggered_by or "").partition(" (")
        rows.append(ActivityLog(
            at=r.started_at, kind="refresh", status=r.status, user=who,
            title="Refresh All" + (f" – after {why.rstrip(')')}" if why else ""),
            detail=(r.message or "").split("\n\n")[0][:2000],
            duration=(r.finished_at - r.started_at).total_seconds() if r.finished_at else None))
    ActivityLog.objects.bulk_create(rows)


class Migration(migrations.Migration):

    dependencies = [("nongrn", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="ActivityLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("at", models.DateTimeField(db_index=True)),
                ("kind", models.CharField(choices=[("upload", "Upload"), ("refresh", "Refresh All")], max_length=10)),
                ("status", models.CharField(choices=[("ok", "Success"), ("failed", "Failed")], max_length=10)),
                ("user", models.CharField(blank=True, max_length=150)),
                ("title", models.CharField(max_length=255)),
                ("detail", models.TextField(blank=True)),
                ("source", models.CharField(blank=True, max_length=100)),
                ("file_size", models.BigIntegerField(blank=True, null=True)),
                ("link", models.URLField(blank=True, max_length=500)),
                ("duration", models.FloatField(blank=True, null=True)),
            ],
            options={"ordering": ["-at", "-id"]},
        ),
        migrations.RunPython(copy_refresh_runs, migrations.RunPython.noop),
    ]
