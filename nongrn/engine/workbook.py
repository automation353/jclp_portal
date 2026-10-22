"""
Builds "Non GRN Age.xlsx" from the portal data, using the original workbook as the template.

Everything structural is copied from the template unchanged – styles, column widths,
sheet order/visibility, every formula, the 5 tables, Power Query queries & connections,
query tables, pivot table layouts, slicers, conditional formats, page setup.  What is
rewritten:

* the data rows of the query tables (Combine A:HY, SR FY 25-26, MDA FY 25-26, MDA FY 26-27),
  exactly as Power Query loads them (text "" stays "", typed nulls stay blank)
* Combine!HZ:JX formula columns – same formulas, cached results from the engine
* Combine row 1 snapshot dates (TODAY() on the running month)
* Report – every formula keeps its text; cached results come from the engine for the
  table/array formulas and from a small evaluator for the plain arithmetic ones
* Customer Dashboard – pivot cache (definition + records), the 4 pivot tables
  (items, row/column items, location), the 4 slicer caches and the rendered pivot cells
* Manual GRN rows
* table / defined-name ranges; calcChain is dropped and a full recalc is requested on open
"""
from __future__ import annotations

import datetime as dt
import math
import re
import zipfile
from collections import defaultdict
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np
import pandas as pd

from . import calc
from .schema import MDA_COLUMNS, MDA_PREV_TYPES, MDA_TYPES, SR_COLUMNS, SR_CURRENT_TYPES, SR_PREV_TYPES

EPOCH = dt.datetime(1899, 12, 30)
SHEET_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
ERR = "#DIV/0!"


# ==========================================================================
# small helpers
# ==========================================================================
def col_letter(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def col_number(s: str) -> int:
    n = 0
    for ch in s:
        n = n * 26 + ord(ch) - 64
    return n


def serial(v) -> float | int | None:
    """Excel serial for date / datetime / Timestamp."""
    if v is None or v is pd.NaT:
        return None
    if isinstance(v, pd.Timestamp):
        v = v.to_pydatetime()
    if isinstance(v, dt.datetime):
        d = (v - EPOCH)
        whole = d.days
        frac = d.seconds / 86400 + d.microseconds / 86400e6
        return whole if frac == 0 else whole + frac
    if isinstance(v, dt.date):
        return (v - EPOCH.date()).days
    if isinstance(v, dt.time):          # calamine: date-formatted serial below 1
        return -1 if v == dt.time(0) else (v.hour * 3600 + v.minute * 60 + v.second) / 86400
    return None


def num_text(v) -> str:
    """Number exactly as a double (shortest round-trip form)."""
    if isinstance(v, (bool, np.bool_)):
        return "1" if v else "0"
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    f = float(v)
    if f.is_integer() and abs(f) < 1e15:
        return str(int(f))
    return repr(f)


def is_blank(v) -> bool:
    return v is None or v is pd.NaT or (isinstance(v, float) and math.isnan(v))


_XML_BAD = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f]")


def xml_text(s: str) -> str:
    s = _XML_BAD.sub("", s)
    return escape(s, {'"': "&quot;"})


class SharedStrings:
    def __init__(self):
        self.index: dict[str, int] = {}
        self.items: list[str] = []
        self.count = 0

    def get(self, s: str) -> int:
        self.count += 1
        i = self.index.get(s)
        if i is None:
            i = self.index[s] = len(self.items)
            self.items.append(s)
        return i

    def xml(self) -> str:
        out = [f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<sst xmlns="{SHEET_MAIN}" '
               f'count="{self.count}" uniqueCount="{len(self.items)}">']
        for s in self.items:
            sp = ' xml:space="preserve"' if s != s.strip() or "\n" in s else ""
            out.append(f"<si><t{sp}>{xml_text(s)}</t></si>")
        out.append("</sst>")
        return "".join(out)


def read_template_sst(z: zipfile.ZipFile) -> list[str]:
    from xml.etree.ElementTree import iterparse
    ns = "{%s}" % SHEET_MAIN
    out = []
    for _, el in iterparse(z.open("xl/sharedStrings.xml")):
        if el.tag == ns + "si":
            out.append("".join(t.text or "" for t in el.iter(ns + "t")))
            el.clear()
    return out


# ---- cell XML builders -----------------------------------------------------
def c_num(ref, v, s=None):
    st = f' s="{s}"' if s is not None else ""
    return f'<c r="{ref}"{st}><v>{num_text(v)}</v></c>'


def c_str(ref, text, sst: SharedStrings, s=None):
    st = f' s="{s}"' if s is not None else ""
    return f'<c r="{ref}"{st} t="s"><v>{sst.get(text)}</v></c>'


def c_blank(ref, s):
    return f'<c r="{ref}" s="{s}"/>' if s is not None else ""


def c_formula(ref, formula_xml, value, s=None, extra=""):
    """formula_xml: complete <f ...>...</f> element; value: number | str | ERR | None."""
    st = f' s="{s}"' if s is not None else ""
    if value is None:
        return f'<c r="{ref}"{st}{extra}>{formula_xml}</c>'
    if isinstance(value, str):
        t = "e" if value.startswith("#") and value in ("#DIV/0!", "#REF!", "#N/A", "#VALUE!") else "str"
        return f'<c r="{ref}"{st} t="{t}"{extra}>{formula_xml}<v>{xml_text(value)}</v></c>'
    return f'<c r="{ref}"{st}{extra}>{formula_xml}<v>{num_text(value)}</v></c>'


# ==========================================================================
# formula text utilities (row shifting for shared / per-row formulas)
# ==========================================================================
_REF = re.compile(r"(?<![A-Za-z_\d.\[])(\$?)([A-Z]{1,3})(\$?)(\d+)(?![\d(\]])")


def shift_formula(f: str, drow: int, dcol: int = 0) -> str:
    def sub(m):
        cabs, col, rabs, row = m.groups()
        c = col if cabs else col_letter(col_number(col) + dcol)
        r = row if rabs else str(int(row) + drow)
        return f"{cabs}{c}{rabs}{r}"
    parts = f.split('"')
    for i in range(0, len(parts), 2):          # only outside string literals
        parts[i] = _REF.sub(sub, parts[i])
    return '"'.join(parts)


# ==========================================================================
# template sheet access
# ==========================================================================
def split_sheet(xml: str):
    if "<sheetData/>" in xml:
        a = xml.index("<sheetData/>")
        return xml[:a], "", xml[a + len("<sheetData/>"):]
    a = xml.index("<sheetData>")
    b = xml.index("</sheetData>")
    return xml[:a], xml[a + len("<sheetData>"):b], xml[b + len("</sheetData>"):]


_ROW = re.compile(r"<row ([^>]*?)(?:/>|>(.*?)</row>)", re.S)
_CELL = re.compile(r"<c r=\"([A-Z]+)(\d+)\"([^>]*?)(?:/>|>(.*?)</c>)", re.S)


def parse_rows(sheet_data: str, upto: int | None = None):
    """{row: (row_attrs, [(col, attrs, inner)])}"""
    rows = {}
    for m in _ROW.finditer(sheet_data):
        attrs, inner = m.group(1), m.group(2) or ""
        r = int(re.search(r'r="(\d+)"', attrs).group(1))
        if upto and r > upto:
            break
        rows[r] = (attrs, [(c.group(1), c.group(3), c.group(4) or "") for c in _CELL.finditer(inner)])
    return rows


def attr(attrs: str, name: str):
    m = re.search(rf'\b{name}="([^"]*)"', attrs)
    return m.group(1) if m else None


