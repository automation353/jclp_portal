import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import TopBar from '../components/TopBar'
import { api } from '../api'

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
const STATUS = {
  live: { label: 'Live', bg: '#e8f5e9', fg: '#1b5e20', dot: '#2e7d32' },
  partial: { label: 'Partial', bg: '#fff8e1', fg: '#e65100', dot: '#ef6c00' },
  pending: { label: 'Pending', bg: '#eceff1', fg: '#455a64', dot: '#90a4ae' },
  input: { label: 'Input', bg: '#e3f2fd', fg: '#1565c0', dot: '#1976d2' },
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
      { id: 'R23', title: 'Green hierarchy FG → child → RM', short: 'FG-level netting shown in By Product (demand − opening − green); RM-tier stock netting pending.', status: 'partial', depends: 'R21, R1', needs: 'RM opening stock, child-part green, safety buffer (Stores/PPC)' },
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
    band: 'Part F — Method & governance  (overlay)',
    note: 'Sit under every band; depend on nothing.',
    rules: [
      { id: 'R28', title: 'Document every rule before coding', short: 'This Rules tab is that live document.', status: 'live', depends: '—', needs: '—' },
      { id: 'R29', title: 'Cross-functional design + automation blueprint', short: 'Pros / cons + blueprint before rollout.', status: 'partial', depends: '—', needs: 'Impact plot + blueprint (cross-functional)' },
    ],
  },
]
const ruleCount = (s) => RULE_BANDS.reduce((a, b) => a + b.rules.filter(r => r.status === s).length, 0)

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
                <Tile label="Products (FGs)" value={fgs.length} kind="score" />
                <Tile label="RM Items" value={rmq.length} kind="info" />
                <Tile label="CP / Packing Items" value={cp.length} kind="score" />
              </div>
              <Filters s={search} set={setSearch} ph="Search BOM code / family / customer" note={`${fgF.length} products`} />
              <div style={{ overflowX: 'auto', marginTop: 10 }}>
                <table className="mto-table" style={{ minWidth: 800 }}>
                  <thead><tr><th></th><th>BOM Code</th><th>Family</th><th>Customer</th><th className="num">Planned FG Qty</th><th className="num">RM Demand (Kg)</th><th className="num">BOM Parts</th></tr></thead>
                  <tbody>
                    {fgF.length === 0 ? <tr><td colSpan={7}>No data — upload the BOM, then Recompute.</td></tr> :
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
                            <td className="num" style={{ fontWeight: 700 }}>{fmt(r.rm_demand)}</td>
                            <td className="num">{nRm + nCp} <span style={{ color: 'var(--muted)', fontSize: 11 }}>({nRm} RM / {nCp} CP)</span></td>
                          </tr>,
                          o && <tr key={r.bom_code + '_x'}><td></td><td colSpan={6} style={{ background: '#f7fafc', padding: '6px 10px' }}>
                            {/* R23 — FG-level netting (from R3SS): demand − (opening + green) → plan */}
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, fontSize: 12, marginBottom: 8, paddingBottom: 8, borderBottom: '1px solid #e2e8f0' }}>
                              <span style={{ fontWeight: 700, color: '#455a64' }}>FG netting (R23):</span>
                              <span>Demand <b>{fmt(r.fg_demand)}</b></span>
                              <span>Opening <b>{fmt(r.fg_opening)}</b></span>
                              <span>FG Stock <b>{fmt(r.fg_stock)}</b></span>
                              <span>Green <b>{fmt(r.fg_green)}</b></span>
                              <span style={{ color: '#0a5fa5' }}>→ Planned <b>{fmt(r.planned)}</b></span>
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
            {view === 'rules' && (<>
              <div className="dash-tile-grid">
                <Tile label="Live" value={ruleCount('live')} kind="score" sub="working in the module" />
                <Tile label="Partial" value={ruleCount('partial')} kind="warn" sub="started, gaps remain" />
                <Tile label="Pending" value={ruleCount('pending')} kind="info" sub="awaiting data / build" />
                <Tile label="Input (upstream)" value={ruleCount('input')} kind="info" sub="from R3SS / MpsSS" />
              </div>
              <p className="sub" style={{ fontSize: 13, marginTop: 10 }}>
                The JCPL operating rules that govern RM Sourcing, grouped by band in build order.
                Status reflects what the module does today — not the full 29-rule spec.
              </p>
              {RULE_BANDS.map(band => (
                <div key={band.band} style={{ marginTop: 18 }}>
                  <h3 style={{ margin: '0 0 2px', fontSize: 15 }}>{band.band}</h3>
                  <p className="sub" style={{ fontSize: 12.5, margin: '0 0 10px' }}>{band.note}</p>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(300px,1fr))', gap: 10 }}>
                    {band.rules.map(r => {
                      const st = STATUS[r.status]
                      return (
                        <div key={r.id} style={{ border: '1px solid #e2e8f0', borderLeft: `4px solid ${st.dot}`, borderRadius: 8, padding: '10px 12px', background: '#fff' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                            <span style={{ fontWeight: 800, fontFamily: 'monospace', fontSize: 13 }}>{r.id}</span>
                            <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 12, background: st.bg, color: st.fg }}>{st.label}</span>
                          </div>
                          <div style={{ fontWeight: 700, fontSize: 13.5, margin: '4px 0 2px' }}>{r.title}</div>
                          <div className="sub" style={{ fontSize: 12.5, lineHeight: 1.35 }}>{r.short}</div>
                          <div style={{ fontSize: 11.5, color: 'var(--muted)', marginTop: 8, display: 'flex', flexDirection: 'column', gap: 2 }}>
                            <span><b>Depends:</b> {r.depends}</span>
                            {r.needs && r.needs !== '—' && <span><b>Needs:</b> {r.needs}</span>}
                          </div>
                          {r.id === 'R19' && dq && dq.ok && (
                            <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px dashed #e2e8f0', fontSize: 11.5 }}>
                              <b>Live BOM check:</b> {fmt(dq.total_items)} item codes ·{' '}
                              <span style={{ color: dq.conflicting_desc_count ? '#e65100' : '#2e7d32', fontWeight: 700 }}>{dq.conflicting_desc_count} conflicting desc.</span> ·{' '}
                              <span style={{ color: dq.blank_desc_count ? '#e65100' : '#2e7d32', fontWeight: 700 }}>{dq.blank_desc_count} blank desc.</span>
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </div>
              ))}
              <div style={{ marginTop: 20, padding: '10px 12px', background: '#f7f9fc', border: '1px solid #e2e8f0', borderRadius: 8, fontSize: 12.5, color: 'var(--muted)' }}>
                <b>Handled by other modules (not RM Sourcing):</b> R4 (Purchase hand-off sheets),
                R8–R10 (line capacity & manpower — PPC), R12–R18 (vendor management & procurement — Purchase).
                Shown here only for context — R12 feeds R5 & R24 above.
              </div>
            </>)}
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
