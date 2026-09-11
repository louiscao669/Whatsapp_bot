import { useCallback, useEffect, useState, type KeyboardEvent, type MouseEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, getCachedApiData } from '../api/client'
import { fetchQaItems, type QaItemRow } from '../api/qaItems'
import { QaItemsBulkPanel } from '../components/QaItemsBulkPanel'
import { QaItemsImportPanel } from '../components/QaItemsImportPanel'

const QA_ITEMS_PATH = '/api/v1/qa-items'

export function QaItemsListPage() {
  const navigate = useNavigate()
  const cachedItems = getCachedApiData<{ items: QaItemRow[] }>(QA_ITEMS_PATH)
  const [items, setItems] = useState<QaItemRow[]>(cachedItems?.items ?? [])
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [loading, setLoading] = useState(!cachedItems)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [showImport, setShowImport] = useState(false)

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

  function toggleSelectAll(checked: boolean) {
    setSelectedIds(checked ? items.map((item) => item.id) : [])
  }

  function toggleGroup(groupIds: string[], checked: boolean) {
    setSelectedIds((current) => checked
      ? Array.from(new Set([...current, ...groupIds]))
      : current.filter((id) => !groupIds.includes(id)))
  }

  function stopRowNavigation(event: MouseEvent) {
    event.stopPropagation()
  }

  const allSelected = items.length > 0 && selectedIds.length === items.length
  const questionGroups = Array.from(items.reduce((groups, item) => {
    const key = item.form_group_id || `${item.passage}\u0000${item.question}`
    const group = groups.get(key) || []
    group.push(item)
    groups.set(key, group)
    return groups
  }, new Map<string, QaItemRow[]>()).values())

  if (loading) {
    return <p className="loading-message">Loading QA items…</p>
  }

  return (
    <section className="panel">
      <div className="panel-heading-row">
        <h2>Questions</h2>
        <button
          type="button"
          className="btn-primary"
          onClick={() => setShowImport((current) => !current)}
        >
          {showImport ? 'Close import' : '+ Import questions'}
        </button>
      </div>
      {error ? <p className="error-message">{error}</p> : null}
      {message ? <p className="success-message">{message}</p> : null}

      {showImport ? (
        <div className="panel-import-drawer">
          <QaItemsImportPanel
            onImported={() => {
              setMessage('Import completed.')
              setShowImport(false)
              loadItems()
            }}
          />
        </div>
      ) : null}

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
                  <th>Forms</th>
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
                {questionGroups.map((forms) => {
                  const item = forms.find((form) => form.question_type === form.automatic_form) || forms[0]
                  const groupIds = forms.map((form) => form.id)
                  const groupSelected = groupIds.every((id) => selectedIds.includes(id))
                  return (
                  <tr
                    key={item.form_group_id || groupIds.join(':')}
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
                        checked={groupSelected}
                        onChange={(e) => toggleGroup(groupIds, e.target.checked)}
                      />
                    </td>
                    <td>{item.passage}</td>
                    <td className="question-cell">{item.question}</td>
                    <td onClick={stopRowNavigation}>
                      <div className="qa-form-list">
                        {forms.sort((a, b) => a.question_type.localeCompare(b.question_type)).map((form) => (
                          <button
                            type="button"
                            className={`qa-form-chip ${form.question_type === form.automatic_form ? 'automatic' : ''}`}
                            key={form.id}
                            onClick={() => openItem(form.id)}
                          >
                            {form.question_type.toUpperCase()}
                            {form.question_type === form.automatic_form ? ' · automatic' : ''}
                          </button>
                        ))}
                      </div>
                    </td>
                    <td>{Array.from(new Set(forms.map((form) => form.review_status))).join(' / ')}</td>
                    <td>{forms.reduce((sum, form) => sum + form.response_count, 0)}</td>
                    <td>{forms.reduce((sum, form) => sum + form.flagged_count, 0)}</td>
                    <td>{item.average_score ?? '—'}</td>
                    <td>{item.min_responses_required}</td>
                    <td>{item.review_priority}</td>
                    <td>{item.active ? 'Yes' : 'No'}</td>
                  </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  )
}
