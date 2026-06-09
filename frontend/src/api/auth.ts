import { apiFetch } from './client'

export type NavPage = {
  label: string
  path: string
}

export type AuthUser = {
  role: string
  email: string | null
  display_name: string | null
}

export type MeResponse = {
  ok: true
  user: AuthUser
  nav: {
    spa: NavPage[]
    exports: NavPage[]
  }
}

export function fetchMe() {
  return apiFetch<MeResponse>('/api/v1/auth/me')
}

export function requestOtp(email: string) {
  return apiFetch<{ ok: true; email: string; message: string }>('/api/v1/auth/otp/request', {
    method: 'POST',
    body: JSON.stringify({ email }),
  })
}

export function verifyOtp(email: string, code: string) {
  return apiFetch<MeResponse>('/api/v1/auth/otp/verify', {
    method: 'POST',
    body: JSON.stringify({ email, code }),
  })
}

export function loginWithToken(token: string) {
  return apiFetch<MeResponse>('/api/v1/auth/token', {
    method: 'POST',
    body: JSON.stringify({ token }),
  })
}

export function logout() {
  return apiFetch<{ ok: true }>('/api/v1/auth/logout', { method: 'POST' })
}
