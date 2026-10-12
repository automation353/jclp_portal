"""Append1 — Demand–Supply Reconciliation computation.

Joins the 5 S&OP data sources (DPR, Forecast, Opening Stock, Green Level,
Sales Register) into a single item-level reconciliation table matching the
``Append1`` sheet in the Sales+Ops Dashboard Google Sheet.

44 columns per item — from raw source aggregations through computed shortfall,
surplus, insight tags, and ₹ financial impact.

Column layout mirrors the Google Sheet ``Append1`` tab:
  A  Item Group         Q  Dispatch %            AH  Surplus Production (₹)
  B  Item Code          R  Closing Inventory      AI  Excess Op. Stock Value (₹)
  C  Product Class      S  Green Level            AJ  Build Required
  D  Original Forecast  T  Free Inventory         AK  Production Counted
  E  Committed Forecast U  Uncovered Shortfall    AL  Prod. Shortfall (₹)
  F  Ops Adjustment     V  Dispatch Gap           AM  Dispatch Gap (₹)
  G  Actual Sales Dem.  W  Shortfall Add. Demand  AN  Shortfall Add. Demand (₹)
  H  Additional Demand  X  Demand Reduction Adj.  AO  Demand Reduction (₹)
  I  Forecast Accuracy% Y  Prod-Driven Shortfall  AP  Excess Dispatch Value (₹)
  J  Opening Inventory  Z  Production Surplus
  K  Actual Production  AA Excess Opening Stock
  L  Stock Adj (Added)  AB Excess Dispatched
  M  Stock Adj (Deduct) AC Sales Insight Tag
  N  Total Available    AD Sales Narrative
  O  Type (MTS/MTO)     AE Ops Insight Tag
  P  Actual Dispatch    AF Ops Narrative
                        AG Ops Capacity Narrative
"""

import logging
from collections import defaultdict, Counter

log = logging.getLogger(__name__)


# ── helpers ─────────────────────────────────────────────────────────────

def _num(val):
    """Safely convert to float, defaulting to 0."""
    if val is None:
        return 0.0
    try:
        v = float(val)
        return v if v == v else 0.0  # NaN check
    except (ValueError, TypeError):
        return 0.0


def _pct(num, denom, digits=1):
    """Percentage string, blank if denom is zero."""
    if not denom:
        return ""
    return f"{round(num / denom * 100, digits)}%"


def _fmt(val, blank_zero=True):
    """Format a number for output: blank string if zero and blank_zero."""
    if blank_zero and val == 0:
        return ""
    return round(val, 2)


# ── ASP table (Item Group → price) ─────────────────────────────────────

# Hardcoded from the ASP tab in the Google Sheet (Finance ASP per piece).
# Updated periodically — kept here so Append1 can be computed without
# fetching the ASP sheet.  Set to 0 for groups that don't have a rate.
ASP_TABLE = {
    "12mm 1Way Serrated": 20.802493458165134,
    "12mm 1Way Spring Insert": 26.934634146341462,
    "12mm 2Way Serrated": 17.524079748575918,
    "12mm 2Way Spring Insert": 0,
    "9mm 2 Way Serrated": 19.580188772975657,
    "9mm 2 Way Spring Insert": 0,
    "CAT SLTB": 73.52670622139345,
    "Coupling": 0,
    "DPF": 0,
    "HD CTWD-14mm": 89.37154055896387,
    "HD CTWD-16mm": 78.1496524213331,
    "HDWD-14mm": 30.95,
    "HDWD-16mm": 52.63922040423484,
    "Mini Clip": 8.925173501577287,
    "MSWD": 6.547389899422255,
    "Others": 0,
    "P-Clips": 11.625558954538711,
    "QRC": 40.04289071680376,
    "SLTB and HDSLTB": 38.9043020787485,
    "SSWD-12mm": 14.688327723645578,
    "SSWD-12mm Jumbo": 33.62,
    "SSWD-12mm liner": 14.880267797737858,
    "SSWD-14mm": 29.81132075471698,
    "SSWD-16mm": 16.52,
    "SSWD-9mm lug locking": 12.1388868101029,
    "SSWD-9mm welding": 10.084215277777778,
    "Stepless": 0,
    "TB-14mm": 20.260979057103295,
    "TB-19mm TL": 24.35772370486656,
    "TB-19mm TX": 28.742253442701013,
    "TB-19mm TX small": 0,
    "V clamp": 18.5,
    "VTB and QVTB": 140.2207637015262,
    "VWD Clamps": 0,
}


# ── Focus Product groups (from the reference Sales+Ops Dashboard "Focus" tab) ──
# The reference classifies an item as "Focus Product" when its ITEM GROUP is one
# of these; every other item is "Regular".  (Not a per-item-code list.)
import re as _re


def _focus_norm(s):
    return _re.sub(r"\s+", " ", str(s or "").strip()).lower()