def cell_value(attrs, inner, old_sst):
    """Python value of a template cell (for constants)."""
    t = attr(attrs, "t")
    v = re.search(r"<v>(.*?)</v>", inner, re.S)
    if t == "s":
        return old_sst[int(v.group(1))]
    if t in ("str", "e"):
        return _unescape(v.group(1)) if v else ""
    if t == "inlineStr":
        return _unescape("".join(re.findall(r"<t[^>]*>(.*?)</t>", inner, re.S)))
    if v is None:
        return None
    x = float(v.group(1))
    return int(x) if x.is_integer() else x


def _unescape(s):
    return s.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&apos;", "'").replace("&amp;", "&")


def remap_cell(col, row, attrs, inner, old_sst, sst):
    """Template cell re-emitted with its shared-string index moved to the new table."""
    if attr(attrs, "t") == "s":
        v = re.search(r"<v>(\d+)</v>", inner)
        inner = re.sub(r"<v>\d+</v>", f"<v>{sst.get(old_sst[int(v.group(1))])}</v>", inner)
    return f'<c r="{col}{row}"{attrs}>{inner}</c>' if inner else f'<c r="{col}{row}"{attrs}/>'


def row_open(r, attrs_template=None):
    keep = ""
    if attrs_template:
        for k in ("ht", "customHeight", "hidden"):
            v = attr(attrs_template, k)
            if v is not None:
                keep += f' {k}="{v}"'
    return f'<row r="{r}"{keep}>'


# ==========================================================================
# Power Query table writer (query-table areas)
# ==========================================================================
class ColumnStyles:
    """Per column: the style the template uses for each kind of value."""

    def __init__(self, rows: dict, first_data_row: int, last_col: int):
        self.map = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
        for r, (_, cells) in rows.items():
            if r < first_data_row:
                continue
            for col, attrs, inner in cells:
                cn = col_number(col)
                if cn > last_col:
                    continue
                t = attr(attrs, "t")
                kind = "str" if t in ("s", "str", "inlineStr") else ("num" if "<v>" in inner else "blank")
                self.map[cn][kind][attr(attrs, "s")] += 1

    def get(self, cn, kind):
        kinds = self.map.get(cn)
        if not kinds:
            return None
        pick = kinds.get(kind) or kinds.get("str") or kinds.get("num") or next(iter(kinds.values()))
        return max(pick.items(), key=lambda kv: kv[1])[0]


TEXTUAL = {"text", "any", None}


def query_cell(ref, v, kind_type, cn, styles: ColumnStyles, sst: SharedStrings):
    """One Power Query output cell. kind_type = the column's final M type."""
    if is_blank(v):
        if kind_type in TEXTUAL:                        # "" stays "" for text/any columns
            return c_str(ref, "", sst, styles.get(cn, "str"))
        return ""                                       # typed null -> blank
    if isinstance(v, str):
        return c_str(ref, v, sst, styles.get(cn, "str"))
    s = serial(v)
    if s is not None:
        return c_num(ref, s, styles.get(cn, "num"))
    if isinstance(v, (int, float, np.integer, np.floating)):
        return c_num(ref, v, styles.get(cn, "num"))
    return c_str(ref, str(v), sst, styles.get(cn, "str"))


def effective_types(base: dict, extra: dict) -> dict:
    t = dict(base)
    t.update(extra)
    return t


SR_CUR_FINAL = effective_types(SR_CURRENT_TYPES, {"Invoice Date": "date", "Goods Received Date": "date"})
SR_PREV_FINAL = effective_types(SR_PREV_TYPES, {"Invoice Date": "date", "Goods Received Date": "date"})
MDA_CUR_FINAL = effective_types(MDA_TYPES, {"Customer GRN Date": "date"})
MDA_PREV_FINAL = dict(MDA_PREV_TYPES)


def write_query_rows(out, frame: pd.DataFrame, columns: list[str], first_row: int, type_maps,
                     styles: ColumnStyles, sst: SharedStrings, extra_cells=None):
    """type_maps: list of (start_index, type_dict) – rows from start_index use that map."""
    values = [frame[c].tolist() if c in frame else [None] * len(frame) for c in columns]
    letters = [col_letter(i + 1) for i in range(len(columns))]
    bounds = sorted(type_maps)
    for i in range(len(frame)):
        tmap = [m for s, m in bounds if i >= s][-1]
        r = first_row + i
        parts = [f'<row r="{r}">']
        for j, col in enumerate(columns):
            parts.append(query_cell(f"{letters[j]}{r}", values[j][i], tmap.get(col), j + 1, styles, sst))
        if extra_cells:
            parts.append(extra_cells(i, r))
        parts.append("</row>")
        out.write("".join(parts))


# ==========================================================================
# Report sheet – cached values
# ==========================================================================
class FormulaEval:
    """Evaluates the plain arithmetic formulas of the Report sheet:
    numbers, cell refs, + - * / ^, unary +/-, SUM(range|list), IFERROR(x, y)."""

    TOKEN = re.compile(r"\s*(?:(\d+\.?\d*(?:E[+-]?\d+)?)|(\$?[A-Z]{1,3}\$?\d+(?::\$?[A-Z]{1,3}\$?\d+)?)|"
                       r"([A-Z_.]+)\(|([-+*/^(),]))", re.I)

    def __init__(self, get):
        self.get = get                       # ref -> value

    def eval(self, text):
        self.toks = []
        pos = 0
        text = text.strip()
        while pos < len(text):
            m = self.TOKEN.match(text, pos)
            if not m:
                raise ValueError(f"cannot parse formula: {text}")
            num, ref, fn, op = m.groups()
            self.toks.append(("num", float(num)) if num else ("ref", ref.replace("$", "")) if ref
                             else ("fn", fn.upper()) if fn else ("op", op))
            pos = m.end()
        self.i = 0
        v = self.expr()
        if self.i != len(self.toks):
            raise ValueError(f"trailing tokens in {text}")
        return v

    def peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else (None, None)

    def take(self):
        t = self.toks[self.i]
        self.i += 1
        return t

    def expr(self):
        v = self.term()
        while self.peek() in (("op", "+"), ("op", "-")):
            op = self.take()[1]
            v = self.arith(v, self.term(), op)
        return v

    def term(self):
        v = self.power()
        while self.peek() in (("op", "*"), ("op", "/")):
            op = self.take()[1]
            v = self.arith(v, self.power(), op)
        return v

    def power(self):
        v = self.unary()
        while self.peek() == ("op", "^"):
            self.take()
            v = self.arith(v, self.unary(), "^")
        return v

    def unary(self):
        if self.peek() in (("op", "+"), ("op", "-")):
            op = self.take()[1]
            v = self.unary()
            return v if op == "+" else self.arith(0.0, v, "-")
        return self.atom()

    def atom(self):
        kind, val = self.take()
        if kind == "num":
            return val
        if kind == "ref":
            if ":" in val:
                return ("range", val)
            return self.get(val)
        if kind == "op" and val == "(":
            v = self.expr()
            self.take()
            return v
        if kind == "fn":
            args = []
            if self.peek() != ("op", ")"):
                args.append(self.expr())
                while self.peek() == ("op", ","):
                    self.take()
                    args.append(self.expr())
            self.take()  # ')'
            return self.call(val, args)
        raise ValueError(f"unexpected token {kind} {val}")

    def cells(self, rng):
        a, b = rng.split(":")
        ma, mb = re.match(r"([A-Z]+)(\d+)", a), re.match(r"([A-Z]+)(\d+)", b)
        out = []
        for r in range(int(ma.group(2)), int(mb.group(2)) + 1):
            for c in range(col_number(ma.group(1)), col_number(mb.group(1)) + 1):
                out.append(self.get(f"{col_letter(c)}{r}"))
        return out

    def call(self, fn, args):
        if fn == "SUM":
            total = 0.0
            for a in args:
                vals = self.cells(a[1]) if isinstance(a, tuple) else [a]
                for v in vals:
                    if isinstance(v, str) and v.startswith("#"):
                        return v
                    if isinstance(v, (int, float)):
                        total += v
            return total
        if fn == "IFERROR":
            v = args[0]
            return args[1] if isinstance(v, str) and v.startswith("#") else v
        raise ValueError(f"function {fn} not supported here")

    @staticmethod
    def arith(a, b, op):
        for v in (a, b):
            if isinstance(v, str) and v.startswith("#"):
                return v
        a = 0.0 if a is None else a
        b = 0.0 if b is None else b
        if isinstance(a, str) or isinstance(b, str):
            return "#VALUE!"
        if op == "+":
            return a + b
        if op == "-":
            return a - b
        if op == "*":
            return a * b
        if op == "/":
            return ERR if b == 0 else a / b
        return a ** b


