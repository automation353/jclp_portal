import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import Card from '../components/Card'
import TopBar from '../components/TopBar'

export default function Departments() {
  const navigate = useNavigate()
  const [departments, setDepartments] = useState([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.departments()
      .then(setDepartments)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  function open(department) {
    if (department.is_open) {
      navigate(`/${department.slug}`)
    } else {
      window.alert(`“${department.name}” — coming soon.\nThis department's modules aren't built yet.`)
    }
  }

  return (
    <section className="screen">
      <TopBar />
      <div className="wrap">
        <div className="crumbs"><Link to="/departments">Home</Link></div>
        <h2 className="title">Departments</h2>
        <p className="sub">
          Select a department to open its work portals. (Purchase is wired to live data; the rest are placeholders.)
        </p>

        {loading && <div className="loading">Loading departments…</div>}
        {error && <div className="login-error">{error}</div>}

        <div className="grid">
          {departments.map((department) => (
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
