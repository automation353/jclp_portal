import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import TopBar from '../components/TopBar'

/* ═══════════════════════════════════════════════════════════════════
   PPCDataR3SS — R3SS Production Plan Sheet View
   ═══════════════════════════════════════════════════════════════════
   Full spreadsheet-style view of the R3SS day-wise production plan.
   Mirrors the Google Sheet PLAN tab with frozen columns, colour
   coding, column group toggles, and filter bar.
*/

/* ─── Helpers ─────────────────────────────────────────────────── */

/** Format a number with Indian locale, optional decimals */
function fmtN(v, dec = 0) {
  if (v == null || v === '') return '—'
  const n = Number(v)
  if (isNaN(n)) return '—'
  return n.toLocaleString('en-IN', {
    minimumFractionDigits: dec,
    maximumFractionDigits: dec,
  })
}

/** Day cell: show nothing for zero (reduces clutter) */
function fmtDay(v) {
  const n = Number(v)
  return n ? n.toLocaleString('en-IN') : ''
}

/** Map colour field → CSS class */
function clrClass(c) {
  const u = (c || '').toUpperCase()
  if (u === 'RED') return 'r3ss-clr-red'
  if (u === 'YELLOW') return 'r3ss-clr-yellow'
  if (u === 'GREEN') return 'r3ss-clr-green'
  if (u === 'BLUE') return 'r3ss-clr-blue'
  return ''
}

/** Map priority → CSS class */
function priClass(p) {
  const u = (p || '').toUpperCase()
  if (u === 'HIGH') return 'r3ss-pri-high'
  if (u === 'MEDIUM') return 'r3ss-pri-medium'
  if (u === 'LOW') return 'r3ss-pri-low'
  return ''
}

/* ─── Column definitions ──────────────────────────────────────── */

const GROUPS = {
  class:   { label: 'Classification' },
  engg:    { label: 'Engineering' },
  policy:  { label: 'Policy' },
  demand:  { label: 'Demand Qty' },
  stock:   { label: 'Stock' },
  plan:    { label: 'Plan' },
  weeks:   { label: 'Weeks' },
  output:  { label: 'Output' },
  days:    { label: 'Days' },
}

/** Default group visibility — Engineering & Policy off by default (mostly zeros) */
const DEFAULT_GROUPS = {
  class: true, engg: false, policy: false,
  demand: true, stock: true, plan: true, weeks: true, output: true, days: true,
}

/**
 * Non-frozen columns — ordered to match the Google Sheet PLAN tab exactly.
 * `last: true` adds a thicker right border (group separator).
 * `sum: true` = include in the totals row.
 * `accent: true` = emphasised styling for the key output column.
 */
