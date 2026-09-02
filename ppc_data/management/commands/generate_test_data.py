"""Generate realistic PPC test Excel files with EXACT field-map headers.

Usage:
    .venv/bin/python manage.py generate_test_data

Creates files in /root/jclp_automation_portal/jcpl/test_data/ppc/
"""

import os
import random
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from openpyxl import Workbook

OUTPUT_DIR = "/root/jclp_automation_portal/jcpl/test_data/ppc"

SECTIONS = ["PRESS", "FORGE", "MACHINE", "ASSEMBLY", "PACKING"]
FAMILIES = ["T-BOLT", "U-BOLT", "FLANGE", "SPRING", "CLAMP"]
SUB_FAMILIES = {"T-BOLT": ["TB-HEX", "TB-CARRIAGE", "TB-STUD"],
                "U-BOLT": ["UB-ROUND", "UB-SQUARE"],
                "FLANGE": ["FL-WELD", "FL-SLIP", "FL-BLIND"],
                "SPRING": ["SP-COMP", "SP-TENSION"],
                "CLAMP": ["CL-PIPE", "CL-HOSE", "CL-BAND"]}
PRODUCT_GROUPS = ["PG-AUTO", "PG-INFRA", "PG-AGRI", "PG-EXPORT"]
PLANTS = ["PLANT-1", "PLANT-2"]
MACHINES = [("M-PR-01", "Press 100T", "PRESS"), ("M-PR-02", "Press 200T", "PRESS"),
            ("M-FG-01", "Forge Hammer 1", "FORGE"), ("M-MC-01", "CNC Lathe 1", "MACHINE"),
            ("M-MC-02", "VMC 1", "MACHINE"), ("M-AS-01", "Assembly Line 1", "ASSEMBLY"),
            ("M-PK-01", "Packing Line 1", "PACKING")]


def _fg_items():
    items = []
    for fam in FAMILIES:
        for sf in SUB_FAMILIES[fam]:
            for i in range(1, 5):
                items.append({"code": f"FG-{sf}-{i:03d}", "desc": f"{sf} Size {i*10}mm",
                              "family": fam, "sub_family": sf, "product_group": random.choice(PRODUCT_GROUPS),
                              "section": random.choice(SECTIONS), "uom": "NOS", "plant": random.choice(PLANTS)})
    return items


def _rm_items():
    names = ["MS Round Bar 10mm", "MS Round Bar 12mm", "MS Round Bar 16mm", "MS Hex Bar 10mm",
             "HR Coil 2mm", "HR Coil 3mm", "CR Sheet 1mm", "Wire Rod 6mm", "Wire Rod 8mm",
             "Alloy Steel Bar 20mm", "SS Round Bar 10mm", "SS Round Bar 12mm"]
    return [{"code": f"RM-{i:03d}", "desc": n, "uom": "KG"} for i, n in enumerate(names, 1)]


def _cp_items():
    names = ["Hex Nut M10", "Hex Nut M12", "Spring Washer M10", "Lock Nut M10",
             "Pin 6x30", "Bush 10mm", "Rivet 4mm", "Rivet 6mm"]
    return [{"code": f"CP-{i:03d}", "desc": n, "uom": "NOS"} for i, n in enumerate(names, 1)]


def _pm_items():
    names = ["Corrugated Box 300x200", "Poly Bag 200x150", "Bubble Wrap 1m",
             "Stretch Film", "Label Sticker A4", "Tape 2inch"]
    return [{"code": f"PM-{i:03d}", "desc": n, "uom": "NOS"} for i, n in enumerate(names, 1)]


