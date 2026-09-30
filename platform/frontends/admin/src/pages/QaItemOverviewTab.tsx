import { useEffect } from 'react'
import { Link, useParams } from 'react-router-dom'
import type { QaItemDetail, QaItemExpectedAnswer } from '../api/qaItems'
import { QaItemSettingsForm } from '../components/QaItemSettingsForm'

function ExpectedAnswerBlock({ answer }: { answer: QaItemExpectedAnswer }) {
  if (answer.kind === 'open') {
    return <p className="detail-text">{answer.text || '—'}</p>
  }

  return (
    <div className="detail-choices">
      {answer.correct_choice ? (
        <p className="detail-meta">Correct choice: {answer.correct_choice}</p>
      ) : null}
      <ul>
        {answer.choices.map((choice) => (
          <li key={choice.letter} className={choice.is_correct ? 'choice-correct' : undefined}>
            <strong>{choice.letter}</strong>: {choice.text || '—'}
            {choice.is_correct ? ' (correct)' : ''}
          </li>
        ))}
      </ul>
    </div>
  )
}

function PromptRecording({
  label,
  recording,
}: {
  label: string
  recording: QaItemDetail['prompt_recordings']['question']
}) {
  if (!recording) {
    return null
  }
  return (
    <div className="detail-recording">
      <p className="detail-meta">
        {label} ({recording.language}, v{recording.version})
      </p>
      <audio controls preload="none" src={recording.media_url} />
    </div>
  )
}

type QaItemOverviewTabProps = {
  item: QaItemDetail
  onItemUpdated: (item: QaItemDetail) => void
  onMessage: (message: string) => void
  onError: (message: string) => void
}

export function QaItemOverviewTab({ item, onItemUpdated, onMessage, onError }: QaItemOverviewTabProps) {
  const { variantId } = useParams<{ variantId: string }>()
  const variants = item.passage_variants ?? []
  const selectedVariant = variants.find((variant) => variant.id === variantId)

  useEffect(() => {
    if (variantId) document.getElementById('passages-by-defect')?.scrollIntoView({ block: 'start' })
  }, [variantId])

  return (
    <>
      <div className="detail-grid">
        <section className="detail-card">
          <h3>Question</h3>
          <dl className="detail-list">
            <dt>Passage</dt>
            <dd>{item.passage}</dd>
            <dt>Question type</dt>
            <dd>{item.question_type}</dd>
            <dt>Review status</dt>
            <dd>{item.review_status}</dd>
            <dt>Active</dt>
            <dd>{item.active ? 'Yes' : 'No'}</dd>
          </dl>
          {item.passage_text ? (
            <>
              <h4>Passage text</h4>
              <p className="detail-text">{item.passage_text}</p>
            </>
          ) : null}
          <h4>Question text</h4>
          <p className="detail-text">{item.question_text}</p>
          <PromptRecording label="Question recording" recording={item.prompt_recordings.question} />
          <h4>Expected answer</h4>
          <ExpectedAnswerBlock answer={item.expected_answer} />
          <PromptRecording label="Answer recording" recording={item.prompt_recordings.answer} />
        </section>

        <section className="detail-card">
          <h3>Analytics</h3>
          <dl className="detail-list">
            <dt>Total responses</dt>
            <dd>{item.analytics.total_responses}</dd>
            <dt>Scored responses</dt>
            <dd>{item.analytics.scored_count}</dd>
            <dt>Average correctness score</dt>
            <dd>{item.analytics.average_score ?? '—'}</dd>
            <dt>Flagged responses</dt>
            <dd>{item.analytics.flagged_count}</dd>
            <dt>Flag rate</dt>
            <dd>{item.analytics.flag_rate ?? '—'}</dd>
            <dt>Meets minimum responses</dt>
            <dd>{item.analytics.meets_min_responses ? 'Yes' : 'No'}</dd>
            <dt>Responses still needed</dt>
            <dd>{item.analytics.responses_needed}</dd>
          </dl>
        </section>
      </div>

      <section className="detail-card" id="passages-by-defect">
        <h3>Passages by defect type</h3>
        {variants.length === 0 ? <p>No experiment passage variants are available for this question.</p> : (
          <nav className="detail-tabs" aria-label="Passage variants">
            {variants.map((variant) => (
              <Link
                key={variant.id}
                className={variant.id === variantId ? 'detail-tab active' : 'detail-tab'}
                aria-current={variant.id === variantId ? 'page' : undefined}
                to={`/qa-items/${encodeURIComponent(item.id)}/passages/${encodeURIComponent(variant.id)}#passages-by-defect`}
              >
                {variant.condition === 'clean' ? 'Clean' : variant.condition} · {variant.language}
              </Link>
            ))}
          </nav>
        )}
        {selectedVariant ? (
          <section aria-label="Selected passage">
            <h4>{selectedVariant.condition === 'clean' ? 'Clean' : selectedVariant.condition} · {selectedVariant.language}</h4>
            {selectedVariant.condition !== 'clean' ? (
              <p className="detail-meta">{selectedVariant.defect_type ?? selectedVariant.condition}{selectedVariant.defect_rate == null ? '' : ` · ${Math.round(selectedVariant.defect_rate * 100)}%`}</p>
            ) : null}
            <p className="detail-meta">{selectedVariant.is_window ? `Question window · ${selectedVariant.verse_numbers.join(', ') || 'Unavailable'}` : 'Full passage'}</p>
            <p className="detail-text" style={{ whiteSpace: 'pre-wrap' }}>{selectedVariant.passage_text ?? 'No question window available for this variant.'}</p>
            {selectedVariant.is_window ? (
              <details>
                <summary>Full passage</summary>
                <p className="detail-text" style={{ whiteSpace: 'pre-wrap' }}>{selectedVariant.full_passage_text}</p>
              </details>
            ) : null}
            <p className="hint">This is the current passage for this condition. Saved participant passages are available in participant metadata.</p>
          </section>
        ) : variantId ? (
          <p role="alert">This passage variant is unavailable for this question. Choose an available variant above.</p>
        ) : variants.length > 0 ? <p>Select a defect type or Clean to open its passage page.</p> : null}
      </section>

      <QaItemSettingsForm
        item={item}
        onUpdated={onItemUpdated}
        onMessage={onMessage}
        onError={onError}
      />
    </>
  )
}
