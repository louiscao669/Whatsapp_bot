import { useState, type KeyboardEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApiResource } from '../hooks/useApiResource'
import { fetchPassageItems, type PassageItem } from '../api/passages'
import { PassageImportPanel } from '../components/PassageImportPanel'

export function PassagesListPage() {
  const navigate = useNavigate()
  const { data, loading, error, reload: loadItems } = useApiResource(
    '/api/v1/passages', fetchPassageItems, null, 'Failed to load passages',
  )
  const items = data?.items ?? []
  const [message, setMessage] = useState('')
  const [showImport, setShowImport] = useState(false)

  function open(item: PassageItem) {
    navigate(`/passages/${encodeURIComponent(item.id)}/${item.chapter_number}`)
  }

  function handleRowKeyDown(event: KeyboardEvent<HTMLTableRowElement>, item: PassageItem) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      open(item)
    }
  }

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
                <th>Book</th>
                <th>Chapter</th>
                <th>Verse count</th>
                <th>Available verses</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr
                  key={`${item.id}-${item.chapter_number}`}
                  className="data-table-row-clickable"
                  tabIndex={0}
                  role="link"
                  aria-label={`Open ${item.translation_name ?? 'unnamed translation'}, chapter ${item.chapter_number}`}
                  onClick={() => open(item)}
                  onKeyDown={(event) => handleRowKeyDown(event, item)}
                >
                  <td>{item.language}</td>
                  <td>{item.translation_name ?? 'Unnamed'}</td>
                  <td style={{ textTransform: 'capitalize' }}>{item.book}</td>
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
