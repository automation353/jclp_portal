import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import TopBar from '../components/TopBar'

export default function SuperAdminUsers() {
  const navigate = useNavigate()
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [toggling, setToggling] = useState(null)

  function load() {
    setLoading(true)
    api.adminUsers()
      .then((data) => setUsers(Array.isArray(data) ? data : data.results || []))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  async function handleToggle(user) {
    if (!window.confirm(`${user.is_active ? 'Deactivate' : 'Activate'} ${user.username}?`)) return
    setToggling(user.id)
    try {
      const res = await api.adminUserToggle(user.id)
      setUsers((prev) =>
        prev.map((u) => (u.id === user.id ? { ...u, is_active: res.is_active } : u))
      )
    } catch (err) {
      window.alert(err.message)
    } finally {
      setToggling(null)
    }
  }

  const filtered = users.filter((u) => {
    if (!search) return true
    const q = search.toLowerCase()
    return (
      u.username.toLowerCase().includes(q) ||
      (u.first_name || '').toLowerCase().includes(q) ||
      (u.last_name || '').toLowerCase().includes(q) ||
      (u.email || '').toLowerCase().includes(q) ||
      (u.department || '').toLowerCase().includes(q)
    )
  })

  return (
    <section className="screen">
      <TopBar subtitle="Super Admin › Users" />
      <div className="wrap wrap-wide">
        <div className="crumbs">
          <Link to="/departments">Home</Link> › <Link to="/super-admin">Admin</Link> › <span>Users</span>
        </div>

        <div className="page-head">
          <div>
            <h2 className="title">User Management</h2>
            <p className="sub">
              {users.length} account{users.length !== 1 ? 's' : ''} total
              {filtered.length !== users.length ? ` · ${filtered.length} shown` : ''}
            </p>
          </div>
          <div className="head-buttons">
            <Link to="/super-admin/users/new" className="btn-upload">+ New User</Link>
          </div>
        </div>

        <div className="sa-search-bar">
          <input
            type="text"
            placeholder="Search users by name, username, email, or department…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="sa-search-input"
          />
        </div>

        {loading && <div className="loading">Loading users…</div>}
        {error && <div className="login-error">{error}</div>}

        {!loading && (
          <div className="sa-table-wrap">
            <table className="sa-table sa-table-users">
              <thead>
                <tr>
                  <th>User</th>
                  <th>Role</th>
                  <th>Department</th>
                  <th>Modules</th>
                  <th>Status</th>
                  <th>Last Login</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((u) => (
                  <tr key={u.id} className={!u.is_active ? 'sa-row-inactive' : ''}>
                    <td>
                      <div className="sa-user-cell">
                        <strong>{u.first_name} {u.last_name}</strong>
                        <span className="sa-user-sub">{u.username}{u.email ? ` · ${u.email}` : ''}</span>
                      </div>
                    </td>
                    <td>
                      <span className={`sa-badge ${u.role === 'super_admin' ? 'sa-badge-accent' : 'sa-badge-muted'}`}>
                        {u.role === 'super_admin' ? 'Super Admin' : 'Admin'}
                      </span>
                    </td>
                    <td>{u.department || '—'}</td>
                    <td>
                      <span className="sa-module-count">
                        {u.role === 'super_admin' ? 'All' : (u.modules?.length || 0)}
                      </span>
                    </td>
                    <td>
                      <span className={`sa-status ${u.is_active ? 'sa-status-active' : 'sa-status-inactive'}`}>
                        {u.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td>
                      {u.last_login
                        ? new Date(u.last_login).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })
                        : 'Never'}
                    </td>
                    <td>
                      <div className="sa-actions">
                        <button
                          className="sa-btn sa-btn-sm"
                          onClick={() => navigate(`/super-admin/users/${u.id}`)}
                        >
                          Edit
                        </button>
                        <button
                          className={`sa-btn sa-btn-sm ${u.is_active ? 'sa-btn-warn' : 'sa-btn-ok'}`}
                          disabled={toggling === u.id}
                          onClick={() => handleToggle(u)}
                        >
                          {toggling === u.id ? '…' : u.is_active ? 'Deactivate' : 'Activate'}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr><td colSpan="7" className="sa-empty">No users found.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  )
}
