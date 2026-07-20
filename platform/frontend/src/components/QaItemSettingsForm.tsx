import { useState, type FormEvent } from 'react'
import { ApiError } from '../api/client'
import { updateQaItemSettings, type QaItemDetail } from '../api/qaItems'

type QaItemSettingsFormProps = {
  item: QaItemDetail
  onUpdated: (item: QaItemDetail) => void
  onMessage: (message: string) => void
  onError: (message: string) => void
}

export function QaItemSettingsForm({ item, onUpdated, onMessage, onError }: QaItemSettingsFormProps) {
  const [minResponses, setMinResponses] = useState(item.settings.min_responses_required)
  const [reviewPriority, setReviewPriority] = useState(item.settings.review_priority)
  const [requiredKeywords, setRequiredKeywords] = useState(item.settings.required_keywords.join('\n'))
  const [optionalKeywords, setOptionalKeywords] = useState(item.settings.optional_keywords.join('\n'))
  const [regenerateRequired, setRegenerateRequired] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    try {
      const result = await updateQaItemSettings(item.id, {
        min_responses_required: minResponses,
        review_priority: reviewPriority,
        required_keywords: requiredKeywords
          .split('\n')
          .map((line) => line.trim())
          .filter(Boolean),
        optional_keywords: optionalKeywords
          .split('\n')
          .map((line) => line.trim())
          .filter(Boolean),
        regenerate_required_keywords: regenerateRequired,
      })
      onUpdated(result.item)
      onMessage(result.message)
    } catch (err) {
      onError(err instanceof ApiError ? err.message : 'Could not save settings')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="detail-card">
      <h3>Question settings</h3>
      <form className="mutation-form" onSubmit={handleSubmit}>
        <label htmlFor="settings-min-responses">Min responses required</label>
        <input
          id="settings-min-responses"
          type="number"
          min={1}
          value={minResponses}
          onChange={(e) => setMinResponses(Number(e.target.value))}
          required
        />
        <label htmlFor="settings-review-priority">Review priority</label>
        <input
          id="settings-review-priority"
          type="number"
          value={reviewPriority}
          onChange={(e) => setReviewPriority(Number(e.target.value))}
          required
        />
        <label htmlFor="settings-required-keywords">Required keywords (one per line)</label>
        <textarea
          id="settings-required-keywords"
          value={requiredKeywords}
          onChange={(e) => setRequiredKeywords(e.target.value)}
          rows={4}
        />
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={regenerateRequired}
            onChange={(e) => setRegenerateRequired(e.target.checked)}
          />
          Replace required keywords from expected answer (ignores edits above)
        </label>
        <label htmlFor="settings-optional-keywords">Optional keywords (one per line)</label>
        <textarea
          id="settings-optional-keywords"
          value={optionalKeywords}
          onChange={(e) => setOptionalKeywords(e.target.value)}
          rows={3}
        />
        <button type="submit" disabled={submitting}>
          Save settings
        </button>
      </form>
    </section>
  )
}
