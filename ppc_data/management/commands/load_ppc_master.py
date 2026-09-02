"""Management command: load a PPC master file from disk.

Usage:
    python manage.py load_ppc_master /path/to/file.xlsx --table-key item_master

Useful for initial bulk loads and testing without going through the
REST endpoint.
"""

import logging

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from ppc_data.models import PPCDataRow, PPCUploadBatch
from ppc_data.parsers import PARSERS

log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Load a PPC master Excel file into the database."

    def add_arguments(self, parser):
        parser.add_argument("file_path", help="Path to the .xlsx file")
        parser.add_argument(
            "--table-key", required=True,
            help=f"Table key. Available: {', '.join(sorted(PARSERS.keys()))}",
        )
        parser.add_argument(
            "--notes", default="", help="Optional notes for this upload batch",
        )

    def handle(self, *args, **options):
        file_path = options["file_path"]
        table_key = options["table_key"]
        notes = options["notes"]

        if table_key not in PARSERS:
            raise CommandError(
                f"Unknown table_key '{table_key}'. "
                f"Available: {', '.join(sorted(PARSERS.keys()))}"
            )

        parser_mod = PARSERS[table_key]
        self.stdout.write(f"Parsing {file_path} as {table_key}...")

        try:
            parsed_rows = parser_mod.parse(file_path)
        except Exception as exc:
            raise CommandError(f"Parse failed: {exc}")

        self.stdout.write(f"Parsed {len(parsed_rows)} rows. Storing...")

        with transaction.atomic():
            PPCUploadBatch.objects.filter(
                table_key=table_key, is_current=True,
            ).update(is_current=False)

            batch = PPCUploadBatch.objects.create(
                uploader=None,
                source_file=file_path,
                original_filename=file_path.rsplit("/", 1)[-1],
                file_type="master",
                level="L0",
                table_key=table_key,
                row_count=len(parsed_rows),
                is_current=True,
                notes=notes or f"CLI load: {file_path}",
            )

            row_objs = [
                PPCDataRow(
                    batch=batch, sr_no=idx + 1,
                    table_key=table_key, data=row,
                )
                for idx, row in enumerate(parsed_rows)
            ]
            PPCDataRow.objects.bulk_create(row_objs, batch_size=500)

        self.stdout.write(self.style.SUCCESS(
            f"Done — batch #{batch.pk}, {len(parsed_rows)} rows stored as "
            f"'{table_key}' (is_current=True)."
        ))
        if parsed_rows:
            self.stdout.write(f"Sample row: {parsed_rows[0]}")
