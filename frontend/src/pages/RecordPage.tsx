import { useCallback, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import {
  deleteRecording,
  fetchRecordDashboard,
  patchRecordingAfterDelete,
  patchRecordingAfterUpload,
  type RecordAnswer,
  type RecordDashboard,
  type RecordRow,
  type RecordTake,
} from '../api/record'
import { RecordControls } from '../components/RecordControls'
import { RetakeConfirmModal } from '../components/RetakeConfirmModal'

export function RecordPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const language = searchParams.get('language') ?? ''

  const [dashboard, setDashboard] = useState<RecordDashboard | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [retakeBlob, setRetakeBlob] = useState<Blob | null>(null)
  const [retakeResolver, setRetakeResolver] = useState<((value: boolean) => void) | null>(null)

  const loadDashboard = useCallback((targetLanguage?: string, options?: { silent?: boolean }) => {
    const silent = options?.silent ?? false
    if (!silent) {
      setLoading(true)
    }
    setError('')
    return fetchRecordDashboard(targetLanguage || undefined)
      .then(setDashboard)
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : 'Failed to load Record page')
      })
      .finally(() => {
        if (!silent) {
          setLoading(false)
        }
      })
  }, [])

  useEffect(() => {
    loadDashboard(language)
  }, [language, loadDashboard])

  function applyLanguage(nextLanguage: string) {
    setSearchParams(nextLanguage ? { language: nextLanguage } : {})
  }

  function handleRetakePreview(blob: Blob) {
    return new Promise<boolean>((resolve) => {
      setRetakeBlob(blob)
      setRetakeResolver(() => resolve)
    })
  }

  function closeRetakeModal(confirmed: boolean) {
    setRetakeBlob(null)
    retakeResolver?.(confirmed)
    setRetakeResolver(null)
  }

  function handleRecordingSaved(
    qaItemId: string,
    recordingType: 'question' | 'answer',
    message: string,
    recording: RecordTake,
    choiceLetter?: string,
  ) {
    setMessage(message)
    setDashboard((current) =>
      current
        ? patchRecordingAfterUpload(current, qaItemId, recordingType, recording, choiceLetter)
        : current,
    )
  }

  async function handleDelete(qaItemId: string, recording: RecordTake) {
    const label = recording.version ? `take v${recording.version}` : 'this take'
    if (!window.confirm(`Remove ${label}? This deletes the recording from the database.`)) {
      return
    }
    try {
      const result = await deleteRecording(recording.id)
      setMessage(result.message)
      setDashboard((current) =>
        current ? patchRecordingAfterDelete(current, qaItemId, recording) : current,
      )
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to remove recording')
    }
  }

  if (loading) {
    return <p className="loading-message">Loading Record…</p>
  }

  const selectedLanguage = dashboard?.language ?? ''

  return (
    <section className="panel record-page">
      <h2>Record</h2>
      <p className="hint">
        Record the <strong>question</strong> audio for each passage in the selected target language.
        Only QAs marked <strong>reviewed</strong> on <Link to="/review-qa?tab=reviewed">Review QA</Link>{' '}
        appear here.
      </p>
      {error ? <p className="error-message">{error}</p> : null}
      {message ? <p className="success-message">{message}</p> : null}

      <section className="detail-card">
        <h3>Record into language</h3>
        <form
          className="mutation-form"
          onSubmit={(event) => {
            event.preventDefault()
            const form = event.currentTarget
            const select = form.elements.namedItem('language') as HTMLSelectElement
            applyLanguage(select.value)
          }}
        >
          <label htmlFor="record-language">Language</label>
          <select
            id="record-language"
            name="language"
            defaultValue={selectedLanguage}
            disabled={!dashboard?.language_options.length}
          >
            {(dashboard?.language_options ?? []).map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
          <p className="hint">Question and answer recordings use the selected language.</p>
          <button type="submit">Apply language</button>
        </form>
      </section>

      {!dashboard?.items.length ? (
        <p className="detail-meta">
          No reviewed QAs yet. Complete Review QA first, then return here.
        </p>
      ) : (
        <div className="table-wrap">
          <table className="data-table record-table">
            <thead>
              <tr>
                <th>Passage</th>
                <th>Question</th>
                <th>Standard answer</th>
                <th>Question recording</th>
              </tr>
            </thead>
            <tbody>
              {dashboard.items.map((row) => (
                <RecordRowView
                  key={row.qa_item_id}
                  row={row}
                  language={selectedLanguage}
                  onRecordingSaved={handleRecordingSaved}
                  onError={setError}
                  onDelete={handleDelete}
                  onRetakePreview={handleRetakePreview}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      <RetakeConfirmModal
        blob={retakeBlob}
        onConfirm={() => closeRetakeModal(true)}
        onCancel={() => closeRetakeModal(false)}
      />
    </section>
  )
}

function RecordRowView({
  row,
  language,
  onRecordingSaved,
  onError,
  onDelete,
  onRetakePreview,
}: {
  row: RecordRow
  language: string
  onRecordingSaved: (
    qaItemId: string,
    recordingType: 'question' | 'answer',
    message: string,
    recording: RecordTake,
    choiceLetter?: string,
  ) => void
  onError: (message: string) => void
  onDelete: (qaItemId: string, recording: RecordTake) => void
  onRetakePreview: (blob: Blob) => Promise<boolean>
}) {
  return (
    <tr>
      <td>{row.passage}</td>
      <td className="question-cell">{row.question}</td>
      <td>
        <AnswerCell
          answer={row.answer}
          qaItemId={row.qa_item_id}
          language={language}
          onRecordingSaved={onRecordingSaved}
          onError={onError}
          onRetakePreview={onRetakePreview}
        />
      </td>
      <td>
        <QuestionRecordingCell
          row={row}
          language={language}
          onRecordingSaved={onRecordingSaved}
          onError={onError}
          onDelete={onDelete}
          onRetakePreview={onRetakePreview}
        />
      </td>
    </tr>
  )
}

function QuestionRecordingCell({
  row,
  language,
  onRecordingSaved,
  onError,
  onDelete,
  onRetakePreview,
}: {
  row: RecordRow
  language: string
  onRecordingSaved: (
    qaItemId: string,
    recordingType: 'question' | 'answer',
    message: string,
    recording: RecordTake,
    choiceLetter?: string,
  ) => void
  onError: (message: string) => void
  onDelete: (qaItemId: string, recording: RecordTake) => void
  onRetakePreview: (blob: Blob) => Promise<boolean>
}) {
  const recording = row.question_recording
  if (!recording) {
    return (
      <RecordControls
        qaItemId={row.qa_item_id}
        recordingType="question"
        language={language}
        mode="new"
        label="Record question"
        onComplete={(message, saved) =>
          onRecordingSaved(row.qa_item_id, 'question', message, saved)
        }
        onError={onError}
      />
    )
  }

  return (
    <div className="recording-take">
      <div className="recording-take-header">
        <span className="detail-meta">{recording.label}</span>
        <div className="action-row">
          <RecordControls
            qaItemId={row.qa_item_id}
            recordingType="question"
            language={language}
            mode="retake"
            label="Retake"
            recordingId={recording.id}
            version={recording.version}
            onComplete={(message, saved) =>
              onRecordingSaved(row.qa_item_id, 'question', message, saved)
            }
            onError={onError}
            onRetakePreview={onRetakePreview}
          />
          <button
            type="button"
            className="link-button"
            onClick={() => onDelete(row.qa_item_id, recording)}
          >
            Remove
          </button>
        </div>
      </div>
      {recording.has_storage ? (
        <audio controls preload="none" src={recording.media_url} />
      ) : (
        <span className="detail-meta">No stored file</span>
      )}
    </div>
  )
}

function AnswerCell({
  answer,
  qaItemId,
  language,
  onRecordingSaved,
  onError,
  onRetakePreview,
}: {
  answer: RecordAnswer
  qaItemId: string
  language: string
  onRecordingSaved: (
    qaItemId: string,
    recordingType: 'question' | 'answer',
    message: string,
    recording: RecordTake,
    choiceLetter?: string,
  ) => void
  onError: (message: string) => void
  onRetakePreview: (blob: Blob) => Promise<boolean>
}) {
  if (answer.kind === 'open') {
    return (
      <div className="record-answer-panel">
        <p>{answer.text || '…'}</p>
        <AnswerRecordingSlot
          qaItemId={qaItemId}
          language={language}
          recording={answer.recording}
          onRecordingSaved={onRecordingSaved}
          onError={onError}
          onRetakePreview={onRetakePreview}
        />
      </div>
    )
  }

  return (
    <ul className="record-answer-slots">
      {answer.slots.map((slot) => (
        <li key={slot.letter}>
          <span className={slot.is_correct ? 'choice-correct' : undefined}>
            {slot.is_correct ? '*' : ''}
            {slot.letter}: {slot.text || '…'}
          </span>
          <AnswerRecordingSlot
            qaItemId={qaItemId}
            language={language}
            choiceLetter={slot.letter}
            recording={slot.recording}
            onRecordingSaved={onRecordingSaved}
            onError={onError}
            onRetakePreview={onRetakePreview}
          />
        </li>
      ))}
    </ul>
  )
}

function AnswerRecordingSlot({
  qaItemId,
  language,
  choiceLetter,
  recording,
  onRecordingSaved,
  onError,
  onRetakePreview,
}: {
  qaItemId: string
  language: string
  choiceLetter?: string
  recording: RecordTake | null
  onRecordingSaved: (
    qaItemId: string,
    recordingType: 'question' | 'answer',
    message: string,
    recording: RecordTake,
    choiceLetter?: string,
  ) => void
  onError: (message: string) => void
  onRetakePreview: (blob: Blob) => Promise<boolean>
}) {
  if (!recording) {
    return (
      <RecordControls
        qaItemId={qaItemId}
        recordingType="answer"
        language={language}
        mode="new"
        label="Record"
        choiceLetter={choiceLetter}
        onComplete={(message, saved) =>
          onRecordingSaved(qaItemId, 'answer', message, saved, choiceLetter)
        }
        onError={onError}
      />
    )
  }

  return (
    <div className="record-answer-controls">
      {recording.has_storage ? (
        <audio controls preload="none" src={recording.media_url} />
      ) : (
        <span className="detail-meta">No stored file</span>
      )}
      <RecordControls
        qaItemId={qaItemId}
        recordingType="answer"
        language={language}
        mode="retake"
        label="Retake"
        choiceLetter={choiceLetter}
        recordingId={recording.id}
        version={recording.version}
        onComplete={(message, saved) =>
          onRecordingSaved(qaItemId, 'answer', message, saved, choiceLetter)
        }
        onError={onError}
        onRetakePreview={onRetakePreview}
      />
    </div>
  )
}
