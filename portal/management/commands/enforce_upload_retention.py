"""Delete old uploaded files once a module has more than 2 uploads.

Applies independently, per module, to every upload-storing app:
    MTO/MTS, PPC, PPC Forecast, Purchase Planning, PPC Data Pipeline.

For each app: keep the 2 most recent uploads' files untouched; for every
upload older than that, delete the file on disk (never touched again by
any app — verified before building this) and stamp file_removed_at. The
database record itself is NEVER deleted — the audit trail (who uploaded
what, when, any notes) stays forever. Only the raw file goes.

MTO/MTS and PPC: the file is disposable once removed — the real data
already lives in MtoMtsItem / the Google Sheet. PPC Forecast and Purchase
Planning have no parsing yet, so the file IS the only copy of that
upload's data — applying the same 2-most-recent rule there is an explicit,
confirmed decision (not an oversight), since neither module has any
uploads yet as of when this was built.

PPC Data Pipeline: retention is per *table_key* (42 types), not global.
The parsed data lives in PPCDataRow — the raw file is disposable.

    python manage.py enforce_upload_retention
"""

import os

from django.core.management.base import BaseCommand
from django.utils import timezone

from portal.notify import notify

KEEP = 2


class Command(BaseCommand):
    help = "Delete upload files past the 2 most recent, per module. DB records are never deleted."

    def _sweep_simple(self, label, model, has_status):
        """Keep the 2 most recent uploads globally for a model."""
        qs = model.objects.order_by("-uploaded_at")
        stale = list(qs[KEEP:])
        deleted = 0
        freed = 0
        for upload in stale:
            if upload.file_removed_at is not None:
                continue
            if has_status and getattr(upload, "status", None) == "processing":
                continue
            path = getattr(upload, "stored_path", "") or getattr(upload, "source_file", "")
            try:
                if path and os.path.exists(path):
                    freed += os.path.getsize(path)
                    os.remove(path)
            except OSError as exc:
                self.stderr.write(f"[warn] could not remove {path}: {exc}")
                continue
            upload.file_removed_at = timezone.now()
            upload.save(update_fields=["file_removed_at"])
            deleted += 1
        return qs.count(), deleted, freed

    def _sweep_ppc_data(self):
        """Keep 2 most recent uploads *per table_key* for PPCUploadBatch.

        The ppc_data app stores 42 different table types in one model, so
        the 2-most-recent rule is applied independently per table_key.
        The parsed data lives in PPCDataRow — only the raw xlsx goes.
        """
        from ppc_data.models import PPCUploadBatch

        all_keys = (
            PPCUploadBatch.objects
            .values_list("table_key", flat=True)
            .distinct()
        )
        total_uploads = 0
        total_deleted = 0
        total_freed = 0

        for key in all_keys:
            qs = PPCUploadBatch.objects.filter(table_key=key).order_by("-uploaded_at")
            count = qs.count()
            total_uploads += count
            stale = list(qs[KEEP:])

            for batch in stale:
                if batch.file_removed_at is not None:
                    continue
                path = batch.source_file
                try:
                    if path and os.path.exists(path):
                        total_freed += os.path.getsize(path)
                        os.remove(path)
                except OSError as exc:
                    self.stderr.write(f"[warn] could not remove {path}: {exc}")
                    continue
                batch.file_removed_at = timezone.now()
                batch.save(update_fields=["file_removed_at"])
                total_deleted += 1

        return total_uploads, total_deleted, total_freed, len(list(all_keys))

    def handle(self, **options):
        from mto_mts.models import MtoMtsUpload
        from ppc.models import PPCUpload
        from ppc_forecast.models import PPCForecastUpload
        from purchase_planning.models import PurchasePlanningUpload

        modules = [
            ("MTO/MTS", MtoMtsUpload, True),   # has a 'status' field to guard on
            ("PPC", PPCUpload, False),
            ("PPC Forecast", PPCForecastUpload, False),
            ("Purchase Planning", PurchasePlanningUpload, False),
        ]

        report_lines = []
        total_deleted = 0
        total_bytes = 0

        for label, model, has_status in modules:
            count, deleted, freed = self._sweep_simple(label, model, has_status)
            total_deleted += deleted
            total_bytes += freed
            report_lines.append(
                f"{label}: {count} total upload(s), kept the {min(KEEP, count)} "
                f"most recent, removed {deleted} older file(s) "
                f"({freed / 1024:.0f} KB freed)."
            )
            self.stdout.write(f"[ok] {label}: removed {deleted} file(s)")

        # PPC Data Pipeline — retention per table_key
        ppc_count, ppc_deleted, ppc_freed, key_count = self._sweep_ppc_data()
        total_deleted += ppc_deleted
        total_bytes += ppc_freed
        report_lines.append(
            f"PPC Data Pipeline: {ppc_count} total batch(es) across "
            f"{key_count} table key(s), kept the {KEEP} most recent per key, "
            f"removed {ppc_deleted} older file(s) ({ppc_freed / 1024:.0f} KB freed)."
        )
        self.stdout.write(f"[ok] PPC Data Pipeline: removed {ppc_deleted} file(s) across {key_count} table keys")

        notify(
            f"Upload retention run — {total_deleted} file(s) removed",
            "Daily retention sweep (keep the 2 most recent uploads per module, delete older "
            "files only — database records are never deleted):\n\n" + "\n".join(report_lines)
            + f"\n\nTotal: {total_deleted} file(s), {total_bytes / 1024:.0f} KB freed.",
        )