def _split_qty(total, n):
    if n <= 0: return []
    base = total // n
    parts = [base] * n
    parts[-1] += total - sum(parts)
    return [max(0, p + random.randint(-max(1, base//5), max(1, base//5))) for p in parts]


class Command(BaseCommand):
    help = "Generate PPC test Excel files with exact field-map headers."

    def handle(self, *args, **options):
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        fg, rm, cp, pm = _fg_items(), _rm_items(), _cp_items(), _pm_items()
        plan_month = "2026-09"
        work_days = [date(2026, 9, 1) + timedelta(days=i) for i in range(30)
                     if (date(2026, 9, 1) + timedelta(days=i)).weekday() < 6
                     and (date(2026, 9, 1) + timedelta(days=i)).month == 9]
        files = {}

        # ── W1.1 Item Master (uses item_master field map headers) ──
        wb = Workbook(); ws = wb.active; ws.title = "Item Master"
        ws.append(["Item Code", "Item Description", "Item Type", "Item Category",
                    "Item Group", "HSN Code", "Site", "Status", "UOM", "Sub Group", "Product Group"])
        for it in fg:
            ws.append([it["code"], it["desc"], "FG", "Finished", it["family"], "7318",
                       "JCPL-1", "Active", it["uom"], it["sub_family"], it["product_group"]])
        for it in rm:
            ws.append([it["code"], it["desc"], "RM", "Raw Material", "Steel", "7213",
                       "JCPL-1", "Active", it["uom"], "", ""])
        for it in cp:
            ws.append([it["code"], it["desc"], "CP", "Component", "Fastener", "7318",
                       "JCPL-1", "Active", it["uom"], "", ""])
        for it in pm:
            ws.append([it["code"], it["desc"], "PM", "Packing", "Packing", "4819",
                       "JCPL-1", "Active", it["uom"], "", ""])
        files["Product Group Mapping.xlsx"] = wb

        # ── W1.2 Family Hierarchy ──
        wb = Workbook(); ws = wb.active; ws.title = "Family Group"
        ws.append(["Item Code", "Item Description", "Jolly Size", "Jolly Code",
                    "Family", "Product Group", "Section", "Customer Category",
                    "Sub Group", "Item Type"])
        for it in fg:
            ws.append([it["code"], it["desc"], f"{random.randint(10,50)}mm", it["code"][:8],
                       it["family"], it["product_group"], it["section"],
                       random.choice(["OEM", "Aftermarket", "Export"]),
                       it["sub_family"], "FG"])
        files["Monitoring.xlsx"] = wb

        # ── W1.4 Route Master ──
        wb = Workbook(); ws = wb.active; ws.title = "Process File"
        ws.append(["Family", "Operation Seq", "Operation Name", "Machine / Line",
                    "Is Semi Output", "Cycle Time", "Setup Time", "Section"])
        for fam in FAMILIES:
            for op_no, m in enumerate(random.sample(MACHINES, min(3, len(MACHINES))), 1):
                ws.append([fam, op_no * 10, f"OP-{op_no}", m[0], "No",
                           round(random.uniform(0.5, 5.0), 2), round(random.uniform(5, 30), 1), m[2]])
        files["Process File.xlsx"] = wb

        # ── W1.5 Operation Stage Map ──
        wb = Workbook(); ws = wb.active; ws.title = "Operation Stages"
        ws.append(["Operation Name", "Stage", "Family", "Section", "Operation Seq"])
        for i, (sec, ops) in enumerate([(s, [f"OP-{j}" for j in range(1, 4)]) for s in SECTIONS]):
            for j, op in enumerate(ops):
                ws.append([op, f"STG-{i*3+j+1:02d}", random.choice(FAMILIES), sec, (j+1)*10])
        files["In process-Rejection.xlsx"] = wb

        # ── W1.6 Capacity ──
        wb = Workbook(); ws = wb.active; ws.title = "Production Targets"
        ws.append(["Family", "Product Group", "Section", "Capacity / Shift (8h)",
                    "Capacity / Shift (12h)", "Monthly Capacity", "Manpower / Shift",
                    "Target PPP (8h)", "Target PPP (12h)", "Working Days", "Setups", "Plant"])
        for fam in FAMILIES:
            for sec in SECTIONS:
                c8 = random.randint(200, 1500)
                ws.append([fam, random.choice(PRODUCT_GROUPS), sec, c8, int(c8*1.5),
                           c8 * 2 * len(work_days), random.randint(3, 12),
                           c8, int(c8*1.5), len(work_days),
                           random.randint(1, 5), "PLANT-1"])
        files["Production Targets.xlsx"] = wb

        # ── W1.7 Machine Master ──
        wb = Workbook(); ws = wb.active; ws.title = "Machine Loading"
        ws.append(["Machine Code", "Machine Name", "Line", "Section", "Plant",
                    "SPM", "Capacity / Shift", "Alternate Machine", "ATMC Group", "Active"])
        for m in MACHINES:
            ws.append([m[0], m[1], m[0], m[2], "PLANT-1",
                       random.randint(10, 60), random.randint(200, 1500),
                       "", m[2], "Yes"])
        files["Machine Loading data.xlsx"] = wb

        # ── W1.8 Batch EBQ ──
        wb = Workbook(); ws = wb.active; ws.title = "EBQ"
        ws.append(["Product Group", "Family", "EBQ Qty", "Batch Size",
                    "No of Batches", "ATMC Feasible", "Section"])
        for fam in FAMILIES:
            for pg in PRODUCT_GROUPS[:2]:
                ebq = random.choice([50, 100, 200, 500])
                ws.append([pg, fam, ebq, ebq * 2, 4, "Yes", random.choice(SECTIONS)])
        files["EBQ Batch Monitoring.xlsx"] = wb

        # ── W1.9 Lead Time ──
        wb = Workbook(); ws = wb.active; ws.title = "Lead Time"
        ws.append(["SKU", "Part Code", "Description", "Family", "Category",
                    "Min Lead Time", "Max Lead Time", "Mfg Lead Time", "UOM"])
        for it in rm + cp + pm:
            ws.append([it["code"], it["code"], it["desc"], "",
                       "RM" if it["code"].startswith("RM") else "CP" if it["code"].startswith("CP") else "PM",
                       random.choice([7, 14]), random.choice([21, 30, 45]),
                       random.choice([5, 10, 15]), it["uom"]])
        files["Lead Time Data.xlsx"] = wb

        # ── W1.11 BOM Master ──
        wb = Workbook(); ws = wb.active; ws.title = "BOM Template"
        ws.append(["BOM Code", "Item Code", "Component", "Component Description",
                    "BOM Qty", "BOM UOM", "Scrap%", "Drawing Revision", "Co-Product",
                    "BOM Type", "Effective From", "Effective To", "Status"])
        for i, it in enumerate(fg):
            bom = f"BOM-{i+1:04d}"
            for r in random.sample(rm, min(3, len(rm))):
                ws.append([bom, it["code"], r["code"], r["desc"],
                           round(random.uniform(0.1, 2.5), 3), r["uom"],
                           round(random.uniform(0, 5), 1), "R1", "No", "Standard",
                           "2026-01-01", "", "Active"])
            for c in random.sample(cp, min(2, len(cp))):
                ws.append([bom, it["code"], c["code"], c["desc"],
                           random.randint(1, 6), c["uom"],
                           round(random.uniform(0, 2), 1), "R1", "No", "Standard",
                           "2026-01-01", "", "Active"])
            p = random.choice(pm)
            ws.append([bom, it["code"], p["code"], p["desc"],
                       1, p["uom"], 0, "R1", "No", "Standard",
                       "2026-01-01", "", "Active"])
        files["BOM_Item_Template.xlsx"] = wb

        # ── W1.14 Stock Policy ──
        wb = Workbook(); ws = wb.active; ws.title = "Green Level"
        ws.append(["Item Code", "Description", "Plant", "Item Type",
                    "Blue Level", "Green Level", "Yellow Level", "Red Level",
                    "Reorder Qty", "Safety Stock", "Daily Consumption",
                    "Lead Time Consumption", "Monthly Avg", "Policy Owner", "Last Reviewed"])
        for it in rm + cp + pm:
            s = random.randint(100, 1000)
            ws.append([it["code"], it["desc"], "PLANT-1",
                       "RM" if it["code"].startswith("RM") else "CP" if it["code"].startswith("CP") else "PM",
                       s*6, s*4, s*2, s, s*3, s, round(s/26, 1), round(s*14/26, 1),
                       s*30//26, "PPC", "2026-08-01"])
        files["Green Level RM CP Packing.xlsx"] = wb

        # ── W1.16 Rate ASP ──
        wb = Workbook(); ws = wb.active; ws.title = "ASP"
        ws.append(["Item Code", "Description", "ASP", "Standard Rate", "Landed Rate", "UOM"])
        for it in fg:
            asp = round(random.uniform(50, 500), 2)
            ws.append([it["code"], it["desc"], asp, asp * 0.9, asp * 1.1, it["uom"]])
        files["ASP for FG.xlsx"] = wb

        # ── L1 ERP FG Stock ──
        wb = Workbook(); ws = wb.active; ws.title = "FG Stock"
        ws.append(["Item Code", "Item Description", "Site", "Location", "Opening",
                    "Receipt", "Issued", "Closing", "UOM", "Batch No",
                    "Item Type", "Item Category", "Item Group"])
        for it in fg:
            op = random.randint(100, 3000); rec = random.randint(0, 500); iss = random.randint(0, 400)
            ws.append([it["code"], it["desc"], "JCPL-1", "WH-FG", op, rec, iss,
                       op+rec-iss, it["uom"], "", "FG", "Finished", it["family"]])
        files["FG Stock Report.xlsx"] = wb

        # ── L1 ERP CP/RM Stock (with Group column) ──
        for label, items, typ in [("CP", cp, "Component"), ("RM", rm, "Raw Material")]:
            wb = Workbook(); ws = wb.active; ws.title = f"{label} Stock"
            ws.append(["Item Code", "Item Description", "Site", "Location", "Opening",
                        "Receipt", "Issued", "Closing", "UOM", "Safety Stock", "Reorder Qty",
                        "Lead Time Days", "Daily Consumption", "Green Level", "Yellow Level",
                        "Red Level", "Current Stock in Kg", "Current Stock Days",
                        "To Be Ordered Qty", "Rate", "Amount", "Category", "Group", "Item Type"])
            for it in items:
                op = random.randint(500, 30000); rec = random.randint(0, 5000); iss = random.randint(0, 4000)
                cl = op + rec - iss; s = random.randint(100, 1000)
                ws.append([it["code"], it["desc"], "JCPL-1", f"WH-{label}", op, rec, iss,
                           cl, it["uom"], s, s*3, 14, round(s/26, 1), s*4, s*2, s,
                           cl * 0.5, round(cl / max(1, s/26), 1), max(0, s*3 - cl),
                           round(random.uniform(10, 200), 2), round(cl * random.uniform(10, 200), 2),
                           typ, label, label])
            files[f"{label} Stock Report.xlsx"] = wb

        # ── L1 ERP PM Stock (no Group column — field map differs) ──
        wb = Workbook(); ws = wb.active; ws.title = "PM Stock"
        ws.append(["Item Code", "Item Description", "Site", "Location", "Opening",
                    "Receipt", "Issued", "Closing", "UOM", "Safety Stock", "Reorder Qty",
                    "Lead Time Days", "Daily Consumption", "Green Level", "Yellow Level",
                    "Red Level", "Current Stock in Kg", "Current Stock Days",
                    "To Be Ordered Qty", "Rate", "Amount", "Category", "Item Type"])
        for it in pm:
            op = random.randint(500, 30000); rec = random.randint(0, 5000); iss = random.randint(0, 4000)
            cl = op + rec - iss; s = random.randint(100, 1000)
            ws.append([it["code"], it["desc"], "JCPL-1", "WH-PM", op, rec, iss,
                       cl, it["uom"], s, s*3, 14, round(s/26, 1), s*4, s*2, s,
                       cl * 0.5, round(cl / max(1, s/26), 1), max(0, s*3 - cl),
                       round(random.uniform(10, 200), 2), round(cl * random.uniform(10, 200), 2),
                       "Packing", "PM"])
        files["PM Stock Report.xlsx"] = wb

        # ── L1 ERP Sales Orders ──
        wb = Workbook(); ws = wb.active; ws.title = "Sales Orders"
        ws.append(["Order No", "Order Date", "Item Code", "Item Description",
                    "Customer Code", "Customer Name", "Order Qty", "Dispatched Qty",
                    "Pending Qty", "Delivery Date", "UOM", "Rate", "Amount", "Status", "MTO / MTS"])
        custs = [("C001", "TATA MOTORS"), ("C002", "MAHINDRA"), ("C003", "ASHOK LEYLAND"),
                 ("C004", "MARUTI SUZUKI"), ("C005", "ESCORTS")]
        for i, it in enumerate(random.sample(fg, min(30, len(fg)))):
            c = random.choice(custs); oq = random.randint(100, 5000); dq = random.randint(0, oq)
            ws.append([f"SO-2026-{i+1:04d}", "2026-08-15", it["code"], it["desc"],
                       c[0], c[1], oq, dq, oq - dq,
                       (date(2026, 9, 1) + timedelta(days=random.randint(0, 29))).isoformat(),
                       it["uom"], round(random.uniform(50, 500), 2), round(oq * random.uniform(50, 500), 2),
                       "Open", random.choice(["MTO", "MTS"])])
        files["Sales Order Report.xlsx"] = wb

        # ── L2 Demand Freeze ──
        wb = Workbook(); ws = wb.active; ws.title = "Demand"
        ws.append(["Item Code", "Item Description", "Family", "Product Group",
                    "Category", "Month", "Demand Qty", "UOM", "Customer", "Plant"])
        for it in fg:
            ws.append([it["code"], it["desc"], it["family"], it["product_group"],
                       "A", plan_month, random.randint(200, 8000), it["uom"], "", it["plant"]])
        files["Forecast Demand Sep 2026.xlsx"] = wb

        # ── L3 MPS Schedule ──
        wb = Workbook(); ws = wb.active; ws.title = "MPS Schedule"
        from ppc_data.field_maps.mps_schedule import FIELD_MAP as MPS_MAP
        mps_headers = list(MPS_MAP.values())
        ws.append(mps_headers)
        for it in fg:
            total = random.randint(200, 6000)
            demand = random.randint(int(total * 0.8), int(total * 1.2))
            weeks = [total // 5] * 4 + [total - 4 * (total // 5)]
            row = {h: "" for h in mps_headers}
            row["Item Code"] = it["code"]
            row["Description"] = it["desc"]
            row["Family"] = it["family"]
            row["Product Group"] = it["product_group"]
            row["Section"] = it["section"]
            row["MTO/MTS"] = random.choice(["MTO", "MTS"])
            row["ATMC Group"] = it["section"]
            row["Priority"] = random.choice(["HIGH", "MEDIUM", "LOW"])
            row["Avg Month Demand"] = demand
            row["Month Demand"] = demand
            row["Net Requirement"] = max(0, demand - random.randint(0, 500))
            row["FG Stock"] = random.randint(50, 2000)
            row["WIP"] = random.randint(0, 300)
            row["Safety Stock"] = random.randint(100, 500)
            row["PAB"] = random.randint(0, 1000)
            row["EBQ"] = random.choice([50, 100, 200, 500])
            row["Batch Qty"] = random.choice([100, 200, 500, 1000])
            row["W1"] = weeks[0]; row["W2"] = weeks[1]; row["W3"] = weeks[2]
            row["W4"] = weeks[3]; row["W5"] = weeks[4]
            row["Total Plan"] = total
            row["Mfg LT"] = random.choice([5, 7, 10, 14])
            row["Rate"] = round(random.uniform(50, 500), 2)
            row["Amount"] = round(total * row["Rate"], 2)
            row["UOM"] = it["uom"]
            row["Plant"] = it["plant"]
            ws.append([row.get(h, "") for h in mps_headers])
        files["MpsSS.xlsm"] = wb

        # ── L4 R3SS Plan ──
        wb = Workbook(); ws = wb.active; ws.title = "All"
        from ppc_data.field_maps.r3ss_plan import FIELD_MAP as R3SS_MAP
        fixed_headers = list(R3SS_MAP.values())
        day_headers = [d.strftime("%-d-%b") for d in work_days]  # "1-Sep", "2-Sep"
        ws.append(fixed_headers + day_headers)
        for it in fg:
            total = random.randint(200, 6000)
            demand = random.randint(int(total * 0.8), int(total * 1.2))
            opening = random.randint(100, 3000)
            closing = max(0, opening + total - demand)
            daily = _split_qty(total, len(work_days))
            # Adjust last day so sum = total
            diff = total - sum(daily)
            daily[-1] = max(0, daily[-1] + diff)

            weeks = _split_qty(total, 5)

            row_vals = {
                "Item Code": it["code"], "Description": it["desc"],
                "Jolly Code": it["code"][:8], "Jolly Size": f"{random.randint(10,50)}mm",
                "Green Level": random.randint(500, 3000),
                "Opening Bal. Qty": opening, "F.G. Stock": random.randint(50, 2000),
                "Pack": random.randint(0, 500), "Disp": random.randint(0, 300),
                "To Plan": total, "Total Plan HW": int(total * 0.6),
                "Total Plan MIT": int(total * 0.4), "Total Plan": total,
                "Difference": total - demand,
                "Initial Demand": demand, "Additional Demand": 0,
                "Total Demand": demand,
                "W1": weeks[0], "W2": weeks[1], "W3": weeks[2], "W4": weeks[3], "W5": weeks[4] if len(weeks) > 4 else 0,
                "Cutting": random.randint(0, 200),
                "Section": it["section"], "MTO / MTS": random.choice(["MTO", "MTS"]),
                "Product Group": it["product_group"], "Family": it["family"],
                "ASP": round(random.uniform(50, 500), 2),
                "Backlog": max(0, demand - total),
                "Plant": it["plant"], "Category": "A",
                "Priority": random.choice(["HIGH", "MEDIUM", "LOW"]),
            }
            row = [row_vals.get(h, "") for h in fixed_headers] + daily
            ws.append(row)
        files["R3 SS September.xlsx"] = wb

        # Save all
        for name, wb in files.items():
            wb.save(os.path.join(OUTPUT_DIR, name))
            self.stdout.write(f"  ✓ {name}")

        self.stdout.write(self.style.SUCCESS(f"\n✅ {len(files)} test files created in {OUTPUT_DIR}/"))
