import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import TopBar from '../components/TopBar'

/* ═══════════════════════════════════════════════════════════════════
   PPCPlanInput — human commit layer (styled like the R3SS dashboard)
   ═══════════════════════════════════════════════════════════════════
   Planners enter the committed Total Plan per item. Values are saved to
   the "Plan Input" Google Sheet tab; the R3SS engine (v11+) overrides
   Total Plan with them on the next recompute, and Difference follows.
*/

function fmtN(v, dec = 0) {
  if (v == null || v === '') return '—'
  const n = Number(v)
  if (isNaN(n)) return '—'
  return n.toLocaleString('en-IN', { minimumFractionDigits: dec, maximumFractionDigits: dec })
}
const num = (v) => {
  const n = Number(String(v ?? '').replace(/,/g, ''))
  return isNaN(n) ? 0 : n
}

const FILTER_FIELDS = [
  { key: 'family',          label: 'Family' },
  { key: 'mto_mts',         label: 'MTO/MTS' },
  { key: 'section',         label: 'Section' },
  { key: 'product_group',   label: 'Group' },
  { key: 'moving_category', label: 'Category' },
  { key: 'customer',        label: 'Customer' },
]

export default function PPCPlanInput() {
  const navigate = useNavigate()
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [needsOnly, setNeedsOnly] = useState(true)
  const [filters, setFilters] = useState({})  // { field: value }
  const [edits, setEdits] = useState({})      // { item_code: stringValue }
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')

  async function load() {
    setLoading(true); setError('')
    try {
      const res = await api.ppcR3ssFromSheet('')
      const list = (res.rows || []).map(r => {
        const d = r.data || {}
        return {
          item_code: d.item_code || '',
          jolly_code: d.jolly_code || '',
          description: d.description || '',
          family: d.family || '',
          mto_mts: d.mto_mts || '',
          section: d.section || '',
          product_group: d.product_group || '',
          moving_category: d.moving_category || '',
          customer: d.category || '',
          fg_stock: num(d.fg_stock),
          to_plan: num(d.to_plan),
          total_plan: num(d.total_plan),
        }
      }).filter(r => r.item_code)
      setRows(list)
    } catch (e) {
      setError(e.message || 'Could not load R3SS data')
    } finally {
      setLoading(false)
    }
  }
  useEffect(() => { load() }, [])

  const filterOpts = useMemo(() => {
    const uniq = key => [...new Set(rows.map(r => r[key]).filter(Boolean))].sort()
    const o = {}
    FILTER_FIELDS.forEach(f => { o[f.key] = uniq(f.key) })
    return o
  }, [rows])

  const view = useMemo(() => {
    const q = search.trim().toLowerCase()
    return rows.filter(r => {
      if (needsOnly && !(r.to_plan > 0)) return false
      for (const [k, v] of Object.entries(filters)) {
        if (v && r[k] !== v) return false
      }
      if (!q) return true
      return r.item_code.toLowerCase().includes(q) ||
             r.jolly_code.toLowerCase().includes(q) ||
             r.description.toLowerCase().includes(q) ||
             r.family.toLowerCase().includes(q)
    })
  }, [rows, search, needsOnly, filters])

  const activeFilters = Object.values(filters).filter(Boolean).length

  const dirtyCount = Object.keys(edits).length

  function setEdit(code, val) { setEdits(prev => ({ ...prev, [code]: val })) }
  function committed(r) {
    if (Object.prototype.hasOwnProperty.call(edits, r.item_code)) return edits[r.item_code]
    return r.total_plan ? String(r.total_plan) : ''
  }

  const totals = useMemo(() => {
    let fg = 0, tp = 0, tot = 0
    view.forEach(r => {
      fg += r.fg_stock; tp += r.to_plan
      const cv = committed(r)
      tot += cv === '' ? 0 : num(cv)
    })
    return { fg, tp, tot }
  }, [view, edits])

  async function save(recompute) {
    if (dirtyCount === 0) { setMsg('Nothing to save'); return }
    setSaving(true); setMsg('')
    try {
      const items = Object.entries(edits).map(([item_code, total_plan]) => {
        const r = rows.find(x => x.item_code === item_code)
        return { item_code, jolly_code: r ? r.jolly_code : '', total_plan }
      })
      const res = await api.ppcR3ssPlanInputSave(items, recompute)
      setEdits({})
      setMsg(recompute
        ? `Saved ${res.saved} item(s) and recomputed.`
        : `Saved ${res.saved} item(s). Use "Save & Recompute" to apply to the dashboard.`)
      await load()
    } catch (e) {
      setMsg('Save failed: ' + (e.message || e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="screen">
      <TopBar subtitle="PPC Department" />
      <div className="wrap wrap-wide">

        {/* Breadcrumbs */}
        <div className="crumbs">
          <Link to="/departments">Home</Link> ›{' '}
          <Link to="/ppc-data">PPC Data</Link> ›{' '}
          <Link to="/ppc-data/r3ss">R3SS Plan</Link> › Plan Input
        </div>
        <button className="backbtn" onClick={() => navigate('/ppc-data/r3ss')}>
          ← Back to R3SS
        </button>

        {/* Header */}
        <div className="page-head" style={{ marginBottom: 14 }}>
          <div>
            <h2 className="title">Plan Input — Committed Total Plan</h2>
            <p className="sub" style={{ marginBottom: 0 }}>
              {view.length} items{dirtyCount ? <> · <strong>{dirtyCount} edited</strong></> : ''}
              {' '}· type the committed Total Plan; Difference updates live
            </p>
          </div>
          <div className="head-buttons">
            <button className="backbtn" onClick={() => save(false)} disabled={saving || !dirtyCount}
              style={{ fontSize: 13, padding: '7px 12px', margin: 0 }}>
              💾 Save
            </button>
            <button className="btn-upload" onClick={() => save(true)} disabled={saving || !dirtyCount}
              style={{ background: '#2e7d32', fontSize: 13, padding: '8px 14px' }}>
              {saving
                ? <><span className="spinner" style={{ borderTopColor: '#fff', borderColor: 'rgba(255,255,255,.35)' }} />Saving…</>
                : '⚡ Save & Recompute'}
            </button>
          </div>
        </div>

        {/* Filters */}
        <div className="r3ss-filters" style={{ marginBottom: 12 }}>
          <input
            type="text"
            placeholder="Search ERP / Jolly / Cust Part No / Family…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{ padding: '4px 8px', border: '1px solid #cbd5e1', borderRadius: 6, fontSize: 12, width: 260 }}
          />
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
            <input type="checkbox" checked={needsOnly} onChange={e => setNeedsOnly(e.target.checked)} />
            Needs plan (To&nbsp;Plan&nbsp;&gt;&nbsp;0)
          </label>

          {FILTER_FIELDS.map(f => (
            <div key={f.key} className="r3ss-filter">
              <label>{f.label}</label>
              <select
                value={filters[f.key] || ''}
                onChange={e => setFilters(prev => ({ ...prev, [f.key]: e.target.value }))}
              >
                <option value="">All</option>
                {(filterOpts[f.key] || []).map(v => (
                  <option key={v} value={v}>{v}</option>
                ))}
              </select>
            </div>
          ))}

          {activeFilters > 0 && (
            <button onClick={() => setFilters({})} style={{
              padding: '4px 8px', border: '1px solid #e9ccc8', borderRadius: 6,
              fontSize: 11, fontWeight: 700, background: '#fef2f2',
              color: '#c62828', cursor: 'pointer',
            }}>
              Clear ({activeFilters})
            </button>
          )}
        </div>

        {msg && <div className="panel" style={{ marginBottom: 12 }}>{msg}</div>}
        {error && <div className="panel" style={{ marginBottom: 12, color: 'var(--bad)' }}>{error}</div>}

        {loading ? (
          <div className="panel" style={{ textAlign: 'center', padding: 44 }}>Loading…</div>
        ) : (
          <div className="r3ss-scroll">
            <table className="r3ss-tbl">
              <thead>
                <tr>
                  <th className="sticky-col" style={{ textAlign: 'left' }}>ERP Code</th>
                  <th className="sticky-col2" style={{ textAlign: 'left' }}>Cust Part No</th>
                  <th style={{ textAlign: 'left' }}>Jolly Code</th>
                  <th style={{ textAlign: 'left' }}>Family</th>
                  <th style={{ textAlign: 'left' }}>Section</th>
                  <th className="num">FG</th>
                  <th className="num">To Plan</th>
                  <th className="num group-sep">Total Plan (commit)</th>
                  <th className="num">Difference</th>
                </tr>
              </thead>
              <tbody>
                {view.slice(0, 2000).map((r, i) => {
                  const cv = committed(r)
                  const diff = cv === '' ? null : num(cv) - r.to_plan
                  const isEdited = Object.prototype.hasOwnProperty.call(edits, r.item_code)
                  return (
                    <tr key={r.item_code || i} style={isEdited ? { background: 'rgba(255,193,7,0.10)' } : undefined}>
                      <td className="sticky-col" style={{
                        fontFamily: "'SF Mono',Consolas,monospace",
                        fontSize: 11.5, fontWeight: 600, letterSpacing: '.01em',
                      }}>
                        {r.item_code}
                      </td>
                      <td className="sticky-col2" title={r.description} style={{
                        fontSize: 11.5, maxWidth: 170, overflow: 'hidden', textOverflow: 'ellipsis',
                      }}>
                        {r.description || '—'}
                      </td>
                      <td>{r.jolly_code || '—'}</td>
                      <td title={r.family} style={{ maxWidth: 150, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {r.family || '—'}
                      </td>
                      <td>{r.section || '—'}</td>
                      <td className="num">{fmtN(r.fg_stock)}</td>
                      <td className="num">{fmtN(r.to_plan)}</td>
                      <td className="num group-sep">
                        <input
                          type="number"
                          value={cv}
                          onChange={e => setEdit(r.item_code, e.target.value)}
                          placeholder="—"
                          style={{
                            width: 96, padding: '3px 6px', textAlign: 'right',
                            fontVariantNumeric: 'tabular-nums', borderRadius: 4,
                            border: '1px solid var(--line, #cbd5e1)',
                          }}
                        />
                      </td>
                      <td className="num" style={{ color: diff == null ? undefined : (diff < 0 ? 'var(--bad)' : 'var(--ok)'), fontWeight: 600 }}>
                        {diff == null ? '—' : fmtN(diff)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
              <tfoot>
                <tr>
                  <td className="sticky-col" style={{ fontWeight: 800, fontSize: 11.5 }}>TOTAL</td>
                  <td className="sticky-col2" style={{ color: 'rgba(255,255,255,.55)', fontSize: 11 }}>
                    {view.length} items
                  </td>
                  <td></td>
                  <td></td>
                  <td></td>
                  <td className="num">{fmtN(totals.fg)}</td>
                  <td className="num">{fmtN(totals.tp)}</td>
                  <td className="num group-sep">{fmtN(totals.tot)}</td>
                  <td className="num">{fmtN(totals.tot - totals.tp)}</td>
                </tr>
              </tfoot>
            </table>
            {view.length > 2000 && (
              <div style={{ padding: 10, opacity: 0.7 }}>Showing first 2,000 — narrow with search.</div>
            )}
          </div>
        )}
      </div>
    </section>
  )
}
