import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import TopBar from '../components/TopBar'

/**
 * Screen 3 — Demand Upload (L2)
 *
 * Rule 3: initial demand is frozen. Changes are dated transactions.
 *
 * Two upload modes:
 *   1. Freeze — upload initial demand for a month (locked once confirmed)
 *   2. Transaction — upload additions / reductions
 */
export default function PPCDataDemand() {
  const navigate = useNavigate()
  const fileRef = useRef(null)

  // Mode
  const [mode, setMode] = useState('freeze') // 'freeze' | 'transaction'

  // Form state
  const [month, setMonth] = useState(() => {
    const d = new Date()
    d.setMonth(d.getMonth() + 1)
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
  })
  const [notes, setNotes] = useState('')

  // Upload state
  const [uploading, setUploading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')

  // Months with frozen demand
  const [months, setMonths] = useState([])
  const [loadingMonths, setLoadingMonths] = useState(true)

  // Demand current view
  const [viewMonth, setViewMonth] = useState('')
  const [demandRows, setDemandRows] = useState(null)
  const [demandSearch, setDemandSearch] = useState('')
  const [loadingDemand, setLoadingDemand] = useState(false)

  useEffect(() => {
    api.ppcDemandMonths().then(d => {
      setMonths(d.months || [])
      if (d.months?.length) setViewMonth(d.months[0].month)
    }).catch(() => {}).finally(() => setLoadingMonths(false))
  }, [result])

  async function handleUpload(e) {
    e.preventDefault()
    const file = fileRef.current?.files[0]
    if (!file) { setError('Select a file first.'); return }
    if (!month) { setError('Select a month.'); return }

    setUploading(true)
    setError('')
    setResult(null)
    try {
      const res = mode === 'freeze'
        ? await api.ppcDemandFreeze(file, month, notes)
        : await api.ppcDemandTransaction(file, month, notes)
      setResult(res)
      if (fileRef.current) fileRef.current.value = ''
      setNotes('')
    } catch (err) {
      setError(err.message)
    } finally {
      setUploading(false)
    }
  }

  async function fetchDemand() {
    if (!viewMonth) return
    setLoadingDemand(true)
    try {
      const d = await api.ppcDemandCurrent(viewMonth, 500, demandSearch)
      setDemandRows(d)
    } catch (err) {
      setDemandRows(null)
    } finally {
      setLoadingDemand(false)
    }
  }

  useEffect(() => { if (viewMonth) fetchDemand() }, [viewMonth])

  function handleDemandSearch(e) {
    e.preventDefault()
    fetchDemand()
  }

  return (
    <section className="screen">
      <TopBar subtitle="PPC Department" />
      <div className="wrap">
        <div className="crumbs">
          <Link to="/departments">Home</Link> ›{' '}
          <Link to="/ppc-data">PPC Data</Link> › Demand Upload
        </div>
        <button className="backbtn" onClick={() => navigate('/ppc-data')}>← Back to PPC Data</button>

        {/* Rule 3 callout */}
        <div style={{
          background: 'linear-gradient(135deg, #e6eff8 0%, #d4e8ff 100%)',
          borderRadius: 8,
          padding: '14px 18px',
          marginBottom: 18,
          borderLeft: '4px solid var(--accent)',
          fontSize: 13,
          lineHeight: 1.6,
        }}>
          <strong style={{ color: 'var(--accent)' }}>Rule 3 — Freeze the Demand</strong><br />
          Initial demand is written once and locked. Changes are dated additions/reductions.
          The frozen number is what adherence is measured against.
        </div>

        {/* Mode selector */}
        <div className="panel">
          <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
            <button
              onClick={() => { setMode('freeze'); setResult(null); setError('') }}
              style={{
                padding: '8px 18px', borderRadius: 6, fontSize: 13, fontWeight: 600,
                border: mode === 'freeze' ? '2px solid var(--accent)' : '1px solid var(--line)',
                background: mode === 'freeze' ? '#e8f4fd' : '#fff',
                color: mode === 'freeze' ? 'var(--accent)' : 'var(--ink)',
                cursor: 'pointer',
              }}>
              🔒 Freeze Initial Demand
            </button>
            <button
              onClick={() => { setMode('transaction'); setResult(null); setError('') }}
              style={{
                padding: '8px 18px', borderRadius: 6, fontSize: 13, fontWeight: 600,
                border: mode === 'transaction' ? '2px solid #b05520' : '1px solid var(--line)',
                background: mode === 'transaction' ? '#faf0e6' : '#fff',
                color: mode === 'transaction' ? '#b05520' : 'var(--ink)',
                cursor: 'pointer',
              }}>
              ± Add/Reduce Demand
            </button>
          </div>

          <form onSubmit={handleUpload}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
              <label style={{ fontSize: 12, fontWeight: 600 }}>
                Month (YYYY-MM)
                <input
                  type="month"
                  value={month}
                  onChange={e => setMonth(e.target.value)}
                  style={{ display: 'block', width: '100%', padding: '6px 10px', border: '1px solid var(--line)', borderRadius: 6, marginTop: 4, fontSize: 13 }}
                />
              </label>
              <label style={{ fontSize: 12, fontWeight: 600 }}>
                Notes (optional)
                <input
                  type="text"
                  value={notes}
                  onChange={e => setNotes(e.target.value)}
                  placeholder={mode === 'freeze' ? 'e.g. Sep forecast final' : 'e.g. W2 addition from SO'}
                  style={{ display: 'block', width: '100%', padding: '6px 10px', border: '1px solid var(--line)', borderRadius: 6, marginTop: 4, fontSize: 13 }}
                />
              </label>
            </div>

            <div style={{ display: 'flex', alignItems: 'end', gap: 12 }}>
              <label style={{ flex: 1, fontSize: 12, fontWeight: 600 }}>
                {mode === 'freeze' ? 'Forecast file (Initial Demand sheet)' : 'Forecast file (Addition/Reduction sheets)'}
                <input
                  ref={fileRef}
                  type="file"
                  accept=".xlsx,.xlsm,.xls"
                  style={{ display: 'block', marginTop: 4, fontSize: 13 }}
                />
              </label>
              <button
                type="submit"
                className="btn-upload"
                disabled={uploading}
                style={{ padding: '8px 20px', fontSize: 13, whiteSpace: 'nowrap' }}
              >
                {uploading ? 'Uploading…' : mode === 'freeze' ? '🔒 Freeze Demand' : '± Upload Changes'}
              </button>
            </div>
          </form>

          {error && <div className="upload-status error" style={{ marginTop: 12 }}>{error}</div>}

          {result && (
            <div className="upload-status ok" style={{ marginTop: 12 }}>
              {mode === 'freeze' ? (
                <>
                  ✅ <strong>{result.frozen}</strong> items frozen for {result.month}.
                  {result.skipped_already_frozen > 0 && (
                    <> <span className="muted">{result.skipped_already_frozen} already frozen (skipped).</span></>
                  )}
                  <span className="muted"> ({result.total_rows} rows parsed)</span>
                </>
              ) : (
                <>
                  ✅ <strong>{result.transactions_created}</strong> transactions created for {result.month}.
                  {result.no_freeze_warnings > 0 && (
                    <> ⚠️ {result.no_freeze_warnings} items had no freeze (skipped).</>
                  )}
                </>
              )}
            </div>
          )}
        </div>

        {/* Frozen months summary */}
        <div className="panel">
          <h3 style={{ marginBottom: 12 }}>Frozen Demand Months</h3>
          {loadingMonths && <div className="loading">Loading…</div>}
          {!loadingMonths && months.length === 0 && (
            <p className="note">No demand frozen yet. Upload a forecast file above to freeze the first month.</p>
          )}
          {months.length > 0 && (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Month</th>
                    <th>Frozen items</th>
                    <th>Transactions</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {months.map(m => (
                    <tr key={m.month} style={viewMonth === m.month ? { background: '#e8f4fd' } : undefined}>
                      <td style={{ fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>{m.month}</td>
                      <td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{m.frozen_items.toLocaleString()}</td>
                      <td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{m.transaction_count}</td>
                      <td>
                        <button
                          onClick={() => { setViewMonth(m.month); setDemandSearch(''); setDemandRows(null) }}
                          style={{ fontSize: 11, padding: '3px 10px', borderRadius: 4, border: '1px solid var(--line)', background: viewMonth === m.month ? 'var(--accent)' : '#fff', color: viewMonth === m.month ? '#fff' : 'var(--ink)', cursor: 'pointer' }}
                        >View</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Effective demand for selected month */}
        {viewMonth && (
          <div className="panel">
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
              <h3 style={{ margin: 0 }}>
                Effective Demand — {viewMonth}
                {demandRows && (
                  <span style={{ fontWeight: 400, fontSize: 13, color: 'var(--muted)', marginLeft: 8 }}>
                    {demandRows.total_items.toLocaleString()} items
                    {demandRows.truncated && <> (showing first {demandRows.items.length})</>}
                  </span>
                )}
              </h3>
              <form onSubmit={handleDemandSearch} style={{ display: 'flex', gap: 6 }}>
                <input
                  type="text"
                  value={demandSearch}
                  onChange={e => setDemandSearch(e.target.value)}
                  placeholder="Search item…"
                  style={{ padding: '6px 10px', border: '1px solid var(--line)', borderRadius: 6, fontSize: 13, width: 180 }}
                />
                <button type="submit" className="btn-upload" style={{ padding: '6px 14px', fontSize: 13 }}>Search</button>
              </form>
            </div>

            {loadingDemand && <div className="loading">Loading…</div>}

            {!loadingDemand && demandRows && demandRows.items.length === 0 && (
              <p className="note">No items match.</p>
            )}

            {!loadingDemand && demandRows && demandRows.items.length > 0 && (
              <div className="table-scroll" style={{ maxHeight: '60vh', overflowY: 'auto' }}>
                <table style={{ fontSize: 12 }}>
                  <thead>
                    <tr>
                      <th style={{ position: 'sticky', top: 0, zIndex: 1, background: '#f0f4f8' }}>Item Code</th>
                      <th style={{ position: 'sticky', top: 0, zIndex: 1, background: '#f0f4f8', textAlign: 'right' }}>Initial</th>
                      <th style={{ position: 'sticky', top: 0, zIndex: 1, background: '#f0f4f8', textAlign: 'right', color: 'var(--ok)' }}>+ Additions</th>
                      <th style={{ position: 'sticky', top: 0, zIndex: 1, background: '#f0f4f8', textAlign: 'right', color: 'var(--bad)' }}>− Reductions</th>
                      <th style={{ position: 'sticky', top: 0, zIndex: 1, background: '#f0f4f8', textAlign: 'right', fontWeight: 700 }}>Effective</th>
                      <th style={{ position: 'sticky', top: 0, zIndex: 1, background: '#f0f4f8', textAlign: 'center' }}>Txns</th>
                      <th style={{ position: 'sticky', top: 0, zIndex: 1, background: '#f0f4f8' }}>Frozen</th>
                    </tr>
                  </thead>
                  <tbody>
                    {demandRows.items.map(item => {
                      const changed = item.additions > 0 || item.reductions > 0
                      return (
                        <tr key={item.item_code}>
                          <td style={{ fontFamily: 'monospace', fontSize: 12, fontWeight: 600 }}>{item.item_code}</td>
                          <td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{item.initial_qty.toLocaleString()}</td>
                          <td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums', color: item.additions > 0 ? 'var(--ok)' : 'var(--muted)' }}>
                            {item.additions > 0 ? `+${item.additions.toLocaleString()}` : '—'}
                          </td>
                          <td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums', color: item.reductions > 0 ? 'var(--bad)' : 'var(--muted)' }}>
                            {item.reductions > 0 ? `−${item.reductions.toLocaleString()}` : '—'}
                          </td>
                          <td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums', fontWeight: 700, background: changed ? '#fefce8' : undefined }}>
                            {item.effective_qty.toLocaleString()}
                          </td>
                          <td style={{ textAlign: 'center', fontVariantNumeric: 'tabular-nums', color: 'var(--muted)' }}>
                            {item.transaction_count || '—'}
                          </td>
                          <td className="muted" style={{ fontSize: 11 }}>
                            {item.frozen_at ? new Date(item.frozen_at).toLocaleDateString() : '—'}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  )
}