const COLS = [
  // Classification — matches R3SS file naming
  { key: 'jolly_code',     label: 'Jolly Code',      group: 'class' },
  { key: 'jolly_size',     label: 'Jolly Size',      group: 'class' },
  { key: 'family',         label: 'Family',          group: 'class' },
  { key: 'product_group',  label: 'Product Group',   group: 'class' },
  { key: 'section',        label: 'Section',         group: 'class' },
  { key: 'plant',          label: 'Plant',           group: 'class' },
  { key: 'mto_mts',        label: 'MTO/MTS',         group: 'class' },
  { key: 'category',       label: 'Customer',         group: 'class' },
  { key: 'priority',       label: 'Priority',        group: 'class', last: true },

  // Engineering
  { key: 'teeth',          label: 'No of Teeth',     group: 'engg', num: true },
  { key: 'strokes',        label: 'No of Strokes',   group: 'engg', num: true },
  { key: 'open_dia',       label: 'Open Dia',        group: 'engg', num: true, dec: 2 },
  { key: 'close_dia',      label: 'Close Dia',       group: 'engg', num: true, dec: 2 },
  { key: 'cut_length',     label: 'Cut Length',      group: 'engg', num: true, dec: 2 },
  { key: 'strip_weight',   label: 'Strip Weight',    group: 'engg', num: true, dec: 2, last: true },

  // Policy
  { key: 'green_level',    label: 'Green Level',     group: 'policy', num: true },
  { key: 'red_level',      label: 'Red Level',       group: 'policy', num: true },
  { key: 'blue_level',     label: 'Blue Level',      group: 'policy', num: true },
  { key: 'colour',         label: 'Colour',          group: 'policy' },
  { key: 'asp',            label: 'ASP',             group: 'policy', num: true, dec: 2 },
  { key: 'ebq',            label: 'EBQ',             group: 'policy', num: true },
  { key: 'lead_time',      label: 'Lead Time',       group: 'policy', num: true, last: true },

  // Demand Qty
  { key: 'initial_demand',      label: 'Initial',          group: 'demand', num: true, sum: true },
  { key: 'additional_demand',   label: 'Additional',       group: 'demand', num: true, sum: true },
  { key: 'total_demand',        label: 'Total',            group: 'demand', num: true, bold: true, sum: true },
  { key: 'sales_order_pending', label: 'SO Pending',      group: 'demand', num: true, sum: true, last: true },

  // Stock
  { key: 'opening_balance',label: 'Opening Balance',  group: 'stock', num: true, sum: true },
  { key: 'fg_stock',       label: 'FG',                group: 'stock', num: true, sum: true },
  { key: 'pack',           label: 'Pack',             group: 'stock', num: true, sum: true },
  { key: 'disp',           label: 'Disp',             group: 'stock', num: true, sum: true, last: true },

  // Plan
  { key: 'level',          label: 'Level',            group: 'plan', num: true },
  { key: 'to_plan',        label: 'To Plan',          group: 'plan', num: true, accent: true, sum: true, last: true },

  // Weekly buckets
  { key: 'w1', label: 'W1', group: 'weeks', num: true, sum: true },
  { key: 'w2', label: 'W2', group: 'weeks', num: true, sum: true },
  { key: 'w3', label: 'W3', group: 'weeks', num: true, sum: true },
  { key: 'w4', label: 'W4', group: 'weeks', num: true, sum: true },
  { key: 'w5', label: 'W5', group: 'weeks', num: true, sum: true, last: true },

  // Plan output
  { key: 'total_plan',     label: 'Total Plan (HW+MIT)', group: 'output', num: true, sum: true },
  { key: 'total_plan_hw',  label: 'Total Plan HW',     group: 'output', num: true, sum: true },
  { key: 'total_plan_mit', label: 'Total Plan MIT',    group: 'output', num: true, sum: true },
  { key: 'cutting',        label: 'Cutting',          group: 'output', num: true, sum: true },
  { key: 'difference',     label: 'Difference',       group: 'output', num: true, sum: true },
  { key: 'backlog',        label: 'Backlog',          group: 'output', num: true, sum: true, last: true },
]

/* ─── Sheet constants ─────────────────────────────────────────── */
const R3SS_SHEET_URL = 'https://docs.google.com/spreadsheets/d/1AHkBgdOLO4YZO6vBqVQHNPmlT-IwFygCf2O8rpidRDU'

/* ═════════════════════════════════════════════════════════════════ */

