"""Field maps for PPC data tables.

Each module exports a FIELD_MAP dict and a TABLE_KEY string.
Import the registry via ``from ppc_data.field_maps import REGISTRY``.

The pattern is identical to purchase_dashboards.field_map — stable keys
on the left, Excel/ERP column headers on the right. Computations read
by stable key; the raw header string is never used outside the parser.
"""

from . import (
    batch_ebq,
    bom_master,
    capacity_ppp,
    customer_part,
    demand_freeze,
    demand_history,
    demand_transaction,
    family_hierarchy,
    item_master,
    lead_time,
    machine_master,
    mps_history,
    mps_schedule,
    operation_stage_map,
    packing_spec,
    part_engineering,
    planning_calendar,
    r3ss_plan,
    r3ss_summary,
    rate_asp,
    reason_codes,
    route_master,
    site_plant_section,
    stock_policy,
    working_calendar,
)

# Central registry: table_key -> {field_map, module}
REGISTRY = {}


def _register(mod):
    REGISTRY[mod.TABLE_KEY] = {
        "field_map": mod.FIELD_MAP,
        "module": mod,
    }


# L0 foundation masters (17 tables)
_register(item_master)              # W1.1
_register(family_hierarchy)         # W1.2
_register(site_plant_section)       # W1.3  (UI form)
_register(route_master)             # W1.4
_register(operation_stage_map)      # W1.5
_register(capacity_ppp)             # W1.6
_register(machine_master)           # W1.7
_register(batch_ebq)                # W1.8
_register(lead_time)                # W1.9
_register(working_calendar)         # W1.10 (UI form)
_register(bom_master)               # W1.11
_register(part_engineering)         # W1.12
_register(customer_part)            # W1.13
_register(stock_policy)             # W1.14
_register(packing_spec)             # W1.15 (build new)
_register(rate_asp)                 # W1.16
_register(reason_codes)             # W1.17 (UI form)

# L2 demand (3 tables)
_register(demand_freeze)            # Initial demand freeze
_register(demand_transaction)       # Additions / reductions
_register(demand_history)           # Historical demand/dispatch

# L3 MPS (3 tables)
_register(mps_schedule)             # THE MPS schedule form
_register(mps_history)              # MPS demand/dispatch history
_register(planning_calendar)        # Week start dates per month

# L4 R3SS plan (2 tables) — Rule 1: One Plan Table
_register(r3ss_plan)                # Day-wise production plan (dynamic date cols)
_register(r3ss_summary)             # FG stock level summary by family
