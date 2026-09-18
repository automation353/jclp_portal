import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import TopBar from '../components/TopBar'

export default function SuperAdmin() {
  const [stats, setStats] = useState(null)
  const [activity, setActivity] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.all([api.adminStats(), api.adminActivity()])
      .then(([s, a]) => {
        setStats(s)
        setActivity(Array.isArray(a) ? a.slice(0, 10) : (a.results || []).slice(0, 10))
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  return (
    <section className="screen">
      <TopBar subtitle="Super Admin" />
      <div className="wrap">
        <div className="crumbs">
          <Link to="/departments">Home</Link> › <span>Super Admin</span>
        </div>

        <div className="page-head">
          <div>
            <h2 className="title">Admin Dashboard</h2>
            <p className="sub">Portal overview — users, modules, and recent activity.</p>
          </div>
        </div>

        {loading && <div className="loading">Loading dashboard…</div>}
        {error && <div className="login-error">{error}</div>}

        {stats && (
          <div className="sa-stats">
            <div className="sa-stat-card">
              <span className="sa-stat-icon">👥</span>
              <div className="sa-stat-body">
                <span className="sa-stat-val">{stats.total_users}</span>
                <span className="sa-stat-label">Total Users</span>
              </div>
            </div>
            <div className="sa-stat-card">
              <span className="sa-stat-icon">✅</span>
              <div className="sa-stat-body">
                <span className="sa-stat-val">{stats.active_users}</span>
                <span className="sa-stat-label">Active Users</span>
              </div>
            </div>
            <div className="sa-stat-card">
              <span className="sa-stat-icon">🔑</span>
              <div className="sa-stat-body">
                <span className="sa-stat-val">{stats.logins_today}</span>
                <span className="sa-stat-label">Logins Today</span>
              </div>
            </div>
            <div className="sa-stat-card">
              <span className="sa-stat-icon">📦</span>
              <div className="sa-stat-body">
                <span className="sa-stat-val">{stats.modules_live} / {stats.modules_total}</span>
                <span className="sa-stat-label">Modules Live</span>
              </div>
            </div>
          </div>
        )}

        <div className="sa-quick-links">
          <Link to="/super-admin/users" className="sa-quick-card">
            <span className="sa-quick-icon">👤</span>
            <div>
              <strong>Manage Users</strong>
              <p>Create, edit, activate/deactivate accounts and assign module access.</p>
            </div>
            <span className="sa-arrow">→</span>
          </Link>
          <Link to="/super-admin/activity" className="sa-quick-card">
            <span className="sa-quick-icon">📋</span>
            <div>
              <strong>Login Activity</strong>
              <p>View sign-in / sign-out history across all portal users.</p>
            </div>
            <span className="sa-arrow">→</span>
          </Link>
        </div>

        {activity.length > 0 && (
          <div className="sa-recent">
            <div className="sa-section-head">
              <h3>Recent Activity</h3>
              <Link to="/super-admin/activity" className="sa-view-all">View all →</Link>
            </div>
            <div className="sa-table-wrap">
              <table className="sa-table">
                <thead>
                  <tr>
                    <th>User</th>
                    <th>Event</th>
                    <th>IP</th>
                    <th>Time</th>
                  </tr>
                </thead>
                <tbody>
                  {activity.map((evt) => (
                    <tr key={evt.id}>
                      <td><strong>{evt.full_name || evt.username}</strong></td>
                      <td>
                        <span className={`sa-badge ${evt.event_type === 'login' ? 'sa-badge-ok' : 'sa-badge-muted'}`}>
                          {evt.event_type}
                        </span>
                      </td>
                      <td className="sa-mono">{evt.ip_address || '—'}</td>
                      <td>{new Date(evt.timestamp).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })}</td>
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
