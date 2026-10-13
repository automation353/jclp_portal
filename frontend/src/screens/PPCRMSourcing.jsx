import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import TopBar from '../components/TopBar'
import { api } from '../api'
import { RULE_SPEC, PRINCIPLES } from './ruleSpec'

const N = (v) => { const x = parseFloat(String(v).replace(/,/g, '')); return Number.isFinite(x) ? x : 0 }
const fmt = (v) => N(v).toLocaleString('en-IN', { maximumFractionDigits: 0 })
const dec = (v) => N(v).toLocaleString('en-IN', { maximumFractionDigits: 2 })
function grade(d) { const s = (d || '').toUpperCase(); for (const g of ['304', '316', '201', '202', '430', '409']) if (s.includes(g)) return `SS ${g}`; return 'Other' }
function cpType(code) { const s = (code || '').toUpperCase(); if (s.startsWith('CP')) return 'Component'; if (s.startsWith('PK') || s.startsWith('BC') || s.startsWith('PC')) return 'Packing'; return 'Other' }

function Tile({ label, value, unit, kind = 'info', sub }) {
  return (
    <div className={`dash-tile dash-tile-${kind}`}>
      <div className="dash-tile-label">{label}</div>
      <div className="dash-tile-value">{value}{unit && <span style={{ fontSize: 13, fontWeight: 600 }}> {unit}</span>}</div>
      {sub && <div className="dash-tile-sub">{sub}</div>}
    </div>
  )
}

const TABS = [
  { key: 'bom', name: 'By Product (BOM)' },
  { key: 'rm', name: 'RM Req' },
  { key: 'cp', name: 'CP Req' },
  { key: 'rules', name: 'Rules' },
]

// ── Rules tracker (static) — the JCPL operating rules that govern RM Sourcing,
// grouped by band in build order. Status reflects what the module does TODAY.
// Pure presentation: no data fetch, no backend, read-only. ──────────────────
// Reuse the dashboard tile colour language (dash-tile-score/warn/blocked/info).
const STATUS = {
  live: { label: 'Live', bg: '#dcefdc', fg: '#1b5e20', dot: '#2e7d32', tint: '#eaf5ea' },
  partial: { label: 'Partial', bg: '#ffecb3', fg: '#e65100', dot: '#f6a800', tint: '#fff8e1' },
  pending: { label: 'Pending', bg: '#dfe4e8', fg: '#455a64', dot: '#607d8b', tint: '#eceff1' },
  input: { label: 'Input', bg: '#d6e8fb', fg: '#1565c0', dot: '#42a5f5', tint: '#f5f9fd' },
  out: { label: 'Other module', bg: '#e0e0e0', fg: '#546e7a', dot: '#b0bec5', tint: '#f6f7f8' },
}
const RULE_BANDS = [
  {
    band: 'Part D — Data, BOM & the RMCP sheet',
    note: 'The core of RM Sourcing: turn the plan into RM & CP requirement.',
    rules: [
      { id: 'R19', title: 'One part number, one description', short: 'Unique item code ↔ description; BOM child-weight revalidation.', status: 'partial', depends: 'Foundation — nothing above works on duplicate codes', needs: 'Dedup list + weight revalidation cycle (IT/ERP, Engineering)' },
      { id: 'R20', title: 'RMCP sheet: A–C downloaded, D–F calculated', short: 'A/B/C from BOM; D = plan-qty lookup; E = BOM qty × plan ÷ 1000; F = UOM.', status: 'live', depends: 'R19', needs: '—' },
      { id: 'R21', title: 'Aggregate RM, no double counting', short: 'SUMIF per RM by unique Item Code; compile view = "Where used".', status: 'live', depends: 'R20', needs: '—' },
      { id: 'R22', title: 'Review manual add-ons', short: 'Manual Reqd Qty tagged "PPC" vs "Computed" in RM Req; auto-inclusion to design.', status: 'partial', depends: 'R20', needs: 'Sept add-on reasons + scrap cases (PPC/Stores)' },
    ],
  },
  {
    band: 'Part E — Inventory levels',
    note: 'Net the requirement against stock & green levels → procurement.',
    rules: [
      { id: 'R23', title: 'Green hierarchy FG → child → RM', short: 'Multi-level FG→CP→RM roll-up live in By Product (RM direct + via CPs); FG plan netting is upstream in R3SS. RM-tier stock netting pending.', status: 'partial', depends: 'R21, R1', needs: 'RM opening stock, child-part green, safety buffer (Stores/PPC)' },
      { id: 'R24', title: 'In-house CP & critical RM at green; vendor CP differs', short: 'No RM green for vendor CP; critical RM (wire/coil) always in-house.', status: 'pending', depends: 'R12 (vendor commitment)', needs: 'In-house vs vendor CP list (Production/Purchase)' },
      { id: 'R25', title: 'Refill green level; customer-specific FG', short: 'Refill is a procurement trigger on the Order-now list.', status: 'pending', depends: 'R23', needs: 'Customer FG ratios, transport batch (Sales/Logistics)' },
      { id: 'R26', title: 'Size levels from sales data / turnover', short: 'Replaces 3-month averages; RM ≈ 60% of cost. LPP optional.', status: 'pending', depends: 'R2', needs: 'Clean sales history, cost structure (Sales/Finance)' },
      { id: 'R27', title: 'Packaging as an annual job', short: 'Packaging split out in CP Req (filter); annual-cycle planning pending.', status: 'partial', depends: '— (independent)', needs: 'White-label list, print lead time (Export/Purchase)' },
    ],
  },
  {
    band: 'Part A — Demand basis  (input · lives in R3SS / MpsSS)',
    note: 'Produced upstream; RM Sourcing consumes the plan quantity.',
    rules: [
      { id: 'R1', title: 'Plan qty = demand − (opening + green)', short: 'Comes in as R3SS to_plan — column D of the RMCP sheet.', status: 'input', depends: 'R23 (green definition)', needs: 'Live upstream' },
      { id: 'R2', title: 'Plan on live orders, not 3-month averages', short: 'Demand policy set upstream; module uses to_plan as given.', status: 'input', depends: '—', needs: 'Green granularity + MTS/MTO tag (PPC)' },
      { id: 'R3', title: 'Plan one month further out', short: 'Horizon set upstream; dashboard can default to month + 2.', status: 'input', depends: '—', needs: 'Live upstream' },
      { id: 'R4', title: 'Advance Nov–Dec & export visibility sheets', short: 'Purchase hand-off sheets; firm Nov released, Dec tentative.', status: 'out', depends: 'R5, R6', needs: 'Confirmed Nov–Dec + export orders (PPC/Sales)' },
    ],
  },
  {
    band: 'Part A — Lead time → dates  (future band)',
    note: 'Turns net requirement into procurement dates. Not started.',
    rules: [
      { id: 'R5', title: 'Trigger procurement early for high lead time', short: 'Reverse-calculate a procurement date per part.', status: 'pending', depends: 'R6, R11, R12', needs: 'RM lead times, special-process list (Purchase/PPC)' },
      { id: 'R6', title: 'Three prolongation lists', short: 'High-lead RM, special CP, shared-infra conversions.', status: 'pending', depends: '— (Purchase-maintained)', needs: 'The three lists (Purchase)' },
      { id: 'R7', title: 'Common-infrastructure trigger quantities', short: 'Flag shared machines; trigger on combined quantity.', status: 'pending', depends: '— (independent flag)', needs: 'Part combinations + thresholds (Purchase/Production)' },
      { id: 'R11', title: 'Keep external / inspection time out of mfg time', short: 'Separate bucket, used only in the backward date calc.', status: 'pending', depends: '— (independent bucket)', needs: 'Inspection customers + durations (Sales/QA)' },
    ],
  },
  {
    band: 'Part B — Capacity & manpower  (other module · PPC)',
    note: 'Production capacity rules — not RM Sourcing. Shown for the full spec.',
    rules: [
      { id: 'R8', title: 'Plan occupancy at 80%; above that, expand', short: 'Per-line ceiling; third shift is emergency only.', status: 'out', depends: 'R9', needs: 'Installed capacity per line (Production)' },
      { id: 'R9', title: 'Map product → infra; book capacity shift-wise', short: 'Re-allocate when a home line is over-demand.', status: 'out', depends: '—', needs: 'Product-to-infra map + tools (Production/Eng)' },
      { id: 'R10', title: 'Move manpower with load; cut-off below 15%', short: 'Consolidate residual load; auto cut-off + override.', status: 'out', depends: 'R9', needs: 'Utilisation + absenteeism (PPC/HR)' },
    ],
  },
  {
    band: 'Part C — Vendor management  (other module · Purchase)',
    note: 'Procurement & vendor rules — not RM Sourcing. R12 feeds R5 & R24.',
    rules: [
      { id: 'R12', title: 'No order without a written committed lead time', short: 'Vendor lead time in writing + D-day sign-off.', status: 'out', depends: '—', needs: 'Written vendor commitments (Purchase)' },
      { id: 'R13', title: 'Sanitise & document the vendor process chain', short: 'End-to-end chain + stress points before ordering.', status: 'out', depends: '—', needs: 'Vendor process maps (Purchase)' },
      { id: 'R14', title: 'Three quotes, release to lowest landed cost', short: 'Formal quotes, audit trail, break monopolies.', status: 'out', depends: '—', needs: 'Quotations (Purchase)' },
      { id: 'R15', title: 'Standardise the ~15-day procurement cycle', short: 'Fixed calendar, rate freeze, fixed lots.', status: 'out', depends: '—', needs: 'Cycle calendar (Purchase)' },
      { id: 'R16', title: 'Vendor stock in ERP by condition; reconcile', short: 'Issued = returned + scrap equivalent.', status: 'out', depends: '—', needs: 'Vendor stock feed (Purchase/Stores)' },
      { id: 'R17', title: 'Upgrade suppliers with inconsistent quality', short: 'Tighten checks + tool validation; replace if needed.', status: 'out', depends: '—', needs: 'Rejection history (QA/Purchase)' },
      { id: 'R18', title: 'Dedicated vehicle + worker-level follow-up', short: 'Vendor-site stock visibility posted into ERP.', status: 'out', depends: '—', needs: 'Freight cost-benefit (Purchase)' },
    ],
  },
  {
    band: 'Part F — Method & governance  (overlay)',
    note: 'Sit under every band; depend on nothing.',
    rules: [
      { id: 'R28', title: 'Document every rule before coding', short: 'This Rules tab is that live document.', status: 'live', depends: '—', needs: '—' },
      { id: 'R29', title: 'Cross-functional design + automation blueprint', short: 'Pros / cons + blueprint before rollout.', status: 'partial', depends: '—', needs: 'Impact plot + blueprint (cross-functional)' },
    ],
  },
]
const ruleCount = (s) => RULE_BANDS.reduce((a, b) => a + b.rules.filter(r => r.status === s).length, 0)

