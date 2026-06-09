import { useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import { bulkQaItemsAction, fetchAssignParticipants, type AssignParticipant } from '../api/qaItems'

type QaItemsBulkPanelProps = {
  selectedIds: string[]
  onComplete: (message: string) => void
  onError: (message: string) => void
  onClearSelection: () => void
}

export function QaItemsBulkPanel({
  selectedIds,
  onComplete,
  onError,
  onClearSelection,
}: QaItemsBulkPanelProps) {
  const [participants, setParticipants] = useState<AssignParticipant[]>([])
  const [participantId, setParticipantId] = useState('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    fetchAssignParticipants()
      .then((data) => setParticipants(data.participants))
      .catch(() => {
        /* participant list loads when bulk panel opens */
      })
  }, [])

  if (!selectedIds.length) {
    return null
  }

  async function runAction(action: 'assign' | 'delete') {
    if (action === 'delete') {
      const confirmed = window.confirm(
        `Delete ${selectedIds.length} question(s) and all related assignments/responses?`,
      )
      if (!confirmed) {
        return
      }
    }

    setSubmitting(true)
    try {
      const result = await bulkQaItemsAction({
        action,
        qa_item_ids: selectedIds,
        participant_id: action === 'assign' ? participantId : undefined,
      })
      onComplete(result.message)
      onClearSelection()
    } catch (err) {
      onError(err instanceof ApiError ? err.message : 'Bulk action failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="detail-card bulk-panel">
      <h3>Bulk actions ({selectedIds.length} selected)</h3>
      <div className="bulk-actions">
        <label htmlFor="bulk-participant">Participant (for assign)</label>
        <select
          id="bulk-participant"
          className="bulk-participant-select"
          value={participantId}
          onChange={(e) => setParticipantId(e.target.value)}
        >
          <option value="">Select participant</option>
          {participants.map((participant) => (
            <option key={participant.id} value={participant.id}>
              {participant.display_name || participant.wa_id} ({participant.wa_id},{' '}
              {participant.target_language || 'any'})
            </option>
          ))}
        </select>
        <div className="action-row">
          <button
            type="button"
            className="btn-success"
            disabled={submitting}
            onClick={() => runAction('assign')}
          >
            Assign selected
          </button>
          <button
            type="button"
            className="btn-danger"
            disabled={submitting}
            onClick={() => runAction('delete')}
          >
            Delete selected
          </button>
          <button type="button" className="link-button" onClick={onClearSelection}>
            Clear selection
          </button>
        </div>
      </div>
    </section>
  )
}
