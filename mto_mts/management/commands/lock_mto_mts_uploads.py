"""Sweep ACTIVE uploads whose lock_at has passed and flip them to LOCKED.

Called from a systemd timer once a day at 00:05 UTC. Also safe to run by
hand for testing:

    python manage.py lock_mto_mts_uploads
    python manage.py lock_mto_mts_uploads --dry-run
    python manage.py lock_mto_mts_uploads --force <upload_id>

Once locked, the upload_edit endpoint rejects further PATCHes and the UI
shows the "Final file post changes is as below" banner (Change 14).
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from mto_mts.models import MtoMtsUpload


class Command(BaseCommand):
    help = "Auto-lock any ACTIVE MTO/MTS upload whose lock_at is in the past."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what WOULD be locked, but don't actually change anything.",
        )
        parser.add_argument(
            "--force",
            type=int,
            metavar="UPLOAD_ID",
            help="Lock this upload immediately, regardless of lock_at.",
        )

    def handle(self, dry_run, force, **options):
        now = timezone.now()

        if force is not None:
            try:
                upload = MtoMtsUpload.objects.get(pk=force)
            except MtoMtsUpload.DoesNotExist:
                self.stderr.write(f"[skip] upload #{force} does not exist")
                return
            if upload.status != MtoMtsUpload.Status.ACTIVE:
                self.stderr.write(
                    f"[skip] upload #{force} status is {upload.status}, not ACTIVE"
                )
                return
            if dry_run:
                self.stdout.write(f"[dry-run] would lock upload #{upload.id}")
                return
            upload.status = MtoMtsUpload.Status.LOCKED
            upload.locked_at = now
            upload.save(update_fields=["status", "locked_at"])
            self.stdout.write(f"[ok] locked upload #{upload.id}")
            return

        expired = MtoMtsUpload.objects.filter(
            status=MtoMtsUpload.Status.ACTIVE,
            lock_at__lte=now,
        )
        count = expired.count()
        if count == 0:
            self.stdout.write(f"[ok] no ACTIVE uploads are past their lock_at (now={now.isoformat()})")
            return

        for upload in expired:
            if dry_run:
                self.stdout.write(
                    f"[dry-run] would lock upload #{upload.id} "
                    f"(lock_at={upload.lock_at.isoformat()})"
                )
                continue
            upload.status = MtoMtsUpload.Status.LOCKED
            upload.locked_at = now
            upload.save(update_fields=["status", "locked_at"])
            self.stdout.write(
                f"[ok] locked upload #{upload.id} "
                f"(was due {upload.lock_at.isoformat()})"
            )

        if dry_run:
            self.stdout.write(f"[dry-run] {count} upload(s) would be locked.")
        else:
            self.stdout.write(f"[ok] locked {count} upload(s).")