FOCUS_GROUPS = {
    _focus_norm(g) for g in [
        "12mm 1Way Serrated", "12mm 1Way Spring Insert",
        "12mm 2Way Serrated", "12mm 2Way Spring Insert",
        "9mm 2 Way Serrated", "9mm 2 Way Spring Insert",
        "CAT SLTB", "Coupling", "DPF",
        "HD CTWD-14mm", "HD CTWD-16mm", "HDWD-14mm", "HDWD-16mm",
        "Stepless", "VTB & QVTB", "VWD Clamps", "Clamp with Key",
        "Barrel Clamps", "TB-32mm", "Strap Clamps", "Waveseal SFC",
    ]
}


# ── Insight tag / narrative generators ──────────────────────────────────
# Implements the Insight Logic Master trigger rules from the Google Sheet.

def _sales_insight_tag(item):
    """Generate Sales Insight Tag (col AC) — pipe-separated tags.

    Triggers from Insight Logic Master rows W-01 through W-07.
    Variables (per Header Reference column mapping):
      G = actual_sales_demand  (committed demand)
      N = actual_dispatch
      I = forecast_accuracy_var (0 = perfect, higher = worse)
    """
    G = item["actual_sales_demand"]
    N = item["actual_dispatch"]
    I = item["forecast_accuracy_var"]

    tags = []

    # W-01 Over-Delivered: dispatch > 110% of demand
    if G > 0 and N > G * 1.1:
        tags.append("Over-Delivered")
    # W-02 On Target: dispatch within ±10% of demand
    elif G > 0 and N >= G * 0.9 and N <= G * 1.1:
        tags.append("On Target")
    # W-03 Short Delivery: dispatch < 90% of demand
    elif G > 0 and N < G * 0.9:
        tags.append("Short Delivery")

    # Forecast accuracy tags
    if I == 0:
        tags.append("Forecast Bullseye")  # W-04
    elif I <= 0.1:
        tags.append("Forecast Drift (Minor)")  # W-05
    elif I <= 0.3:
        tags.append("Forecast Drift (Moderate)")  # W-06
    elif I > 0.3:
        tags.append("Forecast Drift (Major)")  # W-07

    return " | ".join(tags) if tags else ""


def _sales_narrative(item):
    """Generate Sales Narrative (col AD) — human-readable summary.

    Triggers from Insight Logic Master rows X-01 through X-13.
    """
    G = item["actual_sales_demand"]
    N = item["actual_dispatch"]
    M = item["type_mts_mto"]
    I = item["forecast_accuracy_var"]
    H = item["additional_demand_dir"]  # positive = committed lower, neg = higher
    U = item["excess_dispatched"]
    V = item["uncovered_shortfall"]

    parts = []

    # X-01 Dispatch header (always)
    if G > 0:
        pct = round(N / G * 100)
        parts.append(f"Dispatch {pct}% of committed ({N:,.0f} vs {G:,.0f}).")
    else:
        parts.append(f"Dispatch {N:,.0f} units (no committed demand).")

    # X-02 / X-03 Type context
    if M == "MTS":
        parts.append("MTS item — buffer stock + green level matters.")
    elif M == "MTO":
        parts.append("MTO item — demand is order-driven.")

    # X-04–X-10 Forecast accuracy narrative
    if I == 0:
        parts.append("Forecast hit dead-on (0% variance) — strong demand sensing.")
    elif I <= 0.1 and H > 0:
        parts.append(f"Forecast tightening of {I:.0%} — minor cut, within normal demand-sensing tolerance.")
    elif I <= 0.1 and H < 0:
        parts.append(f"Forecast raised by {I:.0%} — minor uplift, well within tolerance.")
    elif I <= 0.3 and H > 0:
        parts.append(f"⚠ Forecast cut by {I:.0%} post-commit — demand softened or deals slipped.")
    elif I <= 0.3 and H < 0:
        parts.append(f"⚠ Forecast raised by {I:.0%} post-commit — late orders pulled in.")
    elif I > 0.3 and H > 0:
        parts.append(f"🚩 Major forecast cut of {I:.0%} — severe over-promise.")
    elif I > 0.3 and H < 0:
        parts.append(f"🚩 Major forecast uplift of {I:.0%} — late demand surge.")

    # X-11/X-12/X-13 Gap actions
    if U > 0:
        parts.append(f"Action: review over-commit of {U:,.0f} units.")
    elif V > 0:
        parts.append(f"Action: recover shortfall of {V:,.0f} units.")
    else:
        parts.append("No open commitment gap.")

    return " ".join(parts)


