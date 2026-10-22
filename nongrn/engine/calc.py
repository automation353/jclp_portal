"""
Worksheet formulas of "Non GRN Age.xlsx" re-implemented with pandas.

Combine!HZ:JX   (table AR_Tax_Register___Detail_Report)  -> combine_formulas()
Report sheet                                              -> build_report()
Customer Dashboard pivots                                 -> pivot_* functions

Every block notes the Excel formula it reproduces.  TODAY() is replaced by
`as_on` so the portal can also show the position as on any past date.
"""
from __future__ import annotations

import calendar
import datetime as dt
from dataclasses import dataclass

import numpy as np
import pandas as pd

AMOUNT_COL = "Item Net Amount"          # Combine!$EB
INV_DATE_COL = "Invoice Date"           # Combine!$C

MONTH_BUCKET_BOUNDS = [0, 1, 16, 31, 61, 91, 181, 366, 999]
MONTH_BUCKET_LABELS = ["NA", "0-15 Days", "16-30 Days", "31-60 Days", "61-90 Days",
                       "91-180 Days", "181-365 Days", "Above 1 Year", "Above 60 Days"]
CURRENT_BUCKET_BOUNDS = [0, 1, 16, 31, 61, 91, 181, 366]
CURRENT_BUCKET_LABELS = ["NA", "1) 0-15 Days", "2) 16-30 Days", "3) 31-60 Days", "4) 61-90 Days",
                         "5) 91-180 Days", "6) 181-365 Days", "7) Above 1 Year"]
REPORT_BUCKETS = MONTH_BUCKET_LABELS[1:]     # Report!B3:B10
GRN_SOURCES = ["1. ERP GRN", "2. Manual GRN", "3. Assumed Inv+30", "4. Not Received"]
LAKH = 100000


@dataclass(frozen=True)
class FiscalYear:
    start_year: int  # 2026 -> FY 26-27

    @property
    def start(self) -> dt.date:
        return dt.date(self.start_year, 4, 1)

    @property
    def end(self) -> dt.date:
        return dt.date(self.start_year + 1, 3, 31)

    @property
    def months(self) -> list[tuple[int, int]]:
        return [(self.start_year + (m < 4), m) for m in (4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2, 3)]

    @property
    def label(self) -> str:
        return f"FY {self.start_year % 100:02d}-{(self.start_year + 1) % 100:02d}"


def month_label(year: int, month: int) -> str:
    return dt.date(year, month, 1).strftime("%b-%y")


def snapshot_dates(fy: FiscalYear, as_on: dt.date) -> list[dt.date]:
    """Combine!IB1:IM1 – month-end dates; the running month uses TODAY()."""
    out = []
    for y, m in fy.months:
        if (y, m) == (as_on.year, as_on.month):
            out.append(as_on)
        else:
            out.append(dt.date(y, m, calendar.monthrange(y, m)[1]))
    return out


def excel_lookup(values: pd.Series, bounds: list[int], labels: list[str]) -> pd.Series:
    """LOOKUP(x,{bounds},{labels}) – largest bound <= x."""
    idx = np.searchsorted(np.array(bounds), values.to_numpy(dtype=float), side="right") - 1
    idx = np.clip(idx, 0, len(labels) - 1)
    return pd.Series(np.array(labels, dtype=object)[idx], index=values.index)


# ==========================================================================
# Combine sheet – formula columns HZ..JX
# ==========================================================================
COMBINE_FORMULA_HEADERS = None  # filled lazily by combine_formulas (depends on FY)


