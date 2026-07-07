import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ApiError, getCachedApiData } from '../api/client'
import {
  fetchReviewResponse,
  submitReviewResponseDecision,
  type ReviewResponseDashboard,
  type ReviewResponseItem,
} from '../api/reviewResponse'

type ReviewResponseGroup = {
  key: string
  language: string
  passage: string
  passage_text: string
  question: string
  expected_answer_en: string
  keywords: ReviewResponseItem['keywords']
  question_target_audio: ReviewResponseItem['question_target_audio']
  responses: ReviewResponseItem[]
}

function groupReviewResponses(items: ReviewResponseItem[]): ReviewResponseGroup[] {
  const groups = new Map<string, ReviewResponseGroup>()

  for (const item of items) {
    const key = `${item.qa_item_id}:${item.language}`
    const existing = groups.get(key)
    if (existing) {
      existing.responses.push(item)
      continue
    }

    groups.set(key, {
      key,
      language: item.language,
      passage: item.passage,
      passage_text: item.passage_text,
      question: item.question,
      expected_answer_en: item.expected_answer_en,
      keywords: item.keywords,
      question_target_audio: item.question_target_audio,
      responses: [item],
    })
  }

  return Array.from(groups.values())
}

function KeywordsBlock({ keywords }: { keywords: ReviewResponseItem['keywords'] }) {
  if (!keywords.required.length && !keywords.optional.length) {
    return <span>—</span>
  }

  return (
    <div className="review-response-keywords">
      {keywords.required.length ? (
        <p>
          <strong>Required:</strong> {keywords.required.join(', ')}
        </p>
      ) : null}
      {keywords.optional.length ? (
        <p>
          <strong>Optional:</strong> {keywords.optional.join(', ')}
        </p>
      ) : null}
    </div>
  )
}

