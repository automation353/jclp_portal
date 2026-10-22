import datetime as dt
import io
import logging
import json
import tempfile
import time

import pandas as pd
from django.contrib import messages
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from . import services
from .engine import calc
from .models import ActivityLog, ManualGRN, RefreshRun


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def current_as_on(request) -> dt.date:
    """Every sheet is calculated as on today (the workbook's TODAY())."""
    return timezone.localdate()


def _ctx(request, active, **extra):
    as_on = current_as_on(request)
    return {"active": active, "as_on": as_on, **extra}


def _no_data(request, active):
    return render(request, "nongrn/no_data.html", _ctx(request, active))


def parse_date(value) -> dt.date | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, (int, float)) and not pd.isna(value):
        return (dt.datetime(1899, 12, 30) + dt.timedelta(days=float(value))).date()
    s = str(value).strip()
    if not s:
        return None
    if s.replace(".", "", 1).isdigit():
        return parse_date(float(s))
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%d-%b-%Y", "%d-%b-%y", "%d/%m/%y",
                "%d %b %Y", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


# --------------------------------------------------------------------------
# pages
# --------------------------------------------------------------------------
def home(request):
    return redirect("nongrn:report")


def report(request):
    wb = services.get_workbook(current_as_on(request))
    if wb is None:
        return _no_data(request, "report")
    return render(request, "nongrn/report.html", _ctx(request, "report", r=wb.report, wb=wb))


DASH_FILTERS = {
    # pivot -> {param: column}
    "trend": {"pg": "Party Group"},                               # PT_Cust_Trend page fields
    "bucket": {"bkt": "Current Bucket"},                                         # slicer (any number of buckets)
    "grn": {},                                                      # PT_Cust_GRN page field
}


def dashboard(request):
    wb = services.get_workbook(current_as_on(request))
    if wb is None:
        return _no_data(request, "dashboard")
    ar = wb.ar
    options = {
        "Site": sorted(ar["Site"].dropna().unique(), key=str.casefold),
        "Party Group": sorted(ar["Party Group"].dropna().unique(), key=str.casefold),
        "GRN Source": sorted(ar["GRN Source"].dropna().unique()),
        "Current Bucket": sorted(ar["Current Bucket"].dropna().unique()),
    }

    def filters_for(pivot):
        out, ui = {}, []
        for param, col in DASH_FILTERS[pivot].items():
            chosen = [v for v in request.GET.getlist(f"{pivot}_{param}") if v in options[col]]
            out[col] = chosen or None
            ui.append({"param": f"{pivot}_{param}", "label": col, "options": options[col], "chosen": chosen})
        return out, ui

    f_trend, ui_trend = filters_for("trend")
    f_bucket, ui_bucket = filters_for("bucket")
    f_grn, ui_grn = filters_for("grn")
    ctx = _ctx(
        request, "dashboard", wb=wb,
        p_bucket=calc.pivot_bucket(ar, f_bucket), ui_bucket=ui_bucket,
        p_trend=calc.pivot_trend(ar, wb.fy, f_trend), ui_trend=ui_trend,
        p_grn=calc.pivot_grn_source(ar, f_grn), ui_grn=ui_grn,
        p_days=calc.pivot_days(ar, {}),
        query=request.GET,
    )
    return render(request, "nongrn/dashboard.html", ctx)


def grid(request, key):
    sheet = services.get_sheet_def(key)
    if not sheet or sheet["kind"] != "grid":
        raise Http404
    wb = services.get_workbook(current_as_on(request))
    if wb is None:
        return _no_data(request, key)
    _, cols = services.grid_frame(wb, key)
    return render(request, "nongrn/grid.html", _ctx(request, key, sheet=sheet, columns=cols))


@require_GET
def grid_data(request, key):
    sheet = services.get_sheet_def(key)
    if not sheet or sheet["kind"] != "grid":
        raise Http404
    wb = services.get_workbook(current_as_on(request))
    if wb is None:
        return JsonResponse({"error": "No data – run Refresh All first."}, status=409)
    filters = {}
    for k, v in request.GET.items():
        if k.startswith("f") and k[1:].isdigit() and v:
            filters[int(k[1:])] = v
    sort = request.GET.get("sort")
    data = services.query_grid(
        wb, key,
        q=request.GET.get("q", "").strip(),
        filters=filters,
        sort=int(sort) if sort not in (None, "") else None,
        desc=request.GET.get("desc") == "1",
        page=int(request.GET.get("page", 1) or 1),
        size=min(int(request.GET.get("size", 100) or 100), 1000),
    )
    return JsonResponse(data)


