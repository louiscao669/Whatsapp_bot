import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import {
  fetchExperimentPassageDetail,
  type ExperimentPassageDetail,
} from '../api/experimentPassages'

function formatTimestamp(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

export function ExperimentPassageDetailPage() {
  const { passageId } = useParams<{ passageId: string }>()
  const [detail, setDetail] = useState<ExperimentPassageDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const loadDetail = useCallback(() => {
    if (!passageId) return Promise.resolve()
    setError('')
    setLoading(true)
    return fetchExperimentPassageDetail(passageId)
      .then((data) => setDetail(data))
      .catch((err) => {
        if (err instanceof ApiError && err.status === 404) {
          setError('Experiment passage not found.')
          return
        }
        setError(err instanceof ApiError ? err.message : 'Failed to load passage')
      })
      .finally(() => setLoading(false))
  }, [passageId])

  useEffect(() => {
    loadDetail()
  }, [loadDetail])

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
              <dt>Created</dt>
              <dd>{formatTimestamp(detail.created_at)}</dd>
            </div>
          </dl>

          <h3>Passage text</h3>
          <pre className="passage-text-block">{detail.passage_text}</pre>
        </>
      ) : null}
    </section>
  )
}
