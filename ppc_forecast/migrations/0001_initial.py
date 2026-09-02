from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PPCForecastUpload",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("original_filename", models.CharField(max_length=255)),
                ("stored_path", models.CharField(max_length=500)),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                ("notes", models.CharField(blank=True, max_length=500)),
                ("uploader", models.ForeignKey(
                    on_delete=models.deletion.PROTECT,
                    related_name="ppc_forecast_uploads",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"ordering": ["-uploaded_at"]},
        ),
    ]