COMPLEX = re.compile(r"SUMIFS|SUMIF|COUNTIF|TODAY|EOMONTH|INDEX|ROWS|_xlfn|AVERAGEIFS|MAXIFS|TRANSPOSE|\[|!")


def report_explicit(ar: pd.DataFrame, sr: pd.DataFrame, fy, as_on, snaps, grid: dict, lakh: float):
    """Values of the Report cells whose formulas read the tables (Excel semantics)."""
    v = {}
    months = calc.month_bucket_cols(fy)
    amt_cols = calc.month_amount_cols(fy)
    buckets = calc.REPORT_BUCKETS
    # C3:N10  SUMIFS(Combine!month, Combine!bucket, $B)
    for j, (a, b) in enumerate(zip(amt_cols, months)):
        sums = ar.groupby(ar[b])[a].sum()
        for i, lbl in enumerate(buckets):
            v[f"{col_letter(3 + j)}{3 + i}"] = float(sums.get(lbl, 0.0))
    cur = ar["Current Non-GRN Amt"].astype(float)
    age = ar["Current Age Days"].astype(float)
    names = ar["Customer Name"]
    v["C14"] = serial(as_on)
    v["C17"] = cur.sum() / lakh
    v["E17"] = int((cur > 0).sum())
    for r, d in ((18, 60), (19, 90), (20, 180)):
        v[f"C{r}"] = cur[age > d].sum() / lakh
        v[f"E{r}"] = int(((cur > 0) & (age > d)).sum())
    key = names.map(lambda s: s.casefold() if isinstance(s, str) else s)        # UNIQUE / SUMIF ignore case
    v["E21"] = int(key[cur > 0].dropna().nunique())
    v["E22"] = int(key[(cur > 0) & (age > 90)].dropna().nunique())
    prev_me = (pd.Timestamp(as_on).replace(day=1) - pd.Timedelta(days=1)).date()
    v["H17"] = serial(prev_me)
    try:
        v["H18"] = ar[amt_cols[snaps.index(prev_me)]].sum() / lakh
    except ValueError:
        v["H18"] = 0.0
    inv = pd.to_datetime(ar["Inv Date"])
    v["H19"] = cur[inv > pd.Timestamp(prev_me)].sum() / lakh
    v["H23"] = cur[inv <= pd.Timestamp(prev_me)].sum() / lakh
    amt = pd.to_numeric(sr[calc.AMOUNT_COL], errors="coerce").fillna(0.0)
    sdate = pd.to_datetime(sr[calc.INV_DATE_COL])
    t = pd.Timestamp(as_on)
    v["C26"] = amt[sdate <= t].sum() / lakh
    v["C28"] = amt[(sdate > t - pd.Timedelta(days=90)) & (sdate <= t)].sum() / lakh
    days = pd.to_numeric(ar["Days to GRN"], errors="coerce")
    known = ~ar["GRN Source"].isin(["4. Not Received", "3. Assumed Inv+30"]) & days.notna()
    v["C30"] = float(days[known].mean()) if known.any() else 0.0
    v["C31"] = cur[ar["GRN Source"] == "3. Assumed Inv+30"].sum() / lakh
    # G35:M49  LET(UNIQUE, SUMIF, SORTBY desc, SEQUENCE(15)) and the per-customer columns
    first = {}
    for k, n in zip(key, names):
        if k is not None and k == k and k not in first:
            first[k] = n
    order = list(first)
    sums = cur.groupby(key).sum()
    ranked = sorted(range(len(order)), key=lambda i: -sums[order[i]])        # stable, like SORTBY
    c17 = v["C17"]
    for i in range(15):
        r = 35 + i
        if i >= len(ranked):
            for c in "GHIJKLM":
                v[f"{c}{r}"] = "#REF!"
            continue
        k = order[ranked[i]]
        m = key == k
        v[f"G{r}"] = first[k]
        v[f"H{r}"] = cur[m].sum() / lakh
        v[f"I{r}"] = (v[f"H{r}"] / c17) if c17 else 0.0
        v[f"J{r}"] = cur[m & (age > 90)].sum() / lakh
        v[f"K{r}"] = int((m & (cur > 0)).sum())
        d = days[m & known]
        v[f"L{r}"] = float(d.mean()) if len(d) else 0.0
        v[f"M{r}"] = float(age[m].max()) if m.any() else 0.0
    return v


def _ref_rc(ref):
    m = re.match(r"\$?([A-Z]+)\$?(\d+)", ref)
    return int(m.group(2)), col_number(m.group(1))


def _range_cells(rng):
    a, b = (rng.split(":") + [rng])[:2]
    (r0, c0), (r1, c1) = _ref_rc(a), _ref_rc(b)
    return r0, c0, r1, c1


