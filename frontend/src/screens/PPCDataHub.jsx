import { Link, useNavigate } from 'react-router-dom'
import Card from '../components/Card'
import TopBar from '../components/TopBar'

const PPC_PORTALS = [
  {
    slug: 'ppc-data/upload',
    name: 'Upload',
    icon: '📤',
    description: 'Upload R3SS source files and foundation masters. Auto-detects file type from filename.',
    status: 'live',
  },
  {
    slug: 'ppc-data/r3ss',
    name: 'R3SS Dashboard',
    icon: '📊',
    description: 'R3SS Production Plan — recompute, view, and sync to Google Sheet.',
    status: 'live',
  },
]

export default function PPCDataHub() {
  const navigate = useNavigate()

  function open(portal) {
    if (portal.status === 'live') navigate(`/${portal.slug}`)
    else window.alert(`"${portal.name}" — coming soon.`)
  }

  return (
    <section className="screen">
      <TopBar subtitle="PPC Department" />
      <div className="wrap">
        <div className="crumbs">
          <Link to="/departments">Home</Link> › PPC Data
        </div>
        <h2 className="title">PPC Data Pipeline</h2>
        <p className="sub">
          Production Planning &amp; Control — upload masters, browse loaded data, track ERP feeds.
        </p>

        <div className="grid">
          {PPC_PORTALS.map((portal) => (
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