# --------------------------------------------------------------------------
# Manual GRN (the editable sheet)
# --------------------------------------------------------------------------
def manual_grn(request):
    rows = list(ManualGRN.objects.order_by("id").values("invoice_no", "grn_date", "updated_at",
                                                        "updated_by__username"))
    for r in rows:
        r["grn_date"] = r["grn_date"].isoformat()
        r["updated_at"] = timezone.localtime(r["updated_at"]).strftime("%d-%m-%Y %H:%M")
    return render(request, "nongrn/manual_grn.html",
                  _ctx(request, "manual-grn", rows_json=json.dumps(rows),
                       has_data=services.get_tables() is not None))


def _invoice_info(wb, invoices):
    if wb is None or not invoices:
        return {}
    sr, ar = wb.tables["sr_current"], wb.ar
    sel = sr["Invoice No"].isin(invoices)
    if not sel.any():
        return {}
    df = pd.DataFrame({
        "inv": sr.loc[sel, "Invoice No"],
        "cust": sr.loc[sel, "Customer Name"],
        "date": pd.to_datetime(sr.loc[sel, "Invoice Date"]),
        "erp": pd.to_datetime(sr.loc[sel, "Goods Received Date"]),
        "receipt": sr.loc[sel, "Receipt Status"],
        "amt": pd.to_numeric(sr.loc[sel, "Item Net Amount"], errors="coerce").fillna(0),
        "src": ar.loc[sel, "GRN Source"],
        "cur": ar.loc[sel, "Current Non-GRN Amt"],
    })
    out = {}
    for inv, g in df.groupby("inv", sort=False):
        first = g.iloc[0]
        out[inv] = {
            "customer": first["cust"],
            "inv_date": first["date"].strftime("%d-%m-%Y") if pd.notna(first["date"]) else "",
            "erp_grn": first["erp"].strftime("%d-%m-%Y") if pd.notna(first["erp"]) else "",
            "receipt": first["receipt"] or "",
            "amount": float(g["amt"].sum()),
            "lines": int(len(g)),
            "source": first["src"],
            "current": float(g["cur"].sum()),
        }
    return out


@transaction.atomic
def _save_manual_rows(rows, user):
    errors, cleaned, seen = [], [], {}
    for i, r in enumerate(rows, start=2):  # sheet row numbers (row 1 = header)
        inv = str(r.get("invoice_no") or "").strip()
        raw_date = r.get("grn_date")
        if not inv and not raw_date:
            continue
        d = parse_date(raw_date)
        if not inv:
            errors.append(f"Row {i}: Invoice Number is empty.")
        if d is None:
            errors.append(f"Row {i}: GRN Date '{raw_date}' is not a valid date.")
        if inv in seen:
            errors.append(f"Row {i}: Invoice {inv} already entered on row {seen[inv]} (XLOOKUP would only use the first).")
        seen.setdefault(inv, i)
        cleaned.append((inv, d))
    if errors:
        return errors
    now = timezone.now()
    ManualGRN.objects.all().delete()
    ManualGRN.objects.bulk_create([
        ManualGRN(invoice_no=inv, grn_date=d, updated_at=now, updated_by=user if user.is_authenticated else None)
        for inv, d in cleaned
    ])
    return []


def manual_grn_api(request):
    if request.method == "POST":
        try:
            payload = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "errors": ["Invalid JSON"]}, status=400)
        errors = _save_manual_rows(payload.get("rows", []), request.user)
        if errors:
            return JsonResponse({"ok": False, "errors": errors}, status=400)
        return JsonResponse({"ok": True, "count": ManualGRN.objects.count()})
    rows = [{"invoice_no": m.invoice_no, "grn_date": m.grn_date.isoformat()} for m in ManualGRN.objects.order_by("id")]
    return JsonResponse({"rows": rows})


@require_POST
def manual_grn_lookup(request):
    """Context for the Manual GRN grid: what each invoice looks like in Combine,
    plus the open invoices that still have no GRN (candidates to enter)."""
    payload = json.loads(request.body or b"{}")
    wb = services.get_workbook(current_as_on(request))
    info = _invoice_info(wb, [str(i).strip() for i in payload.get("invoices", []) if i])
    candidates = []
    if wb is not None:
        q = str(payload.get("q", "")).strip().lower()
        ar = wb.ar
        open_ = ar[(ar["Current Non-GRN Amt"] != 0) & ar["GRN Source"].isin(["4. Not Received", "3. Assumed Inv+30"])]
        g = open_.groupby("Invoice No.", sort=False).agg(
            customer=("Customer Name", "first"), inv_date=("Inv Date", "first"),
            amount=("Current Non-GRN Amt", "sum"), age=("Current Age Days", "max"), source=("GRN Source", "first"))
        if q:
            g = g[g.index.str.lower().str.contains(q, regex=False) | g["customer"].str.lower().str.contains(q, regex=False)]
        g = g.sort_values("age", ascending=False).head(200)
        candidates = [{"invoice_no": inv, "customer": r.customer,
                       "inv_date": r.inv_date.strftime("%d-%m-%Y") if pd.notna(r.inv_date) else "",
                       "amount": float(r.amount), "age": int(r.age), "source": r.source}
                      for inv, r in g.iterrows()]
    return JsonResponse({"info": info, "candidates": candidates})


