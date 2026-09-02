"""Control 5 — "We paid an advance — did the material ever come?"

Spec §Control 5. The control with the largest single cash consequence and
the least available data.

WHAT THIS CONTROL CAN AND CANNOT SAY — read this before trusting a number.

The spec asks for three feeds: the vendor ledger (the advances themselves),
the goods receipt register, and the PO register. Only the third exists. So:

* We CAN identify every PO written on ADVANCE payment terms, the advance
  percentage those terms specify, how much has been received against each,
  and how long each has been outstanding. That is a real, aged, per-vendor
  exposure list, and it did not exist anywhere before.
* We CANNOT confirm that any money actually left JCPL. "Advance terms" is
  not "advance paid" — only the vendor ledger proves payment. Every figure
  here is therefore EXPOSURE AT RISK, never confirmed unrecovered cash, and
  the board says so on its face.
* Two of the spec's seven verdicts are not computable at all and report as
  NOT CHECKABLE rather than as zero: an advance with no PO behind it (we
  start FROM POs, so a PO-less advance is invisible by construction), and
  vendors carrying both a debit and a credit balance.

The GRN columns in the source are present but entirely zero, so receipt is
read from `Next Transaction Qty` — the quantity already taken in against
the PO, which is the same thing under a different name (Next Transaction
Name reads "GIN" on every line).
"""

import datetime
import re

from purchase_dashboards.field_map import num, rupees_in, txt

CONTROL_KEY = "c5"
TITLE = "Control 5 — Advance paid, did material arrive?"
JCPL_WORDING = (
    "Look at money paid to a vendor in advance. Has the lead time passed? "
    "Has any material been received against it?"
)

EPOCH = datetime.date(1899, 12, 30)
RECOVERY_MULTIPLE = 2      # spec: RECOVERY RISK at twice the lead time
DEFAULT_LEAD_DAYS = 30     # used only where the item carries no lead time

LINE_COLS = [
    {"key": "po_number", "label": "PO number"},
    {"key": "po_date", "label": "PO date"},
    {"key": "vendor", "label": "Vendor"},
    {"key": "item_code", "label": "Item Code"},
    {"key": "item_description", "label": "Description"},
    {"key": "category", "label": "Category"},
    {"key": "advance_pct", "label": "Advance %", "numeric": True},
    {"key": "net_amount", "label": "PO value", "numeric": True, "rupees": True},
    {"key": "exposure", "label": "Advance exposure", "numeric": True, "rupees": True},
    {"key": "ordered_qty", "label": "Ordered", "numeric": True},
    {"key": "received_qty", "label": "Received", "numeric": True},
    {"key": "age_days", "label": "Age (days)", "numeric": True},
    {"key": "lead_days", "label": "Lead time", "numeric": True},
    {"key": "verdict", "label": "Verdict", "pill": "verdict"},
    {"key": "action", "label": "Action"},
]

ACTIONS = {
    "WITHIN LEAD TIME":         "Normal — monitor",
    "OVERDUE — NOTHING RECEIVED": "Chase the vendor, the clock has expired",
    "RECOVERY RISK":            "Formal recovery notice — escalate to CFO",
    "PART RECEIVED":            "Advance partly justified — track the balance",
    "ADVANCE ON DEAD STOCK":    "Cash paid forward for material that is not turning — escalate",
    "FULLY RECEIVED":           "Closed — material arrived",
}

_PCT = re.compile(r"(\d{1,3})\s*%\s*ADVANCE|ADVANCE[^0-9]{0,12}(\d{1,3})\s*%")


def advance_pct(term):
    """The advance percentage the payment term specifies, or None if the term
    is not an advance term at all. '100% Advance Against Proforma Invoice'
    -> 100; '30% Advance Balance Against PI' -> 30."""
    t = txt(term).upper()
    if "ADVANCE" not in t:
        return None
    m = _PCT.search(t)
    if m:
        pct = m.group(1) or m.group(2)
        try:
            v = int(pct)
            if 0 < v <= 100:
                return v
        except (TypeError, ValueError):
            pass
    # An advance term whose percentage we cannot parse — treat as 100% and
    # flag it, rather than silently valuing the exposure at zero.
    return 100


