import React, { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import TopBar from '../components/TopBar'

/* ── Formatters ── */
const R = { textAlign: 'right', fontVariantNumeric: 'tabular-nums' }

function fmt(n) {
  if (n == null || isNaN(n)) return '—'
  return Number(n).toLocaleString('en-IN', { maximumFractionDigits: 0 })
}

function fmtD(n) {
  if (n == null || isNaN(n)) return '—'
  return Number(n).toLocaleString('en-IN', { maximumFractionDigits: 1 })
}

function fmtCr(n) {
  if (n == null || isNaN(n) || n === 0) return '₹0'
  const abs = Math.abs(n)
  const sign = n < 0 ? '-' : ''
  if (abs >= 1e7) return `${sign}₹${(abs / 1e7).toFixed(2)} Cr`
  if (abs >= 1e5) return `${sign}₹${(abs / 1e5).toFixed(2)} L`
  return `${sign}₹${Number(abs).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
}

function fmtV(n) {
  if (!n || n === 0) return '—'
  const abs = Math.abs(n)
  if (abs >= 1e7) return '₹' + (abs / 1e7).toFixed(1) + ' Cr'
  if (abs >= 1e5) return '₹' + (abs / 1e5).toFixed(1) + ' L'
  return '₹' + Number(abs).toLocaleString('en-IN', { maximumFractionDigits: 0 })
}


/* ── Colour constants matching the reference spreadsheet ── */
const C = {
  navy:    '#1a3a5c',   // VOLUME & FULFILMENT, HEALTH RATIOS headers
  red:     '#b71c1c',   // EXCEPTIONS header, Top 10 shortfall/gap
  olive:   '#5d5a1e',   // TYPE BREAKDOWN, Top 10 excess inv
  teal:    '#2e5949',   // SALES INSIGHT TAGS header
  gold:    '#b8860b',   // OEM Segment badge
  green:   '#2e7d32',   // data labels, positive %
  redText: '#c62828',   // negative / critical values
  muted:   '#555',
  rowAlt:  '#f8fafb',   // subtle alternating row
  hdrText: '#fff',
}

/* ── Shared section-header bar ── */
function SectionBar({ bg, children, columns }) {
  return (
    <tr style={{ background: bg }}>
      <td
        colSpan={columns ? undefined : 99}
        style={{
          color: C.hdrText, fontWeight: 800, fontSize: 13,
          padding: '8px 14px', letterSpacing: '.02em',
        }}
      >
        {children}
      </td>
      {columns && columns.map((col, i) => (
        <td key={i} style={{
          color: C.hdrText, fontWeight: 700, fontSize: 12,
          padding: '8px 10px', textAlign: 'right',
        }}>
          {col}
        </td>
      ))}
    </tr>
  )
}

function pickSums(v, key) {
  return {
    total: v.total?.[key] ?? 0,
    focus: v.focus?.[key] ?? 0,
    regular: v.regular?.[key] ?? 0,
  }
}


/* ═══════════════════════════════════════════════════════════════════
   Main component
   ═══════════════════════════════════════════════════════════════════ */
export default function SopDemandSupply() {
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => { load() }, [])

  function load() {
    setLoading(true)
    setError('')
    api.sopDemandSupply()
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }

  function refresh() {
    setRefreshing(true)
    setError('')
    api.sopRefresh()
      .then(() => {
        // Backend starts a background recompute (~20s).
        // Reload the dashboard after a delay to pick up fresh data.
        setTimeout(() => {
          load()
          setRefreshing(false)
        }, 22000)
      })
      .catch((err) => {
        setError(err.message)
        setRefreshing(false)
      })
  }

  const v = data?.volume
  const h = data?.health
  const ex = data?.exceptions
  const sg = data?.shortfall_gaps
  const se = data?.surplus_excess
  const fi = data?.financial_impact
  const ins = data?.insights_summary
  const ev = data?.exceptions_value

  /* ── Table cell styles ── */
  const label = { color: C.green, fontWeight: 500, padding: '6px 14px', fontSize: 13 }
  const num   = { ...R, padding: '6px 14px', fontWeight: 600, fontSize: 13 }
  const numBold = { ...num, fontWeight: 800 }
  const pct   = { ...R, padding: '6px 14px', fontWeight: 600, fontSize: 13, color: C.muted }

  return (
    <section className="screen">
      <TopBar subtitle="S&OP Department" />
      <div className="wrap wrap-wide">
        <div className="crumbs">
          <Link to="/departments">Home</Link> ›{' '}
          <Link to="/s-and-op">S&amp;OP</Link> › Demand &amp; Supply
        </div>
        <button className="backbtn" onClick={() => navigate('/s-and-op')}>
          ← Back to S&amp;OP
        </button>

        <div className="panel" style={{ padding: 0, overflow: 'hidden' }}>

          {/* ── Page header (matches reference row 2-3) ── */}
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
            padding: '22px 24px 14px', borderBottom: '1px solid #e2e8f0',
          }}>
            <div>
              <h3 style={{ fontSize: 22, fontWeight: 800, color: '#1a2a3a', margin: 0 }}>
                Demand &amp; Supply Visibility Dashboard
              </h3>
              <p style={{
                margin: '6px 0 0', fontSize: 13, fontStyle: 'italic', color: C.green,
              }}>
                Live summary of all {v?.total_items || '—'} line items in Append1 — refreshes automatically as ERP data flows in.
              </p>
            </div>
            <div style={{ textAlign: 'right', flexShrink: 0 }}>
              <div style={{ fontSize: 22, fontWeight: 800, color: C.gold }}>OEM Segment</div>
              <div style={{ fontSize: 14, fontWeight: 700, color: '#333', marginTop: 2 }}>
                As of {new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }).replace(/ /g, '-')}
              </div>
              <div style={{ display: 'flex', gap: 8, marginTop: 10, justifyContent: 'flex-end' }}>
                <button
                  className="btn-upload"
                  onClick={() => navigate('/s-and-op/demand-supply/upload')}
                  style={{ fontSize: 12, padding: '6px 14px' }}
                >
                  📤 Upload Data
                </button>
                <button
                  type="button"
                  className="btn-upload"
                  onClick={load}
                  disabled={loading || refreshing}
                  style={{ background: 'var(--steel)', fontSize: 12, padding: '6px 14px' }}
                >
                  {loading ? 'Loading…' : '⟳ Refresh'}
                </button>
                <button
                  type="button"
                  className="btn-upload"
                  onClick={refresh}
                  disabled={loading || refreshing}
                  style={{ background: '#e67e22', fontSize: 12, padding: '6px 14px' }}
                  title="Recompute Append1 from Google Sheet source data"
                >
                  {refreshing ? '⏳ Recomputing…' : '🔄 Recompute'}
                </button>
              </div>
            </div>
          </div>

          {/* ── Upload status strip ── */}
          {data?.uploads && (
            <div style={{
              display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap',
              padding: '8px 24px', background: '#f5f9fd', borderBottom: '1px solid #e2e8f0',
              fontSize: 12, color: '#555',
            }}>
              {Object.entries(data.uploads).map(([key, info], i, arr) => (
                <React.Fragment key={key}>
                  <span style={{ color: info.has_data ? C.green : '#bbb' }}>
                    {info.has_data ? '●' : '○'}
                  </span>
                  <span>
                    {info.label}
                    {info.has_data && <b> ({info.row_count.toLocaleString('en-IN')})</b>}
                  </span>
                  {i < arr.length - 1 && <span style={{ color: '#ccc' }}>·</span>}
                </React.Fragment>
              ))}
            </div>
          )}

          {loading && !data && <div className="loading" style={{ padding: 40 }}>Loading dashboard…</div>}
          {error && <div className="upload-status error" style={{ margin: 14 }}>{error}</div>}

          {data && !data.has_data && (
            <div style={{ textAlign: 'center', padding: '3rem' }}>
              <div style={{ fontSize: 48, marginBottom: 16 }}>📭</div>
              <p style={{ fontSize: '1.1rem', color: '#666', marginBottom: 20 }}>
                {data.message || 'No data uploaded yet. Upload the 5 data files to power this dashboard.'}
              </p>
              <button className="btn-upload" onClick={() => navigate('/s-and-op/demand-supply/upload')}>
                📤 Upload Data Files
              </button>
            </div>
          )}

          {data?.has_data && v && (
            <div style={{ overflowX: 'auto' }}>
              <table style={{
                width: '100%', borderCollapse: 'collapse', fontFamily: 'Calibri, -apple-system, sans-serif',
                minWidth: 700,
              }}>
                <colgroup>
                  <col style={{ width: '48%' }} />
                  <col style={{ width: '15%' }} />
                  <col style={{ width: '13%' }} />
                  <col style={{ width: '14%' }} />
                  <col style={{ width: '10%' }} />
                </colgroup>
                <tbody>

                  {/* ═══ VOLUME & FULFILMENT ═══ */}
                  <SectionBar bg={C.navy} columns={['Total', 'Focus', 'Regular']}>
                    VOLUME &amp; FULFILMENT
                  </SectionBar>
                  <VRow label="Total Items" t={v.total_items} f={v.focus_items} r={v.regular_items} bold />
                  <VRow label="Original Forecast (units)" t={v.total?.forecast} f={v.focus?.forecast} r={v.regular?.forecast} />
                  <VRow label="Ops+Sales-Reviewed Forecast Committed" t={v.total?.committed} f={v.focus?.committed} r={v.regular?.committed} />
                  <VRow label="Actual Sales Demand" t={v.total?.actual_sales} f={v.focus?.actual_sales} r={v.regular?.actual_sales} />
                  <VRow label="Additional Demand (Punched, Not Committed)" t={v.total?.additional_demand} f={v.focus?.additional_demand} r={v.regular?.additional_demand} neg />
                  <VRow label="Actual Production (units)" t={v.total?.production} f={v.focus?.production} r={v.regular?.production} />
                  <VRow label="Actual Dispatch (units)" t={v.total?.dispatch} f={v.focus?.dispatch} r={v.regular?.dispatch} />
                  <VRow label="Closing Inventory (units)" t={v.total?.closing_inventory} f={v.focus?.closing_inventory} r={v.regular?.closing_inventory} />
                  <VRow label="Free Inventory above Green Level" t={v.total?.free_inventory} f={v.focus?.free_inventory} r={v.regular?.free_inventory} />

                  {/* spacer */}
                  <tr><td colSpan={5} style={{ height: 12 }}></td></tr>

                  {/* ═══ HEALTH RATIOS ═══ */}
                  <SectionBar bg={C.navy} columns={['Total', 'Focus', 'Regular']}>
                    HEALTH RATIOS
                  </SectionBar>
                  <PctRow label="Dispatch Fulfilment (Dispatch ÷ Committed)" t={h.dispatch_fulfilment} f={h.focus?.dispatch_fulfilment} r={h.regular?.dispatch_fulfilment} />
                  <PctRow label="Forecast Accuracy (Hit Rate — within 10%)" t={h.forecast_accuracy} f={h.focus?.forecast_accuracy} r={h.regular?.forecast_accuracy} remark="-10% to +10%" />
                  <PctRow label="Production Coverage (capped — surpluses can't mask shortfalls)" t={h.production_coverage} f={h.focus?.production_coverage} r={h.regular?.production_coverage} />

                  {/* spacer */}
                  <tr><td colSpan={5} style={{ height: 12 }}></td></tr>

                  {/* ═══ EXCEPTIONS — ITEM COUNTS ═══ */}
                  <SectionBar bg={C.red} columns={['Count', 'Focus', 'Regular']}>
                    EXCEPTIONS — ITEM COUNTS
                  </SectionBar>
                  {/* sub-header with % of Items */}
                  <ExcRow label="Items with Production-Driven Shortfall" data={ex.production_shortfall} total={v.total_items} />
                  <ExcRow label="Items in Production Surplus — Current Period" data={ex.production_surplus} total={v.total_items} />
                  <ExcRow label="Items with Excess Opening Stock" data={ex.excess_opening_stock} total={v.total_items} />
                  <ExcRow label="Items with Dispatch Gap (shippable from stock)" data={ex.dispatch_gap} total={v.total_items} />
                  <ExcRow label="Items Below Green Level (Closing Inv < GL)" data={ex.below_green_level} total={v.total_items} isRed />
                  <ExcRow label="Items At/Above Green Level (Closing Inv ≥ GL)" data={ex.above_green_level} total={v.total_items} isGreen />

                  {/* spacer */}
                  <tr><td colSpan={5} style={{ height: 12 }}></td></tr>

                  {/* ═══ TYPE BREAKDOWN — MTS / MTO / TBC ═══ */}
                  <TypeSection types={data.type_breakdown} totalItems={v.total_items} />

                  {/* spacer */}
                  <tr><td colSpan={5} style={{ height: 12 }}></td></tr>

                  {/* ═══ SALES INSIGHT TAGS ═══ */}
                  <TagSection
                    title="SALES INSIGHT TAGS — DISTRIBUTION"
                    bg={C.teal}
                    tags={ins?.sales_tags}
                    total={v.total_items}
                    order={['On Target', 'Over-Delivered', 'Short Delivery',
                      'Dispatch Gap', 'Production Shortfall',
                      'Forecast Bullseye', 'Forecast Drift (Minor)', 'Forecast Drift (Moderate)', 'Forecast Drift (Major)']}
                  />

                  {/* spacer */}
                  <tr><td colSpan={5} style={{ height: 12 }}></td></tr>

                  {/* ═══ OPERATIONS INSIGHT TAGS ═══ */}
                  <TagSection
                    title="OPERATIONS INSIGHT TAGS — DISTRIBUTION"
                    bg={C.olive}
                    tags={ins?.ops_tags}
                    total={v.total_items}
                    order={['Healthy Stock', 'Production Shortfall', 'Below Safety', 'Stock-Out Risk',
                      'Excess Inventory', 'Production Surplus', 'Unsold MTO Stock', 'Over-Production',
                      'Type TBC', 'Capacity Gap (Major)', 'Capacity Gap (Moderate)', 'Capacity Gap (Minor)', 'Ops Over-Commit']}
                  />

                  {/* spacer */}
                  <tr><td colSpan={5} style={{ height: 12 }}></td></tr>

                  {/* ═══ TOP 10 — PRODUCTION SHORTFALL ═══ */}
                  <Top10Section
                    title="TOP 10 — PRODUCTION-DRIVEN SHORTFALL (Units customer is short, no stock to cover)"
                    bg={C.red}
                    items={data.top10_shortfall}
                    columns={[
                      { key: 'committed', label: 'Committed' },
                      { key: 'production', label: 'Production' },
                      { key: 'dispatch', label: 'Dispatch' },
                      { key: 'shortfall', label: 'Shortfall', color: C.redText },
                    ]}
                  />

                  {/* spacer */}
                  <tr><td colSpan={5} style={{ height: 12 }}></td></tr>

                  {/* ═══ TOP 10 — DISPATCH GAP ═══ */}
                  <Top10Section
                    title="TOP 10 — DISPATCH GAP (Units shippable from stock to close customer commitment)"
                    bg={C.red}
                    items={data.top10_dispatch_gap}
                    columns={[
                      { key: 'committed', label: 'Committed' },
                      { key: 'dispatch', label: 'Dispatch' },
                      { key: 'gap', label: 'Gap', color: C.redText },
                      { key: 'closing_stock', label: 'Closing Stock' },
                    ]}
                  />

                  {/* spacer */}
                  <tr><td colSpan={5} style={{ height: 12 }}></td></tr>

                  {/* ═══ TOP 10 — EXCESS FREE INVENTORY ═══ */}
                  <Top10Section
                    title="TOP 10 — EXCESS FREE INVENTORY (Capital Tied Up Above Green Level)"
                    bg={C.olive}
                    items={data.top10_free_inventory}
                    columns={[
                      { key: 'closing', label: 'Closing Inv' },
                      { key: 'green_level', label: 'Green Level' },
                      { key: 'free_inv', label: 'Free Inv', color: C.green },
                    ]}
                  />

                  {/* spacer */}
                  <tr><td colSpan={5} style={{ height: 12 }}></td></tr>

                  {/* ═══ TOP 10 — BELOW GREEN LEVEL ═══ */}
                  <Top10Section
                    title="TOP 10 — BELOW GREEN LEVEL (Closing Inventory below Safety Stock)"
                    bg={C.red}
                    items={data.top10_below_green}
                    columns={[
                      { key: 'closing', label: 'Closing Stock' },
                      { key: 'green_level', label: 'Green Level' },
                      { key: 'deficit', label: 'Deficit', color: C.redText },
                    ]}
                  />

                  {/* spacer */}
                  <tr><td colSpan={5} style={{ height: 12 }}></td></tr>

                  {/* ═══ EXCEPTIONS — Qty & ₹ VALUE ═══ */}
                  <ExceptionsValueSection ev={ev} />

                  {/* ═══ FINANCIAL IMPACT ═══ */}
                  <FinancialSection fi={fi} totalItems={v.total_items} />

                </tbody>
              </table>
            </div>
          )}

          {/* bottom padding */}
          <div style={{ height: 20 }}></div>
        </div>
      </div>
    </section>
  )
}


/* ═══════════════════════════════════════════════════════════════════
   Row components — spreadsheet-style matching the reference
   ═══════════════════════════════════════════════════════════════════ */

/* Volume row — label + Total/Focus/Regular */
function VRow({ label: lbl, t, f, r, bold, neg }) {
  const labelS = {
    color: C.green, fontWeight: bold ? 700 : 500,
    padding: '5px 14px', fontSize: 13, borderBottom: '1px solid #f0f0f0',
  }
  const numS = {
    ...R, padding: '5px 14px', fontWeight: bold ? 800 : 600, fontSize: 13,
    borderBottom: '1px solid #f0f0f0',
  }
  const isNeg = (v) => neg && v < 0
  return (
    <tr style={bold ? { background: '#f5f8ff' } : undefined}>
      <td style={labelS} colSpan={2}>{lbl}</td>
      <td style={{ ...numS, color: isNeg(t) ? C.redText : undefined }}>{fmt(t)}</td>
      <td style={{ ...numS, color: isNeg(f) ? C.redText : undefined }}>{fmt(f)}</td>
      <td style={{ ...numS, color: isNeg(r) ? C.redText : undefined }}>{fmt(r)}</td>
    </tr>
  )
}

/* Health % row — green percentages */
function PctRow({ label: lbl, t, f, r, remark }) {
  const labelS = {
    color: C.green, fontWeight: 500, padding: '5px 14px', fontSize: 13,
    borderBottom: '1px solid #f0f0f0',
  }
  const pctS = {
    ...R, padding: '5px 14px', fontWeight: 700, fontSize: 13,
    color: C.green, borderBottom: '1px solid #f0f0f0',
  }
  return (
    <tr>
      <td style={labelS} colSpan={2}>{lbl}</td>
      <td style={pctS}>{t || 0}%</td>
      <td style={pctS}>{f || 0}%</td>
      <td style={pctS}>{r || 0}%</td>
    </tr>
  )
}

/* Exception count row */
function ExcRow({ label: lbl, data, total, isRed, isGreen }) {
  const d = data || {}
  const t = d.total ?? d ?? 0
  const f = d.focus ?? 0
  const rg = d.regular ?? 0
  const pctVal = total > 0 ? `${(t / total * 100).toFixed(1)}%` : '—'

  const color = isRed ? C.redText : isGreen ? C.green : undefined
  const labelS = {
    fontWeight: 500, padding: '5px 14px', fontSize: 13,
    borderBottom: '1px solid #f0f0f0',
    color: isRed ? C.redText : isGreen ? C.green : '#333',
  }
  const numS = {
    ...R, padding: '5px 14px', fontWeight: 700, fontSize: 13,
    borderBottom: '1px solid #f0f0f0', color,
  }
  return (
    <tr>
      <td style={labelS} colSpan={1}>{lbl}</td>
      <td style={numS}>{fmt(t)}</td>
      <td style={numS}>{fmt(f)}</td>
      <td style={numS}>{fmt(rg)}</td>
      <td style={{ ...R, padding: '5px 14px', fontSize: 13, color: color || C.muted, borderBottom: '1px solid #f0f0f0' }}>
        {pctVal}
      </td>
    </tr>
  )
}


/* ═══ TYPE BREAKDOWN section ═══ */
function TypeSection({ types, totalItems }) {
  if (!types || types.length === 0) return null
  const hdrS = {
    color: C.hdrText, fontWeight: 700, fontSize: 12,
    padding: '8px 10px', textAlign: 'right',
  }
  const labelS = { fontWeight: 600, padding: '5px 14px', fontSize: 13, borderBottom: '1px solid #f0f0f0' }
  const numS = { ...R, padding: '5px 14px', fontWeight: 600, fontSize: 13, borderBottom: '1px solid #f0f0f0' }

  // Combine capacity gap tags if present
  const typeLabels = { MTS: 'MTS — Make to Stock', MTO: 'MTO — Make to Order', TBC: 'TBC — Classification Pending' }
  const totals = { items: 0, forecast: 0, committed: 0, production: 0, dispatch: 0 }
  types.forEach(t => {
    totals.items += t.items
    totals.forecast += t.forecast
    totals.committed += t.committed || 0
    totals.production += t.production
    totals.dispatch += t.dispatch
  })

  return (
    <>
      <tr style={{ background: C.olive }}>
        <td style={{ color: C.hdrText, fontWeight: 800, fontSize: 13, padding: '8px 14px' }} colSpan={1}>
          TYPE BREAKDOWN — MTS / MTO / TBC
        </td>
        <td style={hdrS}>Items</td>
        <td style={hdrS}>Share %</td>
        <td style={hdrS}>Forecast</td>
        <td style={hdrS}>Production</td>
      </tr>
      <tr style={{ background: '#f5f5f0' }}>
        <td style={{ fontWeight: 700, fontSize: 11, padding: '4px 14px', color: C.muted }}>Type</td>
        <td style={{ ...R, fontSize: 11, padding: '4px 10px', color: C.muted, fontWeight: 700 }}></td>
        <td style={{ ...R, fontSize: 11, padding: '4px 10px', color: C.muted, fontWeight: 700 }}></td>
        <td style={{ ...R, fontSize: 11, padding: '4px 10px', color: C.muted, fontWeight: 700 }}>Committed</td>
        <td style={{ ...R, fontSize: 11, padding: '4px 10px', color: C.muted, fontWeight: 700 }}>Dispatch</td>
      </tr>
      {types.map((t, i) => {
        const isTBC = t.type === 'TBC'
        const color = isTBC ? C.redText : undefined
        return (
          <tr key={i}>
            <td style={{ ...labelS, color }}>{typeLabels[t.type] || t.type}</td>
            <td style={{ ...numS, color }}>{fmt(t.items)}</td>
            <td style={{ ...numS, color }}>{t.share_pct}%</td>
            <td style={{ ...numS, color }}>{fmt(t.forecast)}</td>
            <td style={{ ...numS, color }}>{fmt(t.dispatch)}</td>
          </tr>
        )
      })}
      <tr style={{ background: '#f5f8ff' }}>
        <td style={{ ...labelS, fontWeight: 800 }}>Total</td>
        <td style={{ ...numS, fontWeight: 800 }}>{fmt(totals.items)}</td>
        <td style={{ ...numS, fontWeight: 800 }}>100.0%</td>
        <td style={{ ...numS, fontWeight: 800 }}>{fmt(totals.forecast)}</td>
        <td style={{ ...numS, fontWeight: 800 }}>{fmt(totals.dispatch)}</td>
      </tr>
    </>
  )
}


/* ═══ TAG DISTRIBUTION section ═══ */
function TagSection({ title, bg, tags, total, order }) {
  if (!tags) return null
  const hdrS = {
    color: C.hdrText, fontWeight: 700, fontSize: 12,
    padding: '8px 10px', textAlign: 'right',
  }
  const labelS = { fontWeight: 500, padding: '5px 14px', fontSize: 13, color: '#333', borderBottom: '1px solid #f0f0f0' }
  const numS = { ...R, padding: '5px 14px', fontWeight: 600, fontSize: 13, borderBottom: '1px solid #f0f0f0' }

  // Merge capacity gap tags for display
  const mergedTags = { ...tags }

  return (
    <>
      <tr style={{ background: bg }}>
        <td style={{ color: C.hdrText, fontWeight: 800, fontSize: 13, padding: '8px 14px' }} colSpan={3}>
          {title}
        </td>
        <td colSpan={2}></td>
      </tr>
      <tr style={{ background: '#f5f5f0' }}>
        <td style={{ fontWeight: 700, fontSize: 11, padding: '4px 14px', color: C.muted }}>Tag</td>
        <td style={{ ...R, fontSize: 11, padding: '4px 10px', color: C.muted, fontWeight: 700 }}>Items</td>
        <td style={{ ...R, fontSize: 11, padding: '4px 10px', color: C.muted, fontWeight: 700 }}>Share %</td>
        <td colSpan={2}></td>
      </tr>
      {order.map((tag, i) => {
        const count = mergedTags[tag] || 0
        const sharePct = total > 0 ? `${(count / total * 100).toFixed(1)}%` : '0.0%'
        return (
          <tr key={i}>
            <td style={labelS}>{tag}</td>
            <td style={numS}>{fmt(count)}</td>
            <td style={numS}>{sharePct}</td>
            <td colSpan={2}></td>
          </tr>
        )
      })}
    </>
  )
}


/* ═══ TOP 10 section ═══ */
function Top10Section({ title, bg, items, columns }) {
  if (!items || items.length === 0) return null
  const hdrS = {
    color: C.hdrText, fontWeight: 700, fontSize: 12,
    padding: '8px 10px', textAlign: 'right',
  }
  const subHdrS = {
    fontWeight: 700, fontSize: 11, padding: '4px 10px', color: C.muted,
    background: '#f5f5f0', borderBottom: '1px solid #e0e0e0',
  }
  const labelS = { fontWeight: 500, padding: '5px 10px', fontSize: 12, borderBottom: '1px solid #f0f0f0' }
  const numS = { ...R, padding: '5px 10px', fontWeight: 600, fontSize: 12, borderBottom: '1px solid #f0f0f0' }
  const monoS = { fontWeight: 600, fontFamily: 'monospace', fontSize: 11.5, padding: '5px 10px', borderBottom: '1px solid #f0f0f0' }

  /* We have 5 main columns in the outer table, but Top 10 needs more.
     Use a nested table for clean column control. */
  const totalCols = 5 + columns.length
  return (
    <>
      <tr style={{ background: bg }}>
        <td colSpan={5} style={{
          color: C.hdrText, fontWeight: 800, fontSize: 13,
          padding: '8px 14px', letterSpacing: '.02em',
        }}>
          {title}
        </td>
      </tr>
      <tr>
        <td colSpan={5} style={{ padding: 0 }}>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 650 }}>
              <thead>
                <tr style={{ background: '#f5f5f0' }}>
                  <th style={{ ...subHdrS, textAlign: 'center', width: 40 }}>Rank</th>
                  <th style={{ ...subHdrS, textAlign: 'left' }}>Item Code</th>
                  <th style={{ ...subHdrS, textAlign: 'left' }}>Item Group</th>
                  <th style={{ ...subHdrS, textAlign: 'center', width: 55 }}>Type</th>
                  {columns.map(c => (
                    <th key={c.key} style={{ ...subHdrS, textAlign: 'right' }}>{c.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {items.map((item, i) => (
                  <tr key={i} style={i % 2 === 1 ? { background: '#fafbfc' } : undefined}>
                    <td style={{ ...labelS, textAlign: 'center', fontWeight: 700, color: '#999' }}>{i + 1}</td>
                    <td style={monoS}>{item.item_code}</td>
                    <td style={labelS}>{item.item_group || '—'}</td>
                    <td style={{ ...labelS, textAlign: 'center' }}>
                      <TypeBadge type={item.type} />
                    </td>
                    {columns.map(c => (
                      <td key={c.key} style={{
                        ...numS,
                        color: c.color || undefined,
                        fontWeight: c.color ? 800 : 600,
                      }}>
                        {fmtD(item[c.key])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </td>
      </tr>
    </>
  )
}


/* ═══ EXCEPTIONS — Qty & ₹ VALUE section ═══ */
function ExceptionsValueSection({ ev }) {
  if (!ev) return null

  const buckets = [
    { key: 'uncovered_shortfall', label: 'Uncovered Shortfall', desc: 'Total customer revenue at risk', highlight: true },
    { key: 'production_driven', label: 'Production-Driven Shortfall', desc: 'Need exceeds opening + production' },
    { key: 'dispatch_gap', label: 'Dispatch Gap', desc: 'Could ship from stock but didn\'t' },
    { key: 'shortfall_addl_demand', label: 'Shortfall on Addl Demand', desc: 'Additional demand uncovered' },
    { key: 'production_surplus', label: 'Production Surplus', desc: 'Produced more than committed need', surplus: true },
    { key: 'excess_opening', label: 'Excess Opening Stock', desc: 'Opening beyond committed + safety', surplus: true },
  ]

  const hdrS = {
    color: C.hdrText, fontWeight: 700, fontSize: 11,
    padding: '6px 8px', textAlign: 'right', borderBottom: '2px solid #333',
  }
  const numS = { ...R, padding: '5px 8px', fontWeight: 600, fontSize: 12, borderBottom: '1px solid #f0f0f0' }
  const valS = { ...numS, fontSize: 11, color: C.muted }

  return (
    <>
      <tr style={{ background: '#2c2c2c' }}>
        <td colSpan={5} style={{
          color: C.hdrText, fontWeight: 800, fontSize: 13,
          padding: '8px 14px', letterSpacing: '.02em',
        }}>
          EXCEPTIONS — Qty &amp; ₹ VALUE (combined, with MTS / MTO / TBC bifurcation)
        </td>
      </tr>
      <tr>
        <td colSpan={5} style={{ padding: 0 }}>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 800 }}>
              <thead>
                <tr style={{ background: '#f5f5f0' }}>
                  <th style={{ ...hdrS, textAlign: 'left', color: '#333' }}>Bucket</th>
                  <th style={{ ...hdrS, color: '#333' }}>Qty</th>
                  <th style={{ ...hdrS, color: '#333' }}>₹ Value</th>
                  <th style={{ ...hdrS, color: '#1565c0', borderLeft: '2px solid #e0e0e0' }}>MTS Qty</th>
                  <th style={{ ...hdrS, color: '#1565c0' }}>MTS ₹</th>
                  <th style={{ ...hdrS, color: '#e65100', borderLeft: '2px solid #e0e0e0' }}>MTO Qty</th>
                  <th style={{ ...hdrS, color: '#e65100' }}>MTO ₹</th>
                  <th style={{ ...hdrS, color: '#757575', borderLeft: '2px solid #e0e0e0' }}>TBC Qty</th>
                  <th style={{ ...hdrS, color: '#757575' }}>TBC ₹</th>
                </tr>
              </thead>
              <tbody>
                {buckets.map((b, i) => {
                  const d = ev[b.key]
                  if (!d) return null
                  const rowBg = b.highlight ? '#fff3e0' : b.surplus ? '#f0faf0' : undefined
                  const rowWeight = b.highlight ? 700 : 400
                  return (
                    <tr key={i} style={{ background: rowBg }}>
                      <td style={{
                        padding: '6px 14px', fontSize: 12, fontWeight: 600,
                        borderBottom: '1px solid #f0f0f0', minWidth: 180,
                      }}>
                        <div>{b.highlight ? '▼ ' : ''}{b.label}</div>
                        <div style={{ fontSize: 10, color: '#888', fontWeight: 400 }}>{b.desc}</div>
                      </td>
                      <td style={{ ...numS, fontWeight: 700 }}>{fmtD(d.total?.qty)}</td>
                      <td style={valS}>{fmtV(d.total?.value)}</td>
                      <td style={{ ...numS, borderLeft: '2px solid #e0e0e0' }}>{fmtD(d.MTS?.qty)}</td>
                      <td style={valS}>{fmtV(d.MTS?.value)}</td>
                      <td style={{ ...numS, borderLeft: '2px solid #e0e0e0' }}>{fmtD(d.MTO?.qty)}</td>
                      <td style={valS}>{fmtV(d.MTO?.value)}</td>
                      <td style={{ ...numS, borderLeft: '2px solid #e0e0e0' }}>{fmtD(d.TBC?.qty)}</td>
                      <td style={valS}>{fmtV(d.TBC?.value)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <div style={{ fontSize: 11, color: '#888', padding: '8px 14px', lineHeight: 1.5 }}>
            Qty = SUM of Append1 exception columns; ₹ Value = rate-weighted.
            MTS/MTO/TBC split via type column. Uncovered = Prod Shortfall + Dispatch Gap + Shortfall Addl Demand per item.
          </div>
        </td>
      </tr>
    </>
  )
}


/* ═══ FINANCIAL IMPACT section ═══ */
function FinancialSection({ fi, totalItems }) {
  if (!fi) return null
  const ratedPct = totalItems > 0 ? Math.round(fi.items_with_rate / totalItems * 100) : 0

  const rows = [
    { label: 'Opening Value', value: fi.opening_value },
    { label: 'Production Value', value: fi.production_value },
    { label: 'Dispatch Value', value: fi.dispatch_value },
    { label: 'Closing Value', value: fi.closing_value },
    { label: 'Surplus Value', value: fi.surplus_value },
    { label: 'Shortfall Value', value: fi.shortfall_value },
    { label: 'Excess Opening Value', value: fi.excess_opening_value },
  ]

  const labelS = { fontWeight: 500, padding: '5px 14px', fontSize: 13, color: '#333', borderBottom: '1px solid #f0f0f0' }
  const numS = { ...R, padding: '5px 14px', fontWeight: 700, fontSize: 13, borderBottom: '1px solid #f0f0f0' }

  return (
    <>
      <tr style={{ background: C.navy }}>
        <td colSpan={5} style={{
          color: C.hdrText, fontWeight: 800, fontSize: 13,
          padding: '8px 14px', letterSpacing: '.02em',
        }}>
          FINANCIAL IMPACT (Rate-Weighted)
        </td>
      </tr>
      {ratedPct < 100 && (
        <tr>
          <td colSpan={5} style={{
            padding: '6px 14px', fontSize: 12,
            background: '#fff8e1', color: '#f57f17',
          }}>
            ⚠️ Rate data for {fi.items_with_rate} of {totalItems} items ({ratedPct}%). Values partial.
          </td>
        </tr>
      )}
      {rows.map((r, i) => (
        <tr key={i}>
          <td style={labelS} colSpan={2}>{r.label}</td>
          <td style={numS} colSpan={3}>{fmtCr(r.value)}</td>
        </tr>
      ))}
    </>
  )
}


/* ═══ Shared mini components ═══ */
function TypeBadge({ type }) {
  const t = String(type || 'TBC').toUpperCase()
  const style = {
    padding: '2px 8px', borderRadius: 10, fontSize: 11, fontWeight: 700,
    background: t === 'MTS' ? '#e3f2fd' : t === 'MTO' ? '#f3e5f5' : '#f5f5f5',
    color: t === 'MTS' ? '#1565c0' : t === 'MTO' ? '#6a1b9a' : '#888',
  }
  return <span style={style}>{t || '—'}</span>
}
