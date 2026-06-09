import { useAuth } from '../auth/AuthContext'

type ExpertLogoutButtonProps = {
  className?: string
}

export function ExpertLogoutButton({ className }: ExpertLogoutButtonProps) {
  const { logout } = useAuth()

  return (
    <button
      type="button"
      className={className ? `expert-logout-button ${className}` : 'expert-logout-button'}
      onClick={() => logout()}
    >
      Log out
    </button>
  )
}