def _ops_insight_tag(item):
    """Generate Operations Insight Tag (col AE) — pipe-separated tags.

    Triggers from Insight Logic Master rows Y-01 through Y-12.
    """
    G = item["actual_sales_demand"]
    M = item["type_mts_mto"]
    N = item["actual_dispatch"]
    O = item["closing_inventory"]
    P = item["green_level"]
    R = item["production_shortfall"]
    S = item["production_surplus"]
    F = item["ops_adjustment"]
    D = item["original_forecast"]

    tags = []

    # Y-01 Production Shortfall
    if R > 0:
        tags.append("Production Shortfall")

    # MTS-specific
    if M == "MTS":
        # Y-03 Stock-Out Risk (check before Y-02 — more severe)
        if P > 0 and O < P * 0.5:
            tags.append("Stock-Out Risk")
        # Y-02 Below Safety
        elif P > 0 and O < P:
            tags.append("Below Safety")
        # Y-04 Excess Inventory
        if G > 0 and S > G * 0.5:
            tags.append("Excess Inventory")
        # Y-05 Production Surplus
        elif S > 0:
            tags.append("Production Surplus")

    # MTO-specific
    if M == "MTO":
        # Y-07 Over-Production (check before Y-06 — more severe)
        if S > 0:
            tags.append("Over-Production")
        # Y-06 Unsold MTO Stock
        elif O > 0 and N >= G:
            tags.append("Unsold MTO Stock")

    # Y-08 to Y-11 Capacity Gap
    if D > 0 and F < 0:
        ratio = abs(F) / D
        if ratio > 0.3:
            tags.append("Capacity Gap (Major)")    # Y-08
        elif ratio > 0.1:
            tags.append("Capacity Gap (Moderate)")  # Y-09
        else:
            tags.append("Capacity Gap (Minor)")     # Y-10
    elif F > 0:
        tags.append("Ops Over-Commit")  # Y-11

    # Y-12 Healthy Stock — only if nothing else triggered
    if not tags:
        tags.append("Healthy Stock")

    return " | ".join(tags)


def _ops_narrative(item):
    """Generate Operations Narrative (col AF).

    Triggers from Insight Logic Master rows Z-01 through Z-06.
    """
    G = item["actual_sales_demand"]
    K = item["actual_production"]
    M = item["type_mts_mto"]
    O = item["closing_inventory"]
    P = item["green_level"]
    R = item["production_shortfall"]
    S = item["production_surplus"]

    parts = []

    # Z-01 Production header (always)
    parts.append(f"Produced {K:,.0f} units against committed {G:,.0f} units.")

    # Z-02 Production Shortfall
    if R > 0:
        parts.append(f"Shortfall of {R:,.0f} units — expedite production or procure.")

    # Z-03 MTS Below Safety
    if M == "MTS" and P > 0 and O < P:
        cover = round(O / P, 1) if P else 0
        parts.append(
            f"Closing {O:,.0f} units. Green level {P:,.0f} "
            f"({cover}x cover) — ⚠ Safety breach — replenish urgently."
        )

    # Z-04 Excess Inventory
    if M == "MTS" and G > 0 and S > G * 0.5:
        parts.append(f"Excess build-up of {S:,.0f} units — throttle production.")

    # Z-05 MTO Over-Production
    if M == "MTO" and S > 0:
        parts.append(
            f"Red flag — produced {S:,.0f} units more than ordered. "
            f"Investigate planning breakdown."
        )

    # Z-06 Healthy Closing
    if R == 0 and S == 0:
        if (M == "MTS" and O >= P) or (M == "MTO" and O == 0):
            parts.append("Production and inventory in healthy state.")

    return " ".join(parts)


def _ops_capacity_narrative(item):
    """Generate Ops Capacity Gap Narrative (col AG).

    Triggers from Insight Logic Master rows AA-01 through AA-05.
    """
    D = item["original_forecast"]
    E = item["committed_forecast"]
    F = item["ops_adjustment"]

    # AA-01 Forecast Accepted
    if F == 0:
        return "Ops accepted Sales forecast in full. No capacity gap at plan stage."

    if D > 0:
        pct = abs(F) / D
        pct_str = f"{pct:.0%}"
    else:
        pct_str = "n/a"

    if F < 0:
        if D > 0 and abs(F) / D > 0.3:
            return (
                f"Ops cut {abs(F):,.0f} units (-{pct_str}) from forecast {D:,.0f}. "
                f"⚠ Major capacity gap — escalate to S&OP."
            )
        elif D > 0 and abs(F) / D > 0.1:
            return (
                f"Ops cut {abs(F):,.0f} units (-{pct_str}) from forecast {D:,.0f}. "
                f"⚠ Moderate gap — line-level mitigation needed."
            )
        else:
            return (
                f"Ops cut {abs(F):,.0f} units (-{pct_str}) from forecast {D:,.0f}. "
                f"Minor adjustment — standard handling."
            )
    else:
        return (
            f"Ops over-committed by {F:,.0f} units (+{pct_str}) vs forecast {D:,.0f}. "
            f"Validate demand uptake with Sales — risk of excess inventory."
        )


# ── Main computation ────────────────────────────────────────────────────

def _get_current_rows(table_key):
    """Fetch all data rows for the current upload of a table_key."""
    from ppc_data.models import PPCUploadBatch
    batch = (
        PPCUploadBatch.objects
        .filter(table_key=table_key, is_current=True)
        .first()
    )
    if not batch:
        return []
    return list(batch.rows.values_list("data", flat=True))


