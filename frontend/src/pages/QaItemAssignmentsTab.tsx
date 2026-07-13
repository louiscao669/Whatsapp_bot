import { useEffect, useState } from 'react'
import { ApiError, getCachedApiData } from '../api/client'
import { fetchQaItemAssignments, type QaItemAssignmentRow } from '../api/qaItems'

type QaItemAssignmentsTabProps = {
  qaItemId: string
  languages: string[]
}

function assignmentsPath(qaItemId: string, languages: string[]) {
  const params = new URLSearchParams()
  for (const language of languages) {
    params.append('languages', language)
  }
  const query = params.toString()
  return `/api/v1/qa-items/${qaItemId}/assignments${query ? `?${query}` : ''}`
}

export function QaItemAssignmentsTab({ qaItemId, languages }: QaItemAssignmentsTabProps) {
  const cachedAssignments = getCachedApiData<{
    assignments: QaItemAssignmentRow[]
    languages: string[]
  }>(assignmentsPath(qaItemId, languages))
  const [assignments, setAssignments] = useState<QaItemAssignmentRow[]>(
    cachedAssignments?.assignments ?? [],
  )
  const [loading, setLoading] = useState(!cachedAssignments)
  const [error, setError] = useState('')

  useEffect(() => {
    const cached = getCachedApiData<{
      assignments: QaItemAssignmentRow[]
      languages: string[]
    }>(assignmentsPath(qaItemId, languages))
    if (cached) {
      setAssignments(cached.assignments)
    }
    setLoading(!cached)
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
