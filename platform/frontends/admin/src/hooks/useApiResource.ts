import { useCallback, useEffect, useRef, useState, type SetStateAction } from 'react'
import { ApiError } from '../api/client'

/** Keep cached data visible while loading, and ignore superseded requests. */
export function useApiResource<T>(
  key: string,
  load: () => Promise<T>,
  initialData: T | null,
  fallbackMessage: string,
  notFoundMessage?: string,
) {
  const [state, setState] = useState(() => ({
    key,
    data: initialData,
    loading: initialData === null,
    error: '',
  }))
  const generation = useRef({ key, id: 0 })

  // A different route/filter gets its own cached data before children render.
  if (state.key !== key) {
    setState({ key, data: initialData, loading: initialData === null, error: '' })
  }

  const request = useCallback(() => {
    generation.current.key = key
    const current = ++generation.current.id
    return load().then(
      (data) => {
        if (current === generation.current.id) {
          setState((previous) => previous.key === key
            ? { key, data, loading: false, error: '' }
            : previous)
        }
      },
      (error: unknown) => {
        if (current === generation.current.id) {
          const message = error instanceof ApiError
            ? (error.status === 404 && notFoundMessage) || error.message
            : fallbackMessage
          setState((previous) => previous.key === key
            ? { ...previous, loading: false, error: message }
            : previous)
        }
      },
    )
  }, [key, load, fallbackMessage, notFoundMessage])

  useEffect(() => {
    const activeGeneration = generation.current
    void request()
    return () => { activeGeneration.id += 1 }
  }, [request])

  const reload = useCallback(() => {
    if (generation.current.key !== key) return Promise.resolve()
    setState((previous) => previous.key === key
      ? { ...previous, loading: previous.data === null, error: '' }
      : previous)
    return request()
  }, [key, request])

  const setData = useCallback((update: SetStateAction<T | null>) => {
    if (generation.current.key !== key) return
    // A successful mutation is newer than any pending background read.
    generation.current.id += 1
    setState((previous) => previous.key === key
      ? {
          ...previous,
          data: typeof update === 'function'
            ? (update as (data: T | null) => T | null)(previous.data)
            : update,
          loading: false,
        }
      : previous)
  }, [key])

  const setError = useCallback((error: string) => {
    setState((previous) => previous.key === key ? { ...previous, error } : previous)
  }, [key])

  return { data: state.data, loading: state.loading, error: state.error, reload, setData, setError }
}
