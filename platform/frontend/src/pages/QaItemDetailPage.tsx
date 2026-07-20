import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ApiError, getCachedApiData } from '../api/client'
import { deleteQaItem, fetchQaItemDetail, type QaItemDetail } from '../api/qaItems'
import { QaItemAssignmentsTab } from './QaItemAssignmentsTab'
import { QaItemOverviewTab } from './QaItemOverviewTab'
import { QaItemResponsesTab } from './QaItemResponsesTab'
import { QaItemStatsTab } from './QaItemStatsTab'

type DetailTab = 'overview' | 'stats' | 'responses' | 'assignments'

function parseLanguagesParam(value: string | null): string[] {
  if (!value) {
    return []
  }
  return value
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean)
}

function parseTab(value: string | null): DetailTab {
  if (value === 'stats' || value === 'responses' || value === 'assignments') {
    return value
  }
  return 'overview'
}

export function QaItemDetailPage() {
  const navigate = useNavigate()
  const { qaItemId } = useParams<{ qaItemId: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  const activeTab = parseTab(searchParams.get('tab'))
  const selectedLanguages = useMemo(
    () => parseLanguagesParam(searchParams.get('languages')),
    [searchParams],
  )
  const detailPath = qaItemId ? `/api/v1/qa-items/${qaItemId}` : ''
  const cachedDetail = detailPath
    ? getCachedApiData<{ item: QaItemDetail }>(detailPath)
    : null

  const [item, setItem] = useState<QaItemDetail | null>(cachedDetail?.item ?? null)
  const [loading, setLoading] = useState(!cachedDetail)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [deleting, setDeleting] = useState(false)

  const loadItem = useCallback(() => {
    if (!qaItemId) {
      return Promise.resolve()
    }
    const cached = getCachedApiData<{ item: QaItemDetail }>(`/api/v1/qa-items/${qaItemId}`)
    if (cached) {
      setItem(cached.item)
      setLoading(false)
    } else {
      setLoading(true)
    }
    setError('')
    return fetchQaItemDetail(qaItemId)
      .then((data) => setItem(data.item))
      .catch((err) => {
        if (err instanceof ApiError && err.status === 404) {
          setError('QA item not found.')
          return
        }
        setError(err instanceof ApiError ? err.message : 'Failed to load QA item')
      })
      .finally(() => setLoading(false))
  }, [qaItemId])

  useEffect(() => {
    loadItem()
  }, [loadItem])

  function setTab(tab: DetailTab) {
    const next = new URLSearchParams(searchParams)
    next.set('tab', tab)
    setSearchParams(next)
  }

  function setLanguages(languages: string[]) {
    const next = new URLSearchParams(searchParams)
    if (languages.length) {
      next.set('languages', languages.join(','))
    } else {
      next.delete('languages')
    }
    setSearchParams(next)
  }

  async function handleDelete() {
    if (!item) {
      return
    }
    const confirmed = window.confirm(
      'Delete this question and all related assignments/responses?',
    )
    if (!confirmed) {
      return
    }
    setDeleting(true)
    setError('')
    try {
      await deleteQaItem(item.id)
      navigate('/qa-items/list')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not delete question')
      setDeleting(false)
    }
  }

  if (!qaItemId) {
    return <p className="error-message">Missing QA item id.</p>
  }

  if (loading) {
    return <p className="loading-message">Loading QA item…</p>
  }

  if (error && !item) {
    return (
      <section className="panel">
        <p className="error-message">{error}</p>
        <p>
          <Link to="/qa-items/list">← Back to QAs</Link>
        </p>
      </section>
    )
  }

  if (!item) {
    return null
  }

  const choiceScored = item.question_type === 'mcq' || item.question_type === 'tf'

  return (
    <section className="panel detail-page">
      <p className="back-link">
        <Link to="/qa-items/list">← Back to QAs</Link>
      </p>

      <div className="detail-header-row">
        <h2>{item.question_text}</h2>
        <button type="button" className="btn-danger" disabled={deleting} onClick={handleDelete}>
          Delete question
        </button>
      </div>

      {error ? <p className="error-message">{error}</p> : null}
      {message ? <p className="success-message">{message}</p> : null}

      <nav className="detail-tabs" aria-label="QA item tabs">
        {(['overview', 'stats', 'responses', 'assignments'] as DetailTab[]).map((tab) => (
          <button
            key={tab}
            type="button"
            className={activeTab === tab ? 'detail-tab active' : 'detail-tab'}
            onClick={() => setTab(tab)}
          >
            {tab === 'overview'
              ? 'Overview'
              : tab === 'stats'
                ? 'Response statistics'
                : tab === 'responses'
                  ? 'Responses'
                  : 'Assignments'}
          </button>
        ))}
      </nav>

      {activeTab === 'overview' ? (
        <QaItemOverviewTab
          item={item}
          onItemUpdated={setItem}
          onMessage={setMessage}
          onError={setError}
        />
      ) : null}

      {activeTab === 'stats' ? (
        <QaItemStatsTab
          qaItemId={item.id}
          selectedLanguages={selectedLanguages}
          onLanguagesChange={setLanguages}
        />
      ) : null}

      {activeTab === 'responses' ? (
        <QaItemResponsesTab
          qaItemId={item.id}
          languages={selectedLanguages}
          choiceScored={choiceScored}
        />
      ) : null}

      {activeTab === 'assignments' ? (
        <QaItemAssignmentsTab qaItemId={item.id} languages={selectedLanguages} />
      ) : null}
    </section>
  )
}