def build_report_sheet(tpl_xml, old_sst, sst, explicit: dict):
    """Report: keep every formula, refresh every cached value."""
    pre, data, post = split_sheet(tpl_xml)
    rows = parse_rows(data)
    cells = {}
    for r, (_, cl) in rows.items():
        for col, attrs, inner in cl:
            cells[f"{col}{r}"] = (r, col, attrs, inner)

    formulas, shared_masters, arrays = {}, {}, {}
    for ref, (r, col, attrs, inner) in cells.items():
        fm = re.search(r"<f([^>]*)>(.*?)</f>|<f([^>]*)/>", inner, re.S)
        if not fm:
            continue
        fattrs = fm.group(1) if fm.group(1) is not None else fm.group(3)
        text = _unescape(fm.group(2) or "")
        if 't="shared"' in fattrs and text:
            shared_masters[attr(fattrs, "si")] = (r, col_number(col), text)
        if 't="array"' in fattrs and attr(fattrs, "ref"):
            arrays[ref] = (attr(fattrs, "ref"), text)
        formulas[ref] = (fattrs, text)
    for ref, (fattrs, text) in list(formulas.items()):
        if 't="shared"' in fattrs and not text:
            r0, c0, master = shared_masters[attr(fattrs, "si")]
            r, col = cells[ref][0], cells[ref][1]
            formulas[ref] = (fattrs, shift_formula(master, r - r0, col_number(col) - c0))

    # spill ranges: child cell -> source cell (TRANSPOSE / plain range copies)
    spill_src, spill_cells = {}, set()
    for top, (rng, text) in arrays.items():
        r0, c0, r1, c1 = _range_cells(rng)
        for rr in range(r0, r1 + 1):
            for cc in range(c0, c1 + 1):
                spill_cells.add(f"{col_letter(cc)}{rr}")
        t = text.strip()
        m = re.fullmatch(r"TRANSPOSE\((\$?[A-Z]+\$?\d+):(\$?[A-Z]+\$?\d+)\)", t)
        m2 = re.fullmatch(r"(\$?[A-Z]+\$?\d+):(\$?[A-Z]+\$?\d+)", t)
        if m or m2:
            sr0, sc0 = _ref_rc((m or m2).group(1))
            for rr in range(r0, r1 + 1):
                for cc in range(c0, c1 + 1):
                    dr, dc = rr - r0, cc - c0
                    src = f"{col_letter(sc0 + dr)}{sr0 + dc}" if m else f"{col_letter(sc0 + dc)}{sr0 + dr}"
                    spill_src[f"{col_letter(cc)}{rr}"] = src

    const = {ref: cell_value(c[2], c[3], old_sst) for ref, c in cells.items() if ref not in formulas}
    memo = {}

    def get(ref):
        if ref in explicit:
            return explicit[ref]
        if ref in memo:
            return memo[ref]
        if ref in spill_src:
            val = get(spill_src[ref])
        elif ref in formulas:
            text = formulas[ref][1]
            if COMPLEX.search(text):
                raise KeyError(f"Report {ref}: no engine value for formula {text}")
            memo[ref] = None            # cycle guard
            val = FormulaEval(get).eval(text)
        else:
            val = const.get(ref)
        memo[ref] = val
        return val

    out = []
    for r in sorted(rows):
        rattrs, cl = rows[r]
        out.append(f"<row {rattrs}>")
        for col, attrs, inner in cl:
            ref = f"{col}{r}"
            if ref in formulas:
                fx = re.search(r"<f[^>]*>.*?</f>|<f[^>]*/>", inner, re.S).group(0)
                keep = "".join(f' {k}="{attr(attrs, k)}"' for k in ("cm", "vm") if attr(attrs, k) is not None)
                out.append(c_formula(ref, fx, _excel_value(get(ref)), attr(attrs, "s"), keep))
            elif ref in spill_cells:
                out.append(_value_cell(ref, get(ref), attr(attrs, "s"), sst))
            else:
                out.append(remap_cell(col, r, attrs, inner, old_sst, sst))
        out.append("</row>")
    return pre + "<sheetData>" + "".join(out) + "</sheetData>" + post


def _excel_value(v):
    if isinstance(v, (np.floating, np.integer)):
        v = v.item()
    if isinstance(v, float) and math.isnan(v):
        return ERR
    return v


def _value_cell(ref, v, s, sst):
    v = _excel_value(v)
    if v is None:
        return c_blank(ref, s) or f'<c r="{ref}"/>'
    if isinstance(v, str):
        if v.startswith("#"):
            st = f' s="{s}"' if s is not None else ""
            return f'<c r="{ref}"{st} t="e"><v>{v}</v></c>'
        return c_str(ref, v, sst, s)
    return c_num(ref, v, s)


# ==========================================================================
# template streaming (Combine sheet XML is ~200 MB: read head + tail only)
# ==========================================================================
def read_head_tail(z: zipfile.ZipFile, name: str, head_bytes=8_000_000, tail_bytes=200_000):
    head, tail = bytearray(), bytearray()
    with z.open(name) as fh:
        while True:
            chunk = fh.read(1 << 20)
            if not chunk:
                break
            if len(head) < head_bytes:
                head += chunk
            tail = (tail + chunk)[-tail_bytes:]
    head_s = head.decode("utf-8", "ignore")
    tail_s = tail.decode("utf-8", "ignore")
    pre = head_s[:head_s.index("<sheetData>")]
    rows_xml = head_s[head_s.index("<sheetData>") + len("<sheetData>"):]
    rows_xml = rows_xml[:rows_xml.rfind("</row>") + len("</row>")]
    post = tail_s[tail_s.rindex("</sheetData>") + len("</sheetData>"):]
    return pre, rows_xml, post


def set_dimension(pre: str, ref: str) -> str:
    return re.sub(r'<dimension ref="[^"]*"/>', f'<dimension ref="{ref}"/>', pre, count=1)


class _Writer:
    """Buffered text writer on top of a binary zip entry."""

    def __init__(self, raw, size=1 << 20):
        self.raw, self.buf, self.n, self.size = raw, [], 0, size

    def write(self, s):
        self.buf.append(s)
        self.n += len(s)
        if self.n >= self.size:
            self.flush()

    def flush(self):
        if self.buf:
            self.raw.write("".join(self.buf).encode("utf-8"))
            self.buf, self.n = [], 0


# ==========================================================================
# Combine
# ==========================================================================
SRC_OF = {"Customer Code": "Customer Code", "Customer Name": "Customer Name", "Site": "Site",
          "Party Group": "Party Group Description", "Credit Term": "Credit Term", "Invoice No.": "Invoice No"}


def combine_cached_values(sr: pd.DataFrame, ar: pd.DataFrame, n_cur: int):
    """Value Excel caches for every HZ:JX cell (dates as serials, "" for blank results)."""
    out = []
    for c in ar.columns:
        s = ar[c]
        if c in ("Revised Billing Date", "Inv Month"):
            vals = [serial(v) if not is_blank(v) else "" for v in s.tolist()]
        elif c in ("Non GRN ", "Inv Date"):
            vals = [serial(v) if not is_blank(v) else 0 for v in s.tolist()]
        elif c == "Days to GRN":
            vals = ["" if is_blank(v) else int(v) for v in s.tolist()]
        elif c in SRC_OF:                     # =[@[column]] returns the cell as it is ("" or 0 if blank)
            src = SRC_OF[c]
            vals = []
            for i, v in enumerate(sr[src].tolist()):
                tmap = SR_CUR_FINAL if i < n_cur else SR_PREV_FINAL
                if is_blank(v):
                    vals.append("" if tmap.get(src) in TEXTUAL else 0)
                elif isinstance(v, str):
                    vals.append(v)
                else:
                    sv = serial(v)
                    vals.append(sv if sv is not None else v)
        elif s.dtype == object:
            vals = ["" if is_blank(v) else v for v in s.tolist()]
        else:
            vals = [v.item() if hasattr(v, "item") else v for v in s.tolist()]
        out.append(vals)
    return out   # [column][row]


def month_snapshot_formula(year: int, month: int) -> str:
    """Snapshot date of one FY month in Combine row 1 (same rule as calc.snapshot_dates)."""
    end = f"DATE({year},{month + 1},0)"
    return f"IF(TODAY()<DATE({year},{month},1),{end},MIN(TODAY(),{end}))"


