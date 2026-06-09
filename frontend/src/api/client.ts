export class ApiError extends Error {
  status: number
  code?: string

  constructor(message: string, status: number, code?: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

type ApiEnvelope = {
  error?: string
  message?: string
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !headers.has('Content-Type') && !(init.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(path, {
    ...init,
    headers,
    credentials: 'include',
  })

  const payload = (await response.json().catch(() => ({}))) as T & ApiEnvelope
  if (!response.ok) {
    throw new ApiError(
      payload.message ?? response.statusText,
      response.status,
      payload.error,
    )
  }
  return payload
}
