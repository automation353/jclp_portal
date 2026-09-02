import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import TopBar from '../components/TopBar'

/**
 * Screen 6a — L5 Feasibility Gate + L6 Release
 *
 * Rule 5: capacity is a gate — plan cannot release without passing.
 *
 * Features:
 *   - Run feasibility check on current R3SS plan
 *   - View capacity, machine, EBQ flags
 *   - Resolve flags with reason codes
 *   - Approve plan → create release
 *   - View/recall releases
 */
export default function PPCFeasibility() {
  const navigate = useNavigate()

  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  // Resolve modal
  const [resolveFlag, setResolveFlag] = useState(null)
  const [reasonCode, setReasonCode] = useState('')
  const [reasonText, setReasonText] = useState('')
  const [resolving, setResolving] = useState(false)

  // Release
  const [releases, setReleases] = useState([])
  const [loadingReleases, setLoadingReleases] = useState(false)

  function refresh() {
    setLoading(true)
    api.ppcFeasibilityStatus()
      .then(d => setStatus(d))
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  function refreshReleases() {
    setLoadingReleases(true)
    api.ppcReleaseList()
      .then(d => setReleases(d.releases || []))
      .catch(() => {})
      .finally(() => setLoadingReleases(false))
  }

  useEffect(() => { refresh(); refreshReleases() }, [])

  async function handleRun() {
    setRunning(true); setError(''); setSuccess('')
    try {
      await api.ppcFeasibilityRun()
      setSuccess('Feasibility check completed.')
      refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setRunning(false)
    }
  }

  async function handleResolve(e) {
    e.preventDefault()
    if (!reasonCode.trim()) return
    setResolving(true)
    try {
      await api.ppcFeasibilityResolve(resolveFlag.id, reasonCode, reasonText)
      setResolveFlag(null)
      setReasonCode('')
      setReasonText('')
      refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setResolving(false)
    }
  }

  async function handleApprove() {
    if (!status?.run) return
    setError(''); setSuccess('')
    try {
      await api.ppcFeasibilityApprove(status.run.id)
      setSuccess('Plan approved! You can now create a release.')
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleRelease() {
    if (!status?.run) return
    setError(''); setSuccess('')
    try {
      const res = await api.ppcReleaseCreate(status.run.id)
      setSuccess(`Release #${res.release_number} created for ${res.plan_month}.`)
      refreshReleases()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleRecall(releaseId) {
    const reason = prompt('Reason for recalling this release:')
    if (!reason) return
    try {
      await api.ppcReleaseRecall(releaseId, reason)
      refreshReleases()
    } catch (err) {
      setError(err.message)
    }
  }

  const run = status?.run
  const flags = status?.flags || []
  const unresolvedFlags = flags.filter(f => !f.resolved)
  const resolvedFlags = flags.filter(f => f.resolved)

  const FLAG_COLORS = { capacity: '#c0392b', machine: '#e67e22', ebq: '#8e44ad' }
  const FLAG_LABELS = { capacity: 'Capacity', machine: 'Machine', ebq: 'EBQ' }

  return (
    <section className="screen">
      <TopBar subtitle="PPC Department" />
      <div className="wrap" style={{ maxWidth: 1000 }}>
        <div className="crumbs">
          <Link to="/departments">Home</Link> ›{' '}
          <Link to="/ppc-data">PPC Data</Link> › Feasibility & Release
        </div>
        <button className="backbtn" onClick={() => navigate('/ppc-data')}>← Back to PPC Data</button>

        {/* Rule 5 callout */}
        <div style={{
          background: 'linear-gradient(135deg, #fbe8e8 0%, #f9dada 100%)',
          borderRadius: 8, padding: '14px 18px', marginBottom: 18,
          borderLeft: '4px solid #c0392b', fontSize: 13, lineHeight: 1.6,
        }}>
          <strong style={{ color: '#c0392b' }}>Rule 5 — Capacity is a Gate</strong><br />
          The plan cannot be released to the shop floor until it passes feasibility checks:
          capacity, machine loading, and EBQ qualification. Every flag must be resolved.
        </div>

        {error && <div className="upload-status error" style={{ marginBottom: 12 }}>{error}</div>}
        {success && <div className="upload-status ok" style={{ marginBottom: 12 }}>{success}</div>}

        {/* Run feasibility */}
        <div className="panel">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
            <h3 style={{ margin: 0 }}>Feasibility Check</h3>
            <button onClick={handleRun} className="btn-upload" disabled={running}
              style={{ padding: '8px 18px', fontSize: 13 }}>
              {running ? 'Running…' : '🔍 Run Feasibility Check'}
            </button>
          </div>
          <p className="note" style={{ marginTop: 8 }}>
            Runs against the current R3SS plan. Checks capacity (W1.6), machine loading (W1.4 + W1.7),
            and EBQ qualification (W1.8).
          </p>
        </div>

        {loading && <div className="loading">Loading…</div>}

        {/* Run summary */}
        {!loading && run && (
          <div className="panel">
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 12 }}>
              <h3 style={{ margin: 0 }}>
                Latest Run — {run.plan_month}
              </h3>
              <span style={{
                padding: '3px 10px', borderRadius: 12, fontSize: 11, fontWeight: 700,
                background: run.status === 'approved' ? '#27ae6020' : run.status === 'flagged' ? '#e74c3c20' : '#95a5a620',
                color: run.status === 'approved' ? '#27ae60' : run.status === 'flagged' ? '#e74c3c' : '#7f8c8d',
              }}>
                {run.status.toUpperCase()}
              </span>
            </div>

            {/* Summary tiles */}
            {run.summary && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(100px, 1fr))', gap: 8, marginBottom: 14 }}>
                {[
                  { label: 'Plan items', value: run.summary.plan_items, color: 'var(--ink)' },
                  { label: 'Capacity flags', value: run.summary.capacity_flags, color: run.summary.capacity_flags > 0 ? '#c0392b' : 'var(--ok)' },
                  { label: 'Machine flags', value: run.summary.machine_flags, color: run.summary.machine_flags > 0 ? '#e67e22' : 'var(--ok)' },
                  { label: 'EBQ flags', value: run.summary.ebq_flags, color: run.summary.ebq_flags > 0 ? '#8e44ad' : 'var(--ok)' },
                  { label: 'Total flags', value: run.summary.total_flags, color: run.summary.total_flags > 0 ? 'var(--bad)' : 'var(--ok)' },
                ].map(t => (
                  <div key={t.label} style={{ textAlign: 'center', padding: '10px 6px', borderRadius: 6, border: '1px solid var(--line)' }}>
                    <div style={{ fontSize: 22, fontWeight: 700, color: t.color, fontVariantNumeric: 'tabular-nums' }}>{t.value}</div>
                    <div style={{ fontSize: 10, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.04em' }}>{t.label}</div>
                  </div>
                ))}
              </div>
            )}

            {/* Actions */}
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {run.status === 'flagged' && unresolvedFlags.length === 0 && (
                <button onClick={handleApprove} className="btn-upload" style={{ padding: '8px 18px', fontSize: 13, background: '#27ae60', borderColor: '#27ae60' }}>
                  ✅ Approve Plan
                </button>
              )}
              {run.status === 'approved' && (
                <button onClick={handleRelease} className="btn-upload" style={{ padding: '8px 18px', fontSize: 13, background: '#2980b9', borderColor: '#2980b9' }}>
                  📦 Create Release
                </button>
              )}
            </div>
          </div>
        )}

        {/* Unresolved flags */}
        {!loading && unresolvedFlags.length > 0 && (
          <div className="panel">
            <h3 style={{ marginBottom: 10, color: '#c0392b' }}>
              ⚠ Unresolved Flags ({unresolvedFlags.length})
            </h3>
            <div className="table-scroll" style={{ maxHeight: '40vh', overflowY: 'auto' }}>
              <table style={{ fontSize: 12 }}>
                <thead>
                  <tr>
                    <th style={{ position: 'sticky', top: 0, background: '#f0f4f8' }}>Type</th>
                    <th style={{ position: 'sticky', top: 0, background: '#f0f4f8' }}>Date</th>
                    <th style={{ position: 'sticky', top: 0, background: '#f0f4f8' }}>Group / Item</th>
                    <th style={{ position: 'sticky', top: 0, background: '#f0f4f8' }}>Section</th>
                    <th style={{ position: 'sticky', top: 0, background: '#f0f4f8', textAlign: 'right' }}>Planned</th>
                    <th style={{ position: 'sticky', top: 0, background: '#f0f4f8', textAlign: 'right' }}>Capacity</th>
                    <th style={{ position: 'sticky', top: 0, background: '#f0f4f8', textAlign: 'right' }}>Overload</th>
                    <th style={{ position: 'sticky', top: 0, background: '#f0f4f8' }}>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {unresolvedFlags.map(f => (
                    <tr key={f.id}>
                      <td>
                        <span style={{ padding: '2px 8px', borderRadius: 10, fontSize: 10, fontWeight: 700,
                          background: (FLAG_COLORS[f.flag_type] || '#999') + '20', color: FLAG_COLORS[f.flag_type] || '#999' }}>
                          {FLAG_LABELS[f.flag_type] || f.flag_type}
                        </span>
                      </td>
                      <td style={{ fontFamily: 'monospace' }}>{f.date || '—'}</td>
                      <td style={{ fontWeight: 600 }}>{f.product_group || f.item_code || '—'}</td>
                      <td>{f.section || '—'}</td>
                      <td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{f.planned_qty.toLocaleString()}</td>
                      <td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{f.capacity_qty.toLocaleString()}</td>
                      <td style={{ textAlign: 'right', fontWeight: 700, color: f.overload_pct > 0 ? '#c0392b' : '#8e44ad' }}>
                        {f.overload_pct > 0 ? `+${f.overload_pct}%` : `${f.overload_pct}%`}
                      </td>
                      <td>
                        <button onClick={() => { setResolveFlag(f); setReasonCode(''); setReasonText('') }}
                          style={{ padding: '3px 10px', borderRadius: 4, border: '1px solid var(--accent)', background: '#fff',
                            color: 'var(--accent)', cursor: 'pointer', fontSize: 11, fontWeight: 600 }}>
                          Resolve
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Resolved flags */}
        {!loading && resolvedFlags.length > 0 && (
          <div className="panel">
            <h3 style={{ marginBottom: 10, color: 'var(--ok)' }}>
              ✅ Resolved Flags ({resolvedFlags.length})
            </h3>
            <div className="table-scroll" style={{ maxHeight: '30vh', overflowY: 'auto' }}>
              <table style={{ fontSize: 12, opacity: 0.8 }}>
                <thead>
                  <tr>
                    <th style={{ position: 'sticky', top: 0, background: '#f0f4f8' }}>Type</th>
                    <th style={{ position: 'sticky', top: 0, background: '#f0f4f8' }}>Date</th>
                    <th style={{ position: 'sticky', top: 0, background: '#f0f4f8' }}>Group / Item</th>
                    <th style={{ position: 'sticky', top: 0, background: '#f0f4f8' }}>Reason</th>
                    <th style={{ position: 'sticky', top: 0, background: '#f0f4f8' }}>Resolved by</th>
                  </tr>
                </thead>
                <tbody>
                  {resolvedFlags.map(f => (
                    <tr key={f.id}>
                      <td><span style={{ padding: '2px 8px', borderRadius: 10, fontSize: 10, fontWeight: 700,
                        background: '#27ae6020', color: '#27ae60' }}>
                        {FLAG_LABELS[f.flag_type]}
                      </span></td>
                      <td style={{ fontFamily: 'monospace' }}>{f.date || '—'}</td>
                      <td>{f.product_group || f.item_code || '—'}</td>
                      <td style={{ fontWeight: 600 }}>{f.reason_code}{f.reason_text ? ` — ${f.reason_text}` : ''}</td>
                      <td>{f.resolved_by__username || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Releases */}
        <div className="panel">
          <h3 style={{ marginBottom: 10 }}>Releases</h3>
          {loadingReleases && <div className="loading">Loading…</div>}
          {!loadingReleases && releases.length === 0 && (
            <p className="note">No releases yet. Run feasibility → approve → create release.</p>
          )}
          {!loadingReleases && releases.length > 0 && (
            <div className="table-scroll">
              <table style={{ fontSize: 12 }}>
                <thead>
                  <tr>
                    <th>Month</th><th>#</th><th>Status</th><th>Items</th><th>Released by</th><th>Released at</th><th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {releases.map(r => (
                    <tr key={r.id}>
                      <td style={{ fontWeight: 700 }}>{r.plan_month}</td>
                      <td>#{r.release_number}</td>
                      <td>
                        <span style={{
                          padding: '2px 8px', borderRadius: 10, fontSize: 10, fontWeight: 700,
                          background: r.status === 'active' ? '#27ae6020' : '#e74c3c20',
                          color: r.status === 'active' ? '#27ae60' : '#e74c3c',
                        }}>
                          {r.status.toUpperCase()}
                        </span>
                      </td>
                      <td>{r.row_count.toLocaleString()}</td>
                      <td>{r.released_by || '—'}</td>
                      <td style={{ fontSize: 11 }}>{new Date(r.released_at).toLocaleString()}</td>
                      <td>
                        <div style={{ display: 'flex', gap: 4 }}>
                          <button onClick={() => navigate(`/ppc-data/release/${r.id}`)}
                            style={{ padding: '2px 8px', borderRadius: 4, border: '1px solid var(--line)', background: '#fff', cursor: 'pointer', fontSize: 11 }}>
                            View
                          </button>
                          {r.status === 'active' && (
                            <button onClick={() => handleRecall(r.id)}
                              style={{ padding: '2px 8px', borderRadius: 4, border: '1px solid #e74c3c', background: '#fff', color: '#e74c3c', cursor: 'pointer', fontSize: 11 }}>
                              Recall
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Resolve modal */}
        {resolveFlag && (
          <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
            <form onSubmit={handleResolve} style={{ background: '#fff', borderRadius: 10, padding: 24, width: 400, maxWidth: '90vw' }}>
              <h3 style={{ marginBottom: 12 }}>Resolve Flag</h3>
              <p style={{ fontSize: 13, marginBottom: 12, color: 'var(--muted)' }}>
                <strong>{FLAG_LABELS[resolveFlag.flag_type]}</strong> — {resolveFlag.product_group || resolveFlag.item_code}
                {resolveFlag.date && <> on {resolveFlag.date}</>}
                <br />
                Planned: {resolveFlag.planned_qty.toLocaleString()} · Capacity: {resolveFlag.capacity_qty.toLocaleString()} · Overload: {resolveFlag.overload_pct}%
              </p>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 10 }}>
                Reason Code *
                <select value={reasonCode} onChange={e => setReasonCode(e.target.value)}
                  style={{ display: 'block', width: '100%', marginTop: 4, padding: '8px 10px', border: '1px solid var(--line)', borderRadius: 6, fontSize: 13 }}>
                  <option value="">Select…</option>
                  <option value="overtime">Overtime approved</option>
                  <option value="outsource">Outsourcing arranged</option>
                  <option value="shift_change">Extra shift added</option>
                  <option value="plan_adjusted">Plan will be adjusted</option>
                  <option value="alternate_machine">Alternate machine available</option>
                  <option value="batch_combine">Batches combined</option>
                  <option value="accepted_risk">Risk accepted by management</option>
                  <option value="other">Other</option>
                </select>
              </label>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 14 }}>
                Explanation (optional)
                <textarea value={reasonText} onChange={e => setReasonText(e.target.value)}
                  rows={2} style={{ display: 'block', width: '100%', marginTop: 4, padding: '8px 10px', border: '1px solid var(--line)', borderRadius: 6, fontSize: 13, resize: 'vertical' }} />
              </label>
              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                <button type="button" onClick={() => setResolveFlag(null)}
                  style={{ padding: '8px 16px', border: '1px solid var(--line)', borderRadius: 6, background: '#fff', cursor: 'pointer', fontSize: 13 }}>
                  Cancel
                </button>
                <button type="submit" className="btn-upload" disabled={!reasonCode || resolving}
                  style={{ padding: '8px 16px', fontSize: 13 }}>
                  {resolving ? 'Saving…' : 'Resolve Flag'}
                </button>
              </div>
            </form>
          </div>
        )}
      </div>
    </section>
  )
}
