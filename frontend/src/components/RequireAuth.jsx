import { Navigate } from 'react-router-dom'
import { useAuth } from '../auth'

export default function RequireAuth({ children }) {
  const { user, loading } = useAuth()

  // Hold the render until the session check finishes, otherwise a refresh on a
  // protected page would flash the login screen before restoring the session.
  if (loading) return null
  if (!user) return <Navigate to="/login" replace />
  return children
}
