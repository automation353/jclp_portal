import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import TopBar from '../components/TopBar'

export default function SuperAdminUserForm() {
  const { id } = useParams()
  const isNew = !id || id === 'new'
  const navigate = useNavigate()

  const [modules, setModules] = useState([])          // all available modules
  const [form, setForm] = useState({
    username: '', first_name: '', last_name: '', email: '',
    role: 'admin', department: '', password: '', modules: [],
  })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const promises = [api.adminModules()]
    if (!isNew) promises.push(api.adminUserDetail(id))

    Promise.all(promises)
      .then(([mods, user]) => {
        setModules(mods)
        if (user) {
          setForm({
            username: user.username || '',
            first_name: user.first_name || '',
            last_name: user.last_name || '',
            email: user.email || '',
            role: user.role || 'admin',
            department: user.department || '',
            password: '',
            modules: user.modules || [],
          })
        }
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [id, isNew])

  function handleChange(e) {
    const { name, value } = e.target
    setForm((prev) => ({ ...prev, [name]: value }))
  }

  function handleModuleToggle(slug) {
    setForm((prev) => {
      const has = prev.modules.includes(slug)
      return {
        ...prev,
        modules: has
          ? prev.modules.filter((s) => s !== slug)
          : [...prev.modules, slug],
      }
    })
  }

  function handleSelectAll() {
    const allSlugs = modules.map((m) => m.slug)
    const hasAll = allSlugs.every((s) => form.modules.includes(s))
    setForm((prev) => ({ ...prev, modules: hasAll ? [] : allSlugs }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setSaving(true)

    const payload = { ...form }
    // Don't send empty password on edit
    if (!isNew && !payload.password) delete payload.password

    try {
      if (isNew) {
        await api.adminUserCreate(payload)
      } else {
        await api.adminUserUpdate(id, payload)
      }
      navigate('/super-admin/users')
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const isSuperAdmin = form.role === 'super_admin'

  return (
    <section className="screen">
      <TopBar subtitle={`Super Admin › ${isNew ? 'New User' : 'Edit User'}`} />
      <div className="wrap">
        <div className="crumbs">
          <Link to="/departments">Home</Link> › <Link to="/super-admin">Admin</Link> ›{' '}
          <Link to="/super-admin/users">Users</Link> ›{' '}
          <span>{isNew ? 'New User' : 'Edit'}</span>
        </div>

        <h2 className="title">{isNew ? 'Create User' : 'Edit User'}</h2>
        <p className="sub">{isNew
          ? 'Fill in the details below to create a new portal account.'
          : 'Update account details and module access.'}</p>

        {loading && <div className="loading">Loading…</div>}
        {error && <div className="login-error">{error}</div>}

        {!loading && (
          <form className="sa-form" onSubmit={handleSubmit}>
            <div className="sa-form-grid">
              <label className="sa-field">
                <span>Username *</span>
                <input name="username" value={form.username} onChange={handleChange}
                  required disabled={!isNew} />
              </label>
              <label className="sa-field">
                <span>Password {isNew ? '*' : '(leave blank to keep)'}</span>
                <input name="password" type="password" value={form.password}
                  onChange={handleChange} required={isNew}
                  autoComplete="new-password" />
              </label>
              <label className="sa-field">
                <span>First Name</span>
                <input name="first_name" value={form.first_name} onChange={handleChange} />
              </label>
              <label className="sa-field">
                <span>Last Name</span>
                <input name="last_name" value={form.last_name} onChange={handleChange} />
              </label>
              <label className="sa-field">
                <span>Email</span>
                <input name="email" type="email" value={form.email} onChange={handleChange} />
              </label>
              <label className="sa-field">
                <span>Role *</span>
                <select name="role" value={form.role} onChange={handleChange}>
                  <option value="admin">Admin</option>
                  <option value="super_admin">Super Admin</option>
                </select>
              </label>
              <label className="sa-field sa-field-full">
                <span>Department</span>
                <select name="department" value={form.department} onChange={handleChange}>
                  <option value="">— Select Department —</option>
                  {modules.map((m) => (
                    <option key={m.slug} value={m.name}>{m.name}</option>
                  ))}
                  <option value="Management">Management</option>
                </select>
              </label>
            </div>

            <div className="sa-modules-section">
              <div className="sa-modules-head">
                <h3>Module Access</h3>
                {isSuperAdmin
                  ? <span className="sa-modules-note">Super Admins have access to all modules.</span>
                  : <button type="button" className="sa-btn sa-btn-sm" onClick={handleSelectAll}>
                      {modules.length > 0 && modules.every((m) => form.modules.includes(m.slug))
                        ? 'Deselect All' : 'Select All'}
                    </button>}
              </div>
              <div className={`sa-modules-grid ${isSuperAdmin ? 'sa-modules-disabled' : ''}`}>
                {modules.map((m) => (
                  <label key={m.slug} className="sa-module-check">
                    <input
                      type="checkbox"
                      checked={isSuperAdmin || form.modules.includes(m.slug)}
                      disabled={isSuperAdmin}
                      onChange={() => handleModuleToggle(m.slug)}
                    />
                    <span className="sa-module-icon">{m.icon}</span>
                    <span className="sa-module-name">{m.name}</span>
                    {m.is_open && <span className="sa-module-live">LIVE</span>}
                  </label>
                ))}
              </div>
            </div>

            <div className="sa-form-actions">
              <button type="submit" className="btn-upload" disabled={saving}>
                {saving ? 'Saving…' : (isNew ? 'Create User' : 'Save Changes')}
              </button>
              <button type="button" className="sa-btn" onClick={() => navigate('/super-admin/users')}>
                Cancel
              </button>
            </div>
          </form>
        )}
      </div>
    </section>
  )
}
