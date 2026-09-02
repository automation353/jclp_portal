import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'
import BrandLogo from '../components/BrandLogo'
import { homeRouteFor } from '../roleHome'

export default function Landing() {
  const navigate = useNavigate()
  const { user } = useAuth()

  // Already signed in? Send Sales/Ops straight to their own dashboard rather
  // than showing them the generic launcher (Change instruction 1).
  const openCompany = () => navigate(user ? homeRouteFor(user) : '/login')

  return (
    <section className="screen">
      <div className="landing-hero">
        <div className="launcher">
          <div className="logo-wrap">
            <BrandLogo variant="launcher" />
          </div>
          <h1>Enterprise Portal</h1>
          <div className="muted">Select your organisation</div>
          <button className="company-btn" onClick={openCompany}>
            <span>JCPL — Jolly Clamps Pvt. Ltd.</span>
            <span className="arrow">→</span>
          </button>
          <div className="muted">Stainless-Steel Clamps &amp; Couplings · Mumbai</div>
        </div>
      </div>
    </section>
  )
}
