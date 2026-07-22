import { Fragment, useCallback, useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import {
  fetchPassageDetail,
  fetchPassageItems,
  type PassageDetail,
  type PassageItem,
} from '../api/passages'
import { PassageImportPanel } from '../components/PassageImportPanel'

const rowKey = (item: Pick<PassageItem, 'id' | 'chapter_number'>) =>
  `${item.id}-${item.chapter_number}`

function formatTimestamp(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

export function PassagesListPage() {
  const [items, setItems] = useState<PassageItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [showImport, setShowImport] = useState(false)

  const [expandedKey, setExpandedKey] = useState<string | null>(null)
  const [details, setDetails] = useState<Record<string, PassageDetail>>({})
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState('')

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

  const toggleRow = useCallback(
    (item: PassageItem) => {
      const key = rowKey(item)
      setDetailError('')
      if (expandedKey === key) {
        setExpandedKey(null)
        return
      }
      setExpandedKey(key)
      if (!details[key]) {
        setDetailLoading(true)
        fetchPassageDetail(item.id, item.chapter_number)
          .then((detail) => setDetails((current) => ({ ...current, [key]: detail })))
          .catch((err) =>
            setDetailError(
              err instanceof ApiError ? err.message : 'Failed to load passage detail',
            ),
          )
          .finally(() => setDetailLoading(false))
      }
    },
    [expandedKey, details],
  )

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
      <p className="hint">
        Available passage translations by language and chapter. Click a row to view its verse
        text and metadata.
      </p>
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
                <th aria-label="Expand" style={{ width: '2rem' }} />
                <th>Language</th>
                <th>Translation</th>
                <th>Chapter</th>
                <th>Verse count</th>
                <th>Available verses</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => {
                const key = rowKey(item)
                const isOpen = expandedKey === key
                const detail = details[key]
                return (
                  <Fragment key={key}>
                    <tr
                      className="clickable-row"
                      style={{ cursor: 'pointer' }}
                      onClick={() => toggleRow(item)}
                      aria-expanded={isOpen}
                    >
                      <td aria-hidden>{isOpen ? '▾' : '▸'}</td>
                      <td>{item.language}</td>
                      <td>{item.translation_name ?? 'Unnamed'}</td>
                      <td>{item.chapter_number}</td>
                      <td>{item.verse_count}</td>
                      <td>{item.verses}</td>
                    </tr>
                    {isOpen ? (
                      <tr className="detail-row">
                        <td colSpan={6}>
                          {detailLoading && !detail ? (
                            <p className="loading-message">Loading verses…</p>
                          ) : detailError && !detail ? (
                            <p className="error-message">{detailError}</p>
                          ) : detail ? (
                            <div className="passage-detail">
                              <dl className="passage-detail-meta">
                                <div>
                                  <dt>Translation</dt>
                                  <dd>{detail.translation_name ?? 'Unnamed'}</dd>
                                </div>
                                <div>
                                  <dt>Language</dt>
                                  <dd>{detail.language}</dd>
                                </div>
                                <div>
                                  <dt>Chapter</dt>
                                  <dd>{detail.chapter_number}</dd>
                                </div>
                                <div>
                                  <dt>Verses</dt>
                                  <dd>{detail.verse_count}</dd>
                                </div>
                                <div>
                                  <dt>Created</dt>
                                  <dd>{formatTimestamp(detail.created_at)}</dd>
                                </div>
                                <div>
                                  <dt>Updated</dt>
                                  <dd>{formatTimestamp(detail.updated_at)}</dd>
                                </div>
                              </dl>
                              <table className="data-table passage-verse-table">
                                <thead>
                                  <tr>
                                    <th style={{ width: '4rem' }}>Verse</th>
                                    <th>Text</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {detail.verses.map((verse) => (
                                    <tr key={verse.verse_number}>
                                      <td>{verse.verse_number}</td>
                                      <td>{verse.text}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          ) : null}
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
