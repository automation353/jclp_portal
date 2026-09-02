# RM Dashboard — the `combined` tab

`combined` is now the RM dashboard. It has **42 columns (A–AP)**. Row 1 is the
header row; row 2 onward is data. The data is entirely formula-driven — it
pulls from `rm_green_level`, `rm_consumption`, `mps_demand`, and
`stock_valuation`. No script writes to this tab.

## 1. Header row (paste into `combined` row 1)

Put each label into its lettered column:

| Col | Header |
| --- | --- |
| A | Sr No. |
| B | Location |
| C | RM Code |
| D | Tally Code |
| E | RM Specification |
| F | Grade |
| G | Component Item |
| H | Levels |
| I | Lead Time (Days) |
| J | Daily Consumption |
| K | Lead Time Consumption |
| L | Reorder Qty |
| M | MPS Demand |
| N | Green Level |
| O | Yellow Level |
| P | Red Level |
| Q | Opening |
| R | Receipt |
| S | Issued |
| T | Current Stock in Kg |
| U | Current Stock (Days) |
| V | Till Date inventory |
| W | Inventory Coverage |
| X | To be ordered Qty |
| Y | MIS |
| Z | Expected Arrival date |
| AA | Rate |
| AB | Amount |
| AC | RL Count |
| AD | YL Count |
| AE | GL Count |
| AF | BL Count |
| AG | Category |
| AH | GL Value |
| AI | Slow Moving |
| AJ | Excel Stock |
| AK | Difference |
| AL | Inventory Type |
| AM | Group |
| AN | Section |
| AO | Hardness |
| AP | Combined Grade |

## 2. Row-2 formulas (paste into `combined` row 2, then drag down)

Paste each formula into its cell in **row 2**. Once row 2 works, select row 2
and drag the fill-handle down to about **row 500** (comfortable buffer over
the ~100–200 real items). Empty rows will just show blanks.

