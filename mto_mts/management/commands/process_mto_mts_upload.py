"""Parse an uploaded xlsx and populate MtoMtsItem / MtoMtsCell rows.

Runs as a subprocess spawned by the upload HTTP endpoint, keeping the
request cheap. Also runnable by hand for troubleshooting:

    python manage.py process_mto_mts_upload <upload_id> [--reprocess]

The command is idempotent: if the target upload is already ACTIVE (or has
items), it exits without doing anything unless ``--reprocess`` is passed,
which wipes the existing items/cells first.

Contract with the upload endpoint
---------------------------------
The endpoint creates an ``MtoMtsUpload`` row with ``status=PROCESSING`` and
a valid ``stored_path``. This command then:

  1. parses the file at ``stored_path`` via ``mto_mts.parser.parse_workbook``
  2. bulk-creates the items and cells
  3. supersedes any older ACTIVE upload
  4. sets its own status to ACTIVE and writes ``validation_notes``.

On any failure the row is left with ``status=FAILED`` and the exception
text in ``validation_notes`` — nothing is silently swallowed.
"""

import time
import traceback

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from mto_mts.models import MtoMtsCell, MtoMtsItem, MtoMtsUpload
from mto_mts.notifications import send_publication_email
from mto_mts.parser import MtoMtsParseError, parse_workbook
from mto_mts.schedule import compute_lock_at


class Command(BaseCommand):
    help = "Parse an uploaded MTO/MTS xlsx and populate items + cells."

    def add_arguments(self, parser):
        parser.add_argument("upload_id", type=int)
        parser.add_argument(
            "--reprocess",
            action="store_true",
            help="Wipe existing items/cells for this upload and parse again.",
        )

    def handle(self, upload_id, reprocess, **options):
        try:
            upload = MtoMtsUpload.objects.get(pk=upload_id)
        except MtoMtsUpload.DoesNotExist:
            raise CommandError(f"MtoMtsUpload id={upload_id} does not exist.")

        if upload.status == MtoMtsUpload.Status.ACTIVE and not reprocess:
            self.stdout.write(
                f"[skip] upload #{upload_id} already ACTIVE — pass --reprocess to redo."
            )
            return

        # Any run overwrites the previous parse for this upload — a retry of a
        # failed one should not accumulate half-populated rows.
        MtoMtsCell.objects.filter(item__upload=upload).delete()
        MtoMtsItem.objects.filter(upload=upload).delete()

        t0 = time.time()
        try:
            result = parse_workbook(upload.stored_path)
        except MtoMtsParseError as exc:
            upload.status = MtoMtsUpload.Status.FAILED
            upload.validation_notes = f"Parse error: {exc}"
            upload.save(update_fields=["status", "validation_notes"])
            self.stderr.write(f"[fail] {exc}")
            return
        except Exception as exc:  # pragma: no cover — belt & braces
            upload.status = MtoMtsUpload.Status.FAILED
            upload.validation_notes = (
                f"Unexpected error: {exc}\n\n{traceback.format_exc()}"
            )
            upload.save(update_fields=["status", "validation_notes"])
            self.stderr.write(f"[fail-unexpected] {exc}")
            return

        parse_seconds = time.time() - t0

        t0 = time.time()
        try:
            with transaction.atomic():
                items_bulk = [
                    MtoMtsItem(
                        upload=upload,
                        item_group=p.item_group,
                        item_code=p.item_code,
                        segment=p.segment,
                        account_description=p.account_description,
                    )
                    for p in result.items
                ]
                MtoMtsItem.objects.bulk_create(items_bulk, batch_size=1000)

                # Refetch with primary keys so we can wire cells to them.
                item_rows = list(
                    MtoMtsItem.objects.filter(upload=upload).order_by("id")
                )
                cells_bulk = []
                for parsed_item, item_row in zip(result.items, item_rows):
                    for pc in parsed_item.cells:
                        cells_bulk.append(
                            MtoMtsCell(
                                item=item_row,
                                month_label=pc.month_label,
                                month_index=pc.month_index,
                                value=pc.value,
                            )
                        )
                MtoMtsCell.objects.bulk_create(cells_bulk, batch_size=5000)

                # Promote to ACTIVE and demote any older ACTIVE one.
                MtoMtsUpload.objects.filter(
                    status=MtoMtsUpload.Status.ACTIVE
                ).exclude(pk=upload.pk).update(
                    status=MtoMtsUpload.Status.SUPERSEDED
                )
                upload.status = MtoMtsUpload.Status.ACTIVE
                upload.month_label = (
                    result.month_labels[-1] if result.month_labels else ""
                )
                upload.validation_notes = "\n".join(result.exceptions)
                upload.lock_at = compute_lock_at(upload.uploaded_at)
                upload.save(
                    update_fields=[
                        "status", "month_label", "validation_notes", "lock_at",
                    ]
                )
        except Exception as exc:
            upload.status = MtoMtsUpload.Status.FAILED
            upload.validation_notes = (
                f"DB insert error: {exc}\n\n{traceback.format_exc()}"
            )
            upload.save(update_fields=["status", "validation_notes"])
            self.stderr.write(f"[fail-db] {exc}")
            return

        insert_seconds = time.time() - t0
        self.stdout.write(
            f"[ok] upload #{upload_id}  "
            f"items={len(result.items)}  "
            f"cells={sum(len(i.cells) for i in result.items)}  "
            f"parse={parse_seconds:.2f}s  insert={insert_seconds:.2f}s  "
            f"warnings={len(result.exceptions)}"
        )

        # Stage E — announce the newly published working file to both
        # departments. Kept last so a failure here doesn't leave the upload
        # stuck in PROCESSING; the row is already ACTIVE at this point.
        try:
            send_publication_email(upload)
            self.stdout.write(f"[ok] publication email dispatched for upload #{upload_id}")
        except Exception as exc:  # pragma: no cover — audit only
            self.stderr.write(f"[warn] publication email failed: {exc}")
