import { Link, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { ExpertLogoutButton } from './ExpertLogoutButton'
import { REVIEW_WORKBENCH_TABS } from '../reviewWorkbench'

export function ReviewWorkbenchLayout() {
  const { user } = useAuth()
  const location = useLocation()

  function isTabActive(path: string) {
    return location.pathname === path || location.pathname.startsWith(`${path}/`)
  }

  return (
    <div className="review-workbench">
      <aside className="review-workbench-sidebar" aria-label="Expert navigation">
        <div className="review-workbench-sidebar-brand">Expert</div>
        <nav className="review-workbench-tabs">
          {REVIEW_WORKBENCH_TABS.map((tab) => (
            <Link
              key={tab.path}
              to={tab.path}
              className={isTabActive(tab.path) ? 'review-workbench-tab active' : 'review-workbench-tab'}
            >
              {tab.label}
            </Link>
          ))}
        </nav>
        <div className="review-workbench-sidebar-footer">
          <span className="review-workbench-user">
            {user?.display_name || user?.email || user?.role}
          </span>
          <ExpertLogoutButton />
        </div>
      </aside>
      <div className="review-workbench-main">
        <div className="review-workbench-toolbar">
          <Link to="/system-languages" className="review-workbench-toolbar-link">
            System Languages
          </Link>
        </div>
        <div className="review-workbench-content">
          <Outlet />
        </div>
      </div>
    </div>
  )
}
