import { Link, useNavigate } from 'react-router-dom'
import Card from '../components/Card'
import TopBar from '../components/TopBar'

const PPC_PORTALS = [
  {
    slug: 'ppc-data/upload',
    name: 'Master Upload',
    icon: '📤',
    description: 'Upload foundation master files — item master, BOM, machine, capacity, and more.',
    status: 'live',
  },
  {
    slug: 'ppc-data/browse',
    name: 'Data Browser',
    icon: '🔍',
    description: 'Browse any loaded table — masters, ERP feeds, demand, MPS. Search and verify.',
    status: 'live',
  },
  {
    slug: 'ppc-data/feeds',
    name: 'Feed Status',
    icon: '📡',
    description: 'Monitor all 17 ERP feeds and master uploads — last pull, row counts, errors.',
    status: 'live',
  },
  {
    slug: 'ppc-data/demand',
    name: 'Demand Freeze',
    icon: '🔒',
    description: 'Freeze initial demand for the month, upload additions and reductions. Rule 3.',
    status: 'live',
  },
  {
    slug: 'ppc-data/mps',
    name: 'MPS Upload',
    icon: '📋',
    description: 'Upload the MPS schedule, history, and planning calendar from MpsSS.',
    status: 'live',
  },
  {
    slug: 'ppc-data/r3ss',
    name: 'R3SS Plan',
    icon: '📊',
    description: 'Upload R3 SS.xlsx — the production plan with day-wise columns. Rule 1: one plan table.',
    status: 'live',
  },
  {
    slug: 'ppc-data/feasibility',
    name: 'Feasibility & Release',
    icon: '🚦',
    description: 'Run capacity / machine / EBQ checks on the plan. Approve and release to shop floor. Rule 5.',
    status: 'live',
  },
  {
    slug: 'ppc-data/material',
    name: 'Material Planning',
    icon: '🧱',
    description: 'BOM explosion + stock allocation. Day-wise RM/CP/PM requirements and shortage flags.',
    status: 'live',
  },
  {
    slug: 'ppc-data/production',
    name: 'Production & Feedback',
    icon: '🏭',
    description: 'Daily production entry, rejection logging, plan adherence scorecard.',
    status: 'live',
  },
  {
    slug: 'ppc',
    name: 'RM CP Packing Upload',
    icon: '📦',
    description: 'Upload RM CP Packing material planning file (existing flow → Google Sheet).',
    status: 'live',
  },
  {
    slug: 'ppc-forecast',
    name: 'PPC Forecast',
    icon: '📈',
    description: 'Upload the PPC forecast file for the S&OP cycle.',
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