def _find_value(row, *candidates):
    """Return the first non-None value from candidate column names."""
    for c in candidates:
        if c in row and row[c] is not None:
            return row[c]
    return None


def compute_append1():
    """Compute the full Append1 reconciliation table.

    Returns:
        list[dict]: One dict per item, keyed by Append1 column names.
    """
    # ── 1. Load all 5 source tables ──
    dpr_rows = _get_current_rows("sop_dpr")
    forecast_rows = _get_current_rows("sop_forecast")
    opening_rows = _get_current_rows("sop_opening_stock")
    green_rows = _get_current_rows("sop_green_level")
    sales_rows = _get_current_rows("sop_sales_register")

    if not any([dpr_rows, forecast_rows, opening_rows, green_rows, sales_rows]):
        return []

    # ── 1b. Detect the reporting window from the data (mirrors the reference
    # Power Query filters) so raw ERP exports are reduced to the same subset
    # the Sales+Ops Dashboard is built on. ──
    def _month_mode(rows, *datecols):
        c = Counter()
        for r in rows:
            for dc in datecols:
                v = r.get(dc)
                if v:
                    c[str(v)[:7]] += 1
                    break
        return c.most_common(1)[0][0] if c else None

    def _date_mode(rows, datecol, predicate=None):
        c = Counter()
        for r in rows:
            if predicate and not predicate(r):
                continue
            v = r.get(datecol)
            if v:
                c[str(v)[:10]] += 1
        return c.most_common(1)[0][0] if c else None

    DPR_MONTH = _month_mode(dpr_rows, "document_date")              # e.g. 2026-09
    SALES_MONTH = _month_mode(sales_rows, "invoice_date")
    # Original-forecast snapshot = the dominant Forecast Date among Party/Monthly rows.
    FC_SNAPSHOT = _date_mode(
        forecast_rows, "forecast_date",
        lambda r: str(r.get("forecast_level", "")).strip() == "Party"
        and str(r.get("forecast_type", "")).strip() == "Monthly",
    )
    FG_CATS = {"FG- OEM", "FG- Fleetguard"}
    SALES_PARTIES = {"JCPL-Non Auto OEMS", "JCPL-OEM"}
    DPR_PROD_VOUCHERS = {"direct jr", "direct jr reversal"}
    log.info("Append1 window: DPR=%s SALES=%s FC_SNAPSHOT=%s", DPR_MONTH, SALES_MONTH, FC_SNAPSHOT)

    # ── 2. Build Green Level lookup (item_code → type, green_level, family) ──
    green_lookup = {}
    for row in green_rows:
        g = _num(row.get("green_level", 0))
        info = {
            "type": str(row.get("mto_mts", "TBC")).strip().upper(),
            "green_level": g,
            "family": str(row.get("family", "")).strip(),
        }
        # Green Level uses erp_code or jolly_code as the item identifier
        for ic_key in ("erp_code", "jolly_code", "item_code"):
            ic = row.get(ic_key)
            if ic and str(ic).strip() and str(ic).strip() != "0":
                ic = str(ic).strip()
                existing = green_lookup.get(ic)
                # Keep the first match, but never let a blank/zero green row
                # overwrite a real green value (the tab has duplicate rows).
                if existing is None or (g > 0 and existing["green_level"] == 0):
                    green_lookup[ic] = info

    # ── 3. Build Opening Stock lookup (item_code → opening qty, landed rate) ──
    # Only FG-OEM and FG-Fleetguard categories (as per Header Reference)
    opening_lookup = defaultdict(lambda: {"qty": 0.0, "landed_rate": 0.0})
    # XLOOKUP-style rate: first occurrence per code in sheet order (any
    # category, value as-is) — this is what the reference uses to value
    # Excess Opening Stock (₹) = XLOOKUP(code, Opening Stock!G, Opening Stock!BB).
    opening_first_rate = {}
    for row in opening_rows:
        ic = str(row.get("item_code", "")).strip()
        if not ic:
            continue
        if ic not in opening_first_rate:
            opening_first_rate[ic] = _num(row.get("closing_landed_rate", 0))
        cat = str(row.get("item_category", "")).strip()
        if cat not in ("FG- OEM", "FG- Fleetguard"):
            continue
        # Use closing_qty as the "opening" for next period
        qty = _num(row.get("closing_qty_base_uom", 0))
        rate = _num(row.get("closing_landed_rate", 0))
        entry = opening_lookup[ic]
        entry["qty"] += qty
        if rate > 0 and entry["landed_rate"] == 0:
            entry["landed_rate"] = rate

    # ── 4. Aggregate Forecast (per item_code) — reference Power Query rules ──
    # Original Forecast  = Forecast Qty where Level=Party, Type=Monthly, Date=snapshot.
    # Actual Demand      = Forecast Qty where Level=Party (all types/dates),
    #                      Quarterly made negative. (NOT total_order_qty — that
    #                      column carries 999,999,999 sentinels.)
    forecast_agg = defaultdict(lambda: {"forecast_qty": 0.0, "item_group": ""})
    demand_agg = defaultdict(float)
    for row in forecast_rows:
        ic = str(row.get("item_code", "")).strip()
        if not ic:
            continue
        level = str(row.get("forecast_level", "")).strip()
        if level != "Party":
            continue
        ftype = str(row.get("forecast_type", "")).strip()
        qty = _num(row.get("forecast_qty", 0))

        # Original Forecast — Monthly at the committed snapshot date
        if ftype == "Monthly" and (not FC_SNAPSHOT or str(row.get("forecast_date", ""))[:10] == FC_SNAPSHOT):
            fa = forecast_agg[ic]
            fa["forecast_qty"] += qty
            grp = _find_value(row, "item_group", "item_class")
            if grp and not fa["item_group"]:
                fa["item_group"] = str(grp).strip()

        # Actual Demand — all Party rows, Quarterly negated
        demand_agg[ic] += (-abs(qty) if ftype == "Quarterly" else qty)

    # ── 5. Aggregate DPR / Stock Ledger (per item_code) ──
    # Production = receipt_qty, Stock adjustments from trading items
    dpr_agg = defaultdict(lambda: {
        "production": 0.0,
        "stock_adj_added": 0.0,
        "stock_adj_deducted": 0.0,
        "prod_value": 0.0,   # net landed value of production (for the DPR rate)
        "item_group": "",
    })
    for row in dpr_rows:
        ic = str(_find_value(row, "item_code", "item_no") or "").strip()
        if not ic:
            continue
        # Reference filters: previous month · FG-OEM / FG-Fleetguard · exclude Coupling
        if DPR_MONTH and str(row.get("document_date", ""))[:7] != DPR_MONTH:
            continue
        if str(row.get("item_category", "")).strip() not in FG_CATS:
            continue
        grp = str(_find_value(row, "item_group", "item_category", "group") or "").strip()
        if grp == "Coupling":
            continue
        vtype_raw = str(row.get("voucher_type", "")).strip()
        vtype = vtype_raw.lower()
        receipt = _num(_find_value(row, "receipt_qty", "receipt_quantity", "production_qty", "inward_qty"))
        issue = _num(_find_value(row, "issue_qty", "issue_quantity", "dispatch_qty", "outward_qty"))
        agg = dpr_agg[ic]
        if vtype == "tradingitemconversion":
            # Trading-item conversions are stock adjustments, not production.
            agg["stock_adj_added"] += receipt
            agg["stock_adj_deducted"] += issue
        elif vtype in DPR_PROD_VOUCHERS:
            # Production (Net DPR) = Receipt − Issue on Direct JR / Direct JR Reversal.
            agg["production"] += receipt - issue
            # Net landed value → used to derive the per-item production rate
            # (DPR Valuation "Rate" = Value ÷ Qty), which values Production
            # Surplus (₹) in the reference — NOT the opening landed rate.
            agg["prod_value"] += (
                _num(_find_value(row, "receipt_landed_value"))
                - _num(_find_value(row, "issue_landed_value"))
            )
        else:
            continue
        if grp and not agg["item_group"]:
            agg["item_group"] = grp

    # ── 6. Aggregate Sales Register (per item_code) ──
    sales_agg = defaultdict(lambda: {"dispatch": 0.0, "item_group": ""})
    for row in sales_rows:
        ic = str(row.get("item_code", "")).strip()
        if not ic:
            continue
        # Reference filters: previous month · Invoice Status = Exported To GL ·
        # Party A/C in {JCPL-Non Auto OEMS, JCPL-OEM}.
        if SALES_MONTH and str(row.get("invoice_date", ""))[:7] != SALES_MONTH:
            continue
        if str(row.get("invoice_status", "")).strip() != "Exported To GL":
            continue
        if str(row.get("party_a_c_description", "")).strip() not in SALES_PARTIES:
            continue
        qty = _num(_find_value(row, "item_sales_qty", "item_base_qty", "item_bill_qty", "qty", "quantity"))
        sales_agg[ic]["dispatch"] += qty
        grp = _find_value(row, "item_group", "item_group_description")
        if grp and not sales_agg[ic]["item_group"]:
            sales_agg[ic]["item_group"] = str(grp).strip()

    # ── 7. Build the universe of item codes ──
    # Reference Append1 = union of Original-Forecast, DPR and Sales items
    # (Opening / Green / Actual-Demand are looked up, not part of the universe).
    all_codes = set()
    all_codes.update(forecast_agg.keys())
    all_codes.update(ic for ic in dpr_agg if dpr_agg[ic]["production"])
    all_codes.update(ic for ic in sales_agg if sales_agg[ic]["dispatch"])

    log.info(
        "Append1: %d item codes (forecast=%d, dpr=%d, sales=%d, opening=%d, green=%d)",
        len(all_codes), len(forecast_agg), len(dpr_agg),
        len(sales_agg), len(opening_lookup), len(green_lookup),
    )

    # ── 8. Compute per-item ──
    result = []
    for ic in sorted(all_codes):
        fc = forecast_agg.get(ic, {})
        dp = dpr_agg.get(ic, {})
        sa = sales_agg.get(ic, {})
        op = opening_lookup.get(ic, {"qty": 0, "landed_rate": 0})
        gl = green_lookup.get(ic, {"type": "TBC", "green_level": 0, "family": ""})

        # ── Source columns ──
        item_group = (fc.get("item_group") or sa.get("item_group")
                      or dp.get("item_group") or gl.get("family", ""))
        if not str(item_group).strip():
            continue  # reference Append1 filters out rows with no Item Group
        # Product Class: "Focus Product" when the Item Group is one of the
        # reference Focus-tab groups, else "Regular" (matches the reference,
        # which classifies by GROUP — not by item code).
        product_class = (
            "Focus Product"
            if _focus_norm(item_group) in FOCUS_GROUPS
            else "Regular"
        )

        # D: Original Forecast
        original_forecast = fc.get("forecast_qty", 0)
        # E: Committed Forecast (currently = D)
        committed_forecast = original_forecast
        # F: Ops Adjustment = E - D
        ops_adjustment = committed_forecast - original_forecast
        # G: Actual Sales Demand — the Party-level forecast demand feed
        # (all types, Quarterly negated); 0 when the item has no demand row
        # (matches the reference — no fallback to committed forecast).
        actual_sales_demand = demand_agg.get(ic, 0)
        # H: Additional Demand = G - D
        additional_demand = actual_sales_demand - original_forecast
        # Direction indicator for narratives (positive = committed lower)
        additional_demand_dir = original_forecast - actual_sales_demand

        # I: Forecast Accuracy %
        if original_forecast == 0 and actual_sales_demand == 0:
            forecast_accuracy_pct = ""
            forecast_accuracy_var = 0
        elif original_forecast == 0:
            forecast_accuracy_pct = "0%" if actual_sales_demand > 0 else "100%"
            forecast_accuracy_var = 1 if actual_sales_demand > 0 else 0
        else:
            var = abs(actual_sales_demand - original_forecast) / original_forecast
            forecast_accuracy_var = var
            acc = max(0, 1 - var)
            forecast_accuracy_pct = f"{round(acc * 100)}%"

        # J: Opening Inventory
        opening_inventory = op["qty"]
        # K: Actual Production
        actual_production = dp.get("production", 0)
        # L: Stock Adjustment (Added)
        stock_adj_added = dp.get("stock_adj_added", 0)
        # M: Stock Adjustment (Deducted)
        stock_adj_deducted = dp.get("stock_adj_deducted", 0)
        # N: Total Available = J + K + L - M
        total_available = opening_inventory + actual_production + stock_adj_added - stock_adj_deducted
        # O: Type (MTS/MTO)
        type_mts_mto = gl["type"]
        # P: Actual Dispatch (from Sales Register)
        actual_dispatch = sa.get("dispatch", 0)
        # Q: Dispatch %
        dispatch_pct = _pct(actual_dispatch, actual_sales_demand)
        # R: Closing Inventory = N - P
        closing_inventory = total_available - actual_dispatch
        # S: Green Level
        green_level = gl["green_level"]
        # T: Free Inventory (Above Green) = MAX(R - S, 0)
        free_inventory = max(closing_inventory - green_level, 0)
        # U: Uncovered Shortfall = MAX(G - P, 0)
        uncovered_shortfall = max(actual_sales_demand - actual_dispatch, 0)
        # V: Dispatch Gap (Shippable from Stock)
        if actual_dispatch < actual_sales_demand and closing_inventory > 0:
            dispatch_gap = min(closing_inventory, actual_sales_demand - actual_dispatch)
        else:
            dispatch_gap = 0
        # W: Shortfall on Additional Demand
        # X: Demand Reduction Adjustment
        # Y: Production-Driven Shortfall
        prod_driven_shortfall = min(
            max(original_forecast - actual_dispatch - closing_inventory, 0),
            max(original_forecast - actual_dispatch, 0),
        )
        # Reconciliation: T = V + W + Y - X
        # W = MAX(T - V - Y, 0)
        shortfall_additional = max(uncovered_shortfall - dispatch_gap - prod_driven_shortfall, 0)
        # X = MAX(V + W + Y - T, 0)
        demand_reduction = max(dispatch_gap + shortfall_additional + prod_driven_shortfall - uncovered_shortfall, 0)
        # Z: Production Surplus = MAX(K - MAX(D + S - J, 0), 0)
        build_needed = max(original_forecast + green_level - opening_inventory, 0)
        production_surplus = max(actual_production - build_needed, 0)
        # AA: Excess Opening Stock = MAX(J - G - S, 0)
        excess_opening_stock = max(opening_inventory - actual_sales_demand - green_level, 0)
        # AB: Excess Dispatched = MAX(P - G, 0)
        excess_dispatched = max(actual_dispatch - actual_sales_demand, 0)

        # Production Shortfall = MAX(G - N, 0) (total available < demand)
        production_shortfall = max(actual_sales_demand - total_available, 0)

        # ── Build the item dict for insight generators ──
        item_data = {
            "actual_sales_demand": actual_sales_demand,
            "actual_dispatch": actual_dispatch,
            "actual_production": actual_production,
            "forecast_accuracy_var": forecast_accuracy_var,
            "additional_demand_dir": additional_demand_dir,
            "excess_dispatched": excess_dispatched,
            "uncovered_shortfall": uncovered_shortfall,
            "type_mts_mto": type_mts_mto,
            "closing_inventory": closing_inventory,
            "green_level": green_level,
            "production_shortfall": production_shortfall,
            "production_surplus": production_surplus,
            "ops_adjustment": ops_adjustment,
            "original_forecast": original_forecast,
            "committed_forecast": committed_forecast,
        }

        # AC: Sales Insight Tag
        sales_tag = _sales_insight_tag(item_data)
        # AD: Sales Narrative
        sales_narrative = _sales_narrative(item_data)
        # AE: Operations Insight Tag
        ops_tag = _ops_insight_tag(item_data)
        # AF: Operations Narrative
        ops_narrative = _ops_narrative(item_data)
        # AG: Ops Capacity Gap Narrative
        ops_cap_narrative = _ops_capacity_narrative(item_data)

        # ── Financial impact columns ──
        asp = ASP_TABLE.get(item_group, 0)
        # Per-item production rate = DPR Valuation "Rate" = net landed value ÷
        # net production qty.  The reference values Production Surplus (₹) with
        # THIS rate (XLOOKUP into DPR Valuation), not the opening landed rate.
        prod_qty_for_rate = dp.get("production", 0)
        prod_rate = (
            dp.get("prod_value", 0) / prod_qty_for_rate
            if prod_qty_for_rate else 0
        )

        # AH: Surplus Production (₹) = Z × production rate (DPR Valuation Rate)
        surplus_production_val = production_surplus * prod_rate
        # AI: Excess Opening Stock Value (₹) = AA × first-row Closing Landed Rate
        # (XLOOKUP into Opening Stock BB — not the FG-filtered aggregate rate).
        excess_opening_val = excess_opening_stock * opening_first_rate.get(ic, 0)
        # AJ: Build Required = MAX(E + S_gl - J, 0)
        build_required = max(committed_forecast + green_level - opening_inventory, 0)
        # AK: Production Counted = MIN(K, AJ)
        production_counted = min(actual_production, build_required) if build_required > 0 else 0
        # AL: Production-Driven Shortfall (₹) = Y × ASP
        prod_shortfall_val = prod_driven_shortfall * asp
        # AM: Dispatch Gap (₹) = V × ASP
        dispatch_gap_val = dispatch_gap * asp
        # AN: Shortfall on Additional Demand (₹) = W × ASP
        shortfall_additional_val = shortfall_additional * asp
        # AO: Demand Reduction Adjustment (₹) = X × ASP
        demand_reduction_val = demand_reduction * asp
        # AP: Excess Dispatch Value (₹) = AB × ASP
        excess_dispatch_val = excess_dispatched * asp

        # AQ: Excess Dispatched from Op Stock = MIN(AB, MAX(J - G, 0))
        excess_from_opstock = min(excess_dispatched, max(opening_inventory - actual_sales_demand, 0))
        # AR: Excess Dispatch from Surplus Production = AB - AQ
        excess_from_surplus = excess_dispatched - excess_from_opstock
        # AS: Excess Dispatch from Op Stock Value (₹) = AQ × ASP
        excess_from_opstock_val = excess_from_opstock * asp
        # AT: Excess Dispatch from Surplus Production Value (₹) = AR × ASP
        excess_from_surplus_val = excess_from_surplus * asp

        # ── Assemble output row ──
        result.append({
            "item_group": item_group,
            "item_code": ic,
            "product_class": product_class,
            "original_forecast": _fmt(original_forecast),
            "committed_forecast": _fmt(committed_forecast),
            "ops_adjustment": _fmt(ops_adjustment),
            "actual_sales_demand": _fmt(actual_sales_demand),
            "additional_demand": _fmt(additional_demand),
            "forecast_accuracy_pct": forecast_accuracy_pct,
            "opening_inventory": _fmt(opening_inventory),
            "actual_production": _fmt(actual_production),
            "stock_adj_added": _fmt(stock_adj_added),
            "stock_adj_deducted": _fmt(stock_adj_deducted),
            "total_available": _fmt(total_available),
            "type_mts_mto": type_mts_mto,
            "actual_dispatch": _fmt(actual_dispatch),
            "dispatch_pct": dispatch_pct,
            "closing_inventory": _fmt(closing_inventory, blank_zero=False),
            "green_level": _fmt(green_level),
            "free_inventory": _fmt(free_inventory),
            "uncovered_shortfall": _fmt(uncovered_shortfall),
            "dispatch_gap": _fmt(dispatch_gap),
            "shortfall_additional_demand": _fmt(shortfall_additional),
            "demand_reduction_adj": _fmt(demand_reduction),
            "prod_driven_shortfall": _fmt(prod_driven_shortfall),
            "production_surplus": _fmt(production_surplus),
            "excess_opening_stock": _fmt(excess_opening_stock),
            "excess_dispatched": _fmt(excess_dispatched),
            "sales_insight_tag": sales_tag,
            "sales_narrative": sales_narrative,
            "ops_insight_tag": ops_tag,
            "ops_narrative": ops_narrative,
            "ops_capacity_narrative": ops_cap_narrative,
            "surplus_production_val": _fmt(surplus_production_val),
            "excess_opening_stock_val": _fmt(excess_opening_val),
            "build_required": _fmt(build_required),
            "production_counted": _fmt(production_counted),
            "prod_shortfall_val": _fmt(prod_shortfall_val),
            "dispatch_gap_val": _fmt(dispatch_gap_val),
            "shortfall_additional_val": _fmt(shortfall_additional_val),
            "demand_reduction_val": _fmt(demand_reduction_val),
            "excess_dispatch_val": _fmt(excess_dispatch_val),
            "excess_dispatch_from_opstock": _fmt(excess_from_opstock),
            "excess_dispatch_from_surplus": _fmt(excess_from_surplus),
            "excess_dispatch_opstock_val": _fmt(excess_from_opstock_val),
            "excess_dispatch_surplus_val": _fmt(excess_from_surplus_val),
        })

    log.info("Append1: computed %d item rows", len(result))
    return result


