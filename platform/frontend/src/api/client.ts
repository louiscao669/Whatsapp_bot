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

const responseCache = new Map<string, unknown>()
const pendingRequests = new Map<string, Promise<unknown>>()
const STORAGE_PREFIX = 'admin_api_cache:'

function requestMethod(init: RequestInit) {
  return String(init.method || 'GET').toUpperCase()
}

function cacheKey(path: string) {
  return path
}

function canCacheGet(path: string) {
  return !path.startsWith('/api/v1/auth/')
}

function cloneCachedValue<T>(value: T): T {
  if (
    typeof structuredClone === 'function'
    && value !== null
    && typeof value === 'object'
  ) {
    return structuredClone(value)
  }
  return value
}

function storageKey(key: string) {
  return `${STORAGE_PREFIX}${key}`
}

function readStoredCache<T>(key: string): T | null {
  if (typeof window === 'undefined') {
    return null
  }
  try {
    const raw = window.sessionStorage.getItem(storageKey(key))
    if (!raw) {
      return null
    }
    return JSON.parse(raw) as T
  } catch {
    return null
  }
}

function writeStoredCache<T>(key: string, value: T) {
  if (typeof window === 'undefined') {
    return
  }
  try {
    window.sessionStorage.setItem(storageKey(key), JSON.stringify(value))
  } catch {
    // In-memory caching still works if storage is unavailable or full.
  }
}

function deleteStoredCache(key: string) {
  if (typeof window === 'undefined') {
    return
  }
  try {
    window.sessionStorage.removeItem(storageKey(key))
  } catch {
    // Ignore storage failures; the memory cache is already authoritative.
  }
}

function storedCacheKeys() {
  if (typeof window === 'undefined') {
    return []
  }
  const keys: string[] = []
  try {
    for (let index = 0; index < window.sessionStorage.length; index += 1) {
      const key = window.sessionStorage.key(index)
      if (key?.startsWith(STORAGE_PREFIX)) {
        keys.push(key.slice(STORAGE_PREFIX.length))
      }
    }
  } catch {
    return []
  }
  return keys
}

function matchesCacheKey(key: string, match: string | RegExp | ((key: string) => boolean)) {
  return typeof match === 'string'
    ? key.startsWith(match)
    : match instanceof RegExp
      ? match.test(key)
      : match(key)
}

export function getCachedApiData<T>(path: string): T | null {
  const key = cacheKey(path)
  if (responseCache.has(key)) {
    return cloneCachedValue(responseCache.get(key) as T)
  }
  if (!canCacheGet(path)) {
    return null
  }
  const stored = readStoredCache<T>(key)
  if (stored !== null) {
    responseCache.set(key, cloneCachedValue(stored))
    return cloneCachedValue(stored)
  }
  return null
}

export function setCachedApiData<T>(path: string, value: T) {
  const key = cacheKey(path)
  responseCache.set(key, cloneCachedValue(value))
  if (canCacheGet(path)) {
    writeStoredCache(key, value)
  }
}

export function clearApiCache(match?: string | RegExp | ((key: string) => boolean)) {
  if (!match) {
    responseCache.clear()
    pendingRequests.clear()
    for (const key of storedCacheKeys()) {
      deleteStoredCache(key)
    }
    return
  }
  for (const key of responseCache.keys()) {
    if (matchesCacheKey(key, match)) {
      responseCache.delete(key)
    }
  }
  for (const key of pendingRequests.keys()) {
    if (matchesCacheKey(key, match)) {
      pendingRequests.delete(key)
    }
  }
  for (const key of storedCacheKeys()) {
    if (matchesCacheKey(key, match)) {
      deleteStoredCache(key)
    }
  }
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = requestMethod(init)
  const isCacheable = method === 'GET' && canCacheGet(path)
  const key = cacheKey(path)

  if (isCacheable && responseCache.has(key)) {
    return cloneCachedValue(responseCache.get(key) as T)
  }
  if (isCacheable) {
    const stored = readStoredCache<T>(key)
    if (stored !== null) {
      responseCache.set(key, cloneCachedValue(stored))
      return cloneCachedValue(stored)
    }
  }
  if (isCacheable && pendingRequests.has(key)) {
    return cloneCachedValue(await pendingRequests.get(key) as T)
  }

  const headers = new Headers(init.headers)
  if (init.body && !headers.has('Content-Type') && !(init.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }

  const request = fetch(path, {
    ...init,
    headers,
    credentials: 'include',
  }).then(async (response) => {
    const payload = (await response.json().catch(() => ({}))) as T & ApiEnvelope
    if (!response.ok) {
      throw new ApiError(
        payload.message ?? response.statusText,
        response.status,
        payload.error,
      )
    }
    if (isCacheable) {
      responseCache.set(key, cloneCachedValue(payload))
      writeStoredCache(key, payload)
    } else {
      clearApiCache('/api/v1/')
    }
    return payload
  }).finally(() => {
    pendingRequests.delete(key)
  })

  if (isCacheable) {
    pendingRequests.set(key, request)
  }
  return cloneCachedValue(await request)
}