def combine_formulas(sr: pd.DataFrame, manual_grn: dict[str, dt.date], fy: FiscalYear,
                     as_on: dt.date) -> tuple[pd.DataFrame, list[dt.date]]:
    """Returns (formula columns frame aligned with `sr`, snapshot dates for row 1)."""
    inv_date = pd.to_datetime(sr[INV_DATE_COL])
    grn_date = pd.to_datetime(sr["Goods Received Date"])
    amount = pd.to_numeric(sr[AMOUNT_COL], errors="coerce").fillna(0.0)
    receipt = sr["Receipt Status"]
    received = receipt.isin(["Received", "Partially Received"])

    manual = sr["Invoice No"].map(lambda k: manual_grn.get(k) if k is not None else None)
    manual = pd.to_datetime(manual)
    has_manual = manual.notna()

    # HZ  Revised Billing Date
    #   =IF(GRN<>"",GRN,IFERROR(XLOOKUP(Inv,'Manual GRN'!A:A,'Manual GRN'!B:B),
    #        IF(OR(Receipt="Received",Receipt="Partially Received"),InvDate+30,"")))
    revised = grn_date.copy()
    revised = revised.where(grn_date.notna(), manual)
    assumed = inv_date + pd.Timedelta(days=30)
    revised = revised.where(revised.notna() | ~received, assumed)

    # IA  Non GRN  =IF(HZ="",DATE(FYend),HZ-1)
    non_grn_till = (revised - pd.Timedelta(days=1)).fillna(pd.Timestamp(fy.end))

    out = {"Revised Billing Date": revised, "Non GRN ": non_grn_till}

    snaps = snapshot_dates(fy, as_on)
    month_nums = [str(m) for _, m in fy.months]
    days_cols, amt_cols = [], []
    for i, snap in enumerate(snaps):
        s = pd.Timestamp(snap)
        live = (inv_date <= s) & (non_grn_till >= s)          # AND($C<=IB$1,$IA>=IB$1)
        out[month_nums[i]] = amount.where(live, 0.0)           # IB..IM  -> $EB or 0
        amt_cols.append(month_nums[i])
    for i, snap in enumerate(snaps):
        s = pd.Timestamp(snap)
        live = (inv_date <= s) & (non_grn_till >= s)
        name = f"Column{13 + i}"
        out[name] = ((s - inv_date).dt.days + 1).where(live, 0).fillna(0).astype(int)   # IN..IY
        days_cols.append(name)
    for i, (y, m) in enumerate(fy.months):                     # IZ..JK  bucket per month-end
        out[month_label(y, m)] = excel_lookup(out[days_cols[i]], MONTH_BUCKET_BOUNDS, MONTH_BUCKET_LABELS)

    out["Customer Code"] = sr["Customer Code"]
    out["Customer Name"] = sr["Customer Name"]
    out["Site"] = sr["Site"]
    out["Party Group"] = sr["Party Group Description"]
    out["Credit Term"] = sr["Credit Term"]
    out["Invoice No."] = sr["Invoice No"]
    out["Inv Date"] = inv_date
    out["Inv Month"] = inv_date.dt.to_period("M").dt.to_timestamp()        # DATE(YEAR,MONTH,1)

    # JT GRN Source
    src = np.where(grn_date.notna(), GRN_SOURCES[0],
                   np.where(has_manual, GRN_SOURCES[1],
                            np.where(received, GRN_SOURCES[2], GRN_SOURCES[3])))
    out["GRN Source"] = pd.Series(src, index=sr.index, dtype=object)

    # JU Days to GRN  =IF(HZ="","",HZ-C)
    out["Days to GRN"] = (revised - inv_date).dt.days

    # JV Current Non-GRN Amt  =IF(AND($C<=TODAY(),$IA>=TODAY()),$EB,0)
    today = pd.Timestamp(as_on)
    live_now = (inv_date <= today) & (non_grn_till >= today)
    out["Current Non-GRN Amt"] = amount.where(live_now, 0.0)
    # JW Current Age Days  =IF($JV<>0,TODAY()-$C+1,0)
    age = ((today - inv_date).dt.days + 1).where(out["Current Non-GRN Amt"] != 0, 0)
    out["Current Age Days"] = age.fillna(0).astype(int)
    # JX Current Bucket
    out["Current Bucket"] = excel_lookup(out["Current Age Days"], CURRENT_BUCKET_BOUNDS, CURRENT_BUCKET_LABELS)

    return pd.DataFrame(out, index=sr.index), snaps


def month_amount_cols(fy: FiscalYear) -> list[str]:
    return [str(m) for _, m in fy.months]


def month_bucket_cols(fy: FiscalYear) -> list[str]:
    return [month_label(y, m) for y, m in fy.months]