export default function PPCDataR3SS() {
  const navigate = useNavigate()
  const fileRef = useRef(null)

  /* ── State ─────────────────────────────────────────────────── */
  const [data, setData] = useState(null)        // ppcR3ssCurrent response
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // Search (server-side via API)
  const [search, setSearch] = useState('')
  const [searchApplied, setSearchApplied] = useState('')

  // Filters (client-side on loaded rows)
  const [filters, setFilters] = useState({})

  // Column group visibility
  const [groups, setGroups] = useState(() => ({ ...DEFAULT_GROUPS }))

  // Upload panel
  const [showUpload, setShowUpload] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadResult, setUploadResult] = useState(null)

  // Compute
  const [computing, setComputing] = useState(false)

  /* ── Data fetching ─────────────────────────────────────────── */

  function refresh(srch = '') {
    setLoading(true)
    setError('')
    // Read the R3SS tab straight from the Google Sheet (computed in-sheet).
    api.ppcR3ssFromSheet(srch)
      .then(d => setData(d))
      .catch(err => {
        if (err.status === 404) setData(null)
        else setError(err.message)
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => { refresh() }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  /* ── Derived data ──────────────────────────────────────────── */

  // Derive plan_month: API field, or infer from first row's days keys
  const planMonth = useMemo(() => {
    if (data?.plan_month) return data.plan_month
    // Fallback: find the month from the first row's days dict
    if (data?.rows?.length) {
      const days = data.rows[0]?.data?.days
      if (days) {
        const firstKey = Object.keys(days).sort()[0]
        if (firstKey) return firstKey.slice(0, 7) // "2026-09-01" → "2026-09"
      }
    }
    return null
  }, [data])

  // Generate day column keys from planMonth (e.g. "2026-09")
  const dayKeys = useMemo(() => {
    if (!planMonth) return []
    const [y, m] = planMonth.split('-').map(Number)
    const count = new Date(y, m, 0).getDate()
    return Array.from({ length: count }, (_, i) => {
      const d = String(i + 1).padStart(2, '0')
      return `${planMonth}-${d}`
    })
  }, [planMonth])

  // Weekend set (Sat=6, Sun=0)
  const weekendDays = useMemo(() => {
    const set = new Set()
    dayKeys.forEach(dk => {
      const dow = new Date(dk + 'T00:00:00').getDay()
      if (dow === 0 || dow === 6) set.add(dk)
    })
    return set
  }, [dayKeys])

  // Visible fixed columns (based on group toggles)
  const visCols = useMemo(
    () => COLS.filter(c => groups[c.group]),
    [groups],
  )

  // Unique values for filter dropdowns
  const filterOpts = useMemo(() => {
    if (!data?.rows) return {}
    const rows = data.rows.map(r => r.data)
    const uniq = key => [...new Set(rows.map(r => r[key]).filter(Boolean))].sort()
    return {
      section:       uniq('section'),
      family:        uniq('family'),
      product_group: uniq('product_group'),
      mto_mts:       uniq('mto_mts'),
      priority:      uniq('priority'),
    }
  }, [data])

  // Client-side filter
  const filteredRows = useMemo(() => {
    if (!data?.rows) return []
    return data.rows.filter(r => {
      const d = r.data
      for (const [k, v] of Object.entries(filters)) {
        if (v && d[k] !== v) return false
      }
      return true
    })
  }, [data, filters])

  // Totals row (only for summable columns + day columns)
  const totals = useMemo(() => {
    const sum = {}
    COLS.filter(c => c.sum).forEach(c => { sum[c.key] = 0 })
    dayKeys.forEach(k => { sum[k] = 0 })
    filteredRows.forEach(r => {
      const d = r.data
      COLS.filter(c => c.sum).forEach(c => { sum[c.key] += Number(d[c.key]) || 0 })
      dayKeys.forEach(k => { sum[k] += Number(d.days?.[k]) || 0 })
    })
    return sum
  }, [filteredRows, dayKeys])

  const activeFilterCount = Object.values(filters).filter(Boolean).length

  /* ── Handlers ──────────────────────────────────────────────── */

  function handleSearch(e) {
    e.preventDefault()
    setSearchApplied(search)
    refresh(search)
  }

  function clearSearch() {
    setSearch('')
    setSearchApplied('')
    refresh('')
  }

  function setFilter(key, val) {
    setFilters(f => ({ ...f, [key]: val || '' }))
  }

  function clearFilters() {
    setFilters({})
  }

  function toggleGroup(key) {
    setGroups(g => ({ ...g, [key]: !g[key] }))
  }

  const [computeStep, setComputeStep] = useState('')

  async function handleCompute() {
    if (!confirm('Recompute R3SS?\nThis clears the current view and reloads the freshly computed R3SS tab from the Google Sheet.')) return
    setComputing(true)
    setComputeStep('Recomputing in Google Sheet…')
    setError('')
    // Keep the current view visible while recomputing; it is replaced wholesale
    // only when the fresh R3SS tab comes back (no "empty" flash mid-compute).
    const timer = setTimeout(() => setComputeStep('Reading fresh R3SS tab…'), 8000)
    try {
      const res = await api.ppcR3ssRecomputeSheet()
      clearTimeout(timer)
      setData(res)
      setComputeStep(`Done — ${res.row_count} rows from Google Sheet`)
    } catch (err) {
      clearTimeout(timer)
      if (err.status === 409) {
        // Guard tripped — some source tabs are still empty. Keep the existing
        // R3SS view (reload it) and tell the user what's missing.
        setError(err.message || 'Waiting for all source tabs to be uploaded.')
        setComputeStep('')
        refresh(searchApplied)
      } else {
        setError(err.message)
      }
    } finally {
      setComputing(false)
      setTimeout(() => setComputeStep(''), 4000)
    }
  }

  async function handleUpload(e) {
    e.preventDefault()
    const file = fileRef.current?.files[0]
    if (!file) return
    setUploading(true)
    setUploadResult(null)
    setError('')
    try {
      const res = await api.ppcR3ssUpload(file, '')
      setUploadResult(res)
      if (fileRef.current) fileRef.current.value = ''
      refresh(searchApplied)
    } catch (err) {
      setError(err.message)
    } finally {
      setUploading(false)
    }
  }

  /* ── Render helpers ────────────────────────────────────────── */

  /** Render a single body cell for a fixed column */
  function renderCell(col, d) {
    const val = d[col.key]
    const sepCls = col.last ? ' group-sep' : ''

    // Special: colour pill
    if (col.key === 'colour') {
      return (
        <td key={col.key} className={`${clrClass(val)}${sepCls}`}>
          {val || '—'}
        </td>
      )
    }

    // Special: MTO/MTS pill
    if (col.key === 'mto_mts') {
      return (
        <td key={col.key} className={sepCls}>
          {val
            ? <span className={val === 'MTO' ? 'r3ss-mto' : 'r3ss-mts'}>{val}</span>
            : '—'}
        </td>
      )
    }

    // Special: priority
    if (col.key === 'priority') {
      return <td key={col.key} className={`${priClass(val)}${sepCls}`}>{val || '—'}</td>
    }

    // Numeric
    if (col.num) {
      const cls = [
        'num',
        col.accent ? 'r3ss-accent' : '',
        sepCls,
      ].filter(Boolean).join(' ')
      return (
        <td key={col.key} className={cls}
          style={col.bold ? { fontWeight: 700 } : undefined}>
          {fmtN(val, col.dec)}
        </td>
      )
    }

    // Text
    return <td key={col.key} className={sepCls || undefined}>{val || '—'}</td>
  }

  /* ── Render ────────────────────────────────────────────────── */

  return (
    <section className="screen">
      <TopBar subtitle="PPC Department" />
      <div className="wrap wrap-wide">

        {/* Breadcrumbs */}
        <div className="crumbs">
          <Link to="/departments">Home</Link> ›{' '}
          <Link to="/ppc-data">PPC Data</Link> › R3SS Plan
        </div>
        <button className="backbtn" onClick={() => navigate('/ppc-data')}>
          ← Back to PPC Data
        </button>

        {/* ─── Header ─────────────────────────────────────────── */}
        <div className="page-head" style={{ marginBottom: 14 }}>
          <div>
            <h2 className="title">R3SS Production Plan</h2>
            {data && (
              <p className="sub" style={{ marginBottom: 0 }}>
                <strong>{planMonth || '—'}</strong> · {data.row_count} items
                {data.uploaded_at && (
                  <> · computed {new Date(data.uploaded_at).toLocaleDateString('en-IN', {
                    day: 'numeric', month: 'short', year: 'numeric',
                    hour: '2-digit', minute: '2-digit',
                  })}</>
                )}
                {data.uploader && <> · by {data.uploader}</>}
              </p>
            )}
          </div>
          <div className="head-buttons">
            <button className="btn-upload" onClick={handleCompute} disabled={computing}
              style={{ background: '#2e7d32', fontSize: 13, padding: '8px 14px' }}>
              {computing
                ? <><span className="spinner" style={{ borderTopColor: '#fff', borderColor: 'rgba(255,255,255,.35)' }} />{computeStep || 'Computing…'}</>
                : '⚡ Recompute'}
            </button>
            <button
              className="backbtn"
              onClick={() => setShowUpload(s => !s)}
              style={{ fontSize: 13, padding: '7px 12px', margin: 0 }}
            >
              {showUpload ? '✕ Close Upload' : '⬆ Upload'}
            </button>
            <a
              href={R3SS_SHEET_URL}
              target="_blank" rel="noopener noreferrer"
              className="backbtn"
              style={{ fontSize: 13, padding: '7px 12px', margin: 0, textDecoration: 'none' }}
            >
              📊 Google Sheet ↗
            </a>
          </div>
        </div>

        {/* ─── Upload panel (collapsible) ─────────────────────── */}
        {showUpload && (
          <div className="panel" style={{ marginBottom: 12 }}>
            <h3 style={{ marginBottom: 8, fontSize: 14 }}>Upload R3 SS.xlsx</h3>
            <form onSubmit={handleUpload} style={{ display: 'flex', gap: 10, alignItems: 'end' }}>
              <input ref={fileRef} type="file" accept=".xlsx,.xlsm,.xls" style={{ fontSize: 13 }} />
              <button type="submit" className="btn-upload" disabled={uploading}
                style={{ padding: '7px 14px', fontSize: 13 }}>
                {uploading ? 'Uploading…' : '⬆ Upload'}
              </button>
            </form>
            {uploadResult && (
              <div className="upload-status success" style={{ marginTop: 10 }}>
                ✅ <strong>{uploadResult.plan_rows}</strong> rows parsed.
                {' '}{uploadResult.date_columns} date columns.
                {uploadResult.plan_month && <> Plan month: <strong>{uploadResult.plan_month}</strong>.</>}
              </div>
            )}
          </div>
        )}

        {/* ─── Error ──────────────────────────────────────────── */}
        {error && (
          <div className="upload-status error" style={{ marginBottom: 12 }}>
            {error}
            <button onClick={() => setError('')}
              style={{ float: 'right', background: 'none', border: 'none', cursor: 'pointer', fontWeight: 700, color: '#991b1b' }}>✕</button>
          </div>
        )}

        {/* ─── Loading ────────────────────────────────────────── */}
        {loading && <div className="loading"><span className="spinner" />Loading R3SS plan…</div>}

        {/* ─── Empty state ────────────────────────────────────── */}
        {!loading && (!data || data.rows.length === 0) && (
          <div className="panel" style={{ textAlign: 'center', padding: 44 }}>
            <div style={{ fontSize: 48, marginBottom: 14 }}>📋</div>
            <h3 style={{ border: 'none', marginBottom: 8 }}>R3SS tab is empty</h3>
            <p className="note" style={{ marginBottom: 16 }}>
              The dashboard reads the R3SS tab from the connected Google Sheet.
              Make sure all 6 source tabs are uploaded, then click Recompute.
            </p>
            <button className="btn-upload" onClick={handleCompute} disabled={computing}
              style={{ background: '#2e7d32' }}>
              {computing ? (computeStep || 'Computing…') : '⚡ Recompute from Google Sheet'}
            </button>
          </div>
        )}

        {/* ─── Main content ───────────────────────────────────── */}
        {!loading && data && data.rows.length > 0 && (<>

          {/* Summary tiles */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(125px, 1fr))',
            gap: 8, marginBottom: 12,
          }}>
            {[
              { label: 'Items',       value: filteredRows.length, color: 'var(--accent)' },
              { label: 'Total Demand',value: totals.total_demand,  color: '#b05520' },
              { label: 'To Plan',     value: totals.to_plan,       color: 'var(--accent)' },
              { label: 'Total Plan (HW+MIT)', value: totals.total_plan, color: 'var(--ok)' },
              { label: 'SO Pending',  value: totals.sales_order_pending, color: '#7c5c00' },
              { label: 'Difference',
                value: totals.difference,
                color: (totals.difference || 0) < 0 ? 'var(--bad)' : 'var(--ok)' },
            ].map(t => (
              <div key={t.label} className="panel" style={{ textAlign: 'center', padding: '10px 6px', marginBottom: 0 }}>
                <div style={{
                  fontSize: 20, fontWeight: 800, color: t.color,
                  fontVariantNumeric: 'tabular-nums',
                }}>
                  {typeof t.value === 'number' ? t.value.toLocaleString('en-IN') : '—'}
                </div>
                <div style={{
                  fontSize: 10, color: 'var(--muted)', textTransform: 'uppercase',
                  letterSpacing: '.04em', fontWeight: 700,
                }}>
                  {t.label}
                </div>
              </div>
            ))}
          </div>

          {/* ─── Filter bar ──────────────────────────────────── */}
          <div className="r3ss-filters">
            {/* Search */}
            <form onSubmit={handleSearch} style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
              <input
                type="text" value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search item…"
                style={{
                  padding: '4px 8px', border: '1px solid #cbd5e1', borderRadius: 6,
                  fontSize: 12, width: 140,
                }}
              />
              <button type="submit" style={{
                padding: '4px 10px', border: '1px solid #cbd5e1', borderRadius: 6,
                fontSize: 11, fontWeight: 700, background: '#fff', cursor: 'pointer',
              }}>
                Go
              </button>
              {searchApplied && (
                <button type="button" onClick={clearSearch} style={{
                  padding: '4px 8px', border: '1px solid #cbd5e1', borderRadius: 6,
                  fontSize: 11, background: '#fff', cursor: 'pointer',
                }}>✕</button>
              )}
            </form>

            <div style={{ width: 1, height: 22, background: '#cbd5e1' }} />

            {/* Dropdown filters */}
            {[
              { key: 'section',       label: 'Section' },
              { key: 'family',        label: 'Family' },
              { key: 'product_group', label: 'Group' },
              { key: 'mto_mts',       label: 'MTO/MTS' },
              { key: 'priority',      label: 'Priority' },
            ].map(f => (
              <div key={f.key} className="r3ss-filter">
                <label>{f.label}</label>
                <select
                  value={filters[f.key] || ''}
                  onChange={e => setFilter(f.key, e.target.value)}
                >
                  <option value="">All</option>
                  {(filterOpts[f.key] || []).map(v => (
                    <option key={v} value={v}>{v}</option>
                  ))}
                </select>
              </div>
            ))}

            {activeFilterCount > 0 && (
              <button onClick={clearFilters} style={{
                padding: '4px 8px', border: '1px solid #e9ccc8', borderRadius: 6,
                fontSize: 11, fontWeight: 700, background: '#fef2f2',
                color: '#c62828', cursor: 'pointer',
              }}>
                Clear ({activeFilterCount})
              </button>
            )}

            <div style={{ flex: 1 }} />

            {/* Column group toggles */}
            <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
              {Object.entries(GROUPS).map(([k, g]) => (
                <button
                  key={k}
                  className={`r3ss-coltoggle${groups[k] ? ' on' : ''}`}
                  onClick={() => toggleGroup(k)}
                >
                  {groups[k] ? '✓ ' : ''}{g.label}
                </button>
              ))}
            </div>
          </div>

          {/* ─── The Sheet Table ─────────────────────────────── */}
          {filteredRows.length === 0 ? (
            <div className="panel" style={{ textAlign: 'center', padding: 30 }}>
              <p className="note">No items match the current filters.</p>
              <button onClick={() => { clearFilters(); if (searchApplied) clearSearch() }}
                className="backbtn" style={{ marginTop: 10 }}>
                Clear all filters
              </button>
            </div>
          ) : (
            <div className="r3ss-scroll">
              <table className="r3ss-tbl">
                <thead>
                  <tr>
                    {/* Frozen: item_code (ERP Code in R3SS file) */}
                    <th className="sticky-col" style={{ textAlign: 'left' }}>ERP Code</th>
                    {/* Frozen: description (Cust Part No in R3SS file) */}
                    <th className="sticky-col2" style={{ textAlign: 'left' }}>Cust Part No</th>
                    {/* Fixed columns */}
                    {visCols.map(c => (
                      <th key={c.key}
                        className={[c.num ? 'num' : '', c.last ? 'group-sep' : ''].filter(Boolean).join(' ') || undefined}>
                        {c.label}
                      </th>
                    ))}
                    {/* Day columns */}
                    {groups.days && dayKeys.map(dk => {
                      const day = parseInt(dk.split('-')[2], 10)
                      const isWknd = weekendDays.has(dk)
                      return (
                        <th key={dk}
                          className="day-col num"
                          title={dk}
                          style={isWknd ? { background: '#374a63', color: '#7b8fa8' } : undefined}>
                          {day}
                        </th>
                      )
                    })}
                  </tr>
                </thead>

                <tbody>
                  {filteredRows.map((row, i) => {
                    const d = row.data
                    return (
                      <tr key={d.item_code || i}>
                        {/* Frozen: item_code */}
                        <td className="sticky-col" style={{
                          fontFamily: "'SF Mono',Consolas,monospace",
                          fontSize: 11.5, fontWeight: 600, letterSpacing: '.01em',
                        }}>
                          {d.item_code}
                        </td>
                        {/* Frozen: description */}
                        <td className="sticky-col2" title={d.description} style={{
                          fontSize: 11.5, maxWidth: 170, overflow: 'hidden', textOverflow: 'ellipsis',
                        }}>
                          {d.description || '—'}
                        </td>
                        {/* Fixed columns */}
                        {visCols.map(c => renderCell(c, d))}
                        {/* Day columns */}
                        {groups.days && dayKeys.map(dk => {
                          const v = d.days?.[dk] || 0
                          const isWknd = weekendDays.has(dk)
                          return (
                            <td key={dk}
                              className="day-col num"
                              style={
                                v ? { fontWeight: 600 }
                                : isWknd ? { background: '#f1f5f9', color: '#b0bac7' }
                                : undefined
                              }>
                              {fmtDay(v)}
                            </td>
                          )
                        })}
                      </tr>
                    )
                  })}
                </tbody>

                <tfoot>
                  <tr>
                    <td className="sticky-col" style={{ fontWeight: 800, fontSize: 11.5 }}>TOTAL</td>
                    <td className="sticky-col2" style={{ color: 'rgba(255,255,255,.55)', fontSize: 11 }}>
                      {filteredRows.length} items
                    </td>
                    {visCols.map(c => (
                      <td key={c.key}
                        className={[c.num ? 'num' : '', c.last ? 'group-sep' : ''].filter(Boolean).join(' ') || undefined}>
                        {c.sum ? fmtN(totals[c.key], c.dec) : ''}
                      </td>
                    ))}
                    {groups.days && dayKeys.map(dk => (
                      <td key={dk} className="day-col num">{fmtDay(totals[dk])}</td>
                    ))}
                  </tr>
                </tfoot>
              </table>
            </div>
          )}

          {/* Row count / footer note */}
          <p className="note" style={{ marginTop: 8 }}>
            Showing {filteredRows.length} of {data.rows.length} items
            {searchApplied && <> · search: "{searchApplied}"</>}
            {activeFilterCount > 0 && <> · {activeFilterCount} filter{activeFilterCount > 1 ? 's' : ''} active</>}
            {' · '}
            <Link to="/ppc-data/browse?table=r3ss_plan" style={{ fontSize: 12 }}>
              Open in Data Browser
            </Link>
          </p>

        </>)}
      </div>
    </section>
  )
}
