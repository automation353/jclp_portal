import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import TopBar from '../components/TopBar'

/**
 * Shared Change Log (Change instructions 9 + 10) — the only report both
 * departments read. Columns per the 11-Aug review:
 *   When | Item | From | To | Comment | Who made the changes.
 * "Field" column is intentionally gone; "By" was renamed.
 */
export default function MtoMtsChanges() {
  const navigate = useNavigate()
  const [changes, setChanges] = useState([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.mtoMtsChanges()
      .then(setChanges)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  return (
    <section className="screen">
      <TopBar subtitle="MTO / MTS — Change Log" />
      <div className="wrap">
        <div className="crumbs">
          <Link to="/departments">Home</Link> ›{' '}
          <Link to="/mto-mts">MTO / MTS</Link> ›{' '}
          Change Log
        </div>
        <button className="backbtn" onClick={() => navigate('/mto-mts')}>← Back to MTO / MTS</button>

        <div className="panel">
          <h3>Change Log</h3>
          <p className="note" style={{ marginBottom: 14 }}>
            The single record of every edit both teams have made this cycle, newest first.
            Append-only — nothing is ever overwritten.
          </p>

          {loading && <div className="loading">Loading change log…</div>}
          {error && <div className="login-error">{error}</div>}

          {!loading && !error && changes.length === 0 && (
            <p className="note">No changes yet.</p>
          )}

          {!loading && !error && changes.length > 0 && (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Item</th>
                    <th>From</th>
                    <th>To</th>
                    <th>Comment</th>
                    <th>Who made the changes</th>
                  </tr>
                </thead>
                <tbody>
                  {changes.map((row) => (
                    <tr key={row.id}>
                      <td className="muted">{new Date(row.changed_at).toLocaleString()}</td>
                      <td><b>{row.item_code}</b> <span className="muted">— {row.item_group}</span></td>
                      <td className="muted">{row.old_value || '—'}</td>
                      <td><b>{row.new_value || '—'}</b></td>
                      <td>{row.comment || <span className="muted">—</span>}</td>
                      <td>
                        <b>{row.changed_by_username}</b>
                        {row.department && <span className="muted"> · {row.department}</span>}
                      </td>
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