# ==========================================================================
# Report sheet
# ==========================================================================
def build_report(sr: pd.DataFrame, ar: pd.DataFrame, fy: FiscalYear, as_on: dt.date,
                 snaps: list[dt.date]) -> dict:
    amt_cols, bkt_cols = month_amount_cols(fy), month_bucket_cols(fy)
    labels = bkt_cols

    # B2:N11  =SUMIFS(Combine!IB:IB,Combine!IZ:IZ,Report!$B3)
    aging = {}
    for a, b in zip(amt_cols, bkt_cols):
        g = ar.groupby(ar[b])[a].sum()
        aging[b] = [float(g.get(lbl, 0.0)) for lbl in REPORT_BUCKETS]
    aging_rows = []
    for i, lbl in enumerate(REPORT_BUCKETS):
        aging_rows.append({"bucket": lbl, "values": [aging[m][i] for m in labels]})
    totals = [sum(aging[m]) for m in labels]

    # Transposed (P13:Y25) & mix % (P28:Y40)
    by_month = []
    for j, m in enumerate(labels):
        vals = [aging[m][i] for i in range(len(REPORT_BUCKETS))]
        tot = totals[j]
        by_month.append({
            "month": m, "values": vals, "total": tot,
            "mix": [(v / tot) if tot else None for v in vals] + [1.0 if tot else None],
        })
    current_idx = next((i for i, (y, mo) in enumerate(fy.months) if (y, mo) == (as_on.year, as_on.month)), None)

    # Lakh summaries P42:V54 and P57:V69
    lakh_a, lakh_b = [], []
    for j, row in enumerate(by_month):
        q, r, s, t, u, v, w, x = row["values"]
        a = {"month": row["month"], "current": j == current_idx,
             "v": [(q + r) / LAKH, s / LAKH, t / LAKH, (u + v + w) / LAKH, (v + w) / LAKH]}
        a["v"].append(a["v"][0] + a["v"][1] + a["v"][2] + a["v"][3])
        lakh_a.append(a)
        b = {"month": row["month"], "current": j == current_idx,
             "v": [(q + r) / LAKH, s / LAKH, (t + u + v + w) / LAKH, (u + v + w) / LAKH, (v + w) / LAKH]}
        b["v"].append(b["v"][0] + b["v"][1] + b["v"][2])
        lakh_b.append(b)

    # ---- Management KPIs -------------------------------------------------
    cur = ar["Current Non-GRN Amt"]
    agedays = ar["Current Age Days"]
    total = cur.sum()
    c17 = total / LAKH

    def share(x):
        return (x / c17) if c17 else 0.0

    kpi_current = [
        {"label": "Total Non-GRN outstanding", "lakh": c17, "pct": share(c17), "count": int((cur > 0).sum())},
    ]
    for d in (60, 90, 180):
        v = cur[agedays > d].sum() / LAKH
        kpi_current.append({"label": f"  Above {d} days", "lakh": v, "pct": share(v),
                            "count": int(((cur > 0) & (agedays > d)).sum())})
    # UNIQUE / SUMIF / COUNTIFS compare text case-insensitively in Excel
    ckey = ar["Customer Name"].map(lambda s: s.casefold() if isinstance(s, str) else s)
    cust_pos = ckey[cur > 0].dropna().nunique()
    cust_90 = ckey[(cur > 0) & (agedays > 90)].dropna().nunique()

    # Month-on-month movement H17:H23
    prev_me = (pd.Timestamp(as_on).replace(day=1) - pd.Timedelta(days=1)).date()   # EOMONTH(today,-1)
    try:
        idx = snaps.index(prev_me)
        opening = ar[amt_cols[idx]].sum() / LAKH
    except ValueError:
        opening = 0.0
    inv_date = ar["Inv Date"]
    new_since = cur[inv_date > pd.Timestamp(prev_me)].sum() / LAKH
    closing = c17
    cleared = opening + new_since - closing
    carried = cur[inv_date <= pd.Timestamp(prev_me)].sum() / LAKH
    movement = [
        {"label": "Previous month-end", "value": prev_me, "kind": "date"},
        {"label": "Opening Non-GRN (previous month-end snapshot)", "value": opening, "kind": "lakh"},
        {"label": "(+) New invoices since month-end still without GRN", "value": new_since, "kind": "lakh"},
        {"label": "(–) Opening balance cleared (GRN received)", "value": cleared, "kind": "lakh"},
        {"label": "Closing Non-GRN (today)", "value": closing, "kind": "lakh"},
        {"label": "% of opening balance cleared", "value": (cleared / opening) if opening else 0.0, "kind": "pct"},
        {"label": "Opening balance still open (carried forward)", "value": carried, "kind": "lakh"},
    ]

    # Billing relationship & GRN speed C26:D31
    sr_amt = pd.to_numeric(sr[AMOUNT_COL], errors="coerce").fillna(0.0)
    sr_date = pd.to_datetime(sr[INV_DATE_COL])
    t = pd.Timestamp(as_on)
    fytd = sr_amt[sr_date <= t].sum() / LAKH
    trailing = sr_amt[(sr_date > t - pd.Timedelta(days=90)) & (sr_date <= t)].sum() / LAKH
    days = pd.to_numeric(ar["Days to GRN"], errors="coerce")
    known = ~ar["GRN Source"].isin(["4. Not Received", "3. Assumed Inv+30"]) & days.notna()
    avg_days = days[known].mean() if known.any() else 0.0
    assumed = cur[ar["GRN Source"] == "3. Assumed Inv+30"].sum() / LAKH
    billing = [
        {"label": "FYTD billing (₹ Lakhs)", "value": fytd, "kind": "lakh"},
        {"label": "Non-GRN as % of FYTD billing", "value": (c17 / fytd) if fytd else 0.0, "kind": "pct"},
        {"label": "Trailing 90-day billing (₹ Lakhs)", "value": trailing, "kind": "lakh"},
        {"label": "Non-GRN days (Non-GRN ÷ avg daily billing, last 90 days)",
         "value": (c17 / (trailing / 90)) if trailing else 0.0, "kind": "num"},
        {"label": "Avg days invoice → GRN (FYTD, where GRN date known)", "value": avg_days, "kind": "num"},
        {"label": "Non-GRN relying on assumed Inv+30 (₹ Lakhs)", "value": assumed, "kind": "lakh",
         "pct": share(assumed)},
    ]

    # Top 15 customers G35:M50
    #   UNIQUE keeps first-appearance order, SORTBY is stable for ties
    first_spelling = {}
    for k, n in zip(ckey, ar["Customer Name"]):
        if isinstance(k, str) and k not in first_spelling:
            first_spelling[k] = n
    order = list(first_spelling)                        # UNIQUE: first appearance
    sums = cur.groupby(ckey, sort=False).sum().reindex(order)
    ranked = sorted(range(len(order)), key=lambda i: -sums.iloc[i])    # SORTBY: stable
    top = []
    for i in ranked[:15]:
        c = first_spelling[order[i]]
        mask = ckey == order[i]
        d = days[mask & known]
        top.append({
            "customer": c,
            "lakh": sums.iloc[i] / LAKH,
            "pct": share(sums.iloc[i] / LAKH),
            "above90": cur[mask & (agedays > 90)].sum() / LAKH,
            "lines": int((mask & (cur > 0)).sum()),
            "avg_days": d.mean() if len(d) else 0.0,
            "oldest": int(agedays[mask].max()) if mask.any() else 0,
        })
    top_total = {
        "lakh": sum(r["lakh"] for r in top),
        "above90": sum(r["above90"] for r in top),
        "lines": sum(r["lines"] for r in top),
    }
    top_total["pct"] = share(top_total["lakh"])
    top10_share = share(sum(r["lakh"] for r in top[:10]))

    # ---- portal visuals (same numbers, regrouped into 5 ordered age groups) ----
    def five(vals):
        q, r_, s, t, u, v, w, x = vals
        return [(q + r_) / LAKH, s / LAKH, t / LAKH, u / LAKH, (v + w + x) / LAKH]

    shown = [j for j, snap in enumerate(snaps) if snap <= as_on] or list(range(len(snaps)))
    chart = {
        "months": [labels[j] + ("*" if j == current_idx else "") for j in shown],
        "groups": ["0-30 days", "31-60 days", "61-90 days", "91-180 days", "Above 180 days"],
        "series": [list(col) for col in zip(*[five(by_month[j]["values"]) for j in shown])],
    }
    # month-end trend per age view (= "Above-60 view" summary table, ₹ Lakhs)
    trend_names = ["0-30 Days", "31-60 Days", "Above 60 Days", "Above 90 Days", "Above 180 Days", "Total"]
    trend = {
        "months": [lakh_b[j]["month"] + ("*" if j == current_idx else "") for j in shown],
        "series": [{"name": nm, "values": [lakh_b[j]["v"][k] for j in shown]} for k, nm in enumerate(trend_names)],
    }
    tiles = {
        "total": c17,
        "opening": opening,
        "delta": c17 - opening if opening else None,
        "delta_pct": ((c17 - opening) / opening) if opening else None,
        "prev_me": prev_me,
        "lines": kpi_current[0]["count"],
        "customers": cust_pos,
        "above": kpi_current[1:],
        "nongrn_days": (c17 / (trailing / 90)) if trailing else 0.0,
        "pct_fytd": (c17 / fytd) if fytd else 0.0,
        "fytd": fytd,
        "avg_days": avg_days,
    }

    return {
        "chart": chart,
        "trend": trend,
        "tiles": tiles,
        "as_on": as_on,
        "lakh_divisor": LAKH,
        "months": labels,
        "current_idx": current_idx,
        "aging_rows": aging_rows,
        "aging_totals": totals,
        "by_month": by_month,
        "buckets": REPORT_BUCKETS,
        "lakh_a": lakh_a,
        "lakh_b": lakh_b,
        "kpi_current": kpi_current,
        "cust_pos": cust_pos,
        "cust_90": cust_90,
        "top10_share": top10_share,
        "movement": movement,
        "billing": billing,
        "top": top,
        "top_total": top_total,
    }


