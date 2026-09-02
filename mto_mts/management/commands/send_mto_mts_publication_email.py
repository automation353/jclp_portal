"""Manually (re-)send the "working file is ready" email for a given upload.

Normally called automatically at the end of ``process_mto_mts_upload``. Use
this by hand when SMTP was down at the original upload time, or when a
department head needs a fresh reminder:

    python manage.py send_mto_mts_publication_email <upload_id> [--review-days 7]

Every send appends a row to ``MtoMtsEmailLog`` — nothing is overwritten.
"""

from django.core.management.base import BaseCommand, CommandError

from mto_mts.models import MtoMtsUpload
from mto_mts.notifications import send_publication_email


class Command(BaseCommand):
    help = "Send (or re-send) the Stage E publication email for an upload."

    def add_arguments(self, parser):
        parser.add_argument("upload_id", type=int)
        parser.add_argument(
            "--review-days",
            type=int,
            default=7,
            help="How many days from now to quote as the review-by date (default 7).",
        )

    def handle(self, upload_id, review_days, **options):
        try:
            upload = MtoMtsUpload.objects.get(pk=upload_id)
        except MtoMtsUpload.DoesNotExist:
            raise CommandError(f"MtoMtsUpload id={upload_id} does not exist.")

        if upload.status != MtoMtsUpload.Status.ACTIVE:
            self.stderr.write(
                f"[warn] upload #{upload_id} status is '{upload.status}' — "
                f"emailing anyway (log row will still be written)."
            )

        send_publication_email(upload, review_by_days=review_days)
        self.stdout.write(f"[ok] publication email dispatched for upload #{upload_id}")
