import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { fetchParticipantDetail, type ParticipantDetail } from '../api/participants'

export function ParticipantDetailPage() {
  const { participantId } = useParams<{ participantId: string }>()
  const [detail, setDetail] = useState<ParticipantDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!participantId) {
      return
    }
    fetchParticipantDetail(participantId)
      .then(setDetail)
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : 'Failed to load participant')
      })
      .finally(() => setLoading(false))
  }, [participantId])

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
      <h2>{participant.display_name || participant.wa_id}</h2>

      <section className="detail-card">
        <h3>Participant</h3>
        <dl className="detail-list">
          <dt>WhatsApp ID</dt>
          <dd>{participant.wa_id}</dd>
          <dt>Language</dt>
          <dd>{participant.language}</dd>
          <dt>Session state</dt>
          <dd>{participant.session_state}</dd>
          <dt>Currently working on</dt>
          <dd>{participant.current_question ?? '—'}</dd>
          <dt>Assigned questions</dt>
          <dd>{participant.assigned_questions ?? '—'}</dd>
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