# ==========================================================================
# Customer Dashboard – pivot tables
# ==========================================================================
def _filter(ar: pd.DataFrame, filters: dict[str, list[str] | None]) -> pd.DataFrame:
    m = pd.Series(True, index=ar.index)
    for col, allowed in filters.items():
        if allowed:
            m &= ar[col].isin(allowed)
    return ar[m]


def _excel_sort_key(s):
    return str(s).casefold()


def pivot_bucket(ar, filters):
    """PT_Cust_Bucket: rows Customer, cols Current Bucket, Sum Current Non-GRN Amt, sort desc."""
    df = _filter(ar, filters)
    cols = sorted(df["Current Bucket"].dropna().unique(), key=_excel_sort_key)
    pt = df.pivot_table(index="Customer Name", columns="Current Bucket", values="Current Non-GRN Amt",
                        aggfunc="sum", sort=False)
    pt = pt.reindex(columns=cols)
    total = df.groupby("Customer Name")["Current Non-GRN Amt"].sum()
    rows = sorted(total.index, key=lambda c: (-total[c], _excel_sort_key(c)))
    body = [{"label": c, "values": [_nan_none(pt.at[c, k]) for k in cols], "total": float(total[c])} for c in rows]
    grand = [float(df.loc[df["Current Bucket"] == k, "Current Non-GRN Amt"].sum()) for k in cols]
    return {"columns": cols, "rows": body, "grand": grand, "grand_total": float(df["Current Non-GRN Amt"].sum())}