// Per-rule dashboards — each reads its own Google Sheet tab (or the live BOM
// check) and renders the real data behind that rule.
const RULE_DASH = {
  R1: { mode: 'r3ss', title: 'R1 — Plan qty = demand − (opening + green)',
    desc: 'The upstream plan inputs per FG, pulled live from R3SS.',
    kpi: rows => [
      { label: 'FGs', value: fmt(rows.length), kind: 'info' },
      { label: 'Total Demand', value: fmt(rows.reduce((a, r) => a + N(r['Total Demand']), 0)), kind: 'info' },
      { label: 'Total To Plan', value: fmt(rows.reduce((a, r) => a + N(r['To Plan']), 0)), kind: 'score' },
    ] },
  R2: { mode: 'r3ss', title: 'R2 — Plan on live orders · MTS / MTO tag',
    desc: 'Each part tagged MTS or MTO from the R3SS overlay — the classification R2 depends on.',
    kpi: rows => [
      { label: 'MTS', value: fmt(rows.filter(r => r['MTO/MTS'] === 'MTS').length), kind: 'score' },
      { label: 'MTO', value: fmt(rows.filter(r => r['MTO/MTS'] === 'MTO').length), kind: 'warn' },
      { label: 'NA / untagged', value: fmt(rows.filter(r => !r['MTO/MTS'] || r['MTO/MTS'] === 'NA').length), kind: 'info' },
    ] },
  R3: { mode: 'r3ss', title: 'R3 — Plan one month ahead',
    desc: 'Planning horizon from R3SS: reference = this month, buffer = next, target = month + 2.',
    kpi: (rows, meta) => [
      { label: 'Plan month', value: (meta && meta.plan_month) || '—', kind: 'info' },
      { label: 'FGs planned', value: fmt(rows.filter(r => N(r['To Plan']) > 0).length), kind: 'score' },
      { label: 'Total To Plan', value: fmt(rows.reduce((a, r) => a + N(r['To Plan']), 0)), kind: 'info' },
    ] },
  R19: { mode: 'dq', title: 'R19 — One part number, one description',
    desc: 'Live check over the uploaded BOM: every item code should map to exactly one description.' },
  R20: { tab: 'CP Req', title: 'R20 — RMCP sheet (A–C downloaded, D–F calculated)',
    desc: 'The explosion sheet: A/B/C from the BOM dump, D = plan-qty lookup, E = BOM qty × plan ÷ 1000, F = UOM.',
    kpi: rows => [
      { label: 'CP-Req lines', value: fmt(rows.length), kind: 'info' },
      { label: 'FGs exploded', value: fmt(new Set(rows.map(r => r['BOM Code'])).size), kind: 'score' },
      { label: 'RM lines', value: fmt(rows.filter(r => /^R(M|1)/i.test(r['Item Code'] || '')).length), kind: 'info' },
    ] },
  R21: { tab: 'RM QTY', title: 'R21 — Aggregate RM (SUMIF, no double counting)',
    desc: 'Each RM code appears once; its Qty = SUMIF of the CP-Req requirement across every FG that uses it.',
    kpi: rows => [
      { label: 'RM codes', value: fmt(rows.length), kind: 'info' },
      { label: 'Total RM Qty', value: fmt(rows.reduce((a, r) => a + N(r.Qty), 0)), unit: 'Kg', kind: 'score' },
    ] },
  R22: { tab: 'RM QTY', title: 'R22 — Manual add-ons (PPC vs Computed)',
    desc: 'Reqd Qty is the PPC head’s manual final — preserved and never overwritten by the automation.',
    kpi: rows => [
      { label: 'RM codes', value: fmt(rows.length), kind: 'info' },
      { label: 'Manual (PPC) overrides', value: fmt(rows.filter(r => (r['Reqd Qty (in kgs)'] || '').toString().trim()).length), kind: 'warn' },
    ] },
  R23: { tab: 'Against Demand RM', title: 'R23 — Net requirement after green (Against Demand RM)',
    desc: 'RM netting: Procurement = To Plan − Stock + Green × 0.6. Stock pending the Stores feed.',
    kpi: rows => [
      { label: 'RM codes', value: fmt(rows.length), kind: 'info' },
      { label: 'Total To Plan', value: fmt(rows.reduce((a, r) => a + N(r['To Plan']), 0)), unit: 'Kg', kind: 'score' },
      { label: 'Net Procurement', value: fmt(rows.reduce((a, r) => a + N(r.Procurement), 0)), unit: 'Kg', kind: 'warn' },
    ] },
  R27: { tab: 'Quantity Sheet', filter: 'packing', title: 'R27 — Packaging (annual job)',
    desc: 'Packaging items split out from components — plan these as a yearly print order.',
    kpi: rows => [{ label: 'Packing items', value: fmt(rows.length), kind: 'score' }] },
}
const NUMCOL = /qty|requirement|demand|plan|procurement|green|stock|\+10|nos|per kg/i

