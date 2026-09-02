"""Run the complete PPC L0→L8 cycle using test data files.

Usage:
    .venv/bin/python manage.py test_full_cycle

Uploads all test files, runs feasibility, creates a release,
runs BOM explosion, stock allocation, and logs test production entries.
"""

import os
import sys
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.test import RequestFactory

DATA_DIR = "/root/jclp_automation_portal/jcpl/test_data/ppc"


class Command(BaseCommand):
    help = "Run the complete PPC L0→L8 cycle with test data."

    def handle(self, *args, **options):
        User = get_user_model()
        user = User.objects.filter(is_superuser=True).first()
        if not user:
            user = User.objects.first()
        if not user:
            self.stderr.write("No users in the database. Create one first.")
            return

        self.stdout.write(f"\nUsing user: {user.username}")
        self.stdout.write("=" * 60)

        # ── STEP 1: L0 Master uploads ──
        self.stdout.write(self.style.HTTP_INFO("\n📦 STEP 1 — L0 Master Uploads"))
        master_files = [
            ("Product Group Mapping.xlsx", None),   # auto → item_master
            ("Monitoring.xlsx", "family_hierarchy"),  # needs manual key
            ("Process File.xlsx", None),              # auto → route_master
            ("In process-Rejection.xlsx", None),      # auto → operation_stage_map
            ("Production Targets.xlsx", None),        # auto → capacity_ppp
            ("Machine Loading data.xlsx", None),      # auto → machine_master
            ("EBQ Batch Monitoring.xlsx", "batch_ebq"),  # needs manual key
            ("Lead Time Data.xlsx", None),            # auto → lead_time
            ("BOM_Item_Template.xlsx", None),         # auto → bom_master
            ("Green Level RM CP Packing.xlsx", None), # auto → stock_policy
            ("ASP for FG.xlsx", None),                # auto → rate_asp
        ]
        for fname, forced_key in master_files:
            self._upload(fname, forced_key, user)

        # ── STEP 2: L1 ERP Stock uploads ──
        self.stdout.write(self.style.HTTP_INFO("\n📡 STEP 2 — L1 ERP Stock Uploads"))
        erp_files = [
            ("FG Stock Report.xlsx", "erp_fg_stock"),
            ("CP Stock Report.xlsx", "erp_cp_stock"),
            ("RM Stock Report.xlsx", "erp_rm_stock"),
            ("PM Stock Report.xlsx", "erp_pm_stock"),
            ("Sales Order Report.xlsx", "erp_sales_orders"),
        ]
        for fname, forced_key in erp_files:
            self._upload(fname, forced_key, user)

        # ── STEP 2b: TCS ION Sheet Sync ──
        self.stdout.write(self.style.HTTP_INFO("\n📊 STEP 2b — TCS ION Sheet Sync"))
        self._sync_erp_to_sheet()

        # ── STEP 3: L2 Demand Freeze ──
        self.stdout.write(self.style.HTTP_INFO("\n🔒 STEP 3 — L2 Demand Freeze"))
        self._upload_demand("Forecast Demand Sep 2026.xlsx", "2026-09", user)

        # ── STEP 4: L3 MPS ──
        self.stdout.write(self.style.HTTP_INFO("\n📋 STEP 4 — L3 MPS Schedule"))
        self._upload_mps("MpsSS.xlsm", user)

        # ── STEP 5: L4 R3SS Plan ──
        self.stdout.write(self.style.HTTP_INFO("\n📊 STEP 5 — L4 R3SS Plan"))
        self._upload_r3ss("R3 SS September.xlsx", user)

        # ── STEP 6: L5 Feasibility ──
        self.stdout.write(self.style.HTTP_INFO("\n🚦 STEP 6 — L5 Feasibility"))
        run_id = self._run_feasibility(user)

        # ── STEP 7: L6 Release ──
        self.stdout.write(self.style.HTTP_INFO("\n🔒 STEP 7 — L6 Release"))
        release_id = self._create_release(run_id, user)

        if release_id:
            # ── STEP 8: L7 BOM Explosion + Stock Allocation ──
            self.stdout.write(self.style.HTTP_INFO("\n🧱 STEP 8 — L7 Material (BOM + Stock)"))
            self._run_material(release_id, user)

            # ── STEP 9: L8 Production Entries ──
            self.stdout.write(self.style.HTTP_INFO("\n🏭 STEP 9 — L8 Production Entries"))
            self._log_production(release_id, user)

            # ── STEP 10: Sheet Sync ──
            self.stdout.write(self.style.HTTP_INFO("\n📋 STEP 10 — Sheet Sync"))
            self._sheet_sync(release_id)

        # ── Summary ──
        self.stdout.write("\n" + "=" * 60)
        self._print_summary()

    def _upload(self, fname, forced_key, user):
        """Upload a file through the parser pipeline."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        from ppc_data.api import _detect_table_key
        from ppc_data.models import PPCDataRow, PPCUploadBatch
        from ppc_data.parsers import PARSERS

        path = os.path.join(DATA_DIR, fname)
        if not os.path.exists(path):
            self.stdout.write(f"  ⏭ {fname} — file not found, skipping")
            return

        table_key = forced_key or _detect_table_key(fname)
        if not table_key:
            self.stdout.write(f"  ⚠ {fname} — could not auto-detect table_key")
            return

        if table_key not in PARSERS:
            self.stdout.write(f"  ⚠ {fname} → {table_key} — no parser registered")
            return

        parser = PARSERS[table_key]
        try:
            rows = parser.parse(path)
        except Exception as exc:
            self.stdout.write(f"  ❌ {fname} → {table_key} — parse error: {exc}")
            return

        # Store
        from django.db import transaction
        with transaction.atomic():
            PPCUploadBatch.objects.filter(
                table_key=table_key, is_current=True
            ).update(is_current=False)

            is_erp = table_key.startswith("erp_")
            batch = PPCUploadBatch.objects.create(
                uploader=user,
                source_file=path,
                original_filename=fname,
                file_type="erp" if is_erp else "master",
                level="L1" if is_erp else "L0",
                table_key=table_key,
                row_count=len(rows),
                is_current=True,
                notes="test_full_cycle",
            )
            PPCDataRow.objects.bulk_create([
                PPCDataRow(batch=batch, sr_no=i+1, table_key=table_key, data=r)
                for i, r in enumerate(rows)
            ], batch_size=500)

        self.stdout.write(f"  ✅ {fname} → {table_key} — {len(rows)} rows")

    def _upload_demand(self, fname, month, user):
        """Upload demand freeze — creates per-item PPCDemandFreeze rows."""
        from ppc_data.models import PPCDemandFreeze, PPCDataRow, PPCUploadBatch
        from ppc_data.parsers import PARSERS
        from django.db import transaction

        path = os.path.join(DATA_DIR, fname)
        parser = PARSERS.get("demand_freeze")
        if not parser:
            self.stdout.write("  ⚠ No demand_freeze parser")
            return

        try:
            rows = parser.parse(path)
        except Exception as exc:
            self.stdout.write(f"  ❌ Demand parse error: {exc}")
            return

        # Clear existing freezes for this month
        old = PPCDemandFreeze.objects.filter(month=month).count()
        if old:
            PPCDemandFreeze.objects.filter(month=month).delete()
            self.stdout.write(f"  ℹ Deleted {old} old freeze rows for {month}")

        with transaction.atomic():
            PPCUploadBatch.objects.filter(
                table_key="demand_freeze", is_current=True
            ).update(is_current=False)

            batch = PPCUploadBatch.objects.create(
                uploader=user,
                source_file=path,
                original_filename=fname,
                file_type="demand",
                level="L2",
                table_key="demand_freeze",
                row_count=len(rows),
                is_current=True,
                notes=f"month={month}",
            )
            PPCDataRow.objects.bulk_create([
                PPCDataRow(batch=batch, sr_no=i+1, table_key="demand_freeze", data=r)
                for i, r in enumerate(rows)
            ], batch_size=500)

            # Create per-item freeze records
            freeze_objs = []
            for r in rows:
                item_code = r.get("item_code", "")
                qty = r.get("initial_qty", 0)
                if item_code:
                    try:
                        qty = float(qty)
                    except (ValueError, TypeError):
                        qty = 0
                    freeze_objs.append(PPCDemandFreeze(
                        item_code=item_code,
                        month=month,
                        initial_qty=qty,
                        frozen_by=user,
                        batch=batch,
                    ))
            PPCDemandFreeze.objects.bulk_create(freeze_objs, batch_size=500)

        self.stdout.write(f"  ✅ Demand frozen for {month} — {len(freeze_objs)} items")

    def _upload_mps(self, fname, user):
        """Upload MPS schedule."""
        path = os.path.join(DATA_DIR, fname)
        self._upload(fname, "mps_schedule", user)

    def _upload_r3ss(self, fname, user):
        """Upload R3SS plan."""
        from ppc_data.parsers.r3ss_file import parse
        from ppc_data.models import PPCDataRow, PPCUploadBatch
        from django.db import transaction

        path = os.path.join(DATA_DIR, fname)
        try:
            rows = parse(path)
        except Exception as exc:
            self.stdout.write(f"  ❌ R3SS parse error: {exc}")
            return

        with transaction.atomic():
            PPCUploadBatch.objects.filter(
                table_key="r3ss_plan", is_current=True
            ).update(is_current=False)

            batch = PPCUploadBatch.objects.create(
                uploader=user,
                source_file=path,
                original_filename=fname,
                file_type="plan",
                level="L4",
                table_key="r3ss_plan",
                row_count=len(rows),
                is_current=True,
                notes="test_full_cycle",
            )
            PPCDataRow.objects.bulk_create([
                PPCDataRow(batch=batch, sr_no=i+1, table_key="r3ss_plan", data=r)
                for i, r in enumerate(rows)
            ], batch_size=500)

        self.stdout.write(f"  ✅ R3SS plan uploaded — {len(rows)} items")

    def _run_feasibility(self, user):
        """Run feasibility checks on the current R3SS plan."""
        from ppc_data.models import PPCCapacityFlag, PPCFeasibilityRun, PPCUploadBatch
        from ppc_data.compute_feasibility import run_feasibility
        from django.utils import timezone

        plan_batch = PPCUploadBatch.objects.filter(
            table_key="r3ss_plan", is_current=True
        ).order_by("-uploaded_at").first()

        if not plan_batch:
            self.stdout.write("  ❌ No R3SS plan batch found")
            return None

        try:
            run = run_feasibility(plan_batch.pk)
        except Exception as exc:
            self.stdout.write(f"  ❌ Feasibility error: {exc}")
            import traceback
            traceback.print_exc()
            return None

        run_id = run.pk
        # Count flags by type
        cap_count = PPCCapacityFlag.objects.filter(run=run, flag_type="capacity").count()
        mach_count = PPCCapacityFlag.objects.filter(run=run, flag_type="machine").count()
        ebq_count = PPCCapacityFlag.objects.filter(run=run, flag_type="ebq").count()
        self.stdout.write(
            f"  ✅ Feasibility run #{run_id}: "
            f"capacity={cap_count}, machine={mach_count}, ebq={ebq_count} flags"
        )

        # Auto-resolve all flags for test purposes
        flags = PPCCapacityFlag.objects.filter(run_id=run_id, resolved_at__isnull=True)
        for f in flags:
            f.reason_code = "accepted_risk"
            f.reason_text = "Auto-resolved for testing"
            f.resolved_by = user
            f.resolved_at = timezone.now()
            f.save()

        resolved_count = flags.count()
        if resolved_count > 0:
            self.stdout.write(f"  ✅ Auto-resolved {resolved_count} flags (accepted_risk)")

        # Approve
        run = PPCFeasibilityRun.objects.get(pk=run_id)
        unresolved = PPCCapacityFlag.objects.filter(run=run, resolved_at__isnull=True).count()
        if unresolved == 0:
            run.status = "approved"
            run.save()
            self.stdout.write(f"  ✅ Run #{run_id} approved")
        else:
            self.stdout.write(f"  ⚠ {unresolved} unresolved flags — cannot approve")

        return run_id

    def _create_release(self, run_id, user):
        """Create a release from the approved feasibility run."""
        if not run_id:
            self.stdout.write("  ⏭ No approved run — skipping release")
            return None

        from ppc_data.models import (
            PPCDataRow, PPCFeasibilityRun, PPCRelease, PPCUploadBatch,
        )
        from django.db import transaction

        run = PPCFeasibilityRun.objects.get(pk=run_id)
        if run.status != "approved":
            self.stdout.write(f"  ⚠ Run #{run_id} is {run.status}, not approved")
            return None

        plan_batch = run.plan_batch

        # Determine plan_month from first row
        first_row = plan_batch.rows.first()
        plan_month = "2026-09"
        if first_row and first_row.data.get("days"):
            dates = sorted(first_row.data["days"].keys())
            if dates:
                plan_month = dates[0][:7]

        # Next release number
        last_release = PPCRelease.objects.filter(
            plan_month=plan_month
        ).order_by("-release_number").first()
        release_number = (last_release.release_number + 1) if last_release else 1

        with transaction.atomic():
            # Snapshot the plan rows
            snapshot = PPCUploadBatch.objects.create(
                uploader=user,
                source_file="",
                original_filename=f"Release #{release_number} snapshot",
                file_type="release",
                level="L6",
                table_key="release_rows",
                row_count=plan_batch.row_count,
                is_current=False,
                notes=f"Snapshot of batch #{plan_batch.pk}",
            )
            plan_rows = list(plan_batch.rows.values_list("sr_no", "data"))
            PPCDataRow.objects.bulk_create([
                PPCDataRow(batch=snapshot, sr_no=sr, table_key="release_rows", data=d)
                for sr, d in plan_rows
            ], batch_size=500)

            release = PPCRelease.objects.create(
                plan_month=plan_month,
                release_number=release_number,
                feasibility_run=run,
                source_batch=plan_batch,
                snapshot_batch=snapshot,
                released_by=user,
                status="active",
            )

        self.stdout.write(
            f"  ✅ Release #{release_number} created for {plan_month} — "
            f"{len(plan_rows)} plan rows snapshotted (release_id={release.pk})"
        )
        return release.pk

    def _run_material(self, release_id, user):
        """Run BOM explosion and stock allocation."""
        from ppc_data.compute_material import run_bom_explosion, run_stock_allocation

        # BOM explosion
        try:
            bom_result = run_bom_explosion(release_id)
            self.stdout.write(
                f"  ✅ BOM explosion: {bom_result['unique_components']} components "
                f"from {bom_result['fg_items_with_bom']} FG items "
                f"({bom_result['fg_items_without_bom']} without BOM)"
            )
        except Exception as exc:
            self.stdout.write(f"  ❌ BOM explosion failed: {exc}")
            import traceback
            traceback.print_exc()
            return

        # Stock allocation
        try:
            alloc_result = run_stock_allocation(release_id)
            self.stdout.write(
                f"  ✅ Stock allocation: {alloc_result['components_with_shortage']} shortages "
                f"out of {alloc_result['total_components']} components"
            )
        except Exception as exc:
            self.stdout.write(f"  ❌ Stock allocation failed: {exc}")
            import traceback
            traceback.print_exc()

    def _log_production(self, release_id, user):
        """Log some test production entries."""
        from ppc_data.models import PPCProductionEntry, PPCRejectionEntry, PPCRelease
        import random

        release = PPCRelease.objects.get(pk=release_id)
        plan_rows = list(release.snapshot_batch.rows.values_list("data", flat=True)[:10])

        entries_created = 0
        for row in plan_rows:
            item = row.get("item_code", "")
            section = row.get("section", "PRESS")
            if not item:
                continue

            # Log 3 days of production
            for day_offset in range(3):
                d = date(2026, 9, 1) + timedelta(days=day_offset)
                total_plan = row.get("total_plan", 0)
                if isinstance(total_plan, (int, float)) and total_plan > 0:
                    daily_target = total_plan / 26
                    actual = int(daily_target * random.uniform(0.7, 1.1))
                else:
                    actual = random.randint(50, 200)

                PPCProductionEntry.objects.update_or_create(
                    date=d,
                    item_code=item,
                    section=section,
                    shift="A",
                    defaults={
                        "release": release,
                        "produced_qty": actual,
                        "entered_by": user,
                    },
                )
                entries_created += 1

        self.stdout.write(f"  ✅ {entries_created} production entries logged (10 items × 3 days)")

        # Log a few rejections
        rej_count = 0
        for row in plan_rows[:5]:
            item = row.get("item_code", "")
            if not item:
                continue
            PPCRejectionEntry.objects.create(
                date=date(2026, 9, 1),
                item_code=item,
                section=row.get("section", "PRESS"),
                stage="STG-04",
                reason_code=random.choice(["R01", "R02", "R03"]),
                rejected_qty=random.randint(5, 50),
                entered_by=user,
            )
            rej_count += 1

        self.stdout.write(f"  ✅ {rej_count} rejection entries logged")

    def _sheet_sync(self, release_id):
        """Push data to Google Sheets via n8n webhooks."""
        from ppc_data.models import PPCRelease
        from ppc_data.sheet_sync import sync_bom_to_sheet, sync_material_to_ppc_sheet

        release = PPCRelease.objects.get(pk=release_id)

        # PPC Planning Sheet (existing)
        try:
            r1 = sync_material_to_ppc_sheet(release)
            if r1.get("ok"):
                self.stdout.write(f"  ✅ PPC Planning Sheet sync — HTTP {r1.get('http_status')}")
            elif not r1.get("attempted"):
                self.stdout.write(f"  ⏭ PPC Planning Sheet — {r1.get('reason')}")
            else:
                self.stdout.write(f"  ⚠ PPC Planning Sheet — {r1}")
        except Exception as exc:
            self.stdout.write(f"  ❌ PPC Planning Sheet sync error: {exc}")

        # Pipeline Sheet (new)
        try:
            r2 = sync_bom_to_sheet(release)
            if r2.get("ok"):
                self.stdout.write(f"  ✅ Pipeline Sheet sync — HTTP {r2.get('http_status')}")
            elif not r2.get("attempted"):
                self.stdout.write(f"  ⏭ Pipeline Sheet — {r2.get('reason')}")
            else:
                self.stdout.write(f"  ⚠ Pipeline Sheet — {r2}")
        except Exception as exc:
            self.stdout.write(f"  ❌ Pipeline Sheet sync error: {exc}")

    def _sync_erp_to_sheet(self):
        """Sync all current ERP batches to the TCS ION Google Sheet."""
        from ppc_data.models import PPCUploadBatch
        from ppc_data.sheet_sync import sync_erp_to_sheet

        erp_batches = (
            PPCUploadBatch.objects
            .filter(table_key__startswith="erp_", is_current=True)
            .order_by("table_key")
        )
        synced = 0
        for batch in erp_batches:
            try:
                result = sync_erp_to_sheet(batch)
                if result.get("ok"):
                    self.stdout.write(
                        f"  ✅ {batch.table_key} ({batch.row_count} rows) "
                        f"→ HTTP {result.get('http_status')}"
                    )
                    synced += 1
                elif not result.get("attempted"):
                    self.stdout.write(
                        f"  ⏭ {batch.table_key} — {result.get('reason')}"
                    )
                else:
                    self.stdout.write(
                        f"  ⚠ {batch.table_key} — HTTP {result.get('http_status', '?')}"
                    )
            except Exception as exc:
                self.stdout.write(f"  ❌ {batch.table_key} — {exc}")

        self.stdout.write(f"  📊 {synced}/{erp_batches.count()} ERP reports synced to TCS ION sheet")

    def _print_summary(self):
        """Print final database state."""
        from ppc_data.models import (
            PPCCapacityFlag, PPCDataRow, PPCDemandFreeze, PPCFeasibilityRun,
            PPCProductionEntry, PPCRejectionEntry, PPCRelease, PPCUploadBatch,
        )

        self.stdout.write(self.style.SUCCESS("\n🏁 FINAL STATE"))
        self.stdout.write(f"  PPCUploadBatch:    {PPCUploadBatch.objects.count()} batches")
        self.stdout.write(f"  PPCDataRow:        {PPCDataRow.objects.count()} rows")
        self.stdout.write(f"  PPCDemandFreeze:   {PPCDemandFreeze.objects.count()} freezes")
        self.stdout.write(f"  PPCFeasibilityRun: {PPCFeasibilityRun.objects.count()} runs")
        self.stdout.write(f"  PPCCapacityFlag:   {PPCCapacityFlag.objects.count()} flags")
        self.stdout.write(f"  PPCRelease:        {PPCRelease.objects.count()} releases")
        self.stdout.write(f"  PPCProductionEntry:{PPCProductionEntry.objects.count()} entries")
        self.stdout.write(f"  PPCRejectionEntry: {PPCRejectionEntry.objects.count()} rejections")

        # Current batches
        current = PPCUploadBatch.objects.filter(is_current=True).order_by("table_key")
        self.stdout.write(f"\n  Current batches ({current.count()}):")
        for b in current:
            self.stdout.write(f"    {b.table_key:25s} {b.row_count:>6,} rows  ({b.file_type}/{b.level})")
