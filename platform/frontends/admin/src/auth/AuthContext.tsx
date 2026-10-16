import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { AuthContext } from './useAuth'
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
    let cancelled = false
    fetchMe()
      .then((data) => {
        if (!cancelled) applySession(setUser, setNav, setExports, data)
      })
      .catch(() => {
        if (cancelled) return
        setUser(null)
        setNav([])
        setExports([])
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

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
