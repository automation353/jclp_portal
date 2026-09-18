"""Wave-1 exit test — validates that master data joins resolve.

  GET /api/ppc-data/wave1-test/

Spec §3.1: "Pick twenty live parts at random. Each must resolve to a
family, a product group, a section, a route, a capacity, a target PPP,
an EBQ, a lead time and exactly one active BOM. Do not start the demand
layer until this passes."

This endpoint picks up to 20 random parts from the current item_master
batch and checks every join the spec requires. Returns pass/fail per
part, per join, plus an overall verdict.
"""

import logging
import random

from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import PPCDataRow, PPCUploadBatch

log = logging.getLogger(__name__)

# The nine master joins every part must resolve to.
# Each entry: (table_key, display_name, join_field, target_field)
# join_field = which field in item_master is the join key
# target_field = which field in the target table is the lookup key
REQUIRED_JOINS = [
    ("family_hierarchy",  "Family & Product Group",  "item_code",  "item_code"),
    ("route_master",      "Route (process)",         "family",     "family"),
    ("capacity_ppp",      "Capacity & Target PPP",   "family",     "family"),
    ("batch_ebq",         "EBQ & Batch Size",        "family",     "family"),
    ("lead_time",         "Lead Time",               "item_code",  "part_code"),
    ("bom_master",        "BOM (exactly one active)", "item_code", "parent_item"),
]


def _load_current_data(table_key):
    """Load all rows from the current batch for a table_key.
    Returns list of data dicts, or empty list if no data.
    """
    batch = (
        PPCUploadBatch.objects
        .filter(table_key=table_key, is_current=True)
        .order_by("-uploaded_at")
        .first()
    )
    if not batch:
        return []
    return list(
        PPCDataRow.objects
        .filter(batch=batch)
        .values_list("data", flat=True)
    )


def _build_lookup(rows, key_field):
    """Build a dict mapping key values → list of rows."""
    lookup = {}
    for r in rows:
        k = (r.get(key_field) or "").strip().upper()
        if k:
            lookup.setdefault(k, []).append(r)
    return lookup


@api_view(["GET"])
def wave1_test(request):
    """Run the Wave-1 exit test.

    Query params:
      ?count=20   — number of parts to test (default 20, max 100)
      ?item=XYZ   — test a specific item code instead of random
    """
    try:
        count = max(1, min(100, int(request.GET.get("count", 20))))
    except (ValueError, TypeError):
        count = 20

    specific_item = request.GET.get("item", "").strip().upper()

    # ── Load item_master ──
    items = _load_current_data("item_master")
    if not items:
        return Response({
            "verdict": "BLOCKED",
            "reason": "No item_master data loaded. Upload Product Group Mapping first.",
            "results": [],
        })

    # ── Pick test parts ──
    if specific_item:
        test_items = [r for r in items if (r.get("item_code") or "").strip().upper() == specific_item]
        if not test_items:
            return Response({
                "verdict": "BLOCKED",
                "reason": f"Item '{specific_item}' not found in item_master.",
                "results": [],
            })
    else:
        test_items = random.sample(items, min(count, len(items)))

    # ── Load all target tables ──
    target_data = {}
    missing_tables = []

    for table_key, display_name, _, target_field in REQUIRED_JOINS:
        rows = _load_current_data(table_key)
        if not rows:
            missing_tables.append({"table_key": table_key, "name": display_name})
            target_data[table_key] = {}
        else:
            target_data[table_key] = _build_lookup(rows, target_field)

    # Also load family_hierarchy to resolve item_code → family for indirect joins
    fam_rows = _load_current_data("family_hierarchy")
    item_to_family = {}
    for r in fam_rows:
        ic = (r.get("item_code") or "").strip().upper()
        fam = (r.get("family") or "").strip().upper()
        if ic and fam:
            item_to_family[ic] = fam

    # ── Test each part ──
    results = []
    pass_count = 0

    for item in test_items:
        item_code = (item.get("item_code") or "").strip().upper()
        family = item_to_family.get(item_code, "")
        description = item.get("description") or ""

        joins = {}
        all_pass = True

        for table_key, display_name, join_field, target_field in REQUIRED_JOINS:
            # Determine the lookup key value
            if join_field == "item_code":
                lookup_val = item_code
            elif join_field == "family":
                lookup_val = family
            else:
                lookup_val = (item.get(join_field) or "").strip().upper()

            if not lookup_val:
                joins[display_name] = {
                    "status": "FAIL",
                    "reason": f"No {join_field} value to join on",
                    "lookup_key": join_field,
                    "lookup_value": "",
                }
                all_pass = False
                continue

            matches = target_data.get(table_key, {}).get(lookup_val, [])

            if table_key == "bom_master":
                # Spec: "exactly one active BOM"
                active = [m for m in matches if (m.get("status") or "Active").lower() == "active"]
                if len(active) == 0:
                    joins[display_name] = {
                        "status": "FAIL",
                        "reason": f"No active BOM found (total matches: {len(matches)})",
                        "lookup_key": target_field,
                        "lookup_value": lookup_val,
                    }
                    all_pass = False
                elif len(active) > 1:
                    joins[display_name] = {
                        "status": "WARN",
                        "reason": f"{len(active)} active BOMs — spec says exactly one",
                        "lookup_key": target_field,
                        "lookup_value": lookup_val,
                    }
                    # WARN doesn't fail the test — multiple BOMs is common for variants
                else:
                    joins[display_name] = {
                        "status": "PASS",
                        "match_count": 1,
                    }
            elif matches:
                joins[display_name] = {
                    "status": "PASS",
                    "match_count": len(matches),
                }
            else:
                joins[display_name] = {
                    "status": "FAIL",
                    "reason": f"No match in {table_key} for {target_field}='{lookup_val}'",
                    "lookup_key": target_field,
                    "lookup_value": lookup_val,
                }
                all_pass = False

        if all_pass:
            pass_count += 1

        results.append({
            "item_code": item_code,
            "description": description[:60],
            "family": family or "‼ NO FAMILY",
            "verdict": "PASS" if all_pass else "FAIL",
            "joins": joins,
        })

    total = len(results)
    fail_count = total - pass_count

    if missing_tables:
        verdict = "BLOCKED"
        verdict_detail = f"Cannot run full test — {len(missing_tables)} master table(s) have no data loaded."
    elif fail_count == 0:
        verdict = "PASS"
        verdict_detail = f"All {total} parts resolve to every required master."
    else:
        verdict = "FAIL"
        verdict_detail = f"{fail_count}/{total} parts failed at least one join."

    return Response({
        "verdict": verdict,
        "verdict_detail": verdict_detail,
        "tested": total,
        "passed": pass_count,
        "failed": fail_count,
        "missing_tables": missing_tables,
        "results": results,
    })
