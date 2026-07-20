import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { ApiError } from '../api/client'
import {
  fetchMe,
  logout as apiLogout,
  loginWithToken,
  requestOtp,
  verifyOtp,
  type AuthUser,
  type MeResponse,
  type NavPage,
} from '../api/auth'

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

const AuthContext = createContext<AuthState | null>(null)

function applySession(
  setUser: (u: AuthUser | null) => void,
  setNav: (n: NavPage[]) => void,
  setExports: (n: NavPage[]) => void,
  data: MeResponse,
) {
  setUser(data.user)
  setNav(data.nav.spa)
  setExports(data.nav.exports ?? [])
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [nav, setNav] = useState<NavPage[]>([])
  const [exports, setExports] = useState<NavPage[]>([])
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      const data = await fetchMe()
      applySession(setUser, setNav, setExports, data)
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setUser(null)
        setNav([])
        setExports([])
        return
      }
      throw error
    }
  }, [])

  useEffect(() => {
    refresh()
      .catch(() => {
        setUser(null)
        setNav([])
        setExports([])
      })
      .finally(() => setLoading(false))
  }, [refresh])

  const sendCode = useCallback(async (email: string) => {
    const result = await requestOtp(email)
    return result.message
  }, [])

  const verifyCode = useCallback(async (email: string, code: string) => {
    const data = await verifyOtp(email, code)
    applySession(setUser, setNav, setExports, data)
    return data
  }, [])

  const tokenLogin = useCallback(async (token: string) => {
    const data = await loginWithToken(token)
    applySession(setUser, setNav, setExports, data)
    return data
  }, [])

  const logout = useCallback(async () => {
    await apiLogout()
    setUser(null)
    setNav([])
    setExports([])
  }, [])

  const value = useMemo(
    () => ({
      user,
      nav,
      exports,
      loading,
      refresh,
      sendCode,
      verifyCode,
      tokenLogin,
      logout,
    }),
    [user, nav, exports, loading, refresh, sendCode, verifyCode, tokenLogin, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return context
}