# ── Column headers matching the Google Sheet Append1 tab ────────────────
APPEND1_HEADERS = [
    "Item Group",
    "Item Code",
    "Product Class",
    "Original Forecast",
    "Ops+Sales-Reviewed Forecast Committed",
    "Ops Adjustment (vs Forecast)",
    "Actual Sales Demand",
    "Additional Demand (Punched, Not Committed)",
    "Forecast Accuracy %",
    "Opening Inventory",
    "Actual Production",
    "Stock Adjustment (Added)",
    "Stock Adjustment (Deducted)",
    "Total Available Inventory",
    "Type (MTS/MTO)",
    "Actual Dispatch",
    "Dispatch %",
    "Closing Inventory",
    "Green Level",
    "Free Inventory (Above Green Level)",
    "Uncovered Shortfall",
    "Dispatch Gap (Shippable from Stock)",
    "Shortfall on Additional Demand (Excluded from Ops)",
    "Demand Reduction Adjustment (Sales Pullback)",
    "Production-Driven Shortfall",
    "Production Surplus",
    "Excess Opening Stock (Above Demand+Safety)",
    "Excess Dispatched",
    "Sales Insight Tag",
    "Sales Narrative",
    "Operations Insight Tag",
    "Operations Narrative",
    "Ops Capacity Gap Narrative",
    "Surplus Production (₹)",
    "Excess Opening Stock Value (₹)",
    "Build Required",
    "Production Counted",
    "Production-Driven Shortfall (₹)",
    "Dispatch Gap (Shippable from Stock) (₹)",
    "Shortfall on Additional Demand (₹)",
    "Demand Reduction Adjustment (₹)",
    "Excess Dispatch Value (₹)",
    "Excess Dispatched from Op Stock",
    "Excess Dispatch from Surplus Production",
    "Excess Dispatch from Op Stock Value (₹)",
    "Excess Dispatch from Surplus Production Value (₹)",
]

