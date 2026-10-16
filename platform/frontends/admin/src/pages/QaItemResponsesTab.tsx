import { useCallback } from 'react'
import { getCachedApiData } from '../api/client'
import {
  type QaItemResponsesPayload,
  fetchQaItemResponses,
  qaItemSectionPath,
  type QaItemChoiceResponse,
  type QaItemOpenResponse,
} from '../api/qaItems'

import { useApiResource } from '../hooks/useApiResource'

type QaItemResponsesTabProps = {
  qaItemId: string
  languages: string[]
  choiceScored: boolean
}

export function QaItemResponsesTab({ qaItemId, languages, choiceScored }: QaItemResponsesTabProps) {
  const path = qaItemSectionPath(qaItemId, 'responses', languages)
  const cached = getCachedApiData<QaItemResponsesPayload>(path)
  const load = useCallback(() => fetchQaItemResponses(qaItemId, languages), [qaItemId, languages])
  const { data, loading, error } = useApiResource(path, load, cached, 'Failed to load responses')
  const responses = data?.responses ?? []

  if (loading) {
    return <p className="loading-message">Loading responses…</p>
  }

  if (error) {
    return <p className="error-message">{error}</p>
  }

  if (!responses.length) {
    return <p className="detail-meta">No responses in the selected language scope.</p>
  }

  if (choiceScored) {
    return (
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Received</th>
              <th>Participant</th>
              <th>Language</th>
              <th>Type</th>
              <th>Recording</th>
              <th>Answer</th>
              <th>Correctness</th>
            </tr>
          </thead>
          <tbody>
            {(responses as QaItemChoiceResponse[]).map((row, index) => (
              <tr key={`${row.received_at}-${index}`}>
                <td>{row.received_at}</td>
                <td>{row.participant}</td>
                <td>{row.language}</td>
                <td>{row.response_type}</td>
                <td>
                  {row.audio_url ? <audio controls preload="none" src={row.audio_url} /> : '—'}
                </td>
                <td>{row.choice_answer}</td>
                <td>{row.correctness}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Received</th>
            <th>Participant</th>
            <th>Language</th>
            <th>Type</th>
            <th>Recording</th>
            <th>Answer</th>
            <th>Score</th>
            <th>Keywords</th>
            <th>Status</th>
            <th>Review</th>
          </tr>
        </thead>
        <tbody>
          {(responses as QaItemOpenResponse[]).map((row, index) => (
            <tr key={`${row.received_at}-${index}`}>
              <td>{row.received_at}</td>
              <td>{row.participant}</td>
              <td>{row.language}</td>
              <td>{row.response_type}</td>
              <td>
                {row.audio_url ? <audio controls preload="none" src={row.audio_url} /> : '—'}
              </td>
              <td className="question-cell">{row.answer || '—'}</td>
              <td>{row.correctness_score ?? '—'}</td>
              <td>
                {row.matched_keywords.length ? (
                  <p>Matched: {row.matched_keywords.join(', ')}</p>
                ) : null}
                {row.missing_keywords.length ? (
                  <p>Missing: {row.missing_keywords.join(', ')}</p>
                ) : null}
              </td>
              <td>{row.correctness_label}</td>
              <td>{row.review_status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