// Per-code calculation trace — shown for the LIVE/computed rules only. `codeCol`
// is the clickable column; `usage:true` pulls the SUMIF breakdown (the FG lines
// that sum to this code); otherwise `rows(row)` gives the row-level arithmetic.
const CALC = {
  R20: {
    codeCol: 'Item Code', formula: 'Qty (Base UOM) = BOM Qty × Qty in Nos ÷ 1000',
    rows: r => [
      ['BOM Qty (per 1000)', r['BOM Qty']],
      ['Qty in Nos (plan)', r['Qty in Nos']],
      [`= ${r['BOM Qty']} × ${r['Qty in Nos']} ÷ 1000`, r['Qty (Base UOM)']],
    ],
    source: 'One CP-Req line, exploded from the BOM against the R3SS plan.',
  },
  R21: { codeCol: 'Item Code', usage: true, resultCol: 'Qty',
    formula: 'Qty = SUMIF — Σ (plan × BOM qty ÷ 1000) over every FG that uses this RM',
    source: 'Aggregated from the CP Req tab by Item Code.' },
  R22: { codeCol: 'Item Code', usage: true, resultCol: 'Qty',
    formula: 'Qty = SUMIF(CP Req). Reqd Qty is a manual PPC override — not computed.',
    source: 'Computed Qty aggregated from CP Req; Reqd Qty entered by the PPC head.' },
  R23: {
    codeCol: 'Item Code', formula: 'Procurement = To Plan − Stock + Green × 0.6',
    rows: r => [
      ['To Plan', r['To Plan']],
      ['Stock', r['Stock'] || '0 (pending Stores feed)'],
      ['Green Level', r['Green Level']],
      [`= ${r['To Plan']} − ${N(r['Stock'])} + ${r['Green Level']} × 0.6`, r['Procurement']],
    ],
    source: 'To Plan from RM QTY; Green rolled up from R3SS; Stock pending.',
  },
  R27: { codeCol: 'Item Code', usage: true, resultCol: 'Qty (Base UOM)',
    formula: 'Qty (Base UOM) = SUMIF — Σ requirement over every FG that uses this item',
    source: 'Aggregated from the CP Req tab by Item Code.' },
}

function SlideOver({ title, onClose, children }) {
  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.35)', zIndex: 60, display: 'flex', justifyContent: 'flex-end' }}>
      <div onClick={e => e.stopPropagation()} style={{ width: 'min(600px,94vw)', background: '#fff', height: '100%', overflowY: 'auto', padding: 20, boxShadow: '-4px 0 16px rgba(0,0,0,.2)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ margin: 0 }}>{title}</h3>
          <button className="backbtn" onClick={onClose}>✕</button>
        </div>
        {children}
      </div>
    </div>
  )
}

