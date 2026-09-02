from django.urls import path

from . import api, api_demand, api_feasibility, api_material, api_mps, api_production, api_r3ss

urlpatterns = [
    # L0 — Master upload screen
    path("upload/", api.upload, name="ppc_data_upload"),
    path("uploads/", api.list_uploads, name="ppc_data_list_uploads"),
    # Table data retrieval (all levels)
    path("table/<slug:table_key>/", api.table_data, name="ppc_data_table"),
    # L1 — ERP landing (n8n → Django)
    path("erp-landing/", api.erp_landing, name="ppc_data_erp_landing"),
    # Feed status (admin monitoring)
    path("feed-status/", api.feed_status, name="ppc_data_feed_status"),

    # L2 — Demand freeze & transactions
    path("demand/freeze/", api_demand.demand_freeze, name="ppc_data_demand_freeze"),
    path("demand/transaction/", api_demand.demand_transaction, name="ppc_data_demand_tx"),
    path("demand/current/", api_demand.demand_current, name="ppc_data_demand_current"),
    path("demand/months/", api_demand.demand_months, name="ppc_data_demand_months"),

    # L3 — MPS schedule & history
    path("mps/upload/", api_mps.mps_upload, name="ppc_data_mps_upload"),
    path("mps/current/", api_mps.mps_current, name="ppc_data_mps_current"),
    path("mps/summary/", api_mps.mps_summary, name="ppc_data_mps_summary"),

    # L4 — R3SS plan (THE deliverable)
    path("r3ss/upload/", api_r3ss.r3ss_upload, name="ppc_data_r3ss_upload"),
    path("r3ss/current/", api_r3ss.r3ss_current, name="ppc_data_r3ss_current"),
    path("r3ss/summary/", api_r3ss.r3ss_summary, name="ppc_data_r3ss_summary"),
    path("r3ss/day/<str:date>/", api_r3ss.r3ss_day, name="ppc_data_r3ss_day"),

    # L5 — Feasibility gate (Rule 5: capacity is a gate)
    path("feasibility/run/", api_feasibility.feasibility_run, name="ppc_data_feasibility_run"),
    path("feasibility/status/", api_feasibility.feasibility_status, name="ppc_data_feasibility_status"),
    path("feasibility/resolve/", api_feasibility.feasibility_resolve, name="ppc_data_feasibility_resolve"),
    path("feasibility/approve/", api_feasibility.feasibility_approve, name="ppc_data_feasibility_approve"),

    # L6 — Release (immutable snapshot)
    path("release/create/", api_feasibility.release_create, name="ppc_data_release_create"),
    path("release/list/", api_feasibility.release_list, name="ppc_data_release_list"),
    path("release/<int:release_id>/", api_feasibility.release_detail, name="ppc_data_release_detail"),
    path("release/<int:release_id>/recall/", api_feasibility.release_recall, name="ppc_data_release_recall"),

    # L7 — Material (BOM explosion + stock allocation)
    path("material/explode/", api_material.material_explode, name="ppc_data_material_explode"),
    path("material/allocate/", api_material.material_allocate, name="ppc_data_material_allocate"),
    path("material/status/", api_material.material_status, name="ppc_data_material_status"),
    path("material/shortages/", api_material.material_shortages, name="ppc_data_material_shortages"),
    path("material/sheet-sync/", api_material.material_sheet_sync, name="ppc_data_material_sheet_sync"),

    # L8 — Production entry & feedback
    path("production/entry/", api_production.production_entry, name="ppc_data_production_entry"),
    path("production/bulk/", api_production.production_bulk_entry, name="ppc_data_production_bulk"),
    path("production/entries/", api_production.production_entries, name="ppc_data_production_entries"),
    path("production/adherence/", api_production.production_adherence, name="ppc_data_production_adherence"),
    path("production/rejection/", api_production.rejection_entry, name="ppc_data_rejection_entry"),
    path("production/rejections/", api_production.rejection_list, name="ppc_data_rejection_list"),
    path("production/scorecard/", api_production.production_scorecard, name="ppc_data_production_scorecard"),
]
