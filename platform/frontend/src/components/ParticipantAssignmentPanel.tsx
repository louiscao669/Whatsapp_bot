import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { ApiError } from '../api/client'
import {
  assignParticipantQuestions,
  fetchParticipantAssignmentOptions,
  type ParticipantAssignmentQuestion,
} from '../api/participants'

type Props = { participantId: string; onAssigned: (message: string) => void }

export function ParticipantAssignmentPanel({ participantId, onAssigned }: Props) {
  const [questions, setQuestions] = useState<ParticipantAssignmentQuestion[]>([])
  const [language, setLanguage] = useState('')
  const [selected, setSelected] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const loadOptions = useCallback(() => {
    setLoading(true)
    setError('')
    return fetchParticipantAssignmentOptions(participantId)
      .then((payload) => {
        setQuestions(payload.questions)
        setLanguage(payload.participant_language)
        setSelected({})
      })
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : 'Could not load assignment options'),
      )
      .finally(() => setLoading(false))
  }, [participantId])

  useEffect(() => { loadOptions() }, [loadOptions])

  function toggleQuestion(question: ParticipantAssignmentQuestion, checked: boolean) {
    setSelected((current) => {
      if (checked) return { ...current, [question.id]: '' }
      const next = { ...current }
      delete next[question.id]
      return next
    })
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const selections = Object.entries(selected).map(([qa_item_id, translation_id]) => ({
      qa_item_id, translation_id,
    }))
    if (!selections.length) return setError('Select at least one question.')
    if (selections.some(({ translation_id }) => !translation_id)) {
      return setError('Choose a passage translation for every selected question.')
    }
    setSubmitting(true)
    setError('')
    try {
      const result = await assignParticipantQuestions(participantId, selections)
      onAssigned(result.message)
      await loadOptions()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Assignment failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="detail-card">
      <h3>Assign questions</h3>
      <p className="detail-meta">
        Select questions, then choose a {language || 'participant-language'} passage. Each
        assignment includes the target verse and up to two verses on either side.
      </p>
      {error ? <p className="error-message">{error}</p> : null}
      {loading ? <p className="loading-message">Loading assignment options…</p> :
      questions.length === 0 ? <p>No unassigned questions have compatible passages.</p> : (
        <form onSubmit={handleSubmit}>
          <div className="table-wrap">
            <table className="data-table">
              <thead><tr><th>Select</th><th>QA passage</th><th>Question</th><th>Type</th><th>Passage translation</th></tr></thead>
              <tbody>{questions.map((question) => {
                const isSelected = Object.hasOwn(selected, question.id)
                return <tr key={question.id}>
                  <td><input type="checkbox" checked={isSelected}
                    disabled={!question.translations.length}
                    onChange={(event) => toggleQuestion(question, event.target.checked)}
                    aria-label={`Select ${question.passage}`} /></td>
                  <td>{question.passage}</td>
                  <td className="question-cell">{question.question}</td>
                  <td>{question.question_type.toUpperCase()}</td>
                  <td>{question.translations.length ? (
                    <select value={selected[question.id] ?? ''} disabled={!isSelected}
                      required={isSelected} onChange={(event) => setSelected((current) => ({
                        ...current, [question.id]: event.target.value,
                      }))}>
                      <option value="">Choose passage…</option>
                      {question.translations.map((translation) =>
                        <option key={translation.id} value={translation.id}>
                          {translation.label} — chapter {question.chapter_number}
                        </option>)}
                    </select>
                  ) : `No ${language} passage for chapter ${question.chapter_number}`}</td>
                </tr>
              })}</tbody>
            </table>
          </div>
          <button type="submit" className="btn-primary" disabled={submitting}>
            {submitting ? 'Assigning…' : 'Assign selected questions'}
          </button>
        </form>
      )}
    </section>
  )
}
