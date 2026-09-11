import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, getCachedApiData, setCachedApiData } from '../api/client'
import { addSystemLanguage, fetchSystemLanguages, removeSystemLanguage } from '../api/systemLanguages'
import { useAuth } from '../auth/AuthContext'
import { homePathForRole } from '../auth/homePath'
import { ExpertLogoutButton } from '../components/ExpertLogoutButton'

export function SystemLanguagesPage() {
  const { user } = useAuth()
  const cachedLanguages = getCachedApiData<{ languages: string[] }>('/api/v1/system-languages')
  const [languages, setLanguages] = useState<string[]>(cachedLanguages?.languages ?? [])
  const [code, setCode] = useState('')
  const [loading, setLoading] = useState(!cachedLanguages)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const useStandaloneShell = user?.role === 'expert' || user?.role === 'admin'
  const backPath = homePathForRole(user?.role)

  const load = useCallback(() => {
    const cached = getCachedApiData<{ languages: string[] }>('/api/v1/system-languages')
    if (cached) {
      setLanguages(cached.languages)
    }
    setLoading(!cached)
    return fetchSystemLanguages()
      .then((data) => setLanguages(data.languages))
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : 'Failed to load languages')
      })
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  async function handleAdd(event: FormEvent) {
    event.preventDefault()
    setError('')
    try {
      const result = await addSystemLanguage(code.trim())
      setLanguages(result.languages)
      setCachedApiData('/api/v1/system-languages', { languages: result.languages })
      setCode('')
      setMessage('Language added.')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not add language')
    }
  }

  async function handleRemove(language: string) {
    if (!window.confirm(`Remove language "${language}"?`)) {
      return
    }
    setError('')
    try {
      const result = await removeSystemLanguage(language)
      setLanguages(result.languages)
      setCachedApiData('/api/v1/system-languages', { languages: result.languages })
      setMessage('Language removed.')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not remove language')
    }
  }

  if (loading) {
    return (
      <div className={useStandaloneShell ? 'expert-standalone-page' : undefined}>
        <p className="loading-message">Loading System Languages…</p>
      </div>
    )
  }

  return (
    <div className={useStandaloneShell ? 'expert-standalone-page' : undefined}>
      {useStandaloneShell ? (
        <div className="expert-standalone-toolbar">
          <Link to={backPath} className="expert-standalone-back">
            ← Back
          </Link>
        </div>
      ) : null}
      <section className="panel">
        <h2>System Languages</h2>
        <p className="hint">Manage language codes available across the system.</p>
        {error ? <p className="error-message">{error}</p> : null}
        {message ? <p className="success-message">{message}</p> : null}

        <form className="mutation-form" onSubmit={handleAdd}>
          <label htmlFor="language-code">Add language code</label>
          <input
            id="language-code"
            value={code}
            onChange={(event) => setCode(event.target.value)}
            placeholder="e.g. eng"
            required
          />
          <button type="submit">Add language</button>
        </form>

        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Code</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {languages.map((language) => (
                <tr key={language}>
                  <td>{language}</td>
                  <td>
                    <button type="button" className="link-button" onClick={() => handleRemove(language)}>
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      {useStandaloneShell ? (
        <div className="expert-standalone-logout">
          <ExpertLogoutButton />
        </div>
      ) : null}
    </div>
  )
}
