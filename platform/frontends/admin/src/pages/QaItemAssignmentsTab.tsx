import { useCallback } from 'react'
import { getCachedApiData } from '../api/client'
import { qaItemSectionPath, fetchQaItemAssignments, type QaItemAssignmentRow } from '../api/qaItems'

import { useApiResource } from '../hooks/useApiResource'

type QaItemAssignmentsTabProps = {
  qaItemId: string
  languages: string[]
}

export function QaItemAssignmentsTab({ qaItemId, languages }: QaItemAssignmentsTabProps) {
  const path = qaItemSectionPath(qaItemId, 'assignments', languages)
  const cached = getCachedApiData<{ assignments: QaItemAssignmentRow[]; languages: string[] }>(path)
  const load = useCallback(() => fetchQaItemAssignments(qaItemId, languages), [qaItemId, languages])
  const { data, loading, error } = useApiResource(path, load, cached, 'Failed to load assignments')
  const assignments = data?.assignments ?? []

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
            <tr key={`${row.participant_id}-${index}`}>
              <td>{row.participant}</td>
              <td>{row.participant_id}</td>
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
