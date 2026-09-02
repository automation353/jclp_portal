"""ERP report field maps — all 17 TCS iON reports.

Each module exports TABLE_KEY, REPORT_NUMBER, FREQUENCY, and FIELD_MAP.
The ERP_REGISTRY drives the landing endpoint, status board, and n8n config.
"""

from . import (
    bom_erp,
    consumables,
    cp_stock,
    dispatch,
    fg_ageing,
    fg_stock,
    forecast,
    item_cost,
    item_master_erp,
    material_issue,
    pending_po,
    pending_pr,
    pm_stock,
    prod_fg,
    prod_semi,
    rm_stock,
    sales_orders,
)

# Central registry: report_key -> module
ERP_REGISTRY = {}

_ALL_MODULES = [
    item_master_erp,    # #1
    bom_erp,            # #2
    fg_stock,           # #3
    cp_stock,           # #4
    rm_stock,           # #5
    pm_stock,           # #6
    consumables,        # #7
    prod_fg,            # #8
    prod_semi,          # #9
    dispatch,           # #10
    forecast,           # #11
    sales_orders,       # #12
    pending_po,         # #13
    pending_pr,         # #14
    material_issue,     # #15
    item_cost,          # #16
    fg_ageing,          # #17
]

for _mod in _ALL_MODULES:
    ERP_REGISTRY[_mod.TABLE_KEY] = {
        "field_map": _mod.FIELD_MAP,
        "report_number": _mod.REPORT_NUMBER,
        "frequency": _mod.FREQUENCY,
        "module": _mod,
    }


def get_erp_field_map(report_key):
    """Return the FIELD_MAP for a given ERP report key, or None."""
    entry = ERP_REGISTRY.get(report_key)
    return entry["field_map"] if entry else None
