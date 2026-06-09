import { useEffect, useState, type FormEvent } from 'react'
import { ApiError } from '../api/client'
import { assignQaItem, fetchAssignParticipants, type AssignParticipant } from '../api/qaItems'

type QaItemAssignFormProps = {
  qaItemId: string
  onMessage: (message: string) => void
  onError: (message: string) => void
}

export function QaItemAssignForm({ qaItemId, onMessage, onError }: QaItemAssignFormProps) {
  const [participants, setParticipants] = useState<AssignParticipant[]>([])
  const [participantId, setParticipantId] = useState('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    fetchAssignParticipants()
      .then((data) => setParticipants(data.participants))
      .catch((err) => {
        onError(err instanceof ApiError ? err.message : 'Failed to load participants')
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps -- load once on mount
  }, [])

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    try {
      const result = await assignQaItem(qaItemId, participantId)
      onMessage(result.message)
      setParticipantId('')
    } catch (err) {
      onError(err instanceof ApiError ? err.message : 'Assignment failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="detail-card" id="assign">
      <h3>Assign to participant</h3>
      <form className="mutation-form" onSubmit={handleSubmit}>
        <label htmlFor="assign-participant">Participant</label>
        <select
          id="assign-participant"
          value={participantId}
          onChange={(e) => setParticipantId(e.target.value)}
          required
        >
          <option value="">Select a participant</option>
          {participants.map((participant) => (
            <option key={participant.id} value={participant.id}>
              {participant.display_name || participant.wa_id} ({participant.wa_id},{' '}
              {participant.target_language || 'any'})
            </option>
          ))}
        </select>
        <button type="submit" disabled={submitting || !participantId}>
          Assign question
        </button>
      </form>
    </section>
  )
}
