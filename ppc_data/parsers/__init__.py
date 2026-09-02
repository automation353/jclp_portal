"""Parsers for PPC Excel files.

Each parser module exports a ``parse(file_path)`` function that returns
a list of dicts keyed by stable field keys. The base module provides
shared utilities (cell cleaning, header detection, etc.).

Import the registry via ``from ppc_data.parsers import PARSERS``.

Tables without parsers (UI-form-only):
  - site_plant_section (W1.3)  — admin / API CRUD
  - working_calendar   (W1.10) — admin / API CRUD
  - packing_spec       (W1.15) — must be built from scratch
  - reason_codes       (W1.17) — admin / API CRUD
"""

from . import (
    asp_fg,
    bom_template,
    customer_part_file,
    dispatch_trends,
    family_hierarchy,
    forecast_demand,
    green_levels,
    lead_time_data,
    machine_loading,
    monitoring_ebq,
    mps_history_file,
    mps_schedule_file,
    part_engineering_file,
    planning_calendar_file,
    process_file,
    product_group_mapping,
    production_targets,
    r3ss_file,
    rejection_stages,
)
from .erp_generic import ERP_PARSERS
from . import sop_generic

# Registry: table_key -> parser module
PARSERS = {
    # L0 foundation masters (13 file-based)
    product_group_mapping.TABLE_KEY:  product_group_mapping,   # item_master
    bom_template.TABLE_KEY:           bom_template,            # bom_master
    family_hierarchy.TABLE_KEY:       family_hierarchy,         # family_hierarchy
    process_file.TABLE_KEY:           process_file,             # route_master
    rejection_stages.TABLE_KEY:       rejection_stages,         # operation_stage_map
    production_targets.TABLE_KEY:     production_targets,       # capacity_ppp
    machine_loading.TABLE_KEY:        machine_loading,          # machine_master
    monitoring_ebq.TABLE_KEY:         monitoring_ebq,           # batch_ebq
    lead_time_data.TABLE_KEY:         lead_time_data,           # lead_time
    part_engineering_file.TABLE_KEY:  part_engineering_file,     # part_engineering
    customer_part_file.TABLE_KEY:     customer_part_file,       # customer_part
    green_levels.TABLE_KEY:           green_levels,             # stock_policy
    asp_fg.TABLE_KEY:                 asp_fg,                   # rate_asp

    # L2 demand
    forecast_demand.TABLE_KEY:        forecast_demand,           # demand_freeze
    dispatch_trends.TABLE_KEY:        dispatch_trends,           # demand_history

    # L3 MPS
    mps_schedule_file.TABLE_KEY:      mps_schedule_file,         # mps_schedule
    mps_history_file.TABLE_KEY:       mps_history_file,          # mps_history
    planning_calendar_file.TABLE_KEY: planning_calendar_file,    # planning_calendar

    # L4 R3SS plan (dynamic date columns)
    r3ss_file.TABLE_KEY:              r3ss_file,                  # r3ss_plan
    "r3ss_summary":                   r3ss_file,                  # r3ss_summary (uses parse_summary)
}

# L1 — ERP reports (manual upload via generic parser, same field maps as erp-landing)
PARSERS.update(ERP_PARSERS)

# ── S&OP uploads (generic passthrough parser) ──────────────────────
for _sop_key in sop_generic.SOP_TABLE_KEYS:
    PARSERS[_sop_key] = sop_generic