@require_POST
def manual_grn_import(request):
    f = request.FILES.get("file")
    if not f:
        return JsonResponse({"ok": False, "errors": ["No file uploaded"]}, status=400)
    name = f.name.lower()
    try:
        if name.endswith(".csv"):
            df = pd.read_csv(f, header=None, dtype=str)
        else:
            df = pd.read_excel(f, header=None, engine="calamine")
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"ok": False, "errors": [f"Could not read file: {exc}"]}, status=400)
    rows = []
    for _, r in df.iterrows():
        inv = "" if pd.isna(r.iloc[0]) else str(r.iloc[0]).strip()
        val = r.iloc[1] if len(r) > 1 else None
        if inv.lower() in ("invoice number", "invoice no", "invoice no."):
            continue  # header row
        d = parse_date(val if not (isinstance(val, float) and pd.isna(val)) else None)
        if inv or d:
            rows.append({"invoice_no": inv, "grn_date": d.isoformat() if d else str(val or "")})
    return JsonResponse({"ok": True, "rows": rows})


# --------------------------------------------------------------------------
# Export
# --------------------------------------------------------------------------
def _excel_value(v):
    if v is None or v is pd.NaT:
        return None
    if isinstance(v, float) and v != v:
        return None
    if isinstance(v, pd.Timestamp):
        return v.to_pydatetime().date() if v == v.normalize() else v.to_pydatetime()
    return v


def export_sheet(request, key, fmt):
    if fmt not in ("xlsx", "csv"):
        raise Http404
    sheet = services.get_sheet_def(key)
    if not sheet:
        raise Http404
    stamp = timezone.localtime().strftime("%Y%m%d-%H%M")
    filename = f"{sheet['title']} {stamp}.{fmt}"
    if key == "manual-grn":
        df = pd.DataFrame(list(ManualGRN.objects.order_by("id").values_list("invoice_no", "grn_date")),
                          columns=["Invoice Number", "GRN Date"])
        headers = list(df.columns)
        df.columns = range(2)
    elif sheet["kind"] == "grid":
        wb = services.get_workbook(current_as_on(request))
        if wb is None:
            raise Http404
        df, cols = services.grid_frame(wb, key)
        headers = [c["name"] for c in cols]
    else:
        raise Http404
    if fmt == "csv":
        buf = io.StringIO()
        out = df.copy()
        out.columns = headers
        out.to_csv(buf, index=False, date_format="%d-%m-%Y")
        resp = HttpResponse(buf.getvalue().encode("utf-8-sig"), content_type="text/csv")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp

    from openpyxl import Workbook as XLWorkbook
    from openpyxl.cell import WriteOnlyCell
    from openpyxl.styles import Font, PatternFill

    xl = XLWorkbook(write_only=True)
    ws = xl.create_sheet(sheet["title"][:31])
    head_fill = PatternFill("solid", fgColor="1F4E78")
    head = []
    for h in headers:
        c = WriteOnlyCell(ws, value=h)
        c.font, c.fill = Font(bold=True, color="FFFFFF"), head_fill
        head.append(c)
    ws.append(head)
    for row in df.itertuples(index=False, name=None):
        ws.append([_excel_value(v) for v in row])
    tmp = tempfile.TemporaryFile()
    xl.save(tmp)
    tmp.seek(0)
    return FileResponse(tmp, as_attachment=True, filename=filename)


