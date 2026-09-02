"""Add MtoMtsEmailLog — audit trail for every email dispatched by the module
(Stage E in the automation brief, plus change-fan-out emails)."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("mto_mts", "0003_current_month_status"),
    ]

    operations = [
        migrations.CreateModel(
            name="MtoMtsEmailLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(
                    choices=[("publication", "Publication"), ("change", "Change")],
                    max_length=20,
                )),
                ("subject", models.CharField(max_length=255)),
                ("recipients", models.TextField(
                    help_text="Comma-separated list of To: addresses this email went to.",
                )),
                ("body_preview", models.TextField(
                    blank=True,
                    help_text="First few lines of the body, for the audit UI.",
                )),
                ("sent_at", models.DateTimeField(auto_now_add=True)),
                ("delivered", models.BooleanField(
                    default=True,
                    help_text="False if the SMTP send raised — the log still records the attempt.",
                )),
                ("upload", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=models.deletion.SET_NULL,
                    related_name="emails",
                    to="mto_mts.mtomtsupload",
                )),
                ("change", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=models.deletion.SET_NULL,
                    related_name="emails",
                    to="mto_mts.mtomtschange",
                )),
            ],
            options={"ordering": ["-sent_at"]},
        ),
    ]
