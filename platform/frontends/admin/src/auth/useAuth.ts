import { createContext, useContext } from 'react'
import type { AuthUser, MeResponse, NavPage } from '../api/auth'

type AuthState = {
  user: AuthUser | null
  nav: NavPage[]
  exports: NavPage[]
  loading: boolean
  refresh: () => Promise<void>
  sendCode: (email: string) => Promise<string>
  verifyCode: (email: string, code: string) => Promise<MeResponse>
  tokenLogin: (token: string) => Promise<MeResponse>
  logout: () => Promise<void>
}

export const AuthContext = createContext<AuthState | null>(null)

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return context
}
