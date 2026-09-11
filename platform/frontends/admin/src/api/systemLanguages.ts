import { apiFetch } from './client'

export function fetchSystemLanguages() {
  return apiFetch<{ languages: string[] }>('/api/v1/system-languages')
}

export function addSystemLanguage(code: string) {
  return apiFetch<{ ok: true; languages: string[] }>('/api/v1/system-languages', {
    method: 'POST',
    body: JSON.stringify({ code }),
  })
}

export function removeSystemLanguage(code: string) {
  return apiFetch<{ ok: true; languages: string[] }>(
    `/api/v1/system-languages/${encodeURIComponent(code)}`,
    { method: 'DELETE' },
  )
}