# --------------------------------------------------------------------------
# Sources & Refresh All
# --------------------------------------------------------------------------
def sources(request):
    if request.method == "POST":
        ajax = request.headers.get("x-requested-with") == "fetch"
        key = request.POST.get("source")
        folder = services.settings.NONGRN_SOURCES.get(key)
        f = request.FILES.get("file")
        user = request.user.get_username() if request.user.is_authenticated else "anonymous"
        label = services.SOURCE_NAMES.get(key, (key or "",))[0]
        t0 = time.monotonic()
        error = None
        if folder is None or f is None:
            error = "Choose a source folder and a file."
        elif not f.name.lower().endswith((".xlsx", ".xlsm", ".xls")):
            error = "Only Excel files can be added to a source folder."
        if error is None and folder.exists():
            # Excel keeps open workbooks locked: nothing in the folder could be replaced
            locked = services.locked_files(folder)
            if locked:
                error = ("Close this file in Excel first, then upload again: " + ", ".join(locked)
                         + ". Nothing was changed.")
        if error is None:
            target = folder / f.name.replace("/", "_").replace("\\", "_")
            try:
                folder.mkdir(parents=True, exist_ok=True)
                with open(target, "wb") as out:
                    for chunk in f.chunks():
                        out.write(chunk)
            except OSError as exc:
                error = f"Could not save {target.name} in {folder}: {exc.strerror or exc}. Nothing was changed."
        if error:
            services.log_upload(False, user, f.name if f else "(no file)", label, error,
                                size=f.size if f else None, duration=time.monotonic() - t0)
            if ajax:
                return JsonResponse({"ok": False, "stage": "portal", "message": error}, status=400)
            messages.error(request, error)
            return redirect("nongrn:sources")

        try:
            replaced = services.archive_old_sources(folder, keep=target)
            # Refresh All runs in the background while n8n converts the file
            refreshing = services.start_refresh(triggered_by=f"{user} (upload {target.name})", queue=True)
            result = {**services.push_to_n8n(target, folder.name), "replaced": replaced, "refreshing": refreshing}
        except Exception as exc:  # noqa: BLE001 – report it in the popup instead of an HTTP 500 page
            logging.getLogger("nongrn").exception("Upload of %s failed", target.name)
            result = {"ok": False, "message": f"The file was saved, but processing failed: {exc}",
                      "link": "", "replaced": [], "refreshing": services.refresh_running()}
        gone = sorted(set(result.get("replaced") or []) | set(result.get("drive_removed") or []))
        services.log_upload(result["ok"], user, target.name, label,
                            result["message"] + (f". Replaced: {', '.join(gone)}" if gone else ""),
                            size=f.size, link=result.get("link") or "", duration=time.monotonic() - t0)
        if ajax:
            return JsonResponse({**result, "stage": "n8n", "file": target.name, "folder": folder.name},
                                status=200 if result["ok"] else 502)
        if result["ok"]:
            messages.success(request, f"File uploaded: {target.name}. {result['message']} Refresh All started."
                                      + (f" Replaced: {', '.join(replaced)}." if replaced else ""))
        else:
            messages.error(request, f"Failed to upload {target.name} to Google Sheets: {result['message']}")
        return redirect("nongrn:sources")
    logs = ActivityLog.objects.all()
    return render(request, "nongrn/sources.html",
                  _ctx(request, "sources", sources=services.source_listing(), logs=logs[:100],
                       log_count=logs.count(), n_uploads=logs.filter(kind=ActivityLog.UPLOAD).count(),
                       n_refresh=logs.filter(kind=ActivityLog.REFRESH).count()))


@require_POST
def clear_logs(request):
    n, _ = ActivityLog.objects.all().delete()
    messages.success(request, f"Activity log cleared ({n} entr{'y' if n == 1 else 'ies'} removed).")
    return redirect("nongrn:sources")


@require_POST
def refresh(request):
    user = request.user.get_username() if request.user.is_authenticated else "anonymous"
    started = services.start_refresh(triggered_by=user)
    if request.headers.get("x-requested-with") == "fetch":
        return JsonResponse({"started": started})
    if started:
        messages.info(request, "Refresh All started – reading the source folders.")
    else:
        messages.warning(request, "A refresh is already running.")
    return redirect(request.POST.get("next") or "nongrn:report")


@require_GET
def refresh_status(request):
    run = RefreshRun.objects.first()
    return JsonResponse({
        "running": services.refresh_running(),
        "last": None if run is None else {
            "status": run.status,
            "started": timezone.localtime(run.started_at).strftime("%d-%m-%Y %H:%M:%S"),
            "finished": timezone.localtime(run.finished_at).strftime("%d-%m-%Y %H:%M:%S") if run.finished_at else None,
            "message": run.message.split("\n\n")[0][:500],
        },
    })


def download_age_workbook(request):
    """The complete Non GRN Age workbook (all sheets, formulas, tables, pivots, queries)."""
    try:
        path = services.build_age_workbook()
    except FileNotFoundError as exc:
        messages.error(request, str(exc))
        return redirect("nongrn:report")
    return FileResponse(open(path, "rb"), as_attachment=True, filename="Non GRN Age.xlsx")
