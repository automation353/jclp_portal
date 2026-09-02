import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import TopBar from '../components/TopBar'

/**
 * Screen 5 — R3SS Plan Upload (L4)
 *
 * Rule 1: One Plan Table. R3SS is stored once.
 *
 * Features:
 *   - Upload R3 SS.xlsx (auto-parses both "All" and "Sheet1")
 *   - Summary tiles: parts, date cols, plan month, sections
 *   - Day-drill: pick a date → see what's planned
 *   - Compact table browser (fixed cols only, days hidden)
 */
export default function PPCDataR3SS() {
  const navigate = useNavigate()
  const fileRef = useRef(null)

  // Upload
  const [notes, setNotes] = useState('')
  const [uploading, setUploading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')

  // Summary
  const [summary, setSummary] = useState(null)
  const [loadingSummary, setLoadingSummary] = useState(true)

  // Plan data (compact)
  const [planData, setPlanData] = useState(null)
  const [planSearch, setPlanSearch] = useState('')
  const [loadingPlan, setLoadingPlan] = useState(false)

  // Day drill
  const [drillDate, setDrillDate] = useState('')
  const [drillSection, setDrillSection] = useState('')
  const [dayData, setDayData] = useState(null)
  const [loadingDay, setLoadingDay] = useState(false)

  function refreshSummary() {
    setLoadingSummary(true)
    api.ppcR3ssSummary()
      .then(d => {
        setSummary(d)
        // Default drill date to first day of plan month
        if (d.plan_month && !drillDate) {
          setDrillDate(`${d.plan_month}-01`)
        }
      })
      .catch(() => {})
      .finally(() => setLoadingSummary(false))
  }

  useEffect(() => { refreshSummary() }, [])

  async function handleUpload(e) {
    e.preventDefault()
    const file = fileRef.current?.files[0]
    if (!file) { setError('Select a file first.'); return }

    setUploading(true)
    setError('')
    setResult(null)
    try {
      const res = await api.ppcR3ssUpload(file, notes)
      setResult(res)
      if (fileRef.current) fileRef.current.value = ''
      setNotes('')
      refreshSummary()
      fetchPlan('')
    } catch (err) {
      setError(err.message)
    } finally {
      setUploading(false)
    }
  }

  async function fetchPlan(search) {
    setLoadingPlan(true)
    try {
      setPlanData(await api.ppcR3ssCurrent(500, search || '', 'compact'))
    } catch (err) {
      if (err.status === 404) setPlanData(null)
    } finally {
      setLoadingPlan(false)
    }
  }

  useEffect(() => { fetchPlan('') }, [])

  function handlePlanSearch(e) {
    e.preventDefault()
    fetchPlan(planSearch)
  }

  async function fetchDay() {
    if (!drillDate) return
    setLoadingDay(true)
    try {
      setDayData(await api.ppcR3ssDay(drillDate, drillSection))
    } catch {
      setDayData(null)
    } finally {
      setLoadingDay(false)
    }
  }

  // Key columns to show in compact view
  const COMPACT_KEYS = [
    'item_code', 'description', 'section', 'product_group', 'mto_mts',
    'green_level', 'opening_balance', 'fg_stock', 'to_plan',
    'total_plan', 'total_demand', 'difference',
    'w1', 'w2', 'w3', 'w4', 'w5',
  ]

  return (
    <section className="screen">
      <TopBar subtitle="PPC Department" />
      <div className="wrap" style={planData?.rows?.length ? { maxWidth: 'none', padding: '22px 26px' } : undefined}>
        <div className="crumbs">
          <Link to="/departments">Home</Link> ›{' '}
          <Link to="/ppc-data">PPC Data</Link> › R3SS Plan
        </div>
        <button className="backbtn" onClick={() => navigate('/ppc-data')}>← Back to PPC Data</button>

        {/* Rule 1 callout */}
        <div style={{
          background: 'linear-gradient(135deg, #faf0e6 0%, #fce8d6 100%)',
          borderRadius: 8,
          padding: '14px 18px',
          marginBottom: 18,
          borderLeft: '4px solid #b05520',
          fontSize: 13,
          lineHeight: 1.6,
        }}>
          <strong style={{ color: '#b05520' }}>Rule 1 — One Plan Table</strong><br />
          R3SS is stored once. Every screen reads from it. No copies. Day-wise columns
          are auto-detected from the header row.
        </div>

        {/* Summary tiles */}
        {summary?.loaded && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: 10, marginBottom: 18 }}>
            <div className="panel" style={{ textAlign: 'center', padding: 14, marginBottom: 0 }}>
              <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--accent)' }}>
                {summary.total_parts.toLocaleString()}
              </div>
              <div style={{ fontSize: 10, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.05em' }}>Parts</div>
            </div>
            <div className="panel" style={{ textAlign: 'center', padding: 14, marginBottom: 0 }}>
              <div style={{ fontSize: 24, fontWeight: 700, color: '#b05520' }}>
                {summary.plan_month || '—'}
              </div>
              <div style={{ fontSize: 10, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.05em' }}>Plan month</div>
            </div>
            <div className="panel" style={{ textAlign: 'center', padding: 14, marginBottom: 0 }}>
              <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--ok)' }}>
                {summary.date_columns}
              </div>
              <div style={{ fontSize: 10, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.05em' }}>Day columns</div>
            </div>
            <div className="panel" style={{ textAlign: 'center', padding: 14, marginBottom: 0 }}>
              <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--ink)' }}>
                {summary.total_plan.toLocaleString()}
              </div>
              <div style={{ fontSize: 10, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.05em' }}>Total plan qty</div>
            </div>
            <div className="panel" style={{ textAlign: 'center', padding: 14, marginBottom: 0 }}>
              <div style={{ fontSize: 24, fontWeight: 700, color: summary.day_sum_mismatches > 0 ? 'var(--bad)' : 'var(--muted)' }}>
                {summary.day_sum_mismatches}
              </div>
              <div style={{ fontSize: 10, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.05em' }}>Mismatches</div>
            </div>
          </div>
        )}

        {/* Section breakdown */}
        {summary?.sections?.length > 0 && (
          <div className="panel" style={{ marginBottom: 18 }}>
            <h3 style={{ marginBottom: 8, fontSize: 14 }}>Plan by Section</h3>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {summary.sections.map(s => (
                <div key={s.section} style={{
                  padding: '6px 12px', borderRadius: 6,
                  border: '1px solid var(--line)', background: '#fafafa',
                  fontSize: 12, minWidth: 100,
                }}>
                  <div style={{ fontWeight: 700 }}>{s.section}</div>
                  <div style={{ color: 'var(--muted)' }}>
                    {s.items} items · {s.total_plan.toLocaleString()} qty
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Upload panel */}
        <div className="panel">
          <h3 style={{ marginBottom: 12 }}>Upload R3 SS.xlsx</h3>
          <p className="note" style={{ marginBottom: 12 }}>
            Upload the R3SS file. The parser auto-detects fixed columns and day-wise date columns
            from the "All" sheet, plus the summary from "Sheet1".
          </p>
          <form onSubmit={handleUpload}>
            <div style={{ display: 'flex', alignItems: 'end', gap: 12 }}>
              <label style={{ flex: 1, fontSize: 12, fontWeight: 600 }}>
                R3 SS.xlsx
                <input
                  ref={fileRef}
                  type="file"
                  accept=".xlsx,.xlsm,.xls"
                  style={{ display: 'block', marginTop: 4, fontSize: 13 }}
                />
              </label>
              <input
                type="text"
                value={notes}
                onChange={e => setNotes(e.target.value)}
                placeholder="Notes (optional)"
                style={{ padding: '6px 10px', border: '1px solid var(--line)', borderRadius: 6, fontSize: 13, width: 200 }}
              />
              <button
                type="submit"
                className="btn-upload"
                disabled={uploading}
                style={{ padding: '8px 18px', fontSize: 13, whiteSpace: 'nowrap' }}
              >
                {uploading ? 'Uploading…' : '⬆ Upload R3SS'}
              </button>
            </div>
          </form>

          {error && <div className="upload-status error" style={{ marginTop: 12 }}>{error}</div>}
          {result && (
            <div className="upload-status ok" style={{ marginTop: 12 }}>
              ✅ <strong>{result.plan_rows}</strong> plan rows parsed.
              {' '}{result.date_columns} date columns detected.
              {result.plan_month && <> Plan month: <strong>{result.plan_month}</strong>.</>}
              {result.day_sum_mismatches > 0 && (
                <> ⚠️ {result.day_sum_mismatches} day-sum mismatches.</>
              )}
              {result.summary_rows > 0 && (
                <> Summary: {result.summary_rows} rows.</>
              )}
            </div>
          )}
        </div>

        {/* Day drill */}
        <div className="panel">
          <h3 style={{ marginBottom: 10 }}>Day Drill — What's planned on a date?</h3>
          <div style={{ display: 'flex', gap: 8, alignItems: 'end', marginBottom: 12, flexWrap: 'wrap' }}>
            <label style={{ fontSize: 12, fontWeight: 600 }}>
              Date
              <input
                type="date"
                value={drillDate}
                onChange={e => setDrillDate(e.target.value)}
                style={{ display: 'block', padding: '6px 10px', border: '1px solid var(--line)', borderRadius: 6, marginTop: 4, fontSize: 13 }}
              />
            </label>
            <label style={{ fontSize: 12, fontWeight: 600 }}>
              Section (optional)
              <input
                type="text"
                value={drillSection}
                onChange={e => setDrillSection(e.target.value)}
                placeholder="e.g. SSWD"
                style={{ display: 'block', padding: '6px 10px', border: '1px solid var(--line)', borderRadius: 6, marginTop: 4, fontSize: 13, width: 120 }}
              />
            </label>
            <button
              onClick={fetchDay}
              className="btn-upload"
              disabled={!drillDate || loadingDay}
              style={{ padding: '8px 16px', fontSize: 13 }}
            >
              {loadingDay ? 'Loading…' : '🔍 Drill'}
            </button>
          </div>

          {dayData && (
            <>
              <p style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 8 }}>
                {dayData.count} items planned on {dayData.date}
                {dayData.section_filter && <> in section "{dayData.section_filter}"</>}
              </p>
              {dayData.items.length > 0 && (
                <div className="table-scroll" style={{ maxHeight: '40vh', overflowY: 'auto' }}>
                  <table style={{ fontSize: 12 }}>
                    <thead>
                      <tr>
                        <th style={{ position: 'sticky', top: 0, zIndex: 1, background: '#f0f4f8' }}>Item Code</th>
                        <th style={{ position: 'sticky', top: 0, zIndex: 1, background: '#f0f4f8' }}>Description</th>
                        <th style={{ position: 'sticky', top: 0, zIndex: 1, background: '#f0f4f8' }}>Section</th>
                        <th style={{ position: 'sticky', top: 0, zIndex: 1, background: '#f0f4f8' }}>Group</th>
                        <th style={{ position: 'sticky', top: 0, zIndex: 1, background: '#f0f4f8' }}>MTO/MTS</th>
                        <th style={{ position: 'sticky', top: 0, zIndex: 1, background: '#f0f4f8', textAlign: 'right', fontWeight: 700 }}>Day Qty</th>
                        <th style={{ position: 'sticky', top: 0, zIndex: 1, background: '#f0f4f8', textAlign: 'right' }}>Total Plan</th>
                      </tr>
                    </thead>
                    <tbody>
                      {dayData.items.map((item, i) => (
                        <tr key={i}>
                          <td style={{ fontFamily: 'monospace', fontSize: 12, fontWeight: 600 }}>{item.item_code}</td>
                          <td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.description || '—'}</td>
                          <td>{item.section || '—'}</td>
                          <td>{item.product_group || '—'}</td>
                          <td>{item.mto_mts || '—'}</td>
                          <td style={{ textAlign: 'right', fontWeight: 700, fontVariantNumeric: 'tabular-nums', color: 'var(--accent)' }}>
                            {typeof item.plan_qty === 'number' ? item.plan_qty.toLocaleString() : item.plan_qty}
                          </td>
                          <td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums', color: 'var(--muted)' }}>
                            {item.total_plan != null ? Number(item.total_plan).toLocaleString() : '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </div>

        {/* Compact plan browser */}
        <div className="panel">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
            <h3 style={{ margin: 0 }}>
              R3SS Plan (compact)
              {planData && (
                <span style={{ fontWeight: 400, fontSize: 13, color: 'var(--muted)', marginLeft: 8 }}>
                  {planData.row_count.toLocaleString()} parts
                  {planData.plan_month && <> · {planData.plan_month}</>}
                  {planData.uploader && <> · by {planData.uploader}</>}
                </span>
              )}
            </h3>
            <form onSubmit={handlePlanSearch} style={{ display: 'flex', gap: 6 }}>
              <input
                type="text"
                value={planSearch}
                onChange={e => setPlanSearch(e.target.value)}
                placeholder="Search item…"
                style={{ padding: '6px 10px', border: '1px solid var(--line)', borderRadius: 6, fontSize: 13, width: 180 }}
              />
              <button type="submit" className="btn-upload" style={{ padding: '6px 14px', fontSize: 13 }}>Search</button>
              {planSearch && (
                <button
                  type="button"
                  onClick={() => { setPlanSearch(''); fetchPlan('') }}
                  style={{ padding: '6px 10px', border: '1px solid var(--line)', borderRadius: 6, background: '#fff', cursor: 'pointer', fontSize: 12 }}
                >Clear</button>
              )}
            </form>
          </div>

          {loadingPlan && <div className="loading">Loading…</div>}

          {!loadingPlan && !planData && (
            <p className="note">No R3SS plan loaded yet. Upload R3 SS.xlsx above.</p>
          )}

          {!loadingPlan && planData && planData.rows.length === 0 && (
            <p className="note">No items match the search.</p>
          )}

          {!loadingPlan && planData && planData.rows.length > 0 && (
            <div className="table-scroll" style={{ maxHeight: '60vh', overflowY: 'auto' }}>
              <table style={{ fontSize: 12 }}>
                <thead>
                  <tr>
                    <th style={{ position: 'sticky', top: 0, zIndex: 1, background: '#f0f4f8' }}>#</th>
                    {COMPACT_KEYS.map(k => (
                      <th key={k} style={{ position: 'sticky', top: 0, zIndex: 1, background: '#f0f4f8', whiteSpace: 'nowrap' }}>{k}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {planData.rows.map(row => (
                    <tr key={row.sr_no}>
                      <td className="muted">{row.sr_no}</td>
                      {COMPACT_KEYS.map(k => (
                        <td key={k} style={{ whiteSpace: 'nowrap', maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          {row.data[k] != null ? String(row.data[k]) : <span className="muted">—</span>}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {planData && (
            <p className="note" style={{ marginTop: 8, fontSize: 11 }}>
              Compact view hides day columns. Use the{' '}
              <Link to="/ppc-data/browse?table=r3ss_plan">Data Browser</Link>{' '}
              to see all columns including daily quantities.
            </p>
          )}
        </div>
      </div>
    </section>
  )
}
