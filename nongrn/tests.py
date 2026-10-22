"""Checks that the portal reproduces Non GRN Age.xlsx.

Run:  python manage.py test nongrn

ExcelParityTest feeds the engine the workbook's own Combine data as on the workbook's own
TODAY() (the value Excel saved in Report!C14) and compares every number on the Report sheet.

The workbook has a few Combine rows whose month-end formulas point at the LAST data row
(e.g. IB12408 = IF(AND($C13282<=IB$1,...),$EB13282,0)) instead of their own row. The portal
deliberately calculates those rows correctly. The test reproduces Excel's broken references
for those rows only, so that it compares like with like; it also lists them.
"""
import datetime as dt
import re
import zipfile
from pathlib import Path

import pandas as pd
from django.conf import settings
from django.test import SimpleTestCase

from . import services
from .engine import calc, ingest, workbook
from .engine.schema import SR_COLUMNS
from .templatetags.nongrn_fmt import inr, lakh, num1, pct

XL = Path(settings.BASE_DIR).parent / "Non GRN Age.xlsx"


class ExcelRoundingTest(SimpleTestCase):
    """Displayed numbers round half away from zero, like Excel's number formats."""

    def test_half_up(self):
        self.assertEqual(inr(90240.5), "90,241")      # Python's own rounding would give 90,240
        self.assertEqual(inr(90240.49), "90,240")
        self.assertEqual(inr(-1234567.5), "(12,34,568)")
        self.assertEqual(lakh(2.675), "2.68")
        self.assertEqual(pct(0.35249), "35.2%")
        self.assertEqual(num1(17.15), "17.2")
        self.assertEqual(num1(17.146), "17.1")


def _sheet_xml(z, name):
    wbx = z.read("xl/workbook.xml").decode()
    rels = z.read("xl/_rels/workbook.xml.rels").decode()
    rid = re.search(r'<sheet [^>]*name="%s"[^>]*r:id="(rId\d+)"' % re.escape(name), wbx).group(1)
    m = re.search(r'Id="%s"[^>]*Target="([^"]+)"' % rid, rels) or re.search(r'Target="([^"]+)"[^>]*Id="%s"' % rid, rels)
    return z.read("xl/" + m.group(1).replace("/xl/", "")).decode()


def broken_rows(combine_xml):
    """{row: source_row} for Combine rows whose IB formula reads $C/$EB of another row."""
    out = {}
    for m in re.finditer(r'<c r="IB(\d+)"[^>]*><f[^>]*>([^<]*)</f>', combine_xml):
        row, f = int(m.group(1)), m.group(2)
        ref = re.search(r"\$C(\d+)", f)
        if ref and int(ref.group(1)) != row:
            out[row] = int(ref.group(1))
    return out


def _norm(v):
    if isinstance(v, dt.datetime):
        return (v - dt.datetime(1899, 12, 30)).total_seconds() / 86400
    if isinstance(v, dt.date):
        return float((v - dt.date(1899, 12, 30)).days)
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    return None if v in (None, "") else v


