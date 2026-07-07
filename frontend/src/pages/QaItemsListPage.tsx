import { useCallback, useEffect, useState, type KeyboardEvent, type MouseEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, getCachedApiData } from '../api/client'
import { fetchQaItems, type QaItemRow } from '../api/qaItems'
import { QaItemsBulkPanel } from '../components/QaItemsBulkPanel'

const QA_ITEMS_PATH = '/api/v1/qa-items'

export function QaItemsListPage() {
  const navigate = useNavigate()
  const cachedItems = getCachedApiData<{ items: QaItemRow[] }>(QA_ITEMS_PATH)
  const [items, setItems] = useState<QaItemRow[]>(cachedItems?.items ?? [])
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [loading, setLoading] = useState(!cachedItems)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const loadItems = useCallback(() => {
    setLoading((current) => current && items.length === 0)
    setError('')
    return fetchQaItems()
      .then((data) => setItems(data.items))
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : 'Failed to load QA items')
      })
      .finally(() => setLoading(false))
  }, [items.length])

  useEffect(() => {
    loadItems()
  }, [loadItems])

  function openItem(itemId: string) {
    navigate(`/qa-items/${itemId}`)
  }

  function handleRowKeyDown(event: KeyboardEvent<HTMLTableRowElement>, itemId: string) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      openItem(itemId)
    }
  }

  function toggleSelected(itemId: string, checked: boolean) {
    setSelectedIds((current) => {
      if (checked) {
        return current.includes(itemId) ? current : [...current, itemId]
      }
      return current.filter((id) => id !== itemId)
    })
  }

  function toggleSelectAll(checked: boolean) {
    setSelectedIds(checked ? items.map((item) => item.id) : [])
  }

  function stopRowNavigation(event: MouseEvent) {
    event.stopPropagation()
  }

  const allSelected = items.length > 0 && selectedIds.length === items.length

  if (loading) {
    return <p className="loading-message">Loading QA items…</p>
  }

  return (
    <section className="panel">
      <h2>QAs</h2>
      {error ? <p className="error-message">{error}</p> : null}
      {message ? <p className="success-message">{message}</p> : null}

      <QaItemsBulkPanel
        selectedIds={selectedIds}
        onComplete={(successMessage) => {
          setMessage(successMessage)
          loadItems()
        }}
        onError={setError}
        onClearSelection={() => setSelectedIds([])}
      />

      {items.length === 0 ? (
        <p>No QA items found.</p>
      ) : (
        <>
          <p className="hint">Click a row to open detail.</p>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>
                    <input
                      type="checkbox"
                      aria-label="Select all QA items"
                      checked={allSelected}
                      onChange={(e) => toggleSelectAll(e.target.checked)}
                      onClick={stopRowNavigation}
                    />
                  </th>
                  <th>Passage</th>
                  <th>Question</th>
                  <th>Type</th>
                  <th>Review</th>
                  <th>Responses</th>
                  <th>Flagged</th>
                  <th>Avg score</th>
                  <th>Min responses</th>
                  <th>Priority</th>
                  <th>Active</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr
                    key={item.id}
                    className="data-table-row-clickable"
                    tabIndex={0}
                    role="link"
                    aria-label={`Open ${item.passage}: ${item.question}`}
                    onClick={() => openItem(item.id)}
                    onKeyDown={(event) => handleRowKeyDown(event, item.id)}
                  >
                    <td onClick={stopRowNavigation}>
                      <input
                        type="checkbox"
                        aria-label={`Select ${item.passage}`}
                        checked={selectedIds.includes(item.id)}
                        onChange={(e) => toggleSelected(item.id, e.target.checked)}
                      />
                    </td>
                    <td>{item.passage}</td>
                    <td className="question-cell">{item.question}</td>
                    <td>{item.question_type}</td>
                    <td>{item.review_status}</td>
                    <td>{item.response_count}</td>
                    <td>{item.flagged_count}</td>
                    <td>{item.average_score ?? '—'}</td>
                    <td>{item.min_responses_required}</td>
                    <td>{item.review_priority}</td>
                    <td>{item.active ? 'Yes' : 'No'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  )
}
