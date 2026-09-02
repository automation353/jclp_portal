import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import TopBar from '../components/TopBar'

const FREQ_LABEL = {
  daily: '🔄 Daily',
  weekly: '📅 Weekly',
  monthly: '📆 Monthly',
  on_change: '⚡ On change',
}

const STATUS_STYLE = {
  ok: { color: 'var(--ok)', fontWeight: 700, label: '● Active' },
  never_pulled: { color: 'var(--muted)', fontWeight: 400, label: '○ Never pulled' },
  error: { color: 'var(--bad)', fontWeight: 700, label: '✕ Error' },
  empty: { color: 'var(--muted)', fontWeight: 400, label: '○ Empty' },
}

function StatusBadge({ status: s }) {
  const style = STATUS_STYLE[s] || STATUS_STYLE.empty
  return <span style={{ color: style.color, fontWeight: style.fontWeight, fontSize: 12 }}>{style.label}</span>
}

function timeAgo(isoString) {
  if (!isoString) return '—'
  const diff = Date.now() - new Date(isoString).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

export default function PPCDataFeeds() {
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  async function refresh() {
    setLoading(true)
    try {
      setData(await api.ppcDataFeedStatus())
      setError('')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }
  useEffect(() => { refresh() }, [])

  const summary = data?.summary || {}

  return (
    <section className="screen">
      <TopBar subtitle="PPC Department" />
      <div className="wrap">
        <div className="crumbs">
          <Link to="/departments">Home</Link> ›{' '}
          <Link to="/ppc-data">PPC Data</Link> › Feed Status
        </div>
        <button className="backbtn" onClick={() => navigate('/ppc-data')}>← Back to PPC Data</button>

        {/* Summary cards */}
        {data && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 10, marginBottom: 20 }}>
            <div className="panel" style={{ textAlign: 'center', padding: 16, marginBottom: 0 }}>
              <div style={{ fontSize: 28, fontWeight: 700, color: 'var(--accent)' }}>{summary.erp_active}</div>
              <div style={{ fontSize: 11, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.05em' }}>ERP feeds active</div>
            </div>
            <div className="panel" style={{ textAlign: 'center', padding: 16, marginBottom: 0 }}>
              <div style={{ fontSize: 28, fontWeight: 700, color: 'var(--muted)' }}>{summary.erp_total - summary.erp_active}</div>
              <div style={{ fontSize: 11, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.05em' }}>ERP not wired</div>
            </div>
            <div className="panel" style={{ textAlign: 'center', padding: 16, marginBottom: 0 }}>
              <div style={{ fontSize: 28, fontWeight: 700, color: 'var(--ok)' }}>{summary.master_loaded}</div>
              <div style={{ fontSize: 11, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.05em' }}>Masters loaded</div>
            </div>
            <div className="panel" style={{ textAlign: 'center', padding: 16, marginBottom: 0 }}>
              <div style={{ fontSize: 28, fontWeight: 700, color: 'var(--muted)' }}>{summary.master_total - summary.master_loaded}</div>
              <div style={{ fontSize: 11, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.05em' }}>Masters empty</div>
            </div>
          </div>
        )}

        {loading && <div className="loading">Loading feed status…</div>}
        {error && <div className="upload-status error">{error}</div>}

        {/* ERP Feeds */}
        {data && (
          <div className="panel">
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
              <h3 style={{ margin: 0 }}>ERP Feeds — TCS iON → Portal</h3>
              <button onClick={refresh} className="btn-upload" style={{ padding: '6px 12px', fontSize: 12, background: 'var(--steel)' }}>
                ⟳ Refresh
              </button>
            </div>
            <p className="note" style={{ marginBottom: 12 }}>
              n8n pulls each report from TCS iON and POSTs to <code>/api/ppc-data/erp-landing/</code>.
              Once a feed is wired, its status turns green.
            </p>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Report key</th>
                    <th>Frequency</th>
                    <th>Status</th>
                    <th>Rows</th>
                    <th>Last pull</th>
                    <th>File / Error</th>
                  </tr>
                </thead>
                <tbody>
                  {(data.erp_feeds || []).map((f) => (
                    <tr key={f.report_key} style={f.status === 'error' ? { background: '#fef2f2' } : undefined}>
                      <td style={{ fontFamily: 'monospace', fontSize: 12, textAlign: 'center' }}>{f.report_number}</td>
                      <td>
                        {f.status === 'ok'
                          ? <Link to={`/ppc-data/browse?table=${f.report_key}`} style={{ fontWeight: 600 }}>{f.report_key}</Link>
                          : <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{f.report_key}</span>}
                      </td>
                      <td style={{ fontSize: 12 }}>{FREQ_LABEL[f.frequency] || f.frequency}</td>
                      <td><StatusBadge status={f.status} /></td>
                      <td style={{ fontVariantNumeric: 'tabular-nums', textAlign: 'right' }}>
                        {f.row_count != null ? f.row_count.toLocaleString() : '—'}
                      </td>
                      <td className="muted" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
                        {f.uploaded_at ? timeAgo(f.uploaded_at) : '—'}
                      </td>
                      <td style={{ fontSize: 12 }}>
                        {f.parse_error
                          ? <span style={{ color: 'var(--bad)' }}>{f.parse_error.slice(0, 60)}</span>
                          : (f.original_filename || '—')}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Master Tables */}
        {data && (
          <div className="panel">
            <h3 style={{ marginBottom: 12 }}>Foundation Masters — Upload Status</h3>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Table key</th>
                    <th>Fields</th>
                    <th>Status</th>
                    <th>Rows</th>
                    <th>Last upload</th>
                    <th>By</th>
                  </tr>
                </thead>
                <tbody>
                  {(data.master_tables || []).map((m) => (
                    <tr key={m.table_key}>
                      <td>
                        {m.status === 'ok'
                          ? <Link to={`/ppc-data/browse?table=${m.table_key}`} style={{ fontWeight: 600 }}>{m.table_key}</Link>
                          : <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{m.table_key}</span>}
                      </td>
                      <td style={{ textAlign: 'center' }}>{m.field_count}</td>
                      <td><StatusBadge status={m.status} /></td>
                      <td style={{ fontVariantNumeric: 'tabular-nums', textAlign: 'right' }}>
                        {m.row_count != null ? m.row_count.toLocaleString() : '—'}
                      </td>
                      <td className="muted" style={{ fontSize: 12 }}>
                        {m.uploaded_at ? timeAgo(m.uploaded_at) : '—'}
                      </td>
                      <td style={{ fontSize: 12 }}>{m.uploader || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </section>
  )
}