| Cell | Formula |
| --- | --- |
| A2 | `=IF(D2="","",ROW()-1)` |
| B2 | `=IFERROR(rm_green_level!C2,"")` |
| C2 | `=IFERROR(rm_green_level!B2,"")` |
| D2 | `=IFERROR(rm_green_level!A2,"")` |
| E2 | `=IFERROR(rm_green_level!D2,"")` |
| F2 | `=IFERROR(rm_green_level!E2,"")` |
| G2 | `=IFERROR(rm_green_level!F2,"")` |
| H2 | `=IFERROR(VLOOKUP($C2,rm_consumption!$A:$D,4,FALSE),0)` |
| I2 | `=IFERROR(rm_green_level!I2,"")` |
| J2 | `=IF(H2=0,0,H2/15)` |
| K2 | `=IFERROR(rm_green_level!J2,"")` |
| L2 | `=IF((N2-T2)+K2<0,0,(N2-T2)+K2)` |
| M2 | `=IFERROR(VLOOKUP($D2,mps_demand!$A:$B,2,FALSE),0)` |
| N2 | `=IF(AL2="MTS",IF(H2>500,H2,0),0)` |
| O2 | `=N2*0.5` |
| P2 | `=N2*0.3` |
| Q2 | `=IFERROR(XLOOKUP($C2, INDEX(stock_valuation_columns!$A:$Z,0,MATCH("Item Code",stock_valuation_columns!$1:$1,0)), INDEX(stock_valuation_columns!$A:$Z,0,MATCH("Opening Qty (Base UOM)",stock_valuation_columns!$1:$1,0))), 0)` |
| R2 | `=IFERROR(XLOOKUP($C2, INDEX(stock_valuation_columns!$A:$Z,0,MATCH("Item Code",stock_valuation_columns!$1:$1,0)), INDEX(stock_valuation_columns!$A:$Z,0,MATCH("Receipts (Base UOM)",stock_valuation_columns!$1:$1,0))), 0)` |
| S2 | `=IFERROR(XLOOKUP($C2, INDEX(stock_valuation_columns!$A:$Z,0,MATCH("Item Code",stock_valuation_columns!$1:$1,0)), INDEX(stock_valuation_columns!$A:$Z,0,MATCH("Issues (Base UOM)",stock_valuation_columns!$1:$1,0))), 0)` |
| T2 | `=IFERROR(XLOOKUP($C2, INDEX(stock_valuation_columns!$A:$Z,0,MATCH("Item Code",stock_valuation_columns!$1:$1,0)), INDEX(stock_valuation_columns!$A:$Z,0,MATCH("Current Stock (Base UOM)",stock_valuation_columns!$1:$1,0))), 0)` |
| U2 | `=IF(J2=0,0,T2/J2)` |
| V2 | `=IF(T2>(H2*2),"HIGH INVENTORY",TODAY()+U2)` |
| W2 | `=IF(U2>365,"365 & Above",IF(U2>180,"180 to 365",IF(U2>120,"120 to 180",IF(U2>60,"60 to 120",IF(U2>30,"30 to 60",IF(U2>15,"15 to 30",IF(U2<15,"0 to 15",0)))))))` |
| X2 | `=IF(M2-T2+N2<0,0,M2-T2+N2)` |
| Y2 | `=IF(R2>X2,"Excess Procured",0)` |
| Z2 | *(leave blank — manual entry when there's an actual expected date)* |
| AA2 | *(leave blank or type the rate manually per item)* |
| AB2 | `=AA2*T2` |
| AC2 | `=IF(O2<500,0,IF(T2<P2,1,0))` |
| AD2 | `=IF(O2<300,0,IF(AND(T2>P2,T2<O2),1,0))` |
| AE2 | `=IF(O2<300,0,IF(AND(T2>O2,T2<N2),1,0))` |
| AF2 | `=IF(O2<300,0,IF(T2>N2,1,0))` |
| AG2 | `=IFERROR(VLOOKUP($C2,rm_consumption!$A:$D,3,FALSE),"")` |
| AH2 | `=AA2*N2` |
| AI2 | `=0` |
| AJ2 | `=IF(OR(AG2="Fast Moving",AG2="Medium Fast"),"MTS","MTO")` |
| AK2 | *(leave blank — unclear semantics in the original; add later if needed)* |
| AL2 | `=IF(OR(AG2="Fast Moving",AG2="Medium Fast"),"MTS","MTO")` |
| AM2 | `=IFERROR(rm_green_level!G2,"")` |
| AN2 | `=IFERROR(rm_green_level!H2,"")` |
| AO2 | *(leave blank — manual entry, e.g. "Soft" / "Hard")* |
| AP2 | `=IF(AM2="SS Coil",F2&" "&AO2,F2)` |

## 3. Prerequisite — DPR highlighting must include the stock columns

The dashboard reads from `stock_valuation_columns` (not the raw `stock_valuation`).
That tab only holds whatever columns you highlighted in the source stock_valuation
tab. So the highlighted-column set for DPR **must include all five** of these
exact column headers, or Q, R, S, T come out zero:

- `Item Code`  *(the join key)*
- `Opening Qty (Base UOM)`
- `Receipts (Base UOM)`
- `Issues (Base UOM)`
- `Current Stock (Base UOM)`

**To update the highlighted set:**

1. Open the `stock_valuation` tab. Highlight (any fill color) all five headers
   above, plus anything else you want in `stock_valuation_columns`.
2. In the Apps Script editor, run **`captureHighlightedColumnNames`**. Confirm
   the Execution log lists all five names.
3. Re-upload one DPR file so `stock_valuation_columns` refreshes with the
   expanded column set.
4. Open `stock_valuation_columns` and verify row 1 shows those five headers
   somewhere across the columns.

The formulas Q2–T2 are written with `XLOOKUP + INDEX + MATCH` so they don't
care which column-letter the field lives in — they look each field up by
header text. But the header text must match exactly (spaces, casing,
parentheses). If your DPR file uses slightly different spellings (e.g.
`Opening Qty (Base UOM) ` with a trailing space), edit the matching string
in the corresponding formula.

**Tally Code vs RM Code vs Item Code — same identifier, different names.**
The dashboard's C column ("RM Code") holds the same value as D ("Tally Code")
— they're the same physical identifier the source files just label
differently. The formulas above look up using `$C2` (which equals `$D2`); the
`stock_valuation_columns` file exposes it under the name `Item Code`, and
`XLOOKUP` finds it by matching that header text.

## 4. What drives the rows

The rows in `combined` correspond one-to-one with the rows in
`rm_green_level`. Whichever items exist there (after your latest RM Green
Level upload) become the visible dashboard rows. If `rm_green_level` grows
past row 500 later, just drag the formulas further down.

Column A auto-hides its serial number for empty rows: `=IF(D2="","",ROW()-1)`.

## 5. Manual-entry columns

- **Z (Expected Arrival date)**, **AA (Rate)**, **AO (Hardness)** — these are
  plain data-entry cells. Type values in when needed. They intentionally have
  no formula.
- **AI (Slow Moving)** — hardcoded 0 for now; we'll wire this to a
  `slow_moving_rm` tab in a later pass if you decide to feed that data in.
- **AK (Difference)** — left blank; the original file's meaning wasn't clear
  from the source formulas. Tell me the intended calculation and I'll add it.
