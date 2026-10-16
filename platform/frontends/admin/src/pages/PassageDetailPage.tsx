import { useCallback } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { fetchPassageDetail } from '../api/passages'

import { useApiResource } from '../hooks/useApiResource'

function formatTimestamp(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

export function PassageDetailPage() {
  const { translationId, chapterNumber } = useParams<{
    translationId: string
    chapterNumber: string
  }>()
  const chapter = Number(chapterNumber)
  const loadDetail = useCallback(() => {
    if (!translationId || !Number.isInteger(chapter) || chapter < 1) {
      return Promise.reject(new ApiError('Passage not found.', 404))
    }
    return fetchPassageDetail(translationId, chapter)
  }, [translationId, chapter])
  const { data: detail, loading, error } = useApiResource(
    `${translationId}/${chapter}`, loadDetail, null, 'Failed to load passage', 'Passage not found.',
  )

  return (
    <section className="panel">
      <p>
        <Link to="/passages" className="review-workbench-toolbar-link">
          ← Back to passages
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
              {detail.translation_name ?? 'Unnamed translation'} — Chapter{' '}
              {detail.chapter_number}
            </h2>
          </div>

          <dl className="passage-detail-meta">
            <div>
              <dt>Translation</dt>
              <dd>{detail.translation_name ?? 'Unnamed'}</dd>
            </div>
            <div>
              <dt>Chapter</dt>
              <dd>{detail.chapter_number}</dd>
            </div>
            <div>
              <dt>Language</dt>
              <dd>{detail.language}</dd>
            </div>
            <div>
              <dt>Verse count</dt>
              <dd>{detail.verse_count}</dd>
            </div>
            <div>
              <dt>Created</dt>
              <dd>{formatTimestamp(detail.created_at)}</dd>
            </div>
            <div>
              <dt>Updated</dt>
              <dd>{formatTimestamp(detail.updated_at)}</dd>
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
