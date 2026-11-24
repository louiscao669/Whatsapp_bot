import { useState, type KeyboardEvent, type MouseEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { getCachedApiData } from '../api/client'
import { fetchQaItems, type QaItemRow } from '../api/qaItems'
import { QaItemsBulkPanel } from '../components/QaItemsBulkPanel'
import { QaItemsImportPanel } from '../components/QaItemsImportPanel'

import { useApiResource } from '../hooks/useApiResource'
import { filterQuestionGroups, groupQuestions, type SearchScope } from '../qaItemGroups'

const QA_ITEMS_PATH = '/api/v1/qa-items'

export function QaItemsListPage() {
  const navigate = useNavigate()
  const savedItems = getCachedApiData<{ items: QaItemRow[] }>(QA_ITEMS_PATH)
  const cachedItems = savedItems?.items.every((item) => typeof item.bank_id === 'string'
    && typeof item.is_current === 'boolean' && Array.isArray(item.mcq_choices)) ? savedItems : null
  const { data, loading, error, setError, reload: loadItems } = useApiResource(
    QA_ITEMS_PATH, fetchQaItems, cachedItems, 'Failed to load QA items',
  )
  const items = data?.items ?? []
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [message, setMessage] = useState('')
  const [showImport, setShowImport] = useState(false)
  const [bank, setBank] = useState('')
  const [query, setQuery] = useState('')
  const [scope, setScope] = useState<SearchScope>('all')
  const [searchHistory, setSearchHistory] = useState(false)

  const groups = groupQuestions(items)
  const banks = Array.from(groups.reduce((result, group) => {
    const item = group.current[0]
    if (!item) return result
    const entry = result.get(item.bank_id) || { id: item.bank_id, label: item.bank_label, count: 0 }
    entry.count += 1
    result.set(item.bank_id, entry)
    return result
  }, new Map<string, { id: string; label: string; count: number }>()).values())
    .sort((a, b) => a.label.localeCompare(b.label))
  const questionGroups = filterQuestionGroups(groups, { bank, query, scope, searchHistory })
  const visibleIds = questionGroups.flatMap((group) => group.current.map((item) => item.id))
  const visibleSelectedIds = selectedIds.filter((id) => visibleIds.includes(id))
  const allSelected = visibleIds.length > 0 && visibleSelectedIds.length === visibleIds.length

  function clearFilters() {
    setBank('')
    setQuery('')
    setScope('all')
    setSearchHistory(false)
    setSelectedIds([])
  }

  function openItem(itemId: string) {
    navigate(`/qa-items/${itemId}`)
  }

  function handleRowKeyDown(event: KeyboardEvent<HTMLTableRowElement>, itemId: string) {
    if (event.target === event.currentTarget && (event.key === 'Enter' || event.key === ' ')) {
      event.preventDefault()
      openItem(itemId)
    }
  }

  function toggleSelectAll(checked: boolean) {
    setSelectedIds(checked ? visibleIds : [])
  }

  function toggleGroup(groupIds: string[], checked: boolean) {
    setSelectedIds((current) => checked
      ? Array.from(new Set([...current, ...groupIds]))
      : current.filter((id) => !groupIds.includes(id)))
  }

  function stopRowNavigation(event: MouseEvent) {
    event.stopPropagation()
  }

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

      <div className="qa-list-filters" role="search" aria-label="Search questions">
        <label>
          Question bank
          <select value={bank} onChange={(event) => { setBank(event.target.value); setSelectedIds([]) }}>
            <option value="">All banks ({groups.length})</option>
            {banks.map((entry) => (
              <option key={entry.id} value={entry.id}>{entry.label} ({entry.count})</option>
            ))}
          </select>
        </label>
        <label className="qa-search-input">
          Search
          <input
            type="search"
            value={query}
            placeholder="Search question, answer, or option text…"
            onChange={(event) => { setQuery(event.target.value); setSelectedIds([]) }}
          />
        </label>
        <label>
          Search in
          <select value={scope} onChange={(event) => { setScope(event.target.value as SearchScope); setSelectedIds([]) }}>
            <option value="all">Questions, answers & options</option>
            <option value="question">Questions</option>
            <option value="answer">Answers</option>
            <option value="options">MCQ options</option>
          </select>
        </label>
        <label className="qa-search-history">
          <input type="checkbox" checked={searchHistory} onChange={(event) => {
            setSearchHistory(event.target.checked); setSelectedIds([])
          }} />
          Search previous versions
        </label>
        {bank || query || scope !== 'all' || searchHistory ? (
          <button type="button" className="link-button" onClick={clearFilters}>Clear filters</button>
        ) : null}
      </div>
      <p className="hint" role="status">
        {questionGroups.length} of {groups.length} questions shown. Current forms appear first; older revisions are under Version history.
      </p>

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
        selectedIds={visibleSelectedIds}
        onComplete={(successMessage) => {
          setMessage(successMessage)
          setSelectedIds([])
          loadItems()
        }}
        onError={setError}
        onClearSelection={() => setSelectedIds([])}
      />

      {items.length === 0 ? (
        <p>No QA items found.</p>
      ) : questionGroups.length === 0 ? (
        <p>No questions match these filters. Try another search or <button type="button" className="link-button" onClick={clearFilters}>clear filters</button>.</p>
      ) : (
        <>
          <p className="hint">Click a row to open detail.</p>
          <div className="table-wrap">
            <table className="data-table qa-questions-table">
              <thead>
                <tr>
                  <th>
                    <input
                      type="checkbox"
                      aria-label="Select all visible current forms"
                      checked={allSelected}
                      onChange={(e) => toggleSelectAll(e.target.checked)}
                      onClick={stopRowNavigation}
                    />
                  </th>
                  <th>Question bank</th>
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
                {questionGroups.map((group) => {
                  const forms = group.current
                  const item = forms.find((form) => form.question_type === form.automatic_form) || forms[0]
                  if (!item) return null
                  const groupIds = forms.map((form) => form.id)
                  const groupSelected = groupIds.every((id) => selectedIds.includes(id))
                  const allVersions = [...forms, ...group.history]
                  const historyMatch = group.matches.some((match) => !match.item.is_current)
                  return (
                  <tr
                    key={group.key}
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
                        aria-label={`Select current forms for ${item.bank_label}: ${item.question}`}
                        checked={groupSelected}
                        onChange={(e) => toggleGroup(groupIds, e.target.checked)}
                      />
                    </td>
                    <td className="qa-bank-cell">{item.bank_label}</td>
                    <td>{item.passage}</td>
                    <td className="question-cell">
                      {item.question}
                      {group.matches.filter((match) => match.label !== 'Question' || !match.item.is_current)
                        .map((match) => (
                          <p className="qa-search-match" key={`${match.item.id}:${match.label}`}>
                            <strong>{!match.item.is_current ? 'Previous version · ' : ''}{match.label}:</strong> {match.text}
                          </p>
                        ))}
                    </td>
                    <td onClick={stopRowNavigation}>
                      <div className="qa-form-list">
                        {forms.map((form) => (
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
                      {group.history.length ? (
                        <details className="qa-version-history" open={historyMatch || undefined}>
                          <summary>Version history ({group.history.length})</summary>
                          {group.history.map((form) => (
                            <div key={form.id}>
                              <button type="button" className="qa-form-chip" onClick={() => openItem(form.id)}>
                                {form.question_type.toUpperCase()} · previous · {new Date(form.created_at).toLocaleDateString()}
                              </button>
                              <p>{form.question}</p>
                            </div>
                          ))}
                        </details>
                      ) : null}
                    </td>
                    <td>{Array.from(new Set(forms.map((form) => form.review_status))).join(' / ')}</td>
                    <td title="Across current and previous versions in this bank">{allVersions.reduce((sum, form) => sum + form.response_count, 0)}</td>
                    <td title="Across current and previous versions in this bank">{allVersions.reduce((sum, form) => sum + form.flagged_count, 0)}</td>
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
