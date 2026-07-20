import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ApiError, getCachedApiData } from '../api/client'
import {
  bulkReviewQaAll,
  bulkReviewQaChapter,
  fetchReviewQa,
  removeReviewQaItem,
  restoreReviewQaItem,
  returnReviewQaUnreviewed,
  type ReviewQaChapter,
  type ReviewQaItem,
  type ReviewQaTab,
} from '../api/reviewQa'
import { ReviewQaUnreviewedItem } from '../components/ReviewQaUnreviewedItem'

const TABS: { id: ReviewQaTab; label: string }[] = [
  { id: 'unreviewed', label: 'Unreviewed QAs' },
  { id: 'reviewed', label: 'Reviewed QAs' },
  { id: 'removed', label: 'Removed QAs' },
]

const CHOICE_LETTERS = ['A', 'B', 'C', 'D'] as const

function ReviewQaStandardAnswer({ item }: { item: ReviewQaItem }) {
  const questionType = item.question_type
  if (questionType === 'mcq' || questionType === 'tf') {
    const slots = item.choice_slots || (questionType === 'mcq' ? 4 : 2)
    const correct = (item.mcq_correct_choice ?? '').toUpperCase()
    return (
      <div className="review-qa-standard-answer">
        <div>Standard Answer:</div>
        {CHOICE_LETTERS.slice(0, slots).map((letter, index) => {
          const text = (item.mcq_choices[index] ?? '').trim() || '…'
          const star = letter === correct ? '*' : ''
          return (
            <div key={letter}>
              {star}
              {letter}: {text}
            </div>
          )
        })}
      </div>
    )
  }

  const answer = (item.expected_answer || '').trim() || '…'
  return <div className="review-qa-standard-answer">Standard Answer: {answer}</div>
}

export function ReviewQaPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const tab = (searchParams.get('tab') as ReviewQaTab) || 'unreviewed'
  const activeTab: ReviewQaTab = TABS.some((entry) => entry.id === tab) ? tab : 'unreviewed'
  const reviewQaPath = `/api/v1/review-qa?tab=${encodeURIComponent(activeTab)}`
  const cachedDashboard = getCachedApiData<{
    chapters: ReviewQaChapter[]
    items: ReviewQaItem[]
  }>(reviewQaPath)

  const [chapters, setChapters] = useState<ReviewQaChapter[]>(cachedDashboard?.chapters ?? [])
  const [removedItems, setRemovedItems] = useState<ReviewQaItem[]>(cachedDashboard?.items ?? [])
  const [loading, setLoading] = useState(!cachedDashboard)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const loadDashboard = useCallback((targetTab: ReviewQaTab) => {
    const cached = getCachedApiData<{
      chapters: ReviewQaChapter[]
      items: ReviewQaItem[]
    }>(`/api/v1/review-qa?tab=${encodeURIComponent(targetTab)}`)
    if (cached) {
      setChapters(cached.chapters)
      setRemovedItems(cached.items)
    }
    setLoading(!cached)
    setError('')
    return fetchReviewQa(targetTab)
      .then((data) => {
        setChapters(data.chapters)
        setRemovedItems(data.items)
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : 'Failed to load Review QA')
      })
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    loadDashboard(activeTab)
  }, [activeTab, loadDashboard])

  function setTab(nextTab: ReviewQaTab) {
    setSearchParams({ tab: nextTab })
  }

  function handleAction(nextTab: ReviewQaTab, successMessage: string) {
    setMessage(successMessage)
    setTab(nextTab)
  }

  async function handleMarkAllReviewed() {
    if (!window.confirm('Mark every unreviewed question as reviewed?')) {
      return
    }
    try {
      const result = await bulkReviewQaAll()
      handleAction(result.tab, result.message)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Bulk action failed')
    }
  }

  async function handleBulk(action: 'mark_reviewed' | 'clear_reviewed', chapter: string) {
    const confirmText =
      action === 'mark_reviewed'
        ? `Mark all questions in ${chapter} as reviewed?`
        : `Return all questions in ${chapter} to unreviewed?`
    if (!window.confirm(confirmText)) {
      return
    }
    try {
      const result = await bulkReviewQaChapter(action, chapter)
      handleAction(result.tab, result.message)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Bulk action failed')
    }
  }

  async function runItemAction(
    action: () => Promise<{ tab: ReviewQaTab; message: string }>,
  ) {
    try {
      const result = await action()
      handleAction(result.tab, result.message)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Action failed')
    }
  }

  if (loading) {
    return <p className="loading-message">Loading Review QA…</p>
  }

  return (
    <section className="panel review-qa-page">
      <h2>Review QA</h2>
      <p className="hint">
        Review question–answer pairs for accuracy and cultural appropriateness. Removed items are
        excluded from participant assignment.
      </p>
      {error ? <p className="error-message">{error}</p> : null}
      {message ? <p className="success-message">{message}</p> : null}

      <nav className="detail-tabs" aria-label="Review QA tabs">
        {TABS.map((entry) => (
          <button
            key={entry.id}
            type="button"
            className={activeTab === entry.id ? 'detail-tab active' : 'detail-tab'}
            onClick={() => setTab(entry.id)}
          >
            {entry.label}
          </button>
        ))}
      </nav>

      {activeTab === 'unreviewed' && chapters.length > 0 ? (
        <div className="review-qa-bulk-bar action-row">
          <button type="button" className="btn-success btn-sm" onClick={handleMarkAllReviewed}>
            Mark all as reviewed
          </button>
        </div>
      ) : null}

      {activeTab === 'removed' ? (
        <RemovedTable
          items={removedItems}
          onRestore={(id) =>
            runItemAction(async () => {
              const result = await restoreReviewQaItem(id)
              return { tab: result.tab, message: result.message }
            })
          }
        />
      ) : (
        <ChapterPanels
          tab={activeTab}
          chapters={chapters}
          onBulk={handleBulk}
          onItemAction={handleAction}
          onItemError={setError}
        />
      )}
    </section>
  )
}

