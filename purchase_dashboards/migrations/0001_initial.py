from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="PurchaseDashSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fetched_at", models.DateTimeField(auto_now_add=True)),
                ("sheet_id", models.CharField(max_length=100)),
                ("gid", models.CharField(max_length=32)),
                ("row_count", models.PositiveIntegerField(default=0)),
                ("is_current", models.BooleanField(default=True)),
                ("fetch_error", models.TextField(blank=True)),
            ],
            options={"ordering": ["-fetched_at"]},
        ),
        migrations.CreateModel(
            name="PurchaseDashRow",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sr_no", models.PositiveIntegerField(blank=True, null=True)),
                ("data", models.JSONField()),
                ("snapshot", models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    related_name="rows",
                    to="purchase_dashboards.purchasedashsnapshot",
                )),
            ],
            options={"ordering": ["sr_no"]},
        ),
        migrations.AddIndex(
            model_name="purchasedashrow",
            index=models.Index(fields=["snapshot", "sr_no"], name="purchase_da_snapsho_9c2010_idx"),
        ),
        migrations.CreateModel(
            name="PurchaseDashResult",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("dashboard_key", models.CharField(max_length=20)),
                ("tiles", models.JSONField()),
                ("detail_rows", models.JSONField(default=list)),
                ("computed_at", models.DateTimeField(auto_now_add=True)),
                ("snapshot", models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    related_name="results",
                    to="purchase_dashboards.purchasedashsnapshot",
                )),
            ],
            options={"ordering": ["dashboard_key"]},
        ),
        migrations.AddConstraint(
            model_name="purchasedashresult",
            constraint=models.UniqueConstraint(
                fields=("snapshot", "dashboard_key"), name="uniq_snap_dash",
            ),
        ),
    ]
