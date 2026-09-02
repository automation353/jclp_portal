import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'
import BrandLogo from './BrandLogo'
import NotificationBell from './NotificationBell'

/**
 * @param subtitle the small second line under "Enterprise Portal" — the
 *   prototype uses it as a location indicator ("Purchase › RM Requirement").
 */
export default function TopBar({ subtitle = 'Jolly Clamps Pvt. Ltd.' }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  async function handleLogout() {
    await logout()
    navigate('/', { replace: true })
  }

  return (
    <div className="topbar">
      <BrandLogo variant="topbar" />
      <div className="brand">
        Enterprise Portal
        <small>{subtitle}</small>
      </div>
      <div className="spacer" />
      {user && <NotificationBell />}
      {user && <div className="userchip">👤 {user.username}</div>}
      <button className="logout" onClick={handleLogout}>Logout</button>
    </div>
  )
}