def pivot_trend(ar, fy, filters):
    """PT_Cust_Trend: rows Customer (A-Z), values = 12 month-end amounts."""
    df = _filter(ar, filters)
    cols = month_amount_cols(fy)
    g = df.groupby("Customer Name")[cols].sum()
    rows = sorted(g.index, key=_excel_sort_key)
    body = [{"label": c, "values": [float(v) for v in g.loc[c].tolist()]} for c in rows]
    return {"columns": month_bucket_cols(fy), "rows": body, "grand": [float(df[c].sum()) for c in cols]}


def pivot_grn_source(ar, filters):
    """PT_Cust_GRN: rows Customer, cols GRN Source, Sum Current Non-GRN Amt, sort desc."""
    df = _filter(ar, filters)
    cols = sorted(df["GRN Source"].dropna().unique(), key=_excel_sort_key)
    pt = df.pivot_table(index="Customer Name", columns="GRN Source", values="Current Non-GRN Amt",
                        aggfunc="sum", sort=False).reindex(columns=cols)
    total = df.groupby("Customer Name")["Current Non-GRN Amt"].sum()
    rows = sorted(total.index, key=lambda c: (-total[c], _excel_sort_key(c)))
    body = [{"label": c, "values": [_nan_none(pt.at[c, k]) for k in cols], "total": float(total[c])} for c in rows]
    grand = [float(df.loc[df["GRN Source"] == k, "Current Non-GRN Amt"].sum()) for k in cols]
    return {"columns": cols, "rows": body, "grand": grand, "grand_total": float(df["Current Non-GRN Amt"].sum())}


def pivot_days(ar, filters):
    """PT_Cust_Days: Average / Max of Days to GRN, Count of Invoice No.; sort desc by average."""
    df = _filter(ar, filters)
    d = pd.to_numeric(df["Days to GRN"], errors="coerce")
    g = pd.DataFrame({"c": df["Customer Name"], "d": d, "n": df["Invoice No."].notna()})
    agg = g.groupby("c").agg(avg=("d", "mean"), mx=("d", "max"), lines=("n", "sum"))
    rows = sorted(agg.index, key=lambda c: (-(agg.at[c, "avg"]) if pd.notna(agg.at[c, "avg"]) else np.inf,
                                             _excel_sort_key(c)))
    body = [{"label": c, "avg": _nan_none(agg.at[c, "avg"]), "max": float(agg.at[c, "mx"]) if pd.notna(agg.at[c, "mx"]) else 0.0,
             "lines": int(agg.at[c, "lines"])} for c in rows]
    return {"rows": body, "grand": {"avg": _nan_none(d.mean()), "max": float(d.max()) if d.notna().any() else 0.0,
                                    "lines": int(g["n"].sum())}}


def _nan_none(v):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else float(v)