def _serial_to_date(v):
    n = num(v)
    if n is None:
        return None
    try:
        return EPOCH + datetime.timedelta(days=int(n))
    except (ValueError, OverflowError):
        return None


def compute(rows, meta=None):
    meta = meta or {}
    po_lines = meta.get("po_lines") or []
    today = datetime.date.today()

    # Item-level context from the combined snapshot: category (for ADVANCE ON
    # DEAD STOCK) and lead time (for the ageing thresholds).
    ctx = {}
    for r in rows:
        d = r["data"]
        for key in (txt(d.get("tally_code")), txt(d.get("rm_code"))):
            if key and key.lower() != "item code required" and key != "0":
                ctx.setdefault(key, {
                    "category": txt(d.get("category")),
                    "lead": num(d.get("lead_time_days")) or 0,
                })

    feed_present = bool(po_lines)
    lines = []
    unparsed_pct = 0

    for pl in po_lines:
        d = pl["data"] if isinstance(pl, dict) else pl.data
        pct = advance_pct(d.get("credit_term"))
        if pct is None:
            continue  # not an advance-terms PO — outside this control

        code = txt(d.get("item_code"))
        c = ctx.get(code) or ctx.get(txt(d.get("item_name"))) or {}
        lead = c.get("lead") or DEFAULT_LEAD_DAYS
        po_date = _serial_to_date(d.get("po_date"))
        age = (today - po_date).days if po_date else None

        ordered = num(d.get("ordered_qty")) or 0
        received = num(d.get("received_qty")) or 0
        net = num(d.get("net_amount")) or 0
        exposure = net * pct / 100.0
        category = c.get("category", "")

        if received >= ordered > 0:
            verdict = "FULLY RECEIVED"
        elif received > 0:
            verdict = "PART RECEIVED"
        elif category in ("Non Moving", "Slow Moving"):
            verdict = "ADVANCE ON DEAD STOCK"
        elif age is not None and age > lead * RECOVERY_MULTIPLE:
            verdict = "RECOVERY RISK"
        elif age is not None and age > lead:
            verdict = "OVERDUE — NOTHING RECEIVED"
        else:
            verdict = "WITHIN LEAD TIME"

        if "ADVANCE" in txt(d.get("credit_term")).upper() and not _PCT.search(
                txt(d.get("credit_term")).upper()):
            unparsed_pct += 1

        lines.append({
            "po_number": txt(d.get("po_number")),
            "po_date": po_date.isoformat() if po_date else "",
            "vendor": txt(d.get("vendor")),
            "item_code": code,
            "item_description": txt(d.get("item_description")),
            "category": category or "—",
            "advance_pct": pct,
            "net_amount": net,
            "exposure": round(exposure, 2),
            "ordered_qty": ordered,
            "received_qty": received,
            "age_days": age,
            "lead_days": lead,
            "verdict": verdict,
            "action": ACTIONS.get(verdict, ""),
        })

    def by(*v): return [x for x in lines if x["verdict"] in v]
    def exp(b): return sum(x["exposure"] for x in b)

    nothing = by("OVERDUE — NOTHING RECEIVED", "RECOVERY RISK", "ADVANCE ON DEAD STOCK", "WITHIN LEAD TIME")
    at_risk = by("OVERDUE — NOTHING RECEIVED", "RECOVERY RISK", "ADVANCE ON DEAD STOCK")

    vendors = {}
    for x in at_risk:
        vendors.setdefault(x["vendor"], {"lines": 0, "exposure": 0.0})
        vendors[x["vendor"]]["lines"] += 1
        vendors[x["vendor"]]["exposure"] += x["exposure"]
    worst = max(vendors.items(), key=lambda kv: kv[1]["exposure"], default=None)

    tiles = {
        "feed_status": {
            "label": "Feed status",
            "value": "PARTIAL" if feed_present else "BLOCKED",
            "sub": (
                "PO register only. Advance TERMS are identifiable, but actual PAYMENTS are "
                "not — the vendor ledger is absent, so nothing here is confirmed cash out. "
                "Every figure is EXPOSURE AT RISK. The GRN register is also absent; receipt "
                "is read from the PO's own GIN quantity instead."
                if feed_present else
                "No PO snapshot available — run manage.py fetch_po_tab."
            ),
            "kind": "warn" if feed_present else "critical",
        },
        "advance_population": {
            "label": "PO lines on advance terms",
            "value": len(lines),
            "sub": f"{rupees_in(exp(lines))} of advance exposure across every advance-terms PO line",
            "kind": "info",
        },
        "exposure_at_risk": {
            "label": "Exposure at risk",
            "value": rupees_in(exp(at_risk)),
            "sub": f"{len(at_risk)} lines on advance terms with NOTHING received and the clock expired",
            "kind": "critical",
            "indicative": True,
        },
        "overdue_nothing": {
            "label": "OVERDUE — NOTHING RECEIVED",
            "value": len(by("OVERDUE — NOTHING RECEIVED")),
            "sub": "Past the item's lead time with no receipt — chase the vendor",
            "kind": "critical",
        },
        "recovery_risk": {
            "label": "RECOVERY RISK",
            "value": len(by("RECOVERY RISK")),
            "sub": f"More than {RECOVERY_MULTIPLE}x the lead time with nothing received — formal recovery",
            "kind": "critical",
        },
        "advance_on_dead": {
            "label": "ADVANCE ON DEAD STOCK",
            "value": len(by("ADVANCE ON DEAD STOCK")),
            "sub": "Cash committed forward for material the sheet says is not turning",
            "kind": "critical",
        },
        "part_received": {
            "label": "PART RECEIVED",
            "value": len(by("PART RECEIVED")),
            "sub": "Advance partly justified — track the balance",
            "kind": "warn",
        },
        "within_lead": {
            "label": "WITHIN LEAD TIME",
            "value": len(by("WITHIN LEAD TIME")),
            "sub": "Normal — the clock has not expired yet",
            "kind": "score",
        },
        "worst_vendor": {
            "label": "Largest single exposure",
            "value": rupees_in(worst[1]["exposure"]) if worst else "—",
            "sub": (f"{worst[0]} — {worst[1]['lines']} lines at risk" if worst
                    else "no exposure at risk"),
            "kind": "warn",
            "indicative": True,
        },
        "not_checkable": {
            "label": "NOT CHECKABLE without the ledger",
            "value": "2 verdicts",
            "sub": "NO PO BEHIND IT (an advance with no purchase order — invisible here by "
                   "construction, since this control starts from POs) and SET-OFF AVAILABLE "
                   "(a vendor carrying both a debit and a credit balance). Reported as "
                   "not-checkable, never as zero.",
            "kind": "info",
        },
        "notes": {
            "label": "Open questions & hazards",
            "value": "4 items",
            "sub": (
                "① ADVANCE TERMS IS NOT ADVANCE PAID. These POs specify an advance; only the "
                "vendor ledger proves money left. Treat every rupee here as exposure, not as "
                "unrecovered cash. "
                f"② {unparsed_pct} advance term(s) had no parseable percentage and were valued "
                "at 100% rather than silently at zero. "
                "③ Open Q15: confirm the recovery-risk threshold — twice the lead time is "
                "proposed; JCPL may already have a policy. "
                "④ Open Q17: the mockup refers to a Tally vendor ledger, this build assumes "
                "TCS iON. Confirm which system holds the ledger of record."
            ),
            "kind": "info",
        },
    }

    def srt(b): return sorted(b, key=lambda x: x["exposure"], reverse=True)
    from purchase_dashboards.drill import block, finalise
    tile_rows = {
        "advance_population": block(LINE_COLS, srt(lines)),
        "exposure_at_risk": block(LINE_COLS, srt(at_risk)),
        "overdue_nothing": block(LINE_COLS, srt(by("OVERDUE — NOTHING RECEIVED"))),
        "recovery_risk": block(LINE_COLS, srt(by("RECOVERY RISK"))),
        "advance_on_dead": block(LINE_COLS, srt(by("ADVANCE ON DEAD STOCK"))),
        "part_received": block(LINE_COLS, srt(by("PART RECEIVED"))),
        "within_lead": block(LINE_COLS, srt(by("WITHIN LEAD TIME"))),
        "worst_vendor": block(LINE_COLS, srt([x for x in at_risk
                                              if worst and x["vendor"] == worst[0]])),
    }
    return finalise(tiles, tile_rows)
