import { useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../api/client'
import { createStudyParticipant, pilotUrl, type CreatedStudyParticipant } from '../api/participants'

export function StudyParticipantPanel({ onCreated }: { onCreated: () => void }) {
  const [label, setLabel] = useState('')
  const enrolling = useRef(false)
  const [submitting, setSubmitting] = useState(false)
  const [created, setCreated] = useState<CreatedStudyParticipant | null>(null)
  const [error, setError] = useState('')
  const [copyStatus, setCopyStatus] = useState('')

  async function enroll(event: FormEvent) {
    event.preventDefault()
    if (enrolling.current) return
    enrolling.current = true
    setSubmitting(true)
    setError('')
    setCreated(null)
    setCopyStatus('')
    try {
      // Keep the request ID until the server confirms, even across a page reload.
      const storageKey = 'pending_sol_study_enrollment'
      const requestId = sessionStorage.getItem(storageKey) || crypto.randomUUID()
      sessionStorage.setItem(storageKey, requestId)
      const result = await createStudyParticipant(requestId, label)
      sessionStorage.removeItem(storageKey)
      setCreated(result)
      setLabel('')
      onCreated()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not confirm enrollment. Try again to recover the same link.')
    } finally {
      enrolling.current = false
      setSubmitting(false)
    }
  }

  async function copyLink(link: string) {
    try {
      await navigator.clipboard.writeText(link)
      setCopyStatus('Link copied.')
    } catch {
      setCopyStatus('Select and copy the personal link below.')
    }
  }

  return (
    <section className="detail-card">
      <h3>Study enrollment</h3>
      <p className="hint">Each reader gets the 66 Chinese from-scratch questions and a personal link. Conditions rotate across groups of eight readers.</p>
      <form className="mutation-form" onSubmit={enroll}>
        <label htmlFor="study-label">Participant label (optional)</label>
        <input id="study-label" value={label} maxLength={200} onChange={(event) => setLabel(event.target.value)} />
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? 'Creating…' : 'Create study participant'}
        </button>
      </form>
      {error && <p className="error-message" role="alert">{error}</p>}
      {created && (
        <div className="test-participant-result">
          <p><Link to={`/participants/${created.participant_id}`}>{created.display_name}</Link> · Cohort {Math.ceil(created.enrollment_number / 8)} · Rotation {created.rotation} of 8</p>
          <p className="test-participant-link">Personal pilot link: <a href={pilotUrl(created.participant_id)} target="_blank" rel="noreferrer">{pilotUrl(created.participant_id)}</a></p>
          <button type="button" className="btn-secondary btn-sm" onClick={() => copyLink(pilotUrl(created.participant_id))}>Copy pilot link</button>
          <span role="status"> {copyStatus}</span>
        </div>
      )}
    </section>
  )
}