function CalcPanel({ ruleId, code, row, onClose }) {
  const calc = CALC[ruleId]
  const [usage, setUsage] = useState(null)
  const [loading, setLoading] = useState(!!calc.usage)
  useEffect(() => {
    if (!calc.usage) return
    let alive = true; setLoading(true)
    api.rmSourcingUsage(code).then(d => { if (alive) setUsage(d.rows || []) }).catch(() => { }).finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [code])
  const total = usage ? usage.reduce((a, u) => a + N(u.requirement), 0) : 0
  return (
    <SlideOver title={<span>Calculation · <span style={{ fontFamily: 'monospace' }}>{code}</span></span>} onClose={onClose}>
      <div style={{ marginTop: 10, padding: '10px 12px', background: '#eef2f7', borderRadius: 8, fontSize: 13, fontWeight: 600, color: 'var(--steel)' }}>{calc.formula}</div>
      <p className="sub" style={{ fontSize: 12.5, marginTop: 8 }}>{calc.source}</p>
      {calc.usage ? (
        loading ? <div>Loading from Google Sheet…</div> : !usage || usage.length === 0 ? <div className="sub">No source lines found.</div> : (<>
          <div style={{ fontSize: 13, margin: '10px 0 6px' }}>Result = <b>{dec(row[calc.resultCol] || total)}</b> = sum of {usage.length} FG lines below:</div>
          <table className="mto-table" style={{ width: '100%' }}>
            <thead><tr><th>FG / BOM Code</th><th className="num">Planned</th><th className="num">× BOM ÷ 1000</th></tr></thead>
            <tbody>
              {usage.map((u, i) => <tr key={i}>
                <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{u.bom_code}</td>
                <td className="num">{fmt(u.planned_qty)}</td>
                <td className="num">{dec(u.requirement)}</td>
              </tr>)}
              <tr><td style={{ fontWeight: 700 }}>Total</td><td></td><td className="num" style={{ fontWeight: 800, color: 'var(--accent)' }}>{dec(total)}</td></tr>
            </tbody>
          </table>
        </>)
      ) : (
        <table className="mto-table" style={{ width: '100%', marginTop: 10 }}>
          <tbody>
            {calc.rows(row).map(([label, val], i, arr) => <tr key={i} style={i === arr.length - 1 ? { fontWeight: 700 } : undefined}>
              <td className="mono" style={{ fontSize: 12.5 }}>{label}</td>
              <td className="num" style={i === arr.length - 1 ? { fontWeight: 800, color: 'var(--accent)' } : undefined}>{val}</td>
            </tr>)}
          </tbody>
        </table>
      )}
    </SlideOver>
  )
}

function DqView({ dq }) {
  if (!dq || !dq.ok) return <div>No BOM uploaded yet.</div>
  const clean = !dq.conflicting_desc_count && !dq.blank_desc_count
  return (<>
    <div className="dash-tile-grid">
      <Tile label="Item codes" value={fmt(dq.total_items)} kind="info" />
      <Tile label="Conflicting descriptions" value={dq.conflicting_desc_count} kind={dq.conflicting_desc_count ? 'critical' : 'score'} />
      <Tile label="Blank descriptions" value={dq.blank_desc_count} kind={dq.blank_desc_count ? 'warn' : 'score'} />
    </div>
    {clean ? <p className="sub" style={{ marginTop: 14, fontSize: 13 }}>✓ Every item code maps to exactly one description — R19 is clean.</p> : (
      <div style={{ overflowX: 'auto', marginTop: 12 }}>
        <table className="mto-table" style={{ minWidth: 560 }}>
          <thead><tr><th>Item Code</th><th>Issue</th><th>Descriptions</th></tr></thead>
          <tbody>
            {(dq.conflicting_desc || []).map((c, i) => <tr key={'c' + i}><td style={{ fontFamily: 'monospace', fontSize: 12 }}>{c.code}</td><td><span className="r3ss-na">conflict</span></td><td className="desc-wrap">{c.descriptions.join('  |  ')}</td></tr>)}
            {(dq.blank_desc || []).map((c, i) => <tr key={'b' + i}><td style={{ fontFamily: 'monospace', fontSize: 12 }}>{c}</td><td><span className="r3ss-na">blank</span></td><td>—</td></tr>)}
          </tbody>
        </table>
      </div>
    )}
  </>)
}

function ExBox({ title, body }) {
  return (
    <div style={{ border: '1px solid #e2e8f0', borderRadius: 8, padding: '10px 12px', background: '#fff' }}>
      <div style={{ fontWeight: 700, fontSize: 11, color: 'var(--muted)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '.03em' }}>{title}</div>
      <pre style={{ margin: 0, fontFamily: 'ui-monospace,monospace', fontSize: 11.5, whiteSpace: 'pre-wrap', lineHeight: 1.5, color: 'var(--steel)' }}>{body}</pre>
    </div>
  )
}
function SpecSection({ spec }) {
  if (!spec) return null
  return (
    <div className="rule-band" style={{ marginTop: 18 }}>
      <h3 className="rule-band-head">Spec &amp; test cases</h3>
      <p className="rule-band-note">{spec.rule}</p>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, margin: '0 0 14px 12px' }}>
        {spec.principles.map(p => <span key={p} className="rule-badge" style={{ background: '#eef2f7', color: 'var(--steel)', textTransform: 'none', letterSpacing: 0 }}>P{p} · {PRINCIPLES[p]}</span>)}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(280px,1fr))', gap: 12 }}>
        <ExBox title="Test case 1" body={spec.ex1} />
        <ExBox title="Test case 2" body={spec.ex2} />
      </div>
      <div style={{ marginTop: 12, fontSize: 12.5, lineHeight: 1.45 }}><b>Validation:</b> {spec.validation}</div>
      <div style={{ marginTop: 8, fontSize: 12.5, padding: '8px 10px', background: '#eef7ef', borderRadius: 6, borderLeft: '3px solid #2e7d32' }}><b>Monthly check:</b> {spec.check}</div>
    </div>
  )
}