export function ReviewResponsePage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const language = searchParams.get('language') ?? ''
  const reviewPath = `/api/v1/review-response${language ? `?language=${encodeURIComponent(language)}` : ''}`
  const cachedDashboard = getCachedApiData<ReviewResponseDashboard>(reviewPath)

  const [dashboard, setDashboard] = useState<ReviewResponseDashboard | null>(cachedDashboard)
  const [loading, setLoading] = useState(!cachedDashboard)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busyId, setBusyId] = useState('')

  const load = useCallback((options?: { silent?: boolean }) => {
    const silent = options?.silent ?? false
    const path = `/api/v1/review-response${language ? `?language=${encodeURIComponent(language)}` : ''}`
    const cached = getCachedApiData<ReviewResponseDashboard>(path)
    if (cached) {
      setDashboard(cached)
    }
    if (!silent) {
      setLoading(!cached)
    }
    setError('')
    return fetchReviewResponse(language || undefined)
      .then(setDashboard)
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : 'Failed to load review queue')
      })
      .finally(() => {
        if (!silent) {
          setLoading(false)
        }
      })
  }, [language])

  useEffect(() => {
    load()
  }, [load])

  const groups = useMemo(
    () => groupReviewResponses(dashboard?.items ?? []),
    [dashboard?.items],
  )

  async function handleDecision(responseId: string, decision: 'correct' | 'incorrect') {
    setBusyId(responseId)
    setError('')
    try {
      const result = await submitReviewResponseDecision(responseId, decision)
      setMessage(result.message)
      load({ silent: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not save decision')
    } finally {
      setBusyId('')
    }
  }

  if (loading && !dashboard) {
    return <p className="loading-message">Loading Review Response…</p>
  }

  return (
    <section className="panel review-response-page">
      <h2>Review Response</h2>
      <p className="hint">Review flagged participant responses awaiting expert review.</p>
      {error ? <p className="error-message">{error}</p> : null}
      {message ? <p className="success-message">{message}</p> : null}

      <form
        className="mutation-form"
        onSubmit={(event) => {
          event.preventDefault()
          const form = event.currentTarget
          const select = form.elements.namedItem('language') as HTMLSelectElement
          setSearchParams(select.value ? { language: select.value } : {})
        }}
      >
        <label htmlFor="review-response-language">Language</label>
        <select id="review-response-language" name="language" defaultValue={language}>
          <option value="">All languages</option>
          {(dashboard?.language_options ?? []).map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
        <button type="submit">Apply language</button>
      </form>

      {!groups.length ? (
        <p className="detail-meta">No responses awaiting review.</p>
      ) : (
        <div className="review-response-groups">
          {groups.map((group) => (
            <section key={group.key} className="review-response-group">
              <header className="review-response-question-panel">
                <div className="review-response-question-heading">
                  <span className="review-response-language-badge">{group.language}</span>
                  <h3 className="review-response-passage">{group.passage}</h3>
                  <span className="review-response-count">
                    {group.responses.length} response{group.responses.length === 1 ? '' : 's'}{' '}
                    awaiting review
                  </span>
                </div>
                {group.passage_text ? (
                  <p className="review-response-passage-text">{group.passage_text}</p>
                ) : null}
                <p className="review-response-question-text">{group.question}</p>
                <dl className="review-response-meta">
                  <div className="review-response-meta-field review-response-meta-expected">
                    <dt>Expected (EN)</dt>
                    <dd>{group.expected_answer_en || '—'}</dd>
                  </div>
                  <div className="review-response-meta-field review-response-meta-keywords">
                    <dt>Keywords</dt>
                    <dd>
                      <KeywordsBlock keywords={group.keywords} />
                    </dd>
                  </div>
                  <div className="review-response-meta-field review-response-meta-audio">
                    <dt>Question audio</dt>
                    <dd>
                      {group.question_target_audio ? (
                        <audio
                          controls
                          preload="none"
                          src={group.question_target_audio.media_url}
                        />
                      ) : (
                        '—'
                      )}
                    </dd>
                  </div>
                </dl>
              </header>

              <div className="review-response-answers-panel">
                <h4 className="review-response-answers-heading">Participant responses</h4>
                <ul className="review-response-answer-list">
                  {group.responses.map((item, index) => (
                    <li key={item.response_id} className="review-response-answer-item">
                      <div className="review-response-answer-index">
                        Response {index + 1}
                      </div>
                      <div className="review-response-answer-grid">
                        <div className="review-response-answer-field">
                          <span className="review-response-field-label">Answer</span>
                          <div className="review-response-answer-content">
                            {item.answer.audio_url ? (
                              <audio controls preload="none" src={item.answer.audio_url} />
                            ) : null}
                            {item.answer.text ? <p>{item.answer.text}</p> : null}
                            {!item.answer.audio_url && !item.answer.text ? '—' : null}
                          </div>
                        </div>
                        <div className="review-response-answer-field review-response-answer-field-narrow">
                          <span className="review-response-field-label">Score</span>
                          <span>{item.score ?? '—'}</span>
                        </div>
                        <div className="review-response-answer-field review-response-answer-field-narrow">
                          <span className="review-response-field-label">Status</span>
                          <span className="review-response-status">{item.review_status}</span>
                        </div>
                        <div className="review-response-answer-field review-response-answer-field-actions">
                          <span className="review-response-field-label">Review</span>
                          <div className="review-response-actions">
                            <button
                              type="button"
                              className="btn-success btn-sm"
                              disabled={busyId === item.response_id}
                              onClick={() => handleDecision(item.response_id, 'correct')}
                            >
                              Mark correct
                            </button>
                            <button
                              type="button"
                              className="btn-danger btn-sm"
                              disabled={busyId === item.response_id}
                              onClick={() => handleDecision(item.response_id, 'incorrect')}
                            >
                              Mark incorrect
                            </button>
                          </div>
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            </section>
          ))}
        </div>
      )}
    </section>
  )
}
