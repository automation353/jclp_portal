import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import TopBar from '../components/TopBar'

/**
 * Screen 4 — MPS Upload (L3)
 *
 * Upload MPS Schedule Form (MpsSS.xlsm), planning calendar,
 * and history data. Browse the current schedule with search.
 */

const MPS_TABLES = [
  { key: 'mps_schedule', label: 'MPS Schedule Form', icon: '📋', desc: 'THE master production schedule — ~1,500 items × 50 columns, week buckets W1-W5.' },
  { key: 'mps_history', label: 'MPS History', icon: '📊', desc: 'Demand Data + Dispatch Data from MpsSS — monthly history for trend analysis.' },
  { key: 'planning_calendar', label: 'Planning Calendar', icon: '📅', desc: 'Week start dates (W1-W5 Mondays) per month. Drives the schedule grid.' },
  { key: 'demand_history', label: 'Demand History', icon: '📈', desc: 'Dispatch Trends — monthly demand/packing/dispatch from 2021 onwards.' },
]

export default function PPCDataMPS() {
  const navigate = useNavigate()
  const fileRef = useRef(null)

  // Upload form
  const [selectedTable, setSelectedTable] = useState('mps_schedule')
  const [notes, setNotes] = useState('')
  const [uploading, setUploading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')

  // MPS summary
  const [summary, setSummary] = useState(null)

  // MPS data browse
  const [mpsData, setMpsData] = useState(null)
  const [mpsSearch, setMpsSearch] = useState('')
  const [loadingMps, setLoadingMps] = useState(false)

  useEffect(() => {
    api.ppcMpsSummary().then(setSummary).catch(() => {})
  }, [result])

  async function handleUpload(e) {
    e.preventDefault()
    const file = fileRef.current?.files[0]
    if (!file) { setError('Select a file first.'); return }

    setUploading(true)
    setError('')
    setResult(null)
    try {
      const res = await api.ppcMpsUpload(file, selectedTable, notes)
      setResult(res)
      if (fileRef.current) fileRef.current.value = ''
      setNotes('')
      // Refresh MPS data if we uploaded the schedule
      if (selectedTable === 'mps_schedule') fetchMps()
    } catch (err) {
      setError(err.message)
    } finally {
      setUploading(false)
    }
  }

  async function fetchMps(search) {
    setLoadingMps(true)
    try {
      setMpsData(await api.ppcMpsCurrent(500, search || ''))
    } catch (err) {
      if (err.status === 404) setMpsData(null)
    } finally {
      setLoadingMps(false)
    }
  }

  useEffect(() => { fetchMps() }, [])

  function handleMpsSearch(e) {
    e.preventDefault()
    fetchMps(mpsSearch)
  }

  const tableMeta = MPS_TABLES.find(t => t.key === selectedTable)

  // Collect columns from MPS data
  const mpsColumns = []
  if (mpsData?.rows?.length) {
    const keySet = new Set()
    mpsData.rows.forEach(r => Object.keys(r.data).forEach(k => keySet.add(k)))
    mpsColumns.push(...Array.from(keySet).sort())
  }

  return (
    <section className="screen">
      <TopBar subtitle="PPC Department" />
      <div className="wrap" style={mpsData?.rows?.length ? { maxWidth: 'none', padding: '22px 26px' } : undefined}>
        <div className="crumbs">
          <Link to="/departments">Home</Link> ›{' '}
          <Link to="/ppc-data">PPC Data</Link> › MPS Upload
        </div>
        <button className="backbtn" onClick={() => navigate('/ppc-data')}>← Back to PPC Data</button>

        {/* Summary tiles */}
        {summary && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 10, marginBottom: 18 }}>
            <div className="panel" style={{ textAlign: 'center', padding: 14, marginBottom: 0 }}>
              <div style={{ fontSize: 26, fontWeight: 700, color: summary.loaded ? 'var(--accent)' : 'var(--muted)' }}>
                {summary.total_items.toLocaleString()}
              </div>
              <div style={{ fontSize: 10, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.05em' }}>MPS Items</div>
            </div>
            <div className="panel" style={{ textAlign: 'center', padding: 14, marginBottom: 0 }}>
              <div style={{ fontSize: 26, fontWeight: 700, color: '#b05520' }}>
                {summary.mto_items.toLocaleString()}
              </div>
              <div style={{ fontSize: 10, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.05em' }}>MTO items</div>
            </div>
            <div className="panel" style={{ textAlign: 'center', padding: 14, marginBottom: 0 }}>
              <div style={{ fontSize: 26, fontWeight: 700, color: 'var(--ok)' }}>
                {summary.mts_items.toLocaleString()}
              </div>
              <div style={{ fontSize: 10, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.05em' }}>MTS items</div>
            </div>
            <div className="panel" style={{ textAlign: 'center', padding: 14, marginBottom: 0 }}>
              <div style={{ fontSize: 26, fontWeight: 700, color: 'var(--ink)' }}>
                {summary.total_plan_qty.toLocaleString()}
              </div>
              <div style={{ fontSize: 10, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.05em' }}>Total plan qty</div>
            </div>
          </div>
        )}

        {/* Upload panel */}
        <div className="panel">
          <h3 style={{ marginBottom: 12 }}>Upload MPS Data</h3>

          {/* Table selector */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 14 }}>
            {MPS_TABLES.map(t => (
              <button
                key={t.key}
                onClick={() => { setSelectedTable(t.key); setResult(null); setError('') }}
                style={{
                  padding: '7px 14px', borderRadius: 6, fontSize: 13,
                  border: selectedTable === t.key ? '2px solid var(--accent)' : '1px solid var(--line)',
                  background: selectedTable === t.key ? '#e8f4fd' : '#fff',
                  color: selectedTable === t.key ? 'var(--accent)' : 'var(--ink)',
                  fontWeight: selectedTable === t.key ? 700 : 400,
                  cursor: 'pointer',
                }}
              >
                {t.icon} {t.label}
              </button>
            ))}
          </div>

          {tableMeta && (
            <p className="note" style={{ marginBottom: 12 }}>{tableMeta.desc}</p>
          )}

          <form onSubmit={handleUpload}>
            <div style={{ display: 'flex', alignItems: 'end', gap: 12 }}>
              <label style={{ flex: 1, fontSize: 12, fontWeight: 600 }}>
                File (.xlsx / .xlsm)
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
                {uploading ? 'Uploading…' : '⬆ Upload'}
              </button>
            </div>
          </form>

          {error && <div className="upload-status error" style={{ marginTop: 12 }}>{error}</div>}
          {result && (
            <div className="upload-status ok" style={{ marginTop: 12 }}>
              ✅ <strong>{result.row_count}</strong> rows parsed for <code>{result.table_key}</code>.
              {result.sample_row && (
                <details style={{ marginTop: 6, fontSize: 12 }}>
                  <summary style={{ cursor: 'pointer', color: 'var(--accent)' }}>Sample row</summary>
                  <pre style={{ background: 'var(--sand)', padding: 8, borderRadius: 4, overflowX: 'auto', marginTop: 4 }}>
                    {JSON.stringify(result.sample_row, null, 2)}
                  </pre>
                </details>
              )}
            </div>
          )}
        </div>

        {/* MPS Schedule data */}
        <div className="panel">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
            <h3 style={{ margin: 0 }}>
              MPS Schedule
              {mpsData && (
                <span style={{ fontWeight: 400, fontSize: 13, color: 'var(--muted)', marginLeft: 8 }}>
                  {mpsData.row_count.toLocaleString()} items
                  {mpsData.uploader && <> · by {mpsData.uploader}</>}
                  {mpsData.uploaded_at && <> · {new Date(mpsData.uploaded_at).toLocaleDateString()}</>}
                </span>
              )}
            </h3>
            <form onSubmit={handleMpsSearch} style={{ display: 'flex', gap: 6 }}>
              <input
                type="text"
                value={mpsSearch}
                onChange={e => setMpsSearch(e.target.value)}
                placeholder="Search item…"
                style={{ padding: '6px 10px', border: '1px solid var(--line)', borderRadius: 6, fontSize: 13, width: 180 }}
              />
              <button type="submit" className="btn-upload" style={{ padding: '6px 14px', fontSize: 13 }}>Search</button>
              {mpsSearch && (
                <button
                  type="button"
                  onClick={() => { setMpsSearch(''); fetchMps('') }}
                  style={{ padding: '6px 10px', border: '1px solid var(--line)', borderRadius: 6, background: '#fff', cursor: 'pointer', fontSize: 12 }}
                >Clear</button>
              )}
            </form>
          </div>

          {loadingMps && <div className="loading">Loading…</div>}

          {!loadingMps && !mpsData && (
            <p className="note">No MPS schedule loaded yet. Upload MpsSS.xlsm above.</p>
          )}

          {!loadingMps && mpsData && mpsData.rows.length === 0 && (
            <p className="note">No items match the search.</p>
          )}

          {!loadingMps && mpsData && mpsData.rows.length > 0 && (
            <div className="table-scroll" style={{ maxHeight: '65vh', overflowY: 'auto' }}>
              <table style={{ fontSize: 12 }}>
                <thead>
                  <tr>
                    <th style={{ position: 'sticky', top: 0, zIndex: 1, background: '#f0f4f8' }}>#</th>
                    {mpsColumns.map(k => (
                      <th key={k} style={{ position: 'sticky', top: 0, zIndex: 1, background: '#f0f4f8', whiteSpace: 'nowrap' }}>{k}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {mpsData.rows.map(row => (
                    <tr key={row.sr_no}>
                      <td className="muted">{row.sr_no}</td>
                      {mpsColumns.map(k => (
                        <td key={k} style={{ whiteSpace: 'nowrap', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          {row.data[k] != null ? String(row.data[k]) : <span className="muted">—</span>}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </section>
  )
}
