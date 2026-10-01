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
]

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

  async function load() {
    setLoading(true)
    try {
      const [a, b, c] = await Promise.all([api.rmSourcingByBom(), api.rmSourcingQuantity(), api.rmSourcingCpReq()])
      setFgs(a.rows || []); setRmq(b.rows || []); setCp(c.rows || []); setSheetUrl(a.sheet_url || '')
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
  const rmView = useMemo(() => rmq.map(r => ({
    code: r['RM Code'], desc: r.Description, demand: N(r.Demand), green: N(r['Green Level']),
    proc: N(r.Demand) + N(r['Green Level']) * 0.6, d10: N(r['Demand +10%']), uom: r.UOM, grade: grade(r.Description),
  })), [rmq])
  const cpView = useMemo(() => cp.map(r => ({
    code: r['Item Code'], desc: r.Description, uom: r.UOM, req: N(r.Requirement), type: cpType(r['Item Code']),
  })), [cp])

  const s = search.toLowerCase()
  const fgF = fgs.filter(r => !s || [r.bom_code, r.family, r.customer, r.erp_code].some(x => (x || '').toLowerCase().includes(s)))
    .sort((a, b) => N(b.rm_demand) - N(a.rm_demand))
  const rmF = rmView.filter(r => !s || r.code.toLowerCase().includes(s) || (r.desc || '').toLowerCase().includes(s))
    .sort((a, b) => b.demand - a.demand)
  const cpF = cpView.filter(r => !s || r.code.toLowerCase().includes(s) || (r.desc || '').toLowerCase().includes(s))
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
                <Tile label="Green Level" value={fmt(rmView.reduce((a, r) => a + r.green, 0))} unit="Kg" kind="score" />
                <Tile label="Suggested Procurement" value={fmt(rmView.reduce((a, r) => a + r.proc, 0))} unit="Kg" kind="warn" />
              </div>
              <Filters s={search} set={setSearch} ph="Search BOM code / family / customer" note={`${fgF.length} products`} />
              <div style={{ overflowX: 'auto', marginTop: 10 }}>
                <table className="mto-table" style={{ minWidth: 800 }}>
                  <thead><tr><th></th><th>BOM Code</th><th>Family</th><th>Customer</th><th className="num">Planned</th><th className="num">RM Demand (Kg)</th><th className="num">RM Items</th></tr></thead>
                  <tbody>
                    {fgF.length === 0 ? <tr><td colSpan={7}>No data — upload the BOM, then Recompute.</td></tr> :
                      fgF.map(r => {
                        const o = open.has(r.bom_code)
                        return [
                          <tr key={r.bom_code} style={{ cursor: 'pointer' }} onClick={() => toggle(r.bom_code)}>
                            <td style={{ width: 24, textAlign: 'center', color: 'var(--muted)' }}>{o ? '▾' : '▸'}</td>
                            <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{r.bom_code}</td>
                            <td>{r.family}</td><td>{r.customer}</td>
                            <td className="num">{fmt(r.planned)}</td>
                            <td className="num" style={{ fontWeight: 700 }}>{fmt(r.rm_demand)}</td>
                            <td className="num">{r.rm_count}</td>
                          </tr>,
                          o && <tr key={r.bom_code + '_x'}><td></td><td colSpan={6} style={{ background: '#f7fafc', padding: '6px 10px' }}>
                            <table style={{ width: '100%', fontSize: 13 }}><tbody>
                              {r.rms.map((m, j) => <tr key={j}>
                                <td style={{ fontFamily: 'monospace', fontSize: 12, padding: '2px 8px' }}>{m.code}</td>
                                <td style={{ padding: '2px 8px' }}>{m.desc}</td>
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
                <Tile label="Total RM Demand" value={fmt(rmF.reduce((a, r) => a + r.demand, 0))} unit="Kg" kind="info" />
                <Tile label="RM Items" value={rmF.length} kind="score" />
                <Tile label="Green Level" value={fmt(rmF.reduce((a, r) => a + r.green, 0))} unit="Kg" kind="score" />
                <Tile label="Suggested Procurement" value={fmt(rmF.reduce((a, r) => a + r.proc, 0))} unit="Kg" kind="warn" />
              </div>
              <Filters s={search} set={setSearch} ph="Search RM code / description" note={`${rmF.length} raw materials`} />
              <div style={{ overflowX: 'auto', marginTop: 10 }}>
                <table className="mto-table" style={{ minWidth: 820 }}>
                  <thead><tr><th>RM Code</th><th>Description</th><th className="num">Demand</th><th className="num">Green Level</th><th className="num">Procurement</th><th className="num">+10%</th><th>UOM</th><th></th></tr></thead>
                  <tbody>
                    {rmF.length === 0 ? <tr><td colSpan={8}>No RM requirement yet.</td></tr> :
                      rmF.map((r, i) => <tr key={i}>
                        <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{r.code}</td>
                        <td>{r.desc}</td>
                        <td className="num">{fmt(r.demand)}</td>
                        <td className="num">{fmt(r.green)}</td>
                        <td className="num" style={{ fontWeight: 700, color: '#ef6c00' }}>{fmt(r.proc)}</td>
                        <td className="num">{fmt(r.d10)}</td>
                        <td>{r.uom}</td>
                        <td><button className="backbtn" style={{ padding: '2px 8px', fontSize: 12 }} onClick={() => openDrill(r.code)}>Where used</button></td>
                      </tr>)}
                  </tbody>
                </table>
              </div>
            </>)}

            {/* ---------- CP REQ ---------- */}
            {view === 'cp' && (<>
              <div className="dash-tile-grid">
                <Tile label="Total Items" value={cpF.length} kind="info" />
                <Tile label="Components (CP)" value={cpF.filter(r => r.type === 'Component').length} kind="info" />
                <Tile label="Packing Items" value={cpF.filter(r => r.type === 'Packing').length} kind="score" />
                <Tile label="Total Requirement" value={fmt(cpF.reduce((a, r) => a + r.req, 0))} kind="warn" sub="mixed UOM (Kgs / Nos)" />
              </div>
              <Filters s={search} set={setSearch} ph="Search item code / description" note={`${cpF.length} CP & packing items`} />
              <div style={{ overflowX: 'auto', marginTop: 10 }}>
                <table className="mto-table" style={{ minWidth: 760 }}>
                  <thead><tr><th>Item Code</th><th>Description</th><th>Type</th><th className="num">Requirement</th><th>UOM</th><th></th></tr></thead>
                  <tbody>
                    {cpF.length === 0 ? <tr><td colSpan={6}>No CP/packing requirement yet.</td></tr> :
                      cpF.map((r, i) => <tr key={i}>
                        <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{r.code}</td>
                        <td>{r.desc}</td>
                        <td><span className={r.type === 'Packing' ? 'r3ss-mts' : 'r3ss-na'}>{r.type}</span></td>
                        <td className="num" style={{ fontWeight: 700 }}>{dec(r.req)}</td>
                        <td>{r.uom}</td>
                        <td><button className="backbtn" style={{ padding: '2px 8px', fontSize: 12 }} onClick={() => openDrill(r.code)}>Where used</button></td>
                      </tr>)}
                  </tbody>
                </table>
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
                <thead><tr><th>FG / BOM Code</th><th className="num">Planned</th><th className="num">Req</th></tr></thead>
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