def write_combine(zout, z, old_sst, sst, sr, ar, n_cur, snaps, as_on, cached, months):
    pre, head_rows, post = read_head_tail(z, "xl/worksheets/sheet3.xml")
    rows = parse_rows(head_rows)
    styles = ColumnStyles(rows, 3, len(SR_COLUMNS))
    n = len(sr)
    last = n + 2
    first_f = len(SR_COLUMNS) + 1                       # HZ
    ncols = len(ar.columns)
    pre = set_dimension(pre, f"A1:{col_letter(first_f + ncols - 1)}{last}")

    row3 = {col: (attrs, inner) for col, attrs, inner in rows[3][1]}
    month_idx = next((i for i, ym in enumerate(months) if ym == (as_on.year, as_on.month)), None)
    volatile = set()
    if month_idx is not None:
        volatile |= {first_f + 2 + month_idx, first_f + 14 + month_idx, first_f + 26 + month_idx}
    ftpl = []
    for j in range(ncols):
        L = col_letter(first_f + j)
        attrs, inner = row3[L]
        fm = re.search(r"<f([^>]*)>(.*?)</f>", inner, re.S)
        fattrs, text = fm.group(1), _unescape(fm.group(2))
        ca = ' ca="1"' if ('ca="1"' in fattrs or (first_f + j) in volatile) else ""
        ftpl.append({"L": L, "shared": 't="shared"' in fattrs, "text": text, "ca": ca, "s": attr(attrs, "s")})

    def formula_cells(i, r):
        parts = []
        for j, t in enumerate(ftpl):
            ref = f"{t['L']}{r}"
            if t["shared"]:
                if r == 3:
                    fx = f'<f t="shared" ref="{t["L"]}3:{t["L"]}{last}"{t["ca"]} si="{j}">{xml_text(t["text"])}</f>'
                else:
                    fx = f'<f t="shared"{t["ca"]} si="{j}"/>'
            else:
                fx = f'<f{t["ca"]}>{xml_text(shift_formula(t["text"], r - 3))}</f>'
            parts.append(c_formula(ref, fx, cached[j][i], t["s"]))
        return "".join(parts)

    with zout.open("xl/worksheets/sheet3.xml", "w", force_zip64=True) as raw:
        out = _Writer(raw)
        out.write(pre + "<sheetData>")
        # row 1: month-end snapshot dates – TODAY() on the running month
        today_fx = None
        for col, attrs, inner in rows[1][1]:
            if "TODAY()" in inner:
                today_fx = re.search(r"<f[^>]*>.*?</f>", inner).group(0)
        snap_cells = {}
        for i, d in enumerate(snaps):
            for base in (first_f + 2, first_f + 14):
                snap_cells[col_letter(base + i)] = (d, months[i])
        r1 = [row_open(1, rows[1][0])]
        for col, attrs, inner in rows[1][1]:
            if col in snap_cells:
                # month column date follows the calendar: running month = today, finished
                # months stop at their last day, a new month starts from the 1st
                d, (y, m) = snap_cells[col]
                fx = f'<f ca="1">{xml_text(month_snapshot_formula(y, m))}</f>'
                r1.append(c_formula(f"{col}1", fx, serial(d) if d else "", attr(attrs, "s")))
            else:
                r1.append(remap_cell(col, 1, attrs, inner, old_sst, sst))
        r1.append("</row>")
        out.write("".join(r1))
        out.write(row_open(2, rows[2][0]) + "".join(remap_cell(c, 2, a, x, old_sst, sst) for c, a, x in rows[2][1]) + "</row>")
        write_query_rows(out, sr, SR_COLUMNS, 3, [(0, SR_CUR_FINAL), (n_cur, SR_PREV_FINAL)], styles, sst,
                         extra_cells=formula_cells)
        out.write("</sheetData>" + post)
        out.flush()
    return last


def write_table_sheet(zout, z, name, old_sst, sst, frame, columns, type_maps):
    """SR FY 25-26 / MDA FY 25-26 / MDA FY 26-27: header row from the template + data rows."""
    pre, head_rows, post = read_head_tail(z, name)
    rows = parse_rows(head_rows)
    styles = ColumnStyles(rows, 2, len(columns))
    last = len(frame) + 1
    pre = set_dimension(pre, f"A1:{col_letter(len(columns))}{last}")
    with zout.open(name, "w", force_zip64=True) as raw:
        out = _Writer(raw)
        out.write(pre + "<sheetData>")
        out.write(row_open(1, rows[1][0]) + "".join(remap_cell(c, 1, a, x, old_sst, sst) for c, a, x in rows[1][1]) + "</row>")
        write_query_rows(out, frame, columns, 2, type_maps, styles, sst)
        out.write("</sheetData>" + post)
        out.flush()
    return last


def template_header(z, name, old_sst):
    _, head_rows, _ = read_head_tail(z, name, head_bytes=400_000)
    rows = parse_rows(head_rows, upto=1)
    return [cell_value(a, x, old_sst) for c, a, x in rows[1][1]]


def build_manual_sheet(tpl_xml, old_sst, sst, manual_rows):
    pre, data, post = split_sheet(tpl_xml)
    rows = parse_rows(data)
    s_a = attr(rows[2][1][0][1], "s") if 2 in rows else None
    s_b = attr(rows[2][1][1][1], "s") if 2 in rows else None
    last = max(max(rows), len(manual_rows) + 1)
    out = [f"<row {rows[1][0]}>" + "".join(remap_cell(c, 1, a, x, old_sst, sst) for c, a, x in rows[1][1]) + "</row>"]
    for k in range(2, last + 1):
        if k - 2 < len(manual_rows):
            inv, d = manual_rows[k - 2]
            out.append(f'<row r="{k}">{c_str(f"A{k}", inv, sst, s_a)}{c_num(f"B{k}", serial(d), s_b)}</row>')
        else:
            out.append(f'<row r="{k}">{c_blank(f"A{k}", s_a)}{c_blank(f"B{k}", s_b)}</row>')
    pre = set_dimension(pre, f"A1:B{last}")
    return pre + "<sheetData>" + "".join(out) + "</sheetData>" + post, last


# ==========================================================================
# Pivot cache, pivot tables, slicers, Customer Dashboard
# ==========================================================================
DATE_FMTS = {"14", "15", "16", "17", "22"}


def excel_text_key(s):
    return ("" if s is None else str(s)).casefold()


def iso(serial_value):
    d = EPOCH + dt.timedelta(days=float(serial_value))
    return d.strftime("%Y-%m-%dT%H:%M:%S")


def _split_elements(xml, tag):
    """Top-level <tag .../> or <tag ...>...</tag> elements (tag is not nested in itself)."""
    return list(re.finditer(rf"<{tag}\b[^>]*/>|<{tag}\b[^>]*>.*?</{tag}>", xml, re.S))


def build_pivot_cache(cd_xml, cached_cols, item_fields, now_serial):
    """Returns (definition_xml, records_iter_factory, items_per_field)."""
    fields = _split_elements(cd_xml, "cacheField")
    n = len(cached_cols[0])
    items = {}
    new_fields = []
    for j, m in enumerate(fields):
        el = m.group(0)
        opening = re.match(r"<cacheField\b[^>]*?(?=/?>)", el).group(0) + ">"
        numfmt = attr(opening, "numFmtId")
        vals = cached_cols[j]
        if j in item_fields:
            order, seen = [], {}
            for v in vals:
                k = "" if v is None else str(v)
                if k not in seen:
                    seen[k] = len(order)
                    order.append(k)
            items[j] = (order, seen)
            body = f'<sharedItems count="{len(order)}">' + "".join(f'<s v="{xml_text(s)}"/>' for s in order) + "</sharedItems>"
        else:
            body = _shared_items_attrs(vals, numfmt in DATE_FMTS)
        new_fields.append(opening + body + "</cacheField>")
    start = cd_xml.index("<cacheFields")
    end = cd_xml.index("</cacheFields>") + len("</cacheFields>")
    xml = cd_xml[:start] + f'<cacheFields count="{len(new_fields)}">' + "".join(new_fields) + "</cacheFields>" + cd_xml[end:]
    xml = re.sub(r'recordCount="\d+"', f'recordCount="{n}"', xml, count=1)
    xml = re.sub(r'refreshedDate="[^"]*"', f'refreshedDate="{now_serial}"', xml, count=1)
    # Excel re-sorts the pivots itself when the file is opened (identical values; its own
    # ordering of rows whose totals are exactly equal)
    if "refreshOnLoad=" not in xml:
        xml = xml.replace("<pivotCacheDefinition ", '<pivotCacheDefinition refreshOnLoad="1" ', 1)
    return xml, items


