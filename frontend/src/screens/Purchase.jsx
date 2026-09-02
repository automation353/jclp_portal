import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import Card from '../components/Card'
import TopBar from '../components/TopBar'

export default function Purchase() {
  const navigate = useNavigate()
  const [portals, setPortals] = useState([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.purchasePortals()
      .then(setPortals)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  function open(portal) {
    if (portal.status === 'live') {
      navigate(`/purchase/${portal.slug}`)
    } else {
      window.alert(`“${portal.name}” — coming soon.\nThis module isn't built yet.`)
    }
  }

  return (
    <section className="screen">
      <TopBar subtitle="Purchase Department" />
      <div className="wrap">
        <div className="crumbs">
          <Link to="/departments">Home</Link> › <Link to="/purchase">Purchase</Link>
        </div>
        <div className="page-head">
          <div>
            <h2 className="title">Purchase — Work Portals</h2>
            <p className="sub">Each tile is a self-contained module. Two are wired to live data.</p>
          </div>
          <div className="head-buttons">
            <Link className="btn-upload" to="/purchase/dashboard">
              📊 Dashboard
            </Link>
            <Link className="btn-upload" to="/purchase/upload">
              ⬆ Upload Data
            </Link>
          </div>
        </div>

        {loading && <div className="loading">Loading work portals…</div>}
        {error && <div className="login-error">{error}</div>}

        <div className="grid">
          {portals.map((portal) => (
            <Card
              key={portal.slug}
              icon={portal.icon}
              title={portal.name}
              description={portal.description}
              tag={portal.status === 'live'
                ? { kind: 'live', label: 'LIVE' }
                : { kind: 'soon', label: 'SOON' }}
              onClick={() => open(portal)}
            />
          ))}
        </div>
      </div>
    </section>
  )
}
