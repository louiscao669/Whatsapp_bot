import { Navigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { homePathForRole } from '../auth/homePath'

export function HomeRedirect() {
  const { user, loading } = useAuth()

  if (loading) {
    return <p className="loading-message">Loading…</p>
  }

  return <Navigate to={homePathForRole(user?.role)} replace />
}