def _shared_items_attrs(vals, is_date):
    nums = [v for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool)]
    has_str = any(isinstance(v, str) for v in vals)
    has_blank = any(v is None for v in vals)
    if not nums:
        a = ""
        if has_blank:
            a += ' containsBlank="1"'
        return f"<sharedItems{a}/>"
    lo, hi = min(nums), max(nums)
    if is_date:
        if has_str or has_blank:
            a = ' containsDate="1" containsMixedTypes="1"' if has_str else ' containsNonDate="0" containsDate="1" containsString="0" containsBlank="1"'
        else:
            a = ' containsSemiMixedTypes="0" containsNonDate="0" containsDate="1" containsString="0"'
        return f'<sharedItems{a} minDate="{iso(lo)}" maxDate="{iso(math.floor(hi) + 1)}"/>'
    integer = all(float(v).is_integer() for v in nums)
    if has_str or has_blank:
        a = ' containsMixedTypes="1"' if has_str else ' containsString="0" containsBlank="1"'
        a += ' containsNumber="1"'
    else:
        a = ' containsSemiMixedTypes="0" containsString="0" containsNumber="1"'
    if integer:
        a += ' containsInteger="1"'
    return f'<sharedItems{a} minValue="{num_text(lo)}" maxValue="{num_text(hi)}"/>'


def write_pivot_records(zout, name, rec_head, cached_cols, items, date_fields):
    n = len(cached_cols[0])
    ncol = len(cached_cols)
    with zout.open(name, "w", force_zip64=True) as raw:
        out = _Writer(raw)
        out.write(re.sub(r'count="\d+"', f'count="{n}"', rec_head, count=1))
        for i in range(n):
            parts = ["<r>"]
            for j in range(ncol):
                v = cached_cols[j][i]
                if j in items:
                    parts.append(f'<x v="{items[j][1]["" if v is None else str(v)]}"/>')
                elif v is None:
                    parts.append("<m/>")
                elif isinstance(v, str):
                    parts.append(f'<s v="{xml_text(v)}"/>')
                elif j in date_fields:
                    parts.append(f'<d v="{iso(v)}"/>')
                else:
                    parts.append(f'<n v="{num_text(v)}"/>')
            parts.append("</r>")
            out.write("".join(parts))
        out.write("</pivotCacheRecords>")
        out.flush()


def _items_xml(sorted_cache_idx):
    return (f'<items count="{len(sorted_cache_idx) + 1}">' + "".join(f'<item x="{x}"/>' for x in sorted_cache_idx)
            + '<item t="default"/></items>')


def _axis_items_xml(tag, positions):
    parts = [f'<{tag} count="{len(positions) + 1}">']
    for p in positions:
        parts.append("<i><x/></i>" if p == 0 else f'<i><x v="{p}"/></i>')
    parts.append(f'<i t="grand"><x/></i></{tag}>')
    return "".join(parts)


