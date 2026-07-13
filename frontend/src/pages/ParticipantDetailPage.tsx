import { useEffect, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError, getCachedApiData } from '../api/client'
import {
  fetchParticipantDetail,
  updateParticipantLanguage,
  type ParticipantDetail,
} from '../api/participants'
import { fetchSystemLanguages } from '../api/systemLanguages'

export function ParticipantDetailPage() {
  const { participantId } = useParams<{ participantId: string }>()
  const cachedDetail = participantId
    ? getCachedApiData<ParticipantDetail>(`/api/v1/participants/${participantId}`)
    : null
  const cachedLanguages = getCachedApiData<{ languages: string[] }>('/api/v1/system-languages')
  const [detail, setDetail] = useState<ParticipantDetail | null>(cachedDetail)
  const [languages, setLanguages] = useState<string[]>(cachedLanguages?.languages ?? [])
  const [language, setLanguage] = useState(cachedDetail?.participant.language ?? '')
  const [loading, setLoading] = useState(!cachedDetail || !cachedLanguages)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [savingLanguage, setSavingLanguage] = useState(false)

  useEffect(() => {
    if (!participantId) {
      return
    }
    const cachedParticipant = getCachedApiData<ParticipantDetail>(`/api/v1/participants/${participantId}`)
    const cachedLanguagePayload = getCachedApiData<{ languages: string[] }>('/api/v1/system-languages')
    if (cachedParticipant) {
      setDetail(cachedParticipant)
      setLanguage(cachedParticipant.participant.language)
    }
    if (cachedLanguagePayload) {
      setLanguages(cachedLanguagePayload.languages)
    }
    setLoading(!cachedParticipant || !cachedLanguagePayload)
    Promise.all([fetchParticipantDetail(participantId), fetchSystemLanguages()])
      .then(([participantDetail, languagePayload]) => {
        setDetail(participantDetail)
        setLanguage(participantDetail.participant.language)
        setLanguages(languagePayload.languages)
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : 'Failed to load participant')
      })
      .finally(() => setLoading(false))
  }, [participantId])

  async function handleLanguageSubmit(event: FormEvent) {
    event.preventDefault()
    if (!participantId) {
      return
    }

    setSavingLanguage(true)
    setError('')
    setMessage('')
    try {
      const result = await updateParticipantLanguage(participantId, language)
      setDetail({ participant: result.participant, history: result.history })
      setLanguage(result.participant.language)
      setLanguages((current) =>
        current.includes(result.participant.language)
          ? current
          : [...current, result.participant.language].sort(),
      )
      setMessage(result.message)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not update language')
    } finally {
      setSavingLanguage(false)
    }
  }

  if (loading) {
    return <p className="loading-message">Loading participant…</p>
  }

  if (error) {
    return (
      <section className="panel">
        <p className="error-message">{error}</p>
        <Link to="/participants">← Back to Participants</Link>
      </section>
    )
  }

  if (!detail) {
    return null
  }

  const participant = detail.participant

  return (
    <section className="panel detail-page">
      <p className="back-link">
        <Link to="/participants">← Back to Participants</Link>
      </p>
      <h2>{participant.display_name || participant.participant_id}</h2>
      {error ? <p className="error-message">{error}</p> : null}
      {message ? <p className="success-message">{message}</p> : null}

      <section className="detail-card">
        <h3>Participant</h3>
        <form className="mutation-form participant-language-form" onSubmit={handleLanguageSubmit}>
          <label htmlFor="participant-language">Language</label>
          <div className="participant-language-row">
            <select
              id="participant-language"
              value={language}
              onChange={(event) => setLanguage(event.target.value)}
              required
            >
              {language && !languages.includes(language) ? (
                <option value={language}>{language}</option>
              ) : null}
              {languages.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
            <button type="submit" disabled={savingLanguage}>
              {savingLanguage ? 'Saving…' : 'Save language'}
            </button>
          </div>
        </form>
        <dl className="detail-list">
          <dt>WhatsApp ID</dt>
          <dd>{participant.participant_id}</dd>
          <dt>Language</dt>
          <dd>{participant.language}</dd>
          <dt>Session state</dt>
          <dd>{participant.session_state}</dd>
          <dt>Currently working on</dt>
          <dd>{participant.current_question ?? '—'}</dd>
          <dt>Questions completed</dt>
          <dd>{participant.questions_completed}</dd>
          <dt>Correct</dt>
          <dd>{participant.correct}</dd>
          <dt>Incorrect</dt>
          <dd>{participant.incorrect}</dd>
          <dt>Under review</dt>
          <dd>{participant.under_review}</dd>
          <dt>Batch size</dt>
          <dd>{participant.batch_size}</dd>
          <dt>Last seen</dt>
          <dd>{participant.last_seen ?? '—'}</dd>
          <dt>Consented</dt>
          <dd>{participant.consented ? 'Yes' : 'No'}</dd>
        </dl>
      </section>

      <section className="detail-card">
        <h3>Questions answered ({detail.history.length})</h3>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Passage</th>
                <th>Question</th>
                <th>Type</th>
                <th>Expected answer</th>
                <th>User answer</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {detail.history.map((row) => (
                <tr key={`${row.qa_item_id}-${row.question}`}>
                  <td>{row.passage}</td>
                  <td>
                    <Link to={`/qa-items/${row.qa_item_id}`}>{row.question}</Link>
                  </td>
                  <td>{row.question_type}</td>
                  <td>{row.expected_answer}</td>
                  <td>{row.user_answer}</td>
                  <td>{row.correctness_status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  )
}
