import { useCallback } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import {
  fetchExperimentPassageDetail,
} from '../api/experimentPassages'

import { useApiResource } from '../hooks/useApiResource'

function formatTimestamp(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

export function ExperimentPassageDetailPage() {
  const { passageId } = useParams<{ passageId: string }>()
  const loadDetail = useCallback(() => passageId
    ? fetchExperimentPassageDetail(passageId)
    : Promise.reject(new ApiError('Experiment passage not found.', 404)), [passageId])
  const { data: detail, loading, error } = useApiResource(
    passageId ?? '', loadDetail, null, 'Failed to load passage', 'Experiment passage not found.',
  )

  return (
    <section className="panel">
      <p>
        <Link to="/experiment-passages" className="review-workbench-toolbar-link">
          ← Back to experiment passages
        </Link>
      </p>

      {loading ? (
        <p className="loading-message">Loading passage…</p>
      ) : error ? (
        <p className="error-message">{error}</p>
      ) : detail ? (
        <>
          <div className="panel-heading-row">
            <h2>
              Luke {detail.chapter} — {detail.name ?? detail.condition}
            </h2>
          </div>

          <dl className="passage-detail-meta">
            <div>
              <dt>Condition</dt>
              <dd>{detail.condition}</dd>
            </div>
            <div>
              <dt>Chapter</dt>
              <dd>{detail.chapter}</dd>
            </div>
            <div>
              <dt>Language</dt>
              <dd>{detail.language}</dd>
            </div>
            <div>
              <dt>Reference</dt>
              <dd>{detail.passage_reference ?? '—'}</dd>
            </div>
            <div>
              <dt>Characters</dt>
              <dd>{detail.char_count}</dd>
            </div>
            <div>
              <dt>Verses</dt>
              <dd>{detail.verse_count}</dd>
            </div>
            <div>
              <dt>Created</dt>
              <dd>{formatTimestamp(detail.created_at)}</dd>
            </div>
          </dl>

          <h3>Passage text</h3>
          <div className="passage-verse-list">
            {detail.verses.map((verse) => (
              <p key={`${verse.position}-${verse.verse_number}`} className="passage-verse-row">
                <strong>{verse.verse_number}</strong>
                <span>{verse.text}</span>
              </p>
            ))}
          </div>
        </>
      ) : null}
    </section>
  )
}
