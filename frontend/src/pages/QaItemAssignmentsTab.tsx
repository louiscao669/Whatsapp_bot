import { useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import { fetchQaItemAssignments, type QaItemAssignmentRow } from '../api/qaItems'

type QaItemAssignmentsTabProps = {
  qaItemId: string
  languages: string[]
}

export function QaItemAssignmentsTab({ qaItemId, languages }: QaItemAssignmentsTabProps) {
  const [assignments, setAssignments] = useState<QaItemAssignmentRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    setLoading(true)
    fetchQaItemAssignments(qaItemId, languages)
      .then((data) => setAssignments(data.assignments))
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : 'Failed to load assignments')
      })
      .finally(() => setLoading(false))
  }, [qaItemId, languages])

  if (loading) {
    return <p className="loading-message">Loading assignments…</p>
  }

  if (error) {
    return <p className="error-message">{error}</p>
  }

  if (!assignments.length) {
    return <p className="detail-meta">No assignments in the selected language scope.</p>
  }

  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Participant</th>
            <th>WhatsApp ID</th>
            <th>Language</th>
            <th>Status</th>
            <th>Assigned</th>
            <th>Completed</th>
            <th>Batch</th>
          </tr>
        </thead>
        <tbody>
          {assignments.map((row, index) => (
            <tr key={`${row.wa_id}-${index}`}>
              <td>{row.participant}</td>
              <td>{row.wa_id}</td>
              <td>{row.language}</td>
              <td>{row.status}</td>
              <td>{row.assigned_at ?? '—'}</td>
              <td>{row.completed_at ?? '—'}</td>
              <td>{row.batch_id || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
