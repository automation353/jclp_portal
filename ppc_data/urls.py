from django.urls import path

from .api import (uploads, dashboard, demand, feasibility, material, mps,
                      production, r3ss, rm_sourcing, wave1_test)

urlpatterns = [
    # L0 — Master upload screen
    path("upload/", uploads.upload, name="ppc_data_upload"),
    path("uploads/", uploads.list_uploads, name="ppc_data_list_uploads"),
    # Table data retrieval (all levels)
    path("table/<slug:table_key>/", uploads.table_data, name="ppc_data_table"),
    # RM Sourcing (RMCP)
    path("rm-sourcing/recompute/", rm_sourcing.rm_recompute, name="ppc_data_rm_recompute"),
    path("rm-sourcing/rm-quantity/", rm_sourcing.rm_quantity, name="ppc_data_rm_quantity"),
    path("rm-sourcing/rm-usage/", rm_sourcing.rm_usage, name="ppc_data_rm_usage"),
    path("rm-sourcing/rm-by-bom/", rm_sourcing.rm_by_bom, name="ppc_data_rm_by_bom"),
    path("rm-sourcing/cp-req/", rm_sourcing.cp_req, name="ppc_data_cp_req"),
    path("rm-sourcing/data-quality/", rm_sourcing.data_quality, name="ppc_data_rm_data_quality"),
    path("rm-sourcing/sheet-tab/", rm_sourcing.sheet_tab, name="ppc_data_rm_sheet_tab"),
    # L1 — ERP landing (n8n → Django)
    path("erp-landing/", uploads.erp_landing, name="ppc_data_erp_landing"),
    # Feed status (admin monitoring)
    path("feed-status/", uploads.feed_status, name="ppc_data_feed_status"),
    # Wave-1 exit test (spec §3.1 — validates master joins)
    path("wave1-test/", wave1_test.wave1_test, name="ppc_data_wave1_test"),

    # L2 — Demand freeze & transactions
    path("demand/freeze/", demand.demand_freeze, name="ppc_data_demand_freeze"),
    path("demand/transaction/", demand.demand_transaction, name="ppc_data_demand_tx"),
    path("demand/current/", demand.demand_current, name="ppc_data_demand_current"),
    path("demand/months/", demand.demand_months, name="ppc_data_demand_months"),
    path("demand/gate/", demand.demand_freeze_gate, name="ppc_data_demand_gate"),
    path("demand/sync-sheet/", demand.demand_sync_sheet, name="ppc_data_demand_sync_sheet"),

    # L3 — MPS schedule, compute & history
    path("mps/upload/", mps.mps_upload, name="ppc_data_mps_upload"),
    path("mps/compute/", mps.mps_compute, name="ppc_data_mps_compute"),
    path("mps/current/", mps.mps_current, name="ppc_data_mps_current"),
    path("mps/summary/", mps.mps_summary, name="ppc_data_mps_summary"),
    path("mps/gate/", mps.mps_gate, name="ppc_data_mps_gate"),

    # L4 — R3SS plan (THE deliverable)
    path("r3ss/upload/", r3ss.r3ss_upload, name="ppc_data_r3ss_upload"),
    path("r3ss/compute/", r3ss.r3ss_compute, name="ppc_data_r3ss_compute"),
    path("r3ss/current/", r3ss.r3ss_current, name="ppc_data_r3ss_current"),
    path("r3ss/from-sheet/", r3ss.r3ss_from_sheet, name="ppc_data_r3ss_from_sheet"),
    path("r3ss/recompute-sheet/", r3ss.r3ss_recompute_sheet, name="ppc_data_r3ss_recompute_sheet"),
    path("r3ss/summary/", r3ss.r3ss_summary, name="ppc_data_r3ss_summary"),
    path("r3ss/day/<str:date>/", r3ss.r3ss_day, name="ppc_data_r3ss_day"),
    path("r3ss/control/", r3ss.r3ss_control, name="ppc_data_r3ss_control"),
    path("r3ss/map/", r3ss.r3ss_map, name="ppc_data_r3ss_map"),

    # L5 — Feasibility gate (Rule 5: capacity is a gate)
    path("feasibility/run/", feasibility.feasibility_run, name="ppc_data_feasibility_run"),
    path("feasibility/status/", feasibility.feasibility_status, name="ppc_data_feasibility_status"),
    path("feasibility/resolve/", feasibility.feasibility_resolve, name="ppc_data_feasibility_resolve"),
    path("feasibility/approve/", feasibility.feasibility_approve, name="ppc_data_feasibility_approve"),

    # L6 — Release (immutable snapshot)
    path("release/create/", feasibility.release_create, name="ppc_data_release_create"),
    path("release/list/", feasibility.release_list, name="ppc_data_release_list"),
    path("release/<int:release_id>/", feasibility.release_detail, name="ppc_data_release_detail"),
    path("release/<int:release_id>/recall/", feasibility.release_recall, name="ppc_data_release_recall"),

    # L7 — Material (BOM explosion + stock allocation)
    path("material/explode/", material.material_explode, name="ppc_data_material_explode"),
    path("material/allocate/", material.material_allocate, name="ppc_data_material_allocate"),
    path("material/status/", material.material_status, name="ppc_data_material_status"),
    path("material/shortages/", material.material_shortages, name="ppc_data_material_shortages"),
    path("material/sheet-sync/", material.material_sheet_sync, name="ppc_data_material_sheet_sync"),

    # L8 — Production entry & feedback
    path("production/entry/", production.production_entry, name="ppc_data_production_entry"),
    path("production/bulk/", production.production_bulk_entry, name="ppc_data_production_bulk"),
    path("production/entries/", production.production_entries, name="ppc_data_production_entries"),
    path("production/adherence/", production.production_adherence, name="ppc_data_production_adherence"),
    path("production/rejection/", production.rejection_entry, name="ppc_data_rejection_entry"),
    path("production/rejections/", production.rejection_list, name="ppc_data_rejection_list"),
    path("production/scorecard/", production.production_scorecard, name="ppc_data_production_scorecard"),

    # L9 — Dashboards (spec §6)
    path("dashboard/capacity/", dashboard.dashboard_capacity, name="ppc_data_dash_capacity"),
    path("dashboard/adherence/", dashboard.dashboard_adherence, name="ppc_data_dash_adherence"),
    path("dashboard/stock/", dashboard.dashboard_stock, name="ppc_data_dash_stock"),
    path("dashboard/shortages/", dashboard.dashboard_shortages, name="ppc_data_dash_shortages"),
    path("dashboard/oee/", dashboard.dashboard_oee, name="ppc_data_dash_oee"),
    path("dashboard/opening/", dashboard.dashboard_opening, name="ppc_data_dash_opening"),
    path("dashboard/refresh/", dashboard.dashboard_refresh, name="ppc_data_dash_refresh"),
    path("dashboard/summary/", dashboard.dashboard_summary, name="ppc_data_dash_summary"),

    # L10 — Parallel run comparison (Phase 11)
    path("parallel-run/", dashboard.parallel_run_compare, name="ppc_data_parallel_run"),
]
