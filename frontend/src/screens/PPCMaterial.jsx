import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import TopBar from '../components/TopBar'

/**
 * Screen 6c — L7 Material — BOM Explosion & Stock Allocation
 *
 * Features:
 *   - Run BOM explosion from active release
 *   - Run stock allocation
 *   - View shortage report (RM/CP/PM filter)
 */
export default function PPCMaterial() {
  const navigate = useNavigate()

  const [matStatus, setMatStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [running, setRunning] = useState('')

  // Shortages
  const [shortages, setShortages] = useState(null)
  const [typeFilter, setTypeFilter] = useState('')
  const [search, setSearch] = useState('')
  const [loadingShort, setLoadingShort] = useState(false)

  function refresh() {
    setLoading(true)
    api.ppcMaterialStatus()
      .then(d => setMatStatus(d))
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => { refresh() }, [])

  async function handleExplode() {
    if (!matStatus?.release_id) return
    setRunning('explode'); setError(''); setSuccess('')
    try {
      const res = await api.ppcMaterialExplode(matStatus.release_id)
      setSuccess(`BOM explosion complete: ${res.unique_components} components from ${res.fg_items_with_bom} FG items.`)
      refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setRunning('')
    }
  }

  async function handleAllocate() {
    if (!matStatus?.release_id) return
    setRunning('allocate'); setError(''); setSuccess('')
    try {
      const res = await api.ppcMaterialAllocate(matStatus.release_id)
      setSuccess(`Stock allocation complete: ${res.components_with_shortage} shortages out of ${res.total_components} components.`)
      refresh()
      fetchShortages()
    } catch (err) {
      setError(err.message)
    } finally {
      setRunning('')
    }
  }

  async function fetchShortages() {
    if (!matStatus?.release_id) return
    setLoadingShort(true)
    try {
      setShortages(await api.ppcMaterialShortages(matStatus.release_id, typeFilter, 500, search))
    } catch {
      setShortages(null)
    } finally {
      setLoadingShort(false)
    }
  }

  useEffect(() => {
    if (matStatus?.loaded && matStatus?.allocation) fetchShortages()
  }, [matStatus?.loaded, typeFilter])

  return (
    <section className="screen">
      <TopBar subtitle="PPC Department" />
      <div className="wrap" style={shortages?.rows?.length ? { maxWidth: 'none', padding: '22px 26px' } : undefined}>
        <div className="crumbs">
          <Link to="/departments">Home</Link> ›{' '}
          <Link to="/ppc-data">PPC Data</Link> › Material Planning
        </div>
        <button className="backbtn" onClick={() => navigate('/ppc-data')}>← Back to PPC Data</button>

        <div style={{
          background: 'linear-gradient(135deg, #eaf0fb 0%, #dde7f8 100%)',
          borderRadius: 8, padding: '14px 18px', marginBottom: 18,
          borderLeft: '4px solid #2471a3', fontSize: 13, lineHeight: 1.6,
        }}>
          <strong style={{ color: '#2471a3' }}>L7 Material — BOM Explosion</strong><br />
          Released plan × BOM master = day-wise RM/CP/PM requirement. Runs entirely in the
          database — exceeds Google Sheets' limits. Stock is allocated earliest dates first.
        </div>

        {error && <div className="upload-status error" style={{ marginBottom: 12 }}>{error}</div>}
        {success && <div className="upload-status ok" style={{ marginBottom: 12 }}>{success}</div>}

        {loading && <div className="loading">Loading…</div>}

        {!loading && !matStatus?.loaded && (
          <div className="panel">
            <p className="note">No active release found. Create a release from the Feasibility screen first.</p>
          </div>
        )}

        {!loading && matStatus?.loaded && (
          <>
            {/* Status tiles */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 10, marginBottom: 18 }}>
              <div className="panel" style={{ textAlign: 'center', padding: 14, marginBottom: 0 }}>
                <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--accent)' }}>
                  {matStatus.plan_month}
                </div>
                <div style={{ fontSize: 10, color: 'var(--muted)', textTransform: 'uppercase' }}>Plan month</div>
              </div>
              <div className="panel" style={{ textAlign: 'center', padding: 14, marginBottom: 0 }}>
                <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--ink)' }}>
                  #{matStatus.release_number}
                </div>
                <div style={{ fontSize: 10, color: 'var(--muted)', textTransform: 'uppercase' }}>Release</div>
              </div>
              <div className="panel" style={{ textAlign: 'center', padding: 14, marginBottom: 0 }}>
                <div style={{ fontSize: 20, fontWeight: 700, color: matStatus.bom ? 'var(--ok)' : 'var(--muted)' }}>
                  {matStatus.bom ? matStatus.bom.row_count.toLocaleString() : '—'}
                </div>
                <div style={{ fontSize: 10, color: 'var(--muted)', textTransform: 'uppercase' }}>Components (BOM)</div>
              </div>
              <div className="panel" style={{ textAlign: 'center', padding: 14, marginBottom: 0 }}>
                <div style={{ fontSize: 20, fontWeight: 700, color: matStatus.allocation ? (shortages?.shortages_count > 0 ? 'var(--bad)' : 'var(--ok)') : 'var(--muted)' }}>
                  {shortages ? shortages.shortages_count : '—'}
                </div>
                <div style={{ fontSize: 10, color: 'var(--muted)', textTransform: 'uppercase' }}>Shortages</div>
              </div>
            </div>

            {/* Actions */}
            <div className="panel">
              <h3 style={{ marginBottom: 10 }}>Actions</h3>
              <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                <button onClick={handleExplode} className="btn-upload" disabled={running === 'explode'}
                  style={{ padding: '8px 18px', fontSize: 13 }}>
                  {running === 'explode' ? 'Running…' : '💥 Run BOM Explosion'}
                </button>
                <button onClick={handleAllocate} className="btn-upload" disabled={running === 'allocate' || !matStatus.bom}
                  style={{ padding: '8px 18px', fontSize: 13, background: matStatus.bom ? '#2471a3' : '#ccc', borderColor: matStatus.bom ? '#2471a3' : '#ccc' }}>
                  {running === 'allocate' ? 'Running…' : '📦 Run Stock Allocation'}
                </button>
                {matStatus.allocation && (
                  <button onClick={async () => {
                    setRunning('sync'); setError(''); setSuccess('')
                    try {
                      const res = await api.ppcMaterialSheetSync(matStatus.release_id)
                      const r = res.sync_results || {}
                      const ok = [r.ppc_planning_sheet, r.pipeline_sheet].filter(s => s?.ok).length
                      setSuccess(`Sheet sync: ${ok} of 2 webhooks succeeded.`)
                    } catch (err) { setError(err.message) }
                    finally { setRunning('') }
                  }} className="btn-upload" disabled={running === 'sync'}
                    style={{ padding: '8px 18px', fontSize: 13, background: '#27ae60', borderColor: '#27ae60' }}>
                    {running === 'sync' ? 'Syncing…' : '📋 Sync to Google Sheet'}
                  </button>
                )}
              </div>
              {!matStatus.bom && (
                <p className="note" style={{ marginTop: 8 }}>Run BOM explosion first, then stock allocation.</p>
              )}
            </div>

            {/* Shortage report */}
            {matStatus.allocation && (
              <div className="panel">
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
                  <h3 style={{ margin: 0 }}>
                    Material Status
                    {shortages && (
                      <span style={{ fontWeight: 400, fontSize: 13, color: 'var(--muted)', marginLeft: 8 }}>
                        {shortages.total_components} components · {shortages.shortages_count} shortages
                      </span>
                    )}
                  </h3>
                  <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                    {['', 'RM', 'CP', 'PM'].map(t => (
                      <button key={t} onClick={() => setTypeFilter(t)}
                        style={{
                          padding: '5px 12px', borderRadius: 6, fontSize: 12, cursor: 'pointer',
                          border: typeFilter === t ? '2px solid var(--accent)' : '1px solid var(--line)',
                          background: typeFilter === t ? '#e8f4fd' : '#fff',
                          fontWeight: typeFilter === t ? 700 : 400,
                        }}>
                        {t || 'All'}
                      </button>
                    ))}
                    <form onSubmit={e => { e.preventDefault(); fetchShortages() }} style={{ display: 'flex', gap: 4 }}>
                      <input type="text" value={search} onChange={e => setSearch(e.target.value)}
                        placeholder="Search item…" style={{ padding: '5px 10px', border: '1px solid var(--line)', borderRadius: 6, fontSize: 12, width: 140 }} />
                      <button type="submit" className="btn-upload" style={{ padding: '5px 10px', fontSize: 12 }}>Go</button>
                    </form>
                  </div>
                </div>

                {loadingShort && <div className="loading">Loading…</div>}

                {!loadingShort && shortages?.rows?.length > 0 && (
                  <div className="table-scroll" style={{ maxHeight: '50vh', overflowY: 'auto' }}>
                    <table style={{ fontSize: 12 }}>
                      <thead>
                        <tr>
                          <th style={{ position: 'sticky', top: 0, background: '#f0f4f8' }}>Component</th>
                          <th style={{ position: 'sticky', top: 0, background: '#f0f4f8' }}>Type</th>
                          <th style={{ position: 'sticky', top: 0, background: '#f0f4f8', textAlign: 'right' }}>Stock</th>
                          <th style={{ position: 'sticky', top: 0, background: '#f0f4f8', textAlign: 'right' }}>Required</th>
                          <th style={{ position: 'sticky', top: 0, background: '#f0f4f8', textAlign: 'right' }}>Allocated</th>
                          <th style={{ position: 'sticky', top: 0, background: '#f0f4f8', textAlign: 'right' }}>Shortage</th>
                          <th style={{ position: 'sticky', top: 0, background: '#f0f4f8' }}>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {shortages.rows.map((r, i) => (
                          <tr key={i}>
                            <td style={{ fontFamily: 'monospace', fontWeight: 600 }}>{r.data.component_item}</td>
                            <td>
                              <span style={{
                                padding: '2px 6px', borderRadius: 4, fontSize: 10, fontWeight: 700,
                                background: r.data.component_type === 'RM' ? '#f39c1220' : r.data.component_type === 'CP' ? '#3498db20' : '#9b59b620',
                                color: r.data.component_type === 'RM' ? '#f39c12' : r.data.component_type === 'CP' ? '#3498db' : '#9b59b6',
                              }}>
                                {r.data.component_type}
                              </span>
                            </td>
                            <td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{Number(r.data.available_stock).toLocaleString()}</td>
                            <td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{Number(r.data.total_requirement).toLocaleString()}</td>
                            <td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{Number(r.data.total_allocated).toLocaleString()}</td>
                            <td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums', fontWeight: 700,
                              color: r.data.has_shortage ? '#c0392b' : 'var(--ok)' }}>
                              {Number(r.data.total_shortage).toLocaleString()}
                            </td>
                            <td>
                              {r.data.has_shortage
                                ? <span style={{ color: '#c0392b', fontWeight: 700, fontSize: 11 }}>⚠ SHORT</span>
                                : <span style={{ color: 'var(--ok)', fontSize: 11 }}>✓ OK</span>}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {!loadingShort && shortages?.rows?.length === 0 && (
                  <p className="note">No components found matching the filter.</p>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </section>
  )
}