def build_dashboard(sheet_xml, old_sst, sst, pts_xml, ar, items, fy):
    """Regenerates the 4 pivot tables (XML) and their rendered cells on the sheet."""
    pre, data, post = split_sheet(sheet_xml)
    rows = parse_rows(data)
    names_items, name_idx = items[39]
    # A-Z item lists (cache indices) per item field
    sorted_idx = {f: sorted(range(len(items[f][0])), key=lambda i, f=f: (excel_text_key(items[f][0][i]), i)) for f in items}
    pos_in_sorted = {f: {ci: p for p, ci in enumerate(sorted_idx[f])} for f in items}

    cust = ar["Customer Name"].map(lambda v: "" if is_blank(v) else str(v))
    cur = ar["Current Non-GRN Amt"].astype(float)
    days = pd.to_numeric(ar["Days to GRN"], errors="coerce")
    customers_az = [names_items[i] for i in sorted_idx[39]]

    def rank_desc(score):          # descending by score, ties A-Z (errors/NaN last)
        return sorted(customers_az, key=lambda c: (math.isnan(score[c]) if isinstance(score[c], float) else False,
                                                   -(score[c] if not (isinstance(score[c], float) and math.isnan(score[c])) else 0),
                                                   excel_text_key(c)))

    results = {}
    new_pts = {}
    for key, xml in pts_xml.items():
        name = attr(re.search(r"<pivotTableDefinition[^>]*>", xml).group(0), "name")
        loc = re.search(r'<location ref="([A-Z]+)(\d+):([A-Z]+)(\d+)"', xml)
        c0, r0 = col_number(loc.group(1)), int(loc.group(2))
        col_field = re.search(r'<colFields count="1"><field x="(-?\d+)"/></colFields>', xml)
        col_field = int(col_field.group(1)) if col_field else -2
        data_fields = re.findall(r'<dataField name="([^"]*)" fld="(\d+)"(?: subtotal="(\w+)")?', xml)
        res = {"name": name, "c0": c0, "r0": r0, "col_field": col_field, "data_fields": data_fields}
        if col_field >= 0:                                    # Customer x (bucket | GRN source)
            fld = int(data_fields[0][1])
            colname = ar.columns[col_field]
            cats = ar[colname].map(lambda v: "" if is_blank(v) else str(v))
            present = sorted({pos_in_sorted[col_field][items[col_field][1][c]] for c in cats.unique()})
            col_labels = [items[col_field][0][sorted_idx[col_field][p]] for p in present]
            grp = ar.iloc[:, fld].astype(float).groupby([cust, cats]).sum()
            totals = ar.iloc[:, fld].astype(float).groupby(cust).sum()
            order = rank_desc({c: totals.get(c, 0.0) for c in customers_az})
            matrix = {c: [grp.get((c, lab)) for lab in col_labels] for c in order}
            res.update(kind="cross", col_positions=present, col_labels=col_labels, order=order, matrix=matrix,
                       row_total={c: float(totals[c]) for c in order},
                       col_total=[float(ar.iloc[:, fld].astype(float)[cats == lab].sum()) for lab in col_labels],
                       grand=float(ar.iloc[:, fld].astype(float).sum()))
        else:                                                 # Customer x several data fields
            cols = []
            for dname, fld, sub in data_fields:
                fld = int(fld)
                if sub == "average":
                    s = days if ar.columns[fld] == "Days to GRN" else pd.to_numeric(ar.iloc[:, fld], errors="coerce")
                    per = s.groupby(cust).mean()
                    cols.append((dname, {c: (float(per.get(c)) if not pd.isna(per.get(c)) else ERR) for c in customers_az},
                                 float(s.mean()) if s.notna().any() else ERR))
                elif sub == "max":
                    s = pd.to_numeric(ar.iloc[:, fld], errors="coerce")
                    per = s.groupby(cust).max()
                    cols.append((dname, {c: (float(per.get(c)) if not pd.isna(per.get(c)) else 0.0) for c in customers_az},
                                 float(s.max()) if s.notna().any() else 0.0))
                elif sub == "count":
                    s = ar.iloc[:, fld].map(lambda v: not is_blank(v) and v != "")
                    per = s.groupby(cust).sum()
                    cols.append((dname, {c: int(per.get(c, 0)) for c in customers_az}, int(s.sum())))
                else:
                    s = ar.iloc[:, fld].astype(float)
                    per = s.groupby(cust).sum()
                    cols.append((dname, {c: float(per.get(c, 0.0)) for c in customers_az}, float(s.sum())))
            if 'sortType="descending"' in xml:
                first = cols[0][1]
                order = rank_desc({c: (first[c] if not isinstance(first[c], str) else float("nan")) for c in customers_az})
            else:
                order = list(customers_az)
            res.update(kind="fields", cols=cols, order=order)
        results[key] = res

        # ---- pivot table XML ----
        pfs = _split_elements(xml[xml.index("<pivotFields"):xml.index("</pivotFields>")], "pivotField")
        base = xml.index("<pivotFields")
        new_xml, cursor = [], 0
        for f_i, m in enumerate(pfs):
            el = m.group(0)
            if f_i in items and "<items" in el:
                el = re.sub(r"<items\b[^>]*>.*?</items>", _items_xml(sorted_idx[f_i]), el, flags=re.S)
            new_xml.append(xml[cursor:base + m.start()] if cursor else xml[:base + m.start()])
            new_xml.append(el)
            cursor = base + m.end()
        new_xml.append(xml[cursor:])
        xml2 = "".join(new_xml)
        row_pos = [pos_in_sorted[39][name_idx[c]] for c in res["order"]]
        xml2 = re.sub(r"<rowItems\b[^>]*>.*?</rowItems>", _axis_items_xml("rowItems", row_pos), xml2, flags=re.S)
        if res["kind"] == "cross":
            xml2 = re.sub(r"<colItems\b[^>]*>.*?</colItems>", _axis_items_xml("colItems", res["col_positions"]), xml2, flags=re.S)
            ncols = len(res["col_labels"]) + 1
            last_row = r0 + 1 + len(res["order"]) + 1
        else:
            ncols = len(res["cols"])
            last_row = r0 + len(res["order"]) + 1
        res["last_row"], res["ncols"] = last_row, ncols
        xml2 = re.sub(r'<location ref="[^"]*"', f'<location ref="{loc.group(1)}{r0}:{col_letter(c0 + ncols)}{last_row}"', xml2, count=1)
        new_pts[key] = xml2

    # ---- rendered cells (rows >= first pivot row are rebuilt) ----
    top = min(r["r0"] for r in results.values())

    def tstyle(r, c):
        if r in rows:
            for col, attrs, inner in rows[r][1]:
                if col_number(col) == c:
                    return attr(attrs, "s")
        return None

    def tlabel(r, c):
        if r in rows:
            for col, attrs, inner in rows[r][1]:
                if col_number(col) == c:
                    return cell_value(attrs, inner, old_sst)
        return None

    grid = defaultdict(dict)
    for res in results.values():
        c0, r0 = res["c0"], res["r0"]
        s_hdr = tstyle(r0, c0)
        if res["kind"] == "cross":
            s_lab, s_val = tstyle(r0 + 2, c0), tstyle(r0 + 2, c0 + 1)
            grid[r0][c0] = ("s", tlabel(r0, c0), s_hdr)
            grid[r0][c0 + 1] = ("s", tlabel(r0, c0 + 1), tstyle(r0, c0 + 1))
            grid[r0 + 1][c0] = ("s", tlabel(r0 + 1, c0), tstyle(r0 + 1, c0))
            for k, lab in enumerate(res["col_labels"] + ["Grand Total"]):
                grid[r0 + 1][c0 + 1 + k] = ("s", lab, None)
            r = r0 + 2
            for c in res["order"]:
                grid[r][c0] = ("s", c, s_lab)
                for k, v in enumerate(res["matrix"][c]):
                    grid[r][c0 + 1 + k] = ("n", v, s_val)
                grid[r][c0 + 1 + len(res["col_labels"])] = ("n", res["row_total"][c], s_val)
                r += 1
            grid[r][c0] = ("s", "Grand Total", s_lab)
            for k, v in enumerate(res["col_total"]):
                grid[r][c0 + 1 + k] = ("n", v, s_val)
            grid[r][c0 + 1 + len(res["col_labels"])] = ("n", res["grand"], s_val)
        else:
            s_lab, s_val = tstyle(r0 + 1, c0), tstyle(r0 + 1, c0 + 1)
            grid[r0][c0] = ("s", tlabel(r0, c0), s_hdr)
            for k, (dname, _, _) in enumerate(res["cols"]):
                grid[r0][c0 + 1 + k] = ("s", dname, tstyle(r0, c0 + 1 + k))
            r = r0 + 1
            for c in res["order"]:
                grid[r][c0] = ("s", c, s_lab)
                for k, (_, per, _) in enumerate(res["cols"]):
                    grid[r][c0 + 1 + k] = ("n", per[c], tstyle(r0 + 1, c0 + 1 + k))
                r += 1
            grid[r][c0] = ("s", "Grand Total", s_lab)
            for k, (_, _, g) in enumerate(res["cols"]):
                grid[r][c0 + 1 + k] = ("n", g, tstyle(r0 + 1, c0 + 1 + k))

    out = []
    for r in sorted(rows):
        if r >= top:
            break
        rattrs, cl = rows[r]
        out.append(f"<row {rattrs}>" + "".join(remap_cell(c, r, a, x, old_sst, sst) for c, a, x in cl) + "</row>")
    last = max(grid)
    for r in range(top, last + 1):
        if r not in grid:
            continue
        parts = [row_open(r, rows[r][0] if r in rows else None)]
        for c in sorted(grid[r]):
            kind, v, s = grid[r][c]
            ref = f"{col_letter(c)}{r}"
            if kind == "s":
                parts.append(c_str(ref, "" if v is None else str(v), sst, s))
            elif v is None:
                parts.append(c_blank(ref, s) or f'<c r="{ref}"/>')
            elif isinstance(v, str):
                st = f' s="{s}"' if s is not None else ""
                parts.append(f'<c r="{ref}"{st} t="e"><v>{v}</v></c>')
            else:
                parts.append(c_num(ref, v, s))
        parts.append("</row>")
        out.append("".join(parts))
    max_col = max(max(g) for g in grid.values())
    pre = set_dimension(pre, f"A1:{col_letter(max(max_col, 39))}{last}")
    return pre + "<sheetData>" + "".join(out) + "</sheetData>" + post, new_pts


def build_slicer_cache(xml, items, field_index):
    order, seen = items[field_index]
    idx = sorted(range(len(order)), key=lambda i: (excel_text_key(order[i]), i))
    body = f'<items count="{len(idx)}">' + "".join(f'<i x="{i}" s="1"/>' for i in idx) + "</items>"
    return re.sub(r"<items\b[^>]*>.*?</items>", body, xml, count=1, flags=re.S)


# ==========================================================================
# workbook assembly
# ==========================================================================
def _sheet_files(z):
    wb = z.read("xl/workbook.xml").decode("utf-8")
    rels = z.read("xl/_rels/workbook.xml.rels").decode("utf-8")
    targets = {}
    for m in re.finditer(r"<Relationship\b[^>]*>", rels):
        tag = m.group(0)
        targets[attr(tag, "Id")] = attr(tag, "Target")
    out = {}
    for m in re.finditer(r"<sheet\b[^>]*/>", wb):
        tag = m.group(0)
        out[_unescape(attr(tag, "name"))] = "xl/" + targets[re.search(r'r:id="([^"]+)"', tag).group(1)].lstrip("/").replace("xl/", "")
    return out