class ExcelParityTest(SimpleTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not XL.exists():
            raise cls.skipTest(cls, f"{XL} not found")
        from python_calamine import CalamineWorkbook
        wb = CalamineWorkbook.from_path(str(XL))
        cls.rep = wb.get_sheet_by_name("Report").to_python(skip_empty_area=False)
        cmb = wb.get_sheet_by_name("Combine").to_python(skip_empty_area=False)
        man = wb.get_sheet_by_name("Manual GRN").to_python(skip_empty_area=False)
        cls.as_on = cls.rep[13][2]                      # Report!C14 = TODAY() as saved
        if isinstance(cls.as_on, dt.datetime):
            cls.as_on = cls.as_on.date()

        sr = pd.DataFrame([r[:233] for r in cmb[2:]], columns=SR_COLUMNS, dtype=object)
        sr = sr.map(lambda v: None if v == "" else v)
        sr["Invoice Date"] = ingest.to_date(sr["Invoice Date"])
        sr["Goods Received Date"] = ingest.to_date(sr["Goods Received Date"])
        manual = {}
        for r in man[1:]:
            if r and r[0] not in (None, "") and str(r[0]) not in manual:
                manual[str(r[0])] = r[1] if isinstance(r[1], dt.date) else None
        manual = {k: v for k, v in manual.items() if v}
        fy = services.fiscal_year()

        z = zipfile.ZipFile(XL)
        cls.broken = broken_rows(_sheet_xml(z, "Combine"))

        # correct calculation (what the portal shows) ...
        ar, snaps = calc.combine_formulas(sr, manual, fy, cls.as_on)
        # ... with Excel's broken references copied in for those rows only
        sr_b = sr.copy()
        for row, src in cls.broken.items():
            for col in ("Invoice Date", "Item Net Amount"):
                sr_b.loc[row - 3, col] = sr.loc[src - 3, col]
        ar_b, _ = calc.combine_formulas(sr_b, manual, fy, cls.as_on)
        cols = calc.month_amount_cols(fy) + [f"Column{13 + i}" for i in range(12)] + calc.month_bucket_cols(fy) + \
            ["Inv Month", "Days to GRN", "Current Non-GRN Amt", "Current Age Days", "Current Bucket"]
        for row in cls.broken:
            for c in cols:
                ar.loc[row - 3, c] = ar_b.loc[row - 3, c]

        old = workbook.read_template_sst(z)
        sst = workbook.SharedStrings()
        explicit = workbook.report_explicit(ar, sr, fy, cls.as_on, snaps, None, 100000.0)
        xml = workbook.build_report_sheet(_sheet_xml(z, "Report"), old, sst, explicit)
        cls.portal = {}
        for m in re.finditer(r'<c r="([A-Z]+)(\d+)"([^>]*?)(?:/>|>(.*?)</c>)', xml, re.S):
            col, row, attrs, inner = m.groups()
            v = re.search(r"<v>(.*?)</v>", inner or "", re.S)
            if v:
                t = workbook.attr(attrs, "t")
                cls.portal[(int(row), workbook.col_number(col))] = (
                    sst.items[int(v.group(1))] if t == "s" else
                    workbook._unescape(v.group(1)) if t in ("str", "e") else float(v.group(1)))

    def _check(self, area):
        """area like 'A1:M13' – every numeric cell equal to the cent, text equal."""
        a, b = area.split(":")
        c0, r0 = re.match(r"([A-Z]+)(\d+)", a).groups()
        c1, r1 = re.match(r"([A-Z]+)(\d+)", b).groups()
        bad = []
        for r in range(int(r0), int(r1) + 1):
            for c in range(workbook.col_number(c0), workbook.col_number(c1) + 1):
                x = _norm(self.rep[r - 1][c - 1]) if r - 1 < len(self.rep) and c - 1 < len(self.rep[r - 1]) else None
                y = _norm(self.portal.get((r, c)))
                if isinstance(x, float) and isinstance(y, float):
                    ok = abs(x - y) < 0.005
                elif isinstance(x, str) and isinstance(y, str):
                    ok = x.replace("\n", " ") == y.replace("\n", " ")
                else:
                    ok = x == y
                if not ok:
                    bad.append(f"{workbook.col_letter(c)}{r}: Excel {x!r} portal {y!r}")
        self.assertEqual(bad, [], f"{area} differs in {len(bad)} cells")

    def test_ageing_rupees(self):
        self._check("A1:N13")

    def test_lakh_and_above60_tables(self):
        self._check("O1:Y70")

    def test_current_position_and_movement(self):
        self._check("A14:M70")

    def test_broken_rows_listed(self):
        # documents the Excel rows the portal calculates differently (correctly)
        print("\nExcel Combine rows reading another row's $C/$EB:",
              ", ".join(f"{r}->{s}" for r, s in sorted(self.broken.items())) or "none")
