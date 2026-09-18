import { Navigate } from 'react-router-dom'
import { useAuth } from '../auth'

/**
 * Route guard that only allows super_admin users through.
 * Unauthenticated users → /login; authenticated non-super-admins → /departments.
 */
export default function RequireSuperAdmin({ children }) {
  const { user, loading } = useAuth()

  if (loading) return null
  if (!user) return <Navigate to="/login" replace />
  if (!user.is_super_admin) return <Navigate to="/departments" replace />
  return children
}
