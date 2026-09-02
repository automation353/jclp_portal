"""Control 6 — "Is this a real item in our books?"

Spec §Control 6. The foundation the other six stand on — every control
joins RM to TCS iON on an item code. Half of it is buildable today, without
any feed at all: absent, zero and placeholder codes, and codes duplicated
across more than one RM row. The other half — whether a present-looking
code actually exists in the books, is active, and matches on UOM/group —
needs the TCS iON stock item master, which does not exist yet. Those rules
report NOT YET CHECKABLE, never a silent pass.

Note on field names: the RM sheet's "Item Name" column is what the brief
calls [RM Code], and its "Item Code" column is what the brief calls
[Tally Code] — see field_map.py. Both are checked here, matching the
brief's own two-code test.
"""

from collections import Counter

from purchase_dashboards.drill import (
    C_GROUP, C_RM, C_SPEC, C_SR, C_TALLY, block, finalise, with_fields,
)
from purchase_dashboards.field_map import is_present_code, txt

CONTROL_KEY = "c6"
TITLE = "Control 6 — Is this a real item in our books?"
JCPL_WORDING = (
    "Take the item code on the row. Does it actually exist in the Tally "
    "item master?"
)

PLACEHOLDERS = {"item code required", "tbd", "n/a", "na"}

LINE_COLS = [
    C_SR, C_TALLY, C_RM, C_SPEC, C_GROUP,
    {"key": "verdict", "label": "Verdict", "pill": "verdict"},
]


def _is_placeholder(v):
    return txt(v).lower() in PLACEHOLDERS


def compute(rows):
    n = len(rows)

    def d(r): return r["data"]

    no_rm_code = [r for r in rows if not is_present_code(d(r).get("rm_code"))]
    no_tally_code = [r for r in rows if not is_present_code(d(r).get("tally_code"))]
    placeholder = [r for r in rows if is_present_code(d(r).get("tally_code"))
                   and _is_placeholder(d(r).get("tally_code"))]
    no_group = [r for r in rows if not txt(d(r).get("group"))]

    # Real, usable tally codes — present, not a placeholder.
    def has_real_code(r):
        v = d(r).get("tally_code")
        return is_present_code(v) and not _is_placeholder(v)

    real_code_rows = [r for r in rows if has_real_code(r)]
    code_counts = Counter(txt(d(r).get("tally_code")) for r in real_code_rows)
    dup_codes = {c for c, cnt in code_counts.items() if cnt > 1}
    duplicate_rows = [r for r in real_code_rows if txt(d(r).get("tally_code")) in dup_codes]

    def verdict_of(r):
        v = d(r).get("tally_code")
        if not is_present_code(v):
            return "NO CODE"
        if _is_placeholder(v):
            return "PLACEHOLDER CODE"
        if txt(v) in dup_codes:
            return "DUPLICATE MAPPING"
        return "NOT YET CONFIRMED — awaiting item master"

    def line(r):
        return dict(with_fields(r), verdict=verdict_of(r))

    all_lines = [line(r) for r in rows]
    join_ready = [x for x in all_lines if x["verdict"] == "NOT YET CONFIRMED — awaiting item master"]
    join_ready_pct = round(100 * len(join_ready) / n, 1) if n else 0

    tiles = {
        "join_readiness": {
            "label": "Join-readiness (today)",
            "value": f"{join_ready_pct}%",
            "sub": f"{len(join_ready)} of {n} rows carry a present, non-placeholder, non-duplicate code — pending item-master confirmation",
            "kind": "score" if join_ready_pct >= 60 else "critical",
        },
        "no_rm_code": {
            "label": "No RM Code",
            "value": len(no_rm_code),
            "sub": f"of {n} — cannot be joined to any other system at all",
            "kind": "critical",
            "brief_target": 102,
        },
        "no_tally_code": {
            "label": "No Tally Code",
            "value": len(no_tally_code),
            "sub": f"of {n} — cannot be reconciled to the books",
            "kind": "critical",
            "brief_target": 25,
        },
        "placeholder_code": {
            "label": "Placeholder code",
            "value": len(placeholder),
            "sub": "\"Item Code Required\" typed into the field that is supposed to be the join key",
            "kind": "critical",
            "brief_target": 53,
        },
        "duplicate_mapping": {
            "label": "Duplicate mapping",
            "value": len(dup_codes),
            "sub": f"distinct Tally Codes shared across {len(duplicate_rows)} RM rows — breaks netting in Controls 1 and 5",
            "kind": "warn",
            "brief_target": 20,
        },
        "distinct_real_codes": {
            "label": "Distinct real Tally Codes",
            "value": len(code_counts),
            "sub": f"across {n} rows — the gap between this and {n} is itself the finding",
            "kind": "info",
            "brief_target": 316,
        },
        "no_group": {
            "label": "No Group recorded",
            "value": len(no_group),
            "sub": "Will fail the stock-group cross-check once the item master arrives",
            "kind": "info",
            "brief_target": 23,
        },
        "not_yet_checkable": {
            "label": "Not yet checkable",
            "value": "4 rules",
            "sub": "CODE NOT IN BOOKS · INACTIVE CODE · UOM MISMATCH · GROUP MISMATCH — needs the TCS iON stock item master, reported as not-checkable, never as a silent pass",
            "kind": "info",
        },
        "notes": {
            "label": "Open questions & hazards",
            "value": "3 items",
            "sub": (
                "① Code formatting (leading zeros, trailing spaces, case) will cause false failures "
                "once the item master arrives — normalise both sides identically before comparing. "
                "② Open Q18: which system holds the item master of record? "
                "③ Open Q20: does TCS iON hold an old-to-new item code mapping that could resolve the "
                "code-mismatch problem automatically?"
            ),
            "kind": "info",
        },
    }

    tile_rows = {
        "no_rm_code": block(
            [C_SR, C_TALLY, C_SPEC, C_GROUP],
            [with_fields(r) for r in no_rm_code],
        ),
        "no_tally_code": block(
            [C_SR, C_RM, C_SPEC, C_GROUP],
            [with_fields(r) for r in no_tally_code],
        ),
        "placeholder_code": block(
            [C_SR, C_TALLY, C_RM, C_SPEC, C_GROUP],
            [with_fields(r) for r in placeholder],
        ),
        "duplicate_mapping": block(
            LINE_COLS, sorted(
                [line(r) for r in duplicate_rows],
                key=lambda x: x["tally_code"],
            ),
        ),
        "no_group": block(
            [C_SR, C_TALLY, C_RM, C_SPEC],
            [with_fields(r) for r in no_group],
        ),
        "join_readiness": block(LINE_COLS, all_lines),
        # not_yet_checkable / notes are static — no row list.
    }

    return finalise(tiles, tile_rows)
