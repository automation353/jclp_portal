import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import TopBar from '../components/TopBar'

export default function SuperAdminActivity() {
  const [events, setEvents] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [filterUser, setFilterUser] = useState('')

  function load(username) {
    setLoading(true)
    api.adminActivity(username)
      .then((data) => setEvents(Array.isArray(data) ? data : data.results || []))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load('') }, [])

  function handleFilter(e) {
    e.preventDefault()
    load(filterUser)
  }

  return (
    <section className="screen">
      <TopBar subtitle="Super Admin › Activity" />
      <div className="wrap wrap-wide">
        <div className="crumbs">
          <Link to="/departments">Home</Link> › <Link to="/super-admin">Admin</Link> › <span>Activity</span>
        </div>

        <h2 className="title">Login Activity</h2>
        <p className="sub">Recent sign-in and sign-out events across all users (up to 200).</p>

        <form className="sa-filter-bar" onSubmit={handleFilter}>
          <input
            type="text"
            placeholder="Filter by username…"
            value={filterUser}
            onChange={(e) => setFilterUser(e.target.value)}
            className="sa-search-input"
          />
          <button type="submit" className="sa-btn">Filter</button>
          {filterUser && (
            <button type="button" className="sa-btn" onClick={() => { setFilterUser(''); load('') }}>
              Clear
            </button>
          )}
        </form>

        {loading && <div className="loading">Loading activity…</div>}
        {error && <div className="login-error">{error}</div>}

        {!loading && (
          <div className="sa-table-wrap">
            <table className="sa-table">
              <thead>
                <tr>
                  <th>User</th>
                  <th>Name</th>
                  <th>Event</th>
                  <th>IP Address</th>
                  <th>Timestamp</th>
                </tr>
              </thead>
              <tbody>
                {events.map((evt) => (
                  <tr key={evt.id}>
                    <td><strong>{evt.username}</strong></td>
                    <td>{evt.full_name || '—'}</td>
                    <td>
                      <span className={`sa-badge ${evt.event_type === 'login' ? 'sa-badge-ok' : 'sa-badge-muted'}`}>
                        {evt.event_type}
                      </span>
                    </td>
                    <td className="sa-mono">{evt.ip_address || '—'}</td>
                    <td>{new Date(evt.timestamp).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })}</td>
                  </tr>
                ))}
                {events.length === 0 && (
                  <tr><td colSpan="5" className="sa-empty">No activity found.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  )
}