function RuleDash({ ruleId, onBack }) {
  const cfg = RULE_DASH[ruleId]
  const spec = RULE_SPEC[ruleId]
  const bandRule = RULE_BANDS.flatMap(b => b.rules).find(r => r.id === ruleId)
  const title = cfg ? cfg.title : `${ruleId} — ${bandRule ? bandRule.title : ''}`
  const [rows, setRows] = useState([])
  const [dq, setDq] = useState(null)
  const [sheetUrl, setSheetUrl] = useState('')
  const [meta, setMeta] = useState({})
  const [loading, setLoading] = useState(!!cfg)
  const [q, setQ] = useState('')
  const [calc, setCalc] = useState(null)   // per-code calculation trace
  const calcCfg = CALC[ruleId]
  useEffect(() => {
    if (!cfg) { setLoading(false); return }
    let alive = true; setLoading(true)
    const run = cfg.mode === 'dq'
      ? api.rmSourcingDataQuality().then(d => { if (alive) setDq(d) })
      : cfg.mode === 'r3ss'
        ? api.rmSourcingR3ss().then(d => { if (!alive) return; setRows(d.rows || []); setMeta({ plan_month: d.plan_month }) })
        : api.rmSourcingTab(cfg.tab).then(d => {
          if (!alive) return
          let rs = d.rows || []
          if (cfg.filter === 'packing') rs = rs.filter(r => cpType(r['Item Code']) === 'Packing')
          setRows(rs); setSheetUrl(d.sheet_url || '')
        })
    run.catch(() => { }).finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [ruleId])

  const cols = rows.length ? Object.keys(rows[0]).filter(k => k) : []
  const s = q.toLowerCase()
  const shown = rows.filter(r => !s || cols.some(c => (r[c] || '').toString().toLowerCase().includes(s)))
  const kpis = cfg && cfg.kpi ? cfg.kpi(rows, meta) : [{ label: 'Rows', value: fmt(rows.length), kind: 'info' }]
  const srcLabel = cfg && cfg.mode === 'r3ss' ? 'live from R3SS' : (cfg ? `live from “${cfg.tab}”` : '')

  return (
    <div style={{ marginTop: 4 }}>
      <button className="backbtn" onClick={onBack}>← Back to Rules</button>
      <h3 style={{ margin: '12px 0 2px' }}>{title}</h3>
      <p className="sub" style={{ fontSize: 13, margin: '0 0 12px' }}>
        {cfg ? cfg.desc : (spec ? spec.rule : '')}
        {cfg && !cfg.mode && <> · <span style={{ color: 'var(--muted)' }}>live from Google Sheet tab “{cfg.tab}”</span></>}
        {cfg && cfg.mode === 'r3ss' && <> · <span style={{ color: 'var(--muted)' }}>live from R3SS</span></>}
        {sheetUrl && <> · <a href={sheetUrl} target="_blank" rel="noopener noreferrer">open sheet</a></>}
      </p>
      {cfg && (loading ? <div>Loading…</div> : cfg.mode === 'dq' ? <DqView dq={dq} /> : (<>
        <div className="dash-tile-grid">{kpis.map((t, i) => <Tile key={i} {...t} />)}</div>
        {calcCfg && <p className="sub" style={{ fontSize: 12.5, marginTop: 10 }}>💡 Click a code to see how its value was calculated and from which data.</p>}
        <Filters s={q} set={setQ} ph="Search" note={`${shown.length} of ${rows.length} rows · ${srcLabel}`} />
        <div style={{ overflowX: 'auto', marginTop: 10 }}>
          <table className="mto-table" style={{ minWidth: 760 }}>
            <thead><tr>{cols.map(c => <th key={c} className={NUMCOL.test(c) ? 'num' : undefined}>{c}</th>)}</tr></thead>
            <tbody>
              {shown.length === 0 ? <tr><td colSpan={cols.length || 1}>No rows in this sheet tab.</td></tr> :
                shown.slice(0, 1000).map((r, i) => <tr key={i}>
                  {cols.map(c => {
                    const val = (r[c] || '').toString().replace(/\u00a0/g, ' ')
                    if (calcCfg && c === calcCfg.codeCol) return (
                      <td key={c}><button onClick={() => setCalc(r)} style={{ background: 'none', border: 'none', padding: 0, color: 'var(--accent)', cursor: 'pointer', fontFamily: 'monospace', fontSize: 12, textDecoration: 'underline' }}>{val}</button></td>
                    )
                    return <td key={c} className={NUMCOL.test(c) ? 'num' : (/desc/i.test(c) ? 'desc-wrap' : undefined)} style={/code/i.test(c) ? { fontFamily: 'monospace', fontSize: 12 } : undefined}>{val}</td>
                  })}
                </tr>)}
            </tbody>
          </table>
        </div>
        {shown.length > 1000 && <p className="sub" style={{ fontSize: 12, marginTop: 6 }}>Showing first 1,000 rows.</p>}
      </>))}
      <SpecSection spec={spec} />
      {calc && calcCfg && <CalcPanel ruleId={ruleId} code={calc[calcCfg.codeCol]} row={calc} onClose={() => setCalc(null)} />}
    </div>
  )
}

export default function PPCRMSourcing() {
  const fileRef = useRef(null)
  const [view, setView] = useState('bom')
  const [fgs, setFgs] = useState([])
  const [rmq, setRmq] = useState([])
  const [cp, setCp] = useState([])
  const [sheetUrl, setSheetUrl] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)
  const [search, setSearch] = useState('')
  const [open, setOpen] = useState(() => new Set())
  const [drill, setDrill] = useState(null)
  const [dq, setDq] = useState(null)          // R19 data-quality check
  const [cpFilter, setCpFilter] = useState('all')   // R27 All / Components / Packing
  const [ruleView, setRuleView] = useState(null)    // open per-rule dashboard

  async function load() {
    setLoading(true)
    try {
      const [a, b, c, q] = await Promise.all([
        api.rmSourcingByBom(), api.rmSourcingQuantity(), api.rmSourcingCpReq(),
        api.rmSourcingDataQuality().catch(() => null),
      ])
      setFgs(a.rows || []); setRmq(b.rows || []); setCp(c.rows || []); setSheetUrl(a.sheet_url || ''); setDq(q || null)
    } catch { setFgs([]); setRmq([]); setCp([]) }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  async function onFile(e) {
    const file = e.target.files?.[0]; e.target.value = ''
    if (!file) return
    setBusy(true); setMsg(null)
    try { const r = await api.ppcDataUpload(file, '', 'bom'); const b = r.bom || {}
      setMsg(b.ok ? { ok: true, text: `BOM uploaded — ${fmt(b.total_rows)} P1 rows.` } : { ok: false, text: `Not synced: ${b.error}` })
      if (b.ok) load()
    } catch (err) { setMsg({ ok: false, text: err.message }) } finally { setBusy(false) }
  }
  async function onRecompute() {
    setBusy(true); setMsg(null)
    try { const r = await api.rmSourcingRecompute()
      setMsg(r.ok ? { ok: true, text: `Recomputed — ${r.planned_parents} FGs, ${r.rm_items} RM.` } : { ok: false, text: r.error })
      if (r.ok) load()
    } catch (err) { setMsg({ ok: false, text: err.message }) } finally { setBusy(false) }
  }
  async function openDrill(code) {
    setDrill({ code, rows: [], loading: true })
    try { setDrill({ code, rows: (await api.rmSourcingUsage(code)).rows || [], loading: false }) }
    catch { setDrill({ code, rows: [], loading: false }) }
  }
  function toggle(c) { setOpen(p => { const n = new Set(p); n.has(c) ? n.delete(c) : n.add(c); return n }) }

  // ---- derived per view ----
  // RM QTY matches the reference columns: Qty (computed), Reqd Qty (PPC head's
  // manual final — preserved across recomputes), Qty +10% helper. No green here:
  // the reference carries green only in the Against Demand tabs.
  const rmView = useMemo(() => rmq.map(r => ({
    code: r['Item Code'] || r['RM Code'], desc: r.Description,
    qty: N(r.Qty), reqd: (r['Reqd Qty (in kgs)'] || r['Reqd Qty'] || '').trim(), d10: N(r['Qty +10%']),
    grade: grade(r.Description),
  })), [rmq])
  // Full Quantity Sheet columns: Qty (Base UOM) computed; qty per kg + Reqd Qty
  // manual; the two "Qty in nos" columns auto-calc once qty per kg is entered.
  const cpView = useMemo(() => cp.map(r => ({
    code: r['Item Code'], desc: r.Description, uom: r.UOM,
    req: N(r['Qty (Base UOM)'] ?? r.Requirement),
    qpk: (r['qty per kg'] || '').toString().trim(),
    nosErp: (r['Qty in nos (ERP)'] || '').toString().trim(),
    reqd: (r['Reqd Qty'] || '').toString().trim(),
    nosCorr: (r['Qty in nos (Correction)'] || '').toString().trim(),
    type: cpType(r['Item Code']),
  })), [cp])

  const s = search.toLowerCase()
  const fgF = fgs.filter(r => !s || [r.bom_code, r.family, r.customer, r.erp_code].some(x => (x || '').toLowerCase().includes(s)))
    .sort((a, b) => N(b.rm_demand) - N(a.rm_demand))
  const rmF = rmView.filter(r => !s || r.code.toLowerCase().includes(s) || (r.desc || '').toLowerCase().includes(s))
    .sort((a, b) => b.qty - a.qty)
  const cpF = cpView
    .filter(r => cpFilter === 'all' || (cpFilter === 'pack' ? r.type === 'Packing' : r.type !== 'Packing'))
    .filter(r => !s || r.code.toLowerCase().includes(s) || (r.desc || '').toLowerCase().includes(s))
    .sort((a, b) => b.req - a.req)

  // Rules tab — live metrics proving each applied rule, + the tab it drills to.
  const cpLines = fgs.reduce((a, b) => a + (b.parts ? b.parts.length : 0), 0)
  const rmKg = rmq.reduce((a, r) => a + N(r.Qty), 0)
  const manualOverrides = rmq.filter(r => (r['Reqd Qty (in kgs)'] || r['Reqd Qty'] || '').toString().trim()).length
  const packCount = cp.filter(r => cpType(r['Item Code']) === 'Packing').length
  const viaCpFgs = fgs.filter(b => N(b.rm_via_cp)).length
  const liveData = {
    R20: { stat: `${fmt(fgs.length)} FGs exploded · ${fmt(cpLines)} CP-Req lines`, tab: 'bom' },
    R21: { stat: `${rmq.length} RM codes · ${fmt(rmKg)} Kg aggregated`, tab: 'rm' },
    R22: { stat: `${manualOverrides} manual (PPC) overrides of ${rmq.length}`, tab: 'rm' },
    R23: { stat: `FG→CP→RM hierarchy · ${fmt(viaCpFgs)} FGs roll RM via CPs`, tab: 'bom' },
    R27: { stat: `${fmt(packCount)} packing items (annual job)`, tab: 'cp' },
  }

  return (
    <section className="screen">
      <TopBar subtitle="PPC Department" />
      <div className="wrap">
        <div className="crumbs"><Link to="/departments">Home</Link> › <Link to="/ppc-data">PPC Data</Link> › RM Sourcing</div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
          <div>
            <h2 className="title" style={{ marginBottom: 2 }}>RM Sourcing</h2>
            <p className="sub" style={{ margin: 0 }}>Material requirement — BOM exploded against the R3SS plan.</p>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <input ref={fileRef} type="file" accept=".xlsx,.xlsm,.xls" style={{ display: 'none' }} onChange={onFile} />
            <button className="btn-upload" disabled={busy} onClick={() => fileRef.current?.click()}>{busy ? 'Working…' : '📤 Upload BOM'}</button>
            <button className="btn-upload" disabled={busy} onClick={onRecompute} style={{ background: '#0a5fa5' }}>🔄 Recompute</button>
            {sheetUrl && <a className="btn-upload" href={sheetUrl} target="_blank" rel="noopener noreferrer" style={{ background: '#0b8043', textDecoration: 'none' }}>📑 Google Sheet</a>}
          </div>
        </div>
        {msg && <div style={{ fontSize: 13, margin: '8px 0', color: msg.ok ? '#1b5e20' : '#b71c1c' }}>{msg.text}</div>}

        {/* Tabs */}
        <div style={{ display: 'flex', gap: 6, margin: '14px 0 10px', borderBottom: '1px solid #dbe6f0' }}>
          {TABS.map(t => (
            <button key={t.key} onClick={() => { setView(t.key); setSearch('') }}
              style={{
                padding: '8px 16px', border: 'none', background: 'none', cursor: 'pointer',
                fontWeight: 700, fontSize: 14, color: view === t.key ? 'var(--accent)' : 'var(--muted)',
                borderBottom: view === t.key ? '3px solid var(--accent)' : '3px solid transparent', marginBottom: -1,
              }}>{t.name}</button>
          ))}
        </div>

        {loading ? <div>Loading…</div> : (
          <>
            {/* ---------- BY PRODUCT (BOM) ---------- */}
            {view === 'bom' && (<>
              <div className="dash-tile-grid">
                <Tile label="Total RM Demand" value={fmt(fgs.reduce((a, r) => a + N(r.rm_demand), 0))} unit="Kg" kind="info" />
                <Tile label="Total CP Demand" value={fmt(fgs.reduce((a, r) => a + N(r.cp_demand), 0))} unit="Nos" kind="score" />
                <Tile label="Products (FGs)" value={fgs.length} kind="score" />
                <Tile label="RM Items" value={rmq.length} kind="info" />
                <Tile label="CP / Packing Items" value={cp.length} kind="score" />
              </div>
              <Filters s={search} set={setSearch} ph="Search BOM code / family / customer" note={`${fgF.length} products`} />
              <div style={{ overflowX: 'auto', marginTop: 10 }}>
                <table className="mto-table" style={{ minWidth: 800 }}>
                  <thead><tr><th></th><th>BOM Code</th><th>Family</th><th>Customer</th><th className="num">Planned FG Qty</th><th className="num">RM Demand (Kg)</th><th className="num">CP Demand (Nos)</th><th className="num">BOM Parts</th></tr></thead>
                  <tbody>
                    {fgF.length === 0 ? <tr><td colSpan={8}>No data — upload the BOM, then Recompute.</td></tr> :
                      fgF.map(r => {
                        const o = open.has(r.bom_code)
                        const parts = r.parts || r.rms || []
                        const nRm = r.rm_count ?? parts.filter(p => p.rm).length
                        const nCp = r.cp_count ?? parts.filter(p => !p.rm).length
                        return [
                          <tr key={r.bom_code} style={{ cursor: 'pointer' }} onClick={() => toggle(r.bom_code)}>
                            <td style={{ width: 24, textAlign: 'center', color: 'var(--muted)' }}>{o ? '▾' : '▸'}</td>
                            <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{r.bom_code}</td>
                            <td>{r.family}</td><td>{r.customer}</td>
                            <td className="num">{fmt(r.planned)}</td>
                            <td className="num" style={{ fontWeight: 700, color: '#1565c0' }}>{fmt(r.rm_demand)}</td>
                            <td className="num" style={{ fontWeight: 700, color: '#6a1b9a' }}>{fmt(r.cp_demand)}</td>
                            <td className="num">{nRm + nCp} <span style={{ color: 'var(--muted)', fontSize: 11 }}>({nRm} RM / {nCp} CP)</span></td>
                          </tr>,
                          o && <tr key={r.bom_code + '_x'}><td></td><td colSpan={7} style={{ background: '#f7fafc', padding: '6px 10px' }}>
                            {/* Planned FG Qty is a read-only INPUT from R3SS (its calculation
                                — demand/safety/FG/WIP/EBQ — lives in the R3SS dashboard, not here). */}
                            <div style={{ fontSize: 12, marginBottom: 8, paddingBottom: 8, borderBottom: '1px solid #e2e8f0', color: '#455a64' }}>
                              <b>Planned FG Qty (from R3SS): {fmt(r.planned)}</b>
                              <span style={{ color: 'var(--muted)' }}> — input to this dashboard; BOM explodes against it below.</span>
                            </div>
                            <table style={{ width: '100%', fontSize: 13 }}><tbody>
                              {parts.map((m, j) => <tr key={j}>
                                <td style={{ fontFamily: 'monospace', fontSize: 12, padding: '2px 8px', whiteSpace: 'nowrap' }}>{m.code}</td>
                                <td style={{ padding: '2px 8px', maxWidth: 340, whiteSpace: 'normal', overflowWrap: 'anywhere' }}>{(m.desc || '').replace(/ /g, ' ')}</td>
                                <td style={{ padding: '2px 8px', whiteSpace: 'nowrap' }}>
                                  <span style={{ fontSize: 11, fontWeight: 600, padding: '1px 6px', borderRadius: 4,
                                    background: m.rm ? '#e3f2fd' : (cpType(m.code) === 'Packing' ? '#e8f5e9' : '#f3e5f5'),
                                    color: m.rm ? '#1565c0' : (cpType(m.code) === 'Packing' ? '#2e7d32' : '#6a1b9a') }}>
                                    {m.rm ? 'RM' : cpType(m.code)}
                                  </span>
                                </td>
                                <td style={{ textAlign: 'right', padding: '2px 8px', whiteSpace: 'nowrap' }}>{dec(m.req)} {m.uom}</td>
                              </tr>)}
                              {/* R21 — multi-level roll-up: RM direct + RM via CP = RM total */}
                              <tr style={{ borderTop: '2px solid #cbd5e0' }}>
                                <td colSpan={3} style={{ padding: '4px 8px', textAlign: 'right', color: '#1565c0' }}>RM used directly in FG →</td>
                                <td style={{ textAlign: 'right', padding: '4px 8px', color: '#1565c0', whiteSpace: 'nowrap' }}>{fmt(r.rm_demand)} Kg</td>
                              </tr>
                              <tr>
                                <td colSpan={3} style={{ padding: '4px 8px', textAlign: 'right', color: '#8e24aa' }}>RM via its CPs (R21) →</td>
                                <td style={{ textAlign: 'right', padding: '4px 8px', color: '#8e24aa', whiteSpace: 'nowrap' }}>
                                  {fmt(r.rm_via_cp || 0)} Kg
                                  {(r.rm_via_cp_parts && r.rm_via_cp_parts.length > 0) &&
                                    <span style={{ color: 'var(--muted)', fontSize: 11 }}> &nbsp;({r.rm_via_cp_parts.length} RM codes)</span>}
                                </td>
                              </tr>
                              <tr style={{ borderTop: '1px solid #cbd5e0' }}>
                                <td colSpan={3} style={{ padding: '4px 8px', textAlign: 'right', fontWeight: 700, color: '#0a5fa5' }}>RM TOTAL to procure →</td>
                                <td style={{ textAlign: 'right', padding: '4px 8px', fontWeight: 700, color: '#0a5fa5', whiteSpace: 'nowrap' }}>{fmt(r.rm_total ?? r.rm_demand)} Kg</td>
                              </tr>
                              <tr>
                                <td colSpan={3} style={{ padding: '4px 8px', textAlign: 'right', fontWeight: 700, color: '#6a1b9a' }}>CP Req total →</td>
                                <td style={{ textAlign: 'right', padding: '4px 8px', fontWeight: 700, color: '#6a1b9a', whiteSpace: 'nowrap' }}>{fmt(r.cp_demand)} Nos</td>
                              </tr>
                              {(r.rm_via_cp_parts && r.rm_via_cp_parts.length > 0) &&
                                <tr><td colSpan={4} style={{ padding: '4px 8px 8px', fontSize: 11, color: '#8e24aa', background: '#faf5fc' }}>
                                  <b>RM reached via CPs:</b> {r.rm_via_cp_parts.map(p => `${p.code} (${dec(p.req)} ${p.uom})`).join(' · ')}
                                </td></tr>}
                            </tbody></table>
                          </td></tr>,
                        ]
                      })}
                  </tbody>
                </table>
              </div>
            </>)}

            {/* ---------- RM REQ ---------- */}
            {view === 'rm' && (<>
              <div className="dash-tile-grid">
                <Tile label="Total RM Qty (computed)" value={fmt(rmF.reduce((a, r) => a + r.qty, 0))} unit="Kg" kind="info" />
                <Tile label="RM Items" value={rmF.length} kind="score" />
                <Tile label="Reqd Qty set (PPC)" value={rmF.filter(r => r.reqd).length} sub="manual final entered" kind="warn" />
              </div>
              <Filters s={search} set={setSearch} ph="Search RM code / description" note={`${rmF.length} raw materials`} />
              <div style={{ overflowX: 'auto', marginTop: 10 }}>
                <table className="mto-table" style={{ minWidth: 760 }}>
                  <thead><tr><th>Item Code</th><th>Description</th><th className="num">Qty</th><th className="num">Reqd Qty</th><th>Source</th><th></th></tr></thead>
                  <tbody>
                    {rmF.length === 0 ? <tr><td colSpan={6}>No RM requirement yet.</td></tr> :
                      rmF.map((r, i) => <tr key={i}>
                        <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{r.code}</td>
                        <td className="desc-wrap">{(r.desc || '').replace(/ /g, ' ')}</td>
                        <td className="num">{fmt(r.qty)}</td>
                        <td className="num" style={{ fontWeight: 700, color: r.reqd ? '#2e7d32' : '#9aa0a6' }}>{r.reqd ? fmt(N(r.reqd)) : '—'}</td>
                        <td>{/* R22 — manual add-on visible as such */}
                          <span style={{ fontSize: 11, fontWeight: 600, padding: '1px 7px', borderRadius: 10, background: r.reqd ? '#fff8e1' : '#eef2f7', color: r.reqd ? '#e65100' : '#64748b' }}>{r.reqd ? 'PPC' : 'Computed'}</span>
                        </td>
                        <td><button className="backbtn" style={{ padding: '2px 8px', fontSize: 12 }} onClick={() => openDrill(r.code)}>Where used</button></td>
                      </tr>)}
                  </tbody>
                </table>
              </div>
            </>)}

            {/* ---------- CP REQ ---------- */}
            {view === 'cp' && (<>
              <div className="dash-tile-grid">
                <Tile label="Total Items" value={cpView.length} kind="info" />
                <Tile label="Components (CP)" value={cpView.filter(r => r.type === 'Component').length} kind="info" />
                <Tile label="Packing Items" value={cpView.filter(r => r.type === 'Packing').length} kind="score" sub="R27 — plan as annual job" />
                <Tile label="Total Requirement" value={fmt(cpView.reduce((a, r) => a + r.req, 0))} kind="warn" sub="mixed UOM (Kgs / Nos)" />
              </div>
              {/* R27 — view packaging separately from components */}
              <div style={{ display: 'flex', gap: 6, marginTop: 12 }}>
                {[['all', 'All'], ['comp', 'Components'], ['pack', 'Packing (annual)']].map(([k, label]) => (
                  <button key={k} onClick={() => setCpFilter(k)} style={{
                    padding: '4px 12px', borderRadius: 16, border: '1px solid #cbd5e1', cursor: 'pointer',
                    fontSize: 12.5, fontWeight: 600,
                    background: cpFilter === k ? 'var(--accent)' : '#fff', color: cpFilter === k ? '#fff' : 'var(--muted)',
                  }}>{label}</button>
                ))}
              </div>
              <Filters s={search} set={setSearch} ph="Search item code / description" note={`${cpF.length} shown`} />
              <div style={{ overflowX: 'auto', marginTop: 10 }}>
                <table className="mto-table" style={{ minWidth: 760 }}>
                  <thead><tr><th>Item Code</th><th>Description</th><th>Type</th><th className="num">Requirement</th><th>UOM</th><th></th></tr></thead>
                  <tbody>
                    {cpF.length === 0 ? <tr><td colSpan={6}>No CP/packing requirement yet.</td></tr> :
                      cpF.map((r, i) => <tr key={i}>
                        <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{r.code}</td>
                        <td className="desc-wrap">{(r.desc || '').replace(/ /g, ' ')}</td>
                        <td><span className={r.type === 'Packing' ? 'r3ss-mts' : 'r3ss-na'}>{r.type}</span></td>
                        <td className="num" style={{ fontWeight: 700 }}>{dec(r.req)}</td>
                        <td>{r.uom}</td>
                        <td><button className="backbtn" style={{ padding: '2px 8px', fontSize: 12 }} onClick={() => openDrill(r.code)}>Where used</button></td>
                      </tr>)}
                  </tbody>
                </table>
              </div>
            </>)}

            {/* ---------- RULES (static tracker) ---------- */}
            {view === 'rules' && (ruleView ? <RuleDash ruleId={ruleView} onBack={() => setRuleView(null)} /> : (<>
              <div className="dash-tile-grid">
                <Tile label="Live" value={ruleCount('live')} kind="score" sub="working in the module" />
                <Tile label="Partial" value={ruleCount('partial')} kind="warn" sub="started, gaps remain" />
                <Tile label="Pending" value={ruleCount('pending')} kind="info" sub="awaiting data / build" />
                <Tile label="Input (upstream)" value={ruleCount('input')} kind="info" sub="from R3SS / MpsSS" />
                <Tile label="Other module" value={ruleCount('out')} kind="blocked" sub="PPC / Purchase" />
              </div>
              <p className="sub" style={{ fontSize: 13, marginTop: 10 }}>
                All 29 JCPL operating rules, grouped by band. Open any card for its principle,
                two worked test cases and the monthly validation check — and its live dashboard
                where data exists. This tab is the living spec (Rule 28).
              </p>
              {RULE_BANDS.map(band => (
                <div key={band.band} className="rule-band">
                  <h3 className="rule-band-head">{band.band}</h3>
                  <p className="rule-band-note">{band.note}</p>
                  <div className="rule-grid">
                    {band.rules.map(r => {
                      const st = STATUS[r.status]
                      return (
                        <div key={r.id} className="rule-card" style={{ borderLeft: `4px solid ${st.dot}`, background: st.tint }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                            <span className="rule-id">{r.id}</span>
                            <span className="rule-badge" style={{ background: st.bg, color: st.fg }}>{st.label}</span>
                          </div>
                          <div className="rule-title">{r.title}</div>
                          <div className="sub" style={{ fontSize: 12.5, lineHeight: 1.35 }}>{r.short}</div>
                          <div style={{ fontSize: 11.5, color: 'var(--muted)', marginTop: 8, display: 'flex', flexDirection: 'column', gap: 2 }}>
                            <span><b>Depends:</b> {r.depends}</span>
                            {r.needs && r.needs !== '—' && <span><b>Needs:</b> {r.needs}</span>}
                          </div>
                          {r.id === 'R19' && dq && dq.ok && (
                            <div style={{ marginTop: 8, fontSize: 11.5 }}>
                              <b>{fmt(dq.total_items)}</b> codes ·{' '}
                              <span style={{ color: dq.conflicting_desc_count ? '#e65100' : '#2e7d32', fontWeight: 700 }}>{dq.conflicting_desc_count} conflict</span> ·{' '}
                              <span style={{ color: dq.blank_desc_count ? '#e65100' : '#2e7d32', fontWeight: 700 }}>{dq.blank_desc_count} blank</span>
                            </div>
                          )}
                          {liveData[r.id] && (
                            <div style={{ marginTop: 8, fontSize: 11.5, fontWeight: 700, color: 'var(--steel)' }}>{liveData[r.id].stat}</div>
                          )}
                          <div style={{ marginTop: 10, paddingTop: 8, borderTop: '1px dashed #cbd5e1', display: 'flex', justifyContent: 'flex-end' }}>
                            <button className="backbtn" style={{ padding: '2px 10px', fontSize: 11 }} onClick={() => setRuleView(r.id)}>
                              {RULE_DASH[r.id] ? 'Open dashboard →' : 'Open spec →'}
                            </button>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              ))}
            </>))}
          </>
        )}
      </div>

      {drill && (
        <div onClick={() => setDrill(null)} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.35)', zIndex: 50, display: 'flex', justifyContent: 'flex-end' }}>
          <div onClick={(e) => e.stopPropagation()} style={{ width: 'min(560px,92vw)', background: '#fff', height: '100%', overflowY: 'auto', padding: 20, boxShadow: '-4px 0 16px rgba(0,0,0,.2)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ margin: 0 }}>Where used — <span style={{ fontFamily: 'monospace' }}>{drill.code}</span></h3>
              <button className="backbtn" onClick={() => setDrill(null)}>✕</button>
            </div>
            <p className="sub" style={{ fontSize: 13 }}>Finished goods that consume this item.</p>
            {drill.loading ? <div>Loading…</div> : drill.rows.length === 0 ? <div>No usage found.</div> : (
              <table className="mto-table" style={{ width: '100%' }}>
                <thead><tr><th>FG / BOM Code</th><th className="num">Planned FG Qty</th><th className="num">Req</th></tr></thead>
                <tbody>{drill.rows.map((u, i) => <tr key={i}>
                  <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{u.bom_code}</td>
                  <td className="num">{fmt(u.planned_qty)}</td>
                  <td className="num">{dec(u.requirement)}</td>
                </tr>)}</tbody>
              </table>
            )}
          </div>
        </div>
      )}
    </section>
  )
}

function Filters({ s, set, ph, note }) {
  return (
    <div className="r3ss-filters" style={{ gap: 10, flexWrap: 'wrap', marginTop: 12 }}>
      <input type="text" placeholder={ph} value={s} onChange={(e) => set(e.target.value)}
        style={{ padding: 8, border: '1px solid #cbd5e1', borderRadius: 6, minWidth: 260 }} />
      <span style={{ fontSize: 13, color: 'var(--muted)' }}>{note}</span>
    </div>
  )
}
