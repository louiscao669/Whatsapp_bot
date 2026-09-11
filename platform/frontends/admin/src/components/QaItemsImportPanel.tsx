import { useEffect, useState, type FormEvent } from 'react'
import { ApiError } from '../api/client'
import { fetchImportTemplate, importQaItems, importQaItemsFromFile } from '../api/qaItems'

type QaItemsImportPanelProps = {
  onImported: () => void
}

export function QaItemsImportPanel({ onImported }: QaItemsImportPanelProps) {
  const [jsonText, setJsonText] = useState('')
  const [jsonFile, setJsonFile] = useState<File | null>(null)
  const [hint, setHint] = useState('')
  const [minResponses, setMinResponses] = useState(3)
  const [reviewPriority, setReviewPriority] = useState(0)
  const [active, setActive] = useState(true)
  const [skipExisting, setSkipExisting] = useState(true)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const importDefaults = {
    min_responses_required: minResponses,
    review_priority: reviewPriority,
    active,
  }

  useEffect(() => {
    fetchImportTemplate()
      .then((data) => setHint(data.hint))
      .catch(() => {
        /* hint is optional */
      })
  }, [])

  async function handlePasteTemplate() {
    try {
      const data = await fetchImportTemplate()
      setJsonText(data.template)
      setJsonFile(null)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not load template')
    }
  }

  function handleFileChange(file: File | null) {
    setJsonFile(file)
    if (file) {
      setJsonText('')
    }
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!jsonFile && !jsonText.trim()) {
      setError('Upload a JSON file or paste JSON text.')
      return
    }

    setSubmitting(true)
    setError('')
    setMessage('')
    try {
      const result = jsonFile
        ? await importQaItemsFromFile(jsonFile, {
            skip_existing: skipExisting,
            defaults: importDefaults,
          })
        : await importQaItems({
            json_text: jsonText,
            skip_existing: skipExisting,
            defaults: importDefaults,
          })
      setMessage(result.message)
      if (result.errors.length) {
        setError(result.errors.slice(0, 3).join('; '))
      } else {
        setJsonText('')
        setJsonFile(null)
        onImported()
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Import failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="detail-card import-panel">
      <h3>Add questions (JSON)</h3>
      {error ? <p className="error-message">{error}</p> : null}
      {message ? <p className="success-message">{message}</p> : null}
      <form className="mutation-form" onSubmit={handleSubmit}>
        <fieldset>
          <legend>Defaults for imported questions</legend>
          <label htmlFor="import-min-responses">Min responses required</label>
          <input
            id="import-min-responses"
            type="number"
            min={1}
            value={minResponses}
            onChange={(e) => setMinResponses(Number(e.target.value))}
            required
          />
          <label htmlFor="import-review-priority">Review priority</label>
          <input
            id="import-review-priority"
            type="number"
            value={reviewPriority}
            onChange={(e) => setReviewPriority(Number(e.target.value))}
            required
          />
          <label className="checkbox-label">
            <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
            Active (include in auto-assignment)
          </label>
        </fieldset>

        <fieldset>
          <legend>Upload JSON file</legend>
          <input
            id="import-json-file"
            type="file"
            accept=".json,application/json"
            onChange={(e) => handleFileChange(e.target.files?.[0] ?? null)}
          />
          {jsonFile ? <p className="detail-meta">Selected: {jsonFile.name}</p> : null}
        </fieldset>

        <fieldset>
          <legend>Paste JSON</legend>
          <button type="button" className="link-button" onClick={handlePasteTemplate}>
            Paste template
          </button>
          <textarea
            id="import-json-text"
            className="json-textarea"
            value={jsonText}
            onChange={(e) => {
              setJsonText(e.target.value)
              if (e.target.value.trim()) {
                setJsonFile(null)
              }
            }}
            placeholder={hint || 'Paste UW JSON array here…'}
            spellCheck={false}
            disabled={Boolean(jsonFile)}
          />
        </fieldset>

        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={skipExisting}
            onChange={(e) => setSkipExisting(e.target.checked)}
          />
          Skip entries whose passage_id already exists
        </label>
        <button type="submit" className="btn-primary import-questions-button" disabled={submitting}>
          Import questions
        </button>
      </form>
    </section>
  )
}
