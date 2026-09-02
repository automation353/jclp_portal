import { Link, useNavigate } from 'react-router-dom'
import Card from '../components/Card'
import TopBar from '../components/TopBar'

// Operations landing — one live module (MTO/MTS Monthly Status), the rest
// are placeholders to match the Departments-page pattern.
const OPERATIONS_PORTALS = [
  {
    slug: 'mto-mts', name: 'MTO / MTS Monthly Status', icon: '📅',
    description: 'Monthly MTO/MTS classification, review, and change log.',
    status: 'live',
  },
  {
    slug: 'production-plan', name: 'Production Plan', icon: '🏭',
    description: 'Rolling monthly plan and WIP tracking.', status: 'soon',
  },
  {
    slug: 'reconciliation', name: 'Reconciliation', icon: '🧾',
    description: 'Stock and production reconciliation.', status: 'soon',
  },
]

export default function Operations() {
  const navigate = useNavigate()

  function open(portal) {
    if (portal.status === 'live') navigate(`/${portal.slug}`)
    else window.alert(`“${portal.name}” — coming soon.\nThis module isn't built yet.`)
  }

  return (
    <section className="screen">
      <TopBar subtitle="Operations Department" />
      <div className="wrap">
        <div className="crumbs">
          <Link to="/departments">Home</Link> › Operations
        </div>
        <h2 className="title">Operations — Work Portals</h2>
        <p className="sub">Pick a module. The MTO / MTS one is live and shared with OEM Sales.</p>

        <div className="grid">
          {OPERATIONS_PORTALS.map((portal) => (
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
