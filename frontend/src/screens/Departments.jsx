import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import Card from '../components/Card'
import TopBar from '../components/TopBar'

export default function Departments() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const [departments, setDepartments] = useState([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.departments()
      .then(setDepartments)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  // Super Admins see everything; regular admins see only their assigned modules.
  const visibleDepts = useMemo(() => {
    if (!user || user.is_super_admin) return departments
    const allowed = new Set(user.modules || [])
    return departments.filter((d) => allowed.has(d.slug))
  }, [departments, user])

  // Some departments open a specific route instead of /<slug>. PPC skips the
  // old File Upload screen and opens the PPC Data Pipeline hub directly.
  const ROUTE_OVERRIDES = { ppc: '/ppc-data' }

  function open(department) {
    if (department.is_open) {
      navigate(ROUTE_OVERRIDES[department.slug] || `/${department.slug}`)
    } else {
      window.alert(`“${department.name}” — coming soon.\nThis department's modules aren't built yet.`)
    }
  }

  return (
    <section className="screen">
      <TopBar />
      <div className="wrap">
        <div className="crumbs"><Link to="/departments">Home</Link></div>
        <div className="page-head">
          <div>
            <h2 className="title">Departments</h2>
            <p className="sub">
              Select a department to open its work portals. (Purchase is wired to live data; the rest are placeholders.)
            </p>
          </div>
          {user?.is_super_admin && (
            <div className="head-buttons">
              <Link className="btn-upload" to="/super-admin">⚙️ Admin Panel</Link>
            </div>
          )}
        </div>

        {loading && <div className="loading">Loading departments…</div>}
        {error && <div className="login-error">{error}</div>}

        <div className="grid">
          {visibleDepts.map((department) => (
            <Card
              key={department.slug}
              icon={department.icon}
              title={department.name}
              description={department.description}
              tag={department.is_open
                ? { kind: 'live', label: 'OPEN' }
                : { kind: 'soon', label: 'SOON' }}
              onClick={() => open(department)}
            />
          ))}
        </div>
      </div>
    </section>
  )
}
