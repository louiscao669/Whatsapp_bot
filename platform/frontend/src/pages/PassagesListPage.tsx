import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import { fetchPassageItems, type PassageItem } from '../api/passages'
import { PassageImportPanel } from '../components/PassageImportPanel'

export function PassagesListPage() {
  const [items, setItems] = useState<PassageItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [showImport, setShowImport] = useState(false)

  const loadItems = useCallback(() => {
    setError('')
    return fetchPassageItems()
      .then(({ items: loadedItems }) => setItems(loadedItems))
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : 'Failed to load passages'),
      )
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    loadItems()
  }, [loadItems])

  if (loading) return <p className="loading-message">Loading passages…</p>

  return (
    <section className="panel">
      <div className="panel-heading-row">
        <h2>Passages</h2>
        <button
          type="button"
          className="btn-primary"
          onClick={() => setShowImport((current) => !current)}
        >
          {showImport ? 'Close import' : '+ Import passages'}
        </button>
      </div>
      <p className="hint">Available passage translations by language and chapter.</p>
      {error ? <p className="error-message">{error}</p> : null}
      {message ? <p className="success-message">{message}</p> : null}

      {showImport ? (
        <div className="panel-import-drawer">
          <PassageImportPanel
            onImported={(successMessage) => {
              setMessage(successMessage)
              setShowImport(false)
              loadItems()
            }}
          />
        </div>
      ) : null}

      {items.length === 0 ? (
        <p>No passages found.</p>
      ) : (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Language</th>
                <th>Translation</th>
                <th>Chapter</th>
                <th>Verse count</th>
                <th>Available verses</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={`${item.id}-${item.chapter_number}`}>
                  <td>{item.language}</td>
                  <td>{item.translation_name ?? 'Unnamed'}</td>
                  <td>{item.chapter_number}</td>
                  <td>{item.verse_count}</td>
                  <td>{item.verses}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
