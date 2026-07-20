import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, getCachedApiData } from '../api/client'
import { fetchParticipants, type ParticipantRow } from '../api/participants'

const PARTICIPANTS_PATH = '/api/v1/participants'

export function ParticipantsPage() {
  const cachedParticipants = getCachedApiData<{ participants: ParticipantRow[] }>(PARTICIPANTS_PATH)
  const [participants, setParticipants] = useState<ParticipantRow[]>(
    cachedParticipants?.participants ?? [],
  )
  const [loading, setLoading] = useState(!cachedParticipants)
  const [error, setError] = useState('')

  useEffect(() => {
    fetchParticipants()
      .then((data) => setParticipants(data.participants))
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : 'Failed to load participants')
      })
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return <p className="loading-message">Loading Participants…</p>
  }

  if (error) {
    return <p className="error-message">{error}</p>
  }

  return (
    <section className="panel">
      <h2>Participants</h2>
      <p className="hint">
        Admin-only view of assigned questions, progress, and response scoring buckets.
      </p>
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>WhatsApp ID</th>
              <th>Display name</th>
              <th>Language</th>
              <th>Session</th>
              <th>Current question</th>
              <th>Completed</th>
              <th>Correct</th>
              <th>Incorrect</th>
              <th>Under review</th>
              <th>Batch</th>
              <th>Last seen</th>
              <th>Consented</th>
            </tr>
          </thead>
          <tbody>
            {participants.map((row) => (
              <tr key={row.id}>
                <td className="wa-id-cell" title={row.participant_id}>{row.participant_id}</td>
                <td className="participant-display-name-cell">
                  <Link to={`/participants/${row.id}`}>{row.display_name || row.participant_id}</Link>
                </td>
                <td>{row.language}</td>
                <td>{row.session_state}</td>
                <td>{row.current_question || '—'}</td>
                <td>{row.questions_completed}</td>
                <td>{row.correct}</td>
                <td>{row.incorrect}</td>
                <td>{row.under_review}</td>
                <td>{row.batch_size}</td>
                <td className="participant-last-seen-cell">{row.last_seen ?? '—'}</td>
                <td>{row.consented ? 'Yes' : 'No'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
