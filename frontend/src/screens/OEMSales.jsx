import { Link, useNavigate } from 'react-router-dom'
import Card from '../components/Card'
import TopBar from '../components/TopBar'

// OEM Sales landing — same MTO/MTS module Operations owns; Sales can view
// and edit their own review column, but not upload the source file.
const SALES_PORTALS = [
  {
    slug: 'mto-mts', name: 'MTO / MTS Monthly Status', icon: '📅',
    description: 'Review and comment on the monthly MTO/MTS classification.',
    status: 'live',
  },
  {
    slug: 'oem-forecast', name: 'OEM Forecast', icon: '📈',
    description: 'Rolling customer-order forecast.', status: 'soon',
  },
  {
    slug: 'non-grn', name: 'Non GRN', icon: '🧾',
    description: 'Non-GRN ageing — Report, Customer Dashboard & Manual GRN.',
    status: 'live', external: '/nongrn/',
  },
]

export default function OEMSales() {
  const navigate = useNavigate()

  function open(portal) {
    // Server-rendered Django modules (e.g. Non GRN) live outside the SPA, so
    // navigate with a full page load rather than the React router.
    if (portal.external) { window.location.href = portal.external; return }
    if (portal.status === 'live') navigate(`/${portal.slug}`)
    else window.alert(`“${portal.name}” — coming soon.\nThis module isn't built yet.`)
  }

  return (
    <section className="screen">
      <TopBar subtitle="OEM Sales Department" />
      <div className="wrap">
        <div className="crumbs">
          <Link to="/departments">Home</Link> › OEM Sales
        </div>
        <h2 className="title">OEM Sales — Work Portals</h2>
        <p className="sub">Pick a module. The MTO / MTS one is live and shared with Operations.</p>

        <div className="grid">
          {SALES_PORTALS.map((portal) => (
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
