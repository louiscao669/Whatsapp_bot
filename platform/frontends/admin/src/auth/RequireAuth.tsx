import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from './AuthContext'

export function RequireAuth({ children, roles }: { children: React.ReactNode; roles?: string[] }) {
  const { user, loading } = useAuth()
  const location = useLocation()

  if (loading) {
    return <p className="loading-message">Checking session…</p>
  }

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }

  const normalizedRole = user.role?.trim().toLowerCase()
  if (roles && (!normalizedRole || !roles.includes(normalizedRole))) {
    return <p className="error-message">You do not have access to this page.</p>
  }

  return children
}
