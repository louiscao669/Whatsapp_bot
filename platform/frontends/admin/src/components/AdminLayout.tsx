import { Outlet } from 'react-router-dom'

export function AdminLayout() {
  return (
    <div className="app-shell app-shell-expert">
      <Outlet />
    </div>
  )
}
