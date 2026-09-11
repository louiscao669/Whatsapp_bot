import { Link, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import {
  ADMIN_EXPORT_SUBTABS,
  ADMIN_EXPORT_TAB,
  ADMIN_MAIN_TABS,
} from '../adminWorkbench'
import { ExpertLogoutButton } from './ExpertLogoutButton'

export function AdminWorkbenchLayout() {
  const { user } = useAuth()
  const location = useLocation()

  function isTabActive(prefix: string) {
    return location.pathname === prefix || location.pathname.startsWith(`${prefix}/`)
  }

  return (
    <div className="review-workbench">
      <aside
        className="review-workbench-sidebar review-workbench-sidebar-admin"
        aria-label="Admin navigation"
      >
        <div className="review-workbench-sidebar-brand">Admin</div>
        <nav className="review-workbench-tabs review-workbench-main-tabs" aria-label="Admin sections">
          {ADMIN_MAIN_TABS.map((tab) => (
            <div key={tab.path}>
              <Link
                to={tab.path}
                className={
                  isTabActive(tab.prefix) ? 'review-workbench-tab active' : 'review-workbench-tab'
                }
              >
                {tab.label}
              </Link>
            </div>
          ))}
        </nav>

        <nav
          className="review-workbench-tabs review-workbench-export-tabs"
          aria-label="Export sections"
        >
          <div>
            <Link
              to={ADMIN_EXPORT_TAB.path}
              className={
                isTabActive(ADMIN_EXPORT_TAB.prefix)
                  ? 'review-workbench-tab active'
                  : 'review-workbench-tab'
              }
            >
              {ADMIN_EXPORT_TAB.label}
            </Link>
            <div className="review-workbench-subtabs">
              {ADMIN_EXPORT_SUBTABS.map((subtab) => (
                <Link
                  key={subtab.path}
                  to={subtab.path}
                  className={
                    location.pathname === subtab.path
                      ? 'review-workbench-subtab active'
                      : 'review-workbench-subtab'
                  }
                >
                  {subtab.label}
                </Link>
              ))}
            </div>
          </div>
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