function ChapterPanels({
  tab,
  chapters,
  onBulk,
  onItemAction,
  onItemError,
}: {
  tab: ReviewQaTab
  chapters: ReviewQaChapter[]
  onBulk: (action: 'mark_reviewed' | 'clear_reviewed', chapter: string) => void
  onItemAction: (tab: ReviewQaTab, message: string) => void
  onItemError: (message: string) => void
}) {
  if (!chapters.length) {
    const empty = {
      unreviewed: 'No unreviewed QA items.',
      reviewed: 'No reviewed QA items yet.',
      removed: 'No removed QA items.',
    }
    return <p>{empty[tab]}</p>
  }

  return (
    <>
      {chapters.map((chapter) => (
        <section key={chapter.chapter} className="review-qa-chapter">
          <div className="review-qa-chapter-header">
            <div>
              <h3>{chapter.chapter}</h3>
              <span className="detail-meta">
                {chapter.count} question{chapter.count === 1 ? '' : 's'}
              </span>
            </div>
            <div className="action-row">
              {chapter.bulk_actions.includes('mark_reviewed') ? (
                <button type="button" onClick={() => onBulk('mark_reviewed', chapter.chapter)}>
                  Mark chapter as reviewed
                </button>
              ) : null}
              {chapter.bulk_actions.includes('clear_reviewed') ? (
                <button
                  type="button"
                  className="btn-success btn-sm"
                  onClick={() => onBulk('clear_reviewed', chapter.chapter)}
                >
                  Return chapter to unreviewed
                </button>
              ) : null}
            </div>
          </div>

          {tab === 'unreviewed' ? (
            chapter.items.map((item) => (
              <ReviewQaUnreviewedItem
                key={item.id}
                item={item}
                onAction={onItemAction}
                onError={onItemError}
              />
            ))
          ) : (
            <ReviewedTable
              items={chapter.items}
              onReturn={(id) =>
                returnReviewQaUnreviewed(id).then((result) => {
                  onItemAction(result.tab, result.message)
                })
              }
              onRemove={(id) => {
                if (!window.confirm('Remove this QA from assignment? It will move to Removed QAs.')) {
                  return Promise.resolve()
                }
                return removeReviewQaItem(id).then((result) => {
                  onItemAction(result.tab, result.message)
                })
              }}
              onError={onItemError}
            />
          )}
        </section>
      ))}
    </>
  )
}

function ReviewedTable({
  items,
  onReturn,
  onRemove,
  onError,
}: {
  items: ReviewQaItem[]
  onReturn: (id: string) => Promise<void>
  onRemove: (id: string) => Promise<void>
  onError: (message: string) => void
}) {
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Passage</th>
            <th>Question</th>
            <th>Standard answer</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              <td>{item.passage}</td>
              <td>{item.question_text}</td>
              <td>
                <ReviewQaStandardAnswer item={item} />
              </td>
              <td>
                <div className="action-row">
                  <button
                    type="button"
                    className="btn-success"
                    onClick={() =>
                      onReturn(item.id).catch((err) =>
                        onError(err instanceof ApiError ? err.message : 'Action failed'),
                      )
                    }
                  >
                    Return to unreviewed
                  </button>
                  <button
                    type="button"
                    className="btn-danger"
                    onClick={() =>
                      onRemove(item.id).catch((err) =>
                        onError(err instanceof ApiError ? err.message : 'Action failed'),
                      )
                    }
                  >
                    Remove
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function RemovedTable({
  items,
  onRestore,
}: {
  items: ReviewQaItem[]
  onRestore: (id: string) => Promise<void>
}) {
  if (!items.length) {
    return <p>No removed QA items.</p>
  }

  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Passage</th>
            <th>Question</th>
            <th>Standard answer</th>
            <th>Removed</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              <td>{item.passage}</td>
              <td>{item.question_text}</td>
              <td>
                <ReviewQaStandardAnswer item={item} />
              </td>
              <td>{item.removed_label ?? '—'}</td>
              <td>
                <button type="button" onClick={() => onRestore(item.id)}>
                  Restore
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