def build_workbook(template: Path, out_path: Path, tables: dict, ar: pd.DataFrame, snaps, fy, as_on: dt.date,
                   manual_rows: list, progress=None):
    """Writes the full Non GRN Age workbook. manual_rows: [(invoice_no, date)] in sheet order."""
    def step(msg):
        if progress:
            progress(msg)

    sr, sr_prev, mda_prev, mda = tables["sr_current"], tables["sr_prev"], tables["mda_prev"], tables["mda"]
    n_cur = len(sr) - len(sr_prev)
    z = zipfile.ZipFile(template)
    old_sst = read_template_sst(z)
    sst = SharedStrings()
    files = _sheet_files(z)
    report_f, dash_f, combine_f = files["Report"], files["Customer Dashboard"], files["Combine"]
    srprev_f = files[f"SR FY {calc.FiscalYear(fy.start_year - 1).label[3:]}"]
    mdaprev_f = files[f"MDA FY {calc.FiscalYear(fy.start_year - 1).label[3:]}"]
    mda_f = files[f"MDA FY {fy.label[3:]}"]
    manual_f = files["Manual GRN"]
    sheet_last = {}
    tmp = out_path.with_suffix(".tmp")
    zout = zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True)
    written = set()
    try:
        # ---- Combine (data + 51 formula columns) ----
        step("Combine sheet")
        cached = combine_cached_values(sr, ar, n_cur)
        sheet_last["Combine"] = write_combine(zout, z, old_sst, sst, sr, ar, n_cur, snaps, as_on, cached, fy.months)
        written.add(combine_f)

        # ---- hidden / data sheets ----
        step("SR / MDA sheets")
        sheet_last[srprev_f] = write_table_sheet(zout, z, srprev_f, old_sst, sst, sr_prev, SR_COLUMNS, [(0, SR_PREV_FINAL)])
        mprev_cols = [c for c in template_header(z, mdaprev_f, old_sst)]
        sheet_last[mdaprev_f] = write_table_sheet(zout, z, mdaprev_f, old_sst, sst, mda_prev, mprev_cols, [(0, MDA_PREV_FINAL)])
        sheet_last[mda_f] = write_table_sheet(zout, z, mda_f, old_sst, sst, mda, MDA_COLUMNS,
                                              [(0, MDA_CUR_FINAL), (len(mda) - len(mda_prev), MDA_PREV_FINAL)])
        written |= {srprev_f, mdaprev_f, mda_f}

        # ---- Manual GRN ----
        manual_xml, sheet_last[manual_f] = build_manual_sheet(z.read(manual_f).decode("utf-8"), old_sst, sst, manual_rows)
        zout.writestr(manual_f, manual_xml)
        written.add(manual_f)

        # ---- Report ----
        step("Report")
        lakh = 100000.0
        explicit = report_explicit(ar, sr, fy, as_on, snaps, None, lakh)
        zout.writestr(report_f, build_report_sheet(z.read(report_f).decode("utf-8"), old_sst, sst, explicit))
        written.add(report_f)

        # ---- pivot cache ----
        step("Pivot cache")
        cd_name = "xl/pivotCache/pivotCacheDefinition1.xml"
        rec_name = "xl/pivotCache/pivotCacheRecords1.xml"
        cd_xml = z.read(cd_name).decode("utf-8")
        item_fields = {39, 40, 41, 46, 50}
        now_serial = round(serial(dt.datetime.now()), 8)
        cd_new, items = build_pivot_cache(cd_xml, cached, item_fields, now_serial)
        zout.writestr(cd_name, cd_new)
        date_fields = {j for j, m in enumerate(_split_elements(cd_xml, "cacheField"))
                       if attr(re.match(r"<cacheField\b[^>]*", m.group(0)).group(0), "numFmtId") in DATE_FMTS}
        with z.open(rec_name) as fh:
            head = fh.read(4000).decode("utf-8", "ignore")
        rec_head = head[:head.index("<r>")] if "<r>" in head else head[:head.index("</pivotCacheRecords>")]
        write_pivot_records(zout, rec_name, rec_head, cached, items, date_fields)
        written |= {cd_name, rec_name}

        # ---- pivot tables + dashboard ----
        step("Customer Dashboard")
        pt_names = [n for n in z.namelist() if re.fullmatch(r"xl/pivotTables/pivotTable\d+\.xml", n)]
        pts = {n: z.read(n).decode("utf-8") for n in pt_names}
        dash_xml, new_pts = build_dashboard(z.read(dash_f).decode("utf-8"), old_sst, sst, pts, ar, items, fy)
        zout.writestr(dash_f, dash_xml)
        for n, x in new_pts.items():
            zout.writestr(n, x)
        written |= set(pt_names) | {dash_f}
        field_by_name = {_unescape(attr(re.match(r"<cacheField\b[^>]*", m.group(0)).group(0), "name")): j
                         for j, m in enumerate(_split_elements(cd_xml, "cacheField"))}
        for n in z.namelist():
            if re.fullmatch(r"xl/slicerCaches/slicerCache\d+\.xml", n):
                x = z.read(n).decode("utf-8")
                src = _unescape(attr(re.search(r"<slicerCacheDefinition\b[^>]*>", x).group(0), "sourceName"))
                zout.writestr(n, build_slicer_cache(x, items, field_by_name[src]))
                written.add(n)

        # ---- tables ----
        rows_of = {"SR_FY_26_27": sheet_last["Combine"], "AR_Tax_Register___Detail_Report": sheet_last["Combine"],
                   "SR_FY_25_26": sheet_last[srprev_f], "MDA_FY_25_26": sheet_last[mdaprev_f], "MDA": sheet_last[mda_f]}
        for n in z.namelist():
            if re.fullmatch(r"xl/tables/table\d+\.xml", n):
                x = z.read(n).decode("utf-8")
                tname = attr(re.search(r"<table\b[^>]*>", x).group(0), "name")
                if tname in rows_of:
                    x = re.sub(r'(\bref="[A-Z]+\d+:[A-Z]+)\d+"', lambda m: f'{m.group(1)}{rows_of[tname]}"', x)
                zout.writestr(n, x)
                written.add(n)

        # ---- workbook.xml: defined names, full recalc on open ----
        wb = z.read("xl/workbook.xml").decode("utf-8")
        name_last = {"Combine": sheet_last["Combine"], "Manual GRN": sheet_last[manual_f]}
        for sname, f in files.items():
            if f in sheet_last:
                name_last[sname] = sheet_last[f]

        def fix_name(m):
            text = _unescape(m.group(2))
            ref = re.match(r"^'?(.*?)'?!\$([A-Z]+)\$(\d+):\$([A-Z]+)\$(\d+)$", text)
            if not ref or ref.group(1) not in name_last or int(ref.group(5)) <= 1:
                return m.group(0)
            new = f"{text[:text.rindex('$') + 1]}{name_last[ref.group(1)]}"
            return m.group(1) + xml_text(new).replace("&quot;", '"') + m.group(3)
        wb = re.sub(r"(<definedName\b[^>]*>)(.*?)(</definedName>)", fix_name, wb)
        wb = re.sub(r"<calcPr\b([^>]*?)/>", lambda m: "<calcPr" + re.sub(r'\s*fullCalcOnLoad="\d"', "", m.group(1)) + ' fullCalcOnLoad="1"/>', wb)
        zout.writestr("xl/workbook.xml", wb)
        written.add("xl/workbook.xml")

        # ---- drop calcChain (Excel rebuilds it) ----
        ct = z.read("[Content_Types].xml").decode("utf-8")
        ct = re.sub(r'<Override PartName="/xl/calcChain.xml"[^>]*/>', "", ct)
        zout.writestr("[Content_Types].xml", ct)
        rels = z.read("xl/_rels/workbook.xml.rels").decode("utf-8")
        rels = re.sub(r'<Relationship\b[^>]*Target="calcChain.xml"[^>]*/>', "", rels)
        zout.writestr("xl/_rels/workbook.xml.rels", rels)
        written |= {"[Content_Types].xml", "xl/_rels/workbook.xml.rels", "xl/calcChain.xml"}

        # ---- shared strings ----
        zout.writestr("xl/sharedStrings.xml", sst.xml())
        written.add("xl/sharedStrings.xml")

        # ---- everything else unchanged ----
        for info in z.infolist():
            if info.filename not in written:
                zout.writestr(info, z.read(info.filename))
    finally:
        zout.close()
        z.close()
    tmp.replace(out_path)
    return out_path