# Maps dict key → position in APPEND1_HEADERS
_KEY_ORDER = [
    "item_group",
    "item_code",
    "product_class",
    "original_forecast",
    "committed_forecast",
    "ops_adjustment",
    "actual_sales_demand",
    "additional_demand",
    "forecast_accuracy_pct",
    "opening_inventory",
    "actual_production",
    "stock_adj_added",
    "stock_adj_deducted",
    "total_available",
    "type_mts_mto",
    "actual_dispatch",
    "dispatch_pct",
    "closing_inventory",
    "green_level",
    "free_inventory",
    "uncovered_shortfall",
    "dispatch_gap",
    "shortfall_additional_demand",
    "demand_reduction_adj",
    "prod_driven_shortfall",
    "production_surplus",
    "excess_opening_stock",
    "excess_dispatched",
    "sales_insight_tag",
    "sales_narrative",
    "ops_insight_tag",
    "ops_narrative",
    "ops_capacity_narrative",
    "surplus_production_val",
    "excess_opening_stock_val",
    "build_required",
    "production_counted",
    "prod_shortfall_val",
    "dispatch_gap_val",
    "shortfall_additional_val",
    "demand_reduction_val",
    "excess_dispatch_val",
    "excess_dispatch_from_opstock",
    "excess_dispatch_from_surplus",
    "excess_dispatch_opstock_val",
    "excess_dispatch_surplus_val",
]
