import { Link, useNavigate } from 'react-router-dom'
import Card from '../components/Card'
import TopBar from '../components/TopBar'

// S&OP landing — one placeholder tile for PPC Forecast. When Dharmik +
// team decide what the module should do, flip status to 'live' and wire
// the route.
const SANDOP_PORTALS = [
  {
    slug: 's-and-op/demand-supply', name: 'Demand & Supply Visibility', icon: '📊',
    description: 'Cross-functional dashboard — demand, plan, production, stock, and gap analysis.',
    status: 'live',
  },
  {
    slug: 's-and-op/demand-supply/upload', name: 'S&OP Data Upload', icon: '📤',
    description: 'Upload the 5 S&OP data files (DPR, Forecast, Opening Stock, Green Level, Sales Register).',
    status: 'live',
  },
  {
    slug: 'ppc-data', name: 'PPC Data Pipeline', icon: '🏭',
    description: 'Upload master files, browse loaded data, and track the PPC data pipeline.',
    status: 'live',
  },
  {
    slug: 'ppc-forecast', name: 'PPC Forecast', icon: '📈',
    description: 'Upload the PPC forecast file for the S&OP cycle.',
    status: 'live',
  },
  {
    slug: 'ppc', name: 'RM CP Packing Upload', icon: '📋',
    description: 'Upload RM CP Packing material planning file (→ Google Sheet).',
    status: 'live',
  },
]

export default function SAndOP() {
  const navigate = useNavigate()

  function open(portal) {
    if (portal.status === 'live') navigate(`/${portal.slug}`)
    else window.alert(`“${portal.name}” — coming soon.\nThis module isn't built yet.`)
  }

  return (
    <section className="screen">
      <TopBar subtitle="S&OP Department" />
      <div className="wrap">
        <div className="crumbs">
          <Link to="/departments">Home</Link> › S&amp;OP
        </div>
        <h2 className="title">S&amp;OP — Work Portals</h2>
        <p className="sub">Sales &amp; Operations Planning modules.</p>

        <div className="grid">
          {SANDOP_PORTALS.map((portal) => (
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
